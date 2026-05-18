"""
BCI Assistive Control - Eye Gaze Mouse Controller
====================================================
Uses webcam + MediaPipe FaceLandmarker to track eye gaze direction
and map it to cursor movement. Blinks/winks for clicks.

Controls:
  - Look LEFT/RIGHT/UP/DOWN  -> cursor moves in that direction
  - Quick BLINK (both eyes)  -> Left Click
  - WINK (one eye hold)      -> Right Click
  - Double BLINK             -> Double Click
  - Long BLINK (>1s)         -> Toggle drag mode

Electrode-free, camera-only assistive control.

Usage:
  python -m src.gaze_mouse
  python -m src.gaze_mouse --speed 15 --smooth 0.3
  python -m src.gaze_mouse --camera 0 --preview

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import threading
import queue
import os
import urllib.request

import cv2
import numpy as np
import pyautogui

from src.utils import setup_logger, DATA_DIR

logger = setup_logger("gaze_mouse")

# ──────────────────────────────────────────────
# MODEL
# ──────────────────────────────────────────────
FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = DATA_DIR / "face_landmarker.task"


def ensure_model():
    if MODEL_PATH.exists():
        return str(MODEL_PATH)
    logger.info(f"Downloading FaceLandmarker model...")
    urllib.request.urlretrieve(FACE_LANDMARKER_URL, str(MODEL_PATH))
    logger.info("Model downloaded.")
    return str(MODEL_PATH)


# ──────────────────────────────────────────────
# LANDMARK INDICES
# ──────────────────────────────────────────────

# Iris center
LEFT_IRIS_CENTER  = 468
RIGHT_IRIS_CENTER = 473

# Eye corners (for horizontal gaze ratio)
LEFT_EYE_INNER   = 133
LEFT_EYE_OUTER   = 33
RIGHT_EYE_INNER  = 362
RIGHT_EYE_OUTER  = 263

# Eye top/bottom (for vertical gaze ratio)
LEFT_EYE_TOP     = 159
LEFT_EYE_BOTTOM  = 145
RIGHT_EYE_TOP    = 386
RIGHT_EYE_BOTTOM = 374

# EAR landmarks (6-point)
LEFT_EYE_EAR  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_EAR = [362, 385, 387, 263, 373, 380]

# ──────────────────────────────────────────────
# THRESHOLDS
# ──────────────────────────────────────────────
EAR_THRESHOLD     = 0.19
BLINK_MAX_FRAMES  = 6
WINK_MIN_FRAMES   = 18
LONG_BLINK_FRAMES = 30  # ~1 second
COOLDOWN_FRAMES   = 12


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def get_point(landmarks, idx, w, h):
    lm = landmarks[idx]
    return np.array([lm.x * w, lm.y * h])


def compute_ear(landmarks, eye_indices, w, h):
    pts = [get_point(landmarks, i, w, h) for i in eye_indices]
    v1 = np.linalg.norm(pts[1] - pts[5])
    v2 = np.linalg.norm(pts[2] - pts[4])
    hor = np.linalg.norm(pts[0] - pts[3])
    if hor == 0:
        return 0.3
    return (v1 + v2) / (2.0 * hor)


def compute_gaze_ratio(landmarks, w, h):
    """
    Compute horizontal and vertical gaze ratios.
    Returns (h_ratio, v_ratio):
      h_ratio: 0.0 = looking LEFT, 0.5 = center, 1.0 = looking RIGHT
      v_ratio: 0.0 = looking UP,   0.5 = center, 1.0 = looking DOWN
    """
    # -- Left eye --
    l_iris = get_point(landmarks, LEFT_IRIS_CENTER, w, h)
    l_inner = get_point(landmarks, LEFT_EYE_INNER, w, h)
    l_outer = get_point(landmarks, LEFT_EYE_OUTER, w, h)
    l_top = get_point(landmarks, LEFT_EYE_TOP, w, h)
    l_bot = get_point(landmarks, LEFT_EYE_BOTTOM, w, h)

    l_width = np.linalg.norm(l_inner - l_outer)
    l_height = np.linalg.norm(l_top - l_bot)

    if l_width > 0:
        l_h_ratio = (l_iris[0] - l_outer[0]) / l_width
    else:
        l_h_ratio = 0.5

    if l_height > 0:
        l_v_ratio = (l_iris[1] - l_top[1]) / l_height
    else:
        l_v_ratio = 0.5

    # -- Right eye --
    r_iris = get_point(landmarks, RIGHT_IRIS_CENTER, w, h)
    r_inner = get_point(landmarks, RIGHT_EYE_INNER, w, h)
    r_outer = get_point(landmarks, RIGHT_EYE_OUTER, w, h)
    r_top = get_point(landmarks, RIGHT_EYE_TOP, w, h)
    r_bot = get_point(landmarks, RIGHT_EYE_BOTTOM, w, h)

    r_width = np.linalg.norm(r_inner - r_outer)
    r_height = np.linalg.norm(r_top - r_bot)

    if r_width > 0:
        r_h_ratio = (r_iris[0] - r_outer[0]) / r_width
    else:
        r_h_ratio = 0.5

    if r_height > 0:
        r_v_ratio = (r_iris[1] - r_top[1]) / r_height
    else:
        r_v_ratio = 0.5

    # Average both eyes
    h_ratio = (l_h_ratio + r_h_ratio) / 2.0
    v_ratio = (l_v_ratio + r_v_ratio) / 2.0

    return h_ratio, v_ratio


# ──────────────────────────────────────────────
# GAZE MOUSE CONTROLLER
# ──────────────────────────────────────────────

class GazeMouse:
    """
    Camera-based gaze-controlled mouse.

    Calibrates gaze center at startup, then maps gaze deviation
    to cursor movement speed.
    """

    def __init__(self, camera_index=0, speed=12, dead_zone=0.06,
                 smooth=0.3, show_preview=True):
        self.camera_index = camera_index
        self.speed = speed
        self.dead_zone = dead_zone        # gaze deviation below this = no movement
        self.smooth = smooth              # smoothing factor (0=no smooth, 1=max smooth)
        self.show_preview = show_preview
        self._running = False

        # Calibration
        self.center_h = 0.5
        self.center_v = 0.5

        # Smoothed gaze
        self.smooth_h = 0.5
        self.smooth_v = 0.5

        # Stats
        self.total_moves = 0
        self.total_clicks = 0
        self.dragging = False

    def run(self):
        import mediapipe as mp

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.01

        model_path = ensure_model()

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error(f"Cannot open camera (index={self.camera_index})")
            return
        logger.info(f"Camera opened: index={self.camera_index}")

        # Set camera to higher FPS if possible
        cap.set(cv2.CAP_PROP_FPS, 30)

        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        landmarker = FaceLandmarker.create_from_options(options)

        # Blink/wink state
        left_closed_count = 0
        right_closed_count = 0
        both_closed_count = 0
        cooldown = 0
        frame_idx = 0

        # Calibration phase
        logger.info("\n" + "=" * 60)
        logger.info("  EYE GAZE MOUSE CONTROLLER")
        logger.info("=" * 60)
        logger.info("  CALIBRATING: Look at the CENTER of your screen")
        logger.info("  for 3 seconds...")
        logger.info("=" * 60)

        cal_samples_h = []
        cal_samples_v = []
        cal_start = time.time()
        calibrating = True

        try:
            while self._running or calibrating:
                self._running = True
                ret, frame = cap.read()
                if not ret:
                    continue

                frame_idx += 1
                frame_h, frame_w = frame.shape[:2]

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int(frame_idx * (1000 / 30))
                result = landmarker.detect_for_video(mp_image, ts)

                if not result.face_landmarks or len(result.face_landmarks) == 0:
                    if self.show_preview:
                        cv2.putText(frame, "No face detected", (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        cv2.imshow("Gaze Mouse", frame)
                        if cv2.waitKey(1) & 0xFF == 27:
                            break
                    continue

                landmarks = result.face_landmarks[0]
                h_ratio, v_ratio = compute_gaze_ratio(landmarks, frame_w, frame_h)

                # ── Calibration ──
                if calibrating:
                    cal_samples_h.append(h_ratio)
                    cal_samples_v.append(v_ratio)

                    if self.show_preview:
                        elapsed = time.time() - cal_start
                        remaining = max(0, 3 - elapsed)
                        cv2.putText(frame, f"CALIBRATING: Look at screen center ({remaining:.1f}s)",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        cv2.putText(frame, f"H: {h_ratio:.3f}  V: {v_ratio:.3f}",
                                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                        cv2.imshow("Gaze Mouse", frame)
                        if cv2.waitKey(1) & 0xFF == 27:
                            break

                    if time.time() - cal_start > 3.0:
                        self.center_h = np.mean(cal_samples_h)
                        self.center_v = np.mean(cal_samples_v)
                        self.smooth_h = self.center_h
                        self.smooth_v = self.center_v
                        calibrating = False
                        logger.info(f"  Calibrated! Center: H={self.center_h:.3f} V={self.center_v:.3f}")
                        logger.info("")
                        logger.info("  Controls:")
                        logger.info("    Look around     -> Move cursor")
                        logger.info("    Quick blink     -> Left click")
                        logger.info("    Wink (hold)     -> Right click")
                        logger.info("    Long blink (1s) -> Toggle drag")
                        logger.info("    Press ESC       -> Quit")
                        logger.info("    Press C         -> Recalibrate")
                        logger.info("=" * 60 + "\n")
                    continue

                # ── Gaze tracking ──
                # Smooth the gaze
                alpha = 1.0 - self.smooth
                self.smooth_h = self.smooth_h * self.smooth + h_ratio * alpha
                self.smooth_v = self.smooth_v * self.smooth + v_ratio * alpha

                # Deviation from center
                dev_h = self.smooth_h - self.center_h  # positive = looking right
                dev_v = self.smooth_v - self.center_v  # positive = looking down

                # Apply dead zone
                if abs(dev_h) < self.dead_zone:
                    dev_h = 0
                else:
                    dev_h = dev_h - np.sign(dev_h) * self.dead_zone

                if abs(dev_v) < self.dead_zone:
                    dev_v = 0
                else:
                    dev_v = dev_v - np.sign(dev_v) * self.dead_zone

                # Scale to pixels (non-linear for precision at center, speed at edges)
                dx = int(dev_h * self.speed * 20 * (1 + abs(dev_h) * 5))
                dy = int(dev_v * self.speed * 15 * (1 + abs(dev_v) * 5))

                # Camera is mirrored: flip horizontal
                dx = -dx

                # Move cursor
                if dx != 0 or dy != 0:
                    pyautogui.moveRel(dx, dy, _pause=False)
                    self.total_moves += 1

                # ── Blink/Wink detection ──
                left_ear = compute_ear(landmarks, LEFT_EYE_EAR, frame_w, frame_h)
                right_ear = compute_ear(landmarks, RIGHT_EYE_EAR, frame_w, frame_h)

                left_closed = left_ear < EAR_THRESHOLD
                right_closed = right_ear < EAR_THRESHOLD

                if left_closed:
                    left_closed_count += 1
                else:
                    left_closed_count = 0

                if right_closed:
                    right_closed_count += 1
                else:
                    right_closed_count = 0

                if left_closed and right_closed:
                    both_closed_count += 1
                else:
                    if cooldown <= 0:
                        # LONG BLINK: toggle drag
                        if both_closed_count >= LONG_BLINK_FRAMES:
                            self.dragging = not self.dragging
                            if self.dragging:
                                pyautogui.mouseDown()
                                logger.info("  [DRAG ON]")
                            else:
                                pyautogui.mouseUp()
                                logger.info("  [DRAG OFF]")
                            cooldown = COOLDOWN_FRAMES

                        # BLINK: left click
                        elif both_closed_count > 0 and both_closed_count <= BLINK_MAX_FRAMES:
                            pyautogui.click()
                            self.total_clicks += 1
                            logger.info(f"  [BLINK -> CLICK] (clicks: {self.total_clicks})")
                            cooldown = COOLDOWN_FRAMES

                        # WINK: right click
                        elif left_closed_count >= WINK_MIN_FRAMES and right_closed_count == 0:
                            pyautogui.rightClick()
                            logger.info("  [WINK LEFT -> RIGHT CLICK]")
                            cooldown = COOLDOWN_FRAMES

                        elif right_closed_count >= WINK_MIN_FRAMES and left_closed_count == 0:
                            pyautogui.rightClick()
                            logger.info("  [WINK RIGHT -> RIGHT CLICK]")
                            cooldown = COOLDOWN_FRAMES

                    both_closed_count = 0

                if cooldown > 0:
                    cooldown -= 1

                # ── Preview ──
                if self.show_preview:
                    # Gaze indicator
                    status_color = (0, 255, 0) if (dx != 0 or dy != 0) else (100, 100, 100)
                    cv2.putText(frame, f"Gaze: H={self.smooth_h:.3f} V={self.smooth_v:.3f}",
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    cv2.putText(frame, f"Move: dx={dx:+d} dy={dy:+d}",
                                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2)
                    cv2.putText(frame, f"EAR: L={left_ear:.2f} R={right_ear:.2f}",
                                (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                    # Direction arrow
                    center_x, center_y = frame_w - 60, 60
                    cv2.circle(frame, (center_x, center_y), 30, (50, 50, 50), -1)
                    arrow_x = center_x + int(dev_h * 300)
                    arrow_y = center_y + int(dev_v * 300)
                    arrow_x = max(center_x-28, min(center_x+28, arrow_x))
                    arrow_y = max(center_y-28, min(center_y+28, arrow_y))
                    cv2.circle(frame, (arrow_x, arrow_y), 5, (0, 255, 0), -1)

                    # Status bar
                    status = "MOVING" if (dx != 0 or dy != 0) else "STILL"
                    if self.dragging:
                        status = "DRAGGING"
                    drag_color = (0, 0, 255) if self.dragging else (0, 200, 0)
                    cv2.putText(frame, status, (10, frame_h - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, drag_color, 2)
                    cv2.putText(frame, f"Clicks: {self.total_clicks}  Moves: {self.total_moves}",
                                (frame_w - 250, frame_h - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

                    # Draw iris positions
                    for iris_idx in [LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER]:
                        pt = get_point(landmarks, iris_idx, frame_w, frame_h)
                        cv2.circle(frame, (int(pt[0]), int(pt[1])), 3, (0, 255, 255), -1)

                    cv2.imshow("Gaze Mouse", frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:  # ESC
                        break
                    elif key == ord('c'):  # Recalibrate
                        cal_samples_h.clear()
                        cal_samples_v.clear()
                        cal_start = time.time()
                        calibrating = True
                        logger.info("  Recalibrating...")

        except KeyboardInterrupt:
            pass
        finally:
            if self.dragging:
                pyautogui.mouseUp()
            cap.release()
            landmarker.close()
            if self.show_preview:
                cv2.destroyAllWindows()
            logger.info(f"\nStopped. Moves: {self.total_moves}  Clicks: {self.total_clicks}")


def main():
    parser = argparse.ArgumentParser(description="Eye Gaze Mouse Controller")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument("--speed", type=int, default=12,
                        help="Cursor speed (default: 12)")
    parser.add_argument("--dead-zone", type=float, default=0.06,
                        help="Gaze dead zone — ignore small eye movements (default: 0.06)")
    parser.add_argument("--smooth", type=float, default=0.3,
                        help="Smoothing 0-0.9 (higher=smoother but slower, default: 0.3)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Hide camera preview window")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  EYE GAZE MOUSE CONTROLLER")
    logger.info("=" * 60)
    logger.info(f"  Camera: {args.camera}")
    logger.info(f"  Speed: {args.speed}")
    logger.info(f"  Dead zone: {args.dead_zone}")
    logger.info(f"  Smoothing: {args.smooth}")
    logger.info("=" * 60)

    controller = GazeMouse(
        camera_index=args.camera,
        speed=args.speed,
        dead_zone=args.dead_zone,
        smooth=args.smooth,
        show_preview=not args.no_preview,
    )
    controller.run()


if __name__ == "__main__":
    main()
