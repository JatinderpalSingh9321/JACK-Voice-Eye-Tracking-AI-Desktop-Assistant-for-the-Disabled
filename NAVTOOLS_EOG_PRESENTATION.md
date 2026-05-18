# NavTools: EOG-Based Assistive Navigation
## Project Presentation & Demonstration Guide

This document outlines the final working implementation of the EOG-based assistive navigation system, designed for hands-free computer interaction.

---

### 1. Executive Summary
**NavTools** is a specialized assistive interface that allows users with limited motor function to control a computer using only eye movements. By capturing **Electrooculography (EOG)** signals from the forehead (Fp1 position), the system classifies blinks based on their temporal dynamics (duration and frequency) to navigate a custom application dashboard.

---

### 2. System Architecture (How it Works)

The system is split into three modular layers:
1.  **Hardware Layer**: 
    *   **BioAmp EXG Pill**: A high-precision analog front-end that captures micro-volt level electrical changes from the eyes.
    *   **Arduino R4 Minima**: Digitizes the signal and streams it to the PC at 500Hz.
2.  **Processing Layer (Python Engine)**:
    *   **Adaptive Baseline Tracking**: Automatically adjusts to signal drift and electrode impedance changes.
    *   **Temporal Classification**: Uses physics-based duration analysis instead of unreliable AI models.
    *   **HTTP Control Link**: Sends commands directly to the UI over a local network socket (Port 7891).
3.  **Application Layer (NavTools UI)**:
    *   **Electron-based Interface**: A modern, high-contrast dashboard optimized for assistive use.
    *   **Direct IPC Integration**: Receives Python commands instantly, even if the window is not in focus.

---

### 3. Demonstration Script (Live Walkthrough)

**Step 1: Preparation**
*   Ensure electrodes are placed at **Fp1** (above left eyebrow), **Fp2** (above right eyebrow - optional/reference), and **Earlobe** (Ground).
*   Launch the NavTools UI (`npm start`).
*   Launch the EOG Controller (`python -m src.navtools_eog_control --port COM7`).

**Step 2: Calibration (The "Wow" Factor)**
*   Show the director the "Baseline Tracking" in the terminal.
*   Explain: *"The system takes 3 seconds to learn your unique eye physiology and current noise floor."*

**Step 3: Navigation Demo**
1.  **Single Quick Blink**: Move the selection right through the apps.
    *   *Explain*: *"A short blink (80-500ms) triggers a 'Next' command."*
2.  **Long Hold Blink**: Move the selection back to the left.
    *   *Explain*: *"Holding the eyes shut for >600ms reverses direction. This is more reliable than trying to detect left/right eye look with a single electrode."*
3.  **Double Blink**: Select an app (e.g., Calculator or Browser).
    *   *Explain*: *"Two quick blinks in rapid succession trigger the 'Select' action. Our 'Refractory Window' logic prevents accidental triggers from natural eye fatigue."*

---

### 4. Anticipated Q&A (Director Level)

**Q1: Why use duration (Short/Long) instead of just Left/Right eye winks?**
*   **Answer**: *"Most single-channel hardware (Fp1) produces nearly identical signal polarities for both left and right winks. By using duration, we create a robust, hardware-agnostic control scheme that doesn't require complex multi-channel setups or expensive medical-grade sensors."*

**Q2: How does the system handle 'Noise' (e.g., the user just blinking naturally)?**
*   **Answer**: *"We implemented a 300ms Refractory Window and an 80ms Minimum Artifact Filter. Natural micro-blinks are ignored, and the 'biphasic recovery' of the signal is filtered out so it isn't miscounted as a double-click."*

**Q3: Can this control other Windows applications?**
*   **Answer**: *"Yes. While we developed a custom UI for maximum accessibility, the Python engine can easily be mapped to generic keyboard emulation (Arrow Keys/Enter) to control any standard software."*

**Q4: What is the benefit of the HTTP Control over standard Keyboard simulation?**
*   **Answer**: *"Security and Reliability. Keyboard simulation requires the window to be 'In Focus'. Our HTTP/IPC architecture allows NavTools to receive commands even if it's in the background, making it a true background service."*

---

### 5. Technical Specifications
*   **Sampling Rate**: 500 Hz
*   **Processing Latency**: < 20ms
*   **Communication**: Local HTTP (127.0.0.1:7891)
*   **Gesture Thresholds**: 
    *   Short: 80ms - 599ms
    *   Long: 600ms+
    *   Double: < 800ms gap
