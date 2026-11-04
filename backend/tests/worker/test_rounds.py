"""A round captures, filters, analyzes, stores and alerts — and degrades gracefully."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from models import Analysis, Camera, Observation
from repositories import analyses as analyses_repo
from tests.factories import seed_site
from tests.worker import conftest
from tests.worker.conftest import Clock, FakeClaude, jpeg
from worker.rounds import run_keepalive, run_site_round


async def test_round_stores_observations_and_frames(db_session, make_deps):
    site = await seed_site(db_session)
    claude = FakeClaude(events=["smoking"])
    deps = make_deps({"a": jpeg(), "b": jpeg(50)}, claude, Clock())
    report = await run_site_round(deps, site.id, {})
    assert (report.captured, report.offline, report.sent) == (2, 0, 2)
    observations = (await db_session.scalars(select(Observation))).all()
    assert sorted(o.events[0] for o in observations) == ["smoking", "smoking"]
    assert all(Path(o.frame_path).is_file() for o in observations)
    assert len(claude.calls) == 1


async def test_round_sends_only_changed_cameras(db_session, make_deps):
    site = await seed_site(db_session)
    claude, clock, states = FakeClaude(), Clock(), {}
    feed = {"a": jpeg(), "b": jpeg()}
    await run_site_round(make_deps(feed, claude, clock), site.id, states)
    clock.now += timedelta(minutes=2)
    feed["b"] = jpeg(block=True)
    report = await run_site_round(make_deps(feed, claude, clock), site.id, states)
    assert report.sent == 1 and len(claude.calls) == 2
    second = [b for b in claude.calls[1]["messages"][0]["content"] if b["type"] == "text"]
    assert any('Camera "b"' in b["text"] for b in second)
    assert not any('Camera "a"' in b["text"] for b in second)


async def test_offline_camera_marked_and_skipped(db_session, make_deps):
    site = await seed_site(db_session)
    report = await run_site_round(make_deps({"a": jpeg()}, FakeClaude(), Clock()), site.id, {})
    assert (report.captured, report.offline, report.sent) == (1, 1, 1)
    cams = {c.key: c for c in (await db_session.scalars(select(Camera))).all()}
    for cam in cams.values():
        await db_session.refresh(cam)
    assert cams["a"].status == "online" and cams["b"].status == "offline"


async def test_failed_analysis_does_not_mark_sent(db_session, make_deps):
    site = await seed_site(db_session)
    states, clock = {}, Clock()
    await run_site_round(make_deps({"a": jpeg()}, FakeClaude(fail=True), clock), site.id, states)
    failed = (await db_session.scalars(select(Analysis))).all()
    assert [a.status for a in failed] == ["failed"]
    clock.now += timedelta(minutes=2)
    retry = await run_site_round(make_deps({"a": jpeg()}, FakeClaude(), clock), site.id, states)
    assert retry.sent == 1


async def test_budget_cap_blocks_calls_and_resets_next_utc_day(db_session, make_deps):
    site = await seed_site(db_session)
    clock = Clock(Clock().now.replace(hour=23, minute=59))
    await analyses_repo.create(
        db_session, site_id=site.id, kind="round", status="ok", model="m",
        started_at=clock.now - timedelta(minutes=1), cost_usd=Decimal("30"),
    )  # fmt: skip
    claude = FakeClaude()
    blocked = await run_site_round(make_deps({"a": jpeg()}, claude, clock), site.id, {})
    assert blocked.sent == 0 and claude.calls == []
    clock.now += timedelta(minutes=2)
    resumed = await run_site_round(make_deps({"a": jpeg()}, claude, clock), site.id, {})
    assert resumed.sent == 1 and len(claude.calls) == 1


async def test_keepalive_only_after_idle(db_session, make_deps):
    site = await seed_site(db_session)
    clock, claude, states = Clock(), FakeClaude(), {}
    await run_site_round(make_deps({"a": jpeg()}, claude, clock), site.id, states)
    assert await run_keepalive(make_deps({}, claude, clock), site.id) is False
    clock.now += timedelta(minutes=56)
    assert await run_keepalive(make_deps({}, claude, clock), site.id) is True
    assert claude.calls[-1]["max_tokens"] == 1
    kinds = [a.kind for a in (await db_session.scalars(select(Analysis))).all()]
    assert sorted(kinds) == ["keepalive", "round"]


async def test_no_database_session_held_during_io(db_session, make_deps):
    # Captures take seconds and model calls longer; holding a pooled connection
    # through them exhausts the pool once a few dozen sites overlap.
    site = await seed_site(db_session)
    claude, clock = FakeClaude(), Clock()
    await run_site_round(make_deps({"a": jpeg(), "b": jpeg()}, claude, clock), site.id, {})
    clock.now += timedelta(minutes=56)
    await run_keepalive(make_deps({}, claude, clock), site.id)
    assert conftest.grabs_with_session_open == [0, 0]
    assert claude.sessions_open_during_calls == [0, 0]


async def test_storage_failure_logs_the_unrecorded_cost(db_session, make_deps, monkeypatch, caplog):
    site = await seed_site(db_session)

    async def broken_create(session, **fields):
        raise RuntimeError("db down")

    monkeypatch.setattr(analyses_repo, "create", broken_create)
    deps = make_deps({"a": jpeg()}, FakeClaude(), Clock())
    with pytest.raises(RuntimeError):
        await run_site_round(deps, site.id, {})
    assert "unrecorded cost" in caplog.text


async def test_every_capture_refreshes_latest_even_when_skipped(db_session, make_deps):
    site = await seed_site(db_session)
    claude, clock, states = FakeClaude(), Clock(), {}
    deps = make_deps({"a": jpeg(), "b": None}, claude, clock)
    await run_site_round(deps, site.id, states)
    latest = Path(deps.settings.FRAMES_DIR) / "_latest" / site.key / "a.jpg"
    first = latest.read_bytes()
    clock.now += timedelta(minutes=2)
    report = await run_site_round(
        make_deps({"a": jpeg(101), "b": None}, claude, clock), site.id, states
    )
    assert report.sent == 0 and latest.read_bytes() != first
    assert not (latest.parent / "b.jpg").exists()
