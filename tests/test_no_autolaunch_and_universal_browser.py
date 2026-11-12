import os
import sys
import time
import unittest.mock
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication(sys.argv)

from main import (
    ControlCenterWindow,
    LuxuryStatusCard,
    QuickLaunchBar,
    arrow_state,
    create_windows_shortcut,
    install_scripts_and_extension,
    launch_browser_for_chess,
)


def test_activate_does_not_launch_browser():
    """Verify that clicking ACTIVATE toggles overlay state and NEVER launches a browser."""
    with unittest.mock.patch("subprocess.Popen") as mock_popen, unittest.mock.patch("os.startfile", create=True) as mock_startfile:
        arrow_state["enabled"] = False
        arrow_state["last_ping"] = 0.0  # Force disconnected state
        win = ControlCenterWindow(active_key="TEST-KEY", hwid="TEST-HWID")

        init_popen_count = mock_popen.call_count
        assert mock_startfile.call_count == 0

        # Click ACTIVATE
        win._toggle_assist()
        assert arrow_state["enabled"] is True
        assert win.action_btn.text() == "DEACTIVATE"

        # Assert no browser was opened on activation
        assert mock_popen.call_count == init_popen_count
        assert mock_startfile.call_count == 0

        # Click DEACTIVATE
        win._toggle_assist()
        assert arrow_state["enabled"] is False
        assert win.action_btn.text() == "ACTIVATE"
        assert mock_popen.call_count == init_popen_count
        assert mock_startfile.call_count == 0


def test_universal_browser_artifacts():
    """Verify that universal userscript and Min browser scripts are properly deployed."""
    ext_dir = install_scripts_and_extension()
    assert os.path.isdir(ext_dir)
    assert os.path.exists(os.path.join(ext_dir, "manifest.json"))
    assert os.path.exists(os.path.join(ext_dir, "content.js"))
    assert os.path.exists(os.path.join(ext_dir, "stockfish.js"))

    # Universal Userscript for Tampermonkey / Min / any browser
    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "ChessStealthPro")
    desktop_script = os.path.join(desktop_folder, "chess-assist.user.js")
    assert os.path.exists(desktop_script)
    with open(desktop_script, "r", encoding="utf-8") as f:
        content = f.read()
    assert "@match" in content
    assert "@include" in content
    assert "setupEngine" in content

    # Desktop unpacked extension & board selector precision
    assert os.path.exists(os.path.join(desktop_folder, "browser-extension", "manifest.json"))
    assert os.path.exists(os.path.join(desktop_folder, "browser-extension", "stockfish.js"))
    assert "getBoardElement" in content
    assert '[id^="board-layout"]' not in content


def test_status_card_click_does_not_launch_browser():
    """Verify that clicking the LuxuryStatusCard NEVER forces a browser launch (100% automatic detection)."""
    card = LuxuryStatusCard()
    arrow_state["last_ping"] = 0.0  # disconnected

    with unittest.mock.patch("main.launch_browser_for_chess") as mock_launch:
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPoint(20, 20),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        card.mousePressEvent(event)
        assert mock_launch.call_count == 0

    card.show_waiting(is_connected=False, browser_name="Brave")
    assert card.ready_big.text() == "READY"
    assert "DETECTED (BRAVE)" in card.status_pill.text()


def test_control_center_has_no_browser_launch_bar():
    """Verify ControlCenterWindow has no QuickLaunchBar buttons."""
    win = ControlCenterWindow(active_key="TEST-KEY", hwid="TEST-HWID")
    assert not hasattr(win, "quick_launch")
    assert len(win.findChildren(QuickLaunchBar)) == 0


def test_arrow_alignment_at_125_dpi():
    """Verify compute_auto_aligned_arrow aligns with exact square centers without top-bar offset error."""
    from main import compute_auto_aligned_arrow
    board_dict = {
        "left": 200.0,
        "top": 60.0,
        "width": 640.0,
        "height": 640.0,
        "innerWidth": 1536.0,
        "innerHeight": 737.0,
        "dpr": 1.25,
    }
    with unittest.mock.patch("main.find_browser_viewport", return_value=(0.0, 79.0, 1536.0, 737.0, 96)), \
         unittest.mock.patch("main._get_overlay_dpr", return_value=1.25):
        arrow_state["side"] = "auto"
        res = compute_auto_aligned_arrow(board_dict, "e2e4", flipped_flag=False)
        assert res is not None
        x1, y1, x2, y2, sq = res
        # sq = 640 / 8 = 80
        # e-file = col 4 -> x = 0 + 200 + 4.5 * 80 = 560
        # rank 2 = row 6 -> y1 = 79 + 60 + 6.5 * 80 = 659
        # rank 4 = row 4 -> y2 = 79 + 60 + 4.5 * 80 = 499
        assert sq == 80
        assert x1 == 560
        assert y1 == 659
        assert x2 == 560
        assert y2 == 499


def test_create_windows_shortcut(tmp_path):
    """Verify create_windows_shortcut creates a valid .lnk file on Windows."""
    test_target = sys.executable
    test_lnk = str(tmp_path / "TestShortcut.lnk")
    created = create_windows_shortcut(target_path=test_target, shortcut_path=test_lnk, arguments="--test")
    assert created is True
    assert os.path.exists(test_lnk)


def test_background_service_worker_stockfish_and_no_repeated_hook():
    """Verify background.js runs Stockfish directly (CSP-immune) and auto_hook never restarts connected browsers."""
    from main import _AUTO_HOOK_HIST, auto_hook_running_browser

    ext_dir = install_scripts_and_extension()
    bg_path = os.path.join(ext_dir, "background.js")
    assert os.path.exists(bg_path)
    with open(bg_path, "r", encoding="utf-8") as f:
        bg_code = f.read()
    assert "importScripts('stockfish.js')" in bg_code
    assert "OVERLAY_BOARD" in bg_code
    assert "/ping" in bg_code

    # Once last_ping > 0, auto_hook_running_browser must never restart the browser
    arrow_state["last_ping"] = time.time()
    _AUTO_HOOK_HIST.clear()
    assert auto_hook_running_browser({"key": "brave", "name": "Brave", "hwnd": 12345}) is False


def test_status_card_waiting_and_detected_states():
    """Verify LuxuryStatusCard handles 'waiting for chess.com', 'Detected', and 'waiting for browser' when closed."""
    from main import LuxuryStatusCard
    card = LuxuryStatusCard()

    # 1. Initial / No browser open: waiting for chess.com
    card.show_waiting(is_connected=False, browser_name=None, was_closed=False)
    assert "WAITING FOR CHESS.COM" in card.status_pill.text()
    assert "Waiting for chess.com" in card.sub_lbl.text()
    assert card.ready_big.text() == "READY"

    # 2. Browser detected but not connected: 'Detected' under READY
    card.show_waiting(is_connected=False, browser_name="Brave", was_closed=False)
    assert "DETECTED (BRAVE)" in card.status_pill.text()
    assert card.ready_big.text() == "READY"
    assert card.sub_lbl.text() == "Detected"

    # 3. User closes browser: resets to waiting for browser
    card.show_waiting(is_connected=False, browser_name=None, was_closed=True)
    assert "WAITING FOR BROWSER" in card.status_pill.text()
    assert "Waiting for browser" in card.sub_lbl.text()
    assert card.ready_big.text() == "READY"


def test_splash_progress_real_updating():
    """Verify LuxurySplashScreen update_progress reflects real loading stages."""
    from main import LuxurySplashScreen
    splash = LuxurySplashScreen()
    assert splash.height() == 230  # compact luxury design without bloated subtitle

    splash.update_progress(25, "Loading engine...")
    assert splash._progress_val == 25
    assert splash.progress_bar.value() == 25
    assert "Loading engine..." in splash.status_lbl.text()
    assert "25%" in splash.status_lbl.text()

    splash.update_progress(55, "Starting services...")
    assert splash.progress_bar.value() == 55
    assert "Starting services..." in splash.status_lbl.text()

    splash.update_progress(100, "Ready")
    assert splash.progress_bar.value() == 100
    assert "Ready" in splash.status_lbl.text()
    splash.close()


