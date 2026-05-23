"""
NavTools — Application Entry Point
====================================
This file is the PyInstaller entry point.
It simply calls the main() function from src.gui_app.

Usage (development):
  python main.py
  python -m src.gui_app

Usage (built exe):
  NavTools.exe
"""

import sys
import os

# When frozen, ensure the _MEIPASS directory is on sys.path
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

from src.gui_app import main

if __name__ == "__main__":
    main()
