"""Camera status and the catalog over HTTP."""

from tests.factories import seed_site


async def test_cameras_status(client, auth_headers, db_session):
    site = await seed_site(db_session)
    resp = await client.get("/api/v1/cameras", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert [(r["site_key"], r["key"], r["status"]) for r in rows] == [
        (site.key, "a", "unknown"),
        (site.key, "b", "unknown"),
    ]
    assert rows[0]["has_frame"] is False


async def test_camera_frame_404_before_any_frame(client, auth_headers, db_session):
    site = await seed_site(db_session)
    resp = await client.get(f"/api/v1/cameras/{site.cameras[0].id}/frame", headers=auth_headers)
    assert resp.status_code == 404


async def test_catalog_lists_event_types(client, auth_headers):
    resp = await client.get("/api/v1/catalog", headers=auth_headers)
    assert sorted(e["key"] for e in resp.json()) == [
        "other_vessel",
        "phone_use",
        "sleeping",
        "smoking",
    ]


async def test_camera_frame_serves_the_latest_capture(
    client, auth_headers, db_session, tmp_path, monkeypatch
):
    from core.config import get_settings
    from repositories import sites as sites_repo
    from services import frames

    site = await seed_site(db_session)
    camera = site.cameras[0]
    monkeypatch.setattr(get_settings(), "FRAMES_DIR", str(tmp_path))
    frames.write(frames.latest_path(str(tmp_path), site.key, camera.key), b"\xff\xd8latest")
    await sites_repo.set_camera_status(db_session, camera.id, "online", camera.created_at)
    resp = await client.get(f"/api/v1/cameras/{camera.id}/frame", headers=auth_headers)
    assert resp.status_code == 200 and resp.content == b"\xff\xd8latest"
    rows = (await client.get("/api/v1/cameras", headers=auth_headers)).json()
    assert [r["has_frame"] for r in rows] == [True, False]
