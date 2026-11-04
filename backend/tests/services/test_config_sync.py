"""Syncing the sites file into the database is idempotent and never deletes history."""

from sqlalchemy import func, select

from core.eagle_config import SitesFile
from models import Camera, Site
from services.config_sync import sync_config
from tests.factories import make_analysis, make_observation, seed_site, site_config


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def test_sync_is_idempotent(db_session):
    cfg = site_config()
    await sync_config(db_session, SitesFile(sites=[cfg]))
    await sync_config(db_session, SitesFile(sites=[cfg]))
    assert await _count(db_session, Site) == 1
    assert await _count(db_session, Camera) == 2


async def test_removed_camera_is_disabled_not_deleted(db_session):
    site = await seed_site(db_session)
    camera_b = next(c for c in site.cameras if c.key == "b")
    analysis = await make_analysis(db_session, site)
    await make_observation(db_session, analysis, camera_b)
    await db_session.commit()

    report = await sync_config(db_session, SitesFile(sites=[site_config(cameras=("a",))]))
    await db_session.commit()

    assert report.disabled == 1
    row = await db_session.get(Camera, camera_b.id)
    await db_session.refresh(row)
    assert row is not None and row.enabled is False
    remaining = await sync_config(db_session, SitesFile(sites=[]))
    assert remaining.disabled == 2  # the site and its last camera
