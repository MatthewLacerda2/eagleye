"""Call Claude with a built request and turn the response into checked results."""

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import anthropic

from core.config import Settings
from services.prompt import DESCRIPTION_MAX

logger = logging.getLogger(__name__)
_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Usage:
    """Token counts of one call."""

    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class CameraResult:
    """What the model reported for one camera."""

    camera_key: str
    events: list[str]
    description: str
    extra: dict[str, Any] | None


@dataclass(frozen=True)
class AnalysisOutcome:
    """Everything worth storing about one call."""

    status: Literal["ok", "failed"]
    error: str | None
    stop_reason: str | None
    results: list[CameraResult]
    usage: Usage
    cost_usd: Decimal
    latency_ms: int
    raw: dict[str, Any] | None


def compute_cost(usage: Usage, settings: Settings) -> Decimal:
    """Dollar cost of a call from its usage (1-hour cache writes)."""
    price_in = Decimal(str(settings.PRICE_INPUT_PER_MTOK))
    weighted = (
        Decimal(usage.input_tokens)
        + Decimal(usage.cache_read_tokens) * Decimal(str(settings.PRICE_CACHE_READ_MULT))
        + Decimal(usage.cache_write_tokens) * Decimal(str(settings.PRICE_CACHE_WRITE_1H_MULT))
    )
    output = Decimal(usage.output_tokens) * Decimal(str(settings.PRICE_OUTPUT_PER_MTOK))
    return (weighted * price_in + output) / _MILLION


def _usage(response: Any) -> Usage:
    u = response.usage
    return Usage(
        input_tokens=u.input_tokens or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        output_tokens=u.output_tokens or 0,
    )


def _shorten(text: str) -> str:
    """Fit the limit without cutting a word: the model counts characters poorly."""
    text = text.strip()
    if len(text) <= DESCRIPTION_MAX:
        return text
    cut = text[: DESCRIPTION_MAX - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:.") + "…"


def _parse(text: str, cameras: set[str], events: set[str]) -> list[CameraResult]:
    results = []
    for entry in json.loads(text)["cameras"]:
        if entry.get("camera") not in cameras:
            logger.warning("model reported an unknown camera: %r", entry.get("camera"))
            continue
        kept = [e for e in entry.get("events", []) if e in events]
        if len(kept) != len(entry.get("events", [])):
            logger.warning("model reported unknown events: %r", entry.get("events"))
        description = _shorten(str(entry.get("description", "")))
        results.append(CameraResult(entry["camera"], kept, description, entry.get("extra")))
    return results


def build_client(settings: Settings) -> anthropic.AsyncAnthropic:
    """The Claude client, with a timeout so a stalled call cannot hold a site for long."""
    return anthropic.AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.ANALYSIS_TIMEOUT_SECONDS,
        max_retries=2,
    )


class Analyzer:
    """Runs one request; every failure becomes a ``failed`` outcome, never an exception."""

    def __init__(self, client: anthropic.AsyncAnthropic, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _outcome(self, response: Any, started: float, **fields: Any) -> AnalysisOutcome:
        usage = _usage(response) if response is not None else Usage()
        raw = response.model_dump(mode="json") if response is not None else None
        defaults = {
            "error": None,
            "results": [],
            "stop_reason": getattr(response, "stop_reason", None),
        }
        return AnalysisOutcome(
            usage=usage,
            cost_usd=compute_cost(usage, self.settings),
            latency_ms=int((time.monotonic() - started) * 1000),
            raw=raw,
            **{**defaults, **fields},
        )

    async def run(
        self, request: dict[str, Any], valid_cameras: set[str], valid_events: set[str], kind: str
    ) -> AnalysisOutcome:
        """Call the model and check its answer against the cameras and events asked about."""
        started = time.monotonic()
        try:
            response = await self.client.messages.create(**request)
        except anthropic.APIError as exc:
            logger.warning("Claude call failed: %s", exc)
            return self._outcome(None, started, status="failed", error=str(exc)[:500])
        if kind == "keepalive":
            return self._outcome(response, started, status="ok")
        if response.stop_reason in ("refusal", "max_tokens"):
            return self._outcome(response, started, status="failed", error=response.stop_reason)
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            results = _parse(text, valid_cameras, valid_events)
        except Exception as exc:  # any shape the schema should have prevented
            return self._outcome(response, started, status="failed", error=f"bad output: {exc}")
        return self._outcome(response, started, status="ok", results=results)
