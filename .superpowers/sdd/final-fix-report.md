# Final Fix Report

## Fixes Applied

### Fix 1 (Important) — analyze.py: wrap video I/O in try/finally
Wrapped the main frame-processing loop in `analyze()` with a `try/finally` block so that `cap.release()` and `out.release()` are guaranteed to be called even if an exception occurs mid-loop. Without this, the VideoWriter would never write the `moov` atom, resulting in a corrupt output `.mp4`.

### Fix 2 (Important) — server.py: bind to localhost only
Changed both server bindings from `''` (0.0.0.0, all interfaces) to `'localhost'`:
- `HTTPServer(('localhost', HTTP_PORT), handler)` in `_start_http_server()`
- `ws_serve(_ws_handler, 'localhost', WEBSOCKET_PORT)` in `_main()`

This prevents the HTTP and WebSocket servers from being exposed on the LAN.

### Fix 3 (Minor) — overlay/app.js: wrap JSON.parse in try/catch
Wrapped the body of `ws.onmessage` in a `try/catch` block. Malformed WebSocket messages that fail JSON parsing no longer crash the overlay; the error is silently ignored.

### Fix 4 (Minor) — analyze.py: guard against input == output
Added a check immediately after the `cap.isOpened()` guard in `analyze()`:
```python
if os.path.abspath(input_path) == os.path.abspath(output_path):
    print('[ERROR] Input and output paths are the same file.')
    sys.exit(1)
```
This prevents the VideoWriter from clobbering the input file.

## Test Results

Command: `pytest tests/ -v`

```
============================= test session starts ==============================
platform darwin -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
collected 13 items

tests/test_analyze.py::test_draw_hud_returns_same_shape PASSED
tests/test_analyze.py::test_draw_hud_modifies_frame PASSED
tests/test_analyze.py::test_build_hud_frame_returns_bgr_image PASSED
tests/test_analyze.py::test_all_positions[top-right] PASSED
tests/test_analyze.py::test_all_positions[top-left] PASSED
tests/test_analyze.py::test_all_positions[bottom-right] PASSED
tests/test_analyze.py::test_all_positions[bottom-left] PASSED
tests/test_frame_analyzer.py::test_first_frame_is_always_new PASSED
tests/test_frame_analyzer.py::test_identical_frame_is_duplicate PASSED
tests/test_frame_analyzer.py::test_different_frame_is_new PASSED
tests/test_frame_analyzer.py::test_fps_counts_new_frames_in_rolling_window PASSED
tests/test_frame_analyzer.py::test_frametime_is_ms_between_new_frames PASSED
tests/test_frame_analyzer.py::test_reset_clears_state PASSED

============================== 13 passed in 1.54s ==============================
```

**Result: 13/13 tests passed. No regressions.**

## Issues Encountered

None. All fixes applied cleanly and tests passed on first run.
