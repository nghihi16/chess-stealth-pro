import os
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from db.database import create_license_record, get_connection

_CURRENT_THEME = "dark"


class KnightLogoWidget(QWidget):
    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg_path = QPainterPath()
        bg_path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 10, 10)
        p.fillPath(bg_path, QColor(245, 158, 11, 36))
        p.setPen(QPen(QColor("#f59e0b"), 1.5))
        p.drawPath(bg_path)

        s = self.width() / 24.0
        knight_pts = QPolygonF(
            [
                QPointF(7 * s, 18 * s),
                QPointF(8 * s, 12 * s),
                QPointF(5 * s, 10 * s),
                QPointF(7 * s, 5 * s),
                QPointF(11 * s, 6 * s),
                QPointF(14 * s, 3 * s),
                QPointF(17 * s, 7 * s),
                QPointF(18 * s, 12 * s),
                QPointF(17 * s, 18 * s),
            ]
        )
        p.setPen(
            QPen(
                QColor("#f59e0b"),
                1.8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        p.setBrush(QColor(245, 158, 11, 55))
        p.drawPolygon(knight_pts)
        p.drawLine(QPointF(5 * s, 20.5 * s), QPointF(19 * s, 20.5 * s))


def _build_qss(theme: str) -> str:
    if theme == "light":
        return """
        QWidget#Root { background-color: #f1f5f9; color: #0f172a; font-family: 'Segoe UI'; }
        QFrame#Card { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; }
        QLabel#Title { color: #0f172a; font-size: 16px; font-weight: 700; }
        QLineEdit {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
        }
        QLineEdit:focus { border: 2px solid #d97706; background-color: #ffffff; }
        QLineEdit#KeyOut { color: #047857; background-color: #f1f5f9; }
        QPushButton#BtnAmber {
            background-color: #d97706; color: #ffffff;
            border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
        }
        QPushButton#BtnAmber:hover { background-color: #b45309; }
        QPushButton#BtnSky {
            background-color: #0284c7; color: #ffffff;
            border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
        }
        QPushButton#BtnSky:hover { background-color: #0369a1; }
        QPushButton#BtnGreen {
            background-color: #059669; color: #ffffff;
            border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
        }
        QPushButton#BtnGreen:hover { background-color: #047857; }
        QPushButton#SecondaryBtn {
            background-color: #ffffff; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            min-height: 40px; font-size: 12px; font-weight: 600; padding: 0 12px;
        }
        QPushButton#SecondaryBtn:hover { border: 1px solid #d97706; }
        """
    return """
    QWidget#Root { background-color: #090b10; color: #f8fafc; font-family: 'Segoe UI'; }
    QFrame#Card { background-color: #12151e; border: 1px solid #262b3d; border-radius: 16px; }
    QLabel#Title { color: #f8fafc; font-size: 16px; font-weight: 700; }
    QLineEdit {
        background-color: #1a1f2e; color: #f8fafc;
        border: 1px solid #2e364f; border-radius: 10px;
        padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
    }
    QLineEdit:focus { border: 2px solid #f59e0b; background-color: #1e2436; }
    QLineEdit#KeyOut { color: #34d399; background-color: #0b0d13; }
    QPushButton#BtnAmber {
        background-color: #f59e0b; color: #09090b;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
    }
    QPushButton#BtnAmber:hover { background-color: #fbbf24; }
    QPushButton#BtnSky {
        background-color: #38bdf8; color: #09090b;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
    }
    QPushButton#BtnSky:hover { background-color: #7dd3fc; }
    QPushButton#BtnGreen {
        background-color: #10b981; color: #09090b;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 700;
    }
    QPushButton#BtnGreen:hover { background-color: #34d399; }
    QPushButton#SecondaryBtn {
        background-color: #1a1f2e; color: #f8fafc;
        border: 1px solid #2e364f; border-radius: 10px;
        min-height: 40px; font-size: 12px; font-weight: 600; padding: 0 12px;
    }
    QPushButton#SecondaryBtn:hover { border: 1px solid #f59e0b; }
    """


def create_db_key(ltype: str, hwid: str = "") -> str:
    hwid_clean = hwid.strip().upper() if hwid.strip() else None
    with get_connection() as conn:
        rec = create_license_record(
            conn,
            license_type=ltype,
            hwid=hwid_clean,
            activate_immediately=bool(hwid_clean),
        )
        return rec["key"]


def run_gui():
    global _CURRENT_THEME
    app = QApplication.instance() or QApplication(sys.argv)

    win = QWidget()
    win.setObjectName("Root")
    win.setWindowTitle("Chess Stealth Pro — KeyGen")
    win.setFixedSize(460, 280)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(KnightLogoWidget(36))
    title = QLabel("KEY GENERATOR")
    title.setObjectName("Title")
    top.addWidget(title)
    top.addStretch()

    theme_btn = QPushButton("Theme")
    theme_btn.setObjectName("SecondaryBtn")
    theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def toggle_theme():
        global _CURRENT_THEME
        _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
        win.setStyleSheet(_build_qss(_CURRENT_THEME))

    theme_btn.clicked.connect(toggle_theme)
    top.addWidget(theme_btn)
    layout.addLayout(top)

    card = QFrame()
    card.setObjectName("Card")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(16, 16, 16, 16)
    card_layout.setSpacing(12)

    hwid_input = QLineEdit()
    hwid_input.setPlaceholderText("HWID (Optional)...")
    hwid_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.addWidget(hwid_input)

    out_input = QLineEdit()
    out_input.setObjectName("KeyOut")
    out_input.setReadOnly(True)
    out_input.setText("...")
    out_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.addWidget(out_input)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    def gen(ltype: str):
        k = create_db_key(ltype, hwid_input.text())
        out_input.setText(k)
        QApplication.clipboard().setText(k)

    b1 = QPushButton("24H KEY")
    b1.setObjectName("BtnAmber")
    b1.setCursor(Qt.CursorShape.PointingHandCursor)
    b1.clicked.connect(lambda: gen("trial_24h"))
    btn_row.addWidget(b1)

    b2 = QPushButton("30-DAY KEY")
    b2.setObjectName("BtnSky")
    b2.setCursor(Qt.CursorShape.PointingHandCursor)
    b2.clicked.connect(lambda: gen("monthly"))
    btn_row.addWidget(b2)

    b3 = QPushButton("LIFETIME KEY")
    b3.setObjectName("BtnGreen")
    b3.setCursor(Qt.CursorShape.PointingHandCursor)
    b3.clicked.connect(lambda: gen("lifetime"))
    btn_row.addWidget(b3)

    card_layout.addLayout(btn_row)
    layout.addWidget(card)

    win.show()
    app.exec()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("trial_24h", "monthly", "lifetime"):
        hwid_arg = sys.argv[2] if len(sys.argv) >= 3 else ""
        print(create_db_key(sys.argv[1], hwid_arg))
    else:
        run_gui()
