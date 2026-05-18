"""
Brain-Only Mouse — with REST detection via probability gap.
Only moves when the model STRONGLY favors one direction.
"""
import argparse, time, pickle, threading
from collections import deque
import numpy as np
import pyautogui
from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, MODELS_DIR, setup_logger
from scipy import signal as sig
from scipy.stats import kurtosis, skew

logger = setup_logger("brain_test")

FS = SAMPLING_RATE
WINDOW_SEC = 2.0
STEP_SEC = 0.3
WINDOW_SAMPLES = int(WINDOW_SEC * FS)
BUF_SIZE = 5000

# ── Feature extraction (must match training) ──
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

def feats(epoch, fs=FS):
    x = _pp(epoch, fs)
    f = []
    freqs, psd = sig.welch(x, fs=fs, nperseg=min(256, len(x)))
    total = np.sum(psd) + 1e-10
    for lo, hi in [(4,8),(8,10),(10,12),(12,16),(16,20),(20,30),(30,45)]:
        mask = (freqs >= lo) & (freqs <= hi)
        bp = np.mean(psd[mask]) if np.any(mask) else 0
        f.extend([bp, bp/total])
    mu = _bp(x, 8, 12, fs)
    f.extend([np.var(mu), np.mean(np.abs(mu)), np.max(np.abs(mu)), np.sqrt(np.mean(mu**2))])
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

# ── Serial ──
class Reader(threading.Thread):
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


def calibrate_baseline(model, reader, window_samples, duration=6):
    """Record resting-state predictions for baseline."""
    logger.info("  CALIBRATING: Relax and do NOT imagine anything for 6 seconds...")
    time.sleep(2)
    logger.info("  >>> Relax NOW...")

    rest_probas = []
    start = time.time()
    while time.time() - start < duration:
        w = reader.get_window(window_samples)
        if w is not None:
            f = feats(w).reshape(1, -1)
            if np.all(np.isfinite(f)):
                proba = model.predict_proba(f)[0]
                rest_probas.append(proba)
        time.sleep(0.3)

    if not rest_probas:
        return 0.5, 0.1  # defaults

    rest_arr = np.array(rest_probas)
    rest_gap_mean = np.mean(np.abs(rest_arr[:, 0] - rest_arr[:, 1]))
    rest_gap_std = np.std(np.abs(rest_arr[:, 0] - rest_arr[:, 1]))

    # The threshold = resting gap + 2 standard deviations
    threshold = rest_gap_mean + 2 * rest_gap_std
    threshold = max(threshold, 0.12)  # minimum gap

    rest_bias = np.mean(rest_arr[:, 1])  # average RIGHT probability at rest
    logger.info(f"  Resting bias: LEFT={np.mean(rest_arr[:, 0]):.0%} RIGHT={rest_bias:.0%}")
    logger.info(f"  Resting gap: {rest_gap_mean:.0%} +/- {rest_gap_std:.0%}")
    logger.info(f"  Movement threshold: gap > {threshold:.0%}")

    return rest_bias, threshold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=12)
    parser.add_argument("--gap", type=float, default=0.0,
                        help="Min probability gap to move (0=auto-calibrate)")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    logger.info("Loading model...")
    with open(MODELS_DIR / "brain_2class_model.pkl", "rb") as f:
        md = pickle.load(f)
    model = md["model"]
    logger.info(f"  CV: {md.get('cv_accuracy','?'):.1%}")

    reader = Reader(args.port)
    reader.start()

    logger.info("  Filling buffer...")
    while reader.get_window(WINDOW_SAMPLES) is None:
        time.sleep(0.5)
    logger.info("  Buffer ready!")

    # Auto-calibrate resting baseline
    rest_bias, gap_threshold = calibrate_baseline(model, reader, WINDOW_SAMPLES)
    if args.gap > 0:
        gap_threshold = args.gap

    logger.info("")
    logger.info("=" * 60)
    logger.info("  BRAIN MOUSE (LEFT vs RIGHT + REST detection)")
    logger.info("=" * 60)
    logger.info(f"  Speed={args.speed}px  Gap threshold={gap_threshold:.0%}")
    logger.info(f"  REST = when |P(L)-P(R)| < {gap_threshold:.0%}")
    logger.info("")
    logger.info("  Imagine LEFT fist  -> cursor LEFT")
    logger.info("  Imagine RIGHT fist -> cursor RIGHT")
    logger.info("  Relax              -> cursor STAYS STILL")
    logger.info("  Ctrl+C = stop")
    logger.info("=" * 60 + "\n")

    moves = 0
    left_count = 0
    right_count = 0
    rest_count = 0
    pred_history = deque(maxlen=2)  # require 2 consecutive

    try:
        while True:
            w = reader.get_window(WINDOW_SAMPLES)
            if w is not None:
                try:
                    f = feats(w).reshape(1, -1)
                    if not np.all(np.isfinite(f)):
                        time.sleep(STEP_SEC)
                        continue

                    proba = model.predict_proba(f)[0]
                    p_left, p_right = proba[0], proba[1]
                    gap = abs(p_left - p_right)
                    pred = 0 if p_left > p_right else 1

                    # REST detection: gap too small = ambiguous = rest
                    if gap < gap_threshold:
                        pred_history.clear()
                        rest_count += 1
                        if rest_count % 15 == 0:
                            logger.info(
                                f"  ... REST (L:{p_left:.0%} R:{p_right:.0%} "
                                f"gap:{gap:.0%} < {gap_threshold:.0%}) "
                                f"[resting {rest_count}]"
                            )
                        time.sleep(STEP_SEC)
                        continue

                    # Smoothing: need 2 consecutive same direction
                    pred_history.append(pred)
                    if len(pred_history) < 2 or len(set(pred_history)) > 1:
                        time.sleep(STEP_SEC)
                        continue

                    # MOVE
                    name = ["LEFT", "RIGHT"][pred]
                    conf = proba[pred]
                    px = int(args.speed * conf)
                    dx = -px if pred == 0 else px

                    pyautogui.moveRel(dx, 0, duration=0.02)
                    moves += 1
                    if pred == 0: left_count += 1
                    else: right_count += 1

                    logger.info(
                        f"  [{moves:4d}] {name:5s} ({conf:.0%}, gap:{gap:.0%}) "
                        f"dx={dx:+d}  [L:{left_count} R:{right_count}]"
                    )

                except Exception as e:
                    logger.error(f"Error: {e}")
            time.sleep(STEP_SEC)

    except KeyboardInterrupt:
        logger.info(
            f"\nDone. Moves={moves} (L:{left_count} R:{right_count}) "
            f"Rest={rest_count}"
        )
    except pyautogui.FailSafeException:
        logger.error("\nFailsafe!")
    finally:
        reader.stop()

if __name__ == "__main__":
    main()
