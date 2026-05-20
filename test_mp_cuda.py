import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import sys
sys.modules['sounddevice'] = None

print("Starting import...", flush=True)
import mediapipe as mp
print("SUCCESS!", flush=True)
