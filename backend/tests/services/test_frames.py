"""Frames are cropped and downscaled before they reach the model."""

import io
from datetime import UTC, datetime

from PIL import Image

from core.eagle_config import Rect
from services import frames


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (120, 80, 40)).save(buffer, "JPEG")
    return buffer.getvalue()


def _size(jpeg: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(jpeg)).size


def test_prepare_downscales_704x480_to_640_wide():
    frame = frames.prepare(_jpeg(704, 480), crop=None, max_side=640)
    assert (frame.width, frame.height) == (640, 436)
    assert _size(frame.jpeg) == (640, 436)
    assert frame.thumb.shape[1] == 64


def test_prepare_never_upscales_352x240():
    frame = frames.prepare(_jpeg(352, 240), crop=None, max_side=640)
    assert (frame.width, frame.height) == (352, 240)


def test_prepare_applies_crop():
    frame = frames.prepare(_jpeg(704, 480), crop=Rect(x=0, y=0, w=0.5, h=0.5), max_side=640)
    assert (frame.width, frame.height) == (352, 240)


def test_frame_path_layout(tmp_path):
    at = datetime(2026, 11, 3, 23, 59, tzinfo=UTC)
    path = frames.frame_path(str(tmp_path), "site-1", "bow", at)
    assert path.startswith(f"{tmp_path}/site-1/bow/2026-11-03/") and path.endswith(".jpg")
    frames.write(path, b"jpeg")
    assert open(path, "rb").read() == b"jpeg"


def test_latest_path_sits_outside_every_site_tree(tmp_path):
    # Site keys start with a letter, so "_latest" can never be a site's directory.
    assert (
        frames.latest_path(str(tmp_path), "site-1", "bow") == f"{tmp_path}/_latest/site-1/bow.jpg"
    )


def test_write_replaces_the_file_whole(tmp_path):
    path = frames.latest_path(str(tmp_path), "s", "bow")
    frames.write(path, b"first")
    frames.write(path, b"second")
    assert open(path, "rb").read() == b"second"
    assert [p.name for p in (tmp_path / "_latest" / "s").iterdir()] == ["bow.jpg"]


def test_remove_deletes_files_and_their_empty_folders(tmp_path):
    at = datetime(2026, 11, 3, tzinfo=UTC)
    gone = frames.frame_path(str(tmp_path), "s", "bow", at)
    kept = frames.frame_path(str(tmp_path), "s", "stern", at)
    frames.write(gone, b"x")
    frames.write(kept, b"y")
    frames.remove([gone, str(tmp_path / "never-existed.jpg")], str(tmp_path))
    assert not (tmp_path / "s" / "bow").exists()
    assert open(kept, "rb").read() == b"y" and tmp_path.is_dir()
