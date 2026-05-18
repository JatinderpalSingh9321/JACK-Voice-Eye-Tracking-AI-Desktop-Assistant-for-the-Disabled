"""
BCI Assistive Control — 3-Class Motor Imagery Data Collection
==============================================================
Collects LEFT, RIGHT, and BOTH-hands motor imagery data from
bipolar C3-C4 electrode placement.

  LEFT  — imagine squeezing LEFT fist
  RIGHT — imagine squeezing RIGHT fist
  BOTH  — imagine squeezing BOTH fists together

Electrode Setup (1 BioAmp EXG Pill):
  IN+  → C3 (left motor cortex)
  IN-  → C4 (right motor cortex)
  GND  → Right earlobe

Usage:
  python -m src.experiment_brain3 --subject 1 --port COM7
  python -m src.experiment_brain3 --subject 1 --port COM7 --trials 80
  python -m src.experiment_brain3 --subject 1 --session 2 --port COM7

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import json
from pathlib import Path

import numpy as np

try:
    import pygame
except ImportError:
    pygame = None

try:
    import serial
except ImportError:
    serial = None

from src.utils import SERIAL_PORT, BAUD_RATE, SAMPLING_RATE, RAW_DATA_DIR, setup_logger

logger = setup_logger("exp_brain3")

# ──────────────────────────────────────────────
# 3-CLASS DEFINITIONS
# ──────────────────────────────────────────────

CLASSES = {
    0: {"name": "LEFT",  "task": "Squeeze LEFT Fist",
        "tip": "Imagine clenching your LEFT hand tightly",
        "arrow": "←", "color": (0, 200, 255)},
    1: {"name": "RIGHT", "task": "Squeeze RIGHT Fist",
        "tip": "Imagine clenching your RIGHT hand tightly",
        "arrow": "→", "color": (255, 166, 0)},
    2: {"name": "BOTH",  "task": "Squeeze BOTH Fists",
        "tip": "Imagine clenching BOTH hands together",
        "arrow": "⬟", "color": (180, 100, 255)},
}

# Trial timing
READY_SEC   = 2.0
CUE_SEC     = 1.0
IMAGINE_SEC = 4.0
REST_SEC    = 2.0

# Display
W, H = 1200, 700
BG       = (15, 15, 25)
TEXT_C   = (210, 210, 220)
REST_C   = (60, 60, 80)
READY_C  = (180, 180, 190)
GO_C     = (100, 255, 100)
BAR_C    = (0, 180, 255)


# ──────────────────────────────────────────────
# DISPLAY HELPERS
# ──────────────────────────────────────────────

def txt(screen, font, text, color, x, y):
    surf = font.render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(x, y)))


def draw_arrow(screen, cid, cx, cy, size=90, color=(255, 255, 255)):
    s = size
    if cid == 0:     # LEFT
        pts = [(cx+s, cy-s//2), (cx-s, cy), (cx+s, cy+s//2)]
    elif cid == 1:   # RIGHT
        pts = [(cx-s, cy-s//2), (cx+s, cy), (cx-s, cy+s//2)]
    elif cid == 2:   # BOTH — draw two arrows pointing inward
        # Left arrow
        pts_l = [(cx-20, cy-s//2), (cx-s-20, cy), (cx-20, cy+s//2)]
        pts_r = [(cx+20, cy-s//2), (cx+s+20, cy), (cx+20, cy+s//2)]
        pygame.draw.polygon(screen, color, pts_l)
        pygame.draw.polygon(screen, (255, 255, 255), pts_l, 3)
        pygame.draw.polygon(screen, color, pts_r)
        pygame.draw.polygon(screen, (255, 255, 255), pts_r, 3)
        return
    else:
        return
    pygame.draw.polygon(screen, color, pts)
    pygame.draw.polygon(screen, (255, 255, 255), pts, 3)


def draw_bar(screen, current, total):
    y = H - 35
    bar_w = W - 100
    x = 50
    frac = current / max(total, 1)
    pygame.draw.rect(screen, (40, 40, 60), (x, y, bar_w, 12), border_radius=6)
    fill = int(bar_w * frac)
    if fill > 0:
        pygame.draw.rect(screen, BAR_C, (x, y, fill, 12), border_radius=6)


# ──────────────────────────────────────────────
# SERIAL
# ──────────────────────────────────────────────

def connect(port):
    logger.info(f"Connecting to {port}...")
    ser = serial.Serial(port, BAUD_RATE, timeout=1)
    time.sleep(2)
    for _ in range(20):
        ser.readline()
    logger.info(f"✓ Connected")
    return ser


def read_sample(ser):
    try:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line and not line.startswith("#"):
            return float(line.split(",")[0])
    except (ValueError, UnicodeDecodeError):
        pass
    return None


# ──────────────────────────────────────────────
# EXPERIMENT
# ──────────────────────────────────────────────

def run(subject_id, session_id=1, port=SERIAL_PORT, trials_total=80):
    if pygame is None:
        logger.error("Install pygame: pip install pygame")
        return

    # Distribute trials across 3 classes as evenly as possible
    per_class = trials_total // 3
    remainder = trials_total % 3
    trial_list = []
    for cid in range(3):
        count = per_class + (1 if cid < remainder else 0)
        trial_list.extend([cid] * count)
    np.random.shuffle(trial_list)
    total = len(trial_list)

    logger.info(f"Subject {subject_id:03d} | Session {session_id} | {total} trials")
    for cid in range(3):
        logger.info(f"  {CLASSES[cid]['name']:6s}: {trial_list.count(cid)} trials")

    # Init
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("🧠 BCI 3-Class Motor Imagery")
    fonts = {
        "title":  pygame.font.SysFont("Segoe UI", 40, bold=True),
        "cue":    pygame.font.SysFont("Segoe UI", 100, bold=True),
        "action": pygame.font.SysFont("Segoe UI", 32),
        "status": pygame.font.SysFont("Segoe UI", 24),
        "tip":    pygame.font.SysFont("Segoe UI", 20, italic=True),
        "info":   pygame.font.SysFont("Consolas", 16),
    }

    # Serial
    ser = None
    try:
        ser = connect(port)
    except Exception as e:
        logger.error(f"Serial failed: {e}")
        pygame.quit()
        return

    # Welcome
    screen.fill(BG)
    txt(screen, fonts["title"], "🧠 3-Class Motor Imagery", (233, 69, 96), W//2, 50)
    txt(screen, fonts["status"],
        f"Subject {subject_id:03d} · Session {session_id} · {total} trials",
        TEXT_C, W//2, 100)

    y = 160
    txt(screen, fonts["status"], "── Electrode Setup ──", BAR_C, W//2, y)
    y += 30
    txt(screen, fonts["info"], "IN+ → C3  |  IN- → C4  |  GND → Earlobe",
        (0, 200, 255), W//2, y)

    y += 50
    txt(screen, fonts["status"], "── Motor Imagery Tasks ──", BAR_C, W//2, y)
    y += 35
    for cid, info in CLASSES.items():
        txt(screen, fonts["info"],
            f"  {info['arrow']}  {info['name']:6s} — {info['task']}",
            info["color"], W//2, y)
        y += 28

    y += 40
    txt(screen, fonts["status"], "Press SPACE to start  ·  ESC to abort",
        READY_C, W//2, y)
    pygame.display.flip()

    # Wait for space
    waiting = True
    while waiting:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or \
               (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                pygame.quit()
                ser.close()
                return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                waiting = False

    # Storage
    all_eeg, all_labels, all_meta = [], [], []
    signal_buf = []

    # Trial loop
    for trial_n, cid in enumerate(trial_list):
        info = CLASSES[cid]
        color = info["color"]

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or \
               (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                _save(subject_id, session_id, all_eeg, all_labels, all_meta)
                pygame.quit()
                ser.close()
                return

        # READY
        screen.fill(BG)
        txt(screen, fonts["cue"], "+", READY_C, W//2, H//2 - 40)
        txt(screen, fonts["status"], f"Trial {trial_n+1}/{total}",
            REST_C, W//2, H//2 + 30)
        draw_bar(screen, trial_n, total)
        pygame.display.flip()
        time.sleep(READY_SEC)

        # CUE
        screen.fill(BG)
        draw_arrow(screen, cid, W//2, H//2 - 40, color=color)
        txt(screen, fonts["action"], info["task"], color, W//2, H//2 + 80)
        txt(screen, fonts["tip"], info["tip"], (150, 150, 170), W//2, H//2 + 120)
        draw_bar(screen, trial_n, total)
        pygame.display.flip()
        time.sleep(CUE_SEC)

        # IMAGINE (record EEG)
        epoch = []
        start = time.time()

        screen.fill(BG)
        draw_arrow(screen, cid, W//2, H//2 - 50, color=color)
        txt(screen, fonts["action"], "IMAGINE NOW", GO_C, W//2, H//2 + 70)
        txt(screen, fonts["tip"], info["tip"], (150, 150, 170), W//2, H//2 + 110)
        draw_bar(screen, trial_n, total)
        pygame.display.flip()

        while time.time() - start < IMAGINE_SEC:
            val = read_sample(ser)
            if val is not None:
                epoch.append(val)
                signal_buf.append(val)
                if len(signal_buf) > 600:
                    signal_buf = signal_buf[-600:]

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or \
                   (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    _save(subject_id, session_id, all_eeg, all_labels, all_meta)
                    pygame.quit()
                    ser.close()
                    return

        # Store
        all_eeg.append(np.array(epoch, dtype=np.float32))
        all_labels.append(cid)
        all_meta.append({
            "trial": trial_n + 1,
            "class_id": cid,
            "class_name": info["name"],
            "n_samples": len(epoch),
            "duration_s": round(time.time() - start, 2),
        })

        logger.info(f"  Trial {trial_n+1:3d}/{total} | {info['name']:6s} | "
                     f"{len(epoch):4d} samples")

        # REST
        screen.fill(BG)
        txt(screen, fonts["status"], "Rest...", REST_C, W//2, H//2)
        draw_bar(screen, trial_n + 1, total)
        pygame.display.flip()
        time.sleep(REST_SEC)

    # Save & Done
    save_path = _save(subject_id, session_id, all_eeg, all_labels, all_meta)

    screen.fill(BG)
    txt(screen, fonts["title"], "✓ Session Complete!", GO_C, W//2, 180)
    txt(screen, fonts["status"],
        f"{total} trials · Subject {subject_id:03d} · Session {session_id}",
        TEXT_C, W//2, 230)
    y = 280
    for cid in range(3):
        count = sum(1 for l in all_labels if l == cid)
        txt(screen, fonts["info"], f"{CLASSES[cid]['name']:6s}: {count} trials",
            CLASSES[cid]["color"], W//2, y)
        y += 25
    txt(screen, fonts["info"], f"Saved: {save_path}", REST_C, W//2, y + 20)
    txt(screen, fonts["status"], "Press any key to exit", READY_C, W//2, y + 60)
    pygame.display.flip()

    waiting = True
    while waiting:
        for ev in pygame.event.get():
            if ev.type in (pygame.QUIT, pygame.KEYDOWN):
                waiting = False

    pygame.quit()
    ser.close()
    logger.info(f"Done: {total} trials saved")


def _save(subject_id, session_id, all_eeg, all_labels, all_meta):
    if not all_eeg:
        return None

    save_dir = RAW_DATA_DIR / f"subject_{subject_id:03d}"
    save_dir.mkdir(parents=True, exist_ok=True)

    data_path = save_dir / f"session_{session_id:02d}_brain3.npz"
    np.savez(data_path,
             data=np.array(all_eeg, dtype=object),
             labels=np.array(all_labels, dtype=np.int32))
    logger.info(f"✓ Data: {data_path}")

    meta = {
        "subject_id": subject_id,
        "session_id": session_id,
        "classes": {str(k): v["name"] for k, v in CLASSES.items()},
        "n_classes": 3,
        "electrode": "bipolar C3-C4 (IN+ C3, IN- C4, GND earlobe)",
        "sampling_rate_hz": SAMPLING_RATE,
        "n_trials": len(all_labels),
        "class_counts": {
            CLASSES[cid]["name"]: sum(1 for l in all_labels if l == cid)
            for cid in range(3)
        },
        "trial_timing": {
            "ready_s": READY_SEC, "cue_s": CUE_SEC,
            "imagine_s": IMAGINE_SEC, "rest_s": REST_SEC,
        },
        "trials": all_meta,
    }
    meta_path = save_dir / f"session_{session_id:02d}_brain3_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, default=str)
    logger.info(f"✓ Meta: {meta_path}")
    return data_path


def main():
    parser = argparse.ArgumentParser(description="3-Class MI Data Collection")
    parser.add_argument("--subject", type=int, required=True)
    parser.add_argument("--session", type=int, default=1)
    parser.add_argument("--port", type=str, default=SERIAL_PORT)
    parser.add_argument("--trials", type=int, default=80,
                        help="Total trials per session (default: 80)")
    args = parser.parse_args()

    run(subject_id=args.subject, session_id=args.session,
        port=args.port, trials_total=args.trials)


if __name__ == "__main__":
    main()
