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


def detect_threshold(cap: cv2.VideoCapture, fps_in: float,
                     sample_secs: float = 5.0) -> float:
    """Sample the first N seconds and find the natural gap between
    compression-artifact diffs (duplicate frames) and real frame diffs."""
    sample_count = int(fps_in * sample_secs)
    diffs = []
    prev_gray = None

    for _ in range(sample_count):
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (320, 180))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_gray is not None:
            diffs.append(float(np.mean(np.abs(gray - prev_gray))))
        prev_gray = gray

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    if len(diffs) < 10:
        return 1.0

    diffs_sorted = sorted(diffs)
    n = len(diffs_sorted)

    # Find the largest relative gap in the lower half of diffs.
    # A 30fps game in a 60fps container has a bimodal distribution:
    # cluster of low diffs (compression artifacts on duplicates) and
    # a cluster of higher diffs (actual new frames). The gap between
    # them is where the threshold should sit.
    best_gap = 0.0
    threshold = 1.0
    for i in range(1, n // 2):
        gap = diffs_sorted[i] - diffs_sorted[i - 1]
        relative_gap = gap / max(diffs_sorted[i - 1], 0.01)
        if relative_gap > best_gap and diffs_sorted[i - 1] < 3.0:
            best_gap = relative_gap
            threshold = (diffs_sorted[i - 1] + diffs_sorted[i]) / 2

    # If no meaningful gap found (all diffs are similar = 60fps game),
    # use a threshold just below the 10th percentile of diffs.
    if best_gap < 2.0:
        threshold = diffs_sorted[n // 10] * 0.5

    return round(max(threshold, 0.1), 2)


def analyze(input_path: str, output_path: str,
            threshold: float | None, position: str) -> None:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f'[ERROR] Cannot open: {input_path}')
        sys.exit(1)

    if os.path.abspath(input_path) == os.path.abspath(output_path):
        print('[ERROR] Input and output paths are the same file.')
        sys.exit(1)

    fps_in = cap.get(cv2.CAP_PROP_FPS) or 60.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if threshold is None:
        print('[Analyze] Auto-detecting threshold from first 5 seconds...')
        threshold = detect_threshold(cap, fps_in)
        print(f'[Analyze] Using threshold: {threshold}')
    else:
        print(f'[Analyze] Using threshold: {threshold} (manual)')

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'),
                          fps_in, (w, h))

    analyzer = FrameAnalyzer(threshold=threshold)
    history: deque[float] = deque([0.0] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
    fps = 0
    frametime_ms = 0.0

    print(f'[Analyze] {total} frames @ {fps_in:.1f}fps → {output_path}')

    try:
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
    finally:
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
    parser.add_argument('--threshold', type=float, default=None,
                        help='Frame difference threshold (default: auto-detected from first 5s)')
    parser.add_argument('--position', default='top-right',
                        choices=['top-right', 'top-left', 'bottom-right', 'bottom-left'],
                        help='HUD corner (default: top-right)')
    args = parser.parse_args()

    if args.out is None:
        base, _ = os.path.splitext(args.input)
        args.out = base + '_annotated.mp4'

    analyze(args.input, args.out, args.threshold, args.position)
