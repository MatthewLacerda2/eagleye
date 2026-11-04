"""One camera's result inside an analysis — the unit a person reviews."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampedUUIDMixin


class Observation(TimestampedUUIDMixin, Base):
    """What the model reported for one camera, and the human review of it."""

    __tablename__ = "observations"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id"), nullable=False, index=True
    )
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    frame_path: Mapped[str | None] = mapped_column(Text)  # None once retention drops it

    review: Mapped[str | None] = mapped_column(String(16))  # correct | incorrect
    review_wrong_events: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    review_missed_events: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera: Mapped[Camera] = relationship()  # noqa: F821
