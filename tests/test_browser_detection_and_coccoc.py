# -*- coding: utf-8 -*-
import os
import sys
import unittest.mock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    KNOWN_BROWSERS,
    get_browser_from_hwnd,
    detect_active_chess_browser,
    _load_or_create_persistent_session_token,
    SESSION_TOKEN,
)


def test_known_browsers_mapping():
    """Verify that browser.exe and coccoc.exe map to ('Cốc Cốc', 'coccoc')."""
    assert KNOWN_BROWSERS.get("browser.exe") == ("Cốc Cốc", "coccoc")
    assert KNOWN_BROWSERS.get("coccoc.exe") == ("Cốc Cốc", "coccoc")
    assert KNOWN_BROWSERS.get("chrome.exe") == ("Google Chrome", "chrome")
    assert KNOWN_BROWSERS.get("msedge.exe") == ("Microsoft Edge", "edge")
    assert KNOWN_BROWSERS.get("brave.exe") == ("Brave", "brave")
    # Non-browsers must NOT be in KNOWN_BROWSERS
    assert "setup_chessstealth.exe" not in KNOWN_BROWSERS
    assert "setup.exe" not in KNOWN_BROWSERS
    assert "installer.exe" not in KNOWN_BROWSERS


def test_setup_chessstealth_never_detected():
    """Verify that Setup_ChessStealth windows are rejected even if title contains 'chess'."""
    with unittest.mock.patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=30), \
         unittest.mock.patch("ctypes.windll.user32.GetWindowTextW") as mock_text, \
         unittest.mock.patch("ctypes.windll.user32.GetForegroundWindow", return_value=12345), \
         unittest.mock.patch("ctypes.windll.user32.GetWindowThreadProcessId"), \
         unittest.mock.patch("main.get_browser_from_hwnd", return_value=("", "")):
        
        # Test title: Setup - Chess Stealth
        def fill_buf(h, buf, maxlen):
            buf.value = "Setup - Chess Stealth Pro"
            return len(buf.value)
        mock_text.side_effect = fill_buf

        res = detect_active_chess_browser()
        assert res is None, "Setup window must NEVER be detected as chess browser"


def test_persistent_session_token():
    """Verify that session token is persistent across calls."""
    token1 = _load_or_create_persistent_session_token()
    token2 = _load_or_create_persistent_session_token()
    assert len(token1) >= 32
    assert token1 == token2
    assert SESSION_TOKEN == token1
