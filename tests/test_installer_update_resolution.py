import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_SETUP_DIR = os.path.join(PROJECT_ROOT, "build_setup")
if BUILD_SETUP_DIR not in sys.path:
    sys.path.insert(0, BUILD_SETUP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_installer_does_not_downgrade_when_bundled_newer_than_github():
    import installer_gui

    decision = installer_gui.resolve_installer_update_state(
        result={
            "available": True,
            "tag": "v3.2.2",
            "version": (3, 2, 2),
            "download_url": "https://github.com/nghihi16/chess-stealth-pro/releases/download/v3.2.2/payload.zip",
        },
        installed_version="v3.2.2",
        bundled_version="3.2.3",
        is_update_mode=True,
    )
    assert decision["download_url"] is None
    assert decision["new_version"] == "3.2.3"
    assert decision["highlight"] is True
    assert "v3.2.3" in decision["badge_text"]
    assert decision["btn_text"] == "Update to v3.2.3"


def test_installer_reports_installed_version_when_up_to_date_ahead_of_github():
    import installer_gui

    decision = installer_gui.resolve_installer_update_state(
        result={
            "available": True,
            "tag": "v3.2.2",
            "version": (3, 2, 2),
            "download_url": "https://github.com/nghihi16/chess-stealth-pro/releases/download/v3.2.2/payload.zip",
        },
        installed_version="3.2.3",
        bundled_version="3.2.3",
        is_update_mode=True,
    )
    assert decision["download_url"] is None
    assert decision["highlight"] is False
    assert "v3.2.3" in decision["badge_text"]
    assert "v3.2.2" not in decision["badge_text"]
    assert decision["btn_text"] == "Reinstall / Repair"


def test_installer_uses_github_when_remote_newer_than_bundle():
    import installer_gui

    url = "https://github.com/nghihi16/chess-stealth-pro/releases/download/v3.2.4/payload.zip"
    decision = installer_gui.resolve_installer_update_state(
        result={
            "available": True,
            "tag": "v3.2.4",
            "version": (3, 2, 4),
            "download_url": url,
        },
        installed_version="3.2.3",
        bundled_version="3.2.3",
        is_update_mode=True,
    )
    assert decision["download_url"] == url
    assert decision["new_version"] == "v3.2.4"
    assert decision["highlight"] is True
    assert "v3.2.4" in decision["badge_text"]
    assert decision["btn_text"] == "Update to v3.2.4"


def test_installer_fresh_install_keeps_bundled_when_github_older():
    import installer_gui

    decision = installer_gui.resolve_installer_update_state(
        result={
            "available": True,
            "tag": "v3.2.2",
            "version": (3, 2, 2),
            "download_url": "https://example.com/v3.2.2/payload.zip",
        },
        installed_version="",
        bundled_version="3.2.3",
        is_update_mode=False,
    )
    assert decision["download_url"] is None
    assert decision["new_version"] == "3.2.3"


def test_setup_wizard_on_github_checked_uses_local_bundle(qapp, monkeypatch):
    import installer_gui

    monkeypatch.setattr(
        installer_gui,
        "get_installed_info",
        lambda: {
            "installed": True,
            "location": r"C:\Temp\ChessStealth",
            "version": installer_gui.APP_VERSION,
            "exe_path": r"C:\Temp\ChessStealth\ChessStealth.exe",
        },
    )
    monkeypatch.setattr(installer_gui.GitHubCheckThread, "start", lambda self: None)

    win = installer_gui.SetupWizardWindow()
    try:
        win.on_github_checked({
            "available": True,
            "tag": "v3.2.2",
            "version": (3, 2, 2),
            "download_url": "https://example.com/v3.2.2/payload.zip",
        })
        assert win.download_url is None
        assert f"v{installer_gui.APP_VERSION}" in win.update_badge_lbl.text()
        assert win.start_btn.text() == "Reinstall / Repair"
    finally:
        win.close()


def test_control_center_sync_live_status_displays_analyzing_move(qapp, monkeypatch):
    import time
    import main as app_main

    orig_detect = app_main.detect_active_chess_browser
    orig_state = app_main.arrow_state.copy()
    cc = app_main.ControlCenterWindow("TEST-KEY", "TEST-HWID")
    try:
        monkeypatch.setattr(
            app_main,
            "detect_active_chess_browser",
            lambda: {"name": "Min Browser", "key": "min", "hwnd": 1, "title": "Chess.com"},
        )
        now = time.time()
        app_main.arrow_state.update({
            "enabled": True,
            "show": True,
            "move": "d2d4",
            "eval": "+0.42",
            "piece": "P",
            "depth": "15",
            "last_seen": now,
            "last_ping": now,
        })
        cc._sync_live_status()
        assert "ANALYZING" in cc.status_card.status_pill.text()
        assert cc.status_card.ready_big.isHidden() is True
        assert cc.status_card.from_sq.text() == "D2"
        assert cc.status_card.to_sq.text() == "D4"
        assert "White Pawn" in cc.status_card.sub_lbl.text()
    finally:
        app_main.arrow_state.clear()
        app_main.arrow_state.update(orig_state)
        app_main.detect_active_chess_browser = orig_detect
        cc.status_timer.stop()
        cc.close()


def test_extract_member_with_retry_recovers_from_transient_permission_error(tmp_path):
    import installer_gui

    attempts = {"count": 0}

    class FakeZip:
        def extract(self, item, target_dir):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise PermissionError(13, "locked")
            out = os.path.join(target_dir, item)
            with open(out, "wb") as f:
                f.write(b"ok")
            return out

    installer_gui._extract_member_with_retry(FakeZip(), "ChessStealth.exe", str(tmp_path), retries=5, delay_sec=0.0)
    assert attempts["count"] == 3
    assert (tmp_path / "ChessStealth.exe").read_bytes() == b"ok"

