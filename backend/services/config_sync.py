"""Bring the database in line with the sites file at worker startup."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.eagle_config import SitesFile
from repositories import sites as sites_repo


@dataclass(frozen=True)
class SyncReport:
    """What a sync did."""

    sites: int
    cameras: int
    disabled: int


async def sync_config(session: AsyncSession, sites: SitesFile) -> SyncReport:
    """Upsert every site and camera by key; disable what the file no longer lists.

    Nothing is deleted, so observations keep their camera. The caller commits.
    """
    cameras = 0
    for cfg in sites.sites:
        site = await sites_repo.upsert_site(session, cfg)
        for camera_cfg in cfg.cameras:
            await sites_repo.upsert_camera(session, site, camera_cfg)
            cameras += 1
    disabled = await sites_repo.disable_missing(
        session,
        {s.key for s in sites.sites},
        {s.key: {c.key for c in s.cameras} for s in sites.sites},
    )
    return SyncReport(sites=len(sites.sites), cameras=cameras, disabled=disabled)
