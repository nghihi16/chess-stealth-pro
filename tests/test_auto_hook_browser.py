import os
import sys
import threading
import unittest.mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main


def _reset_hook_state():
    main._AUTO_HOOK_HIST.clear()
    main.arrow_state["last_ping"] = 0.0


def test_is_browser_already_hooked_checks_cmdline_flags():
    hwnd_pid = 4242
    with unittest.mock.patch("ctypes.windll.user32.GetWindowThreadProcessId", side_effect=lambda h, p: setattr(p._obj, "value", hwnd_pid)), \
         unittest.mock.patch("main._get_process_cmdline", return_value='"brave.exe" --load-extension="C:\\ext"'), \
         unittest.mock.patch("main._list_pids_by_exe_name", return_value=[]):
        assert main._is_browser_already_hooked(123, r"C:\Brave\brave.exe") is True

    with unittest.mock.patch("ctypes.windll.user32.GetWindowThreadProcessId", side_effect=lambda h, p: setattr(p._obj, "value", 100)), \
         unittest.mock.patch("main._list_pids_by_exe_name", return_value=[100, 200]), \
         unittest.mock.patch("main._get_process_cmdline", side_effect=lambda pid: "--load-extension=abc" if pid == 200 else "brave.exe"):
        assert main._is_browser_already_hooked(123, r"C:\Brave\brave.exe") is True

    with unittest.mock.patch("ctypes.windll.user32.GetWindowThreadProcessId", side_effect=lambda h, p: setattr(p._obj, "value", 100)), \
         unittest.mock.patch("main._list_pids_by_exe_name", return_value=[100]), \
         unittest.mock.patch("main._get_process_cmdline", return_value='"brave.exe" --profile-directory=Default'):
        assert main._is_browser_already_hooked(123, r"C:\Brave\brave.exe") is False


def test_auto_hook_skips_browser_already_having_load_extension(monkeypatch):
    _reset_hook_state()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with unittest.mock.patch("sys.platform", "win32"), \
         unittest.mock.patch("main.find_browser_exe", return_value=r"C:\Brave\brave.exe"), \
         unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("main._is_browser_already_hooked", return_value=True), \
         unittest.mock.patch("subprocess.run") as mock_run, \
         unittest.mock.patch("subprocess.Popen") as mock_popen:
        ok = main.auto_hook_running_browser({"name": "Brave", "key": "brave", "hwnd": 0})

    assert ok is False
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_auto_hook_never_kills_chrome_137_plus_without_userscript_manager(monkeypatch):
    _reset_hook_state()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with unittest.mock.patch("sys.platform", "win32"), \
         unittest.mock.patch("main.find_browser_exe", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"), \
         unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("main._is_browser_already_hooked", return_value=False), \
         unittest.mock.patch("main._get_pe_major_version", return_value=154), \
         unittest.mock.patch("main._chrome_userscript_manager_installed", return_value=False), \
         unittest.mock.patch("subprocess.run") as mock_run, \
         unittest.mock.patch("subprocess.Popen") as mock_popen:
        ok = main.auto_hook_running_browser({"name": "Google Chrome", "key": "chrome", "hwnd": 0})

    assert ok is False
    mock_run.assert_not_called()
    mock_popen.assert_not_called()


def test_auto_hook_opens_userscript_in_chrome_when_manager_installed(monkeypatch):
    _reset_hook_state()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with unittest.mock.patch("sys.platform", "win32"), \
         unittest.mock.patch("main.find_browser_exe", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"), \
         unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("main._is_browser_already_hooked", return_value=False), \
         unittest.mock.patch("main._get_pe_major_version", return_value=154), \
         unittest.mock.patch("main._chrome_userscript_manager_installed", return_value=True), \
         unittest.mock.patch("subprocess.run") as mock_run, \
         unittest.mock.patch("subprocess.Popen") as mock_popen:
        ok = main.auto_hook_running_browser({"name": "Google Chrome", "key": "chrome", "hwnd": 0})

    assert ok is True
    mock_run.assert_not_called()
    mock_popen.assert_called_once()
    assert "chess-assist.user.js" in mock_popen.call_args[0][0][1]


def test_auto_hook_gracefully_reloads_unhooked_brave_without_taskkill_when_wm_close_exits(monkeypatch):
    _reset_hook_state()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    class ImmediateThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    with unittest.mock.patch("sys.platform", "win32"), \
         unittest.mock.patch("main.find_browser_exe", return_value=r"C:\Brave\brave.exe"), \
         unittest.mock.patch("os.path.exists", return_value=True), \
         unittest.mock.patch("main._is_browser_already_hooked", return_value=False), \
         unittest.mock.patch("main._close_browser_windows_gracefully"), \
         unittest.mock.patch("main._wait_for_process_exit", return_value=True), \
         unittest.mock.patch("threading.Thread", ImmediateThread), \
         unittest.mock.patch("subprocess.run") as mock_run, \
         unittest.mock.patch("subprocess.Popen") as mock_popen:
        ok = main.auto_hook_running_browser({"name": "Brave", "key": "brave", "hwnd": 0})

    assert ok is True
    mock_run.assert_not_called()
    mock_popen.assert_called_once()
    launched = mock_popen.call_args[0][0]
    assert "--restore-last-session" in launched
    assert any(arg.startswith("--load-extension=") for arg in launched)


def test_sync_live_status_shows_native_vision_ready_without_killing_chrome(qapp, monkeypatch):
    _reset_hook_state()
    orig_state = main.arrow_state.copy()
    cc = main.ControlCenterWindow("TEST-KEY", "TEST-HWID")
    cc.status_timer.stop()
    try:
        main.arrow_state.update({
            "enabled": True,
            "show": False,
            "last_seen": 0.0,
            "last_ping": 0.0,
            "vision_active": False,
            "vision_status": "",
        })

        monkeypatch.setattr(
            main,
            "detect_active_chess_browser",
            lambda: {"name": "Google Chrome", "key": "chrome", "hwnd": 1, "title": "Chess.com"},
        )
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        with unittest.mock.patch("sys.platform", "win32"), \
             unittest.mock.patch("subprocess.run") as mock_run, \
             unittest.mock.patch("subprocess.Popen") as mock_popen:
            cc._sync_live_status()
            assert "DETECTED (GOOGLE CHROME)" in cc.status_card.status_pill.text()
            assert cc.status_card.sub_lbl.text() == "Native Vision Ready (Google Chrome) • Open board"

            main.arrow_state.update({
                "last_seen": main.time.time(),
                "vision_active": True,
                "vision_status": "need_start_pos",
            })
            cc._sync_live_status()
            assert "CONNECTED (GOOGLE CHROME)" in cc.status_card.status_pill.text()
            assert cc.status_card.sub_lbl.text() == "Start New Game (Move 1) to lock pieces"

        mock_run.assert_not_called()
        mock_popen.assert_not_called()
    finally:
        main.arrow_state.clear()
        main.arrow_state.update(orig_state)
        cc.status_timer.stop()
        cc.close()
