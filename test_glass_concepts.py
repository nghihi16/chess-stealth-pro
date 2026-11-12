import os
import sys
import math
from PIL import Image

sys.path.insert(0, r"C:\Users\Windows\ChessStealthPro")
os.chdir(r"C:\Users\Windows\ChessStealthPro")

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPixmap, QFont, QIcon
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect
)
import main as app_main

app = QApplication.instance() or QApplication(sys.argv)

queen_raw = Image.open(r"C:\Users\Windows\ChessStealthPro\assets\queen_light.png").convert("RGBA")
qw, qh = 175, 355
queen_resized = queen_raw.resize((qw, qh), Image.Resampling.LANCZOS)
queen_alpha = queen_resized.split()[3]

class ConceptAHalftoneCard(QFrame):
    """
    Concept A: 'Cyber Halftone Matrix'
    Features:
    - Halftone Queen watermark made of scaling luminous dots (Image 1 style)
    - Specular top rim refraction line
    - Image 2 style horizontal luminous divider
    - Glass pill inputs & lens action buttons
    """
    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("FrostedCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(410)

    def set_theme(self, t):
        self.theme = t
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, float(self.width()) - 1.0, float(self.height()) - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)

        w = self.width()
        h = self.height()

        if self.theme == "dark":
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(22, 26, 36, 235))
            grad.setColorAt(0.4, QColor(14, 16, 24, 245))
            grad.setColorAt(1.0, QColor(8, 10, 15, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Cyan/ice ambient tint
            radial = QRadialGradient(QPointF(60, 40), 220)
            radial.setColorAt(0.0, QColor(56, 189, 248, 28))
            radial.setColorAt(1.0, QColor(56, 189, 248, 0))
            p.fillRect(self.rect(), QBrush(radial))

            # Halftone Queen Matrix
            grid_step = 15
            qx0 = w - qw - 14
            qy0 = 38
            p.setPen(Qt.PenStyle.NoPen)
            for gy in range(16, h - 16, grid_step):
                for gx in range(18, w - 16, grid_step):
                    ix = gx - qx0
                    iy = gy - qy0
                    q_val = 0.0
                    if 0 <= ix < qw and 0 <= iy < qh:
                        q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                    fade = max(0.0, min(1.0, (gx - 130) / 180.0))
                    weight = q_val * fade

                    if weight > 0.05:
                        dot_r = 1.0 + weight * 2.8
                        alpha = int(25 + weight * 170)
                        p.setBrush(QColor(255, 255, 255, alpha))
                        p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                    else:
                        p.setBrush(QColor(255, 255, 255, 12))
                        p.drawEllipse(QPointF(gx, gy), 0.9, 0.9)

            # Specular top edge highlight line
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.2))
            p.drawLine(QPointF(28, 1.5), QPointF(w - 28, 1.5))

            # Image 2 Style Luminous Divider Line
            div_y = h - 136
            div_grad = QLinearGradient(28, div_y, w - 28, div_y)
            div_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            div_grad.setColorAt(0.15, QColor(255, 255, 255, 38))
            div_grad.setColorAt(0.5, QColor(255, 255, 255, 60))
            div_grad.setColorAt(0.85, QColor(255, 255, 255, 38))
            div_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(28, div_y), QPointF(w - 28, div_y))

            # Outer Crisp Glass Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 68))
            border_grad.setColorAt(0.3, QColor(255, 255, 255, 28))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 16))
            p.setPen(QPen(QBrush(border_grad), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.4, QColor(245, 248, 252, 250))
            grad.setColorAt(1.0, QColor(236, 241, 248, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Soft blue ambient tint
            radial = QRadialGradient(QPointF(60, 40), 220)
            radial.setColorAt(0.0, QColor(0, 113, 227, 20))
            radial.setColorAt(1.0, QColor(0, 113, 227, 0))
            p.fillRect(self.rect(), QBrush(radial))

            # Halftone Matrix in Light Mode
            grid_step = 15
            qx0 = w - qw - 14
            qy0 = 38
            p.setPen(Qt.PenStyle.NoPen)
            for gy in range(16, h - 16, grid_step):
                for gx in range(18, w - 16, grid_step):
                    ix = gx - qx0
                    iy = gy - qy0
                    q_val = 0.0
                    if 0 <= ix < qw and 0 <= iy < qh:
                        q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                    fade = max(0.0, min(1.0, (gx - 130) / 180.0))
                    weight = q_val * fade

                    if weight > 0.05:
                        dot_r = 1.0 + weight * 2.8
                        alpha = int(40 + weight * 145)
                        p.setBrush(QColor(71, 85, 105, alpha))
                        p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                    else:
                        p.setBrush(QColor(148, 163, 184, 32))
                        p.drawEllipse(QPointF(gx, gy), 0.9, 0.9)

            # Specular top edge highlight
            p.setPen(QPen(QColor(255, 255, 255, 240), 1.2))
            p.drawLine(QPointF(28, 1.5), QPointF(w - 28, 1.5))

            # Luminous Divider Line
            div_y = h - 136
            div_grad = QLinearGradient(28, div_y, w - 28, div_y)
            div_grad.setColorAt(0.0, QColor(15, 23, 42, 0))
            div_grad.setColorAt(0.2, QColor(15, 23, 42, 32))
            div_grad.setColorAt(0.5, QColor(15, 23, 42, 50))
            div_grad.setColorAt(0.8, QColor(15, 23, 42, 32))
            div_grad.setColorAt(1.0, QColor(15, 23, 42, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(28, div_y), QPointF(w - 28, div_y))

            # Outer Crisp Glass Border
            p.setClipping(False)
            p.setPen(QPen(QColor(15, 23, 42, 42), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


class ConceptBVisionOSCard(QFrame):
    """
    Concept B: 'VisionOS Liquid Frosted Aura'
    Features:
    - Deep smoked liquid glass gradient with dual specular edge light (top & left)
    - Ultra-clean micro-coordinate grid (+)
    - Luminous accent badge & divider
    """
    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("FrostedCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(410)

    def set_theme(self, t):
        self.theme = t
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, float(self.width()) - 1.0, float(self.height()) - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)

        w = self.width()
        h = self.height()

        if self.theme == "dark":
            # Deep smoked obsidian glass
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(26, 30, 42, 240))
            grad.setColorAt(0.5, QColor(16, 18, 26, 248))
            grad.setColorAt(1.0, QColor(10, 12, 18, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Dual Ambient aura: Top-Right violet + Bottom-Left cyan
            aura1 = QRadialGradient(QPointF(w - 40, 50), 220)
            aura1.setColorAt(0.0, QColor(129, 140, 248, 28))
            aura1.setColorAt(1.0, QColor(129, 140, 248, 0))
            p.fillRect(self.rect(), QBrush(aura1))

            aura2 = QRadialGradient(QPointF(40, h - 80), 200)
            aura2.setColorAt(0.0, QColor(56, 189, 248, 22))
            aura2.setColorAt(1.0, QColor(56, 189, 248, 0))
            p.fillRect(self.rect(), QBrush(aura2))

            # Micro-cross (+) coordinate grid
            cross_pen = QPen(QColor(255, 255, 255, 18), 1.0)
            p.setPen(cross_pen)
            step = 22
            for x in range(24, w - 16, step):
                for y in range(24, h - 16, step):
                    p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
                    p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))

            # Specular top highlight line
            p.setPen(QPen(QColor(255, 255, 255, 65), 1.2))
            p.drawLine(QPointF(28, 1.5), QPointF(w - 28, 1.5))

            # Luminous Divider Line
            div_y = h - 136
            div_grad = QLinearGradient(28, div_y, w - 28, div_y)
            div_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            div_grad.setColorAt(0.2, QColor(255, 255, 255, 42))
            div_grad.setColorAt(0.5, QColor(255, 255, 255, 68))
            div_grad.setColorAt(0.8, QColor(255, 255, 255, 42))
            div_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(28, div_y), QPointF(w - 28, div_y))

            # Outer Crisp Glass Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 75))
            border_grad.setColorAt(0.4, QColor(255, 255, 255, 30))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 18))
            p.setPen(QPen(QBrush(border_grad), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.5, QColor(246, 249, 253, 250))
            grad.setColorAt(1.0, QColor(238, 243, 250, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Dual Soft Blue aura
            aura1 = QRadialGradient(QPointF(w - 40, 50), 220)
            aura1.setColorAt(0.0, QColor(99, 102, 241, 16))
            aura1.setColorAt(1.0, QColor(99, 102, 241, 0))
            p.fillRect(self.rect(), QBrush(aura1))

            aura2 = QRadialGradient(QPointF(40, h - 80), 200)
            aura2.setColorAt(0.0, QColor(14, 165, 233, 16))
            aura2.setColorAt(1.0, QColor(14, 165, 233, 0))
            p.fillRect(self.rect(), QBrush(aura2))

            # Micro-cross (+) coordinate grid
            cross_pen = QPen(QColor(100, 116, 139, 36), 1.0)
            p.setPen(cross_pen)
            step = 22
            for x in range(24, w - 16, step):
                for y in range(24, h - 16, step):
                    p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
                    p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))

            # Specular top highlight line
            p.setPen(QPen(QColor(255, 255, 255, 240), 1.2))
            p.drawLine(QPointF(28, 1.5), QPointF(w - 28, 1.5))

            # Luminous Divider Line
            div_y = h - 136
            div_grad = QLinearGradient(28, div_y, w - 28, div_y)
            div_grad.setColorAt(0.0, QColor(15, 23, 42, 0))
            div_grad.setColorAt(0.2, QColor(15, 23, 42, 34))
            div_grad.setColorAt(0.5, QColor(15, 23, 42, 55))
            div_grad.setColorAt(0.8, QColor(15, 23, 42, 34))
            div_grad.setColorAt(1.0, QColor(15, 23, 42, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(28, div_y), QPointF(w - 28, div_y))

            # Outer Crisp Glass Border
            p.setClipping(False)
            p.setPen(QPen(QColor(15, 23, 42, 42), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


def render_all_demos():
    brain_dir = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"

    # 1. Concept A - Dark
    app_main._CURRENT_THEME = "dark"
    w1 = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    # Replace card with Concept A
    old_card = w1.card
    card_parent_layout = old_card.parentWidget().layout().itemAt(1).layout()
    # Find card in layout
    for i in range(card_parent_layout.count()):
        if card_parent_layout.itemAt(i).widget() == old_card:
            card_idx = i
            break
    
    new_card_a_dark = ConceptAHalftoneCard(theme="dark")
    # Move children layout to new card
    card_layout = old_card.layout()
    new_card_a_dark.setLayout(card_layout)
    card_parent_layout.replaceWidget(old_card, new_card_a_dark)
    old_card.deleteLater()
    w1.card = new_card_a_dark

    w1.show()
    app.processEvents()
    out_a_dark = os.path.join(brain_dir, "demo_concept_a_dark.png")
    w1.grab().save(out_a_dark)

    # Concept A - Light
    w1._toggle_theme()
    app.processEvents()
    out_a_light = os.path.join(brain_dir, "demo_concept_a_light.png")
    w1.grab().save(out_a_light)
    w1.close()

    # 2. Concept B - Dark
    app_main._CURRENT_THEME = "dark"
    w2 = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_b = w2.card
    card_parent_layout_b = old_card_b.parentWidget().layout().itemAt(1).layout()
    new_card_b_dark = ConceptBVisionOSCard(theme="dark")
    new_card_b_dark.setLayout(old_card_b.layout())
    card_parent_layout_b.replaceWidget(old_card_b, new_card_b_dark)
    old_card_b.deleteLater()
    w2.card = new_card_b_dark

    w2.show()
    app.processEvents()
    out_b_dark = os.path.join(brain_dir, "demo_concept_b_dark.png")
    w2.grab().save(out_b_dark)

    # Concept B - Light
    w2._toggle_theme()
    app.processEvents()
    out_b_light = os.path.join(brain_dir, "demo_concept_b_light.png")
    w2.grab().save(out_b_light)
    w2.close()

    print("Rendered all 4 demo screenshots successfully!")

if __name__ == "__main__":
    render_all_demos()
