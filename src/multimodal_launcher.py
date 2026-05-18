"""
NavTools Multimodal Launcher
=============================
Starts all three modules in one process:
  1. Gaze Tracker — moves the Windows cursor with eye tracking
  2. EOG Controller — blink-to-click at gaze position
  3. Voice Assistant — offline interactive voice commands

Usage:
  python -m src.multimodal_launcher --port COM7
  python -m src.multimodal_launcher --port COM7 --preview
  python -m src.multimodal_launcher --port COM7 --no-voice
  python -m src.multimodal_launcher --port COM7 --no-gaze

Group No. 7 | 8th Semester Major Project
"""

import argparse
import time
import sys

from src.utils import setup_logger

logger = setup_logger("multimodal")


def main():
    parser = argparse.ArgumentParser(
        description="NavTools Multimodal Launcher — Gaze + EOG + Voice"
    )
    parser.add_argument("--port", default="COM7",
                        help="Arduino COM port (default: COM7)")
    parser.add_argument("--sensitivity", type=float, default=2.5,
                        help="EOG blink threshold multiplier (default: 2.5)")
    parser.add_argument("--mode", choices=["navtools", "mouse"],
                        default="mouse",
                        help="EOG mode: 'navtools' or 'mouse' (default: mouse)")
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
    parser.add_argument("--no-eog", action="store_true",
                        help="Disable EOG controller")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging for all modules")
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
                wake_word=args.wake_word,
                require_attention=not args.no_gaze,
                port=args.port,
            )
            voice_assistant.start()
            threads.append(voice_assistant)
            logger.info("  ✅ Voice Assistant  — STARTED")
        except Exception as e:
            logger.warning(f"  ⚠ Voice Assistant failed to start: {e}")
            logger.warning("  → Continuing without voice control")
    else:
        logger.info("  ⏭ Voice Assistant  — DISABLED")

    # ── 3. EOG CONTROLLER ─────────────────────────
    eog_thread = None
    if not args.no_eog:
        try:
            from src.navtools_eog_control import run as eog_run
            import threading

            use_attention = not args.no_gaze

            def _eog_worker():
                eog_run(
                    port=args.port,
                    sensitivity=args.sensitivity,
                    debug=args.debug,
                    mode=args.mode,
                    require_attention=use_attention,
                )

            eog_thread = threading.Thread(
                target=_eog_worker, daemon=True, name="EOGController"
            )
            eog_thread.start()
            threads.append(eog_thread)
            logger.info("  ✅ EOG Controller   — STARTED")
        except Exception as e:
            logger.warning(f"  ⚠ EOG Controller failed to start: {e}")
            logger.warning("  → Continuing without EOG control")
    else:
        logger.info("  ⏭ EOG Controller   — DISABLED")

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
        # EOG thread exits on its own since it's daemon

        # Give threads a moment to clean up
        time.sleep(1)
        logger.info("✓ All modules stopped. Goodbye!")


if __name__ == "__main__":
    main()
