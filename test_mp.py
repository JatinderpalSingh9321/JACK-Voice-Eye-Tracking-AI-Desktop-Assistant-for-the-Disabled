import sys
print("Importing MediaPipe...", flush=True)
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

print("Loading model...", flush=True)
model_path = r"data\face_landmarker.task"
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=RunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False,
)

print("Creating FaceLandmarker...", flush=True)
try:
    landmarker = FaceLandmarker.create_from_options(options)
    print("SUCCESS", flush=True)
except Exception as e:
    print(f"FAILED: {e}", flush=True)
