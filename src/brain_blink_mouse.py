"""
BCI Combined Controller — Blinks + Motor Imagery from ONE EEG channel
=====================================================================
Single BioAmp EXG Pill at C3-C4 bipolar. Detects BOTH:
  - Blink artifacts (large amplitude spikes) for UP/DOWN/Click
  - Motor imagery (LEFT/RIGHT from trained model)

Electrode Setup:
  IN+  ->  C3 (left motor cortex)
  IN-  ->  C4 (right motor cortex)
  GND  ->  Right earlobe

Controls:
  Motor Imagery:
    LEFT fist  -> cursor LEFT
    RIGHT fist -> cursor RIGHT

  Blinks (from same EEG signal):
    1 blink    -> cursor UP
    2 blinks   -> cursor DOWN
    3 blinks   -> Left Click

Usage:
  python -m src.brain_blink_mouse --port COM7
  python -m src.brain_blink_mouse --port COM7 --speed 15

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
from scipy import signal as sig
from scipy.stats import kurtosis, skew

logger = setup_logger("brain_blink")

FS = SAMPLING_RATE
WINDOW_SEC = 2.0
WINDOW_SAMPLES = int(WINDOW_SEC * FS)
STEP_SEC = 0.3
BUF_SIZE = 8000


# ──────────────────────────────────────────────
# Feature extraction (matches training)
# ──────────────────────────────────────────────
def _bp(x, lo, hi, fs):
    nyq = fs / 2
    lo_n, hi_n = max(lo/nyq, 0.01), min(hi/nyq, 0.99)
    if lo_n >= hi_n: return x
    b, a = sig.butter(4, [lo_n, hi_n], btype='band')
    return sig.filtfilt(b, a, x)

def _pp(x, fs):
    b, a = sig.butter(4, [1/(fs/2), 45/(fs/2)], btype='band')
    x = sig.filtfilt(b, a, x)
    b_n, a_n = sig.iirnotch(50, 30, fs)
    return sig.filtfilt(b_n, a_n, x)

def extract_features(epoch, fs=FS):
    x = _pp(epoch, fs)
    f = []
    freqs, psd = sig.welch(x, fs=fs, nperseg=min(256, len(x)))
    total = np.sum(psd) + 1e-10
    for lo, hi in [(4,8),(8,10),(10,12),(12,16),(16,20),(20,30),(30,45)]:
        mask = (freqs >= lo) & (freqs <= hi)
        bp = np.mean(psd[mask]) if np.any(mask) else 0
        f.extend([bp, bp/total])
    mu = _bp(x, 8, 12, fs)
    f.extend([np.var(mu), np.mean(np.abs(mu)), np.max(np.abs(mu)),
              np.sqrt(np.mean(mu**2))])
    beta = _bp(x, 12, 30, fs)
    f.extend([np.var(beta), np.mean(np.abs(beta))])
    f.append(np.var(mu) / (np.var(beta) + 1e-10))
    q = len(x) // 4
    for i in range(4):
        s = x[i*q:(i+1)*q]
        f.append(np.var(_bp(s, 8, 12, fs)) if len(s) > 20 else 0)
    mid = len(x) // 2
    for lo, hi in [(8,12),(12,20),(20,30)]:
        h1, h2 = _bp(x[:mid], lo, hi, fs), _bp(x[mid:], lo, hi, fs)
        f.append((np.var(h2) - np.var(h1)) / (np.var(h1) + 1e-10))
    f.extend([np.mean(x), np.median(x), skew(x), kurtosis(x), np.std(x)])
    f.append(np.sum(x > 0) / len(x))
    dx = np.diff(x)
    ddx = np.diff(dx)
    var_x = np.var(x) + 1e-10
    mob = np.sqrt(np.var(dx) / var_x)
    f.extend([var_x, mob, np.sqrt(np.var(ddx)/(np.var(dx)+1e-10))/(mob+1e-10)])
    f.append(np.sum(np.diff(np.sign(x)) != 0) / len(x))
    mu_mask = (freqs >= 8) & (freqs <= 12)
    f.append(freqs[mu_mask][np.argmax(psd[mu_mask])] if np.any(mu_mask) else 10)
    return np.array(f, dtype=np.float32)


# ──────────────────────────────────────────────
# Serial Reader
# ──────────────────────────────────────────────
class SerialReader(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.buf = deque(maxlen=BUF_SIZE)
        self._running = False
        self._lock = threading.Lock()

    def run(self):
        import serial as s
        self._running = True
        try:
            ser = s.Serial(self.port, BAUD_RATE, timeout=1)
            time.sleep(2)
            for _ in range(20): ser.readline()
            logger.info(f"Serial OK ({self.port})")
            while self._running:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line and not line.startswith("#"):
                        with self._lock:
                            self.buf.append(float(line.split(",")[0]))
                except: pass
            ser.close()
        except Exception as e:
            logger.error(f"Serial: {e}")
            self._running = False

    def stop(self): self._running = False

    def get_window(self, n):
        with self._lock:
            if len(self.buf) < n: return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)

    def get_recent(self, n):
        """Get most recent n samples for blink detection."""
        with self._lock:
            if len(self.buf) < n: return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)


# ──────────────────────────────────────────────
# Blink Detector (from EEG signal)
# ──────────────────────────────────────────────
class BlinkDetector:
    """
    Detects blinks from C3-C4 EEG signal.
    Blinks appear as large transient spikes even at motor cortex
    electrodes because EOG artifacts propagate across the scalp.
    """

    def __init__(self, fs=FS):
        self.fs = fs
        self.baseline_rms = None
        self.blink_threshold = None

        # Blink counting
        self.blink_times = []           # timestamps of detected blinks
        self.blink_window = 1.5         # seconds to count blinks
        self.last_blink_action = 0      # cooldown timestamp
        self.action_cooldown = 2.0      # seconds between actions
        self.in_blink = False
        self.blink_samples = 0

    def calibrate(self, resting_data):
        """Set blink threshold from resting EEG (no blinks)."""
        self.baseline_rms = np.sqrt(np.mean(resting_data**2))
        # Blinks are typically 3-8x the resting amplitude
        self.blink_threshold = self.baseline_rms * 3.5
        logger.info(f"  Blink detector: baseline RMS={self.baseline_rms:.1f}, "
                     f"threshold={self.blink_threshold:.1f}")

    def detect(self, recent_samples):
        """
        Check most recent samples for a blink.
        Returns: number of blinks detected (0, 1, 2, 3) or None if cooling down.
        """
        if self.blink_threshold is None:
            return 0

        now = time.time()

        # Check cooldown
        if now - self.last_blink_action < self.action_cooldown:
            return 0

        # Look at recent ~100ms of signal for spike detection
        check_n = int(0.1 * self.fs)  # 25 samples at 250Hz
        if len(recent_samples) < check_n:
            return 0

        window = recent_samples[-check_n:]
        peak = np.max(np.abs(window - np.mean(window)))

        # Blink detection (rising edge)
        if peak > self.blink_threshold and not self.in_blink:
            self.in_blink = True
            self.blink_samples = 0
            self.blink_times.append(now)

        elif peak < self.blink_threshold * 0.5:
            self.in_blink = False

        if self.in_blink:
            self.blink_samples += 1

        # Remove old blinks outside window
        self.blink_times = [t for t in self.blink_times
                            if now - t < self.blink_window]

        # Check if we have a complete blink pattern
        # (wait 0.8s after last blink to see if more are coming)
        if len(self.blink_times) > 0:
            time_since_last = now - self.blink_times[-1]
            if time_since_last > 0.8:
                count = len(self.blink_times)
                self.blink_times.clear()
                self.last_blink_action = now
                return min(count, 3)

        return 0


# ──────────────────────────────────────────────
# Main Controller
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Brain+Blink Mouse Controller")
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=12)
    parser.add_argument("--mi-threshold", type=float, default=0.55,
                        help="MI confidence threshold (default: 0.55)")
    parser.add_argument("--blink-scale", type=float, default=3.5,
                        help="Blink detection sensitivity (lower=more sensitive)")
    parser.add_argument("--jump", type=int, default=50,
                        help="Pixels per blink action (default: 50)")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    # Load MI model
    logger.info("Loading motor imagery model...")
    try:
        with open(MODELS_DIR / "brain_2class_model.pkl", "rb") as f:
            md = pickle.load(f)
        model = md["model"]
        logger.info(f"  Model loaded (CV: {md.get('cv_accuracy', '?'):.1%})")
    except FileNotFoundError:
        logger.error("No model found! Run training first.")
        return

    # Start serial
    reader = SerialReader(args.port)
    reader.start()

    # Wait for buffer
    logger.info("  Filling buffer...")
    while reader.get_window(WINDOW_SAMPLES) is None:
        time.sleep(0.5)
    logger.info("  Buffer ready!")

    # Calibrate blink detector
    blink_det = BlinkDetector()
    blink_det.blink_threshold = None

    logger.info("\n  CALIBRATING: Relax for 5 seconds. DO NOT BLINK.\n")
    time.sleep(2)
    logger.info("  >>> Measuring baseline NOW (keep eyes open)...")

    resting_samples = []
    start = time.time()
    while time.time() - start < 5:
        w = reader.get_recent(50)
        if w is not None:
            resting_samples.extend(w[-10:])
        time.sleep(0.1)

    resting_data = np.array(resting_samples, dtype=np.float64)
    blink_det.calibrate(resting_data)
    blink_det.blink_threshold *= (args.blink_scale / 3.5)

    # Ready
    logger.info("\n" + "=" * 60)
    logger.info("  BRAIN + BLINK MOUSE CONTROLLER")
    logger.info("=" * 60)
    logger.info(f"  Electrodes: IN+=C3, IN-=C4, GND=Earlobe")
    logger.info(f"  Speed: {args.speed}px  |  Jump: {args.jump}px")
    logger.info("")
    logger.info("  BRAIN (Motor Imagery):")
    logger.info("    LEFT fist  -> cursor LEFT")
    logger.info("    RIGHT fist -> cursor RIGHT")
    logger.info("")
    logger.info("  BLINKS (from same EEG signal):")
    logger.info("    1 blink    -> cursor UP")
    logger.info("    2 blinks   -> cursor DOWN")
    logger.info("    3 blinks   -> LEFT CLICK")
    logger.info("")
    logger.info("  Ctrl+C = stop  |  Corner = failsafe")
    logger.info("=" * 60 + "\n")

    # State
    moves = 0
    left_c = right_c = up_c = down_c = click_c = 0
    pred_history = deque(maxlen=2)
    last_mi = time.time()
    blink_pause = False     # pause MI during blink
    blink_pause_until = 0

    try:
        while True:
            now = time.time()

            # ── Blink Detection (priority over MI) ──
            recent = reader.get_recent(200)
            if recent is not None:
                blink_count = blink_det.detect(recent)

                if blink_count == 1:
                    pyautogui.moveRel(0, -args.jump, duration=0.1)
                    up_c += 1
                    moves += 1
                    blink_pause_until = now + 1.5
                    pred_history.clear()
                    logger.info(f"  [BLINK x1] UP (+{args.jump}px) "
                                f"[L:{left_c} R:{right_c} U:{up_c} D:{down_c}]")

                elif blink_count == 2:
                    pyautogui.moveRel(0, args.jump, duration=0.1)
                    down_c += 1
                    moves += 1
                    blink_pause_until = now + 1.5
                    pred_history.clear()
                    logger.info(f"  [BLINK x2] DOWN (+{args.jump}px) "
                                f"[L:{left_c} R:{right_c} U:{up_c} D:{down_c}]")

                elif blink_count >= 3:
                    pyautogui.click()
                    click_c += 1
                    blink_pause_until = now + 2.0
                    pred_history.clear()
                    logger.info(f"  [BLINK x3] CLICK! (total clicks: {click_c})")

            # ── Motor Imagery (LEFT/RIGHT) ──
            if now < blink_pause_until:
                # Pause MI after blink to avoid false triggers
                time.sleep(STEP_SEC)
                continue

            if now - last_mi >= STEP_SEC:
                last_mi = now
                window = reader.get_window(WINDOW_SAMPLES)
                if window is not None:
                    try:
                        feats = extract_features(window).reshape(1, -1)
                        if not np.all(np.isfinite(feats)):
                            continue

                        pred = model.predict(feats)[0]
                        proba = model.predict_proba(feats)[0]
                        conf = proba[pred]

                        if conf < args.mi_threshold:
                            pred_history.clear()
                            time.sleep(STEP_SEC)
                            continue

                        # Smoothing: 2 consecutive same prediction
                        pred_history.append(pred)
                        if len(pred_history) < 2 or len(set(pred_history)) > 1:
                            time.sleep(STEP_SEC)
                            continue

                        # Move LEFT or RIGHT
                        name = ["LEFT", "RIGHT"][pred]
                        px = int(args.speed * conf)
                        dx = -px if pred == 0 else px

                        pyautogui.moveRel(dx, 0, duration=0.02)
                        moves += 1
                        if pred == 0: left_c += 1
                        else: right_c += 1

                        logger.info(
                            f"  [MI] {name:5s} ({conf:.0%}) dx={dx:+d} "
                            f"[L:{left_c} R:{right_c} U:{up_c} D:{down_c}]"
                        )

                    except Exception as e:
                        logger.error(f"MI error: {e}")

            time.sleep(0.05)

    except KeyboardInterrupt:
        logger.info(
            f"\nDone. Total moves={moves} "
            f"(L:{left_c} R:{right_c} U:{up_c} D:{down_c}) "
            f"Clicks:{click_c}"
        )
    except pyautogui.FailSafeException:
        logger.error("\nFailsafe!")
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
