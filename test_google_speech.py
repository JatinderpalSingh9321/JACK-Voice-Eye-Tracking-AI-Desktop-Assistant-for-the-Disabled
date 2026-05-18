"""Test with FIXED low energy threshold + shows what's heard in real-time."""
import speech_recognition as sr
import sys

recognizer = sr.Recognizer()

# DON'T use auto-adjust — force a low threshold so speech always triggers
recognizer.energy_threshold = 400
recognizer.dynamic_energy_threshold = False  # Don't auto-adjust
recognizer.pause_threshold = 0.8

print("=" * 55)
print("  SPEECH TEST (fixed threshold=400)")
print("  Speak clearly into your mic. 5 rounds.")
print("  Say: 'wake up brains' or 'hello' or 'open calculator'")
print("=" * 55)

for round_num in range(1, 6):
    print(f"\n--- Round {round_num}: Speak now! ---")
    try:
        with sr.Microphone() as source:
            print("  Listening... (speak within 5 seconds)")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
            audio_bytes = len(audio.get_raw_data())
            print(f"  Got audio ({audio_bytes} bytes, {audio_bytes/32000:.1f}s)")
        
        # Send to Google with Indian English
        print("  Recognizing...", end=" ", flush=True)
        text = recognizer.recognize_google(audio, language="en-IN")
        print(f"HEARD: \"{text}\"")
        
    except sr.WaitTimeoutError:
        print("  (timeout - no speech detected)")
    except sr.UnknownValueError:
        print("  (could not understand - try speaking louder/closer)")
    except sr.RequestError as e:
        print(f"  (API error: {e})")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")

print("\nDone!")
