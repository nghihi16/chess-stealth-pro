import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from main import COLOR_PRESETS, arrow_state, ColorSwatch, ControlCenterWindow

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
