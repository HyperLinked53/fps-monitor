import asyncio
import json
import os
import sys
import threading
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import cv2

from frame_analyzer import FrameAnalyzer, detect_threshold

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
    server = HTTPServer(('localhost', HTTP_PORT), handler)
    print(f"[HTTP] Overlay at http://localhost:{HTTP_PORT}")
    server.serve_forever()


def _camera_loop(camera_index: int, threshold: float | None):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(
            f"[ERROR] Cannot open camera {camera_index}. "
            "Make sure OBS Virtual Camera is running. Try --camera 1 or --camera 2."
        )
        return

    cap.set(cv2.CAP_PROP_FPS, 60)
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    print(f"[Camera] Reading from device index {camera_index} at {actual_fps:.0f}fps")

    if threshold is None:
        print("[Calibrate] Sampling 5 seconds to auto-detect threshold — overlay live shortly...")
        threshold = detect_threshold(cap, actual_fps, sample_secs=5.0)
        print(f"[Calibrate] Using threshold: {threshold}")
    else:
        print(f"[Calibrate] Using threshold: {threshold} (manual)")

    analyzer = FrameAnalyzer(threshold=threshold)

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

    async with ws_serve(_ws_handler, 'localhost', WEBSOCKET_PORT):
        await _broadcaster()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='FPS/Frametime OBS overlay server')
    parser.add_argument('--camera', type=int, default=0,
                        help='Camera device index for OBS Virtual Camera (default: 0)')
    parser.add_argument('--threshold', type=float, default=None,
                        help='Frame difference threshold (default: auto-detected from first 5s)')
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.camera, args.threshold))
    except KeyboardInterrupt:
        print('\n[Server] Stopped.')
