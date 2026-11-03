"""Observation listing, detail, review and frames over HTTP."""

from datetime import timedelta

from tests.factories import T0, make_analysis, make_observation, seed_site


async def _seed(db_session, tmp_path):
    site = await seed_site(db_session)
    analysis = await make_analysis(db_session, site)
    quiet = await make_observation(db_session, analysis, site.cameras[0], T0)
    flagged = await make_observation(
        db_session, analysis, site.cameras[1], T0 + timedelta(minutes=1), events=["smoking"]
    )
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"\xff\xd8jpeg")
    flagged.frame_path = str(frame)
    await db_session.commit()
    return site, quiet, flagged


async def test_requires_auth(client):
    assert (await client.get("/api/v1/observations")).status_code == 401


async def test_list_filters(client, auth_headers, db_session, tmp_path):
    site, quiet, flagged = await _seed(db_session, tmp_path)
    url = "/api/v1/observations"
    everything = (await client.get(url, headers=auth_headers)).json()
    assert [o["id"] for o in everything] == [str(flagged.id), str(quiet.id)]
    assert everything[0]["site_key"] == site.key and everything[0]["camera_key"] == "b"
    only = await client.get(url, params={"only_events": "true"}, headers=auth_headers)
    assert [o["id"] for o in only.json()] == [str(flagged.id)]


async def test_detail_has_analysis_and_siblings(client, auth_headers, db_session, tmp_path):
    _, quiet, flagged = await _seed(db_session, tmp_path)
    detail = (await client.get(f"/api/v1/observations/{flagged.id}", headers=auth_headers)).json()
    assert detail["analysis"]["model"] == "claude-haiku-5-5"
    assert [s["id"] for s in detail["siblings"]] == [str(quiet.id)]


async def test_review_happy_path(client, auth_headers, db_session, tmp_path):
    _, _, flagged = await _seed(db_session, tmp_path)
    body = {"review": "incorrect", "wrong_events": ["smoking"], "missed_events": ["sleeping"]}
    resp = await client.put(
        f"/api/v1/observations/{flagged.id}/review", json=body, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["review_wrong_events"] == ["smoking"]
    assert resp.json()["review_missed_events"] == ["sleeping"]


async def test_review_rejects_unknown_missed_event(client, auth_headers, db_session, tmp_path):
    _, _, flagged = await _seed(db_session, tmp_path)
    body = {"review": "incorrect", "missed_events": ["dancing"]}
    url = f"/api/v1/observations/{flagged.id}/review"
    assert (await client.put(url, json=body, headers=auth_headers)).status_code == 422
    body = {"review": "incorrect", "wrong_events": ["sleeping"]}  # not flagged
    assert (await client.put(url, json=body, headers=auth_headers)).status_code == 422


async def test_frame_served_and_404_when_file_missing(client, auth_headers, db_session, tmp_path):
    _, quiet, flagged = await _seed(db_session, tmp_path)
    ok = await client.get(f"/api/v1/observations/{flagged.id}/frame", headers=auth_headers)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    missing = await client.get(f"/api/v1/observations/{quiet.id}/frame", headers=auth_headers)
    assert missing.status_code == 404
