"""Observation listing filters and retention."""

from datetime import timedelta

from repositories import observations as observations_repo
from tests.factories import T0, make_analysis, make_observation, seed_site


async def _seed(db_session):
    site = await seed_site(db_session)
    cam = site.cameras[0]
    analysis = await make_analysis(db_session, site)
    quiet = await make_observation(db_session, analysis, cam, T0, events=[])
    event = await make_observation(
        db_session, analysis, cam, T0 + timedelta(minutes=1), events=["smoking"]
    )
    reviewed = await make_observation(
        db_session, analysis, cam, T0 + timedelta(minutes=2), events=["smoking"], review="correct"
    )
    return site, quiet, event, reviewed


async def test_list_recent_filters(db_session):
    site, quiet, event, reviewed = await _seed(db_session)
    kw = {"site_key": None, "event_key": None, "limit": 50, "before": None}

    everything = await observations_repo.list_recent(
        db_session, only_events=False, unreviewed=False, **kw
    )
    assert [o.id for o in everything] == [reviewed.id, event.id, quiet.id]

    events = await observations_repo.list_recent(
        db_session, only_events=True, unreviewed=False, **kw
    )
    assert [o.id for o in events] == [reviewed.id, event.id]

    todo = await observations_repo.list_recent(db_session, only_events=True, unreviewed=True, **kw)
    assert [o.id for o in todo] == [event.id]


async def test_list_recent_by_event_and_before(db_session):
    site, quiet, event, reviewed = await _seed(db_session)
    rows = await observations_repo.list_recent(
        db_session,
        only_events=False,
        unreviewed=False,
        site_key=site.key,
        event_key="smoking",
        limit=50,
        before=reviewed.observed_at,
    )
    assert [o.id for o in rows] == [event.id]


async def test_delete_older_than_keeps_reviewed(db_session):
    site, quiet, event, reviewed = await _seed(db_session)
    paths = await observations_repo.delete_older_than(db_session, T0 + timedelta(hours=1))
    assert sorted(paths) == sorted([quiet.frame_path, event.frame_path])
    assert await observations_repo.get(db_session, reviewed.id) is not None
    assert await observations_repo.get(db_session, quiet.id) is None
