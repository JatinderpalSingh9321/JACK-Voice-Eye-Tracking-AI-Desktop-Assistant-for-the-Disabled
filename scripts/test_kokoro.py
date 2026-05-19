import os
import sys

# Ensure correct module paths
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.voice_assistant import speak
    print("Testing SAPI5 / Kokoro integration...")
    speak("Hello! I am Jim, your new high-quality AI voice assistant. How can I help you today?")
    print("Test complete.")
except Exception as e:
    print(f"Error: {e}")
