import os
import sys
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import EngineCard, EngineDropdownPopup, AVAILABLE_ENGINES, get_asset_path

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_engines_list_valid():
    assert len(AVAILABLE_ENGINES) >= 3
    for eng in AVAILABLE_ENGINES:
        assert "id" in eng
        assert "name" in eng
        assert "details" in eng
        assert "icon" in eng
        ic_path = get_asset_path(eng["icon"])
        assert os.path.exists(ic_path), f"Icon {ic_path} does not exist"

def test_engine_card_and_dropdown(qapp):
    card = EngineCard(theme="dark")
    card.resize(344, 76)
    card.show()

    assert card.current_engine_id == "sf_20"
    assert card._dropdown is None or not card._dropdown.isVisible()

    # Simulate click to open
    card._toggle_popup()
    assert card._dropdown is not None
    assert card._dropdown.isVisible()

    # Pick komodo_dragon engine
    komodo_eng = [e for e in AVAILABLE_ENGINES if e["id"] == "komodo_dragon"][0]
    card._on_engine_picked(komodo_eng)

    assert card.current_engine_id == "komodo_dragon"
    assert "Dragon 3.3" in card.title_lbl.text()
    assert card.icon_file == "icon_engine_komodo.png"

    # Close dropdown
    card._dropdown.close()
    assert card._dropdown is None or not card._dropdown.isVisible()

    # Verify debounce protection prevents instant reopening
    assert card._last_close_time > 0
    card._last_close_time = time.time() + 5.0
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.mousePressEvent(event)
    assert card._dropdown is None or not card._dropdown.isVisible()

    card.close()

def test_engine_item_widget_click_no_crash(qapp):
    card = EngineCard(theme="dark")
    card.resize(344, 76)
    card.show()
    card._toggle_popup()
    assert card._dropdown is not None
    assert len(card._dropdown.items) > 1

    # Simulate mouse press on second engine item (e.g. SF 16 level 16)
    target_item = card._dropdown.items[1]
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    
    # Must not raise RuntimeError: libshiboken: Internal C++ object already deleted
    target_item.mousePressEvent(event)
    qapp.processEvents()

    assert card.current_engine_id == target_item.engine_data["id"]
    card.close()


def test_engine_dropdown_toggle_open_and_close(qapp):
    card = EngineCard(theme="dark")
    card.resize(344, 76)
    card.show()

    # 1st click: open
    event1 = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.mousePressEvent(event1)
    assert card._dropdown is not None
    assert card._dropdown.isVisible()

    # 2nd click: close cleanly without crash
    event2 = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.mousePressEvent(event2)
    assert not card._dropdown.isVisible()

    card.close()

