"""
NavTools Multimodal Launcher
=============================
Starts the two main assistive modules in one process:
  1. Gaze Tracker — moves the Windows cursor with camera eye tracking
  2. Voice Assistant — offline interactive voice commands (Jim)

Usage:
  python -m src.multimodal_launcher
  python -m src.multimodal_launcher --preview
  python -m src.multimodal_launcher --no-voice
  python -m src.multimodal_launcher --no-gaze

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import sys

from src.utils import setup_logger

logger = setup_logger("multimodal")


def main():
    parser = argparse.ArgumentParser(
        description="NavTools Multimodal Launcher — Gaze + Voice"
    )
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index for gaze tracker (default: 0)")
    parser.add_argument("--smoothing", type=float, default=0.85,
                        help="Gaze EMA smoothing (default: 0.85)")
    parser.add_argument("--preview", action="store_true",
                        help="Show gaze tracker debug preview")
    parser.add_argument("--wake-word", default=None,
                        help="Voice assistant wake word (default: none)")
    parser.add_argument("--no-voice", action="store_true",
                        help="Disable voice assistant")
    parser.add_argument("--no-gaze", action="store_true",
                        help="Disable gaze tracker")
    args = parser.parse_args()

    threads = []

    logger.info("")
    logger.info("=" * 60)
    logger.info("  NavTools Multimodal System — Starting Up")
    logger.info("=" * 60)
    logger.info("")

    # ── 1. GAZE TRACKER ──────────────────────────
    gaze_tracker = None
    if not args.no_gaze:
        try:
            from src.gaze_tracker import GazeTracker
            gaze_tracker = GazeTracker(
                camera_id=args.camera,
                smoothing=args.smoothing,
                show_preview=args.preview,
            )
            gaze_tracker.start()
            threads.append(gaze_tracker)
            logger.info("  ✅ Gaze Tracker     — STARTED")
        except Exception as e:
            logger.warning(f"  ⚠ Gaze Tracker failed to start: {e}")
            logger.warning("  → Continuing without gaze tracking")
    else:
        logger.info("  ⏭ Gaze Tracker     — DISABLED")

    # Give the camera a moment to initialise
    if gaze_tracker:
        time.sleep(1.5)

    # ── 2. VOICE ASSISTANT ────────────────────────
    voice_assistant = None
    if not args.no_voice:
        try:
            from src.voice_assistant import VoiceAssistant
            voice_assistant = VoiceAssistant(
                require_attention=not args.no_gaze,
            )
            voice_assistant.start()
            threads.append(voice_assistant)
            logger.info("  ✅ Voice Assistant  — STARTED")
        except Exception as e:
            logger.warning(f"  ⚠ Voice Assistant failed to start: {e}")
            logger.warning("  → Continuing without voice control")
    else:
        logger.info("  ⏭ Voice Assistant  — DISABLED")

    logger.info("")
    logger.info("=" * 60)
    logger.info("  All modules launched. Press Ctrl+C to stop all.")
    logger.info("=" * 60)
    logger.info("")

    # ── Keep alive ────────────────────────────────
    try:
        while True:
            # Check if any critical thread has died
            alive = [t for t in threads if t.is_alive()]
            if not alive:
                logger.warning("All modules have stopped.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n✓ Shutting down all modules...")

        if gaze_tracker:
            gaze_tracker.stop()
        if voice_assistant:
            voice_assistant.stop()

        # Give threads a moment to clean up
        time.sleep(1)
        logger.info("✓ All modules stopped. Goodbye!")


if __name__ == "__main__":
    main()
