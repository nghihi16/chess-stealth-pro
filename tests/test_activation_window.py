import sys
import os
sys.path.insert(0, r"C:\Users\Windows\ChessStealthPro")
from PySide6.QtWidgets import QApplication
import main as app_main

def test_activation_window_init():
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    assert w.width() == 840
    assert w.height() == 520
    assert w.hwid_display.text() == "A3F9-27C1-88D0"
    assert w.card is not None
    w.close()
