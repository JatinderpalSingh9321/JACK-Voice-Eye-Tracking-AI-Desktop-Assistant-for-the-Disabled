"""
Gaze Tracker — Eye tracking cursor + attention detection
=========================================================
Uses MediaPipe FaceLandmarker (Tasks API) to:
  1. Track iris position and map it to the Windows OS mouse cursor.
  2. Detect whether the user is looking at the screen (attention gating).

Runs as a daemon thread so it can be imported by the launcher.

Usage (standalone):
  python -m src.gaze_tracker
  python -m src.gaze_tracker --camera 0 --smoothing 0.15 --preview

Group No. 7 | 8th Semester Major Project
"""

import argparse
import os
import threading
import time
import urllib.request

import cv2
import numpy as np
import pyautogui

from src.utils import setup_logger, DATA_DIR
from src.attention_state import attention

logger = setup_logger("gaze_tracker")

# Prevent pyautogui fail-safe from triggering when cursor hits corner
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ──────────────────────────────────────────────
# MODEL MANAGEMENT
# ──────────────────────────────────────────────

MODEL_PATH = DATA_DIR / "face_landmarker.task"
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"


def ensure_model():
    """Download the FaceLandmarker model if missing."""
    if MODEL_PATH.exists():
        return str(MODEL_PATH)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("  Downloading FaceLandmarker model (~5MB)...")
    urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
    logger.info(f"  ✓ Model saved to {MODEL_PATH}")
    return str(MODEL_PATH)


# ──────────────────────────────────────────────
# IRIS LANDMARK INDICES (478 mesh + 10 iris = 478..487)
# ──────────────────────────────────────────────

# Left eye corners + iris center
L_EYE_OUTER  = 33
L_EYE_INNER  = 133
L_IRIS_CENTER = 468

# Right eye corners + iris center
R_EYE_OUTER  = 362
R_EYE_INNER  = 263
R_IRIS_CENTER = 473

# Eye open/close landmarks (top/bottom eyelid)
L_EYE_TOP = 159
L_EYE_BOT = 145
R_EYE_TOP = 386
R_EYE_BOT = 374

# Head pose landmarks
NOSE_TIP         = 1
CHIN             = 152
LEFT_EYE_CORNER  = 33
RIGHT_EYE_CORNER = 263
LEFT_MOUTH       = 61
RIGHT_MOUTH      = 291


class GazeTracker(threading.Thread):
    """
    Webcam-based gaze tracking thread using MediaPipe Tasks API.

    Parameters
    ----------
    camera_id : int
        OpenCV camera index (default 0).
    smoothing : float
        EMA smoothing factor (0 = no smoothing, 1 = infinite smoothing).
    show_preview : bool
        If True, shows a small debug preview window.
    """

    def __init__(self, camera_id=0, smoothing=0.15, show_preview=False):
        super().__init__(daemon=True, name="GazeTracker")
        self.camera_id = camera_id
        self.smoothing = smoothing
        self.show_preview = show_preview
        self._running = False

        # Smoothed cursor position
        self._sx = 0.5
        self._sy = 0.5

        # Screen dimensions
        screen_w, screen_h = pyautogui.size()
        attention.set_screen_size(screen_w, screen_h)
        self._sw = screen_w
        self._sh = screen_h
        logger.info(f"  Screen: {screen_w}×{screen_h}")

        # Calibration boundaries (auto-expand on use)
        self._cal_xmin = 0.35
        self._cal_xmax = 0.65
        self._cal_ymin = 0.30
        self._cal_ymax = 0.70

    def run(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceLandmarker,
            FaceLandmarkerOptions,
            RunningMode,
        )

        self._running = True

        # Ensure model is downloaded
        model_path = ensure_model()

        # Configure FaceLandmarker
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )

        landmarker = FaceLandmarker.create_from_options(options)

        cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        if not cap.isOpened():
            logger.error(f"Cannot open camera {self.camera_id}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)

        logger.info("✓ Camera opened — gaze tracking active")

        frame_ts = 0
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)  # Mirror
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            frame_ts += 33  # ~30fps in milliseconds

            result = landmarker.detect_for_video(mp_image, frame_ts)

            if result.face_landmarks and len(result.face_landmarks) > 0:
                lm = result.face_landmarks[0]  # List of NormalizedLandmark

                # Check if we have iris landmarks (need >= 478)
                if len(lm) < 478:
                    attention.is_attentive = False
                    continue

                # ── Attention: check if eyes are open ──
                eyes_open = self._check_eyes_open(lm)

                # ── Attention: check head pose ──
                looking_at_screen = self._check_head_pose(lm, frame.shape)

                is_attentive = eyes_open and looking_at_screen
                attention.is_attentive = is_attentive

                if is_attentive:
                    # ── Calculate gaze from iris position ──
                    gx, gy = self._calc_gaze(lm)
                    self._update_cursor(gx, gy)

                if self.show_preview:
                    self._draw_debug(frame, lm, is_attentive)

            else:
                attention.is_attentive = False

            if self.show_preview:
                cv2.imshow("Gaze Tracker", frame)
                if cv2.waitKey(1) & 0xFF == 27:  # ESC
                    break

        landmarker.close()
        cap.release()
        if self.show_preview:
            cv2.destroyAllWindows()
        logger.info("Gaze tracker stopped")

    def stop(self):
        self._running = False

    # ── Internal methods ──────────────────────────

    def _check_eyes_open(self, lm) -> bool:
        """Check Eye Aspect Ratio (EAR) — closed eyes = not attentive."""
        def ear(top_idx, bot_idx, outer_idx, inner_idx):
            v_dist = abs(lm[top_idx].y - lm[bot_idx].y)
            h_dist = abs(lm[outer_idx].x - lm[inner_idx].x)
            return v_dist / (h_dist + 1e-6)

        l_ear = ear(L_EYE_TOP, L_EYE_BOT, L_EYE_OUTER, L_EYE_INNER)
        r_ear = ear(R_EYE_TOP, R_EYE_BOT, R_EYE_OUTER, R_EYE_INNER)
        avg_ear = (l_ear + r_ear) / 2.0

        return avg_ear > 0.045  # Threshold for "open"

    def _check_head_pose(self, lm, img_shape) -> bool:
        """Check if head is facing roughly toward the camera."""
        h, w, _ = img_shape

        # 3D model points (generic face proportions)
        model_points = np.array([
            (0.0,  0.0,  0.0),       # Nose tip
            (0.0, -330.0, -65.0),     # Chin
            (-225.0, 170.0, -135.0),  # Left eye corner
            (225.0, 170.0, -135.0),   # Right eye corner
            (-150.0, -150.0, -125.0), # Left mouth
            (150.0, -150.0, -125.0),  # Right mouth
        ], dtype=np.float64)

        # 2D image points from landmarks
        indices = [NOSE_TIP, CHIN, LEFT_EYE_CORNER, RIGHT_EYE_CORNER,
                   LEFT_MOUTH, RIGHT_MOUTH]
        image_points = np.array([
            (lm[i].x * w, lm[i].y * h) for i in indices
        ], dtype=np.float64)

        # Camera matrix approximation
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1))

        _, rotation_vec, _ = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs
        )
        rmat, _ = cv2.Rodrigues(rotation_vec)
        angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)

        yaw = angles[1]
        pitch = angles[0]

        # Within ±25° yaw and ±20° pitch → looking at screen
        return abs(yaw) < 25 and abs(pitch) < 20

    def _calc_gaze(self, lm) -> tuple:
        """Calculate normalised gaze position (0..1) from iris landmarks."""
        def iris_ratio(iris_idx, outer_idx, inner_idx, top_idx, bot_idx):
            iris_x = lm[iris_idx].x
            outer_x = lm[outer_idx].x
            inner_x = lm[inner_idx].x
            hx = (iris_x - outer_x) / (inner_x - outer_x + 1e-6)

            iris_y = lm[iris_idx].y
            top_y = lm[top_idx].y
            bot_y = lm[bot_idx].y
            hy = (iris_y - top_y) / (bot_y - top_y + 1e-6)

            return hx, hy

        lx, ly = iris_ratio(L_IRIS_CENTER, L_EYE_OUTER, L_EYE_INNER,
                            L_EYE_TOP, L_EYE_BOT)
        rx, ry = iris_ratio(R_IRIS_CENTER, R_EYE_OUTER, R_EYE_INNER,
                            R_EYE_TOP, R_EYE_BOT)

        # Average both eyes
        gx = (lx + rx) / 2.0
        gy = (ly + ry) / 2.0

        # Auto-calibrate boundaries
        alpha = 0.01
        self._cal_xmin = min(self._cal_xmin, gx) * (1 - alpha) + gx * alpha
        self._cal_xmax = max(self._cal_xmax, gx) * (1 - alpha) + gx * alpha
        self._cal_ymin = min(self._cal_ymin, gy) * (1 - alpha) + gy * alpha
        self._cal_ymax = max(self._cal_ymax, gy) * (1 - alpha) + gy * alpha

        x_range = self._cal_xmax - self._cal_xmin
        y_range = self._cal_ymax - self._cal_ymin

        nx = (gx - self._cal_xmin) / (x_range + 1e-6)
        ny = (gy - self._cal_ymin) / (y_range + 1e-6)

        return float(np.clip(nx, 0, 1)), float(np.clip(ny, 0, 1))

    def _update_cursor(self, gx: float, gy: float):
        """Apply EMA smoothing and move the OS cursor."""
        alpha = self.smoothing
        self._sx = self._sx * alpha + gx * (1 - alpha)
        self._sy = self._sy * alpha + gy * (1 - alpha)

        px = int(self._sx * self._sw)
        py = int(self._sy * self._sh)

        attention.set_gaze(self._sx, self._sy)

        try:
            pyautogui.moveTo(px, py, _pause=False)
        except Exception:
            pass

    def _draw_debug(self, frame, lm, is_attentive):
        """Draw debug overlay on the preview window."""
        h, w, _ = frame.shape

        # Draw iris positions
        for idx in [L_IRIS_CENTER, R_IRIS_CENTER]:
            if idx < len(lm):
                cx = int(lm[idx].x * w)
                cy = int(lm[idx].y * h)
                cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)

        # Attention indicator
        color = (0, 255, 0) if is_attentive else (0, 0, 255)
        label = "ATTENTIVE" if is_attentive else "LOOKING AWAY"
        cv2.putText(frame, label, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # Cursor position
        sx, sy = attention.get_gaze_screen()
        cv2.putText(frame, f"Cursor: ({sx}, {sy})", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


# ──────────────────────────────────────────────
# ENTRY POINT (standalone)
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gaze Tracker — Eye tracking cursor")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default: 0)")
    parser.add_argument("--smoothing", type=float, default=0.15,
                        help="EMA smoothing factor (default: 0.15)")
    parser.add_argument("--preview", action="store_true",
                        help="Show debug preview window")
    args = parser.parse_args()

    tracker = GazeTracker(
        camera_id=args.camera,
        smoothing=args.smoothing,
        show_preview=args.preview
    )
    tracker.start()

    logger.info("Gaze tracker running. Press Ctrl+C to stop.")
    try:
        while tracker.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        tracker.stop()
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
