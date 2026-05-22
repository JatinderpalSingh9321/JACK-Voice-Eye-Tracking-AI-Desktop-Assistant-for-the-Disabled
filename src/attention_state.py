"""
Attention State — Thread-safe shared state for the multimodal system.
=====================================================================
All modules (gaze tracker, EOG controller, voice assistant) read/write
through this singleton so they stay in sync.

Group No. 7 | 8th Semester Major Project
"""

import threading
import time


class AttentionState:
    """Thread-safe singleton holding the current attention & gaze state."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        self._state_lock = threading.Lock()
        self._is_attentive = False
        self._gaze_x = 0.0          # normalised 0..1
        self._gaze_y = 0.0          # normalised 0..1
        self._last_update = 0.0
        self._screen_w = 1920
        self._screen_h = 1080
        self._voice_name = "zira"   # Default to soft female voice
        self._voice_speed = 1.0
        self._mic_sensitivity = 300  # Highly sensitive default to capture soft speech

    # ── Attention ──────────────────────────────
    @property
    def is_attentive(self) -> bool:
        with self._state_lock:
            # Stale if gaze tracker hasn't updated in 2s
            if time.time() - self._last_update > 2.0:
                return False
            return self._is_attentive

    @is_attentive.setter
    def is_attentive(self, val: bool):
        with self._state_lock:
            self._is_attentive = val
            self._last_update = time.time()

    # ── Gaze coordinates ──────────────────────
    def set_gaze(self, nx: float, ny: float):
        """Set normalised gaze (0..1)."""
        with self._state_lock:
            self._gaze_x = max(0.0, min(1.0, nx))
            self._gaze_y = max(0.0, min(1.0, ny))
            self._last_update = time.time()

    def get_gaze_screen(self) -> tuple:
        """Return gaze position in screen pixel coordinates."""
        with self._state_lock:
            return (
                int(self._gaze_x * self._screen_w),
                int(self._gaze_y * self._screen_h),
            )

    def set_screen_size(self, w: int, h: int):
        with self._state_lock:
            self._screen_w = w
            self._screen_h = h

    @property
    def voice_name(self) -> str:
        with self._state_lock:
            return self._voice_name

    @voice_name.setter
    def voice_name(self, name: str):
        with self._state_lock:
            self._voice_name = name

    @property
    def voice_speed(self) -> float:
        with self._state_lock:
            return self._voice_speed

    @voice_speed.setter
    def voice_speed(self, val: float):
        with self._state_lock:
            self._voice_speed = val

    @property
    def mic_sensitivity(self) -> int:
        with self._state_lock:
            return self._mic_sensitivity

    @mic_sensitivity.setter
    def mic_sensitivity(self, val: int):
        with self._state_lock:
            self._mic_sensitivity = val


# Module-level convenience
attention = AttentionState()
