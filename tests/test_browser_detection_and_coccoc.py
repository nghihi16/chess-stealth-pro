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


def test_firefox_auto_hook_opens_userscript():
    """Verify that auto_hook_running_browser for Firefox triggers opening the userscript install URL."""
    from main import auto_hook_running_browser, _AUTO_HOOK_HIST, arrow_state

    # Reset state
    _AUTO_HOOK_HIST.pop("firefox", None)
    arrow_state["last_ping"] = 0.0

    opened_urls = []
    with unittest.mock.patch("subprocess.Popen") as mock_popen, \
         unittest.mock.patch("main.find_browser_exe", return_value=r"C:\Program Files\Mozilla Firefox\firefox.exe"), \
         unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("sys.platform", "win32"), \
         unittest.mock.patch.dict(os.environ, {}, clear=False):
        
        # Remove PYTEST_CURRENT_TEST check for this specific unit test
        if "PYTEST_CURRENT_TEST" in os.environ:
            del os.environ["PYTEST_CURRENT_TEST"]
        try:
            detected = {"name": "Mozilla Firefox", "key": "firefox", "hwnd": 0}
            ret = auto_hook_running_browser(detected)
            assert ret is True
            assert mock_popen.called
            args = mock_popen.call_args[0][0]
            assert "127.0.0.1:8765/chess-assist.user.js" in args[1]
        finally:
            os.environ["PYTEST_CURRENT_TEST"] = "1"


def test_min_browser_userscript_header_and_token():
    """Verify that Min userscript starts with // ==UserScript== at line 1 and contains SESSION_TOKEN."""
    from main import install_scripts_and_extension, SESSION_TOKEN
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        with unittest.mock.patch.dict(os.environ, {"APPDATA": tmpdir}):
            install_scripts_and_extension()
            min_script = os.path.join(tmpdir, "Min", "userscripts", "chess-assist.js")
            assert os.path.exists(min_script)
            with open(min_script, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                all_content = f.read()
            assert first_line == "// ==UserScript=="
            assert f"const SESSION_TOKEN = '{SESSION_TOKEN}';" in all_content
            assert "setupEngine" in all_content


def test_server_origin_auth():
    """Verify that requests from chess.com Origin pass _check_auth even without token."""
    from main import StealthOverlayServer
    import io

    class DummyReq:
        def makefile(self, *args, **kwargs):
            return io.BytesIO(b"GET / HTTP/1.1\r\nOrigin: https://www.chess.com\r\n\r\n")

    server_handler = StealthOverlayServer.__new__(StealthOverlayServer)
    server_handler.headers = {"Origin": "https://www.chess.com"}
    server_handler.path = "/update"
    assert server_handler._check_auth() is True

    # But external random site is rejected
    server_handler.headers = {"Origin": "https://malicious-site.com"}
    assert server_handler._check_auth() is False


