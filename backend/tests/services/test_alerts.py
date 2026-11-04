"""Alert webhooks: signed, filtered by catalog, rate-limited per camera and event."""

import hashlib
import hmac
import json

import httpx

from core.config import Settings
from core.eagle_config import EventType
from services.alerts import AlertSender
from tests.factories import make_analysis, make_observation, seed_site

TYPES = {
    "smoking": EventType(key="smoking", name="Smoking", description="x", alert=True),
    "other_vessel": EventType(key="other_vessel", name="Boat", description="x", alert=False),
}


async def _no_sleep(_seconds: float) -> None:
    return None


async def _setup(db_session, handler, events=("smoking",), urls="https://hook.invalid/a"):
    site = await seed_site(db_session)
    camera = site.cameras[0]
    obs = await make_observation(
        db_session, await make_analysis(db_session, site), camera, events=list(events)
    )
    settings = Settings(ALERT_WEBHOOK_URLS=urls, ALERT_WEBHOOK_SECRET="s3cret")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sender = AlertSender(http, settings, sleep=_no_sleep)
    return sender, site, camera, obs


async def test_no_urls_no_requests(db_session):
    calls = []
    sender, site, camera, obs = await _setup(db_session, calls.append, urls="")
    assert await sender.send(db_session, site, camera, obs, TYPES) == []
    assert calls == []


async def test_alert_sent_and_signed(db_session):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    sender, site, camera, obs = await _setup(db_session, handler)
    deliveries = await sender.send(db_session, site, camera, obs, TYPES)
    assert [d.status for d in deliveries] == ["sent"]
    body = seen[0].content
    expected = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert seen[0].headers["X-Eagleye-Signature"] == f"sha256={expected}"
    payload = json.loads(body)
    assert payload["events"][0]["key"] == "smoking" and payload["camera"]["key"] == camera.key
    assert payload["url"].endswith(f"/observations/{obs.id}")


async def test_non_alert_event_not_sent(db_session):
    calls = []
    sender, site, camera, obs = await _setup(db_session, calls.append, events=("other_vessel",))
    assert await sender.send(db_session, site, camera, obs, TYPES) == []
    assert calls == []


async def test_cooldown_suppresses_second_alert(db_session):
    sender, site, camera, obs = await _setup(db_session, lambda r: httpx.Response(200))
    assert len(await sender.send(db_session, site, camera, obs, TYPES)) == 1
    assert await sender.send(db_session, site, camera, obs, TYPES) == []


async def test_failed_delivery_recorded_after_retries(db_session):
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(503)

    sender, site, camera, obs = await _setup(db_session, handler)
    deliveries = await sender.send(db_session, site, camera, obs, TYPES)
    assert [(d.status, d.attempts) for d in deliveries] == [("failed", 3)]
    assert len(attempts) == 3 and "503" in deliveries[0].last_error
