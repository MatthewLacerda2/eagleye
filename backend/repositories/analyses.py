"""Analysis data access: model calls, their usage and cost."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Analysis


async def create(session: AsyncSession, **fields: Any) -> Analysis:
    """Insert an analysis and flush so its id is populated."""
    analysis = Analysis(**fields)
    session.add(analysis)
    await session.flush()
    return analysis


async def get(session: AsyncSession, analysis_id: uuid.UUID) -> Analysis | None:
    """One analysis by id."""
    return await session.get(Analysis, analysis_id)


async def spent_usd_since(session: AsyncSession, since: datetime) -> Decimal:
    """Total cost of analyses started at or after ``since``."""
    total = await session.scalar(
        select(func.coalesce(func.sum(Analysis.cost_usd), 0)).where(Analysis.started_at >= since)
    )
    return Decimal(total)


async def last_started_at(session: AsyncSession, site_id: uuid.UUID) -> datetime | None:
    """When the site's most recent analysis (any kind) started."""
    return await session.scalar(
        select(func.max(Analysis.started_at)).where(Analysis.site_id == site_id)
    )
