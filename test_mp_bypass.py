import sys
# Prevent sounddevice from loading and hanging the system!
sys.modules['sounddevice'] = None

try:
    import mediapipe as mp
    print("Mediapipe imported successfully without sounddevice!")
except Exception as e:
    print(f"Exception during mediapipe import: {e}")
