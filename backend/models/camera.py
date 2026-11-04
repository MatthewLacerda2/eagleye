"""A camera feed belonging to a site, plus its live status."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampedUUIDMixin


class Camera(TimestampedUUIDMixin, Base):
    """Config columns mirror the sites file; status columns are the worker's."""

    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("site_id", "key", name="uq_cameras_site_key"),)

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    crop: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ignore: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    last_capture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_frame_path: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site] = relationship(back_populates="cameras")  # noqa: F821
