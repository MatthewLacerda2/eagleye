"""Camera status endpoints: is the watch actually watching?"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from repositories import sites as sites_repo
from schemas.cameras import CameraStatus
from schemas.frames import JpegResponse

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraStatus])
async def list_cameras(session: AsyncSession = Depends(get_db)) -> list[CameraStatus]:
    """Every camera of every enabled site, by site and key."""
    return [CameraStatus.from_model(c) for c in await sites_repo.list_cameras_with_site(session)]


@router.get("/{camera_id}/frame", response_class=JpegResponse)
async def camera_frame(
    camera_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> JpegResponse:
    """The last frame of this camera that the model saw."""
    camera = await sites_repo.get_camera(session, camera_id)
    path = camera.last_sent_frame_path if camera else None
    if path is None or not Path(path).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No frame yet")
    return JpegResponse(path)
