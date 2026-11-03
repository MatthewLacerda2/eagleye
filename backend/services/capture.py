"""Grab one frame from a camera feed with ffmpeg.

Camera failures are normal (uplinks drop for hours), so nothing here raises:
any failure — bad URL, non-zero exit, empty output, timeout — returns ``None``.
"""

import asyncio
import contextlib
import logging
import os
import signal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _command(ffmpeg_bin: str, source_url: str, timeout_s: float) -> list[str]:
    args = [ffmpeg_bin, "-nostdin", "-v", "error"]
    if urlparse(source_url).path.endswith(".m3u8"):
        # Start at the newest HLS segment instead of the oldest in the window.
        args += ["-live_start_index", "-1"]
    if "://" in source_url:
        args += ["-rw_timeout", str(int(timeout_s * 1_000_000))]
    args += ["-i", source_url, "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg"]
    return [*args, "-q:v", "3", "-"]


async def grab_frame(source_url: str, timeout_s: float, ffmpeg_bin: str) -> bytes | None:
    """Return one JPEG frame from ``source_url``, or ``None`` on any failure."""
    try:
        process = await asyncio.create_subprocess_exec(
            *_command(ffmpeg_bin, source_url, timeout_s),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group, so a timeout kills every child
        )
    except OSError as exc:
        logger.warning("ffmpeg could not start: %s", exc)
        return None
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout_s)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        return None
    if process.returncode != 0 or not stdout:
        logger.debug("grab failed (%s): %s", process.returncode, stderr[-300:])
        return None
    return stdout
