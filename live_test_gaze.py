import cv2
import time
import numpy as np
from src.gaze_tracker import GazeTracker, L_IRIS_CENTER, R_IRIS_CENTER, L_EYE_OUTER, L_EYE_INNER

class LiveTester(GazeTracker):
    def __init__(self):
        super().__init__(camera_id=0, smoothing=0.15, show_preview=True)
        self.logs = []
        self.start_time = time.time()
        
    def _update_cursor(self, gx, gy):
        # We override this to just log data instead of moving mouse!
        if len(self.logs) < 100: # capture 100 frames
            self.logs.append((gx, gy))

    def _draw_debug(self, frame, lm, is_attentive):
        h, w, _ = frame.shape
        # Put text on screen for user
        cv2.putText(frame, "PLEASE LOOK AT THE CENTER OF YOUR SCREEN", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        gx = (lm[L_IRIS_CENTER].x + lm[R_IRIS_CENTER].x) / 2.0
        gy = (lm[L_IRIS_CENTER].y + lm[R_IRIS_CENTER].y) / 2.0
        
        cv2.putText(frame, f"Raw GX: {gx:.4f} GY: {gy:.4f}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        # Original debug drawing
        super()._draw_debug(frame, lm, True)

if __name__ == "__main__":
    print("Starting Live Gaze Tester...")
    tester = LiveTester()
    tester.start()
    
    print("Recording data for 10 seconds...")
    time.sleep(10)
    tester.stop()
    
    with open("gaze_logs.txt", "w") as f:
        for x, y in tester.logs:
            f.write(f"{x},{y}\n")
    print("Logs saved to gaze_logs.txt")
