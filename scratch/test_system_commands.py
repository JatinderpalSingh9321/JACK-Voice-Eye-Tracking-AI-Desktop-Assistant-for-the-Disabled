import sys
import os
import time
from unittest.mock import MagicMock, patch

# Add project root to python path explicitly
sys.path.append("d:/8th sem/bio2/biot")

from src.voice_assistant import VoiceAssistant, VOICE_COMMANDS

def test_static_mappings():
    print("Testing static VOICE_COMMANDS registrations:")
    
    expected_mappings = {
        "open task view":          ("task_view", "open", "Opening task view"),
        "show task view":          ("task_view", "open", "Opening task view"),
        "close task view":         ("task_view", "close", "Closing task view"),
        "select app":              ("task_view", "select", "Selecting application"),
        "next app":                ("task_view", "next", "Moving to next application"),
        "previous app":            ("task_view", "prev", "Moving to previous application"),
        "select app up":           ("task_view", "up", "Moving focus up"),
        "select app down":         ("task_view", "down", "Moving focus down"),
        
        "close file explorer":     ("close_explorer", "active", "Closing file explorer"),
        "close the file explorer": ("close_explorer", "active", "Closing the file explorer"),
        "close explorer":          ("close_explorer", "active", "Closing explorer"),
        "close active folder":     ("close_explorer", "active", "Closing active folder"),
        "close open folders":      ("close_explorer", "all", "Closing open folders"),
        "close all folders":       ("close_explorer", "all", "Closing all folders"),
    }
    
    for cmd, expected in expected_mappings.items():
        assert cmd in VOICE_COMMANDS, f"Command '{cmd}' not found in VOICE_COMMANDS"
        actual = VOICE_COMMANDS[cmd]
        assert actual == expected, f"For '{cmd}', expected {expected}, got {actual}"
        print(f"  OK: '{cmd}' mapped to {actual}")
    print("Static voice command checks passed!\n")

def test_dynamic_closing_parsing():
    print("Testing dynamic close voice command parsing:")
    assistant = VoiceAssistant(require_attention=False)
    assistant._execute = MagicMock()
    assistant._execute_dynamic = MagicMock()
    
    close_cases = [
        # (input_text, expected_is_dynamic, expected_action, expected_arg)
        ("close disk d", False, "close_explorer", "drive:D"),
        ("close drive c", False, "close_explorer", "drive:C"),
        ("close local disk e", False, "close_explorer", "drive:E"),
        ("close downloads folder", False, "close_explorer", "folder:downloads"),
        ("close python project folder", False, "close_explorer", "folder:python project"),
        ("close desktop", False, "close_explorer", "folder:desktop"),
        ("close file explorer", False, "close_explorer", "active"), # Static command
        ("close calculator", True, "close_app", "calculator"), # Excluded, should fuzzy match close_app via DYNAMIC_PREFIXES
        ("close the assistant", False, "stop_assistant", None), # Excluded, should exact match stop_assistant
    ]
    
    for input_text, is_dynamic, expected_action, expected_arg in close_cases:
        assistant._execute.reset_mock()
        assistant._execute_dynamic.reset_mock()
        
        assistant._process_command(input_text)
        
        if is_dynamic:
            assistant._execute_dynamic.assert_called_once()
            called_args = assistant._execute_dynamic.call_args[0]
            assert called_args[0] == expected_action, f"Expected {expected_action}, got {called_args[0]} for '{input_text}'"
            assert called_args[1] == expected_arg, f"Expected arg '{expected_arg}', got '{called_args[1]}' for '{input_text}'"
            print(f"  OK: '{input_text}' correctly parsed to _execute_dynamic('{expected_action}', '{called_args[1]}')")
        else:
            assistant._execute.assert_called_once()
            called_args = assistant._execute.call_args[0]
            assert called_args[0] == expected_action, f"Expected {expected_action}, got {called_args[0]} for '{input_text}'"
            if expected_arg is not None:
                assert called_args[1] == expected_arg, f"Expected arg '{expected_arg}', got '{called_args[1]}' for '{input_text}'"
            print(f"  OK: '{input_text}' correctly parsed to _execute('{expected_action}', '{called_args[1]}')")
        
    print("Dynamic parsing checks passed!\n")

@patch('pyautogui.hotkey')
@patch('pyautogui.press')
def test_task_view_handler(mock_press, mock_hotkey):
    print("Testing Task View action handler execution:")
    assistant = VoiceAssistant(require_attention=False)
    
    # 1. Open task view
    assistant._execute("task_view", "open", "Opening task view")
    mock_hotkey.assert_called_with('win', 'tab')
    print("  OK: task_view 'open' hotkey triggered")
    
    # 2. Close task view
    mock_press.reset_mock()
    assistant._execute("task_view", "close", "Closing task view")
    mock_press.assert_called_with('escape')
    print("  OK: task_view 'close' press triggered")
    
    # 3. Select app
    mock_press.reset_mock()
    assistant._execute("task_view", "select", "Selecting app")
    mock_press.assert_called_with('enter')
    print("  OK: task_view 'select' press triggered")
    
    # 4. Next/Prev/Up/Down
    for action, key in [("next", "right"), ("prev", "left"), ("up", "up"), ("down", "down")]:
        mock_press.reset_mock()
        assistant._execute("task_view", action, f"Moving {action}")
        mock_press.assert_called_with(key)
        print(f"  OK: task_view '{action}' triggered '{key}' key press")
        
    print("Task view handler checks passed!\n")

if __name__ == "__main__":
    test_static_mappings()
    test_dynamic_closing_parsing()
    test_task_view_handler()
    print("All system command integration tests passed successfully!")
