"""Worker fixtures: a fake camera feed, a fake Claude, a controllable clock."""

import io
import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PIL import Image

from core.config import Settings
from core.eagle_config import Catalog, EventType
from services.analyzer import Analyzer
from services.change_filter import ChangeFilter
from worker.rounds import RoundDeps


def jpeg(shade: int = 100, block: bool = False) -> bytes:
    image = Image.new("RGB", (704, 480), (shade, shade, shade))
    if block:
        image.paste((250, 250, 250), (200, 150, 500, 400))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


class FakeClaude:
    """Answers for every camera that got a frame; reports `events` for each."""

    def __init__(self, events: list[str] | None = None, fail: bool = False):
        self.events, self.fail, self.calls = events or [], fail, []
        self.messages = self

    async def create(self, **request):
        self.calls.append(request)
        texts = [b["text"] for b in request["messages"][0]["content"] if b["type"] == "text"]
        cams = [m.group(1) for t in texts if (m := re.match(r'Camera "([^"]+)"', t))]
        body = {
            "cameras": [{"camera": c, "events": self.events, "description": "ok"} for c in cams]
        }
        usage = SimpleNamespace(
            input_tokens=500, cache_read_input_tokens=0, cache_creation_input_tokens=4000,
            output_tokens=100,
        )  # fmt: skip
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="{oops" if self.fail else json.dumps(body))],
            stop_reason="end_turn", usage=usage, model_dump=lambda mode="json": {},
        )  # fmt: skip


class Clock:
    def __init__(self, now: datetime = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def make_deps(db_session, tmp_path):
    def _make(feed: dict[str, bytes | None], claude: FakeClaude, clock: Clock, **overrides):
        settings = Settings(FRAMES_DIR=str(tmp_path / "frames"), **overrides)

        @asynccontextmanager
        async def session_factory():
            yield db_session

        async def grab(url: str, timeout_s: float, ffmpeg_bin: str) -> bytes | None:
            return feed.get(url.rsplit("/", 1)[-1].removesuffix(".m3u8"))

        catalog = Catalog(
            instructions="x",
            event_types=[EventType(key="smoking", name="Smoking", description="x")],
        )
        return RoundDeps(
            session_factory=session_factory, grab=grab, change_filter=ChangeFilter(settings),
            analyzer=Analyzer(claude, settings), alert_sender=None, catalog=catalog,
            settings=settings, clock=clock,
        )  # fmt: skip

    return _make
