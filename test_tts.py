"""Test: does pyttsx3 work at all in a thread?"""
import pyttsx3
import threading
import time

def speak_test():
    print("Thread: creating engine...")
    engine = pyttsx3.init()
    engine.setProperty('rate', 170)
    print("Thread: speaking...")
    engine.say("Hello, I am Brains assistant. Testing one two three.")
    engine.runAndWait()
    print("Thread: done speaking!")
    engine.stop()
    print("Thread: engine stopped")

print("Main: starting speech thread...")
t = threading.Thread(target=speak_test, daemon=True)
t.start()

# Wait for it
t.join(timeout=15)
if t.is_alive():
    print("HANG DETECTED: pyttsx3 runAndWait() is stuck in thread!")
    print("This is a known Windows bug with pyttsx3 in daemon threads.")
else:
    print("Main: thread completed normally")
