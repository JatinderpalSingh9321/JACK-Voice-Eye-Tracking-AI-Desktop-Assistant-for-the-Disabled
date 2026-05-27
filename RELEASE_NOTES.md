# NavTools v1.0.0 — First Public Release 🎉

**NavTools** is a completely hands-free assistive control suite for Windows, combining webcam-based eye gaze tracking and an offline voice assistant (Jim) — no extra hardware required.

---

## 🚀 What's Included

- 👁️ **Gaze Tracker** — MediaPipe Face Mesh cursor control with blink/wink clicking
- 🎙️ **Jim Voice Assistant** — 120+ voice commands (browser, apps, files, YouTube Music, system)
- 🔮 **Floating Orb UI** — Transparent, frameless PyQt5 animated orb with drag support
- 🎛️ **Control Center Dashboard** — Tkinter dark-mode settings panel (Voice, Gaze, General tabs)
- 🗣️ **Kokoro ONNX TTS** — High-quality offline voice output with Windows SAPI5 fallback

---

## 📦 How to Install

1. Download **`NavTools-v1.0.0-Windows.zip`** below
2. Extract the zip to any folder
3. Double-click **`NavTools\NavTools.exe`**
4. Allow webcam and microphone access when prompted
5. The glowing **Orb** will appear in the top-right corner of your screen

> ⚠️ **Windows SmartScreen** may show a warning on first launch — click **"More info" → "Run anyway"**. This is expected for unsigned executables.

---

## 🎮 Quick Controls

| Action | Effect |
|--------|--------|
| Double-click the Orb | Open Settings Dashboard |
| Right-click the Orb | Exit the application |
| Say **"hey Jim"** | Wake the voice assistant |
| Say **"wake up Jim"** | Alternative wake phrase |
| Say **"close the assistant"** | Graceful shutdown |

---

## 🔧 System Requirements

- **OS:** Windows 10 / 11 (64-bit)
- **RAM:** 4 GB minimum, 8 GB recommended
- **Webcam:** Any USB or built-in webcam
- **Microphone:** Any USB or built-in microphone
- **Internet:** Required for Google Speech Recognition (voice commands)
- **No Python installation required**

---

## 📋 What's New in v1.0.0

- Initial public release
- PyQt5/QWebEngineView fully transparent floating Orb
- General Settings tab: voice profile, speaking speed, microphone sensitivity
- YouTube Music dedicated voice controls (play, next, mute, like, shuffle)
- Positional link/file clicking ("click first result", "open second file")
- Gaze tracker voice controls ("start eye tracking", "stop eye tracking")
- Kokoro ONNX TTS bundled (Zira and Sarah voice profiles)
- One-click installer (`install.bat`) and launcher (`run.bat`)

---

## 📁 Bundle Contents

```
NavTools-v1.0.0-Windows.zip
├── NavTools/
│   ├── NavTools.exe          ← Launch this
│   └── _internal/            ← All dependencies (do not delete)
├── HOW_TO_RUN.txt
├── README.md
└── README.pdf
```

---

*Group No. 7 — 8th Semester Major Project, 2026*
