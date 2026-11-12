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

class AuthenticGlassWindow(app_main.ActivationWindow):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)
        painter.setClipPath(path)

        w, h = float(self.width()), float(self.height())
        is_dark = (self.theme == "dark")

        pix = self.bg_dark_pix if is_dark else self.bg_light_pix
        if not pix.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), pix)
        else:
            painter.fillRect(self.rect(), QColor("#08090d" if is_dark else "#f5f5f7"))

        # Soft ambient glassmorphism backlight orbs behind the card (x: 400 to 820)
        if is_dark:
            # Orb 1: Upper-right deep royal sapphire
            orb1 = QRadialGradient(QPointF(740, 90), 220)
            orb1.setColorAt(0.0, QColor(37, 99, 235, 95))   # Royal Blue
            orb1.setColorAt(0.5, QColor(29, 78, 216, 45))
            orb1.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(410, 20, 410, 480), QBrush(orb1))

            # Orb 2: Lower-left soft cyan
            orb2 = QRadialGradient(QPointF(470, 420), 190)
            orb2.setColorAt(0.0, QColor(14, 165, 233, 75))  # Cyan/Sky
            orb2.setColorAt(0.6, QColor(14, 165, 233, 20))
            orb2.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(QRectF(410, 20, 410, 480), QBrush(orb2))
        else:
            # Light mode ambient orbs
            orb1 = QRadialGradient(QPointF(740, 90), 220)
            orb1.setColorAt(0.0, QColor(186, 230, 253, 140)) # Soft Sky
            orb1.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(QRectF(410, 20, 410, 480), QBrush(orb1))

            orb2 = QRadialGradient(QPointF(470, 420), 190)
            orb2.setColorAt(0.0, QColor(224, 231, 255, 120)) # Soft Indigo
            orb2.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(QRectF(410, 20, 410, 480), QBrush(orb2))

        painter.setClipping(False)

        border_pen = QPen(QColor(255, 255, 255, 28) if is_dark else QColor(0, 0, 0, 24), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)


class AuthenticGlassCard(QFrame):
    """
    True Dribbble/Apple-Grade Glassmorphism
    - 135-degree diagonal frosted glass gradient
    - Crisp 1px luminous border
    - Specular top glare line
    - Translucent depth
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
            # 1. Smoked Glass Base (Frosted Acrylic)
            p.fillRect(self.rect(), QColor(15, 20, 32, 130))

            # 2. 135-degree Glass Sheen (Diagonal light bounce)
            glass_grad = QLinearGradient(0, 0, w, h)
            glass_grad.setColorAt(0.0, QColor(255, 255, 255, 36))  # Luminous top-left
            glass_grad.setColorAt(0.35, QColor(255, 255, 255, 14))
            glass_grad.setColorAt(0.7, QColor(255, 255, 255, 6))
            glass_grad.setColorAt(1.0, QColor(255, 255, 255, 14))
            p.fillRect(self.rect(), QBrush(glass_grad))

            # 3. Top Specular Glint Line
            p.setPen(QPen(QColor(255, 255, 255, 110), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            # 4. Authentic 1px Glassmorphic Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 120))  # Bright top-left
            border_grad.setColorAt(0.4, QColor(255, 255, 255, 40))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 16))   # Soft bottom-right
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode Frosted Glass
            p.fillRect(self.rect(), QColor(255, 255, 255, 195))

            glass_grad = QLinearGradient(0, 0, w, h)
            glass_grad.setColorAt(0.0, QColor(255, 255, 255, 180))
            glass_grad.setColorAt(0.5, QColor(245, 248, 253, 140))
            glass_grad.setColorAt(1.0, QColor(235, 241, 250, 160))
            p.fillRect(self.rect(), QBrush(glass_grad))

            p.setPen(QPen(QColor(255, 255, 255, 255), 1.0))
            p.drawLine(QPointF(24, 1.0), QPointF(w - 24, 1.0))

            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            border_grad.setColorAt(0.5, QColor(15, 23, 42, 40))
            border_grad.setColorAt(1.0, QColor(15, 23, 42, 20))
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


GLASS_DARK_STYLESHEET = """
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

/* Translucent Frosted Glass Pill Input */
QLineEdit#KeyInput {
    background: rgba(255, 255, 255, 0.07);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 22px;
    padding: 0 18px;
    min-height: 44px; max-height: 44px;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
}
QLineEdit#KeyInput:focus {
    border: 1.5px solid rgba(255, 255, 255, 0.70);
    background: rgba(255, 255, 255, 0.12);
}

/* Glass Hardware ID Capsule */
QLabel#HwidDisplay {
    color: #E2E8F0;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 16px;
}

/* Glass Copy Pill */
QPushButton#CopyPillBtn {
    background: rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 20px;
    min-height: 40px; max-height: 40px;
    padding: 0 18px; font-size: 12px; font-weight: 700;
}
QPushButton#CopyPillBtn:hover {
    background: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.50);
}

/* Glass Circular Social Buttons */
QPushButton#SocialIconBtn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 19px;
}
QPushButton#SocialIconBtn:hover {
    background: rgba(255, 255, 255, 0.18);
    border-color: rgba(255, 255, 255, 0.55);
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
"""

GLASS_LIGHT_STYLESHEET = """
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
    background: rgba(255, 255, 255, 0.94);
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
    background: rgba(241, 245, 249, 0.90);
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
    background: rgba(255, 255, 255, 0.90);
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
    background: rgba(255, 255, 255, 0.90);
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

def generate_true_glassmorphism():
    # 1. Dark Render
    app_main._CURRENT_THEME = "dark"
    w_dark = AuthenticGlassWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_d = w_dark.card
    body_layout_d = w_dark.layout().itemAt(1).layout()
    new_card_d = AuthenticGlassCard(theme="dark")
    new_card_d.setLayout(old_card_d.layout())
    body_layout_d.replaceWidget(old_card_d, new_card_d)
    old_card_d.deleteLater()
    w_dark.card = new_card_d

    w_dark.setStyleSheet(GLASS_DARK_STYLESHEET)

    # Ambient drop shadow: diffuse, floating acrylic glass
    shadow_d = QGraphicsDropShadowEffect(w_dark.card)
    shadow_d.setBlurRadius(46)
    shadow_d.setOffset(0, 16)
    shadow_d.setColor(QColor(0, 0, 0, 170))
    w_dark.card.setGraphicsEffect(shadow_d)

    w_dark.show()
    if hasattr(w_dark, "_in_anim"):
        w_dark._in_anim.stop()
    w_dark.setWindowOpacity(1.0)
    app.processEvents()
    dark_out = os.path.join(brain_dir, "glassmorphism_v3_dark.png")
    w_dark.grab().save(dark_out)
    w_dark.close()

    # 2. Light Render
    app_main._CURRENT_THEME = "light"
    w_light = AuthenticGlassWindow("A3F9-27C1-88D0", lambda k: None)
    old_card_l = w_light.card
    body_layout_l = w_light.layout().itemAt(1).layout()
    new_card_l = AuthenticGlassCard(theme="light")
    new_card_l.setLayout(old_card_l.layout())
    body_layout_l.replaceWidget(old_card_l, new_card_l)
    old_card_l.deleteLater()
    w_light.card = new_card_l

    w_light.setStyleSheet(GLASS_LIGHT_STYLESHEET)

    shadow_l = QGraphicsDropShadowEffect(w_light.card)
    shadow_l.setBlurRadius(36)
    shadow_l.setOffset(0, 12)
    shadow_l.setColor(QColor(0, 0, 0, 36))
    w_light.card.setGraphicsEffect(shadow_l)

    w_light.show()
    if hasattr(w_light, "_in_anim"):
        w_light._in_anim.stop()
    w_light.setWindowOpacity(1.0)
    app.processEvents()
    light_out = os.path.join(brain_dir, "glassmorphism_v3_light.png")
    w_light.grab().save(light_out)
    w_light.close()

    print("Rendered authentic glassmorphism v3 successfully!")

if __name__ == "__main__":
    generate_true_glassmorphism()
