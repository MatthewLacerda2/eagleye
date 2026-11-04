"""Decide, without AI, whether a camera's new frame is worth sending to the model.

The thumbnail is split into a grid. A cell changed when its mean absolute
difference from the last *sent* frame exceeds a threshold (comparing with the
last sent frame, not the last capture, lets slow drift accumulate). A frame is
sent when enough cells changed.

On-screen overlays (clocks, logos, channel labels) sit in different places on
every camera, so instead of hand-drawn masks each camera learns an auto-mask:
cells that changed between most consecutive captures are ignored.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import numpy as np

from core.config import Settings
from core.eagle_config import Rect

Reason = Literal["first", "changed", "stale", "unchanged"]


def cell_diffs(a: np.ndarray, b: np.ndarray, cols: int, rows: int) -> np.ndarray:
    """Mean absolute difference per grid cell, shape ``(rows, cols)``."""
    if b.shape != a.shape:
        ys = np.linspace(0, b.shape[0] - 1, a.shape[0]).round().astype(int)
        xs = np.linspace(0, b.shape[1] - 1, a.shape[1]).round().astype(int)
        b = b[np.ix_(ys, xs)]
    diff = np.abs(a - b)
    out = np.zeros((rows, cols), dtype=np.float32)
    for r, band in enumerate(np.array_split(diff, rows, axis=0)):
        for c, cell in enumerate(np.array_split(band, cols, axis=1)):
            out[r, c] = cell.mean() if cell.size else 0.0
    return out


def ignore_mask(rows: int, cols: int, rects: list[Rect]) -> np.ndarray:
    """Cells overlapping any of ``rects`` (fractions of the frame)."""
    mask = np.zeros((rows, cols), dtype=bool)
    for rect in rects:
        r0, r1 = int(rect.y * rows), int(np.ceil((rect.y + rect.h) * rows))
        c0, c1 = int(rect.x * cols), int(np.ceil((rect.x + rect.w) * cols))
        mask[r0:r1, c0:c1] = True
    return mask


@dataclass
class CameraChangeState:
    """Per-camera memory kept by the worker between rounds."""

    last_capture: np.ndarray | None
    last_sent: np.ndarray | None
    last_sent_at: datetime | None
    history: deque[np.ndarray] = field(default_factory=deque)

    @classmethod
    def new(cls, window: int) -> CameraChangeState:
        """An empty state whose auto-mask remembers ``window`` captures."""
        return cls(None, None, None, deque(maxlen=window))


@dataclass(frozen=True)
class ChangeDecision:
    """Whether to send the frame, and why."""

    send: bool
    reason: Reason
    changed_cells: int


class ChangeFilter:
    """Applies the grid comparison and the auto-mask with the configured thresholds."""

    def __init__(self, settings: Settings) -> None:
        self.cols = settings.CHANGE_GRID_COLS
        self.rows = settings.CHANGE_GRID_ROWS
        self.threshold = settings.CHANGE_CELL_THRESHOLD
        self.min_cells = settings.CHANGE_MIN_CELLS
        self.max_unsent = timedelta(minutes=settings.MAX_UNSENT_MINUTES)
        self.mask_samples = settings.AUTOMASK_MIN_SAMPLES
        self.mask_ratio = settings.AUTOMASK_RATIO

    def _changed(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return cell_diffs(a, b, self.cols, self.rows) > self.threshold

    def _auto_mask(self, state: CameraChangeState) -> np.ndarray:
        if len(state.history) < self.mask_samples:
            return np.zeros((self.rows, self.cols), dtype=bool)
        return np.mean(np.stack(state.history), axis=0) > self.mask_ratio

    def decide(
        self, state: CameraChangeState, thumb: np.ndarray, ignore: list[Rect], now: datetime
    ) -> ChangeDecision:
        """Update the auto-mask with this capture and decide whether to send it."""
        if state.last_capture is not None:
            state.history.append(self._changed(thumb, state.last_capture))
        state.last_capture = thumb
        if state.last_sent is None or state.last_sent_at is None:
            return ChangeDecision(True, "first", 0)
        masked = self._auto_mask(state) | ignore_mask(self.rows, self.cols, ignore)
        changed = int((self._changed(thumb, state.last_sent) & ~masked).sum())
        if now - state.last_sent_at > self.max_unsent:
            return ChangeDecision(True, "stale", changed)
        if changed >= self.min_cells:
            return ChangeDecision(True, "changed", changed)
        return ChangeDecision(False, "unchanged", changed)

    def mark_sent(self, state: CameraChangeState, thumb: np.ndarray, at: datetime) -> None:
        """Remember the frame the model actually received."""
        state.last_sent = thumb
        state.last_sent_at = at
