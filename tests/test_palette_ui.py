import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from main import COLOR_PRESETS, arrow_state, ColorSwatch, ControlCenterWindow, ModernColorPickerDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_color_presets_integrity():
    assert len(COLOR_PRESETS) >= 5
    for name, qc in COLOR_PRESETS.items():
        assert isinstance(qc, QColor)
        assert qc.isValid()
        assert qc.alpha() > 0


def test_color_swatch_callback(qapp):
    selected = []
    qc = QColor(34, 211, 238, 230)
    swatch = ColorSwatch("Cyan (Stealth)", qc, lambda n: selected.append(n))
    assert swatch.name == "Cyan (Stealth)"
    assert swatch.is_active is False
    swatch.click()
    assert selected == ["Cyan (Stealth)"]


def test_control_center_palette_state(qapp):
    win = ControlCenterWindow(active_key="TEST-PALETTE-KEY", hwid="TEST-HWID")
    assert win.active_color_name in COLOR_PRESETS
    assert len(win.swatches) == len(COLOR_PRESETS)

    # Change color
    win._on_color_changed("Emerald (Green)")
    assert arrow_state["qcolor"] == COLOR_PRESETS["Emerald (Green)"]
    assert win.swatches["Emerald (Green)"].is_active is True
    assert win.swatches["Orange (Classic)"].is_active is False
    assert win.color_combo.currentText() == "Emerald (Green)"

    # Change side
    win._on_side_changed("b")
    assert arrow_state["side"] == "b"
    assert win.side_combo.currentData() == "b"

    # Theme toggle
    win._toggle_theme()
    assert win.active_color_name == "Emerald (Green)"
    win.close()


def test_modern_color_picker_dialog(qapp):
    init_col = QColor(245, 158, 11, 230)
    dlg = ModernColorPickerDialog(init_col, theme="dark")
    assert dlg.current_color == init_col

    # Quick pick
    dlg._pick_quick_color("#22D3EE")
    assert dlg.current_color.red() == 0x22
    assert dlg.current_color.green() == 0xD3
    assert dlg.current_color.blue() == 0xEE

    # Hex edit
    dlg._on_hex_edited("#10B981")
    assert dlg.current_color.red() == 0x10
    assert dlg.current_color.green() == 0xB9
    assert dlg.current_color.blue() == 0x81

    # Slider edit
    dlg.slider_r.setValue(200)
    dlg.slider_g.setValue(100)
    dlg.slider_b.setValue(50)
    dlg._on_slider_changed()
    assert dlg.current_color.red() == 200
    assert dlg.current_color.green() == 100
    assert dlg.current_color.blue() == 50
    dlg.close()


def test_modern_logout_dialog(qapp):
    from main import ModernLogoutDialog
    dlg_dark = ModernLogoutDialog(theme="dark")
    assert dlg_dark.theme == "dark"
    assert not dlg_dark.confirmed
    dlg_dark._on_confirm()
    assert dlg_dark.confirmed
    dlg_dark.close()

    dlg_light = ModernLogoutDialog(theme="light")
    assert dlg_light.theme == "light"
    dlg_light.reject()
    assert not dlg_light.confirmed
    dlg_light.close()


def test_luxury_splash_screen(qapp):
    from main import LuxurySplashScreen
    finished_called = []
    splash = LuxurySplashScreen(on_finish=lambda: finished_called.append(True))
    assert splash._progress_val == 0
    splash._progress_val = 98
    splash._step_progress()
    assert splash._progress_val >= 100
    splash.close()


