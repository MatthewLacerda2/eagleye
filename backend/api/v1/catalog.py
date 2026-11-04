"""The event catalog, for the admin's filters and review choices."""

from fastapi import APIRouter, Depends

from api.deps import get_catalog
from core.eagle_config import Catalog
from schemas.cameras import EventTypeRead

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[EventTypeRead])
async def list_event_types(catalog: Catalog = Depends(get_catalog)) -> list[EventTypeRead]:
    """Every event type the watchman reports."""
    return [
        EventTypeRead(key=e.key, name=e.name, severity=e.severity, alert=e.alert)
        for e in catalog.event_types
    ]
