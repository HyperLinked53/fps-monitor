import numpy as np
import pytest
from analyze import draw_hud, build_hud_frame


def blank_frame(w=1920, h=1080):
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_draw_hud_returns_same_shape():
    frame = blank_frame()
    result = draw_hud(frame.copy(), fps=60, frametime_ms=16.7,
                      history=[16.7] * 120, position='top-right')
    assert result.shape == frame.shape


def test_draw_hud_modifies_frame():
    frame = blank_frame()
    result = draw_hud(frame.copy(), fps=60, frametime_ms=16.7,
                      history=[16.7] * 120, position='top-right')
    assert not np.array_equal(result, frame)


def test_build_hud_frame_returns_bgr_image():
    frame = build_hud_frame(fps=30, frametime_ms=33.3,
                             history=[33.3] * 120, width=200, height=90)
    assert frame.shape == (90, 200, 3)
    assert frame.dtype == np.uint8


@pytest.mark.parametrize('position', [
    'top-right', 'top-left', 'bottom-right', 'bottom-left'
])
def test_all_positions(position):
    frame = blank_frame()
    result = draw_hud(frame.copy(), fps=60, frametime_ms=16.7,
                      history=[16.7] * 120, position=position)
    assert result.shape == frame.shape
