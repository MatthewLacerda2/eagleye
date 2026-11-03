"""Build the Claude request in three layers, the first two cached for an hour.

1. Catalog (``system``): role, the operator's instructions, every event type.
2. Site (first user block): the site's context and all its cameras.
3. Round (after the breakpoints): the time and the frames that changed.

Layers 1 and 2 must be byte-identical between calls — no time, no IDs, sorted
lists — or the cache never hits. Real calls and keep-alives are built by the
same functions for the same reason.
"""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.config import Settings
from core.eagle_config import Catalog
from models import Camera, Site

CACHE_1H = {"type": "ephemeral", "ttl": "1h"}
DESCRIPTION_MAX = 100

_ROLE = """You are an automated security watch. You receive still frames from security \
cameras and report, for each camera, which of the catalogued events below the frame clearly \
shows. Nobody is watching the screens: your report is the watch."""

_RULES = f"""Rules:
- Report only the event keys listed above. Anything else is not an event.
- Judge only what is visible in the frame. When unsure, do not report the event.
- Return one entry per camera you received a frame for, with "events": [] when nothing \
listed is happening.
- "description": at most {DESCRIPTION_MAX} characters, in English, saying what the frame \
shows; when an event is reported, say what in the frame shows it.
- A dark, blurred, fogged or frozen picture is not an event; say so in the description."""


@dataclass(frozen=True)
class RoundFrame:
    """One camera's frame in this round."""

    camera_key: str
    camera_label: str
    jpeg: bytes


def render_system(catalog: Catalog) -> str:
    """Layer 1: role, operator instructions, the event catalog, output rules."""
    parts = [_ROLE, "Operator instructions:\n" + catalog.instructions.strip(), "Events:"]
    for event in sorted(catalog.event_types, key=lambda e: e.key):
        lines = [f'- key "{event.key}" — {event.name}: {event.description.strip()}']
        lines += [f"  Not this event: {c.strip()}" for c in event.counter_examples]
        parts.append("\n".join(lines))
    parts.append(_RULES)
    return "\n\n".join(parts)


def render_site(site: Site, cameras: list[Camera]) -> str:
    """Layer 2: the site and every camera it has, sorted by key."""
    lines = [f"Site: {site.name}", f"Time zone: {site.timezone}"]
    if site.context.strip():
        lines.append("Context:\n" + site.context.strip())
    lines.append("Cameras:")
    for camera in sorted(cameras, key=lambda c: c.key):
        about = f": {camera.description.strip()}" if camera.description.strip() else ""
        lines.append(f'- camera "{camera.key}" — {camera.label}{about}')
    return "\n".join(lines)


def output_schema(catalog: Catalog, camera_keys: list[str]) -> dict[str, Any]:
    """The JSON schema the model must answer with."""
    properties: dict[str, Any] = {
        "camera": {"type": "string", "enum": sorted(camera_keys)},
        "events": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(e.key for e in catalog.event_types)},
        },
        "description": {"type": "string"},
    }
    if catalog.extra_schema is not None:
        properties["extra"] = catalog.extra_schema
    item = {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"cameras": {"type": "array", "items": item}},
        "required": ["cameras"],
        "additionalProperties": False,
    }


def _now_text(site: Site, now_utc: datetime) -> str:
    local = now_utc.astimezone(ZoneInfo(site.timezone))
    return (
        f"Now: {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"(local {local.strftime('%Y-%m-%d %H:%M')}, {site.timezone})."
    )


def _base(
    catalog: Catalog,
    site: Site,
    cameras: list[Camera],
    round_blocks: list[dict],
    settings: Settings,
) -> dict[str, Any]:
    site_block = {"type": "text", "text": render_site(site, cameras), "cache_control": CACHE_1H}
    return {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": settings.ANALYSIS_MAX_TOKENS,
        "system": [{"type": "text", "text": render_system(catalog), "cache_control": CACHE_1H}],
        "messages": [{"role": "user", "content": [site_block, *round_blocks]}],
        "output_config": {
            "effort": "medium",
            "format": {
                "type": "json_schema",
                "schema": output_schema(catalog, [c.key for c in cameras]),
            },
        },
    }


def build_request(
    catalog: Catalog,
    site: Site,
    cameras: list[Camera],
    frames: list[RoundFrame],
    now_utc: datetime,
    settings: Settings,
) -> dict[str, Any]:
    """Keyword arguments for ``client.messages.create`` for one round."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"{_now_text(site, now_utc)} Frames from {len(frames)} cameras follow.",
        }
    ]
    for frame in frames:
        blocks.append(
            {"type": "text", "text": f'Camera "{frame.camera_key}" — {frame.camera_label}:'}
        )
        data = base64.standard_b64encode(frame.jpeg).decode("ascii")
        blocks.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
            }
        )
    return _base(catalog, site, cameras, blocks, settings)


def build_keepalive(
    catalog: Catalog, site: Site, cameras: list[Camera], now_utc: datetime, settings: Settings
) -> dict[str, Any]:
    """The same cached layers with no frames; ``max_tokens`` 1 because 0 rejects formats."""
    text = f"{_now_text(site, now_utc)} Keep-alive: no frames this round; return an empty cameras list."
    request = _base(catalog, site, cameras, [{"type": "text", "text": text}], settings)
    request["max_tokens"] = 1
    return request
