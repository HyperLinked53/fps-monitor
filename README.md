# FPS & Frametime Monitor

Real-time FPS counter and frametime graph for Switch 2 gameplay captured via OBS with a capture card. Displays as an OBS Browser Source overlay so it shows up in your recordings and stream. Also includes a CLI to burn the overlay into recorded video files after the fact.

![Overlay preview: "58 FPS" with a scrolling green/yellow/red frametime bar graph]

---

## How it works

Your capture card sends a fixed 60fps signal to OBS. When a Switch 2 game runs at 30fps, every frame is duplicated. This tool detects those duplicates by comparing consecutive frames pixel-by-pixel — unique frames count as new renders, letting it calculate the game's actual FPS and the time between frames (frametime).

---

## Requirements

- Python 3.11+
- OBS Studio with Virtual Camera support
- A capture card outputting 60fps to OBS

---

## Installation

```bash
git clone https://github.com/HyperLinked53/fps-monitor.git
cd fps-monitor
pip install -r requirements.txt
```

---

## Real-Time OBS Overlay

### Step 1 — Start OBS Virtual Camera

Open OBS, then:

```
Tools → Virtual Camera → Start Virtual Camera
```

The virtual camera makes your OBS video feed available to other apps as a camera device.

### Step 2 — Start the server

```bash
./start.sh
```

Or directly:

```bash
python server.py
```

You should see:

```
[HTTP] Overlay at http://localhost:8080
[WS]   WebSocket on ws://localhost:8765
[Camera] Reading from device index 0
       In OBS: Add Source → Browser → http://localhost:8080
       Press Ctrl+C to stop.
```

> **Wrong camera?** If you have multiple cameras, try `python server.py --camera 1` or `--camera 2` until the correct feed is detected.

### Step 3 — Add the overlay to OBS

1. In OBS, click **+** in the **Sources** panel
2. Select **Browser**
3. Set the URL to: `http://localhost:8080`
4. Set Width to **224** and Height to **90**
5. Check **"Shutdown source when not visible"**
6. Click **OK**
7. Drag the source to your preferred corner in the scene

### Step 4 — Play

Launch your Switch 2 game. The overlay will show:

- **FPS number** — white at 50+fps, yellow at 30–49fps, red below 30fps
- **Frametime graph** — 120 bars (~2 seconds of history), color-coded per frame:
  - Green: ≤20ms (smooth)
  - Yellow: ≤33ms (mild)
  - Red: >33ms (stutter)
- Subtle grid lines at 16.7ms (60fps target) and 33.3ms (30fps target)

### Step 5 — Stop

Press `Ctrl+C` in the terminal to stop the server.

---

## Post-Processing: Burn Overlay into a Recording

After you've recorded a session with OBS, you can burn the FPS/frametime overlay directly into the video file.

### Basic usage

```bash
python analyze.py your_recording.mkv
```

This reads the video, analyzes every frame, and saves the result as:

```
your_recording_annotated.mp4
```

Progress is printed every 300 frames:

```
[Analyze] 10800 frames @ 60.0fps → your_recording_annotated.mp4
  300/10800 (3%)
  600/10800 (6%)
  ...
[Done] Saved to your_recording_annotated.mp4
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--out <path>` | `<input>_annotated.mp4` | Override the output file path |
| `--threshold <float>` | `1.0` | Frame difference sensitivity. Lower = more sensitive (may false-positive on noisy/grainy footage). Raise to 2.0–3.0 if seeing too many duplicate frames flagged as new. |
| `--position` | `top-right` | HUD corner: `top-right`, `top-left`, `bottom-right`, `bottom-left` |

### Examples

```bash
# Save to a specific path
python analyze.py gameplay.mkv --out gameplay_with_fps.mp4

# Place overlay in bottom-left corner
python analyze.py gameplay.mkv --position bottom-left

# Increase threshold for grainy footage
python analyze.py gameplay.mkv --threshold 2.5

# Combine options
python analyze.py gameplay.mkv --out output.mp4 --position top-left --threshold 1.5
```

---

## Tuning the Threshold

The `--threshold` controls how different two frames must be before they're counted as a new render. The default of `1.0` works well for most Switch 2 games, but you may need to adjust it:

| Situation | Recommended threshold |
|-----------|----------------------|
| Clean capture, solid colors | 0.5–1.0 (default) |
| Games with film grain or noise | 2.0–3.0 |
| FPS reads too high (detecting noise as frames) | Increase |
| FPS reads too low (missing real frames) | Decrease |

---

## Troubleshooting

**"Cannot open camera 0"**
- OBS Virtual Camera isn't running. Go to OBS → Tools → Virtual Camera → Start.
- Try a different camera index: `python server.py --camera 1`

**Overlay shows "-- FPS" and doesn't update**
- The server isn't running, or the Browser Source URL is wrong.
- Make sure the server terminal shows `[Camera] Reading from device index N`.
- Confirm the Browser Source URL is exactly `http://localhost:8080`.

**FPS seems wrong (e.g. shows 60 when game is running at 30)**
- The threshold may be too low — small visual noise is being counted as new frames.
- Try: `python server.py --threshold 2.0`

**Post-processing is very slow**
- This is CPU-bound. A 1-hour 1080p60 recording takes roughly 10–20 minutes depending on your machine.

---

## File Structure

```
fps-monitor/
├── server.py          # Real-time server (WebSocket + HTTP + camera capture)
├── analyze.py         # Post-processing CLI
├── frame_analyzer.py  # Shared frame detection logic
├── start.sh           # Convenience launch script
├── requirements.txt
├── overlay/
│   ├── index.html     # OBS Browser Source page
│   ├── style.css      # Transparent HUD styling
│   └── app.js         # WebSocket client + canvas graph
└── tests/
    ├── test_frame_analyzer.py
    └── test_analyze.py
```
