"""
BCI Hybrid Mouse Controller — Brain (L/R) + Camera (Clicks)
=============================================================
Brain (C3-C4 bipolar): LEFT/RIGHT cursor movement
Camera (webcam):       BLINK=click, WINK=toggle H/V mode

Modes:
  HORIZONTAL (default): LEFT imagery=left, RIGHT imagery=right
  VERTICAL:             LEFT imagery=up,   RIGHT imagery=down

Usage:
  python -m src.mouse_hybrid --port COM7
  python -m src.mouse_hybrid --port COM7 --speed 20
  python -m src.mouse_hybrid --port COM7 --no-camera

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import pickle
import threading
from collections import deque

import numpy as np
import pyautogui

from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, MODELS_DIR, setup_logger

logger = setup_logger("hybrid_mouse")

# ──────────────────────────────────────────────
# Inline feature extraction (matches training)
# ──────────────────────────────────────────────
from scipy import signal as sig
from scipy.stats import kurtosis, skew

def _bp(x, lo, hi, fs):
    nyq = fs / 2
    lo_n, hi_n = max(lo/nyq, 0.01), min(hi/nyq, 0.99)
    if lo_n >= hi_n: return x
    b, a = sig.butter(4, [lo_n, hi_n], btype='band')
    return sig.filtfilt(b, a, x)

def _preprocess(x, fs):
    b, a = sig.butter(4, [1/(fs/2), 45/(fs/2)], btype='band')
    x = sig.filtfilt(b, a, x)
    b_n, a_n = sig.iirnotch(50, 30, fs)
    return sig.filtfilt(b_n, a_n, x)

def extract_features(epoch, fs=SAMPLING_RATE):
    x = _preprocess(epoch, fs)
    features = []
    freqs, psd = sig.welch(x, fs=fs, nperseg=min(256, len(x)))
    total = np.sum(psd) + 1e-10
    for lo, hi in [(4,8),(8,10),(10,12),(12,16),(16,20),(20,30),(30,45)]:
        mask = (freqs >= lo) & (freqs <= hi)
        bp = np.mean(psd[mask]) if np.any(mask) else 0
        features.extend([bp, bp/total])
    mu = _bp(x, 8, 12, fs)
    features.extend([np.var(mu), np.mean(np.abs(mu)), np.max(np.abs(mu)), np.sqrt(np.mean(mu**2))])
    beta = _bp(x, 12, 30, fs)
    features.extend([np.var(beta), np.mean(np.abs(beta))])
    features.append(np.var(mu) / (np.var(beta) + 1e-10))
    q = len(x) // 4
    for i in range(4):
        s = x[i*q:(i+1)*q]
        features.append(np.var(_bp(s, 8, 12, fs)) if len(s) > 20 else 0)
    mid = len(x) // 2
    for lo, hi in [(8,12),(12,20),(20,30)]:
        h1, h2 = _bp(x[:mid], lo, hi, fs), _bp(x[mid:], lo, hi, fs)
        features.append((np.var(h2) - np.var(h1)) / (np.var(h1) + 1e-10))
    features.extend([np.mean(x), np.median(x), skew(x), kurtosis(x), np.std(x)])
    features.append(np.sum(x > 0) / len(x))
    dx, ddx = np.diff(x), np.diff(np.diff(x))
    var_x = np.var(x) + 1e-10
    mob = np.sqrt(np.var(dx) / var_x)
    features.extend([var_x, mob, np.sqrt(np.var(ddx)/(np.var(dx)+1e-10))/(mob+1e-10)])
    features.append(np.sum(np.diff(np.sign(x)) != 0) / len(x))
    mu_mask = (freqs >= 8) & (freqs <= 12)
    features.append(freqs[mu_mask][np.argmax(psd[mu_mask])] if np.any(mu_mask) else 10)
    return np.array(features, dtype=np.float32)


# ──────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────
WINDOW_SEC = 2.0
STEP_SEC = 0.3
WINDOW_SAMPLES = int(WINDOW_SEC * SAMPLING_RATE)
BUF_SIZE = 5000


# ──────────────────────────────────────────────
# SERIAL READER (same as before)
# ──────────────────────────────────────────────
class SerialReader(threading.Thread):
    def __init__(self, port, baud=BAUD_RATE):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self.buf = deque(maxlen=BUF_SIZE)
        self._running = False
        self._lock = threading.Lock()

    def run(self):
        import serial as s
        self._running = True
        try:
            ser = s.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            for _ in range(20): ser.readline()
            logger.info(f"Serial OK ({self.port})")
            while self._running:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line and not line.startswith("#"):
                        with self._lock:
                            self.buf.append(float(line.split(",")[0]))
                except (ValueError, UnicodeDecodeError):
                    pass
            ser.close()
        except Exception as e:
            logger.error(f"Serial: {e}")
            self._running = False

    def stop(self): self._running = False

    def get_window(self, n):
        with self._lock:
            if len(self.buf) < n: return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hybrid Brain+Camera Mouse")
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=12)
    parser.add_argument("--threshold", type=float, default=0.62,
                        help="Min confidence to move (default: 0.62)")
    parser.add_argument("--smooth", type=int, default=2)
    parser.add_argument("--no-camera", action="store_true")
    parser.add_argument("--model", default=str(MODELS_DIR / "brain_2class_model.pkl"))
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    # Load model
    logger.info(f"Loading: {args.model}")
    with open(args.model, "rb") as f:
        model_data = pickle.load(f)
    model = model_data["model"]
    logger.info(f"  CV accuracy: {model_data.get('cv_accuracy', '?'):.1%}")

    # Start camera
    eye_tracker = None
    if not args.no_camera:
        try:
            from src.eye_tracker import EyeTracker
            eye_tracker = EyeTracker(show_preview=False)
            eye_tracker.start()
            logger.info("Camera eye tracker started")
        except Exception as e:
            logger.warning(f"Camera unavailable: {e}")

    # Start serial
    reader = SerialReader(args.port)
    reader.start()

    # State
    mode = "HORIZONTAL"  # or "VERTICAL"
    pred_history = deque(maxlen=args.smooth)
    total_moves = 0

    logger.info("")
    logger.info("=" * 60)
    logger.info("  HYBRID BRAIN+CAMERA MOUSE")
    logger.info("=" * 60)
    logger.info(f"  Speed: {args.speed}px | Threshold: {args.threshold}")
    logger.info(f"  Window: {WINDOW_SEC}s | Smooth: {args.smooth}")
    logger.info("")
    logger.info("  BRAIN (C3-C4):")
    logger.info("    LEFT imagery  -> move LEFT/UP")
    logger.info("    RIGHT imagery -> move RIGHT/DOWN")
    logger.info("")
    if eye_tracker:
        logger.info("  CAMERA:")
        logger.info("    BLINK -> Left Click")
        logger.info("    WINK  -> Toggle H/V Mode")
    logger.info("")
    logger.info(f"  Current Mode: [{mode}]")
    logger.info("  Ctrl+C to stop | Corner = failsafe")
    logger.info("=" * 60)

    # Wait for buffer
    logger.info("  Filling buffer...")
    while reader.get_window(WINDOW_SAMPLES) is None:
        time.sleep(0.5)
    logger.info("  Buffer ready! Start imagining.\n")

    try:
        while True:
            # ── Camera events ──
            if eye_tracker:
                event = eye_tracker.get_event(timeout=0.01)
                if event == "BLINK":
                    pyautogui.click()
                    logger.info("  [CAMERA] BLINK -> CLICK")
                elif event == "WINK":
                    mode = "VERTICAL" if mode == "HORIZONTAL" else "HORIZONTAL"
                    logger.info(f"  [CAMERA] WINK -> Mode: {mode}")

            # ── Brain prediction ──
            window = reader.get_window(WINDOW_SAMPLES)
            if window is not None:
                try:
                    feats = extract_features(window).reshape(1, -1)
                    if not np.all(np.isfinite(feats)):
                        time.sleep(STEP_SEC)
                        continue

                    pred = model.predict(feats)[0]
                    proba = model.predict_proba(feats)[0]
                    conf = proba[pred]
                    direction = ["LEFT", "RIGHT"][pred]

                    if conf < args.threshold:
                        pred_history.clear()
                        time.sleep(STEP_SEC)
                        continue

                    pred_history.append(pred)
                    if len(pred_history) < args.smooth or len(set(pred_history)) > 1:
                        time.sleep(STEP_SEC)
                        continue

                    # Move!
                    px = int(args.speed * conf)
                    if mode == "HORIZONTAL":
                        dx = -px if pred == 0 else px
                        dy = 0
                    else:
                        dx = 0
                        dy = -px if pred == 0 else px

                    pyautogui.moveRel(dx, dy, duration=0.02)
                    total_moves += 1

                    dir_label = {
                        ("HORIZONTAL", 0): "LEFT",  ("HORIZONTAL", 1): "RIGHT",
                        ("VERTICAL", 0): "UP",      ("VERTICAL", 1): "DOWN",
                    }[(mode, pred)]

                    logger.info(
                        f"  [{total_moves:4d}] {dir_label:6s} ({conf:.0%}) "
                        f"[{mode[0]}] ({dx:+d},{dy:+d})"
                    )

                except Exception as e:
                    logger.error(f"Predict error: {e}")

            time.sleep(STEP_SEC)

    except KeyboardInterrupt:
        logger.info(f"\nStopped. Moves: {total_moves}")
    except pyautogui.FailSafeException:
        logger.error("\nFailsafe!")
    finally:
        reader.stop()
        if eye_tracker:
            eye_tracker.stop()


if __name__ == "__main__":
    main()
