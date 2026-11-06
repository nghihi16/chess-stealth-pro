import os
import sys

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap
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
from logo_assets import LOGOS

_CURRENT_THEME = "dark"


def pixmap_from_data_uri(data_uri: str, size: int) -> QPixmap:
    raw_b64 = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
    ba = QByteArray.fromBase64(raw_b64.encode("ascii"))
    pm = QPixmap()
    pm.loadFromData(ba)
    return pm.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def app_icon() -> QIcon:
    return QIcon(pixmap_from_data_uri(LOGOS["pawn"], 128))


def build_brand_header() -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)

    logo_lbl = QLabel()
    logo_lbl.setPixmap(pixmap_from_data_uri(LOGOS["pawn"], 46))
    logo_lbl.setFixedSize(46, 46)
    h.addWidget(logo_lbl)

    txt_col = QVBoxLayout()
    txt_col.setContentsMargins(0, 0, 0, 0)
    txt_col.setSpacing(0)

    c_lbl = QLabel("C H E S S")
    c_lbl.setObjectName("BrandChess")
    s_lbl = QLabel("S T E A L T H   •   K E Y G E N")
    s_lbl.setObjectName("BrandStealth")
    txt_col.addWidget(c_lbl)
    txt_col.addWidget(s_lbl)
    h.addLayout(txt_col)
    return w


def _build_qss(theme: str) -> str:
    if theme == "light":
        return """
        QWidget#Root { background-color: #f1f5f9; color: #0f172a; font-family: 'Segoe UI'; }
        QFrame#Card { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; }
        QLabel#BrandChess { color: #0f172a; font-size: 16px; font-weight: 800; }
        QLabel#BrandStealth { color: #0284c7; font-size: 10px; font-weight: 800; }
        QLineEdit {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
        }
        QLineEdit:focus { border: 2px solid #0284c7; background-color: #ffffff; }
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
        QPushButton#SecondaryBtn:hover { border: 1px solid #0284c7; }
        """
    return """
    QWidget#Root { background-color: #060911; color: #f8fafc; font-family: 'Segoe UI'; }
    QFrame#Card { background-color: #0d121e; border: 1px solid #1e293b; border-radius: 16px; }
    QLabel#BrandChess { color: #f8fafc; font-size: 16px; font-weight: 800; }
    QLabel#BrandStealth { color: #22d3ee; font-size: 10px; font-weight: 800; }
    QLineEdit {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 10px;
        padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
    }
    QLineEdit:focus { border: 2px solid #22d3ee; background-color: #1a2436; }
    QLineEdit#KeyOut { color: #34d399; background-color: #090d16; }
    QPushButton#BtnAmber {
        background-color: #f59e0b; color: #060911;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 800;
    }
    QPushButton#BtnAmber:hover { background-color: #fbbf24; }
    QPushButton#BtnSky {
        background-color: #22d3ee; color: #060911;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 800;
    }
    QPushButton#BtnSky:hover { background-color: #38bdf8; }
    QPushButton#BtnGreen {
        background-color: #10b981; color: #060911;
        border: none; border-radius: 10px; min-height: 44px; font-size: 12px; font-weight: 800;
    }
    QPushButton#BtnGreen:hover { background-color: #34d399; }
    QPushButton#SecondaryBtn {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 10px;
        min-height: 40px; font-size: 12px; font-weight: 600; padding: 0 12px;
    }
    QPushButton#SecondaryBtn:hover { border: 1px solid #22d3ee; }
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
    app.setWindowIcon(app_icon())

    win = QWidget()
    win.setObjectName("Root")
    win.setWindowTitle("CHESS STEALTH — Key Generator")
    win.setWindowIcon(app_icon())
    win.setFixedSize(460, 290)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(build_brand_header())
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
