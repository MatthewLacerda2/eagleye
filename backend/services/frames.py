"""Frame preparation: crop, downscale, JPEG, and the change filter's thumbnail."""

import io
import os
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


def latest_path(frames_dir: str, site_key: str, camera_key: str) -> str:
    """The camera's most recent capture, overwritten every round: ``<dir>/_latest/<site>/<camera>.jpg``.

    Site keys start with a letter, so ``_latest`` never collides with a site's folder.
    """
    return str(Path(frames_dir) / "_latest" / site_key / f"{camera_key}.jpg")


def write(path: str, jpeg: bytes) -> None:
    """Write a frame file whole, creating its directories; a reader never sees half of it."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    partial.write_bytes(jpeg)
    os.replace(partial, target)


def remove(paths: list[str], frames_dir: str) -> None:
    """Delete frame files, then any folder they leave empty, up to ``frames_dir``."""
    root = Path(frames_dir).resolve()
    for path in paths:
        target = Path(path)
        target.unlink(missing_ok=True)
        folder = target.parent.resolve()
        while folder != root and root in folder.parents:
            try:
                folder.rmdir()
            except OSError:  # not empty, or already gone
                break
            folder = folder.parent
