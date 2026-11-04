"""Observation endpoints: the morning review."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_catalog, get_db
from core.eagle_config import Catalog
from repositories import analyses as analyses_repo
from repositories import observations as observations_repo
from schemas.frames import JpegResponse
from schemas.observations import AnalysisRead, ObservationDetail, ObservationRead, ReviewWrite

router = APIRouter(prefix="/observations", tags=["observations"])
_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found")


@router.get("", response_model=list[ObservationRead])
async def list_observations(
    only_events: bool = Query(False),
    site: str | None = Query(None),
    event: str | None = Query(None),
    unreviewed: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[ObservationRead]:
    """Newest observations first, filtered."""
    rows = await observations_repo.list_recent(
        session,
        only_events=only_events,
        site_key=site,
        event_key=event,
        unreviewed=unreviewed,
        limit=limit,
        before=before,
    )
    return [ObservationRead.from_model(o) for o in rows]


@router.get("/{observation_id}", response_model=ObservationDetail)
async def get_observation(
    observation_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ObservationDetail:
    """One observation with its analysis and the other cameras analyzed with it."""
    obs = await observations_repo.get(session, observation_id)
    if obs is None:
        raise _NOT_FOUND
    analysis = await analyses_repo.get(session, obs.analysis_id)
    siblings = await observations_repo.list_for_analysis(session, obs.analysis_id)
    return ObservationDetail(
        **ObservationRead.from_model(obs).model_dump(),
        analysis=AnalysisRead.from_model(analysis),
        siblings=[ObservationRead.from_model(s) for s in siblings if s.id != obs.id],
    )


@router.put("/{observation_id}/review", response_model=ObservationRead)
async def review_observation(
    observation_id: uuid.UUID,
    payload: ReviewWrite,
    session: AsyncSession = Depends(get_db),
    catalog: Catalog = Depends(get_catalog),
) -> ObservationRead:
    """Mark an observation correct or incorrect, naming wrong and missed events."""
    obs = await observations_repo.get(session, observation_id)
    if obs is None:
        raise _NOT_FOUND
    wrong, missed = payload.wrong_events, payload.missed_events
    if payload.review == "correct":
        wrong, missed = [], []
    if not set(wrong) <= set(obs.events):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "wrong_events must be flagged")
    if not set(missed) <= {e.key for e in catalog.event_types}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown event in missed_events")
    await observations_repo.set_review(
        session, obs, payload.review, wrong, missed, payload.note, datetime.now(UTC)
    )
    await session.commit()
    return ObservationRead.from_model(obs)


@router.get("/{observation_id}/frame", response_class=JpegResponse)
async def observation_frame(
    observation_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> JpegResponse:
    """The frame the model saw, unless retention has already removed it."""
    obs = await observations_repo.get(session, observation_id)
    if obs is None or obs.frame_path is None or not Path(obs.frame_path).is_file():
        raise _NOT_FOUND
    return JpegResponse(obs.frame_path)
