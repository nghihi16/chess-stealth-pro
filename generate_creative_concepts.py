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
brain_dir = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"

# Load Queen silhouette for halftone
queen_raw = Image.open(r"C:\Users\Windows\ChessStealthPro\assets\queen_light.png").convert("RGBA")
qw, qh = 150, 300
queen_resized = queen_raw.resize((qw, qh), Image.Resampling.LANCZOS)
queen_alpha = queen_resized.split()[3]

def draw_glass_sheen(p, w, h, is_dark=True):
    # Top specular line
    spec_pen = QPen(QColor(255, 255, 255, 120 if is_dark else 240), 1.5)
    p.setPen(spec_pen)
    p.drawLine(QPointF(28, 1.5), QPointF(w - 28, 1.5))

    # Left specular reflection arc
    left_spec = QLinearGradient(1.5, 28, 1.5, 160)
    left_spec.setColorAt(0.0, QColor(255, 255, 255, 90 if is_dark else 180))
    left_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setPen(QPen(QBrush(left_spec), 1.2))
    p.drawLine(QPointF(1.5, 28), QPointF(1.5, 160))

    # Diagonal glass glare
    glare_path = QPainterPath()
    glare_path.moveTo(0, 0)
    glare_path.lineTo(w * 0.75, 0)
    glare_path.lineTo(0, h * 0.65)
    glare_path.closeSubpath()
    glare_grad = QLinearGradient(0, 0, w * 0.5, h * 0.5)
    glare_grad.setColorAt(0.0, QColor(255, 255, 255, 20 if is_dark else 50))
    glare_grad.setColorAt(0.4, QColor(255, 255, 255, 7 if is_dark else 18))
    glare_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(glare_path, QBrush(glare_grad))

def draw_luminous_divider(p, w, div_y, is_dark=True):
    div_grad = QLinearGradient(24, div_y, w - 24, div_y)
    if is_dark:
        div_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        div_grad.setColorAt(0.2, QColor(255, 255, 255, 40))
        div_grad.setColorAt(0.5, QColor(255, 255, 255, 100))
        div_grad.setColorAt(0.8, QColor(255, 255, 255, 40))
        div_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    else:
        div_grad.setColorAt(0.0, QColor(15, 23, 42, 0))
        div_grad.setColorAt(0.2, QColor(15, 23, 42, 40))
        div_grad.setColorAt(0.5, QColor(15, 23, 42, 90))
        div_grad.setColorAt(0.8, QColor(15, 23, 42, 40))
        div_grad.setColorAt(1.0, QColor(15, 23, 42, 0))
    p.setPen(QPen(QBrush(div_grad), 1.0))
    p.drawLine(QPointF(24, div_y), QPointF(w - 24, div_y))

    flare_col = QColor(255, 255, 255, 180) if is_dark else QColor(15, 23, 42, 130)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(flare_col)
    p.drawEllipse(QPointF(w * 0.5, div_y), 1.8, 1.8)


class Concept1Card(QFrame):
    """Concept 1: Cyber Matrix Glass (Image 1 Halftone + Specular Glare)"""
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
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)
        is_dark = (self.theme == "dark")

        if is_dark:
            # Rich Smoked Glass
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(26, 32, 46, 238))
            grad.setColorAt(0.45, QColor(14, 17, 26, 245))
            grad.setColorAt(1.0, QColor(8, 10, 16, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Cyan-Blue Aurora Refraction
            aura = QRadialGradient(QPointF(w * 0.78, 55), 250)
            aura.setColorAt(0.0, QColor(56, 189, 248, 48))
            aura.setColorAt(0.55, QColor(99, 102, 241, 20))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            # Halftone Queen Matrix
            grid_step = 14
            qx0 = int(w - qw - 10)
            qy0 = 15
            p.setPen(Qt.PenStyle.NoPen)
            for gy in range(16, int(h - 138), grid_step):
                for gx in range(18, int(w - 14), grid_step):
                    ix, iy = gx - qx0, gy - qy0
                    q_val = 0.0
                    if 0 <= ix < qw and 0 <= iy < qh:
                        q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                    fade_x = max(0.0, min(1.0, (gx - 150) / 140.0))
                    fade_y = max(0.0, min(1.0, 1.0 - (gy - 190) / 75.0 if gy > 190 else 1.0))
                    weight = q_val * fade_x * fade_y

                    if weight > 0.06:
                        dot_r = 0.9 + weight * 2.5
                        alpha = int(35 + weight * 175)
                        p.setBrush(QColor(186, 230, 253, alpha))
                        p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                    else:
                        p.setBrush(QColor(255, 255, 255, 12))
                        p.drawEllipse(QPointF(gx, gy), 0.8, 0.8)

            draw_glass_sheen(p, w, h, is_dark=True)
            draw_luminous_divider(p, w, h - 134, is_dark=True)

            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 95))
            border_grad.setColorAt(0.35, QColor(255, 255, 255, 35))
            border_grad.setColorAt(0.7, QColor(56, 189, 248, 55))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 22))
            p.setPen(QPen(QBrush(border_grad), 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.45, QColor(246, 249, 253, 250))
            grad.setColorAt(1.0, QColor(236, 242, 250, 255))
            p.fillRect(self.rect(), QBrush(grad))

            aura = QRadialGradient(QPointF(w * 0.78, 55), 250)
            aura.setColorAt(0.0, QColor(0, 113, 227, 28))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            grid_step = 14
            qx0 = int(w - qw - 10)
            qy0 = 15
            p.setPen(Qt.PenStyle.NoPen)
            for gy in range(16, int(h - 138), grid_step):
                for gx in range(18, int(w - 14), grid_step):
                    ix, iy = gx - qx0, gy - qy0
                    q_val = 0.0
                    if 0 <= ix < qw and 0 <= iy < qh:
                        q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                    fade_x = max(0.0, min(1.0, (gx - 150) / 140.0))
                    fade_y = max(0.0, min(1.0, 1.0 - (gy - 190) / 75.0 if gy > 190 else 1.0))
                    weight = q_val * fade_x * fade_y

                    if weight > 0.06:
                        dot_r = 0.9 + weight * 2.5
                        alpha = int(45 + weight * 160)
                        p.setBrush(QColor(51, 65, 85, alpha))
                        p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                    else:
                        p.setBrush(QColor(148, 163, 184, 32))
                        p.drawEllipse(QPointF(gx, gy), 0.8, 0.8)

            draw_glass_sheen(p, w, h, is_dark=False)
            draw_luminous_divider(p, w, h - 134, is_dark=False)

            p.setClipping(False)
            p.setPen(QPen(QColor(15, 23, 42, 45), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


class Concept2Card(QFrame):
    """Concept 2: VisionOS Prism Glass"""
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
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)
        is_dark = (self.theme == "dark")

        if is_dark:
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(30, 35, 52, 240))
            grad.setColorAt(0.5, QColor(16, 19, 28, 248))
            grad.setColorAt(1.0, QColor(9, 11, 17, 255))
            p.fillRect(self.rect(), QBrush(grad))

            aura1 = QRadialGradient(QPointF(w - 30, 45), 230)
            aura1.setColorAt(0.0, QColor(139, 92, 246, 36))
            aura1.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura1))

            aura2 = QRadialGradient(QPointF(45, h - 70), 210)
            aura2.setColorAt(0.0, QColor(56, 189, 248, 28))
            aura2.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura2))

            cross_pen = QPen(QColor(255, 255, 255, 22), 1.0)
            p.setPen(cross_pen)
            step = 22
            for x in range(24, int(w - 16), step):
                for y in range(24, int(h - 138), step):
                    p.drawLine(QPointF(x - 2.5, y), QPointF(x + 2.5, y))
                    p.drawLine(QPointF(x, y - 2.5), QPointF(x, y + 2.5))

            draw_glass_sheen(p, w, h, is_dark=True)
            draw_luminous_divider(p, w, h - 134, is_dark=True)

            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 100))
            border_grad.setColorAt(0.4, QColor(255, 255, 255, 35))
            border_grad.setColorAt(0.8, QColor(167, 139, 250, 50))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 20))
            p.setPen(QPen(QBrush(border_grad), 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.5, QColor(246, 249, 253, 250))
            grad.setColorAt(1.0, QColor(238, 243, 250, 255))
            p.fillRect(self.rect(), QBrush(grad))

            aura = QRadialGradient(QPointF(w - 30, 45), 230)
            aura.setColorAt(0.0, QColor(99, 102, 241, 20))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            cross_pen = QPen(QColor(100, 116, 139, 38), 1.0)
            p.setPen(cross_pen)
            step = 22
            for x in range(24, int(w - 16), step):
                for y in range(24, int(h - 138), step):
                    p.drawLine(QPointF(x - 2.5, y), QPointF(x + 2.5, y))
                    p.drawLine(QPointF(x, y - 2.5), QPointF(x, y + 2.5))

            draw_glass_sheen(p, w, h, is_dark=False)
            draw_luminous_divider(p, w, h - 134, is_dark=False)

            p.setClipping(False)
            p.setPen(QPen(QColor(15, 23, 42, 45), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


class Concept3Card(QFrame):
    """Concept 3: Neon Stealth Glass (Laser Cyan Border + Circuit Nodes)"""
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
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)
        is_dark = (self.theme == "dark")

        if is_dark:
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(20, 25, 38, 242))
            grad.setColorAt(0.5, QColor(12, 15, 23, 248))
            grad.setColorAt(1.0, QColor(6, 8, 14, 255))
            p.fillRect(self.rect(), QBrush(grad))

            aura = QRadialGradient(QPointF(w * 0.8, 50), 260)
            aura.setColorAt(0.0, QColor(0, 210, 255, 48))
            aura.setColorAt(0.6, QColor(0, 113, 227, 20))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            p.setPen(Qt.PenStyle.NoPen)
            step = 18
            for x in range(20, int(w - 14), step):
                for y in range(20, int(h - 138), step):
                    is_node = ((x + y) % (step * 3) == 0)
                    if is_node:
                        p.setBrush(QColor(56, 189, 248, 70))
                        p.drawEllipse(QPointF(x, y), 1.5, 1.5)
                    else:
                        p.setBrush(QColor(255, 255, 255, 12))
                        p.drawEllipse(QPointF(x, y), 0.8, 0.8)

            draw_glass_sheen(p, w, h, is_dark=True)
            draw_luminous_divider(p, w, h - 134, is_dark=True)

            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(56, 189, 248, 130))
            border_grad.setColorAt(0.4, QColor(255, 255, 255, 45))
            border_grad.setColorAt(0.8, QColor(56, 189, 248, 80))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 20))
            p.setPen(QPen(QBrush(border_grad), 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)
        else:
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.5, QColor(245, 249, 254, 250))
            grad.setColorAt(1.0, QColor(237, 243, 251, 255))
            p.fillRect(self.rect(), QBrush(grad))

            aura = QRadialGradient(QPointF(w * 0.8, 50), 260)
            aura.setColorAt(0.0, QColor(0, 163, 255, 28))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            p.setPen(Qt.PenStyle.NoPen)
            step = 18
            for x in range(20, int(w - 14), step):
                for y in range(20, int(h - 138), step):
                    is_node = ((x + y) % (step * 3) == 0)
                    if is_node:
                        p.setBrush(QColor(0, 113, 227, 70))
                        p.drawEllipse(QPointF(x, y), 1.5, 1.5)
                    else:
                        p.setBrush(QColor(148, 163, 184, 32))
                        p.drawEllipse(QPointF(x, y), 0.8, 0.8)

            draw_glass_sheen(p, w, h, is_dark=False)
            draw_luminous_divider(p, w, h - 134, is_dark=False)

            p.setClipping(False)
            p.setPen(QPen(QColor(0, 113, 227, 65), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


# Custom Glass Stylesheet for Controls (Lens buttons, Frosted inputs, High-gloss buttons)
GLASS_DARK_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #f5f5f7; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #a1a1a6; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(255, 255, 255, 0.10); color: #ffffff; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(255, 255, 255, 0.16); color: #ffffff; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #ffffff; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
QLabel#FieldLabel { color: #94A3B8; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; }

/* Frosted Glass Pill Input */
QLineEdit#KeyInput {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.08), stop:1 rgba(255, 255, 255, 0.03));
    color: #ffffff;
    border: 1.5px solid rgba(255, 255, 255, 0.20);
    border-radius: 22px;
    padding: 0 20px;
    min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 1.5px solid #38BDF8;
    background: rgba(56, 189, 248, 0.08);
}

/* Glass Hardware Capsule */
QLabel#HwidDisplay {
    color: #E2E8F0;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.05);
    border: 1.5px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px;
}

/* Crystal Glass Copy Pill */
QPushButton#CopyPillBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.16), stop:1 rgba(255, 255, 255, 0.06));
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover {
    background: #38BDF8; color: #090B10; border-color: #38BDF8;
}

/* Convex Glass Lens Social Buttons */
QPushButton#SocialIconBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.15), stop:1 rgba(255, 255, 255, 0.04));
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    border-radius: 19px;
}
QPushButton#SocialIconBtn:hover {
    background: rgba(56, 189, 248, 0.25);
    border-color: #38BDF8;
}

/* Luminous Action Bars */
QPushButton#ActivateBarBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #E2E8F0);
    color: #090B10;
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-radius: 23px;
    min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.1em;
}
QPushButton#ActivateBarBtn:hover {
    background: #FFFFFF;
}

QPushButton#GetKeyBarBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.10), stop:1 rgba(255, 255, 255, 0.03));
    color: #ffffff;
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    border-radius: 23px;
    min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.1em;
}
QPushButton#GetKeyBarBtn:hover {
    background: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.5);
    color: #ffffff;
}
"""

GLASS_LIGHT_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #090B10; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #64748B; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(0, 0, 0, 0.07); color: #090B10; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.15); color: #EF4444; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #0F172A; font-size: 32px; font-weight: 800; letter-spacing: -0.02em; }
QLabel#FieldLabel { color: #475569; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; }

QLineEdit#KeyInput {
    background: #FFFFFF; color: #0F172A;
    border: 1.5px solid #CBD5E1; border-radius: 22px;
    padding: 0 20px; min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 2px solid #0071E3; background: #FFFFFF;
}

QLabel#HwidDisplay {
    color: #0F172A; font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: #F1F5F9; border: 1.5px solid #CBD5E1; border-radius: 20px;
    min-height: 40px; max-height: 40px; padding: 0 18px;
}

QPushButton#CopyPillBtn {
    background: #0F172A; color: #FFFFFF; border: 1px solid #0F172A; border-radius: 20px;
    min-height: 40px; max-height: 40px; padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover { background: #0071E3; border-color: #0071E3; }

QPushButton#SocialIconBtn {
    background: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 19px;
}
QPushButton#SocialIconBtn:hover { background: #F8FAFC; border-color: #0F172A; }

QPushButton#ActivateBarBtn {
    background: #0F172A; color: #FFFFFF; border: none; border-radius: 23px;
    min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.1em;
}
QPushButton#ActivateBarBtn:hover { background: #1E293B; }

QPushButton#GetKeyBarBtn {
    background: #FFFFFF; color: #0F172A; border: 1.5px solid #CBD5E1; border-radius: 23px;
    min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.1em;
}
QPushButton#GetKeyBarBtn:hover { background: #F8FAFC; border-color: #0F172A; }
"""

def generate_styled_demos():
    concepts = [
        ("concept_1_cyber_matrix", Concept1Card),
        ("concept_2_visionos_prism", Concept2Card),
        ("concept_3_neon_stealth", Concept3Card),
    ]

    for name, card_cls in concepts:
        # 1. Dark Render
        app_main._CURRENT_THEME = "dark"
        w_dark = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
        old_card_d = w_dark.card
        body_layout_d = w_dark.layout().itemAt(1).layout()
        new_card_d = card_cls(theme="dark")
        new_card_d.setLayout(old_card_d.layout())
        body_layout_d.replaceWidget(old_card_d, new_card_d)
        old_card_d.deleteLater()
        w_dark.card = new_card_d

        w_dark.setStyleSheet(GLASS_DARK_QSS)

        shadow_d = QGraphicsDropShadowEffect(w_dark.card)
        shadow_d.setBlurRadius(36)
        shadow_d.setOffset(0, 10)
        shadow_d.setColor(QColor(0, 0, 0, 160))
        w_dark.card.setGraphicsEffect(shadow_d)

        w_dark.show()
        w_dark.setWindowOpacity(1.0)
        app.processEvents()
        dark_file = os.path.join(brain_dir, f"{name}_dark.png")
        w_dark.grab().save(dark_file)
        w_dark.close()

        # 2. Light Render (Fresh instance with CURRENT_THEME = 'light')
        app_main._CURRENT_THEME = "light"
        w_light = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
        old_card_l = w_light.card
        body_layout_l = w_light.layout().itemAt(1).layout()
        new_card_l = card_cls(theme="light")
        new_card_l.setLayout(old_card_l.layout())
        body_layout_l.replaceWidget(old_card_l, new_card_l)
        old_card_l.deleteLater()
        w_light.card = new_card_l

        w_light.setStyleSheet(GLASS_LIGHT_QSS)

        shadow_l = QGraphicsDropShadowEffect(w_light.card)
        shadow_l.setBlurRadius(32)
        shadow_l.setOffset(0, 10)
        shadow_l.setColor(QColor(0, 0, 0, 48))
        w_light.card.setGraphicsEffect(shadow_l)

        w_light.show()
        w_light.setWindowOpacity(1.0)
        app.processEvents()
        light_file = os.path.join(brain_dir, f"{name}_light.png")
        w_light.grab().save(light_file)
        w_light.close()

        print(f"Generated clean {name} dark & light")

if __name__ == "__main__":
    generate_styled_demos()
    print("ALL ENHANCED DEMOS COMPLETE!")
