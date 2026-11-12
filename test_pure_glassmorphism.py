import os
import sys

sys.path.insert(0, r"C:\Users\Windows\ChessStealthPro")
os.chdir(r"C:\Users\Windows\ChessStealthPro")

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPixmap, QFont
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect
)
import main as app_main

app = QApplication.instance() or QApplication(sys.argv)
brain_dir = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"

class PureGlassmorphismCard(QFrame):
    """
    Pure Glassmorphism Card Container
    - True optical translucency (no heavy opaque fills)
    - Delicate 1px specular gradient border (top bright, bottom subtle)
    - Soft atmospheric background illumination under the glass
    - Zero gimmicks / zero visual noise
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

        # 1. Rounded rectangle clip path
        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)
        is_dark = (self.theme == "dark")

        if is_dark:
            # Base smoked translucent tint (allows background depth to breathe through)
            p.fillRect(self.rect(), QColor(14, 18, 28, 175))

            # Vertical glass sheen gradient (top specular light catching the surface)
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 24))
            grad.setColorAt(0.3, QColor(255, 255, 255, 10))
            grad.setColorAt(0.7, QColor(255, 255, 255, 4))
            grad.setColorAt(1.0, QColor(255, 255, 255, 8))
            p.fillRect(self.rect(), QBrush(grad))

            # Subtle top-edge light glint
            p.setPen(QPen(QColor(255, 255, 255, 85), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            # Crisp 1px Glassmorphic Specular Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 80))   # Light from above
            border_grad.setColorAt(0.4, QColor(255, 255, 255, 28))   # Sides
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 10))   # Bottom
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode: Frosted Acrylic Glass
            p.fillRect(self.rect(), QColor(255, 255, 255, 215))

            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 120))
            grad.setColorAt(1.0, QColor(238, 242, 248, 140))
            p.fillRect(self.rect(), QBrush(grad))

            # Top light glint
            p.setPen(QPen(QColor(255, 255, 255, 250), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            # Crisp 1px Glass Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            border_grad.setColorAt(0.5, QColor(15, 23, 42, 35))
            border_grad.setColorAt(1.0, QColor(15, 23, 42, 20))
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


# Minimalist, Tasteful Glassmorphism QSS
PURE_GLASS_DARK_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #f5f5f7; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #94A3B8; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(255, 255, 255, 0.10); color: #ffffff; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.20); color: #EF4444; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #ffffff; font-size: 30px; font-weight: 800; letter-spacing: -0.03em; }
QLabel#FieldLabel { color: #94A3B8; font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }

/* Translucent Glass Pill Input */
QLineEdit#KeyInput {
    background: rgba(255, 255, 255, 0.06);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 22px;
    padding: 0 18px;
    min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 1.5px solid rgba(255, 255, 255, 0.65);
    background: rgba(255, 255, 255, 0.10);
}

/* Glass Hardware ID Capsule */
QLabel#HwidDisplay {
    color: #E2E8F0;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.13);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 16px;
}

/* Glass Copy Pill */
QPushButton#CopyPillBtn {
    background: rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover {
    background: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.45);
}
QPushButton#CopyPillBtn:pressed {
    background: rgba(255, 255, 255, 0.08);
}

/* Glass Circular Social Buttons */
QPushButton#SocialIconBtn {
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 19px;
}
QPushButton#SocialIconBtn:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.45);
}
QPushButton#SocialIconBtn:pressed {
    background: rgba(255, 255, 255, 0.04);
}

/* Action Bars: Solid High-Contrast ACTIVATE + Glass GET KEY */
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
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 23px;
    min-height: 46px; max-height: 46px;
    font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
}
QPushButton#GetKeyBarBtn:hover {
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.42);
    color: #FFFFFF;
}
QPushButton#GetKeyBarBtn:pressed {
    background: rgba(255, 255, 255, 0.03);
}
"""

PURE_GLASS_LIGHT_QSS = """
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
QLabel#BrandTitle { color: #090B10; font-size: 14px; font-weight: 700; }
QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
    background-color: transparent; color: #64748B; border: none; border-radius: 6px; font-size: 13px; font-weight: 700;
}
QPushButton#WindowCtrlBtn:hover { background-color: rgba(0, 0, 0, 0.07); color: #090B10; }
QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.15); color: #EF4444; }

QFrame#FrostedCard { background-color: transparent; border: none; }
QLabel#ActivateTitle { color: #0F172A; font-size: 30px; font-weight: 800; letter-spacing: -0.03em; }
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

def render_pure_glassmorphism():
    # 1. Dark Mode
    app_main._CURRENT_THEME = "dark"
    w_dark = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_d = w_dark.card
    body_layout_d = w_dark.layout().itemAt(1).layout()
    new_card_d = PureGlassmorphismCard(theme="dark")
    new_card_d.setLayout(old_card_d.layout())
    body_layout_d.replaceWidget(old_card_d, new_card_d)
    old_card_d.deleteLater()
    w_dark.card = new_card_d

    w_dark.setStyleSheet(PURE_GLASS_DARK_QSS)

    # Ambient drop shadow: diffuse, floating acrylic glass
    shadow_d = QGraphicsDropShadowEffect(w_dark.card)
    shadow_d.setBlurRadius(42)
    shadow_d.setOffset(0, 12)
    shadow_d.setColor(QColor(0, 0, 0, 140))
    w_dark.card.setGraphicsEffect(shadow_d)

    w_dark.show()
    w_dark.setWindowOpacity(1.0)
    app.processEvents()
    dark_out = os.path.join(brain_dir, "glassmorphism_pure_dark.png")
    w_dark.grab().save(dark_out)
    w_dark.close()

    # 2. Light Mode
    app_main._CURRENT_THEME = "light"
    w_light = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_l = w_light.card
    body_layout_l = w_light.layout().itemAt(1).layout()
    new_card_l = PureGlassmorphismCard(theme="light")
    new_card_l.setLayout(old_card_l.layout())
    body_layout_l.replaceWidget(old_card_l, new_card_l)
    old_card_l.deleteLater()
    w_light.card = new_card_l

    w_light.setStyleSheet(PURE_GLASS_LIGHT_QSS)

    shadow_l = QGraphicsDropShadowEffect(w_light.card)
    shadow_l.setBlurRadius(36)
    shadow_l.setOffset(0, 10)
    shadow_l.setColor(QColor(0, 0, 0, 36))
    w_light.card.setGraphicsEffect(shadow_l)

    w_light.show()
    w_light.setWindowOpacity(1.0)
    app.processEvents()
    light_out = os.path.join(brain_dir, "glassmorphism_pure_light.png")
    w_light.grab().save(light_out)
    w_light.close()

    print("Rendered pure glassmorphism dark & light successfully!")

if __name__ == "__main__":
    render_pure_glassmorphism()
