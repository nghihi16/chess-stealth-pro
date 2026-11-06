import ctypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.parse

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from api.server import start_background_api_server
from license_core.hwid import get_hwid
from license_core.url_scheme import parse_url_scheme_arg, register_custom_url_scheme
from license_core.verifier import activate_or_verify_key, derive_arrow_scale_factor

# ================= CẤU HÌNH HỆ THỐNG =================
API_BASE_URL = os.environ.get("CHESSPRO_API_URL", "http://127.0.0.1:8766")
WEB_GET_KEY_URL = os.environ.get(
    "CHESSPRO_GET_KEY_URL", "https://nghihi16.github.io/chess-stealth-pro/"
)
BUY_LIFE_URL = "https://gumroad.com/"

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ChessStealthPro")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APP_DIR, "license.dat")

# Win32 Constants cho Stealth Overlay (Tàng hình trước OBS / TikTok Live Studio)
WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

arrow_state = {
    "x1": 0,
    "y1": 0,
    "x2": 0,
    "y2": 0,
    "size": 60,
    "show": False,
    "last_seen": 0.0,
    "offset_y": 0,
}

# ================= MÃ NGUỒN ZERO-DOM BRIDGE TỰ ĐỘNG CÀI ĐẶT =================
STEALTH_USERSCRIPT_CODE = r"""// ==UserScript==
// @name         Chess.com Zero-DOM Stealth Bridge
// @match        *://www.chess.com/*
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  if (window.__CHESS_STEALTH_BRIDGE_ACTIVE__) return;
  window.__CHESS_STEALTH_BRIDGE_ACTIVE__ = true;

  let isEnabled = true;
  let manualSide = 'auto';
  let stockfishWorker = null;
  let lastBoardKey = '';
  let currentBestMove = null;
  let draggedPieceInfo = null;

  let exactOffsetX = null;
  let exactOffsetY = null;
  let lastWinX = window.screenX;
  let lastWinY = window.screenY;
  let lastInnerW = window.innerWidth;
  let lastInnerH = window.innerHeight;

  function updateCalibration(e) {
    if (typeof e.screenX === 'number' && typeof e.clientX === 'number') {
      exactOffsetX = e.screenX - e.clientX;
      exactOffsetY = e.screenY - e.clientY;
      lastWinX = window.screenX;
      lastWinY = window.screenY;
      lastInnerW = window.innerWidth;
      lastInnerH = window.innerHeight;
    }
  }

  window.addEventListener('pointermove', updateCalibration, { passive: true, capture: true });
  window.addEventListener('mousemove', updateCalibration, { passive: true, capture: true });
  window.addEventListener('pointerdown', updateCalibration, { passive: true, capture: true });

  function sendToOverlay(payload) {
    const body = JSON.stringify(payload);
    if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
      try {
        chrome.runtime.sendMessage({ type: 'OVERLAY_UPDATE', payload });
      } catch (_) {}
    }
    fetch('http://127.0.0.1:8765/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
      mode: 'cors'
    }).catch(() => {
      const q = payload.show
        ? `s=1&x1=${payload.x1}&y1=${payload.y1}&x2=${payload.x2}&y2=${payload.y2}&sz=${payload.size}&t=${Date.now()}`
        : `s=0&t=${Date.now()}`;
      const img = new Image();
      img.src = `http://127.0.0.1:8765/u?${q}`;
    });
  }

  function updateOverlayCoords(boardEl, move) {
    if (!isEnabled || document.hidden || !boardEl || !move || move.length < 4) {
      sendToOverlay({ show: false });
      return;
    }

    const rect = boardEl.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) {
      sendToOverlay({ show: false });
      return;
    }

    if (
      window.screenX !== lastWinX ||
      window.screenY !== lastWinY ||
      window.innerWidth !== lastInnerW ||
      window.innerHeight !== lastInnerH
    ) {
      exactOffsetX = null;
      exactOffsetY = null;
    }

    let screenOffsetX, screenOffsetY;
    if (exactOffsetX !== null && exactOffsetY !== null) {
      screenOffsetX = exactOffsetX;
      screenOffsetY = exactOffsetY;
    } else {
      const borderOffsetX = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
      const chromeHeight = Math.max(0, window.outerHeight - window.innerHeight - borderOffsetX);
      screenOffsetX = window.screenX + borderOffsetX;
      screenOffsetY = window.screenY + chromeHeight;
    }

    const isFlipped = boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped');
    const sqSize = rect.width / 8;

    function sqToScreen(sq) {
      const file = sq.charCodeAt(0) - 97;
      const rank = parseInt(sq[1], 10) - 1;
      const col = isFlipped ? (7 - file) : file;
      const row = isFlipped ? rank : (7 - rank);

      return {
        x: Math.round(screenOffsetX + rect.left + (col + 0.5) * sqSize),
        y: Math.round(screenOffsetY + rect.top + (row + 0.5) * sqSize)
      };
    }

    const from = sqToScreen(move.substring(0, 2));
    const to = sqToScreen(move.substring(2, 4));

    sendToOverlay({
      show: true,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      size: Math.round(sqSize),
      move: move
    });
  }

  function setupEngine() {
    try {
      const workerCode = `importScripts('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js');`;
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      stockfishWorker = new Worker(URL.createObjectURL(blob));

      stockfishWorker.onmessage = function (event) {
        if (!isEnabled) return;
        const line = typeof event.data === 'string' ? event.data : '';

        if (line.startsWith('info') && line.includes(' pv ')) {
          const pvMatch = line.match(/ pv ([a-h][1-8][a-h][1-8][qrbn]?)/);
          if (pvMatch && pvMatch[1]) {
            currentBestMove = pvMatch[1];
            const boardEl = document.querySelector('wc-chess-board, .board');
            if (boardEl) updateOverlayCoords(boardEl, currentBestMove);
          }
        }

        if (line.startsWith('bestmove')) {
          const move = line.split(' ')[1];
          if (move && move !== '(none)' && move.length >= 4) {
            currentBestMove = move;
            const boardEl = document.querySelector('wc-chess-board, .board');
            if (boardEl) updateOverlayCoords(boardEl, currentBestMove);
          }
        }
      };

      stockfishWorker.postMessage('uci');
      stockfishWorker.postMessage('setoption name Skill Level value 20');
      stockfishWorker.postMessage('isready');
    } catch (_) {}
  }

  setupEngine();

  window.addEventListener('keydown', (e) => {
    if (e.altKey && e.key.toLowerCase() === 'x') {
      isEnabled = !isEnabled;
      if (!isEnabled) {
        currentBestMove = null;
        sendToOverlay({ show: false });
      } else {
        lastBoardKey = '';
      }
    } else if (e.altKey && e.key.toLowerCase() === 'c') {
      manualSide = manualSide === 'auto' ? 'b' : (manualSide === 'b' ? 'w' : 'auto');
      lastBoardKey = '';
    }
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) sendToOverlay({ show: false });
    else lastBoardKey = '';
  });

  window.addEventListener('beforeunload', () => {
    sendToOverlay({ show: false });
  });

  document.addEventListener('pointerdown', (e) => {
    const pieceEl = e.target.closest('.piece');
    if (pieceEl) {
      const classes = Array.from(pieceEl.classList);
      let type = null, sq = null;
      for (const c of classes) {
        if (/^[wb][prnbqk]$/.test(c)) type = c;
        if (/^square-\d\d$/.test(c)) sq = c.split('-')[1];
      }
      if (type && sq) draggedPieceInfo = { type, sq };
    }
  }, true);

  document.addEventListener('pointerup', () => {
    draggedPieceInfo = null;
  }, true);

  function extractBoard() {
    const boardEl = document.querySelector('wc-chess-board, .board');
    if (!boardEl) return null;

    const grid = Array(8).fill(null).map(() => Array(8).fill(''));
    const pieces = boardEl.querySelectorAll('.piece');
    if (pieces.length === 0) return null;

    let whiteKing = false, blackKing = false;

    pieces.forEach(p => {
      const classes = Array.from(p.classList);
      if (classes.includes('animating')) return;

      let type = null, sq = null;
      for (const c of classes) {
        if (/^[wb][prnbqk]$/.test(c)) type = c;
        if (/^square-\d\d$/.test(c)) sq = c.split('-')[1];
      }

      if (classes.includes('dragging') && !sq && draggedPieceInfo) {
        type = draggedPieceInfo.type;
        sq = draggedPieceInfo.sq;
      }

      if (type && sq) {
        const col = parseInt(sq[0], 10) - 1;
        const row = 8 - parseInt(sq[1], 10);
        if (row >= 0 && row < 8 && col >= 0 && col < 8) {
          const char = type[0] === 'w' ? type[1].toUpperCase() : type[1].toLowerCase();
          grid[row][col] = char;
          if (char === 'K') whiteKing = true;
          if (char === 'k') blackKing = true;
        }
      }
    });

    if (!whiteKing || !blackKing) return null;

    const fenRows = grid.map(row => {
      let empty = 0, str = '';
      row.forEach(cell => {
        if (cell === '') empty++;
        else {
          if (empty > 0) { str += empty; empty = 0; }
          str += cell;
        }
      });
      if (empty > 0) str += empty;
      return str;
    });

    const isFlipped = boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped');
    const mySide = manualSide !== 'auto' ? manualSide : (isFlipped ? 'b' : 'w');
    const boardPart = fenRows.join('/');

    return {
      boardEl,
      mySide,
      boardPart,
      fen: `${boardPart} ${mySide} KQkq - 0 1`
    };
  }

  setInterval(() => {
    if (!isEnabled || !stockfishWorker || document.hidden) return;

    const state = extractBoard();
    if (!state) {
      sendToOverlay({ show: false });
      return;
    }

    if (currentBestMove) {
      updateOverlayCoords(state.boardEl, currentBestMove);
    }

    const currentKey = `${state.boardPart}_${state.mySide}`;
    if (currentKey === lastBoardKey) return;

    lastBoardKey = currentKey;
    stockfishWorker.postMessage('stop');
    stockfishWorker.postMessage('position fen ' + state.fen);
    stockfishWorker.postMessage('go depth 13 movetime 180');
  }, 25);
})();
"""


# ================= TỰ ĐỘNG CÀI ĐẶT SCRIPT & MỞ TRÌNH DUYỆT =================
def setup_and_launch_browser(browser_type: str):
    min_userscripts_dir = os.path.join(os.getenv("APPDATA", ""), "Min", "userscripts")
    min_settings_file = os.path.join(os.getenv("APPDATA", ""), "Min", "settings.json")
    try:
        os.makedirs(min_userscripts_dir, exist_ok=True)
        target_js = os.path.join(min_userscripts_dir, "chess-assist.js")
        with open(target_js, "w", encoding="utf-8") as f:
            f.write(STEALTH_USERSCRIPT_CODE)

        if os.path.exists(min_settings_file):
            with open(min_settings_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not cfg.get("userscriptsEnabled"):
                cfg["userscriptsEnabled"] = True
                with open(min_settings_file, "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
    except Exception:
        pass

    ext_dir = os.path.join(APP_DIR, "browser-extension")
    try:
        os.makedirs(ext_dir, exist_ok=True)
        manifest = {
            "manifest_version": 3,
            "name": "Chess Stealth Bridge",
            "version": "1.0.0",
            "description": "Zero-DOM bridge for Windows WDA_EXCLUDEFROMCAPTURE stealth overlay.",
            "permissions": ["storage"],
            "host_permissions": ["*://*.chess.com/*", "http://127.0.0.1:8765/*"],
            "background": {"service_worker": "background.js"},
            "content_scripts": [
                {
                    "matches": ["*://*.chess.com/*"],
                    "js": ["content.js"],
                    "run_at": "document_end",
                }
            ],
        }
        with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        with open(os.path.join(ext_dir, "content.js"), "w", encoding="utf-8") as f:
            f.write(STEALTH_USERSCRIPT_CODE)
        with open(os.path.join(ext_dir, "background.js"), "w", encoding="utf-8") as f:
            f.write(
                "chrome.runtime.onMessage.addListener((m)=>{if(m&&m.type==='OVERLAY_UPDATE'&&m.payload){fetch('http://127.0.0.1:8765/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(m.payload)}).catch(()=>{});}});\n"
            )
    except Exception:
        pass

    chess_url = "https://www.chess.com/play/computer"
    try:
        if browser_type == "min":
            min_exe = os.path.join(os.getenv("LOCALAPPDATA", ""), "min", "Min.exe")
            if os.path.exists(min_exe):
                subprocess.Popen([min_exe, chess_url])
        elif browser_type == "brave":
            brave_paths = [
                os.path.join(os.getenv("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            ]
            for bp in brave_paths:
                if os.path.exists(bp):
                    subprocess.Popen([bp, f"--load-extension={ext_dir}", chess_url])
                    break
        elif browser_type == "chrome":
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            for cp in chrome_paths:
                if os.path.exists(cp):
                    subprocess.Popen([cp, f"--load-extension={ext_dir}", chess_url])
                    break
    except Exception:
        pass


# ================= SERVER NHẬN TỌA ĐỘ & OVERLAY TÀNG HÌNH =================
class StealthOverlayServer(BaseHTTPRequestHandler):
    def _send_cors(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors()

    def do_GET(self):
        global arrow_state
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "s" in params:
            show_flag = params["s"][0] == "1"
            arrow_state["show"] = show_flag
            arrow_state["last_seen"] = time.time()
            if show_flag:
                try:
                    arrow_state["x1"] = int(float(params.get("x1", [0])[0]))
                    arrow_state["y1"] = int(float(params.get("y1", [0])[0]))
                    arrow_state["x2"] = int(float(params.get("x2", [0])[0]))
                    arrow_state["y2"] = int(float(params.get("y2", [0])[0]))
                    arrow_state["size"] = int(float(params.get("sz", [60])[0]))
                except Exception:
                    pass
        self._send_cors()
        self.wfile.write(b"OK")

    def do_POST(self):
        global arrow_state
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            try:
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body)
                arrow_state["show"] = bool(data.get("show", False))
                arrow_state["last_seen"] = time.time()
                if arrow_state["show"]:
                    arrow_state["x1"] = int(data.get("x1", 0))
                    arrow_state["y1"] = int(data.get("y1", 0))
                    arrow_state["x2"] = int(data.get("x2", 0))
                    arrow_state["y2"] = int(data.get("y2", 0))
                    arrow_state["size"] = int(data.get("size", 60))
            except Exception:
                pass
        self._send_cors()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        return


def launch_stealth_engine(browser_type: str, active_key: str, hwid: str):
    setup_and_launch_browser(browser_type)

    def run_http():
        try:
            srv = HTTPServer(("127.0.0.1", 8765), StealthOverlayServer)
            srv.serve_forever()
        except Exception:
            pass

    threading.Thread(target=run_http, daemon=True).start()

    # Định kỳ gọi lại /verify mỗi 30 phút để làm mới chữ ký Ed25519
    def periodic_reverify():
        while True:
            time.sleep(1800)
            activate_or_verify_key(API_BASE_URL, active_key, hwid)

    threading.Thread(target=periodic_reverify, daemon=True).start()

    app = QApplication.instance() or QApplication(sys.argv)
    overlay = QtStealthOverlay()
    overlay.showFullScreen()
    app.exec()


class QtStealthOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
        )
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    def _tick(self):
        if (ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) and (
            ctypes.windll.user32.GetAsyncKeyState(0x51) & 0x8000
        ):
            QApplication.quit()
            sys.exit(0)
        self.update()

    def paintEvent(self, _event):
        now = time.time()
        gate_scale = derive_arrow_scale_factor()
        if gate_scale <= 0.0 or not arrow_state["show"] or (now - arrow_state["last_seen"] > 1.8):
            return

        x1 = float(arrow_state["x1"])
        y1 = float(arrow_state["y1"] + arrow_state["offset_y"])
        x2 = float(arrow_state["x2"])
        y2 = float(arrow_state["y2"] + arrow_state["offset_y"])
        sq = max(32.0, float(arrow_state["size"])) * gate_scale

        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist <= 6:
            return

        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux

        shaft_w = sq * 0.22
        head_w = sq * 0.50
        head_l = sq * 0.38
        offset = sq * 0.12

        sx, sy = x1 + ux * offset, y1 + uy * offset
        nx, ny = x2 - ux * head_l, y2 - uy * head_l

        poly = QPolygonF(
            [
                QPointF(sx + px * (shaft_w / 2), sy + py * (shaft_w / 2)),
                QPointF(nx + px * (shaft_w / 2), ny + py * (shaft_w / 2)),
                QPointF(nx + px * (head_w / 2), ny + py * (head_w / 2)),
                QPointF(x2, y2),
                QPointF(nx - px * (head_w / 2), ny - py * (head_w / 2)),
                QPointF(nx - px * (shaft_w / 2), ny - py * (shaft_w / 2)),
                QPointF(sx - px * (shaft_w / 2), sy - py * (shaft_w / 2)),
            ]
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 170, 0, 220))
        painter.drawPolygon(poly)


# ================= LOGO QUÂN MÃ CỜ VUA (CHESS KNIGHT VECTOR) =================
class KnightLogoWidget(QWidget):
    def __init__(self, size: int = 38, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Nền bo góc hiện đại
        bg_path = QPainterPath()
        bg_path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 10, 10)
        p.fillPath(bg_path, QColor(245, 158, 11, 36))
        p.setPen(QPen(QColor("#f59e0b"), 1.5))
        p.drawPath(bg_path)

        # Vẽ Quân Mã (Stealth Knight) bằng Vector Polygon
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
        p.setPen(QPen(QColor("#f59e0b"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(245, 158, 11, 55))
        p.drawPolygon(knight_pts)
        p.drawLine(QPointF(5 * s, 20.5 * s), QPointF(19 * s, 20.5 * s))


def _build_qss(theme: str) -> str:
    if theme == "light":
        return """
        QWidget#Root { background-color: #f1f5f9; color: #0f172a; font-family: 'Segoe UI'; }
        QFrame#Card { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; }
        QLabel#Title { color: #0f172a; font-size: 16px; font-weight: 700; }
        QLabel#Muted { color: #475569; font-size: 12px; font-weight: 600; }
        QLineEdit {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
        }
        QLineEdit:focus { border: 2px solid #d97706; background-color: #ffffff; }
        QPushButton#PrimaryBtn {
            background-color: #d97706; color: #ffffff;
            border: none; border-radius: 10px;
            min-height: 44px; font-size: 13px; font-weight: 700;
        }
        QPushButton#PrimaryBtn:hover { background-color: #b45309; }
        QPushButton#SecondaryBtn {
            background-color: #ffffff; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            min-height: 42px; font-size: 12px; font-weight: 600; padding: 0 12px;
        }
        QPushButton#SecondaryBtn:hover { border: 1px solid #d97706; background-color: #f8fafc; }
        QRadioButton { color: #0f172a; font-size: 13px; font-weight: 600; spacing: 10px; padding: 8px 4px; }
        QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #94a3b8; }
        QRadioButton::indicator:checked { background-color: #d97706; border: 2px solid #d97706; }
        """
    return """
    QWidget#Root { background-color: #090b10; color: #f8fafc; font-family: 'Segoe UI'; }
    QFrame#Card { background-color: #12151e; border: 1px solid #262b3d; border-radius: 16px; }
    QLabel#Title { color: #f8fafc; font-size: 16px; font-weight: 700; }
    QLabel#Muted { color: #94a3b8; font-size: 12px; font-weight: 600; }
    QLineEdit {
        background-color: #1a1f2e; color: #f8fafc;
        border: 1px solid #2e364f; border-radius: 10px;
        padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
    }
    QLineEdit:focus { border: 2px solid #f59e0b; background-color: #1e2436; }
    QPushButton#PrimaryBtn {
        background-color: #f59e0b; color: #09090b;
        border: none; border-radius: 10px;
        min-height: 44px; font-size: 13px; font-weight: 700;
    }
    QPushButton#PrimaryBtn:hover { background-color: #fbbf24; }
    QPushButton#SecondaryBtn {
        background-color: #1a1f2e; color: #f8fafc;
        border: 1px solid #2e364f; border-radius: 10px;
        min-height: 42px; font-size: 12px; font-weight: 600; padding: 0 12px;
    }
    QPushButton#SecondaryBtn:hover { border: 1px solid #f59e0b; background-color: #232a3d; }
    QRadioButton { color: #f8fafc; font-size: 13px; font-weight: 600; spacing: 10px; padding: 8px 4px; }
    QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #475569; }
    QRadioButton::indicator:checked { background-color: #f59e0b; border: 2px solid #f59e0b; }
    """


_CURRENT_THEME = "dark"


def show_browser_selector(_license_info: str, active_key: str, hwid: str):
    global _CURRENT_THEME
    app = QApplication.instance() or QApplication(sys.argv)

    win = QWidget()
    win.setObjectName("Root")
    win.setWindowTitle("Chess Stealth Pro")
    win.setFixedSize(420, 340)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.addWidget(KnightLogoWidget(36))
    title = QLabel("Chọn Trình Duyệt")
    title.setObjectName("Title")
    top.addWidget(title)
    top.addStretch()

    theme_btn = QPushButton("Sáng / Tối")
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
    card_layout.setContentsMargins(16, 12, 16, 12)
    card_layout.setSpacing(4)

    group = QButtonGroup(win)
    browsers = [
        ("Min Browser", "min"),
        ("Brave Browser", "brave"),
        ("Google Chrome", "chrome"),
        ("Chỉ bật Overlay", "other"),
    ]
    selected_browser = {"val": "min"}

    for idx, (label_text, val) in enumerate(browsers):
        rb = QRadioButton(label_text)
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        if idx == 0:
            rb.setChecked(True)
        rb.toggled.connect(lambda checked, v=val: selected_browser.update({"val": v}) if checked else None)
        group.addButton(rb)
        card_layout.addWidget(rb)

    layout.addWidget(card)

    start_btn = QPushButton("BẮT ĐẦU")
    start_btn.setObjectName("PrimaryBtn")
    start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def on_start():
        chosen = selected_browser["val"]
        win.close()
        launch_stealth_engine(chosen, active_key, hwid)

    start_btn.clicked.connect(on_start)
    layout.addWidget(start_btn)

    win.show()
    app.exec()


def main():
    global _CURRENT_THEME
    register_custom_url_scheme("chesspro")
    start_background_api_server("127.0.0.1", 8766)

    hwid = get_hwid()
    url_scheme_key = parse_url_scheme_arg(sys.argv)

    saved_key = url_scheme_key or ""
    if not saved_key and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved_key = f.read().strip()
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)

    win = QWidget()
    win.setObjectName("Root")
    win.setWindowTitle("Chess Stealth Pro")
    win.setFixedSize(430, 290)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    # Top Header
    top = QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(KnightLogoWidget(36))
    title = QLabel("CHESS STEALTH PRO")
    title.setObjectName("Title")
    top.addWidget(title)
    top.addStretch()

    copy_hwid_btn = QPushButton("Copy HWID")
    copy_hwid_btn.setObjectName("SecondaryBtn")
    copy_hwid_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def copy_hwid():
        QApplication.clipboard().setText(hwid)
        copy_hwid_btn.setText("Đã chép")

    copy_hwid_btn.clicked.connect(copy_hwid)
    top.addWidget(copy_hwid_btn)

    theme_btn = QPushButton("Sáng / Tối")
    theme_btn.setObjectName("SecondaryBtn")
    theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def toggle_theme():
        global _CURRENT_THEME
        _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
        win.setStyleSheet(_build_qss(_CURRENT_THEME))

    theme_btn.clicked.connect(toggle_theme)
    top.addWidget(theme_btn)
    layout.addLayout(top)

    # Card
    card = QFrame()
    card.setObjectName("Card")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(16, 16, 16, 16)
    card_layout.setSpacing(12)

    key_input = QLineEdit()
    key_input.setPlaceholderText("Nhập License Key...")
    key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if saved_key:
        key_input.setText(saved_key)
    card_layout.addWidget(key_input)

    act_btn = QPushButton("KÍCH HOẠT")
    act_btn.setObjectName("PrimaryBtn")
    act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    card_layout.addWidget(act_btn)
    layout.addWidget(card)

    # Bottom Buttons
    bottom = QHBoxLayout()
    bottom.setSpacing(10)

    get_key_btn = QPushButton("Lấy Key 24h")
    get_key_btn.setObjectName("SecondaryBtn")
    get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    get_key_btn.clicked.connect(lambda: os.startfile(WEB_GET_KEY_URL))
    bottom.addWidget(get_key_btn)

    buy_btn = QPushButton("Mua Key VIP")
    buy_btn.setObjectName("SecondaryBtn")
    buy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    buy_btn.clicked.connect(lambda: os.startfile(BUY_LIFE_URL))
    bottom.addWidget(buy_btn)
    layout.addLayout(bottom)

    def handle_activate():
        k = key_input.text().strip()
        if not k:
            QMessageBox.warning(win, "Thiếu Key", "Vui lòng nhập mã License Key!")
            return
        valid, msg = activate_or_verify_key(API_BASE_URL, k, hwid)
        if valid:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(k)
            except Exception:
                pass
            win.close()
            show_browser_selector(msg, k, hwid)
        else:
            QMessageBox.critical(win, "Lỗi", msg)

    act_btn.clicked.connect(handle_activate)
    key_input.returnPressed.connect(handle_activate)

    win.show()
    if url_scheme_key:
        QTimer.singleShot(250, handle_activate)

    app.exec()


if __name__ == "__main__":
    main()
