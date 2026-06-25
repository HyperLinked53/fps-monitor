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
