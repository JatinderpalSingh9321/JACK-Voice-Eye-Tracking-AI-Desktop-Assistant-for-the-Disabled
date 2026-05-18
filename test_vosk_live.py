"""Live diagnostic: shows audio amplitude + what Vosk hears in real-time."""
import vosk
import json
import pyaudio
import struct
import time
import sys

MODEL_PATH = r"D:\8th sem\bio\data\vosk-model-small-en-in-0.4"

print("Loading Vosk model...")
model = vosk.Model(MODEL_PATH)
rec = vosk.KaldiRecognizer(model, 16000)
rec.SetWords(True)

pa = pyaudio.PyAudio()

# Show default device
default = pa.get_default_input_device_info()
print(f"Using mic: [{default['index']}] {default['name']}")
print(f"Native rate: {default['defaultSampleRate']}")

stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=4000,
)

print("")
print("=" * 55)
print("  LIVE VOSK TEST - Speak now! (20 seconds)")
print("  Say: 'wake up brains' or 'hello' or 'open browser'")
print("=" * 55)
print("")

start = time.time()
heard_anything = False

while time.time() - start < 20:
    data = stream.read(4000, exception_on_overflow=False)
    
    # Show amplitude
    samples = struct.unpack(f'{len(data)//2}h', data)
    amp = max(abs(s) for s in samples)
    bar = "#" * min(int(amp / 300), 40)
    
    is_final = rec.AcceptWaveform(data)
    
    if is_final:
        result = json.loads(rec.Result())
        text = result.get("text", "")
        if text:
            heard_anything = True
            print(f"\n  >>> FINAL: \"{text}\"")
            print(f"      (amp={amp})")
        else:
            # Empty final = silence detected
            sys.stdout.write(f"  amp={amp:5d} |{bar:<40s}| [silence]    \r")
    else:
        partial = json.loads(rec.PartialResult())
        p = partial.get("partial", "")
        if p:
            heard_anything = True
            sys.stdout.write(f"  amp={amp:5d} |{bar:<40s}| partial: \"{p}\"          \r")
        else:
            sys.stdout.write(f"  amp={amp:5d} |{bar:<40s}|                          \r")
    
    sys.stdout.flush()

# Get any remaining
final = json.loads(rec.FinalResult())
if final.get("text"):
    print(f"\n  >>> LEFTOVER: \"{final['text']}\"")

stream.stop_stream()
stream.close()
pa.terminate()

print("\n")
if not heard_anything:
    print("  !! VOSK HEARD NOTHING !!")
    print("  Possible causes:")
    print("  1. Mic is muted in Windows Sound Settings")
    print("  2. Wrong mic selected (check Sound > Input)")
    print("  3. Mic volume too low")
    print("  4. Speaking too far from mic")
else:
    print("  Vosk heard speech successfully!")
print("")
