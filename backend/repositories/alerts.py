"""Alert delivery records."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from models import AlertDelivery


async def create(session: AsyncSession, **fields: Any) -> AlertDelivery:
    """Insert a delivery record and flush."""
    delivery = AlertDelivery(**fields)
    session.add(delivery)
    await session.flush()
    return delivery
