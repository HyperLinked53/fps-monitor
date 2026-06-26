# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_frame_analyzer.py::test_identical_frame_is_duplicate -v

# Start real-time overlay server (auto-calibrates threshold from first 5s)
python3 server.py

# Start with manual threshold and specific camera index
python3 server.py --camera 1 --threshold 0.3

# Post-process a recorded video
python3 analyze.py "recording.mp4"
python3 analyze.py "recording.mp4" --scale 2.0 --position bottom-right
```

## Architecture

The system has two modes — real-time and post-processing — built on a shared detection module.

**`frame_analyzer.py`** is the core. `FrameAnalyzer` detects real game FPS from a fixed-rate video feed (60fps capture card) by comparing consecutive downsampled grayscale frames. A diff below the threshold = duplicate frame (game didn't render); at or above = new game frame. FPS is a rolling 1-second count of new frames; frametime is ms between them. `detect_threshold()` (also in this file) auto-calibrates by sampling N frames and finding the largest relative gap in the lower half of the diff distribution — the valley between compression-artifact diffs and real frame diffs.

**Real-time mode** (`server.py`): reads from OBS Virtual Camera via OpenCV in a daemon thread, runs `FrameAnalyzer`, and broadcasts JSON `{fps, frametime_ms, is_new_frame, diff}` over WebSocket (port 8765). A second daemon thread serves `overlay/` as static HTTP (port 8080). On startup, runs 5-second calibration via `detect_threshold()` before the analyzer starts. Both servers bind to `localhost` only.

**Browser overlay** (`overlay/`): OBS adds `http://localhost:8080` as a Browser Source. `app.js` connects via WebSocket, renders a scrolling 120-bar frametime canvas, and holds the last valid FPS reading for 2 seconds during static/menu scenes (frames with low visual change) to prevent single-digit drops.

**Post-processing mode** (`analyze.py`): reads a video file, auto-detects threshold from the first 5 seconds, renders the HUD onto each frame using OpenCV drawing, writes video to a temp file, then uses `ffmpeg` (subprocess) to mux the original audio back in. The `--scale` flag (default 2.0) multiplies all HUD dimensions and font sizes proportionally.

## Key Behaviours to Preserve

- `detect_threshold` calls `cap.set(cv2.CAP_PROP_POS_FRAMES, 0)` after sampling — this is a no-op on live cameras but rewinds video files. Don't remove it.
- The rolling-window eviction uses `<=` (not `<`) so a frame at exactly `t=0.0` is not counted at `t=1.0`.
- Both servers bind to `'localhost'`, not `''` — do not change to `0.0.0.0`.
- ffmpeg is called with `-map 1:a:0?` — the `?` makes audio optional so silent recordings don't error.
- The overlay's `MIN_VALID_FPS = 20` hold logic is intentional for menu scenes; do not lower it below 20.
