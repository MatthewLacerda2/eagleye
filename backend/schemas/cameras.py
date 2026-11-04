"""Camera status and catalog schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from models import Camera


class CameraStatus(BaseModel):
    """Whether a camera is being watched, and when it last was."""

    id: uuid.UUID
    site_key: str
    site_name: str
    key: str
    label: str
    enabled: bool
    status: str
    last_capture_at: datetime | None
    last_sent_at: datetime | None
    has_frame: bool

    @classmethod
    def from_model(cls, camera: Camera) -> CameraStatus:
        """Flatten a camera with its site."""
        return cls(
            id=camera.id,
            site_key=camera.site.key,
            site_name=camera.site.name,
            key=camera.key,
            label=camera.label,
            enabled=camera.enabled,
            status=camera.status,
            last_capture_at=camera.last_capture_at,
            last_sent_at=camera.last_sent_at,
            has_frame=camera.last_capture_at is not None,
        )


class EventTypeRead(BaseModel):
    """A catalog event type, as the admin needs it."""

    key: str
    name: str
    severity: str
    alert: bool
