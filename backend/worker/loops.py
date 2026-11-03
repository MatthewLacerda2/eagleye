"""Worker process: load config, sync it, then run every site's loop forever."""

import asyncio
import logging
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from prometheus_client import start_http_server

from core.config import Settings, get_settings
from core.database import SessionLocal
from core.eagle_config import ConfigError, load_catalog, load_sites
from repositories import observations as observations_repo
from repositories import sites as sites_repo
from services import metrics
from services.alerts import AlertSender
from services.analyzer import Analyzer, build_client
from services.capture import grab_frame
from services.change_filter import CameraChangeState, ChangeFilter
from services.config_sync import sync_config
from worker.rounds import RoundDeps, run_keepalive, run_site_round

logger = logging.getLogger("eagleye.worker")
Sleep = Callable[[float], Awaitable[None]]
RETENTION_EVERY = timedelta(days=1)


async def site_loop(
    deps: RoundDeps | None,
    site_id: uuid.UUID,
    offset_s: float,
    interval_s: float,
    sleep: Sleep = asyncio.sleep,
    max_iterations: int | None = None,
) -> None:
    """Run one site's rounds forever; an exception costs one round, never the loop."""
    states: dict[uuid.UUID, CameraChangeState] = {}
    await sleep(offset_s)
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        started = time.monotonic()
        try:
            report = await run_site_round(deps, site_id, states)
            logger.info("site %s round: %s", site_id, report)
            await run_keepalive(deps, site_id)
        except Exception:
            logger.exception("site %s round failed", site_id)
        await sleep(max(0.0, interval_s - (time.monotonic() - started)))


async def retention_loop(settings: Settings, sleep: Sleep = asyncio.sleep) -> None:
    """Once a day: delete old unreviewed observations and their frames."""
    while True:
        try:
            cutoff = datetime.now(UTC) - timedelta(days=settings.RETENTION_DAYS)
            async with SessionLocal() as session:
                paths = await observations_repo.delete_older_than(session, cutoff)
                await session.commit()
            for path in paths:
                Path(path).unlink(missing_ok=True)
            logger.info("retention removed %d observations", len(paths))
        except Exception:
            logger.exception("retention failed")
        await sleep(RETENTION_EVERY.total_seconds())


async def cameras_gauge_loop(interval_s: float, sleep: Sleep = asyncio.sleep) -> None:
    """Keep the cameras-online gauge current."""
    while True:
        try:
            async with SessionLocal() as session:
                metrics.cameras_online.set(await sites_repo.count_online(session))
        except Exception:
            logger.exception("cameras gauge failed")
        await sleep(interval_s)


def _fail(message: str) -> None:
    logger.error(message)
    sys.exit(2)


async def main() -> None:
    """Load and sync config, start metrics, and run every site concurrently."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        _fail("ANTHROPIC_API_KEY is not set")
    try:
        catalog = load_catalog(settings.CATALOG_PATH)
        sites_file = load_sites(settings.SITES_PATH)
    except ConfigError as exc:
        _fail(f"invalid configuration: {exc}")
    async with SessionLocal() as session:
        report = await sync_config(session, sites_file)
        await session.commit()
        sites = await sites_repo.list_enabled_sites(session)
    logger.info("config synced: %s", report)
    # Binding does a reverse DNS lookup that can stall for tens of seconds on some
    # hosts; never let it delay the watch.
    threading.Thread(target=start_http_server, args=(settings.METRICS_PORT,), daemon=True).start()

    http = httpx.AsyncClient()
    deps = RoundDeps(
        session_factory=SessionLocal,
        grab=grab_frame,
        change_filter=ChangeFilter(settings),
        analyzer=Analyzer(build_client(settings), settings),
        alert_sender=AlertSender(http, settings),
        catalog=catalog,
        settings=settings,
        capture_slots=asyncio.Semaphore(settings.CAPTURE_CONCURRENCY),
        analysis_slots=asyncio.Semaphore(settings.ANALYSIS_CONCURRENCY),
    )
    interval = settings.ROUND_INTERVAL_SECONDS
    # Stagger sites so their first calls do not all write the shared catalog cache at once.
    tasks = [
        site_loop(deps, site.id, i * interval / max(1, len(sites)), interval)
        for i, site in enumerate(sites)
    ]
    await asyncio.gather(*tasks, retention_loop(settings), cameras_gauge_loop(30))
