"""The analyzer turns a model response into results, and never lets a bad one through."""

import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx

from core.config import Settings
from services.analyzer import Analyzer, Usage, compute_cost

CAMS, EVENTS = {"bow", "wheel"}, {"smoking", "other_vessel"}


class FakeClient:
    def __init__(
        self, text: str = "", stop_reason: str = "end_turn", error: Exception | None = None
    ):
        usage = SimpleNamespace(
            input_tokens=100, cache_read_input_tokens=5000,
            cache_creation_input_tokens=None, output_tokens=50,
        )  # fmt: skip
        self.response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=stop_reason, usage=usage, model_dump=lambda mode="json": {"ok": 1},
        )  # fmt: skip
        self.error = error
        self.messages = self

    async def create(self, **kwargs):
        if self.error:
            raise self.error
        return self.response


async def _run(client: FakeClient, kind: str = "round"):
    return await Analyzer(client, Settings()).run({}, CAMS, EVENTS, kind)


def test_compute_cost():
    usage = Usage(
        input_tokens=1000, cache_read_tokens=5000, cache_write_tokens=0, output_tokens=200
    )
    assert compute_cost(usage, Settings()) == Decimal("0.00025")


async def test_analyzer_drops_unknown_camera_and_event():
    body = {"cameras": [
        {"camera": "bow", "events": ["smoking", "dancing"], "description": "x" * 150},
        {"camera": "ghost", "events": ["smoking"], "description": "?"},
    ]}  # fmt: skip
    outcome = await _run(FakeClient(json.dumps(body)))
    assert outcome.status == "ok"
    assert [(r.camera_key, r.events) for r in outcome.results] == [("bow", ["smoking"])]
    assert len(outcome.results[0].description) == 100
    assert outcome.usage.cache_read_tokens == 5000 and outcome.usage.cache_write_tokens == 0


async def test_analyzer_malformed_json_is_failed():
    outcome = await _run(FakeClient("{not json"))
    assert outcome.status == "failed" and outcome.results == []
    assert outcome.cost_usd > 0  # the call was still billed


async def test_analyzer_refusal_is_failed():
    outcome = await _run(FakeClient('{"cameras": []}', stop_reason="refusal"))
    assert outcome.status == "failed" and outcome.stop_reason == "refusal"


async def test_analyzer_api_error_is_failed():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.invalid"))
    outcome = await _run(FakeClient(error=error))
    assert outcome.status == "failed" and outcome.cost_usd == 0


async def test_keepalive_max_tokens_stop_is_ok():
    outcome = await _run(FakeClient("", stop_reason="max_tokens"), kind="keepalive")
    assert outcome.status == "ok" and outcome.results == []


async def test_analyzer_non_object_entry_is_failed_not_raised():
    outcome = await _run(FakeClient(json.dumps({"cameras": ["bow"]})))
    assert outcome.status == "failed" and outcome.error.startswith("bad output")


def test_client_has_a_bounded_timeout():
    from services.analyzer import build_client

    client = build_client(Settings(ANTHROPIC_API_KEY="k"))
    assert client.timeout == 90 and client.max_retries == 2


def test_default_max_tokens_leaves_room_for_thinking_over_20_images():
    assert Settings().ANALYSIS_MAX_TOKENS >= 8000
