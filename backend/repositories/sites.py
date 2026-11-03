"""Site and camera data access. The only module that issues site/camera SQL."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from core.eagle_config import CameraConfig, SiteConfig
from models import Camera, Site


async def upsert_site(session: AsyncSession, cfg: SiteConfig) -> Site:
    """Create or update the site with ``cfg.key`` and (re-)enable it."""
    site = await session.scalar(select(Site).where(Site.key == cfg.key))
    if site is None:
        site = Site(key=cfg.key)
        session.add(site)
    site.name, site.timezone, site.context, site.enabled = cfg.name, cfg.timezone, cfg.context, True
    await session.flush()
    return site


async def upsert_camera(session: AsyncSession, site: Site, cfg: CameraConfig) -> Camera:
    """Create or update the camera ``cfg.key`` of ``site``."""
    camera = await session.scalar(
        select(Camera).where(Camera.site_id == site.id, Camera.key == cfg.key)
    )
    if camera is None:
        camera = Camera(site_id=site.id, key=cfg.key)
        session.add(camera)
    camera.label = cfg.label
    camera.description = cfg.description
    camera.source_url = cfg.source_url
    camera.crop = cfg.crop.model_dump() if cfg.crop else None
    camera.ignore = [r.model_dump() for r in cfg.ignore]
    camera.enabled = cfg.enabled
    await session.flush()
    return camera


async def disable_missing(
    session: AsyncSession, site_keys: set[str], camera_keys_by_site: dict[str, set[str]]
) -> int:
    """Disable enabled sites/cameras absent from the config; return how many."""
    disabled = 0
    for site in await session.scalars(select(Site).where(Site.enabled.is_(True))):
        if site.key not in site_keys:
            site.enabled = False
            disabled += 1
        keep = camera_keys_by_site.get(site.key, set())
        result = await session.execute(
            update(Camera)
            .where(Camera.site_id == site.id, Camera.enabled.is_(True), Camera.key.not_in(keep))
            .values(enabled=False)
        )
        disabled += result.rowcount
    await session.flush()
    return disabled


async def list_enabled_sites(session: AsyncSession) -> list[Site]:
    """Enabled sites with only their enabled cameras loaded, both sorted by key."""
    result = await session.scalars(
        select(Site)
        .where(Site.enabled.is_(True))
        .options(
            selectinload(Site.cameras),
            with_loader_criteria(Camera, Camera.enabled.is_(True)),
        )
        .order_by(Site.key)
        .execution_options(populate_existing=True)
    )
    return list(result.all())


async def get_site(session: AsyncSession, site_id: uuid.UUID) -> Site | None:
    """One site with its enabled cameras."""
    result = await session.scalars(
        select(Site)
        .where(Site.id == site_id)
        .options(
            selectinload(Site.cameras),
            with_loader_criteria(Camera, Camera.enabled.is_(True)),
        )
        .execution_options(populate_existing=True)
    )
    return result.first()


async def get_camera(session: AsyncSession, camera_id: uuid.UUID) -> Camera | None:
    """One camera with its site."""
    return await session.scalar(
        select(Camera).where(Camera.id == camera_id).options(selectinload(Camera.site))
    )


async def list_cameras_with_site(session: AsyncSession) -> list[Camera]:
    """Every camera of an enabled site, with its site, ordered by site and key."""
    result = await session.scalars(
        select(Camera)
        .join(Site)
        .where(Site.enabled.is_(True))
        .options(selectinload(Camera.site))
        .order_by(Site.key, Camera.key)
    )
    return list(result.all())


async def set_camera_status(
    session: AsyncSession, camera_id: uuid.UUID, status: str, at: datetime
) -> None:
    """Record a capture attempt's outcome."""
    values: dict[str, object] = {"status": status}
    if status == "online":
        values["last_capture_at"] = at
    await session.execute(update(Camera).where(Camera.id == camera_id).values(**values))


async def mark_sent(
    session: AsyncSession, camera_id: uuid.UUID, frame_path: str, at: datetime
) -> None:
    """Record the frame most recently sent to the model."""
    await session.execute(
        update(Camera)
        .where(Camera.id == camera_id)
        .values(last_sent_at=at, last_sent_frame_path=frame_path)
    )


async def count_online(session: AsyncSession) -> int:
    """Enabled cameras whose last capture succeeded."""
    cameras = await list_cameras_with_site(session)
    return sum(1 for c in cameras if c.enabled and c.status == "online")
