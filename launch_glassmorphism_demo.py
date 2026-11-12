"""
Live Interactive Demo for Pure Glassmorphism
Run with: python launch_glassmorphism_demo.py
Press Ctrl+T to toggle between Dark Mode and Light Mode anytime!
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
import main as app_main

def run():
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    w.setWindowTitle("Chess Stealth — Pure Glassmorphism (Ctrl+T to toggle theme)")
    w.show()
    app.exec()

if __name__ == "__main__":
    run()
