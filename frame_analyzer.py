from collections import deque
import numpy as np
import cv2


def detect_threshold(cap: 'cv2.VideoCapture', fps: float,
                     sample_secs: float = 5.0) -> float:
    """Sample frames and find the natural gap between compression-artifact
    diffs (duplicate frames) and real frame diffs. Works on both video files
    (seeks back to 0 after sampling) and live camera feeds (no seek)."""
    sample_count = int(fps * sample_secs)
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

    # Seek back to start if the source supports it (video files)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    if len(diffs) < 10:
        return 1.0

    diffs_sorted = sorted(diffs)
    n = len(diffs_sorted)

    # Find the largest relative gap in the lower half — the valley between
    # compression-artifact diffs and real new-frame diffs.
    best_gap = 0.0
    threshold = 1.0
    for i in range(1, n // 2):
        gap = diffs_sorted[i] - diffs_sorted[i - 1]
        relative_gap = gap / max(diffs_sorted[i - 1], 0.01)
        if relative_gap > best_gap and diffs_sorted[i - 1] < 3.0:
            best_gap = relative_gap
            threshold = (diffs_sorted[i - 1] + diffs_sorted[i]) / 2

    # No meaningful gap found — all diffs are similar, likely a 60fps game.
    # Use a threshold just below the 10th percentile.
    if best_gap < 2.0:
        threshold = diffs_sorted[n // 10] * 0.5

    return round(max(threshold, 0.1), 2)


class FrameAnalyzer:
    def __init__(self, threshold: float = 0.3):
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
        while self._new_frame_timestamps and self._new_frame_timestamps[0] <= cutoff:
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
