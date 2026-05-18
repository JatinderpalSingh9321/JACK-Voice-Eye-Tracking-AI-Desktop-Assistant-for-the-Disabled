"""
Diagnostic Test Script for Gaze Tracking and Camera Attention Model
===================================================================
Runs the gaze tracker in a daemon thread and prints live attention & gaze
coordinates to the console, showing when you look away or close your eyes.

Usage:
  python test_gaze_attention.py --preview
"""

import argparse
import sys
import time
from src.gaze_tracker import GazeTracker
from src.attention_state import attention
from src.utils import setup_logger

logger = setup_logger("test_gaze_attention")

def main():
    parser = argparse.ArgumentParser(description="Test Gaze and Attention Model")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--preview", action="store_true", help="Show webcam video preview")
    args = parser.parse_args()

    print("=" * 65)
    print("  GAZE TRACKER & ATTENTION MODEL LIVE TEST")
    print("=" * 65)
    print("  Instructions:")
    print("  1. Look directly at the screen -> Should show ATTENTIVE")
    print("  2. Look away or turn your head -> Should show LOOKING AWAY")
    print("  3. Close your eyes -> Should show LOOKING AWAY (low Eye Aspect Ratio)")
    print("  4. Press Ctrl+C in this terminal to stop.")
    print("=" * 65)
    print("Initializing MediaPipe and Camera. Please wait...\n")

    # Disable moving cursor during testing so it doesn't hijack the user's mouse!
    # Let's monkeypatch GazeTracker._update_cursor to print coordinates but not call pyautogui.moveTo
    original_update = GazeTracker._update_cursor
    def mock_update_cursor(self, gx, gy):
        alpha = self.smoothing
        self._sx = self._sx * alpha + gx * (1 - alpha)
        self._sy = self._sy * alpha + gy * (1 - alpha)
        attention.set_gaze(self._sx, self._sy)
        # We do NOT call pyautogui.moveTo(px, py) so the user can use their system normally during test!

    GazeTracker._update_cursor = mock_update_cursor

    # Initialize and start the tracker thread
    tracker = GazeTracker(camera_id=args.camera, smoothing=0.15, show_preview=args.preview)
    tracker.start()

    # Wait for the thread to launch and capture its first frames
    time.sleep(2.0)

    if not tracker.is_alive():
        print("[-] Error: GazeTracker thread failed to start. Check webcam availability.")
        sys.exit(1)

    print("[+] GazeTracker running successfully. Starting live console display...\n")

    last_attentive_state = None
    try:
        while tracker.is_alive():
            is_att = attention.is_attentive
            sx, sy = attention.get_gaze_screen()
            
            # Print only on change, or periodically
            state_str = "🟢 ATTENTIVE" if is_att else "🔴 LOOKING AWAY / EYE CLOSED"
            
            # Get raw normalized gaze to print precise changes
            with attention._state_lock:
                gx, gy = attention._gaze_x, attention._gaze_y
                
            sys.stdout.write(f"\rState: {state_str:30s} | Gaze Screen: ({sx:4d}, {sy:4d}) | Normalised Gaze: ({gx:.3f}, {gy:.3f})")
            sys.stdout.flush()
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nStopping GazeTracker thread...")
    finally:
        tracker.stop()
        # Wait a moment for thread cleanup
        time.sleep(1.0)
        print("[+] Test completed.")

if __name__ == "__main__":
    main()
