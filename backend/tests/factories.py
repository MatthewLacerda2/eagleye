"""Builders shared by repository, service and worker tests."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.eagle_config import CameraConfig, SiteConfig, SitesFile
from models import Analysis, Camera, Observation, Site
from repositories import analyses as analyses_repo
from repositories import observations as observations_repo
from repositories import sites as sites_repo
from services.config_sync import sync_config

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def site_config(key: str = "s1", cameras: tuple[str, ...] = ("a", "b")) -> SiteConfig:
    cams = [
        CameraConfig(key=c, label=c.upper(), source_url=f"https://example.invalid/{c}.m3u8")
        for c in cameras
    ]
    return SiteConfig(key=key, name=key.upper(), timezone="UTC", cameras=cams)


async def seed_site(session: AsyncSession, cfg: SiteConfig | None = None) -> Site:
    cfg = cfg or site_config()
    await sync_config(session, SitesFile(sites=[cfg]))
    await session.commit()
    sites = await sites_repo.list_enabled_sites(session)
    return next(s for s in sites if s.key == cfg.key)


async def make_analysis(
    session: AsyncSession, site: Site, started_at: datetime = T0, cost: str = "0.001"
) -> Analysis:
    return await analyses_repo.create(
        session,
        site_id=site.id,
        kind="round",
        status="ok",
        model="claude-haiku-5-5",
        started_at=started_at,
        latency_ms=100,
        input_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=0,
        cost_usd=Decimal(cost),
    )


async def make_observation(
    session: AsyncSession,
    analysis: Analysis,
    camera: Camera,
    observed_at: datetime = T0,
    events: list[str] | None = None,
    review: str | None = None,
) -> Observation:
    return await observations_repo.create(
        session,
        analysis_id=analysis.id,
        camera_id=camera.id,
        observed_at=observed_at,
        events=events or [],
        description="something",
        frame_path=f"/frames/{camera.key}.jpg",
        review=review,
    )
