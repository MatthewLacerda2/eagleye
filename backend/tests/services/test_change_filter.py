"""Only frames that really changed reach the model; clocks and flicker do not count."""

from datetime import UTC, datetime, timedelta

import numpy as np

from core.config import Settings
from core.eagle_config import Rect
from services.change_filter import CameraChangeState, ChangeFilter

NOW = datetime(2026, 11, 3, 3, 0, tzinfo=UTC)
SETTINGS = Settings()  # 16x12 grid, threshold 12, min 2 cells, mask after 10 samples


def _thumb(value: float = 50.0) -> np.ndarray:
    return np.full((48, 64), value, dtype=np.float32)  # 12 rows x 16 cols of 4x4 px


def _sent_state(flt: ChangeFilter, thumb: np.ndarray) -> CameraChangeState:
    state = CameraChangeState.new(SETTINGS.AUTOMASK_WINDOW)
    assert flt.decide(state, thumb, [], NOW).reason == "first"
    flt.mark_sent(state, thumb, NOW)
    return state


def test_first_frame_is_sent():
    flt = ChangeFilter(SETTINGS)
    decision = flt.decide(CameraChangeState.new(30), _thumb(), [], NOW)
    assert decision.send and decision.reason == "first"


def test_identical_frame_unchanged():
    flt = ChangeFilter(SETTINGS)
    state = _sent_state(flt, _thumb())
    decision = flt.decide(state, _thumb(), [], NOW + timedelta(minutes=2))
    assert not decision.send and decision.reason == "unchanged"


def test_big_change_is_sent():
    flt = ChangeFilter(SETTINGS)
    state = _sent_state(flt, _thumb())
    moved = _thumb()
    moved[20:40, 20:40] = 200
    decision = flt.decide(state, moved, [], NOW + timedelta(minutes=2))
    assert decision.send and decision.reason == "changed" and decision.changed_cells >= 16


def test_clock_cell_is_auto_masked():
    flt = ChangeFilter(SETTINGS)
    state = _sent_state(flt, _thumb())
    reasons = []
    for i in range(1, 15):
        frame = _thumb()
        frame[0:4, 52:64] = 200 if i % 2 else 0  # a 3-cell clock that ticks every capture
        reasons.append(flt.decide(state, frame, [], NOW + timedelta(minutes=2 * i)).reason)
    assert reasons[0] == "changed"  # before the mask is learned
    assert reasons[-1] == "unchanged"  # after it


def test_stale_camera_is_sent():
    flt = ChangeFilter(SETTINGS)
    state = _sent_state(flt, _thumb())
    decision = flt.decide(state, _thumb(), [], NOW + timedelta(minutes=61))
    assert decision.send and decision.reason == "stale"


def test_ignore_rect_excludes_cells():
    flt = ChangeFilter(SETTINGS)
    state = _sent_state(flt, _thumb())
    overlay = _thumb()
    overlay[40:48, 0:16] = 255  # bottom-left 2x4 cells
    ignore = [Rect(x=0, y=0.75, w=0.25, h=0.25)]
    assert flt.decide(state, overlay, ignore, NOW + timedelta(minutes=2)).reason == "unchanged"
