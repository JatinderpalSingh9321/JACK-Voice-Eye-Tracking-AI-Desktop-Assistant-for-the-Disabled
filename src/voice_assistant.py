"""
Jack — Interactive Voice Assistant for NavTools
=================================================
Uses Google Speech Recognition (accurate with Indian accent)
and Windows SAPI5 for speech output.

Flow:
  1. User says "wake up Jack"
  2. Jack responds: "What can I help you with today?"
  3. User speaks their command (e.g., "search for Python tutorials")
  4. Jack executes and confirms vocally
  5. Jack goes back to idle, waiting for "wake up Jack" again

Supports:
  - App launching (browser, calculator, notepad, etc.)
  - Browser search ("search for ...")
  - File Explorer search ("find file ...")
  - Tab navigation (next tab, previous tab, close tab, new tab)
  - Page navigation (go back, go forward, refresh)
  - Scrolling (scroll up/down, page up/down, go to top/bottom)
  - Link clicking ("click link", "open link")
  - Window management (close, minimize, maximize, switch window)
  - System controls (volume, screenshot, lock)

Usage (standalone):
  python -m src.voice_assistant
  python -m src.voice_assistant --no-attention

Group No. 7 | 8th Semester Major Project
"""

import argparse
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# pythoncom and win32com are loaded lazily inside speak() to avoid
# crashing the module if pywin32 is not installed.
import speech_recognition as sr

from src.utils import setup_logger, PROJECT_ROOT, DATA_DIR
from src.attention_state import attention

logger = setup_logger("jack")


# ──────────────────────────────────────────────
# TEXT-TO-SPEECH (Kokoro ONNX & Windows SAPI5)
# ──────────────────────────────────────────────

try:
    import sounddevice as sd
    from kokoro_onnx import Kokoro
    
    kokoro_model_path = os.path.join(PROJECT_ROOT, "models", "kokoro", "kokoro-v1.0.onnx")
    kokoro_voices_path = os.path.join(PROJECT_ROOT, "models", "kokoro", "voices-v1.0.bin")
    
    if os.path.exists(kokoro_model_path) and os.path.exists(kokoro_voices_path):
        _kokoro_tts = Kokoro(kokoro_model_path, kokoro_voices_path)
        logger.info("Kokoro TTS initialized successfully.")
    else:
        _kokoro_tts = None
        logger.warning("Kokoro TTS model files not found. Falling back to SAPI5.")
except ImportError as e:
    _kokoro_tts = None
    logger.warning(f"kokoro_onnx or sounddevice not installed. Falling back to SAPI5. Error details: {e}")
except Exception as e:
    _kokoro_tts = None
    logger.error(f"Error initializing Kokoro TTS: {e}")

_speak_lock = threading.Lock()
_active_assistant = None

def speak(text: str):
    """Speak text using Kokoro TTS (high quality) or fallback to Windows SAPI5."""
    logger.info(f"  [Jack]: \"{text}\"")
    
    global _active_assistant
    if _active_assistant and _active_assistant.state_callback:
        try:
            _active_assistant.state_callback("speaking")
        except Exception:
            pass

    try:
        with _speak_lock:
            # Dynamic settings retrieval
            v_name = attention.voice_name.lower()
            speed_val = attention.voice_speed

            if _kokoro_tts is not None:
                try:
                    # Map standard voices to Kokoro profiles:
                    # - zira -> af_bella (soft female)
                    # - sarah -> af_sarah (natural female)
                    # - michael -> am_michael (natural male)
                    # - david -> am_adam (natural male)
                    kokoro_voice = "af_bella" # default soft female
                    if "sarah" in v_name:
                        kokoro_voice = "af_sarah"
                    elif "michael" in v_name:
                        kokoro_voice = "am_michael"
                    elif "david" in v_name or "male" in v_name:
                        kokoro_voice = "am_adam"
                    elif "female" in v_name:
                        kokoro_voice = "af_bella"

                    samples, sample_rate = _kokoro_tts.create(text, voice=kokoro_voice, speed=speed_val, lang="en-us")
                    sd.play(samples, sample_rate)
                    sd.wait()
                    return
                except Exception as e:
                    logger.error(f"Kokoro TTS generation failed, falling back to SAPI5: {e}")
                    # Fallthrough to SAPI5...

            # Try direct COM first for 0ms start latency fallback
            try:
                import pythoncom
                import win32com.client
                try:
                    pythoncom.CoInitialize()
                except Exception:
                    pass # Already initialized in this thread
                
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                
                # Match SAPI5 voices
                voices = voice.GetVoices()
                selected_voice = None
                
                # Fuzzy match voice name
                for i in range(voices.Count):
                    v_desc = voices.Item(i).GetDescription().lower()
                    if "zira" in v_name or "female" in v_name:
                        if "zira" in v_desc or "female" in v_desc or "hazel" in v_desc:
                            selected_voice = voices.Item(i)
                            break
                    elif "david" in v_name or "male" in v_name:
                        if "david" in v_desc or "male" in v_desc or "adam" in v_desc:
                            selected_voice = voices.Item(i)
                            break

                if selected_voice is None:
                    # Direct match fallback by gender
                    for i in range(voices.Count):
                        v_desc = voices.Item(i).GetDescription().lower()
                        if "zira" in v_name or "female" in v_name:
                            if "female" in v_desc:
                                selected_voice = voices.Item(i)
                                break
                        else:
                            if "male" in v_desc:
                                selected_voice = voices.Item(i)
                                break

                if selected_voice is not None:
                    voice.Voice = selected_voice

                # Map float speed (0.5..2.0) to SAPI5 Rate (-10..10)
                rate_val = max(-10, min(10, int((speed_val - 1.0) * 10)))
                voice.Rate = rate_val
                
                voice.Speak(text)
                return
            except ImportError:
                logger.debug("pywin32 not installed, skipping direct SAPI5 COM speech.")
            except Exception as e:
                logger.debug(f"Direct SAPI5 COM speech failed, falling back to PowerShell: {e}")

            # Fallback to PowerShell subprocess
            safe = text.replace("'", "''")
            # Rate mapping for PowerShell synthesiser:
            # Rate is also integer from -10 to 10
            rate_val = max(-10, min(10, int((speed_val - 1.0) * 10)))
            
            # Decide PowerShell voice snippet based on selected voice
            voice_select_snippet = ""
            if "zira" in v_name or "female" in v_name:
                voice_select_snippet = '$s.SelectVoice(\'Microsoft Zira Desktop\');'
            elif "david" in v_name or "male" in v_name:
                voice_select_snippet = '$s.SelectVoice(\'Microsoft David Desktop\');'

            cmd = (
                f"powershell -Command \""
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"{voice_select_snippet} "
                f"$s.Rate = {rate_val}; "
                f"$s.Speak('{safe}')\""
            )
            try:
                subprocess.run(cmd, shell=True, timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.error(f"  TTS error: {e}")
    finally:
        if _active_assistant and _active_assistant.state_callback:
            try:
                _active_assistant.state_callback(_active_assistant._state)
            except Exception:
                pass


# ──────────────────────────────────────────────
# STATIC COMMAND DEFINITIONS
# ──────────────────────────────────────────────

VOICE_COMMANDS = {
    # ── App Launches — Browsers & Web ──
    "open browser":        ("launch", "start https://www.google.com", "Opening web browser"),
    "open chrome":         ("launch", "start chrome", "Opening Chrome"),
    "open google":         ("launch", "start https://www.google.com", "Opening Google"),
    "open youtube":        ("launch", "start https://www.youtube.com", "Opening YouTube"),
    "open edge":           ("launch", "start msedge", "Opening Microsoft Edge"),
    "open firefox":        ("launch", "start firefox", "Opening Firefox"),

    # ── App Launches — Windows Built-in ──
    "open calculator":     ("launch", "calc", "Opening calculator"),
    "open notepad":        ("launch", "notepad", "Opening notepad"),
    "open windows settings":("launch", "start ms-settings:", "Opening Windows Settings"),
    "open file explorer":  ("launch", "explorer", "Opening file explorer"),
    "open explorer":       ("launch", "explorer", "Opening file explorer"),
    "open my computer":    ("launch", "explorer ::{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "Opening My Computer"),
    "open this pc":        ("launch", "explorer ::{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "Opening This PC"),
    "open recycle bin":    ("launch", "explorer ::{645FF040-5081-101B-9F08-00AA002F954E}", "Opening Recycle Bin"),
    "open control panel":  ("launch", "control", "Opening Control Panel"),
    "open task manager":   ("launch", "taskmgr", "Opening Task Manager"),
    "open camera":         ("launch", "start microsoft.windows.camera:", "Opening camera"),
    "open terminal":       ("launch", "wt", "Opening terminal"),
    "open command prompt": ("launch", "cmd", "Opening Command Prompt"),
    "open powershell":     ("launch", "powershell", "Opening PowerShell"),
    "open paint":          ("launch", "mspaint", "Opening paint"),
    "open snipping tool":  ("launch", "snippingtool", "Opening Snipping Tool"),
    "open clock":          ("launch", "start ms-clock:", "Opening clock"),
    "open alarms":         ("launch", "start ms-clock:", "Opening alarms"),
    "open calendar":       ("launch", "start outlookcal:", "Opening calendar"),
    "open maps":           ("launch", "start bingmaps:", "Opening maps"),
    "open weather":        ("launch", "start bingweather:", "Opening weather"),
    "open store":          ("launch", "start ms-windows-store:", "Opening Microsoft Store"),
    "open microsoft store":("launch", "start ms-windows-store:", "Opening Microsoft Store"),
    "open mail":           ("launch", "start outlookmail:", "Opening mail"),
    "open photos":         ("launch", "start ms-photos:", "Opening Photos"),
    "open music":          ("launch", "start mswindowsmusic:", "Opening music player"),
    "open videos":         ("launch", "start mswindowsvideo:", "Opening video player"),
    "open sticky notes":   ("launch", "start ms-stickynotes:", "Opening Sticky Notes"),
    "open voice recorder": ("launch", "start ms-soundrecorder:", "Opening Voice Recorder"),
    "open recorder":       ("launch", "start ms-soundrecorder:", "Opening Voice Recorder"),
    "open magnifier":      ("launch", "magnify", "Opening Magnifier"),
    "open narrator":       ("launch", "narrator", "Opening Narrator"),
    "open device manager": ("launch", "devmgmt.msc", "Opening Device Manager"),
    "open disk management":("launch", "diskmgmt.msc", "Opening Disk Management"),
    "open system info":    ("launch", "msinfo32", "Opening System Information"),
    "open remote desktop": ("launch", "mstsc", "Opening Remote Desktop"),

    # ── App Launches — Microsoft Office ──
    "open word":           ("launch", "start winword", "Opening Microsoft Word"),
    "open excel":          ("launch", "start excel", "Opening Microsoft Excel"),
    "open powerpoint":     ("launch", "start powerpnt", "Opening PowerPoint"),
    "open outlook":        ("launch", "start outlook", "Opening Outlook"),
    "open teams":          ("launch", "start msteams:", "Opening Microsoft Teams"),
    "open onenote":        ("launch", "start onenote:", "Opening OneNote"),

    # ── App Launches — Third Party (Start Menu search) ──
    "open steam":          ("start_menu", "Steam", "Opening Steam"),
    "open discord":        ("start_menu", "Discord", "Opening Discord"),
    "open spotify":        ("start_menu", "Spotify", "Opening Spotify"),
    "open telegram":       ("start_menu", "Telegram", "Opening Telegram"),
    "open whatsapp":       ("start_menu", "WhatsApp", "Opening WhatsApp"),
    "open zoom":           ("start_menu", "Zoom", "Opening Zoom"),
    "open nvidia":         ("start_menu", "NVIDIA", "Opening NVIDIA App"),
    "open nvidia app":     ("start_menu", "NVIDIA", "Opening NVIDIA App"),
    "open geforce":        ("start_menu", "GeForce", "Opening GeForce Experience"),
    "open obs":            ("start_menu", "OBS", "Opening OBS Studio"),
    "open vlc":            ("start_menu", "VLC", "Opening VLC"),
    "open vs code":        ("start_menu", "Visual Studio Code", "Opening VS Code"),
    "open visual studio":  ("start_menu", "Visual Studio", "Opening Visual Studio"),
    "open photoshop":      ("start_menu", "Photoshop", "Opening Photoshop"),
    "open premiere":       ("start_menu", "Premiere", "Opening Premiere Pro"),
    "open blender":        ("start_menu", "Blender", "Opening Blender"),
    "open unity":          ("start_menu", "Unity", "Opening Unity"),
    "open epic games":     ("start_menu", "Epic Games", "Opening Epic Games"),
    "open brave":          ("start_menu", "Brave", "Opening Brave Browser"),
    "open opera":          ("start_menu", "Opera", "Opening Opera"),

    # ── App Launches — Folders ──
    "open downloads":        ("open_custom_folder", "downloads", "Opening downloads folder"),
    "open downloads folder":  ("open_custom_folder", "downloads", "Opening downloads folder"),
    "open documents":        ("open_custom_folder", "documents", "Opening documents folder"),
    "open documents folder":  ("open_custom_folder", "documents", "Opening documents folder"),
    "open desktop":          ("open_custom_folder", "desktop", "Opening desktop folder"),
    "open desktop folder":    ("open_custom_folder", "desktop", "Opening desktop folder"),
    "open pictures":         ("open_custom_folder", "pictures", "Opening pictures folder"),
    "open pictures folder":  ("open_custom_folder", "pictures", "Opening pictures folder"),
    "open picture folder":   ("open_custom_folder", "pictures", "Opening pictures folder"),
    "open music folder":     ("open_custom_folder", "music", "Opening music folder"),
    "open videos folder":    ("open_custom_folder", "videos", "Opening videos folder"),
    "open video folder":     ("open_custom_folder", "videos", "Opening video folder"),

    # ── Tab Navigation ──
    "next tab":            ("hotkey", "ctrl+tab", "Switching to next tab"),
    "previous tab":        ("hotkey", "ctrl+shift+tab", "Switching to previous tab"),
    "close tab":           ("hotkey", "ctrl+w", "Closing tab"),
    "close current tab":   ("hotkey", "ctrl+w", "Closing current tab"),
    "close this tab":      ("hotkey", "ctrl+w", "Closing this tab"),
    "new tab":             ("hotkey", "ctrl+t", "Opening new tab"),
    "open new tab":        ("hotkey", "ctrl+t", "Opening new tab"),
    "open a new tab":      ("hotkey", "ctrl+t", "Opening new tab"),
    "reopen tab":          ("hotkey", "ctrl+shift+t", "Reopening last closed tab"),

    # ── Page Navigation ──
    "go back":             ("hotkey", "alt+left", "Going back"),
    "go forward":          ("hotkey", "alt+right", "Going forward"),
    "refresh":             ("hotkey", "F5", "Refreshing page"),
    "refresh page":        ("hotkey", "F5", "Refreshing page"),
    "reload":              ("hotkey", "F5", "Reloading page"),
    "reload page":         ("hotkey", "F5", "Reloading page"),
    "go home":             ("hotkey", "alt+home", "Going to home page"),
    "address bar":         ("hotkey", "ctrl+l", "Focusing address bar"),
    "focus address bar":   ("hotkey", "ctrl+l", "Focusing address bar"),

    # ── Scrolling ──
    "scroll up":           ("scroll", "up_3", "Scrolling up"),
    "scroll down":         ("scroll", "down_3", "Scrolling down"),
    "scroll up more":      ("scroll", "up_10", "Scrolling up more"),
    "scroll down more":    ("scroll", "down_10", "Scrolling down more"),
    "scroll left":         ("scroll", "left_3", "Scrolling left"),
    "scroll right":        ("scroll", "right_3", "Scrolling right"),
    "page up":             ("hotkey", "pageup", "Page up"),
    "page down":           ("hotkey", "pagedown", "Page down"),
    "go to top":           ("hotkey", "ctrl+home", "Going to top of page"),
    "go to bottom":        ("hotkey", "ctrl+end", "Going to bottom of page"),
    "top of page":         ("hotkey", "ctrl+home", "Going to top of page"),
    "bottom of page":      ("hotkey", "ctrl+end", "Going to bottom of page"),

    # ── Click / Mouse ──
    "click":               ("mouse_click", "left", "Clicking"),
    "click here":          ("mouse_click", "left", "Clicking here"),
    "click link":          ("mouse_click", "left", "Clicking link"),
    "click the link":      ("mouse_click", "left", "Clicking the link"),
    "click that":          ("mouse_click", "left", "Clicking"),
    "click on that":       ("mouse_click", "left", "Clicking"),
    "right click":         ("mouse_click", "right", "Right clicking"),
    "double click":        ("mouse_click", "double", "Double clicking"),
    "open link":           ("mouse_click", "left", "Opening link"),
    "open the link":       ("mouse_click", "left", "Opening the link"),
    "open link in new tab": ("hotkey", "ctrl+enter", "Opening link in new tab"),
    # Positional link/result clicking (works on Google search results)
    "click first link":     ("click_nth_link", "1", "Clicking the first link"),
    "click the first link":  ("click_nth_link", "1", "Clicking the first link"),
    "click first result":   ("click_nth_link", "1", "Clicking the first result"),
    "click the first result":("click_nth_link", "1", "Clicking the first result"),
    "open first link":      ("click_nth_link", "1", "Opening the first link"),
    "open first result":    ("click_nth_link", "1", "Opening the first result"),
    "open the first link":  ("click_nth_link", "1", "Opening the first link"),
    "click second link":    ("click_nth_link", "2", "Clicking the second link"),
    "click the second link": ("click_nth_link", "2", "Clicking the second link"),
    "click second result":  ("click_nth_link", "2", "Clicking the second result"),
    "click the second result":("click_nth_link", "2", "Clicking the second result"),
    "open second link":     ("click_nth_link", "2", "Opening the second link"),
    "open the second link": ("click_nth_link", "2", "Opening the second link"),
    "click third link":     ("click_nth_link", "3", "Clicking the third link"),
    "click the third link":  ("click_nth_link", "3", "Clicking the third link"),
    "click third result":   ("click_nth_link", "3", "Clicking the third result"),
    "open third link":      ("click_nth_link", "3", "Opening the third link"),
    "click fourth link":    ("click_nth_link", "4", "Clicking the fourth link"),
    "click the fourth link": ("click_nth_link", "4", "Clicking the fourth link"),
    "click fourth result":  ("click_nth_link", "4", "Clicking the fourth result"),
    "open fourth link":     ("click_nth_link", "4", "Opening the fourth link"),
    "click fifth link":     ("click_nth_link", "5", "Clicking the fifth link"),
    "click the fifth link":  ("click_nth_link", "5", "Clicking the fifth link"),
    "click fifth result":   ("click_nth_link", "5", "Clicking the fifth result"),
    "open fifth link":      ("click_nth_link", "5", "Opening the fifth link"),
    "click last link":      ("click_nth_link", "-1", "Clicking the last link"),
    "click the last link":   ("click_nth_link", "-1", "Clicking the last link"),
    "click last result":    ("click_nth_link", "-1", "Clicking the last result"),
    "open last link":       ("click_nth_link", "-1", "Opening the last link"),
    "open the last link":   ("click_nth_link", "-1", "Opening the last link"),
    "next link":            ("hotkey", "tab", "Moving to next link"),
    "previous link":        ("hotkey", "shift+tab", "Moving to previous link"),

    # ── File Selection (in File Explorer) ──
    "open first file":      ("select_nth_file", "1_open", "Opening the first file"),
    "open the first file":  ("select_nth_file", "1_open", "Opening the first file"),
    "open second file":     ("select_nth_file", "2_open", "Opening the second file"),
    "open the second file": ("select_nth_file", "2_open", "Opening the second file"),
    "open third file":      ("select_nth_file", "3_open", "Opening the third file"),
    "open the third file":  ("select_nth_file", "3_open", "Opening the third file"),
    "open fourth file":     ("select_nth_file", "4_open", "Opening the fourth file"),
    "open the fourth file": ("select_nth_file", "4_open", "Opening the fourth file"),
    "open fifth file":      ("select_nth_file", "5_open", "Opening the fifth file"),
    "open the fifth file":  ("select_nth_file", "5_open", "Opening the fifth file"),
    "open last file":       ("select_nth_file", "-1_open", "Opening the last file"),
    "open the last file":   ("select_nth_file", "-1_open", "Opening the last file"),
    "select first file":    ("select_nth_file", "1_select", "Selecting the first file"),
    "select the first file": ("select_nth_file", "1_select", "Selecting the first file"),
    "select second file":   ("select_nth_file", "2_select", "Selecting the second file"),
    "select the second file":("select_nth_file", "2_select", "Selecting the second file"),
    "select third file":    ("select_nth_file", "3_select", "Selecting the third file"),
    "select last file":     ("select_nth_file", "-1_select", "Selecting the last file"),
    "open next file":       ("select_nth_file", "next_open", "Opening the next file"),
    "open previous file":   ("select_nth_file", "prev_open", "Opening the previous file"),
    "next file":            ("select_nth_file", "next_select", "Selecting next file"),
    "previous file":        ("select_nth_file", "prev_select", "Selecting previous file"),

    # ── Folder Selection (in File Explorer) ──
    "open first folder":      ("select_nth_file", "1_open", "Opening the first folder"),
    "open the first folder":  ("select_nth_file", "1_open", "Opening the first folder"),
    "open second folder":     ("select_nth_file", "2_open", "Opening the second folder"),
    "open the second folder": ("select_nth_file", "2_open", "Opening the second folder"),
    "open third folder":      ("select_nth_file", "3_open", "Opening the third folder"),
    "open the third folder":  ("select_nth_file", "3_open", "Opening the third folder"),
    "open fourth folder":     ("select_nth_file", "4_open", "Opening the fourth folder"),
    "open the fourth folder": ("select_nth_file", "4_open", "Opening the fourth folder"),
    "open fifth folder":      ("select_nth_file", "5_open", "Opening the fifth folder"),
    "open the fifth folder":  ("select_nth_file", "5_open", "Opening the fifth folder"),
    "open last folder":       ("select_nth_file", "-1_open", "Opening the last folder"),
    "open the last folder":   ("select_nth_file", "-1_open", "Opening the last folder"),
    "select first folder":    ("select_nth_file", "1_select", "Selecting the first folder"),
    "select the first folder":("select_nth_file", "1_select", "Selecting the first folder"),
    "select second folder":   ("select_nth_file", "2_select", "Selecting the second folder"),
    "select the second folder":("select_nth_file", "2_select", "Selecting the second folder"),
    "select third folder":    ("select_nth_file", "3_select", "Selecting the third folder"),
    "select last folder":     ("select_nth_file", "-1_select", "Selecting the last folder"),
    "open next folder":       ("select_nth_file", "next_open", "Opening the next folder"),
    "open previous folder":   ("select_nth_file", "prev_open", "Opening the previous folder"),
    "next folder":            ("select_nth_file", "next_select", "Selecting next folder"),
    "previous folder":        ("select_nth_file", "prev_select", "Selecting previous folder"),

    # ── Selection and Deselection ──
    "unselect folder":          ("deselect_item", "selected", "Unselecting selected folder"),
    "unselect selected folder": ("deselect_item", "selected", "Unselecting selected folder"),
    "unselect file":            ("deselect_item", "selected", "Unselecting selected file"),
    "unselect selected file":   ("deselect_item", "selected", "Unselecting selected file"),
    "deselect folder":          ("deselect_item", "selected", "Deselecting selected folder"),
    "deselect file":            ("deselect_item", "selected", "Deselecting selected file"),
    "unselect this":            ("deselect_item", "selected", "Unselecting this"),
    "deselect this":            ("deselect_item", "selected", "Deselecting this"),
    "deselect":                 ("deselect_item", "all", "Deselecting items"),
    "unselect":                 ("deselect_item", "all", "Unselecting items"),
    "unselect all":             ("deselect_item", "all", "Unselecting all items"),
    "deselect all":             ("deselect_item", "all", "Deselecting all items"),

    # ── File Operations (on selected file in Explorer) ──
    "open selected file":   ("hotkey", "enter", "Opening selected file"),
    "open this file":       ("hotkey", "enter", "Opening this file"),
    "open it":              ("hotkey", "enter", "Opening it"),
    "open folder":          ("hotkey", "enter", "Opening folder"),
    "open selected folder": ("hotkey", "enter", "Opening selected folder"),
    "open this folder":     ("hotkey", "enter", "Opening this folder"),
    "go back a folder":     ("hotkey", "alt+left", "Going back"),
    "back a folder":        ("hotkey", "alt+left", "Going back"),
    "go back folder":       ("hotkey", "alt+left", "Going back"),
    "properties":           ("hotkey", "alt+enter", "Showing properties"),
    "file properties":      ("hotkey", "alt+enter", "Showing file properties"),
    "show properties":      ("hotkey", "alt+enter", "Showing properties"),
    "show its properties":  ("hotkey", "alt+enter", "Showing properties"),
    "folder properties":    ("hotkey", "alt+enter", "Showing properties"),
    "show folder properties": ("hotkey", "alt+enter", "Showing properties"),
    "delete file":          ("hotkey", "delete", "Deleting file"),
    "delete folder":        ("hotkey", "delete", "Deleting folder"),
    "delete selected folder": ("hotkey", "delete", "Deleting folder"),
    "delete this":          ("hotkey", "delete", "Deleting"),
    "delete":               ("hotkey", "delete", "Deleting"),
    "permanent delete":     ("hotkey", "shift+delete", "Permanently deleting"),
    "rename file":          ("hotkey", "F2", "Renaming file"),
    "rename":               ("hotkey", "F2", "Ready to rename"),
    "rename this":          ("hotkey", "F2", "Ready to rename"),
    "copy file":            ("hotkey", "ctrl+c", "Copied file"),
    "cut file":             ("hotkey", "ctrl+x", "Cut file"),
    "paste file":           ("hotkey", "ctrl+v", "Pasting"),
    "new folder":           ("hotkey", "ctrl+shift+n", "Creating new folder"),
    "create folder":        ("hotkey", "ctrl+shift+n", "Creating new folder"),

    # ── Task View & App Switching ──
    "open task view":        ("task_view", "open", "Opening task view"),
    "show task view":        ("task_view", "open", "Opening task view"),
    "task view":             ("task_view", "open", "Opening task view"),
    "close task view":       ("task_view", "close", "Closing task view"),
    "exit task view":        ("task_view", "close", "Closing task view"),
    "select app":            ("task_view", "select", "Selecting application"),
    "select this app":       ("task_view", "select", "Selecting application"),
    "open this app":         ("task_view", "select", "Selecting application"),
    "choose app":            ("task_view", "select", "Selecting application"),
    "next app":              ("task_view", "next", "Moving to next application"),
    "next window":           ("task_view", "next", "Moving to next application"),
    "select next application": ("task_view", "next", "Moving to next application"),
    "previous app":          ("task_view", "prev", "Moving to previous application"),
    "prev app":              ("task_view", "prev", "Moving to previous application"),
    "select previous application": ("task_view", "prev", "Moving to previous application"),
    "select app up":         ("task_view", "up", "Moving focus up"),
    "move up":               ("task_view", "up", "Moving focus up"),
    "go up":                 ("task_view", "up", "Moving focus up"),
    "select app down":       ("task_view", "down", "Moving focus down"),
    "move down":             ("task_view", "down", "Moving focus down"),
    "go down":               ("task_view", "down", "Moving focus down"),

    # ── Explorer Window Closing ──
    "close file explorer":       ("close_explorer", "active", "Closing file explorer"),
    "close the file explorer":   ("close_explorer", "active", "Closing the file explorer"),
    "close explorer":            ("close_explorer", "active", "Closing explorer"),
    "close active folder":       ("close_explorer", "active", "Closing active folder"),
    "close folder":              ("close_explorer", "active", "Closing folder"),
    "close open folders":        ("close_explorer", "all", "Closing open folders"),
    "close all folders":         ("close_explorer", "all", "Closing all folders"),
    "close all explorer windows": ("close_explorer", "all", "Closing all explorer windows"),

    # ── Close / Dismiss / Cancel ──
    "close properties":             ("close_properties", None, "Closing properties"),
    "close properties window":      ("close_properties", None, "Closing properties window"),
    "close properties dialog":      ("close_properties", None, "Closing properties dialog"),
    "close folder properties":      ("close_properties", None, "Closing properties"),
    "close file properties":        ("close_properties", None, "Closing properties"),
    "close dialog":         ("hotkey", "escape", "Closing dialog"),
    "close popup":          ("hotkey", "escape", "Closing popup"),
    "close menu":           ("hotkey", "escape", "Closing menu"),
    "close this":           ("hotkey", "alt+F4", "Closing this"),
    "close it":             ("hotkey", "escape", "Closing it"),
    "dismiss":              ("hotkey", "escape", "Dismissed"),
    "cancel":               ("hotkey", "escape", "Cancelled"),
    "escape":               ("hotkey", "escape", "Escape"),
    "go back":              ("hotkey", "alt+left", "Going back"),
    "press ok":             ("hotkey", "enter", "Pressing OK"),
    "ok":                   ("hotkey", "enter", "OK"),
    "confirm":              ("hotkey", "enter", "Confirmed"),
    "press yes":            ("hotkey", "alt+y", "Pressing Yes"),
    "yes":                  ("hotkey", "alt+y", "Yes"),
    "press no":             ("hotkey", "alt+n", "Pressing No"),
    "no":                   ("hotkey", "alt+n", "No"),

    # ── Find on Page ──
    "find on page":        ("hotkey", "ctrl+f", "Opening find on page"),
    "find":                ("hotkey", "ctrl+f", "Opening find on page"),

    # ── Window Management ──
    "close window":        ("hotkey", "alt+F4", "Closing window"),
    "close this":          ("hotkey", "alt+F4", "Closing window"),
    "close this window":   ("hotkey", "alt+F4", "Closing window"),
    "minimize":            ("hotkey", "win+down", "Minimizing window"),
    "minimize window":     ("hotkey", "win+down", "Minimizing"),
    "maximize":            ("hotkey", "win+up", "Maximizing window"),
    "maximize window":     ("hotkey", "win+up", "Maximizing"),
    "switch window":       ("hotkey", "alt+tab", "Switching window"),
    "switch app":          ("hotkey", "alt+tab", "Switching app"),
    "show desktop":        ("hotkey", "win+d", "Showing desktop"),
    "snap left":           ("hotkey", "win+left", "Snapping window left"),
    "snap right":          ("hotkey", "win+right", "Snapping window right"),
    "full screen":         ("hotkey", "F11", "Toggling full screen"),

    # ── System ──
    "take screenshot":     ("hotkey", "win+shift+s", "Taking screenshot"),
    "screenshot":          ("hotkey", "win+shift+s", "Taking screenshot"),
    "lock screen":         ("hotkey", "win+l", "Locking screen"),
    "volume up":           ("hotkey", "volumeup", "Volume up"),
    "volume down":         ("hotkey", "volumedown", "Volume down"),
    "mute":                ("hotkey", "volumemute", "Toggling mute"),
    "play pause":          ("hotkey", "playpause", "Play or pause"),
    "copy":                ("hotkey", "ctrl+c", "Copied"),
    "paste":               ("hotkey", "ctrl+v", "Pasted"),
    "undo":                ("hotkey", "ctrl+z", "Undo"),
    "redo":                ("hotkey", "ctrl+y", "Redo"),
    "select all":          ("hotkey", "ctrl+a", "Selected all"),

    # ── Global Media Controls (work in any app via Windows media keys) ──
    "play":                ("hotkey", "playpause",  "Playing"),
    "pause":               ("hotkey", "playpause",  "Pausing"),
    "play pause":          ("hotkey", "playpause",  "Toggling playback"),
    "play or pause":       ("hotkey", "playpause",  "Toggling playback"),
    "toggle playback":     ("hotkey", "playpause",  "Toggling playback"),
    "next song":           ("hotkey", "nexttrack",  "Next track"),
    "next track":          ("hotkey", "nexttrack",  "Next track"),
    "previous song":       ("hotkey", "prevtrack",  "Previous track"),
    "previous track":      ("hotkey", "prevtrack",  "Previous track"),
    "skip song":           ("hotkey", "nexttrack",  "Skipping to next song"),
    "skip track":          ("hotkey", "nexttrack",  "Skipping track"),
    "go back song":        ("hotkey", "prevtrack",  "Going back one track"),

    # ── YouTube Music (focuses YT Music tab, uses its keyboard shortcuts) ──
    "play music":              ("yt_music", "play_pause", "Toggling music playback"),
    "pause music":             ("yt_music", "play_pause", "Pausing music"),
    "resume music":            ("yt_music", "play_pause", "Resuming music"),
    "play youtube music":      ("yt_music", "play_pause", "Toggling YouTube Music"),
    "pause youtube music":     ("yt_music", "play_pause", "Pausing YouTube Music"),
    "play the music":          ("yt_music", "play_pause", "Toggling YouTube Music"),
    "pause the music":         ("yt_music", "play_pause", "Pausing the music"),
    "start music":             ("yt_music", "play_pause", "Starting music"),
    "stop music":              ("yt_music", "play_pause", "Stopping music"),
    "next music":              ("yt_music", "next",       "Next song on YouTube Music"),
    "next on youtube music":   ("yt_music", "next",       "Next song on YouTube Music"),
    "previous music":          ("yt_music", "prev",       "Previous song on YouTube Music"),
    "previous on youtube music":("yt_music", "prev",      "Previous song on YouTube Music"),
    "mute music":              ("yt_music", "mute",       "Muting music"),
    "unmute music":            ("yt_music", "mute",       "Unmuting music"),
    "like this song":          ("yt_music", "like",       "Liking this song"),
    "dislike this song":       ("yt_music", "dislike",    "Disliking this song"),
    "shuffle music":           ("yt_music", "shuffle",    "Toggling shuffle"),
    "shuffle on":              ("yt_music", "shuffle",    "Toggling shuffle"),
    "volume up music":         ("yt_music", "vol_up",     "Increasing music volume"),
    "volume down music":       ("yt_music", "vol_down",   "Decreasing music volume"),
    "open youtube music":      ("launch",   "start https://music.youtube.com", "Opening YouTube Music"),

    # ── NavTools UI ──
    "go right":            ("nav", "right", "Moving right"),
    "move right":          ("nav", "right", "Moving right"),
    "next":                ("nav", "right", "Next"),
    "go left":             ("nav", "left", "Moving left"),
    "move left":           ("nav", "left", "Moving left"),
    "previous":            ("nav", "left", "Previous"),
    "select":              ("nav", "select", "Selecting"),
    "enter":               ("nav", "select", "Entering"),

    # ── Assistant ──
    "what can you do":     ("help", None, None),
    "help":                ("help", None, None),
    "help me":             ("help", None, None),
    "stop listening":      ("sleep", None, "Going to sleep. Say wake up Jack when you need me."),
    "go to sleep":         ("sleep", None, "Going to sleep. Say wake up Jack when you need me."),
    "sleep":               ("sleep", None, "Going to sleep. Say wake up Jack when you need me."),
    "close the assistant": ("stop_assistant", None, "Shutting down. Goodbye!"),
    "stop the assistant":  ("stop_assistant", None, "Shutting down. Goodbye!"),
    "turn off the assistant":("stop_assistant", None, "Shutting down. Goodbye!"),
    "turn off assistant":  ("stop_assistant", None, "Shutting down. Goodbye!"),
    "off the assistant":   ("stop_assistant", None, "Shutting down. Goodbye!"),
    "close assistant":     ("stop_assistant", None, "Shutting down. Goodbye!"),
    "stop assistant":      ("stop_assistant", None, "Shutting down. Goodbye!"),
    "exit application":    ("stop_assistant", None, "Shutting down. Goodbye!"),
    "quit application":    ("stop_assistant", None, "Shutting down. Goodbye!"),

    # ── Utilities & Shortcuts ──
    "take screenshot":     ("take_screenshot", None, "Taking a screenshot"),
    "take a screenshot":   ("take_screenshot", None, "Taking a screenshot"),
    "capture screen":      ("take_screenshot", None, "Taking a screenshot"),
    "screenshot":          ("take_screenshot", None, "Taking a screenshot"),
    "lock screen":         ("lock_pc", None, "Locking the computer"),
    "lock computer":       ("lock_pc", None, "Locking the computer"),
    "lock pc":             ("lock_pc", None, "Locking the computer"),
    "mute volume":         ("mute_unmute", "mute", "Muting volume"),
    "mute audio":          ("mute_unmute", "mute", "Muting volume"),
    "mute pc":             ("mute_unmute", "mute", "Muting volume"),
    "mute":                ("mute_unmute", "mute", "Muting volume"),
    "unmute volume":       ("mute_unmute", "unmute", "Restoring volume"),
    "unmute audio":        ("mute_unmute", "unmute", "Restoring volume"),
    "unmute pc":           ("mute_unmute", "unmute", "Restoring volume"),
    "unmute":              ("mute_unmute", "unmute", "Restoring volume"),
    "minimize all windows":("minimize_all", None, "Showing the desktop"),
    "minimize windows":    ("minimize_all", None, "Showing the desktop"),
    "show desktop":        ("minimize_all", None, "Showing the desktop"),
    "hide windows":        ("minimize_all", None, "Showing the desktop"),
    "maximize window":     ("maximize", None, "Maximizing window"),
    "maximize":            ("maximize", None, "Maximizing window"),

    # ── Date / Time / Info ──
    "what time is it":     ("tell_time", None, None),
    "what's the time":     ("tell_time", None, None),
    "tell me the time":    ("tell_time", None, None),
    "current time":        ("tell_time", None, None),
    "time please":         ("tell_time", None, None),
    "what date is it":     ("tell_date", None, None),
    "what's the date":     ("tell_date", None, None),
    "what is the date":    ("tell_date", None, None),
    "tell me the date":    ("tell_date", None, None),
    "today's date":        ("tell_date", None, None),
    "current date":        ("tell_date", None, None),
    "what day is it":      ("tell_day", None, None),
    "what day is today":   ("tell_day", None, None),
    "what's today":        ("tell_day", None, None),

    # ── Battery ──
    "battery status":      ("battery", None, None),
    "battery level":       ("battery", None, None),
    "check battery":       ("battery", None, None),
    "how much battery":    ("battery", None, None),
    "battery percentage":  ("battery", None, None),
    "battery percent":     ("battery", None, None),

    # ── System Power ──
    "shutdown computer":   ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "shut down computer":  ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "shutdown the computer":("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "shut down the computer":("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "shutdown pc":         ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "shut down pc":        ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "turn off computer":   ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "turn off the computer":("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "turn off pc":         ("power", "shutdown", "Shutting down the computer in 10 seconds. Say cancel to abort."),
    "restart computer":    ("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "restart the computer":("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "restart pc":          ("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "reboot computer":     ("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "reboot the computer": ("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "reboot pc":           ("power", "restart", "Restarting the computer in 10 seconds. Say cancel to abort."),
    "sleep computer":      ("power", "sleep_pc", "Putting the computer to sleep."),
    "sleep the computer":  ("power", "sleep_pc", "Putting the computer to sleep."),
    "sleep pc":            ("power", "sleep_pc", "Putting the computer to sleep."),
    "put computer to sleep":("power", "sleep_pc", "Putting the computer to sleep."),
    "cancel shutdown":     ("power", "cancel", "Shutdown cancelled."),
    "cancel restart":      ("power", "cancel", "Restart cancelled."),
    "abort shutdown":      ("power", "cancel", "Shutdown cancelled."),
    "abort restart":       ("power", "cancel", "Restart cancelled."),

    # ── Wi-Fi ──
    "turn on wifi":        ("wifi", "on", "Turning on Wi-Fi"),
    "turn off wifi":       ("wifi", "off", "Turning off Wi-Fi"),
    "enable wifi":         ("wifi", "on", "Enabling Wi-Fi"),
    "disable wifi":        ("wifi", "off", "Disabling Wi-Fi"),
    "wifi on":             ("wifi", "on", "Turning on Wi-Fi"),
    "wifi off":            ("wifi", "off", "Turning off Wi-Fi"),
    "show wifi networks":  ("list_wifi", None, None),
    "show wifi":           ("list_wifi", None, None),
    "list wifi networks":  ("list_wifi", None, None),
    "list wifi":           ("list_wifi", None, None),
    "scan wifi":           ("list_wifi", None, None),
    "scan wifi networks":  ("list_wifi", None, None),
    "available wifi":      ("list_wifi", None, None),
    "available networks":  ("list_wifi", None, None),
    "show available networks": ("list_wifi", None, None),
    "show available wifi":     ("list_wifi", None, None),
    "what wifi networks are available": ("list_wifi", None, None),
    "which wifi":          ("list_wifi", None, None),
    "disconnect wifi":     ("disconnect_wifi", None, "Disconnecting from Wi-Fi"),
    "disconnect from wifi":("disconnect_wifi", None, "Disconnecting from Wi-Fi"),
    "disconnect network":  ("disconnect_wifi", None, "Disconnecting from Wi-Fi"),
    "disconnect from network":("disconnect_wifi", None, "Disconnecting from Wi-Fi"),

    # ── Brightness ──
    "increase brightness": ("brightness", "up", "Increasing brightness"),
    "decrease brightness": ("brightness", "down", "Decreasing brightness"),
    "brightness up":       ("brightness", "up", "Increasing brightness"),
    "brightness down":     ("brightness", "down", "Decreasing brightness"),
    "maximum brightness":  ("brightness", "max", "Setting maximum brightness"),
    "minimum brightness":  ("brightness", "min", "Setting minimum brightness"),
    "full brightness":     ("brightness", "max", "Setting maximum brightness"),

    # ── Dynamic Launchers ──
    "launch eye tracking":    ("launch_gaze", None, "Launching gaze tracking mechanism"),
    "launch eye cursor":      ("launch_gaze", None, "Launching gaze tracking mechanism"),
    "start eye tracking":     ("launch_gaze", None, "Launching gaze tracking mechanism"),
    "start eye cursor":       ("launch_gaze", None, "Launching gaze tracking mechanism"),
    "stop eye tracking":      ("stop_gaze", None, "Stopping gaze tracking mechanism"),
    "stop eye cursor":        ("stop_gaze", None, "Stopping gaze tracking mechanism"),
    "close eye tracking":     ("stop_gaze", None, "Stopping gaze tracking mechanism"),
    "close eye cursor":       ("stop_gaze", None, "Stopping gaze tracking mechanism"),

    # ── UI Commands ──
    "open assistant settings":   ("ui_command", "open_settings", "Opening settings panel"),
    "open assistance settings":  ("ui_command", "open_settings", "Opening settings panel"),
    "open assistant setting":    ("ui_command", "open_settings", "Opening settings panel"),
    "open assistance setting":   ("ui_command", "open_settings", "Opening settings panel"),
    "open settings":             ("ui_command", "open_settings", "Opening settings panel"),
    "open settings panel":       ("ui_command", "open_settings", "Opening settings panel"),
    "open setting panel":         ("ui_command", "open_settings", "Opening settings panel"),
    "open settings dashboard":   ("ui_command", "open_settings", "Opening settings panel"),
    "open setting dashboard":     ("ui_command", "open_settings", "Opening settings panel"),
    "show assistant settings":   ("ui_command", "open_settings", "Opening settings panel"),
    "show assistance settings":  ("ui_command", "open_settings", "Opening settings panel"),
    "show assistant setting":    ("ui_command", "open_settings", "Opening settings panel"),
    "show assistance setting":   ("ui_command", "open_settings", "Opening settings panel"),
    "show settings":             ("ui_command", "open_settings", "Opening settings panel"),
    "show settings panel":       ("ui_command", "open_settings", "Opening settings panel"),
    "show setting panel":         ("ui_command", "open_settings", "Opening settings panel"),
    "show settings dashboard":   ("ui_command", "open_settings", "Opening settings panel"),
    "show setting dashboard":     ("ui_command", "open_settings", "Opening settings panel"),
    "open control center":       ("ui_command", "open_settings", "Opening settings panel"),
    "open assistant control center": ("ui_command", "open_settings", "Opening settings panel"),
    "open assistance control center":("ui_command", "open_settings", "Opening settings panel"),
    "show control center":       ("ui_command", "open_settings", "Opening settings panel"),
    "show assistant control center": ("ui_command", "open_settings", "Opening settings panel"),
    "show assistance control center":("ui_command", "open_settings", "Opening settings panel"),
    "open dashboard":            ("ui_command", "open_settings", "Opening settings panel"),
    "show dashboard":            ("ui_command", "open_settings", "Opening settings panel"),
    "open control dashboard":     ("ui_command", "open_settings", "Opening settings panel"),
    "show control dashboard":     ("ui_command", "open_settings", "Opening settings panel"),
    "open navtools settings":     ("ui_command", "open_settings", "Opening settings panel"),
    "open navigation settings":   ("ui_command", "open_settings", "Opening settings panel"),
    "open assistant panel":      ("ui_command", "open_settings", "Opening settings panel"),
    "show assistant panel":      ("ui_command", "open_settings", "Opening settings panel"),
    "open panel":                ("ui_command", "open_settings", "Opening settings panel"),
    "show panel":                ("ui_command", "open_settings", "Opening settings panel"),

    "close assistant settings":  ("ui_command", "close_settings", "Closing settings panel"),
    "close assistance settings": ("ui_command", "close_settings", "Closing settings panel"),
    "close assistant setting":   ("ui_command", "close_settings", "Closing settings panel"),
    "close assistance setting":  ("ui_command", "close_settings", "Closing settings panel"),
    "close settings":            ("ui_command", "close_settings", "Closing settings panel"),
    "close settings panel":      ("ui_command", "close_settings", "Closing settings panel"),
    "close setting panel":        ("ui_command", "close_settings", "Closing settings panel"),
    "close settings dashboard":  ("ui_command", "close_settings", "Closing settings panel"),
    "close setting dashboard":    ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistant settings":   ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistance settings":  ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistant setting":    ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistance setting":   ("ui_command", "close_settings", "Closing settings panel"),
    "hide settings":             ("ui_command", "close_settings", "Closing settings panel"),
    "hide settings panel":       ("ui_command", "close_settings", "Closing settings panel"),
    "hide setting panel":         ("ui_command", "close_settings", "Closing settings panel"),
    "hide settings dashboard":   ("ui_command", "close_settings", "Closing settings panel"),
    "hide setting dashboard":     ("ui_command", "close_settings", "Closing settings panel"),
    "close control center":      ("ui_command", "close_settings", "Closing settings panel"),
    "close assistant control center": ("ui_command", "close_settings", "Closing settings panel"),
    "close assistance control center":("ui_command", "close_settings", "Closing settings panel"),
    "hide control center":       ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistant control center": ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistance control center":("ui_command", "close_settings", "Closing settings panel"),
    "close dashboard":           ("ui_command", "close_settings", "Closing settings panel"),
    "hide dashboard":            ("ui_command", "close_settings", "Closing settings panel"),
    "close control dashboard":   ("ui_command", "close_settings", "Closing settings panel"),
    "hide control dashboard":   ("ui_command", "close_settings", "Closing settings panel"),
    "close navtools settings":   ("ui_command", "close_settings", "Closing settings panel"),
    "close navigation settings": ("ui_command", "close_settings", "Closing settings panel"),
    "close assistant panel":     ("ui_command", "close_settings", "Closing settings panel"),
    "hide assistant panel":     ("ui_command", "close_settings", "Closing settings panel"),
    "close panel":               ("ui_command", "close_settings", "Closing settings panel"),
    "hide panel":                ("ui_command", "close_settings", "Closing settings panel"),
}

# Dynamic command prefixes — these extract a query from the speech
# Order matters: more specific prefixes must come BEFORE general ones
DYNAMIC_PREFIXES = [
    ("do a calculation of",   "calculate"),
    ("calculate",             "calculate"),
    ("do calculation of",      "calculate"),
    ("set sensitivity to ",   "set_sensitivity"),
    ("set the sensitivity to ","set_sensitivity"),
    ("adjust sensitivity to ","set_sensitivity"),
    ("adjust the sensitivity to ","set_sensitivity"),
    ("change sensitivity to ","set_sensitivity"),
    ("change the sensitivity to ","set_sensitivity"),
    ("increase sensitivity to ","set_sensitivity"),
    ("increase the sensitivity to ","set_sensitivity"),
    ("decrease sensitivity to ","set_sensitivity"),
    ("decrease the sensitivity to ","set_sensitivity"),
    ("set sensitivity ",      "set_sensitivity"),
    ("set the sensitivity ",  "set_sensitivity"),
    ("sensitivity ",          "set_sensitivity"),
    ("set voice speed to ",   "set_voice_speed"),
    ("set the voice speed to ","set_voice_speed"),
    ("set speed to ",         "set_voice_speed"),
    ("change voice speed to ","set_voice_speed"),
    ("change speed to ",      "set_voice_speed"),
    ("increase speed to ",    "set_voice_speed"),
    ("decrease speed to ",    "set_voice_speed"),
    ("set voice speed ",      "set_voice_speed"),
    ("set speed ",            "set_voice_speed"),
    ("voice speed ",          "set_voice_speed"),
    ("speed ",                "set_voice_speed"),
    ("set volume to ",        "set_volume"),
    ("set the volume to ",    "set_volume"),
    ("change volume to ",     "set_volume"),
    ("change the volume to ", "set_volume"),
    ("adjust volume to ",     "set_volume"),
    ("adjust the volume to ", "set_volume"),
    ("set volume ",           "set_volume"),
    ("set the volume ",       "set_volume"),
    ("volume ",               "set_volume"),
    ("set brightness to ",    "set_brightness"),
    ("set the brightness to ","set_brightness"),
    ("change brightness to ", "set_brightness"),
    ("change the brightness to ","set_brightness"),
    ("set brightness ",       "set_brightness"),
    ("set the brightness ",   "set_brightness"),
    ("brightness ",           "set_brightness"),
    ("connect to wifi ",      "connect_wifi"),
    ("connect to network ",   "connect_wifi"),
    ("connect to the wifi ",  "connect_wifi"),
    ("connect to the network ","connect_wifi"),
    ("connect wifi ",         "connect_wifi"),
    ("join wifi ",            "connect_wifi"),
    ("join network ",         "connect_wifi"),
    ("switch to wifi ",       "connect_wifi"),
    ("switch wifi to ",       "connect_wifi"),
    ("search in explorer for", "find_file"),
    ("search in file explorer for", "find_file"),
    ("search in explorer",    "find_file"),
    ("search in file explorer","find_file"),
    ("find file",             "find_file"),
    ("find folder",           "find_file"),
    ("search file",           "find_file"),
    ("search files for",      "find_file"),
    ("google search for",     "search_google"),
    ("google search",         "search_google"),
    ("google",                "search_google"),
    ("search for",            "search_smart"),
    ("search",                "search_smart"),
    ("look up",               "search_smart"),
    ("open file",             "open_file"),
    ("open folder",           "open_folder"),
    ("open website",          "open_url"),
    ("go to website",         "open_url"),
    ("go to",                 "open_url"),
    ("type",                  "type_text"),
    ("play ",                 "play_music"),
    ("close ",                "close_app"),
    ("stop ",                 "close_app"),
    ("terminate ",            "close_app"),
    ("exit ",                 "close_app"),
    ("open ",                 "open_app"),
]

# Suffixes that specify WHERE to search (stripped from query)
SEARCH_TARGET_SUFFIXES = [
    ("in file explorer",  "explorer"),
    ("in explorer",       "explorer"),
    ("in files",          "explorer"),
    ("in folders",        "explorer"),
    ("on youtube music",  "youtube_music"),
    ("in youtube music",  "youtube_music"),
    ("on youtube",        "youtube"),
    ("in browser",        "google"),
    ("in chrome",         "google"),
    ("in google",         "google"),
    ("on google",         "google"),
    ("on chrome",         "google"),
    ("on browser",        "google"),
    ("on the web",        "google"),
    ("online",            "google"),
]


# ──────────────────────────────────────────────
# WAKE PHRASE DETECTION (optimised)
# ──────────────────────────────────────────────

# All known name-sounds that Google en-IN may produce for "Jim"
_JIM_SOUNDS = frozenset({
    "jim", "gym", "gem", "tim", "him", "dim", "vim", "gin",
    "gm", "jm", "gy", "gi", "gim", "jeem", "geem",
    # Common Google Speech Indian-accent mishears
    "hygiene", "jeans", "jean", "gene", "chin", "shin",
    "slim", "chime", "jam", "gum", "zoom", "jig",
    "chimb", "jib", "gimp", "jimp",
    # Calibration-discovered mishears (user's actual voice)
    "jack", "jac", "jak",
    # Single-syllable sounds Google produces
    "team", "deem", "seem", "theme",
})

# Trigger/context words that appear alongside the name
_WAKE_TRIGGERS = frozenset({
    "wake", "woke", "waking", "up", "hey", "hi", "hello",
    "wakey", "yo", "ok", "okay", "hay", "haye",
    "breakup", "makeup", "because", "a",
})

# Pre-built frozenset of full wake phrases for O(1) lookup
WAKE_PHRASES = frozenset({
    # ── Full phrases ──
    "wake up jim", "wake up gym", "wake up gem",
    "wake up tim", "wake up him", "wake up team",
    "wake up dim", "wake up gim", "wake up jeem",
    "wakeup jim", "wakeup gym", "wake of jim", "wake of gym",
    "hey jim", "hey gym", "hey gem", "hey tim", "hey him",
    "hey dim", "hey gin", "hey vim", "hey gim", "hey jeem",
    "hi jim", "hi gym", "hi gem", "hi tim", "hi him",
    "hi dim", "hi gim",
    "hello jim", "hello gym", "hello gem",
    "yo jim", "yo gym",
    "ok jim", "ok gym", "okay jim", "okay gym",
    "a jim", "a gym", "a gem",
    "wakey wakey jim", "wakey wakey gym", "wakey wakey gem", "wakey wakey",
    "wake up", "wakeup",
    # ── Name only (short triggers) ──
    "jim", "gym", "gem", "tim", "gim", "jeem", "geem",
    # ── Google Speech Indian-accent mishears ──
    "hygiene", "hey hygiene", "wake up hygiene", "hi hygiene",
    "jeans", "hey jeans", "wake up jeans", "hi jeans",
    "jean", "hey jean", "wake up jean", "hi jean",
    "gene", "hey gene", "wake up gene", "hi gene",
    "gin", "hey gin", "wake up gin", "hi gin",
    "chin", "hey chin", "wake up chin",
    "shin", "hey shin", "wake up shin",
    "chime", "hey chime", "wake up chime",
    # ── Compound mishears ──
    "breakup gym", "break up gym", "breakup jim", "break up jim",
    "makeup gym", "make up gym", "makeup jim", "make up jim",
    "because gym", "because jim",
    "waking gym", "waking jim", "waking up gym", "waking up jim",
    # ── Calibration-discovered (user's actual voice) ──
    "jack", "jack jack", "hey jack", "hi jack", "hello jack",
    "wake up jack", "wakeup jack", "ok jack", "okay jack",
    "yo jack", "a jack",
})

STATE_IDLE      = "idle"
STATE_LISTENING = "listening"
STATE_SLEEPING  = "sleeping"


def _contains_wake(text: str) -> bool:
    """Check if any wake phrase variant appears in the text.

    Uses a three-tier strategy:
      1. Exact full-string match against frozenset  (fastest)
      2. Substring scan for each known phrase        (catches embedded wake words)
      3. Fuzzy word-level match                      (catches unknown combos)
    """
    cleaned = text.lower().strip().strip('.?!,;:-_`"\'')

    # Tier 1: exact full-string match (O(1))
    if cleaned in WAKE_PHRASES:
        return True

    # Tier 2: substring containment (handles "um wake up jim please")
    for phrase in WAKE_PHRASES:
        if len(phrase) > 2 and phrase in cleaned:
            return True

    # Tier 3: fuzzy word-level — any Jim-sound + any trigger word
    words = set(cleaned.split())
    if words & _JIM_SOUNDS and words & _WAKE_TRIGGERS:
        return True

    # Tier 4: phonetic proximity — single word within 1 edit of "jim"
    for w in words:
        if len(w) <= 4 and w not in {"the", "and", "for", "but", "not", "you", "are"}:
            if _is_near_jim(w):
                return True

    return False


def _is_near_jim(word: str) -> bool:
    """Check if a word is within 1 character edit of 'jack', 'jim' or 'gym'."""
    targets = ("jack", "jim", "gym")
    for t in targets:
        if word == t:
            return True
        if len(word) == len(t):
            diffs = sum(a != b for a, b in zip(word, t))
            if diffs <= 1:
                return True
        elif abs(len(word) - len(t)) == 1:
            # One insertion or deletion
            longer, shorter = (word, t) if len(word) > len(t) else (t, word)
            i = j = misses = 0
            while i < len(longer) and j < len(shorter):
                if longer[i] != shorter[j]:
                    misses += 1
                    i += 1
                else:
                    i += 1
                    j += 1
            if misses <= 1:
                return True
    return False


def _strip_wake(text: str) -> str:
    """Remove the wake phrase from text and return the remainder."""
    text = text.lower().strip()
    for phrase in WAKE_PHRASES:
        if phrase in text:
            remainder = text.split(phrase, 1)[-1].strip()
            return remainder.strip('.?!,;:-_`"\'')
    return text.strip('.?!,;:-_`"\'')


def _parse_number_from_text(text: str):
    """Parse text containing numbers (either digits like '400' or words like 'four hundred') into a float/int."""
    if not text:
        return None
    import re
    # Check if there is a digit (integer or decimal) in the text first
    digit_match = re.findall(r'\d+\.\d+|\d+', text)
    if digit_match:
        try:
            return float(digit_match[0])
        except ValueError:
            pass

    # If no digits found, parse spoken English words
    words = text.lower().replace("-", " ").split()
    
    num_words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
    }
    
    multipliers = {
        "hundred": 100,
        "thousand": 1000
    }
    
    total = 0
    current = 0
    found_any = False
    
    for word in words:
        if word in num_words:
            current += num_words[word]
            found_any = True
        elif word in multipliers:
            factor = multipliers[word]
            if current == 0:
                current = 1
            current *= factor
            total += current
            current = 0
            found_any = True
        elif word == "point":
            found_any = True
            try:
                idx = words.index(word)
                decimal_part = 0.0
                divisor = 10.0
                for dec_word in words[idx+1:]:
                    if dec_word in num_words and num_words[dec_word] < 10:
                        decimal_part += num_words[dec_word] / divisor
                        divisor *= 10.0
                    else:
                        break
                total += current + decimal_part
                return total
            except Exception:
                pass
            
    total += current
    return total if found_any else None


# ──────────────────────────────────────────────
# JIM VOICE ASSISTANT
# ──────────────────────────────────────────────

class VoiceAssistant(threading.Thread):
    """
    Interactive voice assistant named Jack.
    Uses Google Speech Recognition (en-IN) + Windows SAPI5 TTS.
    """

    def __init__(self, require_attention=True, ui_callback=None, state_callback=None, **kwargs):
        super().__init__(daemon=True, name="VoiceAssistant")
        global _active_assistant
        _active_assistant = self
        self.require_attention = require_attention
        self.ui_callback = ui_callback
        self.state_callback = state_callback
        self._running = False
        self._state = STATE_IDLE
        self.gaze_tracker = None
        self._api_errors = 0          # Track consecutive API failures

        # Speech recognizer — tuned for responsiveness
        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold = 400
        self._recognizer.dynamic_energy_threshold = False
        self._recognizer.pause_threshold = 0.6        # Faster phrase-end detection
        self._recognizer.non_speaking_duration = 0.4   # Less silence needed to start

    def _listen(self, mic, timeout=5, phrase_time_limit=6, for_wake=False) -> str:
        """Listen to microphone and return transcribed text.

        Args:
            for_wake: If True, request multiple alternatives from Google
                      to improve wake-word hit rate.
        """
        try:
            self._recognizer.energy_threshold = attention.mic_sensitivity
            if not for_wake:
                logger.info(f"  (listening with sensitivity {self._recognizer.energy_threshold}...)")
            audio = self._recognizer.listen(
                mic, timeout=timeout,
                phrase_time_limit=phrase_time_limit
            )
            audio_len = len(audio.get_raw_data())
            # Skip very short audio (< 0.3s) — likely noise bursts
            if audio_len < 9600:
                return ""
            logger.info(f"  (got {audio_len/32000:.1f}s audio, recognizing...)")

            try:
                if for_wake:
                    # Request multiple alternatives for better wake-word matching
                    results = self._recognizer.recognize_google(
                        audio, language="en-IN", show_all=True
                    )
                    if not results or not isinstance(results, dict):
                        return ""
                    alternatives = results.get("alternative", [])
                    # Check ALL alternatives for wake phrase
                    for alt in alternatives:
                        transcript = alt.get("transcript", "").lower().strip()
                        if transcript and _contains_wake(transcript):
                            logger.info(f'  >>> YOU SAID: "{transcript}" (wake detected)')
                            self._api_errors = 0
                            return transcript
                    # No wake phrase found — return top transcript anyway
                    if alternatives:
                        top = alternatives[0].get("transcript", "").lower().strip()
                        if top:
                            logger.info(f'  >>> YOU SAID: "{top}"')
                            self._api_errors = 0
                            return top
                    return ""
                else:
                    text = self._recognizer.recognize_google(audio, language="en-IN")
                    logger.info(f'  >>> YOU SAID: "{text}"')
                    self._api_errors = 0
                    return text.lower().strip()

            except sr.UnknownValueError:
                logger.info("  (could not understand)")
                return ""
            except sr.RequestError as e:
                self._api_errors += 1
                logger.warning(f"  (Google API error #{self._api_errors}: {e})")

                # Check actual internet connectivity
                online = self._check_internet()

                # Decide whether to speak to the user
                # Repeat the offline/error message after every second try (less spammy)
                should_speak = (self._api_errors % 2 == 0)

                if should_speak:
                    if self.state_callback: self.state_callback("speaking")
                    if not online:
                        speak("I can't reach the internet right now. Please check your Wi-Fi or network connection. I'll keep trying.")
                    else:
                        speak("I'm having trouble connecting to the speech service. The internet seems fine, so this may be a temporary issue.")
                    if self.state_callback: self.state_callback(self._state)

                # Back off — longer when offline to save resources
                if self._api_errors >= 3:
                    if online:
                        backoff = min(5, self._api_errors - 2)
                    else:
                        backoff = min(15, self._api_errors)
                    logger.warning(f"  (backing off {backoff}s — {'online' if online else 'OFFLINE'})")
                    time.sleep(backoff)
                return ""

        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            logger.error(f"  Listen error: {type(e).__name__}: {e}")
            return ""
    @staticmethod
    def _check_internet(timeout=2) -> bool:
        """Quick internet connectivity check via socket to Google DNS."""
        import socket
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=timeout)
            sock.close()
            return True
        except OSError:
            return False

    def set_state(self, new_state: str):
        self._state = new_state
        if self.state_callback:
            self.state_callback(new_state)

    def run(self):
        self._running = True
        self.set_state(STATE_IDLE)

        # Greeting BEFORE opening mic
        if self.state_callback: self.state_callback("speaking")
        speak("Jack assistant is online. Say wake up Jack or hey Jack to activate me.")
        if self.state_callback: self.state_callback(STATE_IDLE)

        # ── Open Microphone ─────────────────────────────────────────
        logger.info("  Opening microphone...")
        try:
            mics = sr.Microphone.list_microphone_names()
            logger.info(f"  Available microphones ({len(mics)}):")
            for i, name in enumerate(mics):
                logger.info(f"    [{i}] {name}")
        except Exception as e:
            logger.warning(f"  Could not list microphones: {e}")

        mic = None
        mic_source = None
        try:
            mic = sr.Microphone()
            mic_source = mic.__enter__()
            logger.info("  Microphone opened successfully.")
            logger.info("  Adjusting for ambient noise (1s)...")
            self._recognizer.adjust_for_ambient_noise(mic_source, duration=1)
            logger.info(f"  Energy threshold set to {self._recognizer.energy_threshold:.0f}")
        except OSError as e:
            logger.error(f"  MICROPHONE ERROR: {e}")
            logger.error("  No audio input device found or device is busy.")
            logger.error("  Check that a microphone is connected and not in use by another app.")
            if self.state_callback: self.state_callback("idle")
            return
        except Exception as e:
            logger.error(f"  Failed to open microphone: {type(e).__name__}: {e}")
            if self.state_callback: self.state_callback("idle")
            return

        logger.info("=" * 55)
        logger.info("  Jack Voice Assistant -- READY")
        logger.info('  Say "wake up Jack" to activate')
        logger.info("=" * 55)

        try:
            while self._running:
                # Attention gate
                if self.require_attention and not attention.is_attentive:
                    time.sleep(0.3)
                    continue

                # ── SLEEPING — only wake phrase wakes up ──
                if self._state == STATE_SLEEPING:
                    text = self._listen(mic_source, timeout=3, phrase_time_limit=4, for_wake=True)
                    if text and _contains_wake(text):
                        self.set_state(STATE_IDLE)
                        logger.info("  Jack woke up from sleep")
                        if self.state_callback: self.state_callback("speaking")
                        speak("I'm back. What can I help you with?")
                        if self.state_callback: self.state_callback(STATE_IDLE)
                    continue

                # ── IDLE — listen for wake phrase with short timeout ──
                if self._state == STATE_IDLE:
                    text = self._listen(mic_source, timeout=2, phrase_time_limit=4, for_wake=True)
                    if not text:
                        continue

                    if _contains_wake(text):
                        after_wake = _strip_wake(text)
                        
                        # Set to active listening state
                        self.set_state(STATE_LISTENING)
                        
                        if after_wake and len(after_wake) > 2:
                            # User said wake phrase + command in one go
                            if self.state_callback: self.state_callback("speaking")
                            # Process first command
                            self._process_command(after_wake)
                            # Now enter active 10s conversation window
                            self._run_conversation_window(mic_source)
                        else:
                            # Wake phrase only — listen for command
                            if self.state_callback: self.state_callback("speaking")
                            speak("What can I help you with today?")
                            if self.state_callback: self.state_callback(STATE_LISTENING)

                            # Give generous timeout for command
                            cmd = self._listen(mic_source, timeout=8, phrase_time_limit=10)
                            if cmd:
                                logger.info(f'  >>> COMMAND: "{cmd}"')
                                self._process_command(cmd)
                                # Enter active 10s conversation window
                                self._run_conversation_window(mic_source)
                            else:
                                # Second chance — maybe user was slow to speak
                                if self.state_callback: self.state_callback("speaking")
                                speak("I'm still listening.")
                                if self.state_callback: self.state_callback(STATE_LISTENING)
                                cmd = self._listen(mic_source, timeout=6, phrase_time_limit=8)
                                if cmd:
                                    logger.info(f'  >>> COMMAND (2nd try): "{cmd}"')
                                    self._process_command(cmd)
                                    # Enter active 10s conversation window
                                    self._run_conversation_window(mic_source)
                                else:
                                    if self.state_callback: self.state_callback("speaking")
                                    speak("I didn't catch that. Say hey Jack to try again.")
                        # Return to IDLE state after conversation window ends
                        self.set_state(STATE_IDLE)
                    continue

        except KeyboardInterrupt:
            pass
        finally:
            if mic is not None:
                try:
                    mic.__exit__(None, None, None)
                except Exception:
                    pass
            if self.state_callback: self.state_callback("speaking")
            speak("Jack signing off. Goodbye.")
            logger.info("Jack assistant stopped")

    def _run_conversation_window(self, mic_source):
        """Remain in active listening state for a 10s window to handle follow-up commands without wake word."""
        start_t = time.time()
        logger.info("  Starting 10-second active conversation window...")
        
        while self._running:
            if self._state != STATE_LISTENING:
                logger.info(f"  State changed to {self._state}. Exiting active conversation window.")
                break

            # Check attention gating if required
            if self.require_attention and not attention.is_attentive:
                time.sleep(0.3)
                continue

            now = time.time()
            elapsed = now - start_t
            if elapsed >= 10.0:
                logger.info("  10-second active window expired. Reverting to standby.")
                if self.state_callback: self.state_callback("speaking")
                speak("Going to standby.")
                break
                
            # Listen with timeout equal to remaining window time, capped at 3s for responsiveness
            timeout = min(3.0, max(1.0, 10.0 - elapsed))
            
            cmd = self._listen(mic_source, timeout=timeout, phrase_time_limit=8)
            if cmd:
                logger.info(f'  >>> FOLLOW-UP COMMAND: "{cmd}"')
                
                # Process user command
                self._process_command(cmd)
                
                # Reset the 10-second active window timer!
                start_t = time.time()
                logger.info("  Resetting 10-second active conversation window.")
            else:
                # Brief sleep to prevent tight CPU looping
                time.sleep(0.1)

    def stop(self):
        self._running = False

    def _process_command(self, text: str):
        """Find the best matching command and execute it."""
        # Clean leading/trailing punctuation and whitespace
        text = text.lower().strip().strip('.?!,;:-_`"\'')

        # 1. Exact static match first
        if text in VOICE_COMMANDS:
            action_type, arg, response = VOICE_COMMANDS[text]
            self._execute(action_type, arg, response)
            return

        # 2. Check for link/result clicking with a number (e.g. "click link three", "click link 3", "click result two", "click result 2")
        # Check for file selection with a number (e.g. "select file four", "select file 4", "open file five", "open file 5")
        clean_text = text.replace("-", " ")
        
        # 2a. Click nth link / result
        link_patterns = [
            "click link ", "click the link ", "open link ", "open the link ",
            "click result ", "click the result ", "open result ", "open the result "
        ]
        for pat in link_patterns:
            if clean_text.startswith(pat):
                num_part = clean_text[len(pat):].strip()
                val = _parse_number_from_text(num_part)
                if val is not None:
                    n = int(val)
                    self._execute("click_nth_link", str(n), f"Clicking link {n}")
                    return

        # 2b. Dynamic select/open nth file/folder/item parser
        # Matches: "select the fifth folder", "select the last folder", "open folder 3", "select folder number 5", etc.
        import re
        pattern1 = r'^(select|open)\s+(?:the\s+)?(\w+|\d+)(?:st|nd|rd|th)?\s+(folder|file|item)$'
        pattern2 = r'^(select|open)\s+(?:the\s+)?(folder|file|item)\s+(?:number\s+)?(\w+|\d+)$'
        
        m1 = re.match(pattern1, clean_text)
        m2 = re.match(pattern2, clean_text)
        
        matched = False
        action = None
        n = None
        item_type = None
        
        ordinals_map = {
            "first": 1, "1st": 1,
            "second": 2, "2nd": 2,
            "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6,
            "seventh": 7, "7th": 7,
            "eighth": 8, "8th": 8,
            "ninth": 9, "9th": 9,
            "tenth": 10, "10th": 10,
            "last": -1
        }
        
        if m1:
            action = m1.group(1)
            num_part = m1.group(2)
            item_type = m1.group(3)
            
            if num_part.isdigit():
                n = int(num_part)
                matched = True
            elif num_part in ordinals_map:
                n = ordinals_map[num_part]
                matched = True
            else:
                val = _parse_number_from_text(num_part)
                if val is not None:
                    n = int(val)
                    matched = True
        elif m2:
            action = m2.group(1)
            item_type = m2.group(2)
            num_part = m2.group(3)
            
            if num_part.isdigit():
                n = int(num_part)
                matched = True
            elif num_part in ordinals_map:
                n = ordinals_map[num_part]
                matched = True
            else:
                val = _parse_number_from_text(num_part)
                if val is not None:
                    n = int(val)
                    matched = True
                    
        if matched and n is not None:
            label = "last" if n == -1 else str(n)
            resp = f"{'Opening' if action == 'open' else 'Selecting'} {item_type} {label}"
            self._execute("select_nth_file", f"{n}_{action}", resp)
            return

        # 2c. Check for dynamic drive commands (e.g. "open c drive", "open local disk d", "open drive e", "open c")
        import re
        drive_patterns = [
            r'^open\s+(local disk|disk|drive)\s+([a-z])$',
            r'^open\s+([a-z])\s+(disk|drive)$'
        ]
        for pat in drive_patterns:
            m = re.match(pat, clean_text)
            if m:
                g1, g2 = m.group(1), m.group(2)
                letter = g1.upper() if len(g1.strip()) == 1 else g2.upper()
                path = f"{letter}:\\"
                if os.path.exists(path):
                    self._execute("open_drive", path, f"Opening drive {letter}")
                    return
                    
        # Single letter drive shortcut: "open c", "open d"
        if clean_text.startswith("open ") and len(clean_text) == 6:
            letter = clean_text[5].upper()
            if 'A' <= letter <= 'Z':
                path = f"{letter}:\\"
                if os.path.exists(path):
                    self._execute("open_drive", path, f"Opening drive {letter}")
                    return

        # 2d. Check for folder opening commands
        # E.g. "open folder downloads", "open python folder", "open downloads folder"
        if clean_text.startswith("open folder "):
            folder_name = clean_text[len("open folder "):].strip()
            self._execute("open_custom_folder", folder_name, f"Opening folder {folder_name}")
            return
        elif clean_text.startswith("open ") and clean_text.endswith(" folder"):
            folder_name = clean_text[5:-7].strip()
            self._execute("open_custom_folder", folder_name, f"Opening folder {folder_name}")
            return

        # 2e. Check for folder/drive/explorer closing commands
        # E.g. "close disk d", "close downloads folder", "close drive c", "close downloads"
        if clean_text.startswith("close "):
            target = clean_text[6:].strip()
            exclude_close = {
                "properties", "properties window", "properties dialog", "folder properties", "file properties",
                "dialog", "popup", "menu", "window", "this", "it", "assistant", "the assistant", "program", "app", 
                "application", "calculator", "notepad", "chrome", "edge", "firefox", "brave", "opera", "word", 
                "excel", "powerpoint", "outlook", "teams", "onenote", "steam", "discord", "spotify", "telegram", 
                "whatsapp", "zoom", "nvidia", "obs", "vlc", "vs code", "visual studio", "photoshop", "premiere", 
                "blender", "unity", "epic games"
            }
            if target not in exclude_close:
                # Check if target matches explorer/file explorer
                if target in ("file explorer", "the file explorer", "explorer", "active folder", "active explorer", "folder"):
                    self._execute("close_explorer", "active", "Closing active File Explorer window")
                    return
                elif target in ("all folders", "all explorer windows", "all file explorers", "all file explorer windows"):
                    self._execute("close_explorer", "all", "Closing all File Explorer windows")
                    return
                
                # Check for drive letter pattern, e.g. "disk d", "drive c", "local disk c", "c drive", "d"
                drive_match = re.match(r'^(?:local disk|disk|drive)?\s*([a-z])(?:\s+drive|\s+disk)?$', target)
                if drive_match:
                    letter = drive_match.group(1).upper()
                    self._execute("close_explorer", f"drive:{letter}", f"Closing drive {letter} window")
                    return
                
                # Otherwise, treat as folder name
                folder_name = target
                if folder_name.endswith(" folder"):
                    folder_name = folder_name[:-7].strip()
                self._execute("close_explorer", f"folder:{folder_name}", f"Closing folder {folder_name} window")
                return

        # 3. Check dynamic prefix commands (search, find, type, go to)
        for prefix, action in DYNAMIC_PREFIXES:
            if text.startswith(prefix):
                query = text[len(prefix):].strip()
                if query:
                    self._execute_dynamic(action, query)
                    return

        # 3. Fuzzy: longest matching phrase contained in text
        best_match = None
        best_len = 0
        for phrase, (action_type, arg, response) in VOICE_COMMANDS.items():
            if phrase in text and len(phrase) > best_len:
                best_match = (action_type, arg, response)
                best_len = len(phrase)

        if best_match:
            self._execute(best_match[0], best_match[1], best_match[2])
        else:
            logger.info(f"  No command matched: \"{text}\"")
            speak(f"Sorry, I didn't understand that. Say help to see what I can do.")

    def _execute_dynamic(self, action: str, query: str):
        """Execute dynamic commands that take a query parameter."""
        import pyautogui
        
        if self.state_callback: self.state_callback("speaking")

        if action == "search_smart":
            # Smart search: detect target app from suffix
            target = "current"  # default: search in current window
            for suffix, t in SEARCH_TARGET_SUFFIXES:
                if query.endswith(suffix):
                    query = query[:-len(suffix)].strip()
                    target = t
                    break

            if target == "google":
                speak(f"Searching Google for {query}")
                encoded = urllib.parse.quote_plus(query)
                url = f"https://www.google.com/search?q={encoded}"
                try:
                    subprocess.Popen(f"start {url}", shell=True)
                except Exception as e:
                    logger.error(f"Search failed: {e}")

            elif target == "explorer":
                speak(f"Searching files for {query}")
                try:
                    subprocess.Popen(
                        f'explorer /root,"search-ms:query={query}"',
                        shell=True
                    )
                except Exception as e:
                    logger.error(f"File search failed: {e}")

            elif target == "youtube_music":
                speak(f"Searching YouTube Music for {query}")
                encoded = urllib.parse.quote_plus(query)
                url = f"https://music.youtube.com/search?q={encoded}"
                try:
                    subprocess.Popen(f"start {url}", shell=True)
                except Exception as e:
                    logger.error(f"YouTube Music search failed: {e}")
                    
            elif target == "youtube":
                speak(f"Searching YouTube for {query}")
                encoded = urllib.parse.quote_plus(query)
                url = f"https://www.youtube.com/results?search_query={encoded}"
                try:
                    subprocess.Popen(f"start {url}", shell=True)
                except Exception as e:
                    logger.error(f"YouTube search failed: {e}")

            else:
                # Search in currently active window using Ctrl+E
                # (works in File Explorer, Chrome, Edge, and many apps)
                speak(f"Searching for {query}")
                pyautogui.hotkey('ctrl', 'e')
                time.sleep(0.5)
                # Clear any existing text and type the query
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.1)
                # Use clipboard to paste (supports all characters)
                try:
                    subprocess.run(
                        ['powershell', '-Command',
                         f"Set-Clipboard -Value '{query.replace(chr(39), chr(39)+chr(39))}'"],
                        timeout=5, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.3)
                    pyautogui.press('enter')
                except Exception as e:
                    logger.error(f"Search typing failed: {e}")

        elif action == "search_google":
            speak(f"Searching Google for {query}")
            encoded = urllib.parse.quote_plus(query)
            url = f"https://www.google.com/search?q={encoded}"
            try:
                subprocess.Popen(f"start {url}", shell=True)
            except Exception as e:
                logger.error(f"Search failed: {e}")

        elif action == "play_music":
            is_yt_music = True
            if query.endswith("on youtube music"):
                query = query[:-16].strip()
            elif query.endswith("on youtube"):
                query = query[:-10].strip()
                is_yt_music = False

            speak(f"Playing {query}")
            try:
                import re
                
                query_string = urllib.parse.urlencode({"search_query": query})
                html_content = urllib.request.urlopen("https://www.youtube.com/results?" + query_string)
                search_results = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html_content.read().decode())
                
                if search_results:
                    video_id = search_results[0]
                    if is_yt_music:
                        url = f"https://music.youtube.com/watch?v={video_id}"
                    else:
                        url = f"https://www.youtube.com/watch?v={video_id}"
                    subprocess.Popen(f"start {url}", shell=True)
                else:
                    speak("I couldn't find that song.")
            except Exception as e:
                logger.error(f"Music play failed: {e}")
                speak("I encountered an error trying to play the music.")

        elif action == "find_file":
            speak(f"Searching files for {query}")
            try:
                subprocess.Popen(f'explorer /root,"search-ms:query={query}"', shell=True)
            except Exception as e:
                logger.error(f"File search failed: {e}")

        elif action == "open_file":
            speak(f"Opening file {query}")
            # Use Windows search to find and open the file
            try:
                subprocess.Popen(f'explorer /root,"search-ms:query={query}"', shell=True)
            except Exception as e:
                logger.error(f"Open file failed: {e}")

        elif action == "open_folder":
            speak(f"Opening folder {query}")
            try:
                subprocess.Popen(f'explorer /root,"search-ms:query={query}&crumb=kind:folder"', shell=True)
            except Exception as e:
                logger.error(f"Open folder failed: {e}")

        elif action == "open_url":
            site = query.strip().replace(" ", "")
            if not site.startswith("http"):
                site = f"https://www.{site}.com"
            speak(f"Opening {query}")
            try:
                subprocess.Popen(f"start {site}", shell=True)
            except Exception as e:
                logger.error(f"URL open failed: {e}")

        elif action == "type_text":
            speak(f"Typing {query}")
            pyautogui.typewrite(query, interval=0.03)

        elif action == "calculate":
            # Clean expression
            expr = query.lower()
            on_calc = False
            if "on calculator" in expr:
                expr = expr.replace("on calculator", "").strip()
                on_calc = True
            elif "in calculator" in expr:
                expr = expr.replace("in calculator", "").strip()
                on_calc = True

            # Word replacements for spoken math operators
            word_map = {
                "plus": "+", "and": "+",
                "minus": "-", "subtract": "-",
                "times": "*", "multiplied by": "*", "multiply": "*", "into": "*", "x": "*",
                "divided by": "/", "divide": "/", "by": "/"
            }
            for word, op in word_map.items():
                expr = expr.replace(word, op)

            # Filter safe characters for evaluation
            safe_chars = set("0123456789+-*/(). ")
            expr_cleaned = "".join(c for c in expr if c in safe_chars).strip()

            try:
                if expr_cleaned:
                    # Evaluate mathematical expression safely
                    result = eval(expr_cleaned, {"__builtins__": None}, {})
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    
                    spoken_expr = expr_cleaned.replace("*", " times ").replace("/", " divided by ")
                    speak(f"The result of {spoken_expr} is {result}")
                    
                    if on_calc:
                        # Focus existing calculator window if open; do not spawn a new window if one exists.
                        import pygetwindow as gw
                        calc_win = None
                        try:
                            # Walk through all windows to find any containing "calculator" (case-insensitive) in title
                            for win in gw.getAllWindows():
                                if "calculator" in win.title.lower():
                                    calc_win = win
                                    break
                        except Exception as win_err:
                            logger.warning(f"Could not search windows with pygetwindow: {win_err}")

                        if calc_win:
                            try:
                                calc_win.restore()
                                calc_win.activate()
                                time.sleep(0.3)  # Wait for window focus shift
                                logger.info(f"✓ Focused existing calculator window: '{calc_win.title}'")
                            except Exception as focus_err:
                                logger.warning(f"Could not focus existing calculator: {focus_err}. Spawning a new one.")
                                subprocess.Popen("calc", shell=True)
                                time.sleep(0.8)
                        else:
                            subprocess.Popen("calc", shell=True)
                            time.sleep(0.8) # Wait for it to focus

                        pyautogui.write(f"{expr_cleaned}=", interval=0.05)
                else:
                    speak("Sorry, I could not extract a valid mathematical expression.")
            except Exception as e:
                logger.error(f"Calculation error: {e}")
                speak("Sorry, I had trouble calculating that. Make sure it is a valid mathematical equation.")

        elif action == "close_app":
            app_name = query.lower().strip()
            
            # Common application process mappings on Windows
            app_process_map = {
                "calculator": ["CalculatorApp.exe", "calc.exe"],
                "notepad": ["notepad.exe"],
                "browser": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"],
                "chrome": ["chrome.exe"],
                "edge": ["msedge.exe"],
                "firefox": ["firefox.exe"],
                "brave": ["brave.exe"],
                "opera": ["opera.exe"],
                "word": ["winword.exe"],
                "excel": ["excel.exe"],
                "powerpoint": ["powerpnt.exe"],
                "outlook": ["outlook.exe"],
                "onenote": ["onenote.exe"],
                "teams": ["teams.exe", "msteams.exe"],
                "steam": ["steam.exe"],
                "discord": ["discord.exe"],
                "spotify": ["spotify.exe"],
                "telegram": ["telegram.exe"],
                "whatsapp": ["whatsapp.exe"],
                "zoom": ["zoom.exe"],
                "nvidia": ["nvcontainer.exe", "nvidia app.exe"],
                "obs": ["obs64.exe", "obs.exe"],
                "vlc": ["vlc.exe"],
                "vs code": ["code.exe"],
                "code": ["code.exe"],
                "visual studio": ["devenv.exe"],
                "photoshop": ["photoshop.exe"],
                "premiere": ["premiere.exe"],
                "blender": ["blender.exe"],
                "unity": ["unity.exe"],
                "epic games": ["epicgameslauncher.exe"],
                "terminal": ["windowsterminal.exe", "wt.exe"],
                "command prompt": ["cmd.exe"],
                "powershell": ["powershell.exe"],
                "paint": ["mspaint.exe"],
                "snipping tool": ["snippingtool.exe"],
                "settings": ["systemsettings.exe"],
                "explorer": ["explorer.exe"],
                "file explorer": ["explorer.exe"],
            }

            speak(f"Closing {query}")

            # 1. First, search and close via window title using pygetwindow
            import pygetwindow as gw
            closed_via_window = False
            try:
                for win in gw.getAllWindows():
                    if app_name in win.title.lower():
                        win.close()
                        closed_via_window = True
                        logger.info(f"✓ Closed window gracefully via pygetwindow: '{win.title}'")
            except Exception as e:
                logger.warning(f"Could not close window gracefully: {e}")

            # 2. Also taskkill matching processes to be thorough
            executables = app_process_map.get(app_name, [f"{app_name}.exe"])
            
            # Protection guard: never close explorer.exe unless explicitly stated as "explorer" or "file explorer"
            if "explorer" in app_name and app_name not in ["explorer", "file explorer"]:
                pass
            else:
                for exe in executables:
                    if exe.lower() == "explorer.exe":
                        continue
                    try:
                        subprocess.run(f"taskkill /f /im {exe}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass

        elif action == "open_app":
            app_name = query.strip()
            speak(f"Opening {app_name}")
            import pyautogui
            try:
                pyautogui.press('win')
                time.sleep(0.8)
                pyautogui.write(app_name, interval=0.03)
                time.sleep(1.0)
                pyautogui.press('enter')
            except Exception as e:
                logger.error(f"Failed to dynamically open application via Start Menu search: {e}")

        elif action == "connect_wifi":
            network_name = query.strip()
            speak(f"Connecting to {network_name}")
            try:
                # First, try to find the best matching network from available list
                result = subprocess.run(
                    'netsh wlan show networks',
                    shell=True, capture_output=True, text=True, timeout=10
                )
                available = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('SSID') and ':' in line:
                        ssid = line.split(':', 1)[1].strip()
                        if ssid:  # Skip empty SSIDs
                            available.append(ssid)

                # Try exact match first, then fuzzy match
                matched_ssid = None
                for ssid in available:
                    if ssid.lower() == network_name.lower():
                        matched_ssid = ssid
                        break
                if not matched_ssid:
                    for ssid in available:
                        if network_name.lower() in ssid.lower() or ssid.lower() in network_name.lower():
                            matched_ssid = ssid
                            break

                if matched_ssid:
                    # Check if a saved profile exists for this network
                    profile_check = subprocess.run(
                        f'netsh wlan show profile name="{matched_ssid}"',
                        shell=True, capture_output=True, text=True, timeout=10
                    )
                    if profile_check.returncode == 0:
                        # Profile exists, connect directly
                        connect_result = subprocess.run(
                            f'netsh wlan connect name="{matched_ssid}"',
                            shell=True, capture_output=True, text=True, timeout=15
                        )
                        if 'successfully' in connect_result.stdout.lower() or connect_result.returncode == 0:
                            speak(f"Connected to {matched_ssid}")
                            logger.info(f"  ✓ Connected to Wi-Fi: {matched_ssid}")
                        else:
                            speak(f"I found {matched_ssid} but couldn't connect. It may require a password.")
                            logger.warning(f"  Wi-Fi connect failed: {connect_result.stdout} {connect_result.stderr}")
                    else:
                        # No saved profile — open Windows Wi-Fi settings panel
                        speak(f"I found {matched_ssid} but it requires a password. Opening Wi-Fi settings so you can connect.")
                        subprocess.Popen('start ms-settings:network-wifi', shell=True)
                else:
                    # Network not found in scan
                    if available:
                        # Suggest similar names
                        top_names = available[:5]
                        names_str = ", ".join(top_names)
                        speak(f"I couldn't find a network called {network_name}. Available networks are: {names_str}")
                    else:
                        speak(f"I couldn't find any Wi-Fi networks. Make sure Wi-Fi is turned on.")
            except Exception as e:
                logger.error(f"Wi-Fi connect failed: {e}")
                speak(f"Sorry, I had trouble connecting to {network_name}.")

        elif action == "set_sensitivity":
            # Extract number from query like "400" or "set sensitivity to 400"
            val = _parse_number_from_text(query)
            if val is not None:
                val = int(val)
                val = max(50, min(4000, val))  # Clamp to reasonable range
                attention.mic_sensitivity = val
                speak(f"Microphone sensitivity set to {val}")
                logger.info(f"  Mic sensitivity changed to {val}")
            else:
                speak(f"Sorry, I couldn't understand the sensitivity value. Please say a number between 50 and 4000.")

        elif action == "set_voice_speed":
            val = _parse_number_from_text(query)
            if val is not None:
                val = float(val)
                val = max(0.5, min(3.0, val))  # Clamp to reasonable range
                attention.voice_speed = val
                speak(f"Voice speed set to {val}")
                logger.info(f"  Voice speed changed to {val}")
            else:
                speak(f"Sorry, I couldn't understand the speed value. Please say a number between 0.5 and 3.")

        elif action == "set_volume":
            val = _parse_number_from_text(query)
            if val is not None:
                val = int(val)
                val = max(0, min(100, val))
                try:
                    subprocess.run(
                        ['powershell', '-Command',
                         f'(New-Object -ComObject WScript.Shell).SendKeys([char]173); '
                         f'$wshell = New-Object -ComObject WScript.Shell; '
                         f'1..50 | ForEach-Object {{ $wshell.SendKeys([char]174) }}; '
                         f'1..{val // 2} | ForEach-Object {{ $wshell.SendKeys([char]175) }}'],
                        timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    speak(f"Volume set to approximately {val} percent")
                except Exception as e:
                    logger.error(f"Volume set failed: {e}")
                    speak("Sorry, I couldn't adjust the volume.")
            else:
                speak("Please say a volume level between 0 and 100.")

        elif action == "set_brightness":
            val = _parse_number_from_text(query)
            if val is not None:
                val = int(val)
                val = max(0, min(100, val))
                try:
                    subprocess.run(
                        ['powershell', '-Command',
                         f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})'],
                        timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    speak(f"Brightness set to {val} percent")
                except Exception as e:
                    logger.error(f"Brightness set failed: {e}")
                    speak("Sorry, I couldn't adjust the brightness. This may not work on desktop monitors.")
            else:
                speak("Please say a brightness level between 0 and 100.")

        elif action == "close_explorer":
            self._execute("close_explorer", query, None)

        elif action == "task_view":
            self._execute("task_view", query, None)

    def _get_active_explorer_window(self):
        """Find the active or top-most visible File Explorer window and document using Shell.Application."""
        import win32gui
        import win32com.client
        import pythoncom
        
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
            
        active_hwnd = win32gui.GetForegroundWindow()
        is_explorer = False
        if active_hwnd:
            class_name = win32gui.GetClassName(active_hwnd)
            if class_name in ("CabinetWClass", "ExploreWClass"):
                is_explorer = True
                
        # Fallback: Find top-most visible File Explorer window if current foreground is not Explorer
        if not is_explorer:
            explorer_hwnds = []
            def enum_cb(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    cls = win32gui.GetClassName(hwnd)
                    if cls in ("CabinetWClass", "ExploreWClass"):
                        explorer_hwnds.append(hwnd)
            win32gui.EnumWindows(enum_cb, None)
            
            if explorer_hwnds:
                active_hwnd = explorer_hwnds[0]
                is_explorer = True
                # Try to bring it to foreground
                try:
                    win32gui.ShowWindow(active_hwnd, 5) # SW_SHOW
                    win32gui.SetForegroundWindow(active_hwnd)
                except Exception:
                    pass
            else:
                return None, None

        try:
            active_title = win32gui.GetWindowText(active_hwnd)
            target_tab_name = None
            if " - File Explorer" in active_title:
                tab_part = active_title.split(" - File Explorer")[0]
                if " and " in tab_part:
                    right_part = tab_part.split(" and ")[-1]
                    if "more tab" in right_part:
                        target_tab_name = tab_part.rsplit(" and ", 1)[0]
                if not target_tab_name:
                    target_tab_name = tab_part
            
            shell = win32com.client.Dispatch("Shell.Application")
            windows = shell.Windows()
            matching_tabs = []
            for i in range(windows.Count):
                w = windows.Item(i)
                try:
                    if w.hwnd == active_hwnd:
                        matching_tabs.append(w)
                except Exception:
                    continue
                    
            if not matching_tabs:
                return None, None
                
            if len(matching_tabs) == 1:
                return matching_tabs[0], matching_tabs[0].Document
                
            if target_tab_name:
                for w in matching_tabs:
                    if w.LocationName.lower() == target_tab_name.lower():
                        return w, w.Document
                        
            return matching_tabs[0], matching_tabs[0].Document
        except Exception as e:
            logger.error(f"Error in _get_active_explorer_window: {e}")
            
        return None, None

    def _select_file_in_explorer(self, pos: str, action: str):
        """Deterministic COM-based file selection inside active File Explorer."""
        import pythoncom
        import time
        import pyautogui
        
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
            
        try:
            window, doc = self._get_active_explorer_window()
            if not doc:
                logger.warning("No active File Explorer window found via COM.")
                return False
                
            folder = doc.Folder
            items = folder.Items()
            count = items.Count
            if count == 0:
                logger.info("No items in the folder.")
                return False
                
            items_list = [items.Item(i) for i in range(count)]
            target_idx = -1
            
            if pos == "next" or pos == "prev":
                focused = doc.FocusedItem
                curr_idx = -1
                if focused:
                    focused_path = focused.Path.lower()
                    for idx, it in enumerate(items_list):
                        if it.Path.lower() == focused_path:
                            curr_idx = idx
                            break
                            
                if curr_idx == -1:
                    target_idx = 0 if pos == "next" else count - 1
                else:
                    target_idx = min(count - 1, curr_idx + 1) if pos == "next" else max(0, curr_idx - 1)
            elif pos == "-1":
                target_idx = count - 1
            else:
                try:
                    n = int(pos)
                    target_idx = max(1, min(count, n)) - 1
                except ValueError:
                    logger.error(f"Invalid position argument: {pos}")
                    return False
                    
            if 0 <= target_idx < count:
                target_item = items_list[target_idx]
                logger.info(f"Selecting item {target_idx}: '{target_item.Name}'")
                # 1 = SVSI_SELECT, 4 = SVSI_DESELECTOTHERS, 8 = SVSI_ENSUREVISIBLE, 16 = SVSI_FOCUS
                doc.SelectItem(target_item, 29)
                time.sleep(0.1)
                
                if action == "open":
                    pyautogui.press('enter')
                return True
        except Exception as e:
            logger.error(f"Error in _select_file_in_explorer: {e}")
            
        return False

    def _deselect_items_in_explorer(self, target_type: str = "selected") -> bool:
        """
        Deselects item(s) in the active Explorer window using Shell.Application COM interface.
        If target_type is 'selected', we deselect all currently selected items.
        If target_type is 'all', we deselect every item.
        """
        import pythoncom
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
            
        try:
            window, doc = self._get_active_explorer_window()
            if not doc:
                logger.warning("No active File Explorer window found via COM.")
                return False
                
            if target_type == "selected":
                selected_items = doc.SelectedItems()
                for i in range(selected_items.Count):
                    doc.SelectItem(selected_items.Item(i), 0)  # 0 = deselect
            else:
                try:
                    doc.SelectItem(None, 4)  # 4 = SVSI_DESELECTOTHERS with None deselects all
                except Exception:
                    pass
                # Fallback: deselect any remaining selected items
                selected_items = doc.SelectedItems()
                for i in range(selected_items.Count):
                    try:
                        doc.SelectItem(selected_items.Item(i), 0)
                    except Exception:
                        pass
            return True
        except Exception as e:
            logger.error(f"Error in _deselect_items_in_explorer: {e}")
        return False

    def _execute(self, action_type: str, arg: str, response: str):
        """Execute a predefined action."""
        import pyautogui
        
        if action_type == "ui_command":
            if self.ui_callback:
                speak(response)
                self.ui_callback(arg)
            else:
                speak("UI callback is not registered.")
            return

        if action_type == "launch":
            speak(response)
            try:
                subprocess.Popen(arg, shell=True)
            except Exception as e:
                logger.error(f"Launch failed: {e}")
                speak("Sorry, I couldn't open that application.")

        elif action_type == "hotkey":
            speak(response)
            keys = arg.split("+")
            try:
                pyautogui.hotkey(*keys)
            except Exception as e:
                logger.error(f"Hotkey failed: {e}")

        elif action_type == "mouse_click":
            speak(response)
            if arg == "left":
                pyautogui.click()
            elif arg == "right":
                pyautogui.rightClick()
            elif arg == "double":
                pyautogui.doubleClick()

        elif action_type == "click_nth_link":
            speak(response)
            n = int(arg)
            # Click the nth search result by calculated screen position.
            # Google search results have a predictable layout:
            #   - Results start at ~22% from top of screen
            #   - Each result block is ~10% of screen height
            #   - Titles are at ~35% from left edge
            screen_w, screen_h = pyautogui.size()

            if n == -1:
                # "Last link" — click near the bottom of visible results
                x = int(screen_w * 0.35)
                y = int(screen_h * 0.80)
            else:
                x = int(screen_w * 0.35)
                y_start = int(screen_h * 0.22)
                y_step = int(screen_h * 0.10)
                y = y_start + (n - 1) * y_step

            logger.info(f"  Clicking at ({x}, {y}) for result #{n}")
            pyautogui.click(x, y)

        elif action_type == "start_menu":
            # Open apps via Windows Start Menu search
            speak(response)
            pyautogui.press('win')
            time.sleep(0.8)
            pyautogui.write(arg, interval=0.03)
            time.sleep(1.0)
            pyautogui.press('enter')

        elif action_type == "select_nth_file":
            speak(response)
            parts = arg.split('_')
            pos = parts[0]      # "1", "2", "-1", "next", "prev"
            action = parts[1]   # "open" or "select"

            success = self._select_file_in_explorer(pos, action)
            if not success:
                logger.warning("COM-based file selection failed, falling back to keyboard sequence.")
                # Fallback to legacy F6 cycling
                pyautogui.press('F6')
                time.sleep(0.3)
                pyautogui.press('F6')
                time.sleep(0.3)

                if pos == "next":
                    pyautogui.press('down')
                elif pos == "prev":
                    pyautogui.press('up')
                elif pos == "-1":
                    pyautogui.press('end')
                else:
                    try:
                        n = int(pos)
                        pyautogui.press('home')
                        time.sleep(0.2)
                        for _ in range(n - 1):
                            pyautogui.press('down')
                            time.sleep(0.1)
                    except ValueError:
                        pass

                time.sleep(0.3)

                if action == "open":
                    pyautogui.press('enter')
                    time.sleep(0.3)
                    pyautogui.press('enter')

        elif action_type == "deselect_item":
            speak(response)
            success = self._deselect_items_in_explorer(arg)
            if not success:
                logger.warning("COM-based deselection failed, falling back to keyboard emulation.")
                # Keyboard fallback: hit escape to clear selection
                pyautogui.press('esc')

        elif action_type == "scroll":
            speak(response)
            parts = arg.split("_")
            direction = parts[0]
            amount = int(parts[1]) if len(parts) > 1 else 3
            if direction == "up":
                pyautogui.scroll(amount)
            elif direction == "down":
                pyautogui.scroll(-amount)
            elif direction == "left":
                pyautogui.hscroll(-amount)
            elif direction == "right":
                pyautogui.hscroll(amount)

        elif action_type == "nav":
            speak(response)
            url = f"http://localhost:7891/{arg}"
            try:
                with urllib.request.urlopen(url, timeout=0.5):
                    pass
            except urllib.error.URLError:
                pass

        elif action_type == "help":
            speak(
                "I'm Jack, your voice assistant. Here's what I can do. "
                "Say open followed by an app name, like open browser or open calculator. "
                "Say search for, followed by what you want, to search Google. "
                "Say find file or open file, to search in file explorer. "
                "Say go to, followed by a website name, like go to youtube. "
                "I can navigate tabs with next tab, previous tab, close tab, new tab. "
                "I can scroll up, scroll down, page up, page down, go to top or bottom. "
                "I can go back, go forward, refresh the page. "
                "Say click or click here to click at the cursor position. "
                "Say click first link, click second link to click links on a page. "
                "I can also take screenshots, switch windows, and control volume. "
                "Say go to sleep to pause me. Say hey Jack or wake up to activate me again."
            )

        elif action_type == "tell_time":
            from datetime import datetime
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            speak(f"The current time is {time_str}")

        elif action_type == "tell_date":
            from datetime import datetime
            now = datetime.now()
            date_str = now.strftime("%B %d, %Y")
            speak(f"Today's date is {date_str}")

        elif action_type == "tell_day":
            from datetime import datetime
            now = datetime.now()
            day_str = now.strftime("%A, %B %d, %Y")
            speak(f"Today is {day_str}")

        elif action_type == "battery":
            try:
                import psutil
                battery = psutil.sensors_battery()
                if battery:
                    pct = battery.percent
                    plugged = "plugged in" if battery.power_plugged else "on battery"
                    if battery.secsleft > 0 and not battery.power_plugged:
                        mins = battery.secsleft // 60
                        hrs = mins // 60
                        mins = mins % 60
                        speak(f"Battery is at {pct} percent, {plugged}. About {hrs} hours and {mins} minutes remaining.")
                    else:
                        speak(f"Battery is at {pct} percent, {plugged}.")
                else:
                    speak("I couldn't detect a battery. This might be a desktop computer.")
            except ImportError:
                speak("Battery monitoring is not available. The psutil package is required.")
            except Exception as e:
                logger.error(f"Battery check failed: {e}")
                speak("Sorry, I couldn't check the battery status.")

        elif action_type == "power":
            if arg == "shutdown":
                speak(response)
                try:
                    subprocess.Popen("shutdown /s /t 10", shell=True)
                except Exception as e:
                    logger.error(f"Shutdown failed: {e}")
            elif arg == "restart":
                speak(response)
                try:
                    subprocess.Popen("shutdown /r /t 10", shell=True)
                except Exception as e:
                    logger.error(f"Restart failed: {e}")
            elif arg == "sleep_pc":
                speak(response)
                try:
                    subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
                except Exception as e:
                    logger.error(f"Sleep failed: {e}")
            elif arg == "cancel":
                speak(response)
                try:
                    subprocess.Popen("shutdown /a", shell=True)
                except Exception as e:
                    logger.error(f"Cancel shutdown failed: {e}")

        elif action_type == "wifi":
            speak(response)
            state = "enabled" if arg == "on" else "disabled"
            try:
                subprocess.run(
                    f'netsh interface set interface "Wi-Fi" {state}',
                    shell=True, timeout=10,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception as e:
                logger.error(f"Wi-Fi toggle failed: {e}")
                speak(f"Sorry, I couldn't turn {'on' if arg == 'on' else 'off'} the Wi-Fi.")

        elif action_type == "list_wifi":
            speak("Scanning for Wi-Fi networks...")
            try:
                result = subprocess.run(
                    'netsh wlan show networks',
                    shell=True, capture_output=True, text=True, timeout=10
                )
                networks = []
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('SSID') and ':' in line:
                        ssid = line.split(':', 1)[1].strip()
                        if ssid:
                            networks.append(ssid)

                if networks:
                    # Deduplicate while preserving order
                    seen = set()
                    unique = []
                    for n in networks:
                        if n.lower() not in seen:
                            seen.add(n.lower())
                            unique.append(n)

                    count = len(unique)
                    if count <= 5:
                        names = ", ".join(unique)
                        speak(f"I found {count} networks: {names}. Say connect to wifi followed by the network name to connect.")
                    else:
                        top5 = ", ".join(unique[:5])
                        speak(f"I found {count} networks. The top ones are: {top5}. Say connect to wifi followed by the network name.")
                    logger.info(f"  Wi-Fi scan found {count} networks: {unique}")
                else:
                    speak("I couldn't find any Wi-Fi networks. Make sure Wi-Fi is enabled.")
            except Exception as e:
                logger.error(f"Wi-Fi scan failed: {e}")
                speak("Sorry, I couldn't scan for Wi-Fi networks.")

        elif action_type == "disconnect_wifi":
            speak(response)
            try:
                result = subprocess.run(
                    'netsh wlan disconnect',
                    shell=True, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    logger.info("  ✓ Disconnected from Wi-Fi")
                else:
                    speak("I couldn't disconnect. You may not be connected to any network.")
            except Exception as e:
                logger.error(f"Wi-Fi disconnect failed: {e}")
                speak("Sorry, I couldn't disconnect from Wi-Fi.")

        elif action_type == "brightness":
            speak(response)
            try:
                if arg == "max":
                    level = 100
                elif arg == "min":
                    level = 10
                elif arg == "up":
                    level = None  # Will increase by 20
                elif arg == "down":
                    level = None  # Will decrease by 20
                else:
                    level = 50

                if level is not None:
                    subprocess.run(
                        ['powershell', '-Command',
                         f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})'],
                        timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                else:
                    # Get current brightness and adjust
                    delta = 20 if arg == "up" else -20
                    subprocess.run(
                        ['powershell', '-Command',
                         f'$b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness; '
                         f'$n = [Math]::Max(0, [Math]::Min(100, $b + {delta})); '
                         f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,$n)'],
                        timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
            except Exception as e:
                logger.error(f"Brightness control failed: {e}")
                speak("Sorry, I couldn't adjust the brightness.")

        elif action_type == "sleep":
            speak(response)
            self._state = STATE_SLEEPING
            logger.info("  Jack entering sleep mode")

        elif action_type == "stop_assistant":
            speak(response)
            if self.ui_callback:
                self.ui_callback("exit_app")
            self.stop()

        elif action_type == "yt_music":
            """Focus the YouTube Music browser tab and send the appropriate shortcut."""
            import pygetwindow as gw

            # YouTube Music shortcuts:
            #   k / Space = play/pause   Shift+N = next   Shift+P = prev
            #   m = mute   Up/Down = volume   Shift+L = like   Shift+D = dislike
            shortcut_map = {
                "play_pause": ("k",),
                "next":       ("shift", "n"),
                "prev":       ("shift", "p"),
                "mute":       ("m",),
                "vol_up":     ("up",),
                "vol_down":   ("down",),
                "like":       ("shift", "l"),
                "dislike":    ("shift", "d"),
                "shuffle":    ("shift", "s"),
            }

            # Find a browser window whose title contains YouTube Music
            yt_win = None
            try:
                for win in gw.getAllWindows():
                    title = win.title.lower()
                    if "youtube music" in title or "music.youtube" in title:
                        yt_win = win
                        break
            except Exception as e:
                logger.warning(f"  pygetwindow search failed: {e}")

            if yt_win is None:
                speak("I couldn't find YouTube Music. Opening it now.")
                try:
                    subprocess.Popen("start https://music.youtube.com", shell=True)
                except Exception:
                    pass
                return

            # Activate the window
            try:
                yt_win.restore()
                yt_win.activate()
                time.sleep(0.4)   # let the OS finish focusing
            except Exception as e:
                logger.warning(f"  Could not activate YouTube Music window: {e}")

            speak(response)
            keys = shortcut_map.get(arg)
            if keys:
                try:
                    if len(keys) == 1:
                        pyautogui.press(keys[0])
                    else:
                        pyautogui.hotkey(*keys)
                    logger.info(f"  YouTube Music: sent {keys}")
                except Exception as e:
                    logger.error(f"  YouTube Music hotkey error: {e}")
            else:
                logger.warning(f"  Unknown yt_music action: {arg}")

        elif action_type == "launch_gaze":
            # Check if active gaze tracker thread already exists
            if self.gaze_tracker and self.gaze_tracker.is_alive():
                speak("Gaze tracking is already active.")
            else:
                speak(response)
                def run_gaze():
                    try:
                        from src.gaze_tracker import GazeTracker
                        tracker = GazeTracker(camera_id=0, smoothing=0.85, show_preview=True, gain=1.6)
                        tracker.start()
                        self.gaze_tracker = tracker
                    except Exception as err:
                        logger.error(f"Gaze Tracker launch failed: {err}")
                
                t = threading.Thread(target=run_gaze, daemon=True, name="GazeTrackerVoice")
                t.start()
                logger.info("  ✅ Dynamic Launcher: Gaze Tracker spawned via voice!")

        elif action_type == "stop_gaze":
            # Check if gaze tracker instance exists and is running
            if self.gaze_tracker and self.gaze_tracker.is_alive():
                speak(response)
                try:
                    self.gaze_tracker.stop()
                except Exception as err:
                    logger.error(f"Failed to stop gaze tracking: {err}")
            else:
                speak("Gaze tracking is not running.")

        elif action_type == "take_screenshot":
            speak(response)
            try:
                pic_dir = os.path.join(os.path.expanduser("~"), "Pictures")
                if not os.path.exists(pic_dir):
                    os.makedirs(pic_dir, exist_ok=True)
                path = os.path.join(pic_dir, f"Screenshot_{int(time.time())}.png")
                pyautogui.screenshot(path)
                logger.info(f"  Screenshot saved to {path}")
                speak("Screenshot taken and saved to Pictures folder")
            except Exception as e:
                logger.error(f"Screenshot failed: {e}")
                speak("Sorry, I could not capture the screen.")

        elif action_type == "lock_pc":
            speak(response)
            try:
                subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
            except Exception as e:
                logger.error(f"Lock PC failed: {e}")
                speak("Sorry, I could not lock the computer.")

        elif action_type == "mute_unmute":
            speak(response)
            try:
                pyautogui.press('volumemute')
            except Exception as e:
                logger.error(f"Mute/Unmute failed: {e}")

        elif action_type == "minimize_all":
            speak(response)
            try:
                pyautogui.hotkey('win', 'd')
            except Exception as e:
                logger.error(f"Minimize all failed: {e}")

        elif action_type == "maximize":
            speak(response)
            try:
                pyautogui.hotkey('win', 'up')
            except Exception as e:
                logger.error(f"Maximize failed: {e}")

        elif action_type == "open_drive":
            speak(response)
            try:
                subprocess.Popen(f'explorer "{arg}"', shell=True)
            except Exception as e:
                logger.error(f"Open drive failed: {e}")
                speak(f"Sorry, I couldn't open drive {arg}")

        elif action_type == "open_custom_folder":
            folder_name = arg.lower().strip()
            
            # Check drive letter
            import re
            drive_match = re.match(r'^(local disk|disk|drive)?\s*([a-z])\s*(disk|drive)?$', folder_name)
            if drive_match:
                letter = drive_match.group(2).upper()
                path = f"{letter}:\\"
                if os.path.exists(path):
                    speak(f"Opening drive {letter}")
                    subprocess.Popen(f'explorer "{path}"', shell=True)
                    return
            
            # Check standard folders
            standards = {
                "downloads": "Downloads",
                "download": "Downloads",
                "documents": "Documents",
                "document": "Documents",
                "pictures": "Pictures",
                "picture": "Pictures",
                "music": "Music",
                "videos": "Videos",
                "video": "Videos",
                "desktop": "Desktop"
            }
            if folder_name in standards:
                target = standards[folder_name]
                path = os.path.join(os.path.expanduser("~"), target)
                if os.path.exists(path):
                    speak(f"Opening {target} folder")
                    subprocess.Popen(f'explorer "{path}"', shell=True)
                    return
            
            # Check user profile subdirectories
            user_profile = os.path.expanduser("~")
            found_dir = None
            try:
                for item in os.listdir(user_profile):
                    item_path = os.path.join(user_profile, item)
                    if os.path.isdir(item_path) and item.lower() == folder_name:
                        found_dir = item_path
                        break
            except Exception:
                pass
                
            if found_dir:
                speak(f"Opening folder {os.path.basename(found_dir)}")
                subprocess.Popen(f'explorer "{found_dir}"', shell=True)
            else:
                speak(f"Searching for folder {arg}")
                subprocess.Popen(f'explorer /root,"search-ms:query={arg}&crumb=kind:folder"', shell=True)

        elif action_type == "close_properties":
            speak(response)
            try:
                import win32gui
                import win32con
                
                def enum_cb(hwnd, extra):
                    title = win32gui.GetWindowText(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    if "properties" in title.lower() and class_name == "#32770":
                        logger.info(f"Closing properties window: '{title}' (HWND: {hwnd})")
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                
                win32gui.EnumWindows(enum_cb, None)
            except Exception as e:
                logger.error(f"Failed to close properties window: {e}")

        elif action_type == "close_explorer":
            if response:
                speak(response)
            target_type = arg.strip() if arg else "active"
            try:
                import pythoncom
                import win32com.client
                import win32gui
                import win32con
                
                try:
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                
                shell = win32com.client.Dispatch("Shell.Application")
                windows = shell.Windows()
                
                if target_type == "active":
                    active_hwnd = win32gui.GetForegroundWindow()
                    if active_hwnd:
                        class_name = win32gui.GetClassName(active_hwnd)
                        if class_name in ("CabinetWClass", "ExploreWClass"):
                            win32gui.PostMessage(active_hwnd, win32con.WM_CLOSE, 0, 0)
                            logger.info("  ✓ Closed active File Explorer window.")
                elif target_type == "all":
                    count = 0
                    for i in range(windows.Count):
                        w = windows.Item(i)
                        try:
                            class_name = win32gui.GetClassName(w.hwnd)
                            if class_name in ("CabinetWClass", "ExploreWClass"):
                                w.Quit()
                                count += 1
                        except Exception:
                            pass
                    logger.info(f"  ✓ Closed {count} File Explorer window(s).")
                elif target_type.startswith("drive:"):
                    letter = target_type.split(":", 1)[1].upper()
                    count = 0
                    for i in range(windows.Count):
                        w = windows.Item(i)
                        try:
                            path = w.Document.Folder.Self.Path
                            if path.upper().startswith(letter + ":"):
                                w.Quit()
                                count += 1
                        except Exception:
                            try:
                                if letter in w.LocationName.upper() or letter in w.LocationURL.upper():
                                    w.Quit()
                                    count += 1
                            except Exception:
                                pass
                    logger.info(f"  ✓ Closed {count} File Explorer window(s) matching drive {letter}.")
                elif target_type.startswith("folder:"):
                    folder_name = target_type.split(":", 1)[1].lower()
                    count = 0
                    for i in range(windows.Count):
                        w = windows.Item(i)
                        try:
                            path = w.Document.Folder.Self.Path
                            if os.path.basename(path).lower() == folder_name or folder_name in path.lower():
                                w.Quit()
                                count += 1
                        except Exception:
                            try:
                                if folder_name in w.LocationName.lower():
                                    w.Quit()
                                    count += 1
                            except Exception:
                                pass
                    logger.info(f"  ✓ Closed {count} File Explorer window(s) matching folder '{folder_name}'.")
            except Exception as e:
                logger.error(f"Failed to close explorer windows: {e}")

        elif action_type == "task_view":
            if response:
                speak(response)
            sub_action = arg.strip().lower() if arg else "open"
            try:
                import pyautogui
                if sub_action == "open":
                    pyautogui.hotkey('win', 'tab')
                elif sub_action == "close":
                    pyautogui.press('escape')
                elif sub_action == "select":
                    pyautogui.press('enter')
                elif sub_action == "next":
                    pyautogui.press('right')
                elif sub_action == "prev":
                    pyautogui.press('left')
                elif sub_action == "up":
                    pyautogui.press('up')
                elif sub_action == "down":
                    pyautogui.press('down')
            except Exception as e:
                logger.error(f"Task view action '{sub_action}' failed: {e}")



# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Jack -- Interactive Voice Assistant"
    )
    parser.add_argument("--no-attention", action="store_true",
                        help="Disable attention gating (always listen)")
    args = parser.parse_args()

    assistant = VoiceAssistant(
        require_attention=not args.no_attention,
    )
    assistant.start()

    logger.info("Jack assistant running. Press Ctrl+C to stop.")
    try:
        while assistant.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        assistant.stop()
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
