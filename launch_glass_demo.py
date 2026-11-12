"""
Live Interactive Demo for Chess Stealth Pro Glass Concepts
Run with: python launch_glass_demo.py [concept1|concept2|concept3]
"""
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPixmap, QFont, QIcon
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect
)
import main as app_main
from generate_creative_concepts import (
    Concept1Card, Concept2Card, Concept3Card,
    GLASS_DARK_QSS, GLASS_LIGHT_QSS
)

def run_demo(concept_name="concept1"):
    app = QApplication.instance() or QApplication(sys.argv)
    
    card_map = {
        "concept1": ("Concept 1: Cyber Matrix Glass (Halftone Queen)", Concept1Card),
        "concept2": ("Concept 2: VisionOS Prism Glass (Micro-Cross)", Concept2Card),
        "concept3": ("Concept 3: Neon Stealth Glass (Laser Cyan)", Concept3Card),
    }

    title, card_cls = card_map.get(concept_name.lower(), card_map["concept1"])

    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    w.setWindowTitle(f"Demo — {title} (Press Ctrl+T to toggle theme)")

    # Replace card
    old_card = w.card
    body_layout = w.layout().itemAt(1).layout()
    new_card = card_cls(theme=w.theme)
    new_card.setLayout(old_card.layout())
    body_layout.replaceWidget(old_card, new_card)
    old_card.deleteLater()
    w.card = new_card

    # Hook theme toggle to custom glass styles
    orig_toggle = w._toggle_theme
    def custom_toggle():
        orig_toggle()
        w.card.set_theme(w.theme)
        if w.theme == "dark":
            w.setStyleSheet(GLASS_DARK_QSS)
            shadow = QGraphicsDropShadowEffect(w.card)
            shadow.setBlurRadius(36)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 160))
            w.card.setGraphicsEffect(shadow)
        else:
            w.setStyleSheet(GLASS_LIGHT_QSS)
            shadow = QGraphicsDropShadowEffect(w.card)
            shadow.setBlurRadius(32)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 48))
            w.card.setGraphicsEffect(shadow)
        w.update()

    w._theme_shortcut.activated.disconnect()
    w._theme_shortcut.activated.connect(custom_toggle)

    # Initial style
    w.setStyleSheet(GLASS_DARK_QSS if w.theme == "dark" else GLASS_LIGHT_QSS)
    shadow = QGraphicsDropShadowEffect(w.card)
    shadow.setBlurRadius(36)
    shadow.setOffset(0, 10)
    shadow.setColor(QColor(0, 0, 0, 160))
    w.card.setGraphicsEffect(shadow)

    w.show()
    app.exec()

if __name__ == "__main__":
    concept = sys.argv[1] if len(sys.argv) > 1 else "concept1"
    run_demo(concept)
