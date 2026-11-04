"""A site: a group of cameras sharing context (a vessel, a building)."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampedUUIDMixin


class Site(TimestampedUUIDMixin, Base):
    """Mirrors one entry of the sites file; disabled, never deleted, when removed."""

    __tablename__ = "sites"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cameras: Mapped[list[Camera]] = relationship(  # noqa: F821
        back_populates="site", order_by="Camera.key"
    )
