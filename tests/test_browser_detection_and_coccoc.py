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


def test_live_move_sync_updates_status_card_without_name_error():
    """Verify _sync_live_status handles a live move without NameError on PIECE_NAMES_EN."""
    import time
    from PySide6.QtWidgets import QApplication
    import main

    _app = QApplication.instance() or QApplication(sys.argv)
    snap = dict(main.arrow_state)
    try:
        with unittest.mock.patch("main.ensure_overlay_running"), \
             unittest.mock.patch("main.install_scripts_and_extension"):
            win = main.ControlCenterWindow(active_key="TEST-KEY", hwid="TEST-HWID")
            win.status_timer.stop()

        now = time.time()
        main.arrow_state.update({
            "enabled": True,
            "show": True,
            "move": "e2e4",
            "piece": "P",
            "depth": "12",
            "eval": "+0.4",
            "last_seen": now,
            "last_ping": now,
        })
        win._last_rendered_sig = None

        with unittest.mock.patch(
            "main.detect_active_chess_browser",
            return_value={"key": "min", "name": "Min Browser", "hwnd": 12345},
        ):
            win._sync_live_status()

        assert win.status_card.from_sq.text() == "E2"
        assert win.status_card.to_sq.text() == "E4"
        assert "White Pawn" in win.status_card.sub_lbl.text()
        assert "ANALYZING" in win.status_card.status_pill.text()
    finally:
        main.arrow_state.clear()
        main.arrow_state.update(snap)


def test_cal_endpoint_uses_imported_qcursor_without_name_error():
    """Verify QCursor is imported in main and /cal handler calibrates without NameError."""
    import main
    assert hasattr(main, "QCursor")

    class DummyPt:
        def x(self): return 400
        def y(self): return 300

    class DummyHandler(main.StealthOverlayServer):
        def __init__(self):
            self.path = "/cal?cx=300&cy=200&dpr=1&iw=1280&ih=720&wx=0&wy=0"
            self.headers = {"Origin": "https://www.chess.com"}
            self.status_code = None
            self.wfile = __import__("io").BytesIO()

        def send_response(self, code, message=None):
            self.status_code = code

        def send_header(self, k, v):
            pass

        def end_headers(self):
            pass

    handler = DummyHandler()
    orig_cal = dict(main._CALIBRATED_VP)
    try:
        main._CALIBRATED_VP.clear()
        with unittest.mock.patch.object(main.QCursor, "pos", return_value=DummyPt()), \
             unittest.mock.patch("main.detect_active_chess_browser", return_value={"key": "min", "name": "Min Browser", "hwnd": 999}), \
             unittest.mock.patch("main._get_visible_window_rect_qt", return_value=(0.0, 0.0, 1280.0, 760.0, False)), \
             unittest.mock.patch("main._get_overlay_dpr", return_value=1.0):
            handler.do_GET()

        assert handler.status_code == 200
        assert main._CALIBRATED_VP.get("left_qt") == 100.0
        assert main._CALIBRATED_VP.get("top_qt") == 100.0
    finally:
        main._CALIBRATED_VP.clear()
        main._CALIBRATED_VP.update(orig_cal)


def test_frozen_chessstealth_does_not_create_shortcut_to_stale_chesspro(tmp_path):
    """When frozen ChessStealth.exe runs, shortcuts must never point to stale Desktop/ChessStealthPro/ChessPro.exe."""
    import main

    fake_installed_exe = str(tmp_path / "Programs" / "ChessStealth" / "ChessStealth.exe")
    os.makedirs(os.path.dirname(fake_installed_exe), exist_ok=True)
    with open(fake_installed_exe, "wb") as f:
        f.write(b"MZ")

    created_targets = []
    def spy_shortcut(target_path, shortcut_path, icon_path="", work_dir="", desc="", arguments=""):
        created_targets.append((target_path, shortcut_path))
        return True

    with unittest.mock.patch.object(main.sys, "frozen", True, create=True), \
         unittest.mock.patch.object(main.sys, "executable", fake_installed_exe), \
         unittest.mock.patch("main.create_windows_shortcut", side_effect=spy_shortcut), \
         unittest.mock.patch.dict(os.environ, {"APPDATA": str(tmp_path)}):
        main.install_scripts_and_extension()

    for target_path, _ in created_targets:
        assert not target_path.lower().endswith("chesspro.exe"), f"Stale ChessPro.exe shortcut target: {target_path}"


def test_kill_other_app_instances_targets_both_exes():
    """Verify single-instance cleanup terminates both ChessPro.exe and ChessStealth.exe."""
    import main

    with unittest.mock.patch("subprocess.run") as mock_run:
        main._kill_other_app_instances(1111, 2222)

    cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list if c.args]
    assert any("IMAGENAME eq ChessPro.exe" in cmd for cmd in cmds)
    assert any("IMAGENAME eq ChessStealth.exe" in cmd for cmd in cmds)


def test_overlay_http_server_sets_reuse_address():
    """Verify overlay HTTP server class sets allow_reuse_address = True."""
    import main
    assert getattr(main, "_StealthThreadingHTTPServer", None) is not None
    assert main._StealthThreadingHTTPServer.allow_reuse_address is True



