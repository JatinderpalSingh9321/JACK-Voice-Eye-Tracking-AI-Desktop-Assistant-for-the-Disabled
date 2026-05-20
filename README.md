<p align="center">
  <h1 align="center">👁️ NavTools: Assistive Gaze Tracking & Voice Assistant</h1>
  <p align="center">
    <strong>A Hands-Free Neural-Interface-Like Assistive System using MediaPipe Gaze Tracking and Offline Voice Command Orchestration</strong>
  </p>
  <p align="center">
    Group No. 7 &nbsp;·&nbsp; 8th Semester Major Project &nbsp;·&nbsp; 2026
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/MediaPipe-Camera-00C7B7?style=flat-square" alt="MediaPipe">
  <img src="https://img.shields.io/badge/Tkinter-UI-blue?style=flat-square" alt="Tkinter">
  <img src="https://img.shields.io/badge/Speech--Recognition-Offline%20TTS-green?style=flat-square" alt="Speech">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
</p>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Core Modules](#-core-modules)
  - [Gaze Tracking and Clicking Gestures](#1-camera-based-gaze-tracking)
  - [Jim Interactive Voice Assistant](#2-jim-interactive-voice-assistant)
- [Software Setup](#-software-setup)
- [How to Run](#-how-to-run)
  - [Multimodal Launcher](#method-1-standalone-multimodal-console-launcher)
  - [Tkinter Settings Dashboard](#method-2-tkinter-settings-dashboard)
- [Unified State Management](#-unified-state-management)
- [Voice Assistant Reference Guide](#-voice-assistant-reference-guide)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 🔬 Overview

**NavTools** is a completely non-invasive, premium assistive control suite that empowers individuals with physical impairments to operate computers hands-free. The system merges **webcam-based eye gaze tracking** with an **offline voice-activated assistant (Jim)**. 

Unlike legacy biosignal-based interfaces (like EEG/EOG), NavTools requires **zero extra hardware**. It leverages standard computer webcams and microphones to deliver smooth cursor movement, rich facial-gesture-based clicking, and highly responsive voice command execution.

### Key Highlights

| Feature | Details |
|---------|---------|
| 👁️ **Gaze Control** | MediaPipe Face Mesh landmark tracking for cursor positioning |
| ⚡ **Gestures** | Blink and Wink gesture recognition for clicks (Left, Right, Double) |
| 🎙️ **Voice Command** | 80+ pre-configured offline/online speech macros (Jim Assistant) |
| 🎛️ **Configuration** | Unified Tkinter dark-mode settings panel for calibration |
| 🧠 **Attention Gating** | Thread-safe inter-module synchronization via shared state |
| 🗣️ **TTS System** | High-fidelity Kokoro ONNX voice generation with local SAPI5 fallback |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INPUT LAYERS (NO EXTRA HARDWARE)             │
│                                                                 │
│       ┌───────────────┐                  ┌─────────────────┐    │
│       │ Standard Mic  │                  │ Standard Webcam │    │
│       └───────┬───────┘                  └────────┬────────┘    │
│               │ Speech Audio                      │ Video Frames │
├───────────────┼───────────────────────────────────┼─────────────┤
│               ▼                                   ▼             │
│   ┌───────────────────────┐           ┌─────────────────────┐   │
│   │  Speech Recognition   │           │ MediaPipe Landmark  │   │
│   │  & Command Processing │           │  & Gesture Engine   │   │
│   └───────────┬───────────┘           └───────────┬─────────┘   │
│               │ Command Signal                    │ (X, Y) Coordinates
│               │                                   │ + EAR Blinks
├───────────────┼───────────────────────────────────┼─────────────┤
│               ▼                                   ▼             │
│    ┌────────────────────────────────────────────────────────┐   │
│    │        Thread-Safe State Synchronization (Attention)   │   │
│    │  - Attentive Eye State Gate   - Shared Volume/Cursor   │   │
│    └───────────────────────────┬────────────────────────────┘   │
│                                │                                │
│                                ▼                                │
├─────────────────────────────────────────────────────────────────┤
│                    OUTPUT INTERFACES & CONTROL                  │
│                                                                 │
│     ┌───────────────────┐             ┌─────────────────────┐   │
│     │   Kokoro ONNX /   │             │   PyAutoGUI OS      │   │
│     │   SAPI5 Speech    │             │   System Controls   │   │
│     └───────────────────┘             └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔌 Core Modules

### 1. Camera-Based Gaze Tracking

The **Gaze Tracker** acts as a virtual mouse by tracking the user's face and eyes using MediaPipe's High-Fidelity Landmark Model (`face_landmarker.task`). 

* **Exponential Moving Average (EMA) Smoothing:** Eliminates natural micro-saccades and camera jitter to provide a smooth, organic cursor movement.
* **Eye Aspect Ratio (EAR) Clicking:** Detects natural blinks and winks for full mouse emulation:
  * 😉 **Left Eye Wink:** Executes a **Left Mouse Click**.
  * 😉 **Right Eye Wink:** Executes a **Right Mouse Click**.
  * 👁️ **Double Blink:** Executes a **Double-Click**.
  * ⏱️ **Extended Hold Blink:** Triggers mouse **Click & Drag**.

### 2. Jim Interactive Voice Assistant

**Jim** is an offline-first interactive digital companion that processes vocal commands. It features:
* **Holographic Voice Orb Visualizer:** Provides real-time feedback with color-coded states (Aqua for listening, Cyan for thinking, Green for speaking, Red for sleeping).
* **Smart Calculation Parser:** Extracts dynamic spoken expressions (e.g., *"calculate fifteen times three plus four"*) and executes them safely, focusing existing calculator instances if open.
* **Smart Web & Local Search:** Supports targeted phrases (e.g., *"search Google for python guides"*, *"find file design_specifications"*, *"type hello world"*).
* ** Kokoro TTS engine:** Integrates lightweight ONNX models to produce crystal-clear human-like speech output offline.

---

## 💻 Software Setup

### Prerequisites

* **OS:** Windows (preferred for direct pywin32 API system hooks).
* **Python:** 3.9 through 3.11.
* **Webcam & Microphone:** Any standard built-in or external USB devices.

### Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/JatinderpalSingh9321/bci-assistive-control.git
   cd bci-assistive-control
   ```

2. **Set Up Virtual Environment:**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install Refactored Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 How to Run

NavTools offers two entry methods depending on your workflow:

### Method 1: Standalone Multimodal Console Launcher
Runs both the Eye Gaze Tracker and Voice Assistant as independent threads with console logs.

```bash
# Basic start (Gaze + Voice)
python -m src.multimodal_launcher

# Start with a real-time webcam preview panel for camera calibration
python -m src.multimodal_launcher --preview

# Disable specific modules
python -m src.multimodal_launcher --no-gaze
```

### Method 2: Tkinter Settings Dashboard
Launches a gorgeous, dark-themed GUI control panel. It allows configuring gaze EMA smoothing, choosing camera index inputs, toggling debug live previews, and managing Voice Assistant states.

```bash
python -m src.gui_app
```

---

## 🧠 Unified State Management

To prevent cursor drift or voice triggers when the user is not actively looking at the screen, NavTools implements a thread-safe singleton state class, `AttentionState`. 

If **Attention Gating** is enabled in the settings dashboard:
1. **Attentive Calibration:** The eye gaze tracker checks if the user's pupils are focused on the monitor.
2. **Signal Gating:** If the user looks away, `attention.is_attentive` is set to `False`.
3. **Trigger Lockout:** The Voice Assistant pauses microphone streaming and cursor positioning freezes, preventing accidental command triggers.
4. **Resumption:** Simply looking back at the screen immediately resumes cursor control and wake-word listening.

---

## 🎙️ Voice Assistant Reference Guide

Jim listens for the wake phrase **"wake up Jim"** or **"hey Jim"**. Once activated, you can speak any of the following pre-configured command classes:

### Browser & Tab Navigation
* *"open google"* / *"open youtube"* — Launches default web browsers to specified addresses.
* *"new tab"* / *"close tab"* — Manages browser workspace tags.
* *"next tab"* / *"previous tab"* — Cycles through active tabs.
* *"go back"* / *"go forward"* / *"refresh page"* — Standard page controls.

### Local Application Launchers
* *"open calculator"* / *"open notepad"* / *"open control panel"* / *"open task manager"* / *"open terminal"* / *"open sticky notes"* — Instantly spawns built-in utilities.
* *"open download folder"* / *"open documents"* / *"open my computer"* — Launches explorer paths.
* *"open VS Code"* / *"open discord"* / *"open spotify"* / *"open photoshop"* — Launches third-party software dynamically from start menu indexing.

### Windows & System Controls
* *"minimize window"* / *"maximize window"* / *"snap left"* / *"snap right"* — Organizes screen windows.
* *"scroll down"* / *"scroll up"* / *"page up"* / *"page down"* — Smooth scroll simulation.
* *"take screenshot"* — Opens Snipping Tool.
* *"lock screen"* — Instantly locks the Windows user session.
* *"volume up"* / *"volume down"* / *"mute"* — Controls audio devices.

### Smart Dynamic Handlers
* *"calculate [expression]"* — Solves equations vocally.
* *"google search for [query]"* — Spawns browser with search results.
* *"find file [filename]"* — Opens File Explorer with a structured query.
* *"type [text]"* — Types text directly into the active cursor field.
* *"close the assistant"* / *"exit application"* — Triggers an application-wide graceful exit.

---

## 🔧 Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| **Jittery cursor** | Low room lighting or low camera frame rate | Increase ambient lighting; reduce gaze `--smoothing` value to `0.9` in the settings GUI. |
| **Blinks not clicking** | Face landmark model file is missing | Ensure `data/face_landmarker.task` is downloaded and placed in the `/data` folder. |
| **Voice command lag** | High ambient microphone noise | Move to a quieter area or check microphone input gain levels. |
| **Kokoro TTS unavailable** | kokoro_onnx is not installed or model weights are missing | The system will automatically fall back to native Windows SAPI5 synthesizer, keeping voice functional. |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<p align="center">
  <strong>Assistive Technology made elegant, lightweight, and accessible to everyone. 👁️🎙️</strong>
</p>
<p align="center">
  <em>Group 7 — 8th Semester Major Project, 2026</em>
</p>
