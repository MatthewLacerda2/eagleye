"""The prompt keeps its cached layers byte-identical and its schema tied to the catalog."""

from datetime import UTC, datetime, timedelta

from core.config import Settings
from core.eagle_config import Catalog, EventType
from models import Camera, Site
from services.prompt import RoundFrame, build_keepalive, build_request, output_schema

NOW = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)
CATALOG = Catalog(
    instructions="Watch the vessel.",
    event_types=[
        EventType(key="smoking", name="Smoking", description="A lit cigarette."),
        EventType(key="other_vessel", name="Other vessel", description="A boat closes in."),
    ],
)
SITE = Site(key="v1", name="Vessel 1", timezone="America/Sao_Paulo", context="A pusher.")
CAMERAS = [
    Camera(key="wheel", label="Wheelhouse", description="Helm."),
    Camera(key="bow", label="Bow", description=""),
]
FRAMES = [RoundFrame("wheel", "Wheelhouse", b"jpeg-2"), RoundFrame("bow", "Bow", b"jpeg-1")]


def _request(now: datetime = NOW, frames: list[RoundFrame] = FRAMES) -> dict:
    return build_request(CATALOG, SITE, CAMERAS, frames, now, Settings())


def test_layers_are_deterministic():
    a, b = _request(NOW), _request(NOW + timedelta(hours=3))
    assert a["system"] == b["system"]
    assert a["messages"] != b["messages"]


def test_both_cached_layers_live_in_system():
    # Images in messages invalidate the messages cache, never the system cache:
    # with both breakpoints in system, a keep-alive without images warms what
    # real calls with images read.
    request = _request()
    assert [b.get("cache_control") for b in request["system"]] == [
        {"type": "ephemeral", "ttl": "1h"},
        {"type": "ephemeral", "ttl": "1h"},
    ]
    assert not any("cache_control" in b for b in request["messages"][0]["content"])
    assert request["output_config"]["effort"] == "medium"
    assert "thinking" not in request and "temperature" not in request


def test_round_block_contains_now_and_images_in_order():
    content = _request()["messages"][0]["content"]
    assert "2026-11-03T03:00" in content[0]["text"]
    assert "00:00" in content[0]["text"]  # local time in America/Sao_Paulo
    assert [b["type"] for b in content[1:]] == ["text", "image", "text", "image"]
    assert "wheel" in content[1]["text"] and "bow" in content[3]["text"]


def test_site_block_lists_cameras_sorted_by_key():
    site_text = _request()["system"][1]["text"]
    assert site_text.index("bow") < site_text.index("wheel")


def test_schema_enums_match_catalog_and_cameras():
    item = output_schema(CATALOG, ["bow", "wheel"])["properties"]["cameras"]["items"]
    assert item["properties"]["camera"]["enum"] == ["bow", "wheel"]
    assert item["properties"]["events"]["items"]["enum"] == ["other_vessel", "smoking"]
    assert item["additionalProperties"] is False
    assert "extra" not in item["properties"]


def test_schema_includes_extra_only_when_configured():
    extra = {
        "type": "object",
        "properties": {"people": {"type": "integer"}},
        "required": ["people"],
        "additionalProperties": False,
    }
    catalog = CATALOG.model_copy(update={"extra_schema": extra})
    item = output_schema(catalog, ["bow"])["properties"]["cameras"]["items"]
    assert item["properties"]["extra"] == extra and "extra" in item["required"]


def test_keepalive_matches_cached_layers_and_has_no_images():
    keepalive = build_keepalive(CATALOG, SITE, CAMERAS, NOW, Settings())
    request = _request()
    assert keepalive["system"] == request["system"]
    assert keepalive["output_config"] == request["output_config"]
    assert keepalive["max_tokens"] == 1
    assert all(b["type"] == "text" for b in keepalive["messages"][0]["content"])
