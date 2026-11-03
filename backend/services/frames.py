"""Frame preparation: crop, downscale, JPEG, and the change filter's thumbnail."""

import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from core.eagle_config import Rect

THUMB_WIDTH = 64
JPEG_QUALITY = 80


@dataclass(frozen=True)
class PreparedFrame:
    """A frame ready for the model plus its grayscale thumbnail."""

    jpeg: bytes
    width: int
    height: int
    thumb: np.ndarray


def _crop(image: Image.Image, crop: Rect | None) -> Image.Image:
    if crop is None:
        return image
    w, h = image.size
    box = (
        round(crop.x * w),
        round(crop.y * h),
        round((crop.x + crop.w) * w),
        round((crop.y + crop.h) * h),
    )
    return image.crop(box)


def _fit(image: Image.Image, max_side: int) -> Image.Image:
    w, h = image.size
    scale = max_side / max(w, h)
    if scale >= 1:
        return image
    return image.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)


def _thumb(image: Image.Image) -> np.ndarray:
    w, h = image.size
    size = (THUMB_WIDTH, max(1, round(h * THUMB_WIDTH / w)))
    gray = image.convert("L").resize(size, Image.Resampling.BILINEAR)
    return np.asarray(gray, dtype=np.float32)


def prepare(raw_jpeg: bytes, crop: Rect | None, max_side: int) -> PreparedFrame:
    """Crop (fractions), downscale so the long side is at most ``max_side``, re-encode."""
    image = _fit(_crop(Image.open(io.BytesIO(raw_jpeg)).convert("RGB"), crop), max_side)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return PreparedFrame(buffer.getvalue(), image.width, image.height, _thumb(image))


def frame_path(frames_dir: str, site_key: str, camera_key: str, at: datetime) -> str:
    """Where a sent frame is stored: ``<dir>/<site>/<camera>/<date>/<uuid>.jpg``."""
    return str(
        Path(frames_dir) / site_key / camera_key / at.date().isoformat() / f"{uuid.uuid4()}.jpg"
    )


def write(path: str, jpeg: bytes) -> None:
    """Write a frame file, creating its directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(jpeg)
