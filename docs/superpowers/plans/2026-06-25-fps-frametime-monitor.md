# FPS & Frametime Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool that detects real game FPS from a 60fps capture card feed and displays it as an OBS Browser Source overlay, with a post-processing mode to burn the overlay into recorded video files.

**Architecture:** A shared `FrameAnalyzer` class detects new vs duplicate frames by comparing downsampled grayscale frames. In real-time mode, `server.py` reads from OBS Virtual Camera, runs the analyzer, and broadcasts FPS/frametime over WebSocket to a local HTML page that OBS loads as a Browser Source. In post-processing mode, `analyze.py` runs the same analyzer on a video file and burns the HUD onto each frame using OpenCV.

**Tech Stack:** Python 3.11+, opencv-python, numpy, websockets, asyncio, vanilla HTML/CSS/JS

## Global Constraints

- Python 3.11+
- opencv-python for all video I/O and frame processing (no ffmpeg)
- Capture card outputs at 60fps to OBS Virtual Camera
- WebSocket server on port 8765, HTTP server on port 8080
- Default duplicate-frame threshold: 1.0 (mean absolute pixel difference, 0–255 scale)
- Default overlay position: top-right corner
- Frametime bar graph: 120 bars, ~2 seconds of history at 60fps
- Bar color thresholds: green ≤20ms, yellow ≤33ms, red >33ms, display capped at 50ms max height

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `start.sh`
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: nothing consumed by other tasks — scaffold only

- [ ] **Step 1: Create requirements.txt**

```
opencv-python>=4.9.0
numpy>=1.26.0
websockets>=12.0
pytest>=8.0.0
```

- [ ] **Step 2: Create start.sh**

```bash
#!/usr/bin/env bash
set -e
python server.py "$@"
```

- [ ] **Step 3: Make start.sh executable and create tests directory**

```bash
chmod +x start.sh
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all four packages install without error.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt start.sh tests/
git commit -m "feat: project scaffold"
```

---

### Task 2: Frame Analyzer

**Files:**
- Create: `frame_analyzer.py`
- Create: `tests/test_frame_analyzer.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `FrameAnalyzer(threshold: float = 1.0)` — class
  - `FrameAnalyzer.process_frame(frame: np.ndarray, timestamp: float) -> dict` — returns `{'is_new_frame': bool, 'fps': int, 'frametime_ms': float, 'diff': float}`
  - `FrameAnalyzer.reset() -> None` — clears all internal state

- [ ] **Step 1: Write failing tests**

`tests/test_frame_analyzer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_frame_analyzer.py -v
```

Expected: `ImportError: No module named 'frame_analyzer'`

- [ ] **Step 3: Implement frame_analyzer.py**

```python
from collections import deque
import numpy as np
import cv2


class FrameAnalyzer:
    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self._prev_gray: np.ndarray | None = None
        self._new_frame_timestamps: deque[float] = deque()
        self._last_new_frame_time: float | None = None

    def process_frame(self, frame: np.ndarray, timestamp: float) -> dict:
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

        if self._prev_gray is None:
            self._prev_gray = gray
            self._last_new_frame_time = timestamp
            self._new_frame_timestamps.append(timestamp)
            return {'is_new_frame': True, 'fps': 0, 'frametime_ms': 0.0, 'diff': 0.0}

        diff = float(np.mean(np.abs(gray - self._prev_gray)))
        is_new = diff >= self.threshold

        if is_new:
            self._prev_gray = gray
            frametime_ms = (timestamp - self._last_new_frame_time) * 1000
            self._last_new_frame_time = timestamp
            self._new_frame_timestamps.append(timestamp)
        else:
            frametime_ms = (timestamp - self._last_new_frame_time) * 1000

        # Evict timestamps older than 1 second
        cutoff = timestamp - 1.0
        while self._new_frame_timestamps and self._new_frame_timestamps[0] < cutoff:
            self._new_frame_timestamps.popleft()

        return {
            'is_new_frame': is_new,
            'fps': len(self._new_frame_timestamps),
            'frametime_ms': round(frametime_ms, 1),
            'diff': round(diff, 3),
        }

    def reset(self) -> None:
        self._prev_gray = None
        self._new_frame_timestamps.clear()
        self._last_new_frame_time = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_frame_analyzer.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frame_analyzer.py tests/test_frame_analyzer.py
git commit -m "feat: frame analyzer with duplicate detection and fps/frametime tracking"
```

---

### Task 3: Real-Time Server

**Files:**
- Create: `server.py`

**Interfaces:**
- Consumes: `FrameAnalyzer` from `frame_analyzer.py`
- Produces:
  - HTTP server at `http://localhost:8080` serving the `overlay/` directory
  - WebSocket server at `ws://localhost:8765` broadcasting JSON: `{'fps': int, 'frametime_ms': float, 'is_new_frame': bool, 'diff': float}`

- [ ] **Step 1: Implement server.py**

```python
import asyncio
import json
import os
import sys
import threading
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import cv2

from frame_analyzer import FrameAnalyzer

try:
    from websockets.server import serve as ws_serve
except ImportError:
    print("Missing dependency: pip install websockets")
    sys.exit(1)

WEBSOCKET_PORT = 8765
HTTP_PORT = 8080
BROADCAST_INTERVAL = 1 / 60

_clients: set = set()
_latest: dict = {'fps': 0, 'frametime_ms': 0.0, 'is_new_frame': False, 'diff': 0.0}


async def _ws_handler(websocket):
    _clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        _clients.discard(websocket)


async def _broadcaster():
    while True:
        if _clients:
            msg = json.dumps(_latest)
            await asyncio.gather(
                *[c.send(msg) for c in list(_clients)],
                return_exceptions=True,
            )
        await asyncio.sleep(BROADCAST_INTERVAL)


def _start_http_server():
    overlay_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'overlay')
    handler = partial(SimpleHTTPRequestHandler, directory=overlay_dir)
    server = HTTPServer(('', HTTP_PORT), handler)
    print(f"[HTTP] Overlay at http://localhost:{HTTP_PORT}")
    server.serve_forever()


def _camera_loop(camera_index: int, threshold: float):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(
            f"[ERROR] Cannot open camera {camera_index}. "
            "Make sure OBS Virtual Camera is running. Try --camera 1 or --camera 2."
        )
        return

    analyzer = FrameAnalyzer(threshold=threshold)
    print(f"[Camera] Reading from device index {camera_index}")

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue
        result = analyzer.process_frame(frame, time.time())
        _latest.update(result)


async def _main(camera_index: int, threshold: float):
    threading.Thread(target=_start_http_server, daemon=True).start()
    threading.Thread(
        target=_camera_loop, args=(camera_index, threshold), daemon=True
    ).start()

    print(f"[WS]   WebSocket on ws://localhost:{WEBSOCKET_PORT}")
    print("       In OBS: Add Source → Browser → http://localhost:8080")
    print("       Press Ctrl+C to stop.\n")

    async with ws_serve(_ws_handler, '', WEBSOCKET_PORT):
        await _broadcaster()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='FPS/Frametime OBS overlay server')
    parser.add_argument('--camera', type=int, default=0,
                        help='Camera device index for OBS Virtual Camera (default: 0)')
    parser.add_argument('--threshold', type=float, default=1.0,
                        help='Frame difference threshold for new-frame detection (default: 1.0)')
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.camera, args.threshold))
    except KeyboardInterrupt:
        print('\n[Server] Stopped.')
```

- [ ] **Step 2: Verify server starts**

Enable OBS Virtual Camera first (OBS → Tools → Virtual Camera → Start), then:

```bash
python server.py
```

Expected output:
```
[HTTP] Overlay at http://localhost:8080
[WS]   WebSocket on ws://localhost:8765
[Camera] Reading from device index 0
       In OBS: Add Source → Browser → http://localhost:8080
       Press Ctrl+C to stop.
```

If camera 0 fails, try `python server.py --camera 1` or `--camera 2`.

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: real-time websocket + http server with camera capture"
```

---

### Task 4: Browser Overlay

**Files:**
- Create: `overlay/index.html`
- Create: `overlay/style.css`
- Create: `overlay/app.js`

**Interfaces:**
- Consumes: WebSocket at `ws://localhost:8765` — messages are JSON `{'fps': int, 'frametime_ms': float, 'is_new_frame': bool}`
- Produces: Browser Source page at `http://localhost:8080`

- [ ] **Step 1: Create overlay/index.html**

```bash
mkdir -p overlay
```

`overlay/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FPS Monitor</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div id="hud">
    <div id="fps">-- FPS</div>
    <canvas id="graph" width="200" height="40"></canvas>
  </div>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create overlay/style.css**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: transparent;
  overflow: hidden;
}

#hud {
  position: fixed;
  top: 12px;
  right: 12px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 8px;
  padding: 8px 12px 6px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  min-width: 200px;
}

#fps {
  font-family: 'Courier New', Courier, monospace;
  font-size: 28px;
  font-weight: bold;
  color: #ffffff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
  letter-spacing: 1px;
  line-height: 1;
}

#graph {
  display: block;
  width: 200px;
  height: 40px;
}
```

- [ ] **Step 3: Create overlay/app.js**

```javascript
const WS_URL = 'ws://localhost:8765';
const HISTORY_SIZE = 120;
const MAX_FRAMETIME_MS = 50;

const fpsEl = document.getElementById('fps');
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');

const history = new Array(HISTORY_SIZE).fill(0);
let currentFps = 0;
let connected = false;

function barColor(ms) {
  if (ms <= 20) return '#00e676';
  if (ms <= 33) return '#ffcc00';
  return '#ff4444';
}

function render() {
  const w = canvas.width;
  const h = canvas.height;
  const barW = w / HISTORY_SIZE;

  ctx.clearRect(0, 0, w, h);

  // Subtle grid lines at 60fps (16.7ms) and 30fps (33.3ms)
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  [16.7, 33.3].forEach(target => {
    const y = h - (target / MAX_FRAMETIME_MS) * h;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  });

  history.forEach((ft, i) => {
    if (ft <= 0) return;
    const barH = Math.min(ft / MAX_FRAMETIME_MS, 1) * h;
    ctx.fillStyle = barColor(ft);
    ctx.fillRect(i * barW, h - barH, Math.max(barW - 1, 1), barH);
  });

  // FPS color and text
  fpsEl.style.color = currentFps >= 50 ? '#ffffff' : currentFps >= 30 ? '#ffcc00' : '#ff4444';
  fpsEl.textContent = connected ? `${currentFps} FPS` : '-- FPS';

  requestAnimationFrame(render);
}

function connect() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => { connected = true; };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    currentFps = data.fps;
    if (data.is_new_frame && data.frametime_ms > 0) {
      history.shift();
      history.push(data.frametime_ms);
    }
  };

  ws.onclose = () => {
    connected = false;
    setTimeout(connect, 1000); // auto-reconnect after 1s
  };

  ws.onerror = () => ws.close();
}

connect();
render();
```

- [ ] **Step 4: Test the overlay in a browser**

With `server.py` running and OBS Virtual Camera active:

```bash
open http://localhost:8080
```

Expected: semi-transparent dark HUD in the top-right showing "-- FPS" until WebSocket connects, then live FPS and scrolling frametime bars.

- [ ] **Step 5: Add to OBS as a Browser Source**

In OBS:
1. Click `+` in Sources → Browser
2. URL: `http://localhost:8080`
3. Width: `224`, Height: `90`
4. Check "Shutdown source when not visible"
5. Click OK, drag to position in scene

- [ ] **Step 6: Commit**

```bash
git add overlay/
git commit -m "feat: browser overlay with fps display and scrolling frametime graph"
```

---

### Task 5: Post-Processing CLI

**Files:**
- Create: `analyze.py`
- Create: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `FrameAnalyzer(threshold: float)` from `frame_analyzer.py`
- Produces:
  - `draw_hud(frame: np.ndarray, fps: int, frametime_ms: float, history: list[float], position: str) -> np.ndarray`
  - `build_hud_frame(fps: int, frametime_ms: float, history: list[float], width: int, height: int) -> np.ndarray`
  - CLI: `python analyze.py <input_video>` → `<input_video>_annotated.mp4`

- [ ] **Step 1: Write failing tests**

`tests/test_analyze.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analyze.py -v
```

Expected: `ImportError: No module named 'analyze'`

- [ ] **Step 3: Implement analyze.py**

```python
import argparse
import os
import sys
from collections import deque

import cv2
import numpy as np

from frame_analyzer import FrameAnalyzer

HUD_W = 212
HUD_H = 82
HISTORY_SIZE = 120
MAX_FRAMETIME_MS = 50
MARGIN = 12


def _bar_color_bgr(ms: float) -> tuple[int, int, int]:
    if ms <= 20:
        return (50, 230, 118)   # green in BGR
    if ms <= 33:
        return (0, 204, 255)    # yellow in BGR
    return (68, 68, 255)        # red in BGR


def build_hud_frame(fps: int, frametime_ms: float,
                    history: list[float],
                    width: int = HUD_W,
                    height: int = HUD_H) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # FPS text
    fps_color = (
        (255, 255, 255) if fps >= 50
        else (0, 204, 255) if fps >= 30
        else (68, 68, 255)
    )
    cv2.putText(img, f'{fps} FPS', (8, 30),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, fps_color, 1, cv2.LINE_AA)

    # Frametime graph area
    gx, gy = 6, 36
    gw, gh = width - 12, height - 42
    bar_w = gw / HISTORY_SIZE

    # Grid lines at 60fps (16.7ms) and 30fps (33.3ms)
    for target_ms in (16.7, 33.3):
        line_y = gy + gh - int((target_ms / MAX_FRAMETIME_MS) * gh)
        cv2.line(img, (gx, line_y), (gx + gw, line_y), (60, 60, 60), 1)

    for i, ft in enumerate(history):
        if ft <= 0:
            continue
        bar_h = int(min(ft / MAX_FRAMETIME_MS, 1.0) * gh)
        x1 = gx + int(i * bar_w)
        x2 = gx + int((i + 1) * bar_w) - 1
        y1 = gy + gh - bar_h
        cv2.rectangle(img, (x1, y1), (x2, gy + gh), _bar_color_bgr(ft), -1)

    return img


def draw_hud(frame: np.ndarray, fps: int, frametime_ms: float,
             history: list[float], position: str = 'top-right') -> np.ndarray:
    fh, fw = frame.shape[:2]
    hud = build_hud_frame(fps, frametime_ms, history)
    hh, hw = hud.shape[:2]

    positions = {
        'top-right':    (fw - hw - MARGIN, MARGIN),
        'top-left':     (MARGIN, MARGIN),
        'bottom-right': (fw - hw - MARGIN, fh - hh - MARGIN),
        'bottom-left':  (MARGIN, fh - hh - MARGIN),
    }
    x, y = positions.get(position, positions['top-right'])

    roi = frame[y:y + hh, x:x + hw]
    frame[y:y + hh, x:x + hw] = cv2.addWeighted(roi, 0.4, hud, 0.6, 0)
    return frame


def analyze(input_path: str, output_path: str,
            threshold: float, position: str) -> None:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f'[ERROR] Cannot open: {input_path}')
        sys.exit(1)

    fps_in = cap.get(cv2.CAP_PROP_FPS) or 60.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'),
                          fps_in, (w, h))

    analyzer = FrameAnalyzer(threshold=threshold)
    history: deque[float] = deque([0.0] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
    fps = 0
    frametime_ms = 0.0

    print(f'[Analyze] {total} frames @ {fps_in:.1f}fps → {output_path}')

    for frame_idx in range(total):
        ret, frame = cap.read()
        if not ret:
            break

        result = analyzer.process_frame(frame, frame_idx / fps_in)
        fps = result['fps']
        if result['is_new_frame']:
            frametime_ms = result['frametime_ms']
            history.append(frametime_ms)

        frame = draw_hud(frame, fps, frametime_ms, list(history), position)
        out.write(frame)

        if frame_idx % 300 == 0 and total:
            print(f'  {frame_idx}/{total} ({frame_idx / total * 100:.0f}%)')

    cap.release()
    out.release()
    print(f'[Done] Saved to {output_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Burn FPS/frametime overlay into a recorded video'
    )
    parser.add_argument('input', help='Input video file (.mp4, .mkv, etc.)')
    parser.add_argument('--out', default=None,
                        help='Output path (default: <input>_annotated.mp4)')
    parser.add_argument('--threshold', type=float, default=1.0,
                        help='Frame difference threshold (default: 1.0)')
    parser.add_argument('--position', default='top-right',
                        choices=['top-right', 'top-left', 'bottom-right', 'bottom-left'],
                        help='HUD corner (default: top-right)')
    args = parser.parse_args()

    if args.out is None:
        base, _ = os.path.splitext(args.input)
        args.out = base + '_annotated.mp4'

    analyze(args.input, args.out, args.threshold, args.position)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_analyze.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Smoke-test with a real recording**

```bash
python analyze.py /path/to/your_recording.mkv
```

Expected: progress lines every 300 frames, then `[Done] Saved to your_recording_annotated.mp4`. Open the output video to confirm the HUD is visible and frametime bars respond to gameplay.

- [ ] **Step 6: Commit**

```bash
git add analyze.py tests/test_analyze.py
git commit -m "feat: post-processing CLI to burn fps/frametime overlay into recorded video"
```
