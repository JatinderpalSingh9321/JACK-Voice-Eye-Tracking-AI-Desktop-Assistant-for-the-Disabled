"""
BCI Assistive Control - SSVEP Mouse Controller
=================================================
Steady-State Visual Evoked Potentials (SSVEP) based cursor control.

How it works:
  1. Screen shows 4 flickering targets (LEFT, RIGHT, UP, DOWN)
  2. Each target flickers at a unique frequency
  3. When you LOOK at a target, your visual cortex generates a
     brain response at that exact frequency
  4. We detect the frequency via FFT -> move cursor in that direction
  5. Look at CENTER (no target) -> cursor stays still
  6. BLINK both eyes briefly -> Click

Electrode Setup (1 BioAmp EXG Pill):
  IN+  ->  Oz (back of skull, just above neck bump)
  IN-  ->  Right earlobe
  GND  ->  Left earlobe

Usage:
  python -m src.ssvep_mouse --port COM7
  python -m src.ssvep_mouse --port COM7 --speed 20

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import threading
from collections import deque

import numpy as np
import pygame
import pyautogui

from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, setup_logger
from scipy import signal as sig

logger = setup_logger("ssvep_mouse")

FS = SAMPLING_RATE
BUF_SIZE = 8000

# ──────────────────────────────────────────────
# SSVEP FREQUENCIES
# ──────────────────────────────────────────────
# Chosen to be distinguishable and achievable on 60Hz displays
TARGETS = {
    "LEFT":  {"freq": 7.5,  "color": (0, 200, 255),  "pos": "left"},
    "RIGHT": {"freq": 10.0, "color": (255, 166, 0),   "pos": "right"},
    "UP":    {"freq": 12.0, "color": (100, 255, 100),  "pos": "top"},
    "DOWN":  {"freq": 15.0, "color": (255, 100, 100),  "pos": "bottom"},
}

# Analysis
ANALYSIS_WINDOW_SEC = 3.0  # seconds of EEG for FFT
ANALYSIS_SAMPLES = int(ANALYSIS_WINDOW_SEC * FS)
STEP_SEC = 0.3             # analyze every 0.3s

# Detection
SNR_THRESHOLD = 1.5        # signal-to-noise ratio threshold
MIN_POWER_RATIO = 1.3      # winning frequency must be 1.3x stronger than second


# ──────────────────────────────────────────────
# SERIAL READER
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
            for _ in range(20):
                ser.readline()
            logger.info(f"Serial OK ({self.port})")
            while self._running:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line and not line.startswith("#"):
                        with self._lock:
                            self.buf.append(float(line.split(",")[0]))
                except:
                    pass
            ser.close()
        except Exception as e:
            logger.error(f"Serial: {e}")
            self._running = False

    def stop(self):
        self._running = False

    def get_window(self, n):
        with self._lock:
            if len(self.buf) < n:
                return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)


# ──────────────────────────────────────────────
# SSVEP DETECTION
# ──────────────────────────────────────────────
def preprocess(x, fs=FS):
    """Bandpass 3-45Hz + notch 50Hz."""
    nyq = fs / 2
    b, a = sig.butter(4, [3/nyq, 45/nyq], btype='band')
    x = sig.filtfilt(b, a, x)
    b_n, a_n = sig.iirnotch(50, 30, fs)
    x = sig.filtfilt(b_n, a_n, x)
    return x


def detect_ssvep(eeg, target_freqs, fs=FS):
    """
    Detect which SSVEP frequency is present in the EEG.

    Returns: (detected_direction, confidence, powers_dict)
      detected_direction: "LEFT"/"RIGHT"/"UP"/"DOWN" or None
      confidence: relative power of detected freq
      powers_dict: power at each target frequency
    """
    x = preprocess(eeg, fs)
    x = x - np.mean(x)  # remove DC

    # Compute PSD with good frequency resolution
    n = len(x)
    nperseg = min(n, int(fs * 2))  # 2-second segments for ~0.5Hz resolution
    freqs, psd = sig.welch(x, fs=fs, nperseg=nperseg, noverlap=nperseg//2)

    # Extract power at each target frequency (and its 2nd harmonic)
    powers = {}
    freq_resolution = freqs[1] - freqs[0]

    for name, info in TARGETS.items():
        f = info["freq"]
        # Power at fundamental frequency (within +/- 0.5Hz)
        mask_f1 = (freqs >= f - 0.5) & (freqs <= f + 0.5)
        p1 = np.max(psd[mask_f1]) if np.any(mask_f1) else 0

        # Power at 2nd harmonic
        f2 = f * 2
        mask_f2 = (freqs >= f2 - 0.5) & (freqs <= f2 + 0.5)
        p2 = np.max(psd[mask_f2]) if np.any(mask_f2) else 0

        # Combined (fundamental + harmonic)
        powers[name] = p1 + 0.5 * p2

    # Compute noise floor (average power in non-target bands)
    target_freqs_list = [t["freq"] for t in TARGETS.values()]
    noise_mask = np.ones_like(freqs, dtype=bool)
    for f in target_freqs_list:
        noise_mask &= ~((freqs >= f - 1) & (freqs <= f + 1))
        noise_mask &= ~((freqs >= f*2 - 1) & (freqs <= f*2 + 1))
    noise_mask &= (freqs >= 5) & (freqs <= 40)
    noise_floor = np.mean(psd[noise_mask]) if np.any(noise_mask) else 1e-10

    # Normalize powers by noise floor (SNR)
    snr = {name: p / (noise_floor + 1e-10) for name, p in powers.items()}

    # Find the winning frequency
    sorted_powers = sorted(powers.items(), key=lambda x: x[1], reverse=True)
    best_name, best_power = sorted_powers[0]
    second_power = sorted_powers[1][1] if len(sorted_powers) > 1 else 0

    best_snr = snr[best_name]
    ratio = best_power / (second_power + 1e-10)

    # Detection criteria
    if best_snr >= SNR_THRESHOLD and ratio >= MIN_POWER_RATIO:
        return best_name, best_snr, snr
    else:
        return None, 0, snr


# ──────────────────────────────────────────────
# STIMULUS DISPLAY + CONTROLLER
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SSVEP Mouse Controller")
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--speed", type=int, default=20,
                        help="Cursor movement speed (default: 20)")
    parser.add_argument("--snr", type=float, default=1.5,
                        help="SNR threshold for detection (default: 1.5)")
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()

    global SNR_THRESHOLD
    SNR_THRESHOLD = args.snr

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02

    # Start serial reader
    reader = SerialReader(args.port)
    reader.start()

    # Pygame setup
    pygame.init()

    if args.fullscreen:
        info = pygame.display.Info()
        W, H = info.current_w, info.current_h
        screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN)
    else:
        W, H = 1200, 800
        screen = pygame.display.set_mode((W, H))

    pygame.display.set_caption("SSVEP BCI Mouse Controller")
    clock = pygame.time.Clock()

    fonts = {
        "big":   pygame.font.SysFont("Segoe UI", 36, bold=True),
        "med":   pygame.font.SysFont("Segoe UI", 22),
        "small": pygame.font.SysFont("Segoe UI", 16),
        "info":  pygame.font.SysFont("Consolas", 14),
    }

    BG = (10, 10, 15)
    CENTER_COLOR = (40, 40, 60)
    TEXT_C = (200, 200, 210)
    ACTIVE_C = (255, 255, 255)

    # Target box dimensions and positions
    BOX_W, BOX_H = 120, 120
    targets_pos = {
        "LEFT":  (80, H//2 - BOX_H//2),
        "RIGHT": (W - 80 - BOX_W, H//2 - BOX_H//2),
        "UP":    (W//2 - BOX_W//2, 60),
        "DOWN":  (W//2 - BOX_W//2, H - 60 - BOX_H),
    }

    # State
    frame_count = 0
    detected_dir = None
    last_analysis = 0
    moves = 0
    clicks = 0
    mode_text = "Waiting for signal..."

    # Blink detection state
    blink_frames = 0
    blink_cooldown = 0

    logger.info("\n" + "=" * 60)
    logger.info("  SSVEP BRAIN-CONTROLLED MOUSE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Electrode Setup:")
    logger.info("    IN+  ->  Oz (back of skull)")
    logger.info("    IN-  ->  Right earlobe")
    logger.info("    GND  ->  Left earlobe")
    logger.info("")
    logger.info("  Look at a flickering box to move cursor")
    logger.info("  Look at CENTER to stop")
    logger.info(f"  Speed: {args.speed}px  SNR threshold: {args.snr}")
    logger.info("  ESC to quit")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Filling buffer...")

    # Wait for buffer
    while reader.get_window(ANALYSIS_SAMPLES) is None:
        clock.tick(60)
        screen.fill(BG)
        txt_surf = fonts["big"].render("Filling buffer...", True, TEXT_C)
        screen.blit(txt_surf, txt_surf.get_rect(center=(W//2, H//2)))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or \
               (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                reader.stop()
                return

    logger.info("  Buffer ready! Look at a target to move.\n")

    running = True
    snr_display = {name: 0 for name in TARGETS}

    try:
        while running:
            dt = clock.tick(60) / 1000.0
            frame_count += 1
            current_time = time.time()

            # ── Events ──
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_SPACE:
                        # Manual click
                        pyautogui.click()
                        clicks += 1

            # ── Draw background ──
            screen.fill(BG)

            # Center fixation cross
            cx, cy = W//2, H//2
            pygame.draw.circle(screen, CENTER_COLOR, (cx, cy), 30)
            pygame.draw.line(screen, TEXT_C, (cx-12, cy), (cx+12, cy), 2)
            pygame.draw.line(screen, TEXT_C, (cx, cy-12), (cx, cy+12), 2)

            # ── Draw flickering targets ──
            for name, info in TARGETS.items():
                freq = info["freq"]
                color = info["color"]
                x, y = targets_pos[name]

                # Determine if box is "on" this frame (square wave flickering)
                # period in frames = FPS / freq
                phase = (frame_count * freq / 60.0) % 1.0
                is_on = phase < 0.5

                if is_on:
                    # Bright box
                    pygame.draw.rect(screen, color, (x, y, BOX_W, BOX_H),
                                     border_radius=8)
                    # Label
                    label = fonts["med"].render(name, True, (0, 0, 0))
                    screen.blit(label, label.get_rect(
                        center=(x + BOX_W//2, y + BOX_H//2 - 12)))
                    freq_label = fonts["small"].render(f"{freq}Hz", True, (0, 0, 0))
                    screen.blit(freq_label, freq_label.get_rect(
                        center=(x + BOX_W//2, y + BOX_H//2 + 15)))
                else:
                    # Dim box
                    dim = tuple(max(20, c//6) for c in color)
                    pygame.draw.rect(screen, dim, (x, y, BOX_W, BOX_H),
                                     border_radius=8)
                    pygame.draw.rect(screen, (40, 40, 40), (x, y, BOX_W, BOX_H),
                                     width=2, border_radius=8)

                # SNR indicator bar
                snr_val = snr_display.get(name, 0)
                bar_w = min(int(snr_val * 15), BOX_W)
                bar_y = y + BOX_H + 5
                pygame.draw.rect(screen, (30, 30, 40), (x, bar_y, BOX_W, 8),
                                 border_radius=4)
                if bar_w > 0:
                    bar_color = (0, 255, 0) if snr_val >= SNR_THRESHOLD else (100, 100, 120)
                    pygame.draw.rect(screen, bar_color, (x, bar_y, bar_w, 8),
                                     border_radius=4)

            # Highlight detected direction
            if detected_dir and detected_dir in targets_pos:
                dx, dy = targets_pos[detected_dir]
                pygame.draw.rect(screen, ACTIVE_C,
                                 (dx-3, dy-3, BOX_W+6, BOX_H+6),
                                 width=3, border_radius=10)

            # ── Status bar ──
            status_y = H - 35
            status = fonts["info"].render(
                f"Detected: {detected_dir or 'NONE'}  |  "
                f"Moves: {moves}  |  Clicks: {clicks}  |  "
                f"Mode: {'ACTIVE' if detected_dir else 'IDLE'}",
                True, TEXT_C
            )
            screen.blit(status, (20, status_y))

            # Instructions
            inst = fonts["info"].render(
                "Look at target = move  |  SPACE = click  |  ESC = quit",
                True, (80, 80, 100)
            )
            screen.blit(inst, inst.get_rect(center=(W//2, 30)))

            pygame.display.flip()

            # ── SSVEP Analysis ──
            if current_time - last_analysis >= STEP_SEC:
                last_analysis = current_time

                eeg = reader.get_window(ANALYSIS_SAMPLES)
                if eeg is not None:
                    target_freqs = [t["freq"] for t in TARGETS.values()]
                    direction, confidence, snr_vals = detect_ssvep(eeg, target_freqs)

                    snr_display = snr_vals
                    detected_dir = direction

                    if direction:
                        # Move cursor
                        px = args.speed
                        dx, dy = 0, 0
                        if direction == "LEFT":
                            dx = -px
                        elif direction == "RIGHT":
                            dx = px
                        elif direction == "UP":
                            dy = -px
                        elif direction == "DOWN":
                            dy = px

                        pyautogui.moveRel(dx, dy, duration=0.02)
                        moves += 1

                        if moves % 5 == 1:
                            logger.info(
                                f"  [{moves:4d}] {direction:5s} "
                                f"(SNR={confidence:.1f}) "
                                f"({dx:+d},{dy:+d})"
                            )

    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
        reader.stop()
        logger.info(f"\nStopped. Moves: {moves}  Clicks: {clicks}")


if __name__ == "__main__":
    main()
