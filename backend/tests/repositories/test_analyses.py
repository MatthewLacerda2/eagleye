"""Spend accounting for the daily budget cap."""

from datetime import timedelta
from decimal import Decimal

from repositories import analyses as analyses_repo
from tests.factories import T0, make_analysis, seed_site


async def test_spent_usd_since_sums_only_after_cutoff(db_session):
    site = await seed_site(db_session)
    await make_analysis(db_session, site, started_at=T0 - timedelta(hours=1), cost="1.5")
    await make_analysis(db_session, site, started_at=T0 + timedelta(minutes=1), cost="0.25")
    await make_analysis(db_session, site, started_at=T0 + timedelta(minutes=2), cost="0.5")

    assert await analyses_repo.spent_usd_since(db_session, T0) == Decimal("0.75")


async def test_last_started_at_is_the_latest(db_session):
    site = await seed_site(db_session)
    assert await analyses_repo.last_started_at(db_session, site.id) is None
    await make_analysis(db_session, site, started_at=T0)
    await make_analysis(db_session, site, started_at=T0 + timedelta(minutes=5))
    assert await analyses_repo.last_started_at(db_session, site.id) == T0 + timedelta(minutes=5)
