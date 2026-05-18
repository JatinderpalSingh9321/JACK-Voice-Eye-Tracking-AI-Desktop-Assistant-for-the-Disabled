"""Quick test: what does Vosk actually hear from your mic?"""
import vosk
import json
import pyaudio
import time

MODEL_PATH = r"D:\8th sem\bio\data\vosk-model-small-en-us-0.15"
model = vosk.Model(MODEL_PATH)
rec = vosk.KaldiRecognizer(model, 16000)

pa = pyaudio.PyAudio()
stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    frames_per_buffer=4000,
)

print("=" * 50)
print("  VOSK MIC TEST — Speak anything!")
print("  Say 'wake up brains' or anything else.")
print("  Running for 15 seconds...")
print("=" * 50)

start = time.time()
while time.time() - start < 15:
    data = stream.read(4000, exception_on_overflow=False)
    if rec.AcceptWaveform(data):
        result = json.loads(rec.Result())
        text = result.get("text", "")
        if text:
            print(f"  HEARD: [{text}]")
    else:
        partial = json.loads(rec.PartialResult())
        p = partial.get("partial", "")
        if p:
            print(f"  partial: [{p}]", end="\r")

final = json.loads(rec.FinalResult())
if final.get("text"):
    print(f"  FINAL: [{final['text']}]")

stream.stop_stream()
stream.close()
pa.terminate()
print("\nDone!")
