"""
NavTools EOG Controller — Dual Mode (NavTools UI + OS Mouse Clicks)
====================================================================
Supports two modes:
  --mode navtools   → Send commands to NavTools UI via HTTP (original)
  --mode mouse      → Simulate native OS mouse clicks at gaze position

In 'mouse' mode, the gaze tracker must be running to provide attention
gating and cursor position.

Controls (mouse mode):
  SHORT BLINK  (80–599ms)   → Left Click
  LONG BLINK   (hold >600ms)→ Right Click
  DOUBLE BLINK (2× quick)   → Double Click

Controls (navtools mode — unchanged):
  SHORT BLINK  (80–599ms)   → Move Right →
  LONG BLINK   (hold >600ms)→ Move Left  ←
  DOUBLE BLINK (2× quick)   → Select & Open App

Usage:
  python -m src.navtools_eog_control --port COM7 --mode mouse
  python -m src.navtools_eog_control --port COM7 --mode navtools --debug

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import threading
import sys
import urllib.request
import urllib.error
from collections import deque

import numpy as np

from src.utils import BAUD_RATE, SAMPLING_RATE, setup_logger
from src.attention_state import attention

logger = setup_logger("navtools_eog")

BUF_SIZE      = 5000
CONTROL_PORT  = 7891   # Must match main.js


# ──────────────────────────────────────────────
# ACTION CONTROLLERS
# ──────────────────────────────────────────────

class NavToolsController:
    """Sends actions to NavTools via HTTP localhost server."""

    ACTION_MAP = {
        "MOVE_RIGHT": "right",
        "MOVE_LEFT":  "left",
        "SELECT":     "select",
    }

    def send(self, action: str):
        endpoint = self.ACTION_MAP.get(action)
        if not endpoint:
            return
        url = f"http://localhost:{CONTROL_PORT}/{endpoint}"
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                pass
            logger.info(f"  ▶ {action}")
        except urllib.error.URLError:
            logger.warning(
                f"  ⚠ Could not reach NavTools on port {CONTROL_PORT}. "
                "Is NavTools running?"
            )


class MouseController:
    """Simulates native Windows OS mouse clicks at the current cursor position."""

    def send(self, action: str):
        import pyautogui
        pyautogui.FAILSAFE = False

        if action == "LEFT_CLICK":
            pyautogui.click()
            logger.info("  🖱 LEFT CLICK")
        elif action == "RIGHT_CLICK":
            pyautogui.rightClick()
            logger.info("  🖱 RIGHT CLICK")
        elif action == "DOUBLE_CLICK":
            pyautogui.doubleClick()
            logger.info("  🖱 DOUBLE CLICK")


# ──────────────────────────────────────────────
# SERIAL READER
# ──────────────────────────────────────────────

class SerialReader(threading.Thread):
    def __init__(self, port, baud=BAUD_RATE):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.buf  = deque(maxlen=BUF_SIZE)
        self._running = False
        self._lock    = threading.Lock()

    def run(self):
        import serial as s
        self._running = True
        try:
            ser = s.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            for _ in range(20):
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line and not line.startswith("#"):
                    break
            logger.info(f"✓ Connected to Arduino on {self.port}")
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

    def get_recent(self, n):
        with self._lock:
            if len(self.buf) < n:
                return None
            return np.array(list(self.buf)[-n:], dtype=np.float64)


# ──────────────────────────────────────────────
# MAIN CONTROLLER
# ──────────────────────────────────────────────

def run(port, sensitivity=2.5, debug=False, mode="navtools",
        require_attention=False):
    """
    Main EOG processing loop.

    Parameters
    ----------
    mode : str
        'navtools' = send HTTP commands to Electron app
        'mouse'    = simulate OS mouse clicks at gaze position
    require_attention : bool
        If True, ignore blinks when user isn't looking at screen.
    """
    if mode == "mouse":
        ctrl = MouseController()
        # Action mapping for mouse mode
        SHORT_ACTION  = "LEFT_CLICK"
        LONG_ACTION   = "RIGHT_CLICK"
        DOUBLE_ACTION = "DOUBLE_CLICK"
    else:
        ctrl = NavToolsController()
        SHORT_ACTION  = "MOVE_RIGHT"
        LONG_ACTION   = "MOVE_LEFT"
        DOUBLE_ACTION = "SELECT"

    reader = SerialReader(port)
    reader.start()

    logger.info("  Buffering signal (3s) — keep eyes OPEN and relaxed...")
    time.sleep(3)

    cal = reader.get_recent(500)
    if cal is None:
        logger.error("No data from Arduino — check connection.")
        return

    baseline  = float(np.mean(cal))
    noise_std = float(np.std(cal))

    BLINK_THRESH   = noise_std * sensitivity
    LONG_BLINK_MS  = 600
    DOUBLE_WIN_S   = 0.8
    COOLDOWN_S     = 1.2
    MIN_BLINK_MS   = 80
    REFRACTORY_S   = 0.30
    BASELINE_ALPHA = 0.003

    logger.info(f"  Baseline: {baseline:.1f} | Noise: {noise_std:.1f}")
    logger.info(f"  Blink threshold: >{BLINK_THRESH:.1f}")
    logger.info("")
    logger.info("=" * 57)
    logger.info(f"  NavTools EOG Controller — {mode.upper()} MODE")
    logger.info("=" * 57)

    if mode == "mouse":
        logger.info("  👁  SHORT BLINK  (80–599ms)     → Left Click")
        logger.info("  👁  LONG BLINK   (hold >600ms)  → Right Click")
        logger.info("  👁👁 DOUBLE BLINK (2× quick)    → Double Click")
        if require_attention:
            logger.info("  🔒 Attention gating: ON (needs gaze tracker)")
    else:
        logger.info("  👁  SHORT BLINK  (80–599ms)     → Move Right →")
        logger.info("  👁  LONG BLINK   (hold >600ms)  → Move Left  ←")
        logger.info("  👁👁 DOUBLE BLINK (2× quick)    → Select & Open App")

    logger.info("")
    logger.info("  Ctrl+C to stop.")
    logger.info("=" * 57)
    logger.info("")

    in_blink          = False
    blink_start_time  = 0.0
    last_blink_end    = 0.0
    last_blink_dur_ms = 0.0
    pending_single    = False
    last_action_time  = 0.0
    action_count      = 0
    in_refractory     = False

    try:
        while True:
            time.sleep(0.02)  # 50 Hz

            raw = reader.get_recent(5)
            if raw is None:
                continue

            sample   = float(np.median(raw))
            centered = sample - baseline
            peak_abs = abs(centered)
            now      = time.time()

            # Adaptive baseline — only update when quiet
            if not in_blink and not in_refractory and peak_abs < BLINK_THRESH * 0.5:
                baseline = baseline * (1 - BASELINE_ALPHA) + sample * BASELINE_ALPHA

            # Refractory period guard
            if in_refractory:
                if (now - last_blink_end) >= REFRACTORY_S:
                    in_refractory = False
                else:
                    continue

            # ── STATE MACHINE ──────────────────────────────────
            if not in_blink:
                if peak_abs >= BLINK_THRESH:
                    # Attention gate check
                    if require_attention and not attention.is_attentive:
                        if debug:
                            logger.info("  🔒 Blink ignored (not attentive)")
                        continue

                    in_blink = True
                    blink_start_time = now
                    if debug:
                        logger.info(f"  ▲ START  amp={centered:+.1f}  base={baseline:.1f}")

                elif pending_single and (now - last_blink_end) > DOUBLE_WIN_S:
                    # Timeout — no second blink came → fire SHORT action
                    pending_single = False
                    if now - last_action_time >= COOLDOWN_S:
                        action_count += 1
                        last_action_time = now
                        logger.info(
                            f"  [{action_count:03d}] {SHORT_ACTION}  "
                            f"(single {last_blink_dur_ms:.0f}ms)"
                        )
                        ctrl.send(SHORT_ACTION)

            else:
                blink_elapsed_ms = (now - blink_start_time) * 1000

                # ── LONG BLINK: fire AS SOON AS threshold crossed ──
                if blink_elapsed_ms >= LONG_BLINK_MS:
                    if now - last_action_time >= COOLDOWN_S:
                        action_count += 1
                        last_action_time = now
                        pending_single   = False
                        logger.info(
                            f"  [{action_count:03d}] {LONG_ACTION}   "
                            f"(hold {blink_elapsed_ms:.0f}ms)"
                        )
                        ctrl.send(LONG_ACTION)
                    # Reset state
                    in_blink      = False
                    last_blink_end = now
                    in_refractory  = True

                # ── SHORT BLINK: wait for eyes to open ──
                elif peak_abs < BLINK_THRESH * 0.5:
                    blink_dur_ms   = blink_elapsed_ms
                    in_blink       = False
                    last_blink_end = now
                    in_refractory  = True

                    if debug:
                        logger.info(f"  ▼ END    dur={blink_dur_ms:.0f}ms")

                    if blink_dur_ms < MIN_BLINK_MS:
                        if debug:
                            logger.info(f"  ✗ ARTIFACT ({blink_dur_ms:.0f}ms) — ignored")
                        continue

                    last_blink_dur_ms = blink_dur_ms

                    # SHORT BLINK — check for double
                    gap = now - last_blink_end
                    if pending_single and gap <= DOUBLE_WIN_S:
                        pending_single = False
                        if now - last_action_time >= COOLDOWN_S:
                            action_count += 1
                            last_action_time = now
                            logger.info(
                                f"  [{action_count:03d}] {DOUBLE_ACTION}  (double blink)"
                            )
                            ctrl.send(DOUBLE_ACTION)
                    else:
                        pending_single = True
                        last_blink_end = now

    except KeyboardInterrupt:
        logger.info(f"\n✓ Stopped. Total actions: {action_count}")
    finally:
        reader.stop()


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NavTools EOG Controller — Dual Mode"
    )
    parser.add_argument("--port",        default="COM7",
                        help="Arduino COM port (default: COM7)")
    parser.add_argument("--sensitivity", type=float, default=2.5,
                        help="Blink threshold multiplier (default: 2.5)")
    parser.add_argument("--mode",        choices=["navtools", "mouse"],
                        default="navtools",
                        help="Control mode: 'navtools' or 'mouse' (default: navtools)")
    parser.add_argument("--attention",   action="store_true",
                        help="Enable attention gating (requires gaze tracker)")
    parser.add_argument("--debug",       action="store_true",
                        help="Show blink onset/offset timing")
    args = parser.parse_args()
    run(
        port=args.port,
        sensitivity=args.sensitivity,
        debug=args.debug,
        mode=args.mode,
        require_attention=args.attention,
    )


if __name__ == "__main__":
    main()
