"""
Brain Mouse — Adaptive Baseline (tracks mu-band drift in real-time).
Only detects FAST changes, not slow drift.
"""
import argparse, time, threading
from collections import deque
import numpy as np
import pyautogui
from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, setup_logger
from scipy import signal as sig

logger = setup_logger("brain_direct")

FS = SAMPLING_RATE
WINDOW_SEC = 2.0
STEP_SEC = 0.25
WINDOW_SAMPLES = int(WINDOW_SEC * FS)
BUF_SIZE = 5000


def bandpass(x, lo, hi, fs):
    nyq = fs / 2
    b, a = sig.butter(4, [lo/nyq, hi/nyq], btype='band')
    return sig.filtfilt(b, a, x)


def get_mu_power(x, fs=FS):
    filtered = bandpass(x, 8, 12, fs)
    return np.sqrt(np.mean(filtered**2))


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=15)
    parser.add_argument("--sensitivity", type=float, default=1.8,
                        help="SDs above/below adaptive baseline (default 1.8)")
    parser.add_argument("--adapt-rate", type=float, default=0.05,
                        help="How fast baseline adapts 0-1 (0.05=slow, 0.2=fast)")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    reader = Reader(args.port)
    reader.start()

    logger.info("  Filling buffer...")
    while reader.get_window(WINDOW_SAMPLES) is None:
        time.sleep(0.5)
    logger.info("  Buffer ready!")

    # Initial calibration — measure resting mu statistics
    logger.info("\n  CALIBRATING (8s): RELAX completely...\n")
    time.sleep(2)
    logger.info("  >>> Measuring NOW...")

    mu_samples = []
    start = time.time()
    while time.time() - start < 8:
        w = reader.get_window(WINDOW_SAMPLES)
        if w is not None:
            w = w - np.mean(w)
            mu_samples.append(get_mu_power(w))
        time.sleep(0.2)

    # Adaptive baseline starts at calibration mean
    mu_ema = np.mean(mu_samples)      # exponential moving average (adaptive center)
    mu_var_ema = np.var(mu_samples)    # adaptive variance
    alpha = args.adapt_rate            # EMA smoothing factor

    logger.info(f"  Initial mu baseline: {mu_ema:.2f}")
    logger.info(f"  Initial mu std: {np.sqrt(mu_var_ema):.2f}")

    logger.info("\n" + "=" * 60)
    logger.info("  BRAIN MOUSE (Adaptive Baseline)")
    logger.info("=" * 60)
    logger.info(f"  Speed={args.speed}px  Sensitivity={args.sensitivity}SD")
    logger.info(f"  Adapt rate={alpha}")
    logger.info("")
    logger.info("  Imagine LEFT fist  -> cursor LEFT  (mu rises quickly)")
    logger.info("  Imagine RIGHT fist -> cursor RIGHT (mu drops quickly)")
    logger.info("  Relax              -> cursor STAYS STILL")
    logger.info("  Ctrl+C = stop")
    logger.info("=" * 60 + "\n")

    moves = 0
    left_c = right_c = rest_c = 0
    pred_history = deque(maxlen=2)
    last_log = 0
    mode = "H"

    try:
        while True:
            w = reader.get_window(WINDOW_SAMPLES)
            if w is None:
                time.sleep(STEP_SEC)
                continue

            w = w - np.mean(w)
            mu = get_mu_power(w)
            rms = np.sqrt(np.mean(w**2))

            # Current adaptive threshold
            mu_std = np.sqrt(mu_var_ema) + 1e-10
            upper = mu_ema + args.sensitivity * mu_std
            lower = mu_ema - args.sensitivity * mu_std

            # Detect jaw clench (huge RMS spike)
            if rms > 500:
                # Don't update baseline during clench
                mode = "V" if mode == "H" else "H"
                logger.info(f"  >>> CLENCH (rms={rms:.0f}) -> Mode: {'HORIZ' if mode=='H' else 'VERT'}")
                pred_history.clear()
                time.sleep(1.0)
                continue

            # Classify
            if mu > upper:
                direction = 0  # LEFT
            elif mu < lower:
                direction = 1  # RIGHT
            else:
                direction = -1  # REST

            if direction == -1:
                # REST: update baseline toward current mu (track drift)
                mu_ema = (1 - alpha) * mu_ema + alpha * mu
                mu_var_ema = (1 - alpha) * mu_var_ema + alpha * (mu - mu_ema)**2
                pred_history.clear()
                rest_c += 1

                now = time.time()
                if now - last_log > 4:
                    logger.info(
                        f"  ... REST (mu={mu:.1f}, base={mu_ema:.1f}+/-{mu_std:.1f}, "
                        f"range=[{lower:.1f}, {upper:.1f}]) [rest {rest_c}]"
                    )
                    last_log = now
            else:
                # ACTIVE: update baseline SLOWER during movement (don't chase it)
                slow_alpha = alpha * 0.3
                mu_ema = (1 - slow_alpha) * mu_ema + slow_alpha * mu
                mu_var_ema = (1 - slow_alpha) * mu_var_ema + slow_alpha * (mu - mu_ema)**2

                # Smoothing: need 2 consecutive same direction
                pred_history.append(direction)
                if len(pred_history) < 2 or len(set(pred_history)) > 1:
                    time.sleep(STEP_SEC)
                    continue

                # MOVE
                deviation = abs(mu - mu_ema) / mu_std
                px = int(args.speed * min(deviation / 3, 1.5))
                px = max(px, 5)

                if mode == "H":
                    dx = -px if direction == 0 else px
                    dy = 0
                else:
                    dx = 0
                    dy = -px if direction == 0 else px

                name = {("H",0):"LEFT", ("H",1):"RIGHT",
                        ("V",0):"UP",   ("V",1):"DOWN"}[(mode, direction)]

                pyautogui.moveRel(dx, dy, duration=0.02)
                moves += 1
                if direction == 0: left_c += 1
                else: right_c += 1

                logger.info(
                    f"  [{moves:4d}] {name:5s} (mu={mu:.1f}, base={mu_ema:.1f}, "
                    f"{deviation:.1f}SD) [{mode}] ({dx:+d},{dy:+d}) "
                    f"[L:{left_c} R:{right_c}]"
                )

            time.sleep(STEP_SEC)

    except KeyboardInterrupt:
        logger.info(f"\nDone. Moves={moves} (L:{left_c} R:{right_c}) Rest={rest_c}")
    except pyautogui.FailSafeException:
        logger.error("\nFailsafe!")
    finally:
        reader.stop()


if __name__ == "__main__":
    main()
