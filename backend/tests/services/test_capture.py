"""ffmpeg frame grabs succeed, fail and time out without raising."""

import shutil
import subprocess
import time

import pytest

from services import capture

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@needs_ffmpeg
async def test_grab_frame_from_local_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=704x480:rate=10",
         "-t", "2", str(clip)],
        check=True,
    )  # fmt: skip
    jpeg = await capture.grab_frame(str(clip), timeout_s=10, ffmpeg_bin="ffmpeg")
    assert jpeg is not None and jpeg[:2] == b"\xff\xd8"


@needs_ffmpeg
async def test_grab_frame_bad_url_returns_none(tmp_path):
    missing = str(tmp_path / "missing.m3u8")
    assert await capture.grab_frame(missing, timeout_s=10, ffmpeg_bin="ffmpeg") is None


async def test_grab_frame_times_out(tmp_path):
    fake = tmp_path / "fake-ffmpeg"
    fake.write_text("#!/bin/sh\nsleep 30\n")
    fake.chmod(0o755)
    started = time.monotonic()
    assert await capture.grab_frame("x", timeout_s=0.5, ffmpeg_bin=str(fake)) is None
    assert time.monotonic() - started < 2


async def test_missing_ffmpeg_binary_returns_none():
    assert await capture.grab_frame("x", timeout_s=1, ffmpeg_bin="/nonexistent/ffmpeg") is None
