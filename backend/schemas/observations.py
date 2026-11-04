"""Observation request/response schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from models import Analysis, Observation


class ObservationRead(BaseModel):
    """One camera's result, with where it came from and its review."""

    id: uuid.UUID
    analysis_id: uuid.UUID
    observed_at: datetime
    site_key: str
    site_name: str
    camera_key: str
    camera_label: str
    events: list[str]
    description: str
    extra: dict[str, Any] | None
    review: Literal["correct", "incorrect"] | None
    review_wrong_events: list[str]
    review_missed_events: list[str]
    review_note: str | None
    reviewed_at: datetime | None

    @classmethod
    def from_model(cls, obs: Observation) -> ObservationRead:
        """Flatten an observation with its camera and site."""
        return cls(
            id=obs.id,
            analysis_id=obs.analysis_id,
            observed_at=obs.observed_at,
            site_key=obs.camera.site.key,
            site_name=obs.camera.site.name,
            camera_key=obs.camera.key,
            camera_label=obs.camera.label,
            events=obs.events,
            description=obs.description,
            extra=obs.extra,
            review=obs.review,  # type: ignore[arg-type]
            review_wrong_events=obs.review_wrong_events,
            review_missed_events=obs.review_missed_events,
            review_note=obs.review_note,
            reviewed_at=obs.reviewed_at,
        )


class AnalysisRead(BaseModel):
    """The model call behind an observation."""

    id: uuid.UUID
    kind: str
    status: str
    error: str | None
    model: str
    started_at: datetime
    latency_ms: int
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    cost_usd: float

    @classmethod
    def from_model(cls, analysis: Analysis) -> AnalysisRead:
        """Copy an analysis row."""
        fields = {name: getattr(analysis, name) for name in cls.model_fields}
        return cls(**{**fields, "cost_usd": float(analysis.cost_usd)})


class ObservationDetail(ObservationRead):
    """An observation with its analysis and the other cameras analyzed with it."""

    analysis: AnalysisRead
    siblings: list[ObservationRead]


class ReviewWrite(BaseModel):
    """A person's verdict on an observation."""

    review: Literal["correct", "incorrect"]
    wrong_events: list[str] = []
    missed_events: list[str] = []
    note: str | None = None
