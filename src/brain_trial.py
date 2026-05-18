"""
Brain Mouse — Discrete Trial Mode.
Matches training exactly: 4-second focused imagery -> one big cursor step.

Flow:
  1. RELAX state (cursor still, baseline recording)
  2. Press SPACE -> "IMAGINE NOW" for 4 seconds
  3. Model classifies the 4-second window -> cursor jumps LEFT or RIGHT
  4. Back to RELAX

This matches the training paradigm exactly (4s epochs, not sliding windows).
"""
import argparse, time, threading, pickle
from collections import deque
import numpy as np

try:
    import pygame
except ImportError:
    pygame = None

import pyautogui
from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, MODELS_DIR, setup_logger
from scipy import signal as sig
from scipy.stats import kurtosis, skew

logger = setup_logger("brain_trial")

FS = SAMPLING_RATE
IMAGINE_SEC = 4.0
IMAGINE_SAMPLES = int(IMAGINE_SEC * FS)

# ── Feature extraction (identical to training) ──
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


class Reader(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.buf = deque(maxlen=10000)
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
    def clear_buf(self):
        with self._lock:
            self.buf.clear()
    def get_recent(self, n):
        with self._lock:
            if len(self.buf) < n: return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)
    def buf_len(self):
        with self._lock:
            return len(self.buf)


def txt(screen, font, text, color, x, y):
    surf = font.render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(x, y)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--jump", type=int, default=100,
                        help="Pixels to move per trial (default 100)")
    args = parser.parse_args()

    if pygame is None:
        logger.error("pip install pygame")
        return

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    # Load model
    logger.info("Loading model...")
    with open(MODELS_DIR / "brain_2class_model.pkl", "rb") as f:
        md = pickle.load(f)
    model = md["model"]
    logger.info(f"  Model CV: {md.get('cv_accuracy','?'):.1%}")

    # Serial
    reader = Reader(args.port)
    reader.start()
    time.sleep(3)

    # Pygame display (instruction window)
    pygame.init()
    W, H = 700, 400
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Brain Mouse - Trial Mode")
    fonts = {
        "big":   pygame.font.SysFont("Segoe UI", 60, bold=True),
        "med":   pygame.font.SysFont("Segoe UI", 30),
        "small": pygame.font.SysFont("Segoe UI", 20),
        "info":  pygame.font.SysFont("Consolas", 16),
    }

    BG = (15, 15, 25)
    GREEN = (100, 255, 100)
    CYAN = (0, 200, 255)
    ORANGE = (255, 166, 0)
    RED = (255, 80, 80)
    GRAY = (120, 120, 140)
    WHITE = (220, 220, 230)

    mode = "H"  # H=horizontal, V=vertical
    trials = 0
    left_c = right_c = correct_c = 0
    running = True

    while running:
        # ── IDLE STATE: Show instructions ──
        screen.fill(BG)
        txt(screen, fonts["med"], "BRAIN MOUSE - Trial Mode", CYAN, W//2, 30)
        txt(screen, fonts["small"],
            f"Mode: {'HORIZONTAL' if mode=='H' else 'VERTICAL'}  |  "
            f"Jump: {args.jump}px  |  Trials: {trials}",
            GRAY, W//2, 65)

        txt(screen, fonts["big"], "RELAX", GRAY, W//2, 150)
        txt(screen, fonts["small"], "Stay still. Clear your mind.", GRAY, W//2, 200)

        txt(screen, fonts["med"], "Press L = imagine LEFT, then record", CYAN, W//2, 260)
        txt(screen, fonts["med"], "Press R = imagine RIGHT, then record", ORANGE, W//2, 295)
        txt(screen, fonts["small"], "Press M = toggle H/V mode  |  ESC = quit", GRAY, W//2, 340)
        txt(screen, fonts["info"],
            f"Results: L={left_c}  R={right_c}  Total={trials}",
            WHITE, W//2, 375)
        pygame.display.flip()

        # Wait for keypress
        waiting = True
        intended = None
        while waiting and running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                    waiting = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                        waiting = False
                    elif ev.key == pygame.K_l:
                        intended = 0  # LEFT
                        waiting = False
                    elif ev.key == pygame.K_r:
                        intended = 1  # RIGHT
                        waiting = False
                    elif ev.key == pygame.K_m:
                        mode = "V" if mode == "H" else "H"
                        # Just update display
            time.sleep(0.05)

        if not running or intended is None:
            break

        intent_name = ["LEFT", "RIGHT"][intended]
        intent_color = CYAN if intended == 0 else ORANGE

        # ── READY: 2 second countdown ──
        for countdown in [2, 1]:
            screen.fill(BG)
            txt(screen, fonts["big"], str(countdown), WHITE, W//2, 120)
            txt(screen, fonts["med"], f"Get ready to imagine {intent_name}",
                intent_color, W//2, 220)
            txt(screen, fonts["small"], "Focus! Stay still!", GRAY, W//2, 260)
            pygame.display.flip()
            time.sleep(1.0)

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False

        if not running:
            break

        # ── IMAGINE: Record 4 seconds ──
        reader.clear_buf()  # Start fresh
        screen.fill(BG)

        # Draw big arrow
        if intended == 0:
            pts = [(W//2+60, H//2-80), (W//2-80, H//2-20), (W//2+60, H//2+40)]
        else:
            pts = [(W//2-60, H//2-80), (W//2+80, H//2-20), (W//2-60, H//2+40)]
        pygame.draw.polygon(screen, intent_color, pts)

        txt(screen, fonts["big"], "IMAGINE NOW!", GREEN, W//2, H//2 + 100)
        txt(screen, fonts["med"], f"Squeeze {intent_name} fist!", intent_color, W//2, H//2 + 150)

        # Progress bar
        bar_y = H - 40
        bar_w = W - 100
        bar_x = 50

        pygame.display.flip()

        start = time.time()
        while time.time() - start < IMAGINE_SEC:
            elapsed = time.time() - start
            frac = elapsed / IMAGINE_SEC

            # Update progress bar
            pygame.draw.rect(screen, (40, 40, 60), (bar_x, bar_y, bar_w, 15), border_radius=7)
            fill = int(bar_w * frac)
            if fill > 0:
                pygame.draw.rect(screen, GREEN, (bar_x, bar_y, fill, 15), border_radius=7)
            pygame.display.flip()

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
            time.sleep(0.05)

        if not running:
            break

        # ── CLASSIFY ──
        epoch = reader.get_recent(IMAGINE_SAMPLES)
        if epoch is None or len(epoch) < 500:
            screen.fill(BG)
            txt(screen, fonts["big"], "NO DATA", RED, W//2, H//2)
            txt(screen, fonts["small"], "Not enough samples recorded", GRAY, W//2, H//2+50)
            pygame.display.flip()
            time.sleep(2)
            continue

        f = feats(epoch).reshape(1, -1)
        if not np.all(np.isfinite(f)):
            screen.fill(BG)
            txt(screen, fonts["big"], "BAD SIGNAL", RED, W//2, H//2)
            pygame.display.flip()
            time.sleep(2)
            continue

        pred = model.predict(f)[0]
        proba = model.predict_proba(f)[0]
        conf = proba[pred]
        pred_name = ["LEFT", "RIGHT"][pred]
        pred_color = CYAN if pred == 0 else ORANGE
        correct = (pred == intended)

        trials += 1
        if pred == 0: left_c += 1
        else: right_c += 1
        if correct: correct_c += 1

        # Move cursor
        px = args.jump
        if mode == "H":
            dx = -px if pred == 0 else px
            dy = 0
        else:
            dx = 0
            dy = -px if pred == 0 else px

        pyautogui.moveRel(dx, dy, duration=0.3)

        # Show result
        screen.fill(BG)
        result_text = "CORRECT!" if correct else "WRONG"
        result_color = GREEN if correct else RED
        txt(screen, fonts["big"], pred_name, pred_color, W//2, 80)
        txt(screen, fonts["med"], f"Confidence: {conf:.0%}", WHITE, W//2, 140)
        txt(screen, fonts["med"], result_text, result_color, W//2, 190)
        txt(screen, fonts["small"],
            f"You intended: {intent_name}  |  Model said: {pred_name}",
            GRAY, W//2, 240)
        txt(screen, fonts["small"],
            f"Cursor moved {pred_name} by {px}px",
            pred_color, W//2, 275)
        txt(screen, fonts["info"],
            f"Accuracy so far: {correct_c}/{trials} = {correct_c/trials:.0%}",
            WHITE, W//2, 320)
        txt(screen, fonts["small"], "Press L/R for next trial", GRAY, W//2, 360)
        pygame.display.flip()

        logger.info(
            f"  Trial {trials}: intended={intent_name} predicted={pred_name} "
            f"conf={conf:.0%} {'OK' if correct else 'WRONG'} "
            f"[acc: {correct_c}/{trials}={correct_c/trials:.0%}]"
        )

        # Wait briefly
        time.sleep(2)

    # Done
    if trials > 0:
        logger.info(f"\nFinal: {correct_c}/{trials} = {correct_c/trials:.0%} accuracy")

    pygame.quit()
    reader.stop()


if __name__ == "__main__":
    main()
