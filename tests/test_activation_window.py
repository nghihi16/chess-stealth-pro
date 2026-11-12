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


def test_activation_window_copy_and_activate(monkeypatch):
    app = QApplication.instance() or QApplication(sys.argv)
    monkeypatch.setattr(app_main.ModernAlertDialog, "exec", lambda self: None)
    activated_key = []
    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: activated_key.append(k))

    # Test copy
    w.copy_btn.click()
    assert w.copy_btn.text() == "Copied!"

    # Test empty key
    w.key_input.setText("")
    w.handle_activate()
    assert not w._activated

    w.close()


def test_activation_window_social_and_get_key(monkeypatch):
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)

    # Check GET KEY button
    assert hasattr(w, "get_key_btn")
    assert w.get_key_btn.text() == "GET KEY"

    # Check social buttons exist and have icons
    assert hasattr(w, "yt_btn")
    assert hasattr(w, "discord_btn")
    assert not w.yt_btn.icon().isNull()
    assert not w.discord_btn.icon().isNull()

    # Check clicking blank URLs does not throw
    w.yt_btn.click()
    w.discord_btn.click()

    # Check theme toggle
    w.theme = "light"
    w._apply_theme()
    w._update_social_icons()
    assert not w.yt_btn.icon().isNull()

    w.close()


