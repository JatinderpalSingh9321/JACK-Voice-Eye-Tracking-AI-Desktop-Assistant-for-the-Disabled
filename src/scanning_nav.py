"""
NavTools — EOG-Based Assistive Navigation System
==================================================
Complete scanning navigation UI with EOG blink/wink detection,
local decision engine, and OS-level app launching.

Electrode Setup (Fp1 referential):
  IN+  ->  Fp1 (left forehead, above left eyebrow)
  IN-  ->  Left earlobe
  GND  ->  Right earlobe

Controls:
  Single blink   -> Select highlighted item (opens the app)
  Double blink   -> Go back / cancel
  Wink right     -> Move highlight to next item
  Wink left      -> Move highlight to previous item

Keyboard Fallback:
  B -> Simulate blink     | D -> Simulate double blink
  W -> Simulate wink right| Q -> Simulate wink left
  ESC -> Quit

Usage:
  python -m src.scanning_nav --port COM7
  python -m src.scanning_nav --simulate   (keyboard only, no hardware)

Group No. 7 | 8th Semester Major Project
"""

import argparse
import subprocess
import time
import threading
import os
import sys
from collections import deque

import numpy as np
import pygame

from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, setup_logger
from src.local_decision import decide_action
from scipy import signal as sig

logger = setup_logger("scanning_nav")

FS = SAMPLING_RATE
BUF_SIZE = 5000


# ──────────────────────────────────────────────
# NAVIGATION ITEMS
# ──────────────────────────────────────────────
NAV_ITEMS = [
    {
        "id": "browser",
        "label": "Open Browser",
        "icon": "globe",
        "color": (41, 128, 185),
        "command": ["cmd", "/c", "start", "https://www.google.com"],
    },
    {
        "id": "folder",
        "label": "Open Folder",
        "icon": "folder",
        "color": (243, 156, 18),
        "command": ["explorer", os.path.expanduser("~\\Documents")],
    },
    {
        "id": "camera",
        "label": "Open Camera",
        "icon": "camera",
        "color": (231, 76, 60),
        "command": ["cmd", "/c", "start", "microsoft.windows.camera:"],
    },
    {
        "id": "notepad",
        "label": "Open Notepad",
        "icon": "notepad",
        "color": (46, 204, 113),
        "command": ["notepad"],
    },
    {
        "id": "calculator",
        "label": "Open Calculator",
        "icon": "calc",
        "color": (155, 89, 182),
        "command": ["calc"],
    },
    {
        "id": "settings",
        "label": "Open Settings",
        "icon": "settings",
        "color": (52, 73, 94),
        "command": ["cmd", "/c", "start", "ms-settings:"],
    },
]


# ──────────────────────────────────────────────
# ICON DRAWING
# ──────────────────────────────────────────────
def draw_icon(surface, icon_type, x, y, size, color):
    """Draw simple geometric icons."""
    cx, cy = x + size // 2, y + size // 2
    r = size // 3

    if icon_type == "globe":
        pygame.draw.circle(surface, color, (cx, cy), r, 3)
        pygame.draw.ellipse(surface, color, (cx - r//2, cy - r, r, r*2), 2)
        pygame.draw.line(surface, color, (cx - r, cy), (cx + r, cy), 2)

    elif icon_type == "folder":
        pygame.draw.rect(surface, color,
                         (cx - r, cy - r//2, r*2, r + r//2), border_radius=3)
        pygame.draw.rect(surface, color,
                         (cx - r, cy - r//2 - 6, r, 8), border_radius=2)

    elif icon_type == "camera":
        pygame.draw.rect(surface, color,
                         (cx - r, cy - r//2, r*2, r), border_radius=4)
        pygame.draw.circle(surface, color, (cx, cy), r//3, 2)
        pygame.draw.rect(surface, color, (cx + r//3, cy - r//2 - 5, r//2, 6))

    elif icon_type == "notepad":
        pygame.draw.rect(surface, color,
                         (cx - r//2, cy - r, r, r*2), border_radius=2)
        for i in range(4):
            ly = cy - r//2 + i * 7
            pygame.draw.line(surface, color,
                             (cx - r//2 + 4, ly), (cx + r//2 - 4, ly), 1)

    elif icon_type == "calc":
        pygame.draw.rect(surface, color,
                         (cx - r//2, cy - r, r, r*2), border_radius=3)
        # Buttons grid
        for row in range(3):
            for col in range(3):
                bx = cx - r//2 + 4 + col * (r//3)
                by = cy - r//3 + row * (r//3)
                pygame.draw.rect(surface, color, (bx, by, r//4, r//4), border_radius=1)

    elif icon_type == "settings":
        pygame.draw.circle(surface, color, (cx, cy), r, 3)
        pygame.draw.circle(surface, color, (cx, cy), r//3)
        for angle in range(0, 360, 45):
            rad = np.radians(angle)
            sx = int(cx + (r + 4) * np.cos(rad))
            sy = int(cy + (r + 4) * np.sin(rad))
            pygame.draw.circle(surface, color, (sx, sy), 3)


# ──────────────────────────────────────────────
# SERIAL READER (EOG)
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

    def get_recent(self, n):
        with self._lock:
            if len(self.buf) < n:
                return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)


# ──────────────────────────────────────────────
# EOG SIGNAL DETECTOR
# ──────────────────────────────────────────────
class EOGDetector:
    """
    Detects blink, double_blink, wink_left, wink_right from Fp1 EOG signal.
    Uses amplitude threshold + pattern timing.
    """

    def __init__(self, fs=FS):
        self.fs = fs
        self.baseline_rms = None
        self.threshold = None

        # Blink state machine
        self.blink_times = []
        self.in_spike = False
        self.spike_start = 0
        self.spike_peak = 0
        self.spike_positive = True

        # Cooldowns
        self.last_action_time = 0
        self.action_cooldown = 1.5

        # Wink detection
        self.positive_peak = 0
        self.negative_peak = 0

    def calibrate(self, resting_data):
        """Set detection thresholds from resting signal."""
        centered = resting_data - np.mean(resting_data)
        self.baseline_rms = np.sqrt(np.mean(centered**2))
        self.threshold = self.baseline_rms * 3.0
        logger.info(f"  EOG calibrated: baseline={self.baseline_rms:.1f}, "
                     f"threshold={self.threshold:.1f}")

    def detect(self, recent_samples) -> str:
        """
        Analyze recent signal for EOG events.
        Returns: 'blink', 'double_blink', 'wink_left', 'wink_right', or ''
        """
        if self.threshold is None or len(recent_samples) < 50:
            return ""

        now = time.time()
        if now - self.last_action_time < self.action_cooldown:
            return ""

        # Center the signal
        x = recent_samples - np.mean(recent_samples)

        # Look at last ~100ms
        check_n = max(int(0.1 * self.fs), 10)
        window = x[-check_n:]

        pos_peak = np.max(window)
        neg_peak = np.min(window)
        abs_peak = max(abs(pos_peak), abs(neg_peak))

        # Spike detection (rising edge)
        if abs_peak > self.threshold and not self.in_spike:
            self.in_spike = True
            self.spike_start = now
            self.spike_positive = pos_peak > abs(neg_peak)
            self.positive_peak = pos_peak
            self.negative_peak = neg_peak

        # Track peak during spike
        if self.in_spike:
            self.positive_peak = max(self.positive_peak, pos_peak)
            self.negative_peak = min(self.negative_peak, neg_peak)

        # Spike end (signal drops below threshold)
        if self.in_spike and abs_peak < self.threshold * 0.4:
            self.in_spike = False
            spike_duration = now - self.spike_start

            if 0.05 < spike_duration < 0.8:  # Valid blink duration
                # Check asymmetry for wink detection
                pos_mag = abs(self.positive_peak)
                neg_mag = abs(self.negative_peak)
                total_mag = pos_mag + neg_mag + 1e-10
                asymmetry = (pos_mag - neg_mag) / total_mag

                self.blink_times.append({
                    "time": now,
                    "asymmetry": asymmetry,
                    "duration": spike_duration,
                    "pos": pos_mag,
                    "neg": neg_mag,
                })

            self.positive_peak = 0
            self.negative_peak = 0

        # Remove old blinks
        self.blink_times = [
            b for b in self.blink_times if now - b["time"] < 1.5
        ]

        # Check for completed patterns (wait 0.7s after last spike)
        if len(self.blink_times) > 0:
            time_since_last = now - self.blink_times[-1]["time"]
            if time_since_last > 0.7:
                result = self._classify_pattern()
                self.blink_times.clear()
                if result:
                    self.last_action_time = now
                    return result

        return ""

    def _classify_pattern(self) -> str:
        """Classify the accumulated blink pattern."""
        n = len(self.blink_times)

        if n == 0:
            return ""

        if n >= 2:
            # Check timing between blinks
            gap = self.blink_times[1]["time"] - self.blink_times[0]["time"]
            if gap < 0.6:
                return "double_blink"

        if n == 1:
            b = self.blink_times[0]
            asym = b["asymmetry"]

            # Strong asymmetry = wink
            if asym > 0.3:
                return "wink_right"
            elif asym < -0.3:
                return "wink_left"
            else:
                return "blink"

        return "blink"


# ──────────────────────────────────────────────
# OS EXECUTION
# ──────────────────────────────────────────────
def execute_action(action: str, nav_items: list) -> str:
    """Execute the action returned by local_decision."""
    if action == "no_action":
        return ""

    if action == "go_back":
        logger.info("  [ACTION] Go Back")
        return "back"

    if action == "move_next":
        return "next"

    if action == "move_previous":
        return "previous"

    # open_<item>
    if action.startswith("open_"):
        item_id = action[5:]
        for item in nav_items:
            if item["id"] == item_id:
                logger.info(f"  [ACTION] Opening: {item['label']}")
                try:
                    subprocess.Popen(
                        item["command"],
                        shell=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return "opened"
                except Exception as e:
                    logger.error(f"  Failed to open: {e}")
                    return "error"

    return ""


# ──────────────────────────────────────────────
# MAIN UI
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NavTools - EOG Scanning Navigation")
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--simulate", action="store_true",
                        help="Keyboard-only mode (no hardware)")
    parser.add_argument("--auto-scan", action="store_true",
                        help="Auto-cycle through items (only blink needed)")
    parser.add_argument("--scan-speed", type=float, default=2.5,
                        help="Auto-scan interval in seconds (default: 2.5)")
    args = parser.parse_args()

    # Pygame setup
    pygame.init()
    W, H = 1000, 650
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("NavTools - EOG Assistive Navigation")
    clock = pygame.time.Clock()

    fonts = {
        "title":  pygame.font.SysFont("Segoe UI", 32, bold=True),
        "item":   pygame.font.SysFont("Segoe UI", 22, bold=True),
        "desc":   pygame.font.SysFont("Segoe UI", 16),
        "status": pygame.font.SysFont("Segoe UI", 14),
        "help":   pygame.font.SysFont("Consolas", 13),
        "toast":  pygame.font.SysFont("Segoe UI", 20, bold=True),
    }

    # Colors
    BG = (15, 18, 25)
    CARD_BG = (25, 30, 42)
    CARD_HOVER = (35, 45, 65)
    HIGHLIGHT_BORDER = (0, 200, 255)
    TEXT_PRIMARY = (220, 225, 235)
    TEXT_DIM = (100, 110, 130)
    SUCCESS = (46, 204, 113)
    WARNING = (243, 156, 18)

    # State
    selected_idx = 0
    toast_msg = ""
    toast_color = SUCCESS
    toast_time = 0

    # Serial + EOG detector
    reader = None
    detector = None

    if not args.simulate:
        reader = SerialReader(args.port)
        reader.start()
        detector = EOGDetector()

        logger.info("  Filling buffer...")
        time.sleep(4)

        # Calibrate
        logger.info("\n  CALIBRATING: Keep eyes OPEN, relax for 5 seconds...\n")
        time.sleep(2)
        logger.info("  >>> Measuring NOW...")
        cal_samples = []
        start = time.time()
        while time.time() - start < 5:
            w = reader.get_recent(50)
            if w is not None:
                cal_samples.extend(w[-10:])
            time.sleep(0.1)

        if cal_samples:
            detector.calibrate(np.array(cal_samples, dtype=np.float64))
        else:
            logger.warning("  No calibration data! Using defaults.")
            detector.baseline_rms = 100
            detector.threshold = 300

    # Auto-scan timer
    last_scan_time = time.time()

    logger.info("\n" + "=" * 60)
    logger.info("  NAVTOOLS - EOG Assistive Navigation")
    logger.info("=" * 60)
    if args.simulate:
        logger.info("  MODE: Keyboard simulation (no hardware)")
    else:
        logger.info("  MODE: Live EOG detection")
    logger.info(f"  Auto-scan: {'ON' if args.auto_scan else 'OFF'}")
    logger.info("")
    logger.info("  Keyboard fallback: B=blink, D=double, W=wink_R, Q=wink_L")
    logger.info("  ESC = quit")
    logger.info("=" * 60 + "\n")

    running = True
    signal_detected = ""
    action_count = 0

    while running:
        dt = clock.tick(30) / 1000.0
        now = time.time()

        # ── Events ──
        signal_detected = ""
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                # Keyboard fallback
                elif ev.key == pygame.K_b:
                    signal_detected = "blink"
                elif ev.key == pygame.K_d:
                    signal_detected = "double_blink"
                elif ev.key == pygame.K_w:
                    signal_detected = "wink_right"
                elif ev.key == pygame.K_q:
                    signal_detected = "wink_left"

        # ── EOG detection ──
        if detector and reader and not signal_detected:
            recent = reader.get_recent(300)
            if recent is not None:
                eog_signal = detector.detect(recent)
                if eog_signal:
                    signal_detected = eog_signal
                    logger.info(f"  [EOG] Detected: {eog_signal}")

        # ── Auto-scan ──
        if args.auto_scan and now - last_scan_time >= args.scan_speed:
            selected_idx = (selected_idx + 1) % len(NAV_ITEMS)
            last_scan_time = now

        # ── Process signal ──
        if signal_detected:
            current_item = NAV_ITEMS[selected_idx]
            action = decide_action(signal_detected, current_item["id"])
            result = execute_action(action, NAV_ITEMS)

            if result == "next":
                selected_idx = (selected_idx + 1) % len(NAV_ITEMS)
                last_scan_time = now
                toast_msg = ">> NEXT"
                toast_color = HIGHLIGHT_BORDER
                toast_time = now
                logger.info(f"  [NAV] Next -> {NAV_ITEMS[selected_idx]['label']}")

            elif result == "previous":
                selected_idx = (selected_idx - 1) % len(NAV_ITEMS)
                last_scan_time = now
                toast_msg = "<< PREVIOUS"
                toast_color = HIGHLIGHT_BORDER
                toast_time = now
                logger.info(f"  [NAV] Previous -> {NAV_ITEMS[selected_idx]['label']}")

            elif result == "opened":
                action_count += 1
                toast_msg = f"OPENED: {current_item['label']}"
                toast_color = SUCCESS
                toast_time = now
                logger.info(f"  [OPENED] {current_item['label']} (#{action_count})")

            elif result == "back":
                toast_msg = "BACK"
                toast_color = WARNING
                toast_time = now

            elif result == "error":
                toast_msg = "ERROR: Could not open"
                toast_color = (231, 76, 60)
                toast_time = now

        # ── Draw ──
        screen.fill(BG)

        # Title bar
        title = fonts["title"].render("NavTools", True, TEXT_PRIMARY)
        screen.blit(title, (30, 20))
        subtitle = fonts["desc"].render(
            "EOG-Based Assistive Navigation  |  "
            f"{'SIMULATE' if args.simulate else 'LIVE'}  |  "
            f"{'Auto-Scan ON' if args.auto_scan else 'Manual'}",
            True, TEXT_DIM
        )
        screen.blit(subtitle, (30, 58))

        # Divider
        pygame.draw.line(screen, (40, 50, 70), (30, 85), (W - 30, 85), 2)

        # Item cards (2 rows x 3 cols)
        card_w, card_h = 280, 200
        pad_x, pad_y = 30, 20
        start_x = (W - (card_w * 3 + pad_x * 2)) // 2
        start_y = 110

        for i, item in enumerate(NAV_ITEMS):
            col = i % 3
            row = i // 3
            cx = start_x + col * (card_w + pad_x)
            cy = start_y + row * (card_h + pad_y)

            is_selected = (i == selected_idx)

            # Card background
            bg = CARD_HOVER if is_selected else CARD_BG
            pygame.draw.rect(screen, bg,
                             (cx, cy, card_w, card_h), border_radius=12)

            # Highlight border
            if is_selected:
                pygame.draw.rect(screen, HIGHLIGHT_BORDER,
                                 (cx - 2, cy - 2, card_w + 4, card_h + 4),
                                 width=3, border_radius=14)
                # Glow effect
                glow_surf = pygame.Surface((card_w + 20, card_h + 20), pygame.SRCALPHA)
                pygame.draw.rect(glow_surf, (*HIGHLIGHT_BORDER, 30),
                                 (0, 0, card_w + 20, card_h + 20),
                                 border_radius=16)
                screen.blit(glow_surf, (cx - 10, cy - 10))

            # Icon
            icon_color = item["color"] if is_selected else tuple(
                min(255, c + 30) for c in item["color"]
            )
            draw_icon(screen, item["icon"], cx + 20, cy + 20, 60, icon_color)

            # Label
            label_color = TEXT_PRIMARY if is_selected else TEXT_DIM
            label = fonts["item"].render(item["label"], True, label_color)
            screen.blit(label, (cx + 90, cy + 35))

            # Index badge
            idx_text = fonts["status"].render(str(i + 1), True,
                                               HIGHLIGHT_BORDER if is_selected else TEXT_DIM)
            pygame.draw.circle(screen, (40, 50, 70) if not is_selected else (30, 40, 60),
                               (cx + card_w - 25, cy + 25), 14)
            screen.blit(idx_text, idx_text.get_rect(
                center=(cx + card_w - 25, cy + 25)))

            # Description
            if is_selected:
                desc = fonts["desc"].render(">> Press BLINK to open <<", True, HIGHLIGHT_BORDER)
                screen.blit(desc, desc.get_rect(center=(cx + card_w//2, cy + card_h - 30)))

        # Toast notification
        if toast_msg and now - toast_time < 2.0:
            alpha = max(0, min(255, int(255 * (1 - (now - toast_time) / 2.0))))
            toast_surf = fonts["toast"].render(toast_msg, True, toast_color)
            toast_rect = toast_surf.get_rect(center=(W//2, H - 100))
            # Background
            bg_rect = toast_rect.inflate(30, 15)
            bg_s = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(bg_s, (20, 25, 35, alpha),
                             (0, 0, bg_rect.width, bg_rect.height),
                             border_radius=8)
            screen.blit(bg_s, bg_rect.topleft)
            screen.blit(toast_surf, toast_rect)

        # Help bar at bottom
        help_texts = [
            "B = Blink(Select)",
            "D = Double(Back)",
            "W = Wink R(Next)",
            "Q = Wink L(Prev)",
            "ESC = Quit",
        ]
        help_y = H - 35
        pygame.draw.rect(screen, (20, 25, 35), (0, help_y - 8, W, 43))
        total_w = sum(fonts["help"].size(t)[0] for t in help_texts) + 40 * (len(help_texts) - 1)
        hx = (W - total_w) // 2
        for ht in help_texts:
            help_surf = fonts["help"].render(ht, True, TEXT_DIM)
            screen.blit(help_surf, (hx, help_y))
            hx += help_surf.get_width() + 40

        # Signal indicator (top right)
        if signal_detected:
            sig_text = fonts["status"].render(f"Signal: {signal_detected}", True, SUCCESS)
            screen.blit(sig_text, (W - 200, 25))

        pygame.display.flip()

    # Cleanup
    pygame.quit()
    if reader:
        reader.stop()
    logger.info(f"\nNavTools stopped. Total actions: {action_count}")


if __name__ == "__main__":
    main()
