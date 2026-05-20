import cv2
import sys

print("Testing cv2.CAP_DSHOW...", flush=True)
try:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if cap.isOpened():
        print("CAP_DSHOW: SUCCESS", flush=True)
        ret, frame = cap.read()
        print(f"CAP_DSHOW frame shape: {frame.shape if ret else 'Failed'}", flush=True)
        cap.release()
    else:
        print("CAP_DSHOW: FAILED TO OPEN", flush=True)
except Exception as e:
    print(f"CAP_DSHOW: Exception {e}", flush=True)

print("Testing default backend...", flush=True)
try:
    cap2 = cv2.VideoCapture(0)
    if cap2.isOpened():
        print("Default: SUCCESS", flush=True)
        ret, frame = cap2.read()
        print(f"Default frame shape: {frame.shape if ret else 'Failed'}", flush=True)
        cap2.release()
    else:
        print("Default: FAILED TO OPEN", flush=True)
except Exception as e:
    print(f"Default: Exception {e}", flush=True)
