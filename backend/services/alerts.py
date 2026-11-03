"""Send an alert to every configured webhook when an observation shows an alert event."""

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.eagle_config import EventType
from models import AlertDelivery, Camera, Observation, Site
from repositories import alerts as alerts_repo
from repositories import observations as observations_repo

logger = logging.getLogger(__name__)
BACKOFF_SECONDS = (1, 4)  # waits between the 3 attempts
SIGNATURE_HEADER = "X-Eagleye-Signature"


def build_payload(
    site: Site,
    camera: Camera,
    obs: Observation,
    event_types: dict[str, EventType],
    public_base_url: str,
) -> dict[str, Any]:
    """The JSON body every webhook receives."""
    return {
        "site": {"key": site.key, "name": site.name},
        "camera": {"key": camera.key, "label": camera.label},
        "events": [
            {"key": k, "name": event_types[k].name, "severity": event_types[k].severity}
            for k in obs.events
            if k in event_types
        ],
        "description": obs.description,
        "extra": obs.extra,
        "observed_at": obs.observed_at.astimezone(UTC).isoformat(),
        "url": f"{public_base_url.rstrip('/')}/observations/{obs.id}",
    }


def sign(body: bytes, secret: str) -> str:
    """Hex HMAC-SHA256 of the body."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class AlertSender:
    """Posts alerts with retries and records every delivery."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.http = http
        self.settings = settings
        self.sleep = sleep
        self.clock = clock

    async def _due(self, session: AsyncSession, camera: Camera, event_key: str) -> bool:
        last = await observations_repo.last_alerted_at(session, camera.id, event_key)
        cooldown = timedelta(minutes=self.settings.ALERT_COOLDOWN_MINUTES)
        return last is None or self.clock() - last >= cooldown

    async def _post(self, url: str, body: bytes) -> tuple[bool, int, str | None]:
        headers = {"Content-Type": "application/json"}
        if self.settings.ALERT_WEBHOOK_SECRET:
            headers[SIGNATURE_HEADER] = "sha256=" + sign(body, self.settings.ALERT_WEBHOOK_SECRET)
        error = None
        for attempt in range(1, len(BACKOFF_SECONDS) + 2):
            try:
                response = await self.http.post(url, content=body, headers=headers, timeout=10)
                if response.is_success:
                    return True, attempt, None
                error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"
            if attempt <= len(BACKOFF_SECONDS):
                await self.sleep(BACKOFF_SECONDS[attempt - 1])
        return False, len(BACKOFF_SECONDS) + 1, error

    async def send(
        self,
        session: AsyncSession,
        site: Site,
        camera: Camera,
        obs: Observation,
        event_types: dict[str, EventType],
    ) -> list[AlertDelivery]:
        """Alert on every alert-worthy event of ``obs`` that is not cooling down."""
        urls = self.settings.alert_webhook_urls_list
        if not urls:
            return []
        due = [
            k
            for k in obs.events
            if k in event_types and event_types[k].alert and await self._due(session, camera, k)
        ]
        if not due:
            return []
        payload = build_payload(site, camera, obs, event_types, self.settings.PUBLIC_BASE_URL)
        body = json.dumps(payload).encode()
        deliveries = []
        for url in urls:
            ok, attempts, error = await self._post(url, body)
            if not ok:
                logger.warning("alert to %s failed after %d attempts: %s", url, attempts, error)
            for key in due:
                deliveries.append(
                    await alerts_repo.create(
                        session,
                        observation_id=obs.id,
                        camera_id=camera.id,
                        url=url,
                        event_key=key,
                        status="sent" if ok else "failed",
                        attempts=attempts,
                        last_error=error,
                    )
                )
        return deliveries
