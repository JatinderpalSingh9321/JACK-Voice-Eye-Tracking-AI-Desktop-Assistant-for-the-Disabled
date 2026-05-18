"""
Local Decision Engine — Maps EOG signals to navigation actions.
Fully offline, no API key required.

Signal types: blink, double_blink, wink_left, wink_right
Actions: open_<item>, go_back, move_next, move_previous, no_action
"""


def decide_action(signal: str, highlighted_item: str) -> str:
    """
    Map a detected EOG signal + current UI state to a navigation action.

    Args:
        signal: One of 'blink', 'double_blink', 'wink_left', 'wink_right'
        highlighted_item: Currently highlighted item in the scanning UI
                          e.g. 'browser', 'folder', 'camera', 'notepad'

    Returns:
        Action string: 'open_<item>', 'go_back', 'move_next', 'move_previous'
    """
    if signal == "blink":
        return f"open_{highlighted_item}"

    if signal == "double_blink":
        return "go_back"

    if signal == "wink_right":
        return "move_next"

    if signal == "wink_left":
        return "move_previous"

    return "no_action"


# ── Action descriptions (for UI display) ──
ACTION_LABELS = {
    "blink":        "SELECT (blink)",
    "double_blink": "BACK (double blink)",
    "wink_left":    "PREVIOUS (wink left)",
    "wink_right":   "NEXT (wink right)",
}

SIGNAL_HELP = {
    "blink":        "Close both eyes briefly (~300ms)",
    "double_blink": "Blink twice quickly within 600ms",
    "wink_left":    "Close ONLY your left eye briefly",
    "wink_right":   "Close ONLY your right eye briefly",
}
