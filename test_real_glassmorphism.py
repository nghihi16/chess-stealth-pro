import os
import sys

sys.path.insert(0, r"C:\Users\Windows\ChessStealthPro")
os.chdir(r"C:\Users\Windows\ChessStealthPro")

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPixmap
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect
)
import main as app_main

app = QApplication.instance() or QApplication(sys.argv)
brain_dir = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"

class RealGlassmorphicActivationWindow(app_main.ActivationWindow):
    """
    Activation Window with TRUE Glassmorphism:
    - Window background has rich atmospheric ambient depth / misty light vignette
    - The card is truly translucent (frosted glass) with 1px delicate light border
    - Multi-layer drop shadow creates actual optical depth
    """
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)
        painter.setClipPath(path)

        w, h = float(self.width()), float(self.height())
        is_dark = (self.theme == "dark")

        # 1. Draw base artwork
        pix = self.bg_dark_pix if is_dark else self.bg_light_pix
        if not pix.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), pix)
        else:
            painter.fillRect(self.rect(), QColor("#08090d" if is_dark else "#f5f5f7"))

        # 2. Rich atmospheric light vignette behind the card area (x: 420 to 820)
        # This provides the physical background texture that allows true glassmorphism to shine!
        if is_dark:
            # Subtle deep slate/sapphire ambient atmospheric glow behind the card
            back_glow = QRadialGradient(QPointF(625, 230), 280)
            back_glow.setColorAt(0.0, QColor(30, 41, 59, 130))  # Slate-800 atmospheric haze
            back_glow.setColorAt(0.5, QColor(15, 23, 42, 80))
            back_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(400, 20, 420, 480), QBrush(back_glow))

            # Faint geometric grid lines passing behind the glass (like Image 1 & 2)
            grid_pen = QPen(QColor(255, 255, 255, 8), 1.0)
            painter.setPen(grid_pen)
            for gy in range(40, int(h - 30), 32):
                painter.drawLine(QPointF(420, gy), QPointF(w - 30, gy))
            for gx in range(430, int(w - 20), 32):
                painter.drawLine(QPointF(gx, 30), QPointF(gx, h - 30))
        else:
            # Light mode ambient atmospheric haze
            back_glow = QRadialGradient(QPointF(625, 230), 280)
            back_glow.setColorAt(0.0, QColor(226, 232, 240, 160))
            back_glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(QRectF(400, 20, 420, 480), QBrush(back_glow))

        painter.setClipping(False)

        # Window outer border
        border_pen = QPen(QColor(255, 255, 255, 28) if is_dark else QColor(0, 0, 0, 24), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)


class TrueGlassCard(QFrame):
    """
    Authentic Glassmorphism Card (as in Image 1 & 2):
    - Translucent frosted glass fill with top specular sheen
    - Multi-layered delicate 1px border
    - Optical depth
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
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)
        is_dark = (self.theme == "dark")

        if is_dark:
            # 1. Base translucent smoked glass (55% opacity - transparent enough to see the grid behind!)
            p.fillRect(self.rect(), QColor(13, 17, 28, 145))

            # 2. Specular glass sheen gradient from top to bottom
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 28))   # Top glass reflection
            grad.setColorAt(0.2, QColor(255, 255, 255, 12))
            grad.setColorAt(0.7, QColor(255, 255, 255, 4))
            grad.setColorAt(1.0, QColor(255, 255, 255, 8))
            p.fillRect(self.rect(), QBrush(grad))

            # 3. Delicate top specular glint line
            p.setPen(QPen(QColor(255, 255, 255, 100), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            # 4. Ultra-fine 1px Glassmorphic border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 95))   # Top bright
            border_grad.setColorAt(0.35, QColor(255, 255, 255, 32))  # Sides
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 12))   # Bottom subtle
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode Frosted Acrylic Glass
            p.fillRect(self.rect(), QColor(255, 255, 255, 215))

            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 120))
            grad.setColorAt(1.0, QColor(238, 243, 250, 160))
            p.fillRect(self.rect(), QBrush(grad))

            p.setPen(QPen(QColor(255, 255, 255, 255), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            border_grad.setColorAt(0.4, QColor(15, 23, 42, 38))
            border_grad.setColorAt(1.0, QColor(15, 23, 42, 18))
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


# Ultra-Refined Glassmorphism Controls Stylesheet (Matching Image 1 & 2 directly)
TRUE_GLASS_DARK_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #f5f5f7; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #94A3B8; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(255, 255, 255, 0.10); color: #ffffff; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.20); color: #EF4444; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #FFFFFF; font-size: 30px; font-weight: 800; letter-spacing: -0.025em; }
QLabel#FieldLabel { color: #94A3B8; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }

/* Translucent Glass Pill Input (Image 1 style) */
QLineEdit#KeyInput {
    background: rgba(255, 255, 255, 0.07);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 22px;
    padding: 0 18px;
    min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 1.5px solid rgba(255, 255, 255, 0.65);
    background: rgba(255, 255, 255, 0.12);
}

/* Glass Hardware ID Capsule */
QLabel#HwidDisplay {
    color: #E2E8F0;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 16px;
}

/* Glass Copy Pill */
QPushButton#CopyPillBtn {
    background: rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.24);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover {
    background: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.5);
}
QPushButton#CopyPillBtn:pressed {
    background: rgba(255, 255, 255, 0.08);
}

/* Glass Circular Social Buttons (Image 1 & 2 style) */
QPushButton#SocialIconBtn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 19px;
}
QPushButton#SocialIconBtn:hover {
    background: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.50);
}
QPushButton#SocialIconBtn:pressed {
    background: rgba(255, 255, 255, 0.05);
}

/* High-Contrast Action Bars */
QPushButton#ActivateBarBtn {
    background: #FFFFFF;
    color: #090B10;
    border: none;
    border-radius: 23px;
    min-height: 46px; max-height: 46px;
    font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
}
QPushButton#ActivateBarBtn:hover {
    background: #F1F5F9;
}
QPushButton#ActivateBarBtn:pressed {
    background: #E2E8F0;
}

QPushButton#GetKeyBarBtn {
    background: rgba(255, 255, 255, 0.06);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 23px;
    min-height: 46px; max-height: 46px;
    font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
}
QPushButton#GetKeyBarBtn:hover {
    background: rgba(255, 255, 255, 0.15);
    border-color: rgba(255, 255, 255, 0.45);
    color: #FFFFFF;
}
QPushButton#GetKeyBarBtn:pressed {
    background: rgba(255, 255, 255, 0.03);
}
"""

TRUE_GLASS_LIGHT_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #090B10; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #64748B; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(0, 0, 0, 0.07); color: #090B10; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.15); color: #EF4444; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #0F172A; font-size: 30px; font-weight: 800; letter-spacing: -0.025em; }
QLabel#FieldLabel { color: #475569; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }

QLineEdit#KeyInput {
    background: rgba(255, 255, 255, 0.92);
    color: #0F172A;
    border: 1.5px solid #CBD5E1;
    border-radius: 22px;
    padding: 0 18px;
    min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 2px solid #0071E3;
    background: #FFFFFF;
}

QLabel#HwidDisplay {
    color: #0F172A;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: rgba(241, 245, 249, 0.85);
    border: 1.5px solid #CBD5E1;
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 16px;
}

QPushButton#CopyPillBtn {
    background: #0F172A;
    color: #FFFFFF;
    border: 1px solid #0F172A;
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover {
    background: #0071E3; border-color: #0071E3;
}

QPushButton#SocialIconBtn {
    background: rgba(255, 255, 255, 0.85);
    border: 1.5px solid #CBD5E1;
    border-radius: 19px;
}
QPushButton#SocialIconBtn:hover {
    background: #FFFFFF;
    border-color: #0F172A;
}

QPushButton#ActivateBarBtn {
    background: #0F172A;
    color: #FFFFFF;
    border: none;
    border-radius: 23px;
    min-height: 46px; max-height: 46px;
    font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
}
QPushButton#ActivateBarBtn:hover {
    background: #1E293B;
}

QPushButton#GetKeyBarBtn {
    background: rgba(255, 255, 255, 0.85);
    color: #0F172A;
    border: 1.5px solid #CBD5E1;
    border-radius: 23px;
    min-height: 46px; max-height: 46px;
    font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
}
QPushButton#GetKeyBarBtn:hover {
    background: #FFFFFF;
    border-color: #0F172A;
}
"""

def render_real_glassmorphism():
    # 1. Dark
    app_main._CURRENT_THEME = "dark"
    w_dark = RealGlassmorphicActivationWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_d = w_dark.card
    body_layout_d = w_dark.layout().itemAt(1).layout()
    new_card_d = TrueGlassCard(theme="dark")
    new_card_d.setLayout(old_card_d.layout())
    body_layout_d.replaceWidget(old_card_d, new_card_d)
    old_card_d.deleteLater()
    w_dark.card = new_card_d

    w_dark.setStyleSheet(TRUE_GLASS_DARK_QSS)

    shadow_d = QGraphicsDropShadowEffect(w_dark.card)
    shadow_d.setBlurRadius(42)
    shadow_d.setOffset(0, 14)
    shadow_d.setColor(QColor(0, 0, 0, 160))
    w_dark.card.setGraphicsEffect(shadow_d)

    w_dark.show()
    w_dark.setWindowOpacity(1.0)
    app.processEvents()
    dark_out = os.path.join(brain_dir, "real_glassmorphism_dark.png")
    w_dark.grab().save(dark_out)
    w_dark.close()

    # 2. Light
    app_main._CURRENT_THEME = "light"
    w_light = RealGlassmorphicActivationWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_l = w_light.card
    body_layout_l = w_light.layout().itemAt(1).layout()
    new_card_l = TrueGlassCard(theme="light")
    new_card_l.setLayout(old_card_l.layout())
    body_layout_l.replaceWidget(old_card_l, new_card_l)
    old_card_l.deleteLater()
    w_light.card = new_card_l

    w_light.setStyleSheet(TRUE_GLASS_LIGHT_QSS)

    shadow_l = QGraphicsDropShadowEffect(w_light.card)
    shadow_l.setBlurRadius(36)
    shadow_l.setOffset(0, 12)
    shadow_l.setColor(QColor(0, 0, 0, 42))
    w_light.card.setGraphicsEffect(shadow_l)

    w_light.show()
    w_light.setWindowOpacity(1.0)
    app.processEvents()
    light_out = os.path.join(brain_dir, "real_glassmorphism_light.png")
    w_light.grab().save(light_out)
    w_light.close()

    print("Rendered real glassmorphism dark & light successfully!")

if __name__ == "__main__":
    render_real_glassmorphism()
