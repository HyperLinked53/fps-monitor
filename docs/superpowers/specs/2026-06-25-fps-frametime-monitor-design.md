# FPS & Frametime Monitor — Design Spec

**Date:** 2026-06-25  
**Status:** Approved

## Overview

A tool that captures real game FPS and frametime from Switch 2 gameplay recorded via OBS with a capture card (60fps output). Operates in two modes:

- **Real-time**: reads OBS Virtual Camera, streams data to an OBS Browser Source overlay
- **Post-processing**: analyzes a recorded video file and burns the overlay into an annotated output video

## Architecture

```
OBS Virtual Camera (60fps)
        │
        ▼
┌──────────────────────┐
│  server.py           │
│  ├─ Frame Analyzer   │  detects new vs duplicate frames
│  └─ WebSocket Server │  streams FPS + frametime to browser
└──────────┬───────────┘
           │  ws://localhost:8765
           ▼
┌──────────────────────┐
│  overlay/index.html  │  OBS Browser Source at localhost:8080
│  FPS number          │
│  Frametime graph     │
└──────────────────────┘

Video file (.mp4/.mkv)
        │
        ▼
┌──────────────────────┐
│  analyze.py          │  CLI — burns overlay into output video
│  (shared analyzer)   │
└──────────────────────┘
```

## Frame Detection Algorithm

The Switch 2 outputs at its native game rate; the capture card always delivers 60fps to OBS. When a game runs at 30fps, every frame is duplicated. We detect real game frames by:

1. Downsample each incoming frame to 320×180 grayscale (fast, ~1ms/frame)
2. Compute mean absolute pixel difference vs previous frame
3. `diff < threshold` → duplicate frame (no new render)
4. `diff ≥ threshold` → new game frame → record timestamp

From this:
- **Game FPS** = count of new frames in a rolling 1-second window
- **Frametime** = ms since the last new frame (16.7ms = 60fps, 33.3ms = 30fps)

Default threshold: `1.0` (tunable via config and `--threshold` CLI flag).

## Overlay Visual Design

Minimal HUD rendered as a transparent Browser Source page:

```
┌─────────────────┐
│ 58 FPS          │   48px monospaced, white. Yellow <50fps, red <30fps
│ ▁▂▃▂▁▂▄▂▁▂▁▃█  │   scrolling bar graph, 120 bars (~2s history)
└─────────────────┘
  semi-transparent dark pill, top-right corner (~200×80px)
```

Frametime bar colors per frame:
- Green: ≤20ms
- Yellow: ≤33ms  
- Red: >33ms (capped at 50ms display height)

Position and opacity are CSS variables for easy customization. OBS setup: add Browser Source → `http://localhost:8080`.

## Post-Processing Pipeline

`python analyze.py <video_file>` workflow:

1. Opens video file, runs frame analyzer on every frame
2. Builds full FPS + frametime dataset for the session
3. Re-renders each frame with the HUD burned in via OpenCV drawing
4. Outputs `<original_filename>_annotated.mp4` in the same directory

CLI flags:
- `--threshold 1.0` — duplicate frame detection sensitivity
- `--out <path>` — override output file path
- `--position top-right|top-left|bottom-right|bottom-left`

## File Structure

```
BenchmarkScript/
├── server.py            # real-time: frame analyzer + WebSocket + HTTP server
├── analyze.py           # post-processing CLI
├── frame_analyzer.py    # shared frame detection logic
├── overlay/
│   ├── index.html       # OBS Browser Source page
│   ├── style.css        # transparent background, HUD styling
│   └── app.js           # WebSocket client + canvas graph renderer
├── requirements.txt
└── start.sh             # convenience launch script
```

## Tech Stack

- Python 3.11+
- `opencv-python` — video capture (Virtual Camera + file) and video writing
- `numpy` — frame difference computation
- `websockets` — WebSocket server
- `asyncio` — async server loop
- Vanilla HTML/CSS/JS — overlay (no framework)
- No ffmpeg dependency — OpenCV handles all video I/O

## Setup Flow

1. `pip install -r requirements.txt`
2. Enable OBS Virtual Camera (Tools → Virtual Camera → Start)
3. `./start.sh` (or `python server.py`)
4. In OBS: Add Source → Browser → URL: `http://localhost:8080` → position in scene
5. Play — overlay is live in OBS
