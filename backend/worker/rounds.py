"""One round for one site, and the keep-alive that keeps its prompt cache warm."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.eagle_config import Catalog, Rect
from models import Camera, Site
from repositories import analyses as analyses_repo
from repositories import observations as observations_repo
from repositories import sites as sites_repo
from services import frames, metrics
from services.alerts import AlertSender
from services.analyzer import AnalysisOutcome, Analyzer
from services.change_filter import CameraChangeState, ChangeFilter
from services.prompt import RoundFrame, build_keepalive, build_request

logger = logging.getLogger(__name__)
Grab = Callable[[str, float, str], Awaitable[bytes | None]]


@dataclass
class RoundDeps:
    """Everything a round needs; tests swap the feed, the model and the clock."""

    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
    grab: Grab
    change_filter: ChangeFilter
    analyzer: Analyzer
    alert_sender: AlertSender | None
    catalog: Catalog
    settings: Settings
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    capture_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(16))
    analysis_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(8))


@dataclass(frozen=True)
class RoundReport:
    """What a round did."""

    captured: int = 0
    offline: int = 0
    sent: int = 0
    analysis_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class _Pending:
    camera: Camera
    state: CameraChangeState
    frame: frames.PreparedFrame


async def _capture(deps: RoundDeps, camera: Camera) -> frames.PreparedFrame | None:
    async with deps.capture_slots:
        with metrics.capture_seconds.time():
            raw = await deps.grab(
                camera.source_url,
                deps.settings.CAPTURE_TIMEOUT_SECONDS,
                deps.settings.CAPTURE_FFMPEG_BIN,
            )
    if raw is None:
        metrics.captures_total.labels("offline").inc()
        return None
    crop = Rect(**camera.crop) if camera.crop else None
    try:
        prepared = await asyncio.to_thread(frames.prepare, raw, crop, deps.settings.FRAME_MAX_SIDE)
    except OSError as exc:  # an undecodable image
        logger.warning("camera %s sent an unreadable frame: %s", camera.key, exc)
        metrics.captures_total.labels("error").inc()
        return None
    metrics.captures_total.labels("ok").inc()
    return prepared


def _today_utc(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def _budget_reached(deps: RoundDeps, session: AsyncSession, now: datetime) -> bool:
    spent = await analyses_repo.spent_usd_since(session, _today_utc(now))
    reached = spent >= deps.settings.DAILY_BUDGET_USD
    metrics.budget_paused.set(1 if reached else 0)
    return reached


def _record_metrics(kind: str, outcome: AnalysisOutcome) -> None:
    metrics.analyses_total.labels(kind, outcome.status).inc()
    metrics.analysis_seconds.observe(outcome.latency_ms / 1000)
    metrics.cost_usd_total.inc(float(outcome.cost_usd))
    usage = outcome.usage
    for name, value in (
        ("input", usage.input_tokens),
        ("cache_read", usage.cache_read_tokens),
        ("cache_write", usage.cache_write_tokens),
        ("output", usage.output_tokens),
    ):
        metrics.tokens_total.labels(name).inc(value)


async def _store_analysis(
    session: AsyncSession,
    deps: RoundDeps,
    site: Site,
    kind: str,
    started: datetime,
    outcome: AnalysisOutcome,
) -> uuid.UUID:
    analysis = await analyses_repo.create(
        session,
        site_id=site.id,
        kind=kind,
        status=outcome.status,
        error=outcome.error,
        model=deps.settings.ANTHROPIC_MODEL,
        stop_reason=outcome.stop_reason,
        started_at=started,
        latency_ms=outcome.latency_ms,
        input_tokens=outcome.usage.input_tokens,
        cache_read_tokens=outcome.usage.cache_read_tokens,
        cache_write_tokens=outcome.usage.cache_write_tokens,
        output_tokens=outcome.usage.output_tokens,
        cost_usd=outcome.cost_usd,
        raw_response=outcome.raw,
    )
    _record_metrics(kind, outcome)
    return analysis.id


async def _analyze_chunk(
    deps: RoundDeps, session: AsyncSession, site: Site, chunk: list[_Pending], now: datetime
) -> uuid.UUID:
    round_frames = [RoundFrame(p.camera.key, p.camera.label, p.frame.jpeg) for p in chunk]
    request = build_request(deps.catalog, site, site.cameras, round_frames, now, deps.settings)
    event_keys = {e.key for e in deps.catalog.event_types}
    async with deps.analysis_slots:
        outcome = await deps.analyzer.run(
            request, {p.camera.key for p in chunk}, event_keys, "round"
        )
    analysis_id = await _store_analysis(session, deps, site, "round", now, outcome)
    by_key = {p.camera.key: p for p in chunk}
    stored = []
    for result in outcome.results if outcome.status == "ok" else []:
        pending = by_key[result.camera_key]
        path = frames.frame_path(deps.settings.FRAMES_DIR, site.key, pending.camera.key, now)
        await asyncio.to_thread(frames.write, path, pending.frame.jpeg)
        obs = await observations_repo.create(
            session,
            analysis_id=analysis_id,
            camera_id=pending.camera.id,
            observed_at=now,
            events=result.events,
            description=result.description,
            extra=result.extra,
            frame_path=path,
        )
        await sites_repo.mark_sent(session, pending.camera, path, now)
        deps.change_filter.mark_sent(pending.state, pending.frame.thumb, now)
        for event in result.events:
            metrics.observations_events_total.labels(event).inc()
        stored.append((pending.camera, obs))
    await session.commit()
    if deps.alert_sender is not None:
        for camera, obs in stored:
            if obs.events:
                deliveries = await deps.alert_sender.send(
                    session, site, camera, obs, deps.catalog.by_key()
                )
                for delivery in deliveries:
                    metrics.alerts_total.labels(delivery.status).inc()
        await session.commit()
    return analysis_id


async def run_site_round(
    deps: RoundDeps, site_id: uuid.UUID, states: dict[uuid.UUID, CameraChangeState]
) -> RoundReport:
    """Capture every camera of the site, analyze the changed ones, store and alert."""
    async with deps.session_factory() as session:
        site = await sites_repo.get_site(session, site_id)
        if site is None or not site.enabled or not site.cameras:
            return RoundReport()
        now = deps.clock()
        captures = await asyncio.gather(*(_capture(deps, c) for c in site.cameras))
        pending: list[_Pending] = []
        for camera, frame in zip(site.cameras, captures, strict=True):
            await sites_repo.set_camera_status(
                session, camera, "online" if frame else "offline", now
            )
            if frame is None:
                continue
            state = states.setdefault(
                camera.id, CameraChangeState.new(deps.settings.AUTOMASK_WINDOW)
            )
            ignore = [Rect(**r) for r in camera.ignore]
            decision = deps.change_filter.decide(state, frame.thumb, ignore, now)
            if decision.send:
                metrics.frames_sent_total.labels(decision.reason).inc()
                pending.append(_Pending(camera, state, frame))
            else:
                metrics.frames_skipped_total.labels(decision.reason).inc()
        await session.commit()
        captured = sum(1 for f in captures if f is not None)
        report = RoundReport(captured=captured, offline=len(captures) - captured)
        if not pending or await _budget_reached(deps, session, now):
            return report
        size = deps.settings.MAX_CAMERAS_PER_CALL
        ids = [
            await _analyze_chunk(deps, session, site, pending[i : i + size], now)
            for i in range(0, len(pending), size)
        ]
        sent = sum(1 for p in pending if p.state.last_sent_at == now)
        return RoundReport(report.captured, report.offline, sent, ids)


async def run_keepalive(deps: RoundDeps, site_id: uuid.UUID) -> bool:
    """Re-read the site's cached prompt layers when it has been idle; return whether sent."""
    settings = deps.settings
    if not settings.KEEPALIVE_ENABLED:
        return False
    async with deps.session_factory() as session:
        site = await sites_repo.get_site(session, site_id)
        if site is None or not any(c.status == "online" for c in site.cameras):
            return False
        now = deps.clock()
        last = await analyses_repo.last_started_at(session, site.id)
        idle = timedelta(minutes=settings.KEEPALIVE_AFTER_MINUTES)
        if last is None or now - last < idle or await _budget_reached(deps, session, now):
            return False
        request = build_keepalive(deps.catalog, site, site.cameras, now, settings)
        async with deps.analysis_slots:
            outcome = await deps.analyzer.run(request, set(), set(), "keepalive")
        await _store_analysis(session, deps, site, "keepalive", now, outcome)
        await session.commit()
        return True
