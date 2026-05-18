"""
BCI Assistive Control — Brain-Controlled Mouse (4-Direction MI)
===============================================================
Real-time mouse cursor control using motor imagery.

Includes a startup CALIBRATION phase that auto-detects which
brain pattern maps to which direction (fixes label mismatches).

Usage:
  python -m src.mouse_control_brain --port COM7
  python -m src.mouse_control_brain --port COM7 --speed 20
  python -m src.mouse_control_brain --simulate
  python -m src.mouse_control_brain --port COM7 --no-calibrate

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import pickle
import threading
from collections import deque, Counter

import numpy as np
import pyautogui

from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, MODELS_DIR, setup_logger
from src.train_brain import extract_features

logger = setup_logger("brain_mouse")

# ──────────────────────────────────────────────
# CONSTANTS (Optimized for low latency)
# ──────────────────────────────────────────────
BUF_SIZE = 5000
WINDOW_SEC = 4.0           # MUST match training epoch length
STEP_SEC = 0.25            # Predict every 0.25s for responsiveness
WINDOW_SAMPLES = int(WINDOW_SEC * SAMPLING_RATE)  # 1000 samples

MI_NAMES = ["LEFT", "RIGHT", "UP", "DOWN"]
DIRECTION_VECTORS = {
    0: (-1,  0),   # LEFT
    1: ( 1,  0),   # RIGHT
    2: ( 0, -1),   # UP
    3: ( 0,  1),   # DOWN
}


# ──────────────────────────────────────────────
# SERIAL READER
# ──────────────────────────────────────────────

class SerialReader(threading.Thread):
    def __init__(self, port, baud=BAUD_RATE, simulate=False):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.simulate = simulate
        self.buf = deque(maxlen=BUF_SIZE)
        self._running = False
        self._lock = threading.Lock()

    def run(self):
        self._running = True
        if self.simulate:
            logger.info("✓ Simulation mode (no hardware)")
            while self._running:
                val = 512 + np.random.normal(0, 5)
                with self._lock:
                    self.buf.append(val)
                time.sleep(1 / SAMPLING_RATE)
            return

        import serial as s
        try:
            ser = s.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            for _ in range(20):
                ser.readline()
            logger.info(f"✓ Serial connected ({self.port})")
            while self._running:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line and not line.startswith("#"):
                        val = float(line.split(",")[0])
                        with self._lock:
                            self.buf.append(val)
                except (ValueError, UnicodeDecodeError):
                    pass
            ser.close()
        except Exception as e:
            logger.error(f"Serial error: {e}")
            self._running = False

    def stop(self):
        self._running = False

    def get_window(self, n_samples):
        with self._lock:
            if len(self.buf) < n_samples:
                return None
            return np.array(list(self.buf)[-n_samples:], dtype=np.float64)


# ──────────────────────────────────────────────
# CALIBRATION
# ──────────────────────────────────────────────

def run_calibration(model, reader, window_samples):
    """
    Ask user to imagine each direction for 8 seconds.
    Record model predictions and build a remap table.
    """
    logger.info("\n" + "=" * 60)
    logger.info("  🎯 CALIBRATION PHASE")
    logger.info("=" * 60)
    logger.info("  We will ask you to imagine 4 actions.")
    logger.info("  Each action lasts 8 seconds.")
    logger.info("  This fixes direction mapping for your brain.\n")

    tasks = [
        ("LEFT",  "Imagine squeezing your LEFT fist"),
        ("RIGHT", "Imagine squeezing your RIGHT fist"),
        ("UP",    "Imagine pressing tongue to roof of mouth"),
        ("DOWN",  "Imagine wiggling your toes"),
    ]

    remap = {}  # intended_direction_id -> model_prediction_id

    for intended_id, (name, instruction) in enumerate(tasks):
        logger.info(f"  ──── Direction: {name} ────")
        logger.info(f"  >>> {instruction}")
        logger.info(f"  Starting in 3 seconds... RELAX first.")
        time.sleep(3)
        logger.info(f"  >>> GO! Imagine {name} NOW for 8 seconds...")

        predictions = []
        start = time.time()
        while time.time() - start < 8.0:
            window = reader.get_window(window_samples)
            if window is not None:
                try:
                    feats = extract_features(window).reshape(1, -1)
                    if np.all(np.isfinite(feats)):
                        pred = model.predict(feats)[0]
                        predictions.append(pred)
                except Exception:
                    pass
            time.sleep(0.3)

        if predictions:
            counts = Counter(predictions)
            most_common = counts.most_common(1)[0][0]
            logger.info(f"  Result: When you imagine {name}, "
                       f"model predicts '{MI_NAMES[most_common]}' "
                       f"({counts[most_common]}/{len(predictions)} times)")
            remap[intended_id] = most_common
        else:
            logger.warning(f"  No predictions for {name}! Using default.")
            remap[intended_id] = intended_id

        logger.info(f"  ✓ {name} mapped. Rest for 3 seconds...\n")
        time.sleep(3)

    # Build reverse lookup: model_prediction -> actual_direction
    pred_to_direction = {}
    for intended_id, pred_id in remap.items():
        pred_to_direction[pred_id] = intended_id

    logger.info("=" * 60)
    logger.info("  CALIBRATION COMPLETE — Direction Map:")
    for intended_id, pred_id in remap.items():
        arrow = ["←", "→", "↑", "↓"][intended_id]
        logger.info(f"    Model '{MI_NAMES[pred_id]}' → Cursor {arrow} {MI_NAMES[intended_id]}")
    logger.info("=" * 60 + "\n")

    return pred_to_direction


# ──────────────────────────────────────────────
# MOUSE CONTROLLER
# ──────────────────────────────────────────────

class BrainMouse:
    def __init__(self, model_data, speed=15, threshold=0.55,
                 remap=None, smooth=2):
        self.model = model_data["model"]
        self.speed = speed
        self.threshold = threshold
        self.smooth = smooth
        self.remap = remap or {0: 0, 1: 1, 2: 2, 3: 3}
        self.prediction_history = deque(maxlen=smooth)
        self.total_moves = 0

    def predict_and_move(self, window_data):
        try:
            features = extract_features(window_data)
            if not np.all(np.isfinite(features)):
                return None

            features_2d = features.reshape(1, -1)
            pred = self.model.predict(features_2d)[0]
            proba = self.model.predict_proba(features_2d)[0]
            confidence = proba[pred]

            # Confidence gate
            if confidence < self.threshold:
                self.prediction_history.clear()
                return {"direction": "REST", "confidence": confidence}

            # Remap prediction to actual direction
            actual_dir = self.remap.get(pred, pred)
            direction_name = MI_NAMES[actual_dir]

            # Smoothing: require N consecutive same-direction predictions
            self.prediction_history.append(actual_dir)
            if len(self.prediction_history) < self.smooth:
                return {"direction": direction_name, "confidence": confidence,
                        "status": "buffering"}
            if len(set(self.prediction_history)) > 1:
                return {"direction": direction_name, "confidence": confidence,
                        "status": "inconsistent"}

            dx, dy = DIRECTION_VECTORS[actual_dir]
            move_x = int(dx * self.speed * confidence)
            move_y = int(dy * self.speed * confidence)

            pyautogui.moveRel(move_x, move_y, duration=0.02)
            self.total_moves += 1

            return {
                "direction": direction_name,
                "raw_pred": MI_NAMES[pred],
                "confidence": confidence,
                "move": (move_x, move_y),
                "status": "MOVED",
            }
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return None


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Brain-Controlled Mouse — 4-Direction Motor Imagery"
    )
    parser.add_argument("--port", type=str, default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=15)
    parser.add_argument("--threshold", type=float, default=0.55,
                        help="Min confidence to move (default: 0.55)")
    parser.add_argument("--smooth", type=int, default=2,
                        help="Consecutive same predictions needed (default: 2)")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--no-calibrate", action="store_true",
                        help="Skip calibration (use default mapping)")
    parser.add_argument("--model", type=str,
                        default=str(MODELS_DIR / "brain_mi_model.pkl"))
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    # Load model
    logger.info(f"Loading model: {args.model}")
    try:
        with open(args.model, "rb") as f:
            model_data = pickle.load(f)
        logger.info(f"  CV accuracy: {model_data.get('cv_accuracy', 'N/A')}")
    except FileNotFoundError:
        logger.error(f"Model not found! Train first.")
        return

    # Start serial
    reader = SerialReader(args.port, simulate=args.simulate)
    reader.start()

    # Wait for buffer
    logger.info("  Waiting for data buffer...")
    while reader.get_window(WINDOW_SAMPLES) is None:
        time.sleep(0.5)
    logger.info("  ✓ Buffer ready!")

    # Calibration
    remap = None
    if not args.no_calibrate:
        remap = run_calibration(model_data["model"], reader, WINDOW_SAMPLES)

    # Controller
    controller = BrainMouse(
        model_data, speed=args.speed,
        threshold=args.threshold, remap=remap,
        smooth=args.smooth
    )

    logger.info("\n" + "=" * 60)
    logger.info("  🧠 LIVE CONTROL ACTIVE")
    logger.info("=" * 60)
    logger.info(f"  Speed: {args.speed}px | Threshold: {args.threshold}")
    logger.info(f"  Window: {WINDOW_SEC}s | Step: {STEP_SEC}s")
    logger.info("  Ctrl+C to stop | Screen corner = failsafe\n")

    try:
        while True:
            window = reader.get_window(WINDOW_SAMPLES)
            if window is not None:
                result = controller.predict_and_move(window)
                if result and result.get("status") == "MOVED":
                    mx, my = result["move"]
                    logger.info(
                        f"  [{controller.total_moves:4d}] "
                        f"{result['direction']:6s} ({result['confidence']:.0%}) "
                        f"moved ({mx:+d}, {my:+d})"
                    )
            time.sleep(STEP_SEC)

    except KeyboardInterrupt:
        logger.info(f"\n✓ Stopped. Total moves: {controller.total_moves}")
    except pyautogui.FailSafeException:
        logger.error("\n✗ Failsafe triggered!")
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
