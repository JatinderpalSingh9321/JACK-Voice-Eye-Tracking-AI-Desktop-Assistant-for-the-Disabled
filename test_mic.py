"""List all audio input devices and test the default one."""
import pyaudio
import struct
import time

pa = pyaudio.PyAudio()

print("=" * 60)
print("  AUDIO INPUT DEVICES")
print("=" * 60)

default_input = pa.get_default_input_device_info()
print(f"\n  Default input device: [{default_input['index']}] {default_input['name']}")
print(f"  Max input channels: {default_input['maxInputChannels']}")
print(f"  Default sample rate: {default_input['defaultSampleRate']}")
print()

for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        marker = " <<<" if i == default_input['index'] else ""
        print(f"  [{i}] {info['name']} (channels: {info['maxInputChannels']}, rate: {info['defaultSampleRate']}){marker}")

print()
print("=" * 60)
print(f"  TESTING default device [{default_input['index']}] for 5 seconds...")
print("  Speak now! You should see amplitude bars.")
print("=" * 60)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=16000,
    input=True,
    input_device_index=default_input['index'],
    frames_per_buffer=1024,
)

start = time.time()
max_amp = 0
while time.time() - start < 5:
    data = stream.read(1024, exception_on_overflow=False)
    samples = struct.unpack(f'{len(data)//2}h', data)
    amp = max(abs(s) for s in samples)
    max_amp = max(max_amp, amp)
    bar = "#" * min(int(amp / 500), 50)
    print(f"  amp={amp:5d} |{bar}", end="\r")

stream.stop_stream()
stream.close()
pa.terminate()

print()
print(f"\n  Max amplitude seen: {max_amp}")
if max_amp < 100:
    print("  ⚠ VERY LOW — mic may be muted or wrong device!")
elif max_amp < 1000:
    print("  ⚠ LOW — try speaking louder or moving closer")
else:
    print("  ✓ Good signal level!")
