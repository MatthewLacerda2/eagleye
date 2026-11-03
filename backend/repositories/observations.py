"""Observation data access: what the model saw, and its human review."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import AlertDelivery, Camera, Observation, Site

_WITH_CAMERA = selectinload(Observation.camera).selectinload(Camera.site)


async def create(session: AsyncSession, **fields: Any) -> Observation:
    """Insert an observation and flush so its id is populated."""
    observation = Observation(**fields)
    session.add(observation)
    await session.flush()
    return observation


async def get(session: AsyncSession, observation_id: uuid.UUID) -> Observation | None:
    """One observation with its camera and site."""
    return await session.scalar(
        select(Observation).where(Observation.id == observation_id).options(_WITH_CAMERA)
    )


async def list_recent(
    session: AsyncSession,
    *,
    only_events: bool,
    site_key: str | None,
    event_key: str | None,
    unreviewed: bool,
    limit: int,
    before: datetime | None,
) -> list[Observation]:
    """Newest first, filtered; ``before`` pages backwards by ``observed_at``."""
    query = select(Observation).options(_WITH_CAMERA)
    if only_events:
        query = query.where(func.cardinality(Observation.events) > 0)
    if unreviewed:
        query = query.where(Observation.review.is_(None))
    if event_key:
        query = query.where(Observation.events.any(event_key))
    if before:
        query = query.where(Observation.observed_at < before)
    if site_key:
        query = query.join(Camera).join(Site).where(Site.key == site_key)
    query = query.order_by(Observation.observed_at.desc()).limit(limit)
    return list((await session.scalars(query)).all())


async def list_for_analysis(session: AsyncSession, analysis_id: uuid.UUID) -> list[Observation]:
    """Every observation produced by one analysis."""
    result = await session.scalars(
        select(Observation)
        .where(Observation.analysis_id == analysis_id)
        .options(_WITH_CAMERA)
        .order_by(Observation.observed_at)
    )
    return list(result.all())


async def set_review(
    session: AsyncSession,
    observation: Observation,
    review: str,
    wrong: list[str],
    missed: list[str],
    note: str | None,
    at: datetime,
) -> Observation:
    """Store a person's verdict on an observation."""
    observation.review = review
    observation.review_wrong_events = wrong
    observation.review_missed_events = missed
    observation.review_note = note
    observation.reviewed_at = at
    await session.flush()
    return observation


async def last_alerted_at(
    session: AsyncSession, camera_id: uuid.UUID, event_key: str
) -> datetime | None:
    """When an alert for this camera and event was last attempted."""
    return await session.scalar(
        select(func.max(AlertDelivery.created_at)).where(
            AlertDelivery.camera_id == camera_id, AlertDelivery.event_key == event_key
        )
    )


async def delete_older_than(session: AsyncSession, cutoff: datetime) -> list[str]:
    """Delete unreviewed observations older than ``cutoff``; return their frame paths."""
    result = await session.execute(
        delete(Observation)
        .where(Observation.observed_at < cutoff, Observation.review.is_(None))
        .returning(Observation.frame_path)
    )
    paths = list(result.scalars().all())
    await session.flush()
    return paths
