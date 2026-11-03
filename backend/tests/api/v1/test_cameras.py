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
