import os
import sys
import math
from PIL import Image

sys.path.insert(0, r"C:\Users\Windows\ChessStealthPro")
os.chdir(r"C:\Users\Windows\ChessStealthPro")

from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
    QPixmap, QFont, QIcon, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect
)
import main as app_main

app = QApplication.instance() or QApplication(sys.argv)

brain_dir = r"C:\Users\Windows\.gemini\antigravity-cli\brain\cc3b4c1b-8ad3-4a28-9821-be072a60b176"

# Load Queen image for halftone watermark
queen_raw = Image.open(r"C:\Users\Windows\ChessStealthPro\assets\queen_light.png").convert("RGBA")
qw, qh = 160, 320
queen_resized = queen_raw.resize((qw, qh), Image.Resampling.LANCZOS)
queen_alpha = queen_resized.split()[3]

class CreativeGlassCard(QFrame):
    """
    Ultra-Creative Frosted Cyber Glass Card
    - Ambient backdrop aura
    - Top specular corner light reflection
    - Halftone chess watermark positioned cleanly on the upper-right behind Key Login & social icons
    - Luminous horizontal separator (Image 2)
    - Prismatic outer border
    """
    def __init__(self, mode="halftone", theme="dark", parent=None):
        super().__init__(parent)
        self.mode = mode # 'halftone' or 'visionos' or 'cyberpunk'
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
        w = float(self.width())
        h = float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)

        if self.theme == "dark":
            # 1. Smoked Glass Base with Rich Translucency
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(25, 30, 44, 230))
            grad.setColorAt(0.45, QColor(14, 17, 26, 240))
            grad.setColorAt(1.0, QColor(7, 9, 15, 252))
            p.fillRect(self.rect(), QBrush(grad))

            # 2. Ambient Refraction Aura inside the glass
            if self.mode == "cyberpunk":
                aura = QRadialGradient(QPointF(w * 0.85, 45), 260)
                aura.setColorAt(0.0, QColor(0, 210, 255, 38))
                aura.setColorAt(0.5, QColor(99, 102, 241, 18))
                aura.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.fillRect(self.rect(), QBrush(aura))
            elif self.mode == "halftone":
                aura = QRadialGradient(QPointF(w - 60, 70), 220)
                aura.setColorAt(0.0, QColor(56, 189, 248, 30))
                aura.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.fillRect(self.rect(), QBrush(aura))
            else: # visionos
                aura = QRadialGradient(QPointF(50, 40), 240)
                aura.setColorAt(0.0, QColor(255, 255, 255, 22))
                aura.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.fillRect(self.rect(), QBrush(aura))

            # 3. Halftone Watermark or Coordinate Grid
            if self.mode == "halftone":
                # Halftone Queen in upper-right quadrant (x: 230 to 395, y: 15 to 260)
                grid_step = 14
                qx0 = int(w - qw - 12)
                qy0 = 18
                p.setPen(Qt.PenStyle.NoPen)
                for gy in range(16, int(h - 138), grid_step):
                    for gx in range(18, int(w - 16), grid_step):
                        ix = gx - qx0
                        iy = gy - qy0
                        q_val = 0.0
                        if 0 <= ix < qw and 0 <= iy < qh:
                            q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                        
                        # Soft falloff to left and bottom so input boxes remain 100% readable
                        fade_x = max(0.0, min(1.0, (gx - 170) / 140.0))
                        fade_y = max(0.0, min(1.0, 1.0 - (gy - 190) / 80.0 if gy > 190 else 1.0))
                        weight = q_val * fade_x * fade_y

                        if weight > 0.06:
                            dot_r = 0.9 + weight * 2.4
                            alpha = int(30 + weight * 165)
                            p.setBrush(QColor(186, 230, 253, alpha)) # Ice cyan-white
                            p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                        else:
                            p.setBrush(QColor(255, 255, 255, 10))
                            p.drawEllipse(QPointF(gx, gy), 0.8, 0.8)

            elif self.mode == "visionos":
                # Micro-cross grid (Image 2 style)
                cross_pen = QPen(QColor(255, 255, 255, 16), 1.0)
                p.setPen(cross_pen)
                step = 22
                for x in range(24, int(w - 16), step):
                    for y in range(24, int(h - 138), step):
                        p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
                        p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))

            elif self.mode == "cyberpunk":
                # Cyber circuit / tech grid dots
                p.setPen(Qt.PenStyle.NoPen)
                step = 18
                for x in range(18, int(w - 14), step):
                    for y in range(18, int(h - 138), step):
                        is_accent = ((x + y) % (step * 4) == 0)
                        if is_accent:
                            p.setBrush(QColor(56, 189, 248, 50))
                            p.drawEllipse(QPointF(x, y), 1.4, 1.4)
                        else:
                            p.setBrush(QColor(255, 255, 255, 10))
                            p.drawEllipse(QPointF(x, y), 0.8, 0.8)

            # 4. Top-Left Specular Glass Rim Reflection (curved arc highlight)
            p.setPen(QPen(QColor(255, 255, 255, 80), 1.4))
            p.drawLine(QPointF(32, 1.5), QPointF(w - 32, 1.5))
            p.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
            p.drawLine(QPointF(1.5, 32), QPointF(1.5, 120))

            # 5. Image 2 Style Luminous Horizontal Divider
            div_y = h - 134
            div_grad = QLinearGradient(26, div_y, w - 26, div_y)
            div_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            div_grad.setColorAt(0.15, QColor(255, 255, 255, 45))
            div_grad.setColorAt(0.5, QColor(255, 255, 255, 75))
            div_grad.setColorAt(0.85, QColor(255, 255, 255, 45))
            div_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(26, div_y), QPointF(w - 26, div_y))

            # 6. Outer Crisp Glass Prismatic Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 85))   # Bright top-left corner
            border_grad.setColorAt(0.35, QColor(255, 255, 255, 30))
            border_grad.setColorAt(0.7, QColor(56, 189, 248, 45))   # Subtle cyan glint
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 20))
            p.setPen(QPen(QBrush(border_grad), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # LIGHT MODE
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(0.45, QColor(245, 248, 253, 250))
            grad.setColorAt(1.0, QColor(235, 241, 249, 255))
            p.fillRect(self.rect(), QBrush(grad))

            # Soft sky aura
            aura = QRadialGradient(QPointF(w - 60, 70), 220)
            aura.setColorAt(0.0, QColor(0, 113, 227, 22))
            aura.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), QBrush(aura))

            if self.mode == "halftone":
                grid_step = 14
                qx0 = int(w - qw - 12)
                qy0 = 18
                p.setPen(Qt.PenStyle.NoPen)
                for gy in range(16, int(h - 138), grid_step):
                    for gx in range(18, int(w - 16), grid_step):
                        ix = gx - qx0
                        iy = gy - qy0
                        q_val = 0.0
                        if 0 <= ix < qw and 0 <= iy < qh:
                            q_val = queen_alpha.getpixel((ix, iy)) / 255.0
                        fade_x = max(0.0, min(1.0, (gx - 170) / 140.0))
                        fade_y = max(0.0, min(1.0, 1.0 - (gy - 190) / 80.0 if gy > 190 else 1.0))
                        weight = q_val * fade_x * fade_y

                        if weight > 0.06:
                            dot_r = 0.9 + weight * 2.4
                            alpha = int(45 + weight * 155)
                            p.setBrush(QColor(51, 65, 85, alpha))
                            p.drawEllipse(QPointF(gx, gy), dot_r, dot_r)
                        else:
                            p.setBrush(QColor(148, 163, 184, 30))
                            p.drawEllipse(QPointF(gx, gy), 0.8, 0.8)
            else:
                cross_pen = QPen(QColor(100, 116, 139, 35), 1.0)
                p.setPen(cross_pen)
                step = 22
                for x in range(24, int(w - 16), step):
                    for y in range(24, int(h - 138), step):
                        p.drawLine(QPointF(x - 2, y), QPointF(x + 2, y))
                        p.drawLine(QPointF(x, y - 2), QPointF(x, y + 2))

            # Specular top edge highlight
            p.setPen(QPen(QColor(255, 255, 255, 240), 1.2))
            p.drawLine(QPointF(32, 1.5), QPointF(w - 32, 1.5))

            # Luminous Divider Line in Light Mode
            div_y = h - 134
            div_grad = QLinearGradient(26, div_y, w - 26, div_y)
            div_grad.setColorAt(0.0, QColor(15, 23, 42, 0))
            div_grad.setColorAt(0.2, QColor(15, 23, 42, 35))
            div_grad.setColorAt(0.5, QColor(15, 23, 42, 60))
            div_grad.setColorAt(0.8, QColor(15, 23, 42, 35))
            div_grad.setColorAt(1.0, QColor(15, 23, 42, 0))
            p.setPen(QPen(QBrush(div_grad), 1.0))
            p.drawLine(QPointF(26, div_y), QPointF(w - 26, div_y))

            # Outer Crisp Glass Border
            p.setClipping(False)
            p.setPen(QPen(QColor(15, 23, 42, 42), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

def render_demo(mode_name, filename_prefix):
    # Dark render
    app_main._CURRENT_THEME = "dark"
    w = app_main.ActivationWindow("A3F9-27C1-88D0", lambda k: None)
    
    # Replace card
    old_card = w.card
    card_parent_layout = old_card.parentWidget().layout().itemAt(1).layout()
    new_card = CreativeGlassCard(mode=mode_name, theme="dark")
    new_card.setLayout(old_card.layout())
    card_parent_layout.replaceWidget(old_card, new_card)
    old_card.deleteLater()
    w.card = new_card

    # Add drop shadow to card
    shadow = QGraphicsDropShadowEffect(w.card)
    shadow.setBlurRadius(36)
    shadow.setOffset(0, 10)
    shadow.setColor(QColor(0, 0, 0, 150))
    w.card.setGraphicsEffect(shadow)

    w.show()
    app.processEvents()
    dark_path = os.path.join(brain_dir, f"{filename_prefix}_dark.png")
    w.grab().save(dark_path)

    # Light render
    w._toggle_theme()
    w.card.set_theme("light")
    shadow_l = QGraphicsDropShadowEffect(w.card)
    shadow_l.setBlurRadius(32)
    shadow_l.setOffset(0, 10)
    shadow_l.setColor(QColor(0, 0, 0, 48))
    w.card.setGraphicsEffect(shadow_l)
    app.processEvents()
    light_path = os.path.join(brain_dir, f"{filename_prefix}_light.png")
    w.grab().save(light_path)
    w.close()
    print(f"Rendered {filename_prefix} dark & light")

if __name__ == "__main__":
    render_demo("halftone", "demo_halftone_v2")
    render_demo("visionos", "demo_visionos_v2")
    render_demo("cyberpunk", "demo_cyberpunk_v2")
    print("All creative demos rendered!")
