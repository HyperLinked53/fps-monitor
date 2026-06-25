import numpy as np
import pytest
from frame_analyzer import FrameAnalyzer


def gray_frame(value: int) -> np.ndarray:
    """Create a uniform BGR frame filled with the given value (0–255)."""
    return np.full((180, 320, 3), value, dtype=np.uint8)


def test_first_frame_is_always_new():
    fa = FrameAnalyzer()
    result = fa.process_frame(gray_frame(0), timestamp=0.0)
    assert result['is_new_frame'] is True


def test_identical_frame_is_duplicate():
    fa = FrameAnalyzer()
    fa.process_frame(gray_frame(128), timestamp=0.0)
    result = fa.process_frame(gray_frame(128), timestamp=0.016)
    assert result['is_new_frame'] is False


def test_different_frame_is_new():
    fa = FrameAnalyzer()
    fa.process_frame(gray_frame(0), timestamp=0.0)
    result = fa.process_frame(gray_frame(255), timestamp=0.016)
    assert result['is_new_frame'] is True


def test_fps_counts_new_frames_in_rolling_window():
    fa = FrameAnalyzer()
    # 60 distinct frames over 1 second = 60 fps
    for i in range(60):
        frame = gray_frame(i % 2 * 200)  # alternates 0 and 200 — always new
        fa.process_frame(frame, timestamp=i * (1 / 60))
    result = fa.process_frame(gray_frame(0), timestamp=1.0)
    assert result['fps'] == 60


def test_frametime_is_ms_between_new_frames():
    fa = FrameAnalyzer()
    fa.process_frame(gray_frame(0), timestamp=0.0)
    fa.process_frame(gray_frame(255), timestamp=0.0333)
    result = fa.process_frame(gray_frame(0), timestamp=0.0666)
    assert abs(result['frametime_ms'] - 33.3) < 1.0


def test_reset_clears_state():
    fa = FrameAnalyzer()
    fa.process_frame(gray_frame(0), timestamp=0.0)
    fa.reset()
    result = fa.process_frame(gray_frame(0), timestamp=1.0)
    assert result['is_new_frame'] is True
    assert result['fps'] == 0
