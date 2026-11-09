import base64
import ctypes
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.parse

from PySide6.QtCore import QByteArray, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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
from logo_assets import LOGOS

API_BASE_URL = os.environ.get("CHESSPRO_API_URL", "http://127.0.0.1:8766")
WEB_GET_KEY_URL = os.environ.get(
    "CHESSPRO_GET_KEY_URL", "https://nghihi16.github.io/chess-stealth-pro/"
)
BUY_LIFE_URL = "https://gumroad.com/"

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ChessStealthPro")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APP_DIR, "license.dat")

WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

COLOR_PRESETS = {
    "Orange (Classic)": QColor(245, 158, 11, 230),
    "Cyan (Stealth)": QColor(34, 211, 238, 230),
    "Emerald (Green)": QColor(16, 185, 129, 230),
    "Crimson (Red)": QColor(239, 68, 68, 230),
    "Gold (Yellow)": QColor(234, 179, 8, 230),
    "Violet (Neon)": QColor(168, 85, 247, 230),
}

arrow_state = {
    "x1": 0,
    "y1": 0,
    "x2": 0,
    "y2": 0,
    "size": 60,
    "show": False,
    "enabled": True,
    "side": "auto",
    "move": "",
    "depth": "",
    "last_seen": 0.0,
    "last_ping": 0.0,
    "offset_y": 0,
    "auto_aligned": False,
    "qcolor": QColor(245, 158, 11, 230),
}

_ACTIVE_WINDOWS = []
_CURRENT_THEME = "dark"
_OVERLAY_INSTANCE = None

# ================= 100% PURE ZERO-DOM STEALTH SCRIPT (ZERO IN-PAGE ELEMENTS) =================
# CHỐNG ANTI-CHEAT TUYỆT ĐỐI: Không chèn bất kỳ thẻ HTML, SVG hay CSS nào vào DOM của Chess.com.
# Toàn bộ việc vẽ mũi tên được xử lý bởi Windows Stealth Overlay phía ngoài màn hình.
STEALTH_USERSCRIPT_CODE = r"""// ==UserScript==
// @name         Chess.com Pure Zero-DOM Stealth Engine
// @match        *://www.chess.com/*
// @match        *://chess.com/*
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  if (window.__CHESS_STEALTH_CORE_RUNNING__) return;
  window.__CHESS_STEALTH_CORE_RUNNING__ = true;

  let isEnabled = true;
  let manualSide = 'auto';
  let stockfishWorker = null;
  let lastBoardKey = '';
  let currentBestMove = null;
  let currentDepth = '';
  let draggedPieceInfo = null;

  // Real-time viewport offset calibration (mouse-independent, supports Min Browser & custom scaling)
  let calibratedOffsetX = null;
  let calibratedOffsetY = null;
  let lastWinX = window.screenX ?? 0;
  let lastWinY = window.screenY ?? 0;

  function updateCalibration(e) {
    if (typeof e.screenX === 'number' && typeof e.clientX === 'number') {
      const dpr = window.devicePixelRatio || 1;
      const offY1 = e.screenY - e.clientY;
      const offY2 = Math.round(e.screenY / dpr - e.clientY);
      const wY = window.screenY ?? 0;

      // Filter: only accept offsets that correspond to a real browser header/tabs height (0..250px)
      if (offY1 >= wY && offY1 <= wY + 250) {
        calibratedOffsetY = offY1;
        calibratedOffsetX = e.screenX - e.clientX;
      } else if (offY2 >= wY && offY2 <= wY + 250) {
        calibratedOffsetY = offY2;
        calibratedOffsetX = Math.round(e.screenX / dpr - e.clientX);
      }
      lastWinX = window.screenX ?? 0;
      lastWinY = window.screenY ?? 0;
    }
  }

  window.addEventListener('pointermove', updateCalibration, { passive: true, capture: true });
  window.addEventListener('pointerdown', updateCalibration, { passive: true, capture: true });

  function sendToOverlay(payload) {
    fetch('http://127.0.0.1:8765/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      mode: 'cors'
    }).then(r => r.json()).then(data => {
      if (data && typeof data.enabled === 'boolean') {
        isEnabled = data.enabled;
      }
      if (data && data.side) {
        manualSide = data.side;
      }
    }).catch(() => {
      const b = payload.board;
      const bParams = b ? `&bl=${b.left}&bt=${b.top}&bw=${b.width}&fl=${payload.flipped ? 1 : 0}` : '';
      const q = payload.show
        ? `s=1&x1=${payload.x1}&y1=${payload.y1}&x2=${payload.x2}&y2=${payload.y2}&sz=${payload.size}&m=${payload.move || ''}&d=${payload.depth || ''}${bParams}&t=${Date.now()}`
        : `s=0&t=${Date.now()}`;
      const img = new Image();
      img.src = `http://127.0.0.1:8765/u?${q}`;
    });
  }

  function updateOverlayCoords(boardEl, move, depth) {
    if (!isEnabled || document.hidden || !boardEl || !move || move.length < 4) {
      sendToOverlay({ show: false });
      return;
    }

    const rect = boardEl.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) {
      sendToOverlay({ show: false });
      return;
    }

    const isFlipped = boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped');
    const sqSize = rect.width / 8;

    if (
      Math.abs((window.screenX ?? 0) - lastWinX) > 4 ||
      Math.abs((window.screenY ?? 0) - lastWinY) > 4
    ) {
      calibratedOffsetX = null;
      calibratedOffsetY = null;
      lastWinX = window.screenX ?? 0;
      lastWinY = window.screenY ?? 0;
    }

    let screenOffsetX, screenOffsetY;
    if (calibratedOffsetX !== null && calibratedOffsetY !== null) {
      screenOffsetX = calibratedOffsetX;
      screenOffsetY = calibratedOffsetY;
    } else {
      const winX = window.screenX ?? window.screenLeft ?? 0;
      const winY = window.screenY ?? window.screenTop ?? 0;
      const borderX = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
      let topBarHeight = Math.max(0, window.outerHeight - window.innerHeight - borderX);

      // Min Browser (Electron) where outerHeight == innerHeight
      const isMin = navigator.userAgent.includes('Min/') || Boolean(window.process?.versions?.electron);
      if (topBarHeight === 0 && isMin) {
        topBarHeight = 60; // Min tab bar standard height
      }

      screenOffsetX = winX + borderX;
      screenOffsetY = winY + topBarHeight;
    }

    function sqToScreenFallback(sq) {
      const file = sq.charCodeAt(0) - 97;
      const rank = parseInt(sq[1], 10) - 1;
      const col = isFlipped ? (7 - file) : file;
      const row = isFlipped ? rank : (7 - rank);

      return {
        x: Math.round(screenOffsetX + rect.left + (col + 0.5) * sqSize),
        y: Math.round(screenOffsetY + rect.top + (row + 0.5) * sqSize)
      };
    }

    const from = sqToScreenFallback(move.substring(0, 2));
    const to = sqToScreenFallback(move.substring(2, 4));

    sendToOverlay({
      show: true,
      board: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height
      },
      flipped: isFlipped,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      size: Math.round(sqSize),
      move: move,
      depth: depth || ''
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
          const depthMatch = line.match(/depth (\d+)/);
          if (pvMatch && pvMatch[1]) {
            currentBestMove = pvMatch[1];
            currentDepth = depthMatch ? depthMatch[1] : '';
            const boardEl = document.querySelector('wc-chess-board, .board');
            if (boardEl) updateOverlayCoords(boardEl, currentBestMove, currentDepth);
          }
        }

        if (line.startsWith('bestmove')) {
          const move = line.split(' ')[1];
          if (move && move !== '(none)' && move.length >= 4) {
            currentBestMove = move;
            const boardEl = document.querySelector('wc-chess-board, .board');
            if (boardEl) updateOverlayCoords(boardEl, currentBestMove, currentDepth);
          }
        }
      };

      stockfishWorker.postMessage('uci');
      stockfishWorker.postMessage('setoption name Skill Level value 20');
      stockfishWorker.postMessage('isready');
    } catch (_) {}
  }

  setupEngine();

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) sendToOverlay({ show: false });
    else lastBoardKey = '';
  });

  window.addEventListener('beforeunload', () => {
    sendToOverlay({ show: false });
  });

  window.addEventListener('resize', () => {
    const boardEl = document.querySelector('wc-chess-board, .board');
    if (boardEl && currentBestMove) updateOverlayCoords(boardEl, currentBestMove, currentDepth);
  });

  window.addEventListener('scroll', () => {
    const boardEl = document.querySelector('wc-chess-board, .board');
    if (boardEl && currentBestMove) updateOverlayCoords(boardEl, currentBestMove, currentDepth);
  }, { passive: true });

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
      updateOverlayCoords(state.boardEl, currentBestMove, currentDepth);
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


def get_asset_path(filename: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, "assets", filename)
    if os.path.exists(p):
        return p
    p_local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", filename)
    if os.path.exists(p_local):
        return p_local
    return filename


def app_icon() -> QIcon:
    return QIcon(pixmap_from_data_uri(LOGOS["pawn"], 128))


def install_scripts_and_extension() -> str:
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
            "name": "Chess Stealth Zero-DOM",
            "version": "2.2.0",
            "description": "Zero-DOM bridge for Windows Stealth Overlay with WDA_EXCLUDEFROMCAPTURE.",
            "permissions": ["storage"],
            "host_permissions": ["*://*.chess.com/*", "http://127.0.0.1:8765/*"],
            "background": {"service_worker": "background.js"},
            "content_scripts": [
                {
                    "matches": ["*://*.chess.com/*", "*://chess.com/*"],
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
    return ext_dir


BROWSER_PATHS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ],
    "brave": [
        os.path.join(os.getenv("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "coccoc": [
        os.path.join(os.getenv("LOCALAPPDATA", ""), "CocCoc", "Browser", "Application", "browser.exe"),
        r"C:\Program Files\CocCoc\Browser\Application\browser.exe",
        r"C:\Program Files (x86)\CocCoc\Browser\Application\browser.exe",
    ],
    "opera": [
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Opera", "opera.exe"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Opera GX", "opera.exe"),
        os.path.join(os.getenv("APPDATA", ""), "Opera Software", "Opera Stable", "opera.exe"),
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Mozilla Firefox", "firefox.exe"),
    ],
    "min": [
        os.path.join(os.getenv("LOCALAPPDATA", ""), "min", "Min.exe"),
    ],
}


def find_browser_exe(browser_type: str) -> str | None:
    for p in BROWSER_PATHS.get(browser_type, []):
        if p and os.path.exists(p):
            return p
    return None


def launch_browser_for_chess(browser_type: str):
    ext_dir = install_scripts_and_extension()
    chess_url = "https://www.chess.com/play/computer"
    exe_path = find_browser_exe(browser_type)

    try:
        if browser_type == "min" and exe_path:
            subprocess.Popen([exe_path, chess_url])
            return

        if browser_type in ("chrome", "edge", "brave", "coccoc", "opera") and exe_path:
            profile_dir = os.path.join(APP_DIR, f"profile_{browser_type}")
            os.makedirs(profile_dir, exist_ok=True)
            subprocess.Popen(
                [
                    exe_path,
                    f"--user-data-dir={profile_dir}",
                    f"--load-extension={ext_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    chess_url,
                ]
            )
            return

        if exe_path:
            subprocess.Popen([exe_path, chess_url])
            return

        os.startfile(chess_url)
    except Exception:
        try:
            os.startfile(chess_url)
        except Exception:
            pass


def find_browser_viewport() -> tuple[int, int, int, int, int] | None:
    """
    Tự động nhận diện chính xác 100% tọa độ Viewport trình duyệt (Chrome, Edge, Brave, Cốc Cốc, Opera, Firefox...)
    bằng Win32 API cấp hệ điều hành (không phụ thuộc vào độ cao Bookmarks bar, tab bar hay sidebar).
    Trả về: (left, top, width, height, dpi)
    """
    user32 = ctypes.windll.user32
    fg = user32.GetForegroundWindow()
    windows_to_check = [fg] if fg else []

    def enum_cb(hwnd, _):
        if hwnd != fg and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            windows_to_check.append(hwnd)
        return True

    user32.EnumWindows(
        ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_cb),
        0,
    )

    for hwnd in windows_to_check:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()

        cname = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cname, 256)
        cls = cname.value.lower()

        if ("chess" in title) or ("chrome_widgetwin_1" in cls) or ("mozillawindowclass" in cls):
            wrect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(wrect))
            vp = []

            def child_cb(chwnd, _):
                cc = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(chwnd, cc, 256)
                c_name = cc.value
                if c_name in ["Chrome_RenderWidgetHostHWND", "MozillaContentWindowClass"]:
                    cr = wintypes.RECT()
                    user32.GetWindowRect(chwnd, ctypes.byref(cr))
                    w, h = cr.right - cr.left, cr.bottom - cr.top
                    if w > 300 and h > 300:
                        dpi = 96
                        try:
                            dpi = user32.GetDpiForWindow(chwnd) or 96
                        except Exception:
                            pass
                        vp.append((cr.left, cr.top, w, h, dpi))
                return True

            user32.EnumChildWindows(
                hwnd,
                ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(child_cb),
                0,
            )
            if vp:
                # Ưu tiên chọn Viewport nội dung trang web thực sự (nằm dưới thanh toolbar/tabs của Electron/Min/Chrome)
                content_views = [c for c in vp if c[1] >= wrect.top + 20]
                if content_views:
                    content_views.sort(key=lambda item: item[2] * item[3], reverse=True)
                    return content_views[0]
                vp.sort(key=lambda item: item[2] * item[3], reverse=True)
                return vp[0]

            # Fallback cho Firefox / Window client area
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            crect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(crect))
            w, h = crect.right, crect.bottom
            if w > 300 and h > 300:
                dpi = 96
                try:
                    dpi = user32.GetDpiForWindow(hwnd) or 96
                except Exception:
                    pass
                return (pt.x, pt.y, w, h, dpi)

    return None


def compute_auto_aligned_arrow(
    board_dict: dict, move_str: str, flipped_flag: bool
) -> tuple[int, int, int, int, int] | None:
    if not board_dict or not move_str or len(move_str) < 4:
        return None
    try:
        vp = find_browser_viewport()
        if not vp:
            return None

        vp_left, vp_top, vp_w, vp_h, dpi = vp
        dpi_scale = max(1.0, dpi / 96.0)

        vp_left_logical = vp_left / dpi_scale
        vp_top_logical = vp_top / dpi_scale

        board_left = vp_left_logical + float(board_dict.get("left", 0))
        board_top = vp_top_logical + float(board_dict.get("top", 0))
        board_w = float(board_dict.get("width", 480))
        sq = board_w / 8.0

        is_flip = flipped_flag
        if arrow_state["side"] == "b":
            is_flip = True
        elif arrow_state["side"] == "w":
            is_flip = False

        f_col = ord(move_str[0].lower()) - ord("a")
        f_rank = int(move_str[1]) - 1
        t_col = ord(move_str[2].lower()) - ord("a")
        t_rank = int(move_str[3]) - 1

        c1 = (7 - f_col) if is_flip else f_col
        r1 = f_rank if is_flip else (7 - f_rank)
        c2 = (7 - t_col) if is_flip else t_col
        r2 = t_rank if is_flip else (7 - t_rank)

        x1 = int(round(board_left + (c1 + 0.5) * sq))
        y1 = int(round(board_top + (r1 + 0.5) * sq))
        x2 = int(round(board_left + (c2 + 0.5) * sq))
        y2 = int(round(board_top + (r2 + 0.5) * sq))
        size = int(round(sq))

        return x1, y1, x2, y2, size
    except Exception:
        return None


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
                    move_str = params.get("m", [""])[0]
                    aligned = None
                    if "bl" in params and "bt" in params and "bw" in params and move_str:
                        board_dict = {
                            "left": float(params["bl"][0]),
                            "top": float(params["bt"][0]),
                            "width": float(params["bw"][0]),
                        }
                        flipped_flag = params.get("fl", ["0"])[0] == "1"
                        aligned = compute_auto_aligned_arrow(board_dict, move_str, flipped_flag)

                    if aligned:
                        arrow_state["x1"], arrow_state["y1"], arrow_state["x2"], arrow_state["y2"], arrow_state["size"] = aligned
                        arrow_state["auto_aligned"] = True
                    else:
                        arrow_state["x1"] = int(float(params.get("x1", [0])[0]))
                        arrow_state["y1"] = int(float(params.get("y1", [0])[0]))
                        arrow_state["x2"] = int(float(params.get("x2", [0])[0]))
                        arrow_state["y2"] = int(float(params.get("y2", [0])[0]))
                        arrow_state["size"] = int(float(params.get("sz", [60])[0]))
                        arrow_state["auto_aligned"] = False

                    arrow_state["move"] = move_str
                    arrow_state["depth"] = params.get("d", [""])[0]
                except Exception:
                    pass
        self._send_cors()
        resp = json.dumps({"ok": True, "enabled": arrow_state["enabled"], "side": arrow_state["side"]}).encode()
        self.wfile.write(resp)

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
                    move_str = str(data.get("move", ""))
                    board_dict = data.get("board")
                    flipped_flag = bool(data.get("flipped", False))
                    aligned = None
                    if board_dict and move_str:
                        aligned = compute_auto_aligned_arrow(board_dict, move_str, flipped_flag)

                    if aligned:
                        arrow_state["x1"], arrow_state["y1"], arrow_state["x2"], arrow_state["y2"], arrow_state["size"] = aligned
                        arrow_state["auto_aligned"] = True
                    else:
                        arrow_state["x1"] = int(data.get("x1", 0))
                        arrow_state["y1"] = int(data.get("y1", 0))
                        arrow_state["x2"] = int(data.get("x2", 0))
                        arrow_state["y2"] = int(data.get("y2", 0))
                        arrow_state["size"] = int(data.get("size", 60))
                        arrow_state["auto_aligned"] = False

                    arrow_state["move"] = move_str
                    arrow_state["depth"] = str(data.get("depth", ""))
            except Exception:
                pass
        self._send_cors()
        resp = json.dumps({"ok": True, "enabled": arrow_state["enabled"], "side": arrow_state["side"]}).encode()
        self.wfile.write(resp)

    def log_message(self, format, *args):
        return


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

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
        )
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

    def _tick(self):
        self.update()

    def paintEvent(self, _event):
        now = time.time()
        gate_scale = derive_arrow_scale_factor()
        if (
            not arrow_state["enabled"]
            or gate_scale <= 0.0
            or not arrow_state["show"]
            or (now - arrow_state["last_seen"] > 1.8)
        ):
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
        color = arrow_state.get("qcolor", QColor(245, 158, 11, 230))
        painter.setBrush(color)
        painter.drawPolygon(poly)


def ensure_overlay_running(active_key: str, hwid: str):
    global _OVERLAY_INSTANCE
    if _OVERLAY_INSTANCE is not None:
        return

    def run_http():
        try:
            srv = HTTPServer(("127.0.0.1", 8765), StealthOverlayServer)
            srv.serve_forever()
        except Exception:
            pass

    threading.Thread(target=run_http, daemon=True).start()

    def periodic_reverify():
        while True:
            time.sleep(1800)
            activate_or_verify_key(API_BASE_URL, active_key, hwid)

    threading.Thread(target=periodic_reverify, daemon=True).start()

    _OVERLAY_INSTANCE = QtStealthOverlay()
    _ACTIVE_WINDOWS.append(_OVERLAY_INSTANCE)
    _OVERLAY_INSTANCE.showFullScreen()


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
    s_lbl = QLabel("S T E A L T H")
    s_lbl.setObjectName("BrandStealth")
    txt_col.addWidget(c_lbl)
    txt_col.addWidget(s_lbl)
    h.addLayout(txt_col)
    return w


SUN_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='#f5f5f7' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
  <circle cx='12' cy='12' r='4'/>
  <path d='M12 2v2'/><path d='M12 20v2'/><path d='m4.93 4.93 1.41 1.41'/><path d='m17.66 17.66 1.41 1.41'/>
  <path d='M2 12h2'/><path d='M20 12h2'/><path d='m6.34 17.66-1.41 1.41'/><path d='m19.07 4.93-1.41 1.41'/>
</svg>"""

MOON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='#1d1d1f' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
  <path d='M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z'/>
</svg>"""

LOGOUT_KEY_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
  <path d='m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4'/>
  <path d='m21 2-9.6 9.6'/>
  <circle cx='7.5' cy='15.5' r='5.5'/>
</svg>"""

PALETTE_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
  <circle cx='13.5' cy='6.5' r='.5' fill='currentColor'/>
  <circle cx='17.5' cy='10.5' r='.5' fill='currentColor'/>
  <circle cx='8.5' cy='7.5' r='.5' fill='currentColor'/>
  <circle cx='6.5' cy='12.5' r='.5' fill='currentColor'/>
  <path d='M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z'/>
</svg>"""


def render_svg_icon(svg_str: str, size: int = 16, color_override: str = None) -> QPixmap:
    if color_override:
        svg_str = svg_str.replace("stroke='currentColor'", f"stroke='{color_override}'").replace("fill='currentColor'", f"fill='{color_override}'")
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    renderer.render(p)
    p.end()
    return pix


AVAILABLE_ENGINES = [
    {
        "id": "sf_20",
        "name": "Stockfish 16",
        "details": "Level 20 • ~3500 ELO (Maximum)",
        "icon": "icon_engine_stockfish.png",
        "skill": 20,
    },
    {
        "id": "sf_16",
        "name": "Stockfish 16",
        "details": "Level 16 • ~2600 ELO (Grandmaster)",
        "icon": "icon_engine_stockfish.png",
        "skill": 16,
    },
    {
        "id": "sf_12",
        "name": "Stockfish 16",
        "details": "Level 12 • ~2000 ELO (Master)",
        "icon": "icon_engine_stockfish.png",
        "skill": 12,
    },
    {
        "id": "komodo_dragon",
        "name": "Dragon 3.3 by Komodo",
        "details": "MCTS Tactical • ~3450 ELO",
        "icon": "icon_engine_komodo.png",
        "skill": 20,
    },
    {
        "id": "lc0",
        "name": "Leela Chess Zero (Lc0)",
        "details": "Deep Neural Net • ~3400 ELO",
        "icon": "icon_engine_lc0.png",
        "skill": 20,
    },
    {
        "id": "maia_1900",
        "name": "Maia Chess 1900",
        "details": "Human Master Style • ~1900 ELO",
        "icon": "icon_engine_maia.png",
        "skill": 12,
    },
    {
        "id": "maia_1500",
        "name": "Maia Chess 1500",
        "details": "Human Club Style • ~1500 ELO",
        "icon": "icon_engine_maia.png",
        "skill": 8,
    },
    {
        "id": "maia_1100",
        "name": "Maia Chess 1100",
        "details": "Human Casual Style • ~1100 ELO",
        "icon": "icon_engine_maia.png",
        "skill": 4,
    },
]


def _build_qss(theme: str) -> str:
    chev_dark = get_asset_path("chevron_dark.png").replace("\\", "/")
    chev_light = get_asset_path("chevron_light.png").replace("\\", "/")
    if theme == "dark":
        return f"""
        QWidget#Root {{ background-color: #090B10; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }}
        QLabel#BrandTitle {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: #FFFFFF;
        }}
        QPushButton#ThemeIconBtn {{
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            min-width: 32px; max-width: 32px;
            min-height: 32px; max-height: 32px;
        }}
        QPushButton#ThemeIconBtn:hover {{
            background-color: rgba(255, 255, 255, 0.12);
            border-color: rgba(255, 255, 255, 0.22);
        }}
        QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {{
            background-color: transparent;
            color: #A1A1AA;
            border: none;
            border-radius: 6px;
            min-width: 28px; max-width: 28px;
            min-height: 28px; max-height: 28px;
            font-size: 13px;
            font-weight: 700;
        }}
        QPushButton#WindowCtrlBtn:hover {{
            background-color: rgba(255, 255, 255, 0.10);
            color: #FFFFFF;
        }}
        QPushButton#WindowCloseBtn:hover {{
            background-color: rgba(255, 255, 255, 0.16);
            color: #FFFFFF;
        }}
        QFrame#StatusCard {{
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
        }}
        QLabel#StatusPill[state="live"] {{
            background-color: rgba(16, 185, 129, 0.16);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.28);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="waiting"] {{
            background-color: rgba(255, 255, 255, 0.06);
            color: #A1A1AA;
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="offline"] {{
            background-color: rgba(239, 68, 68, 0.15);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.28);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#MetaText {{
            color: #71717A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 500;
        }}
        QLabel#SquareBadge {{
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 8px;
            padding: 2px 10px;
            color: #FFFFFF;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#MoveArrow {{
            color: #A1A1AA;
            font-size: 18px;
            font-weight: 600;
        }}
        QLabel#ReadyBig[state="ready"] {{
            color: #FFFFFF;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 26px;
            font-weight: 800;
            letter-spacing: 1px;
        }}
        QLabel#ReadyBig[state="deactivated"] {{
            color: #F87171;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#EvalChip {{
            background-color: rgba(16, 185, 129, 0.16);
            color: #10B981;
            border: 1px solid rgba(16, 185, 129, 0.30);
            border-radius: 8px;
            padding: 3px 12px;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
        }}
        QLabel#SubDetail {{
            color: #A1A1AA;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
        }}
        QLabel#SectionHeader {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 600;
            color: #E4E4E7;
        }}
        QFrame#EngineCard {{
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
        }}
        QFrame#EngineCard:hover {{
            background-color: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.16);
        }}
        QLabel#EngineTitle {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: #FFFFFF;
        }}
        QLabel#EngineSub {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            color: #A1A1AA;
        }}
        QPushButton#MainActionBtnDeactivate {{
            background-color: rgba(255, 255, 255, 0.05);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.20);
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnDeactivate:hover {{
            background-color: rgba(239, 68, 68, 0.18);
            border-color: rgba(239, 68, 68, 0.50);
            color: #EF4444;
        }}
        QPushButton#MainActionBtnActivate {{
            background-color: #FFFFFF;
            color: #090B10;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border: none;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnActivate:hover {{
            background-color: #F4F4F5;
        }}
        """
    else:
        return f"""
        QWidget#Root {{ background-color: #FFFFFF; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }}
        QLabel#BrandTitle {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
            color: #090B10;
        }}
        QPushButton#ThemeIconBtn {{
            background-color: #FFFFFF;
            border: 1px solid rgba(0, 0, 0, 0.12);
            border-radius: 8px;
            min-width: 32px; max-width: 32px;
            min-height: 32px; max-height: 32px;
        }}
        QPushButton#ThemeIconBtn:hover {{
            background-color: #F4F4F5;
            border-color: rgba(0, 0, 0, 0.20);
        }}
        QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {{
            background-color: transparent;
            color: #71717A;
            border: none;
            border-radius: 6px;
            min-width: 28px; max-width: 28px;
            min-height: 28px; max-height: 28px;
            font-size: 13px;
            font-weight: 700;
        }}
        QPushButton#WindowCtrlBtn:hover {{
            background-color: rgba(0, 0, 0, 0.06);
            color: #090B10;
        }}
        QPushButton#WindowCloseBtn:hover {{
            background-color: rgba(0, 0, 0, 0.10);
            color: #090B10;
        }}
        QFrame#StatusCard {{
            background-color: #FFFFFF;
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 14px;
        }}
        QLabel#StatusPill[state="live"] {{
            background-color: rgba(5, 150, 105, 0.10);
            color: #059669;
            border: 1px solid rgba(5, 150, 105, 0.20);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="waiting"] {{
            background-color: #F4F4F5;
            color: #52525B;
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="offline"] {{
            background-color: #FEF2F2;
            color: #DC2626;
            border: 1px solid rgba(220, 38, 38, 0.25);
            border-radius: 6px;
            padding: 2px 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#MetaText {{
            color: #71717A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 500;
        }}
        QLabel#SquareBadge {{
            background-color: #F4F4F5;
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 8px;
            padding: 2px 10px;
            color: #090B10;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#MoveArrow {{
            color: #71717A;
            font-size: 18px;
            font-weight: 600;
        }}
        QLabel#ReadyBig[state="ready"] {{
            color: #090B10;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 26px;
            font-weight: 800;
            letter-spacing: 1px;
        }}
        QLabel#ReadyBig[state="deactivated"] {{
            color: #DC2626;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#EvalChip {{
            background-color: rgba(5, 150, 105, 0.10);
            color: #059669;
            border: 1px solid rgba(5, 150, 105, 0.20);
            border-radius: 8px;
            padding: 3px 12px;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
        }}
        QLabel#SubDetail {{
            color: #71717A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
        }}
        QLabel#SectionHeader {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 600;
            color: #27272A;
        }}
        QFrame#EngineCard {{
            background-color: #FFFFFF;
            border: 1px solid rgba(0, 0, 0, 0.08);
            border-radius: 12px;
        }}
        QFrame#EngineCard:hover {{
            background-color: #FFFFFF;
            border: 1px solid rgba(0, 0, 0, 0.18);
        }}
        QLabel#EngineTitle {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: #090B10;
        }}
        QLabel#EngineSub {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            color: #52525B;
        }}
        QPushButton#MainActionBtnDeactivate {{
            background-color: #FFFFFF;
            color: #090B10;
            border: 1px solid rgba(0, 0, 0, 0.18);
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnDeactivate:hover {{
            background-color: #FEE2E2;
            border-color: rgba(220, 38, 38, 0.45);
            color: #B91C1C;
        }}
        QPushButton#MainActionBtnActivate {{
            background-color: #18181B;
            color: #FFFFFF;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border: none;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnActivate:hover {{
            background-color: #27272A;
        }}
        """


class MetallicWordmarkLabel(QLabel):
    def __init__(self, text: str = "PRO", theme: str = "dark", parent=None):
        super().__init__(parent)
        self.wordmark = text
        self.theme = theme
        self.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
        self.setFixedSize(40 if text == "FREE" else 32, 18)

    def set_data(self, text: str, theme: str):
        self.wordmark = text
        self.theme = theme
        self.setFixedSize(40 if text == "FREE" else 32, 18)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = self.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.3)
        painter.setFont(font)

        grad = QLinearGradient(0, 2, 0, 16)
        if self.theme == "dark":
            if self.wordmark == "PRO":
                grad.setColorAt(0.0, QColor("#FFFFFF"))
                grad.setColorAt(0.35, QColor("#E2E8F0"))
                grad.setColorAt(0.65, QColor("#94A3B8"))
                grad.setColorAt(1.0, QColor("#CBD5E1"))
            else:
                grad.setColorAt(0.0, QColor("#CBD5E1"))
                grad.setColorAt(0.50, QColor("#94A3B8"))
                grad.setColorAt(1.0, QColor("#64748B"))
        else:
            if self.wordmark == "PRO":
                grad.setColorAt(0.0, QColor("#0F172A"))
                grad.setColorAt(0.35, QColor("#334155"))
                grad.setColorAt(0.65, QColor("#64748B"))
                grad.setColorAt(1.0, QColor("#1E293B"))
            else:
                grad.setColorAt(0.0, QColor("#64748B"))
                grad.setColorAt(0.50, QColor("#475569"))
                grad.setColorAt(1.0, QColor("#0F172A"))

        painter.setPen(QPen(grad, 1))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.wordmark)
        painter.end()


class LuxuryStatusCard(QFrame):
    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("StatusCard")
        self.setFixedHeight(106)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self.status_pill = QLabel("●  LIVE LOCKED")
        self.status_pill.setObjectName("StatusPill")
        top_row.addWidget(self.status_pill)
        top_row.addStretch()

        self.meta_lbl = QLabel("Depth 15  •  Stockfish 16")
        self.meta_lbl.setObjectName("MetaText")
        top_row.addWidget(self.meta_lbl)
        lay.addLayout(top_row)

        self.hero_row = QHBoxLayout()
        self.hero_row.setContentsMargins(0, 2, 0, 2)
        self.hero_row.setSpacing(8)

        self.from_sq = QLabel("E2")
        self.from_sq.setObjectName("SquareBadge")
        self.hero_row.addWidget(self.from_sq)

        self.arrow_sym = QLabel("→")
        self.arrow_sym.setObjectName("MoveArrow")
        self.hero_row.addWidget(self.arrow_sym)

        self.to_sq = QLabel("E4")
        self.to_sq.setObjectName("SquareBadge")
        self.hero_row.addWidget(self.to_sq)

        self.ready_big = QLabel("READY")
        self.ready_big.setObjectName("ReadyBig")
        self.ready_big.hide()
        self.hero_row.addWidget(self.ready_big)

        self.hero_row.addStretch()

        self.eval_chip = QLabel("+0.45")
        self.eval_chip.setObjectName("EvalChip")
        self.hero_row.addWidget(self.eval_chip)
        lay.addLayout(self.hero_row)

        self.sub_lbl = QLabel("White Pawn  •  Recommended Move")
        self.sub_lbl.setObjectName("SubDetail")
        lay.addWidget(self.sub_lbl)

    def show_live_move(self, from_sq: str, to_sq: str, eval_str: str, piece: str, depth: str):
        self.from_sq.show()
        self.arrow_sym.show()
        self.to_sq.show()
        self.eval_chip.show()
        self.ready_big.hide()

        self.from_sq.setText(from_sq.upper())
        self.to_sq.setText(to_sq.upper())
        self.eval_chip.setText(eval_str)
        self.status_pill.setText("●  LIVE")
        self.status_pill.setProperty("state", "live")
        self.meta_lbl.setText(f"Depth {depth}  •  0.3s")
        self.sub_lbl.setText(f"{piece}  •  Recommended Move")
        self._refresh_styles()

    def show_waiting(self, is_connected: bool = True):
        self.from_sq.hide()
        self.arrow_sym.hide()
        self.to_sq.hide()
        self.eval_chip.hide()
        self.ready_big.show()

        self.ready_big.setText("READY")
        self.ready_big.setProperty("state", "ready")
        self.status_pill.setText("●  CONNECTED" if is_connected else "●  WAITING")
        self.status_pill.setProperty("state", "waiting")
        self.meta_lbl.setText("Chess.com Engine")
        self.sub_lbl.setText("Start a game on Chess.com to detect moves")
        self._refresh_styles()

    def show_deactivated(self):
        self.from_sq.hide()
        self.arrow_sym.hide()
        self.to_sq.hide()
        self.eval_chip.hide()
        self.ready_big.show()

        self.ready_big.setText("DEACTIVATED")
        self.ready_big.setProperty("state", "deactivated")
        self.status_pill.setText("●  OFFLINE")
        self.status_pill.setProperty("state", "offline")
        self.meta_lbl.setText("Assist Paused")
        self.sub_lbl.setText("Click ACTIVATE to resume live analysis")
        self._refresh_styles()

    def _refresh_styles(self):
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.ready_big.style().unpolish(self.ready_big)
        self.ready_big.style().polish(self.ready_big)


class ArrowPreviewWidget(QWidget):
    def __init__(self, color: QColor, theme: str = "light", parent=None):
        super().__init__(parent)
        self.arrow_color = color
        self.theme = theme
        self.setFixedHeight(46)

    def set_color(self, color: QColor):
        self.arrow_color = color
        self.update()

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        bg_rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)
        bg_col = QColor(255, 255, 255) if self.theme == "light" else QColor(255, 255, 255, 12)
        border_col = QColor(0, 0, 0, 24) if self.theme == "light" else QColor(255, 255, 255, 24)
        p.setBrush(bg_col)
        p.setPen(QPen(border_col, 1))
        p.drawRoundedRect(bg_rect, 10, 10)

        arrow_len = 86.0
        cx = w / 2.0
        shaft_start_x = cx - (arrow_len / 2.0)
        head_tip_x = cx + (arrow_len / 2.0)
        head_len = 18.0
        head_base_x = head_tip_x - head_len
        cy = h / 2.0
        shaft_half_thick = 5.0
        head_half_thick = 12.0

        poly = QPolygonF([
            QPointF(shaft_start_x, cy - shaft_half_thick),
            QPointF(head_base_x, cy - shaft_half_thick),
            QPointF(head_base_x, cy - head_half_thick),
            QPointF(head_tip_x, cy),
            QPointF(head_base_x, cy + head_half_thick),
            QPointF(head_base_x, cy + shaft_half_thick),
            QPointF(shaft_start_x, cy + shaft_half_thick),
        ])

        p.setBrush(self.arrow_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(poly)
        p.end()


class ColorPickerButton(QPushButton):
    def __init__(self, color: QColor, on_color_changed=None, theme: str = "light", parent=None):
        super().__init__(parent)
        self.current_color = color
        self.on_color_changed = on_color_changed
        self.theme = theme
        self.setFixedSize(68, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._open_dialog)

    def set_color(self, color: QColor):
        self.current_color = color
        self.update()

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def _open_dialog(self):
        new_color = QColorDialog.getColor(
            self.current_color,
            self.window(),
            "Choose Arrow Color (RGB)",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if new_color.isValid():
            self.current_color = new_color
            self.update()
            if self.on_color_changed:
                self.on_color_changed(new_color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        bg_col = QColor(255, 255, 255) if self.theme == "light" else QColor(255, 255, 255, 14)
        border_col = QColor(0, 0, 0, 28) if self.theme == "light" else QColor(255, 255, 255, 28)
        p.setBrush(bg_col)
        p.setPen(QPen(border_col, 1))
        p.drawRoundedRect(rect, 10, 10)

        swatch_rect = QRectF(8, 8, 30, 30)
        p.setBrush(self.current_color)
        p.setPen(QPen(QColor(0, 0, 0, 35) if self.theme == "light" else QColor(255, 255, 255, 60), 1))
        p.drawRoundedRect(swatch_rect, 7, 7)

        icon_pix = render_svg_icon(PALETTE_SVG, 16, "#4B5563" if self.theme == "light" else "#9CA3AF")
        p.drawPixmap(44, 15, icon_pix)
        p.end()


class ColorSwatch(QPushButton):
    def __init__(self, name: str, color: QColor, on_click=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.color = color
        self.on_click = on_click
        self.is_active = False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._handle_click)

    def _handle_click(self):
        if self.on_click:
            self.on_click(self.name)

    def set_active(self, active: bool):
        self.is_active = active
        self.update()


class EngineCard(QFrame):
    def __init__(self, engine_name: str = "Stockfish 16", details: str = "Level 20 • ~3500 ELO (Maximum)", icon_file: str = "icon_engine_stockfish.png", on_select=None, theme: str = "light", parent=None):
        super().__init__(parent)
        self.setObjectName("EngineCard")
        self.engine_name = engine_name
        self.details = details
        self.icon_file = icon_file
        self.on_select = on_select
        self.theme = theme
        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 14, 8)
        layout.setSpacing(12)

        self.icon_box = QLabel()
        self.icon_box.setObjectName("EngineIconBox")
        self.icon_box.setFixedSize(38, 38)
        self.icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel(self.engine_name)
        self.title_lbl.setObjectName("EngineTitle")
        self.title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.sub_lbl = QLabel(self.details)
        self.sub_lbl.setObjectName("EngineSub")
        self.sub_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.sub_lbl)
        layout.addLayout(text_col, 1)

        self.chevron_lbl = QLabel()
        self.chevron_lbl.setObjectName("EngineChevron")
        self.chevron_lbl.setFixedSize(16, 16)
        self.chevron_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chevron_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.chevron_lbl)

        self._update_assets()

    def set_data(self, name: str, details: str, icon_file: str = "icon_engine_stockfish.png"):
        self.engine_name = name
        self.details = details
        self.icon_file = icon_file
        self.title_lbl.setText(name)
        self.sub_lbl.setText(details)
        self._update_assets()

    def set_theme(self, theme: str):
        self.theme = theme
        self._update_assets()

    def _update_assets(self):
        chev_file = "chevron_dark.png" if self.theme == "light" else "chevron_light.png"
        chev_p = get_asset_path(chev_file)
        if os.path.exists(chev_p):
            self.chevron_lbl.setPixmap(QPixmap(chev_p).scaled(10, 10, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        icon_p = get_asset_path(self.icon_file)
        if os.path.exists(icon_p):
            pix = QPixmap(icon_p).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_box.setPixmap(pix)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_engine_menu()
        super().mousePressEvent(event)

    def _show_engine_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181B;
                color: #F4F4F5;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px;
                font-family: -apple-system, "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
            }
        """ if self.theme == "dark" else """
            QMenu {
                background-color: #FFFFFF;
                color: #18181B;
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 8px;
                padding: 6px;
                font-family: -apple-system, "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 24px 8px 12px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: #F4F4F5;
            }
        """)

        for eng in AVAILABLE_ENGINES:
            action_text = f"{eng['name']}  —  {eng['details']}"
            act = QAction(action_text, menu)
            ic_p = get_asset_path(eng["icon"])
            if os.path.exists(ic_p):
                act.setIcon(QIcon(ic_p))
            def _make_handler(target_eng=eng):
                def _h():
                    self.set_data(target_eng["name"], target_eng["details"], target_eng["icon"])
                    if self.on_select:
                        self.on_select(target_eng)
                return _h
            act.triggered.connect(_make_handler(eng))
            menu.addAction(act)

        menu.exec(self.mapToGlobal(QPointF(0, self.height()).toPoint()))


class ControlCenterWindow(QWidget):
    def __init__(self, active_key: str, hwid: str):
        super().__init__()
        self.active_key = active_key
        self.hwid = hwid
        self.setObjectName("Root")
        self.setWindowTitle("Chess Stealth")
        self.setWindowIcon(app_icon())
        self.setFixedWidth(380)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos = None

        self.active_color_name = "Orange (Classic)"
        self.swatches = {
            name: ColorSwatch(name, qc, self._on_color_changed)
            for name, qc in COLOR_PRESETS.items()
        }
        if "Orange (Classic)" in self.swatches:
            self.swatches["Orange (Classic)"].is_active = True

        self._theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._theme_shortcut.activated.connect(self._toggle_theme)

        ensure_overlay_running(active_key, hwid)
        install_scripts_and_extension()

        self._build_ui()
        self.setStyleSheet(_build_qss(_CURRENT_THEME))
        self.adjustSize()

        self._last_rendered_sig = None
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._sync_live_status)
        self.status_timer.start(250)

    @property
    def color_combo(self):
        class _Proxy:
            def __init__(self, p): self.p = p
            def currentText(self): return self.p.active_color_name
        return _Proxy(self)

    @property
    def side_combo(self):
        class _Proxy:
            def __init__(self, p): self.p = p
            def currentData(self): return arrow_state.get("side", "auto")
        return _Proxy(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos") and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)
        p.setClipPath(path)
        bg_col = QColor("#090B10") if _CURRENT_THEME == "dark" else QColor("#FFFFFF")
        p.fillRect(self.rect(), bg_col)
        p.setClipping(False)

        border_pen = QPen(QColor(255, 255, 255, 25) if _CURRENT_THEME == "dark" else QColor(0, 0, 0, 24), 1)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)

    def closeEvent(self, event):
        event.accept()
        if hasattr(self, "status_timer") and self.status_timer.isActive():
            self.status_timer.stop()

    def _key_tier_wordmark(self) -> str:
        k = (self.active_key or "").upper()
        if k.startswith("LIFEVIP-") or k.startswith("PRO30D-"):
            return "PRO"
        return "FREE"

    def _update_brand_logo(self):
        icon_name = "queen_light.png" if _CURRENT_THEME == "dark" else "queen_dark.png"
        icon_path = get_asset_path(icon_name)
        if hasattr(self, "brand_logo_lbl") and os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.brand_logo_lbl.setPixmap(pix)

    def _update_logout_icon(self):
        col = "#FFFFFF" if _CURRENT_THEME == "dark" else "#0F172A"
        icon_pix = render_svg_icon(LOGOUT_KEY_SVG, 15, col)
        self.logout_btn.setIcon(QIcon(icon_pix))
        self.logout_btn.setIconSize(QSize(15, 15))

    def _logout_key(self):
        reply = QMessageBox.question(
            self,
            "Đổi Key / Đăng xuất",
            "Bạn có chắc muốn đăng xuất mã key hiện tại để nhập key khác không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(CONFIG_FILE):
                    os.remove(CONFIG_FILE)
                cache_f = os.path.join(APP_DIR, "verified_session.json")
                if os.path.exists(cache_f):
                    os.remove(cache_f)
            except Exception:
                pass
            self.close()
            def open_control_center(k: str):
                ctrl = ControlCenterWindow(k, self.hwid)
                _ACTIVE_WINDOWS.append(ctrl)
                ctrl.show()
            win = ActivationWindow(self.hwid, open_control_center)
            _ACTIVE_WINDOWS.append(win)
            win.show()

    def _update_theme_icon(self):
        icon_pix = render_svg_icon(SUN_SVG if _CURRENT_THEME == "dark" else MOON_SVG, 16)
        self.theme_btn.setIcon(QIcon(icon_pix))
        self.theme_btn.setIconSize(QSize(16, 16))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 20)
        root.setSpacing(14)

        # 1. Header Bar: Queen Logo + Chess Stealth + PRO + Logout + Theme + Min + Close
        top = QHBoxLayout()
        top.setSpacing(8)

        self.brand_logo_lbl = QLabel()
        self._update_brand_logo()
        top.addWidget(self.brand_logo_lbl)

        title = QLabel("Chess Stealth")
        title.setObjectName("BrandTitle")
        top.addWidget(title)

        tier_txt = self._key_tier_wordmark()
        self.pro_lbl = MetallicWordmarkLabel(tier_txt, _CURRENT_THEME)
        top.addWidget(self.pro_lbl)

        top.addStretch()

        self.logout_btn = QPushButton()
        self.logout_btn.setObjectName("ThemeIconBtn")
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setToolTip("Đổi Key / Đăng xuất")
        self._update_logout_icon()
        self.logout_btn.clicked.connect(self._logout_key)
        top.addWidget(self.logout_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeIconBtn")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_theme_icon()
        self.theme_btn.clicked.connect(self._toggle_theme)
        top.addWidget(self.theme_btn)

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("WindowCtrlBtn")
        self.min_btn.setFixedSize(28, 28)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.showMinimized)
        top.addWidget(self.min_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("WindowCloseBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close)
        top.addWidget(self.close_btn)

        root.addLayout(top)

        # 2. Status Card (Luxury tactical move badges & status pill)
        self.status_card = LuxuryStatusCard(theme=_CURRENT_THEME)
        root.addWidget(self.status_card)

        # 3. Engine Section
        eng_sec = QVBoxLayout()
        eng_sec.setSpacing(6)
        lbl_eng = QLabel("Engine")
        lbl_eng.setObjectName("SectionHeader")
        eng_sec.addWidget(lbl_eng)

        self.engine_card = EngineCard(
            engine_name="Stockfish 16",
            details="Level 20 • ~3500 ELO (Maximum)",
            icon_file="icon_engine_stockfish.png",
            on_select=self._on_engine_selected,
            theme=_CURRENT_THEME,
        )
        eng_sec.addWidget(self.engine_card)
        root.addLayout(eng_sec)

        # 4. Arrow Color Section
        arr_sec = QVBoxLayout()
        arr_sec.setSpacing(6)
        lbl_arr = QLabel("Arrow Color")
        lbl_arr.setObjectName("SectionHeader")
        arr_sec.addWidget(lbl_arr)

        arr_row = QHBoxLayout()
        arr_row.setSpacing(10)

        cur_color = arrow_state.get("qcolor", QColor(245, 158, 11, 230))
        self.color_btn = ColorPickerButton(
            cur_color,
            on_color_changed=self._on_rgb_color_picked,
            theme=_CURRENT_THEME,
        )
        arr_row.addWidget(self.color_btn)

        self.arrow_preview = ArrowPreviewWidget(cur_color, theme=_CURRENT_THEME)
        arr_row.addWidget(self.arrow_preview, 1)
        arr_sec.addLayout(arr_row)
        root.addLayout(arr_sec)

        # 5. Bottom Action Button: DEACTIVATE when running, ACTIVATE when paused
        self.action_btn = QPushButton("DEACTIVATE" if arrow_state["enabled"] else "ACTIVATE")
        self.action_btn.setObjectName("MainActionBtnDeactivate" if arrow_state["enabled"] else "MainActionBtnActivate")
        self.action_btn.setFixedHeight(44)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.clicked.connect(self._toggle_assist)
        root.addWidget(self.action_btn)

    def _on_engine_selected(self, eng_data: dict):
        skill_val = eng_data.get("skill", 20)
        arrow_state["skill"] = int(skill_val)
        depth_map = {20: (15, 250), 16: (13, 180), 12: (11, 140), 8: (9, 100), 4: (7, 80)}
        d_val, mt_val = depth_map.get(int(skill_val), (15, 250))
        arrow_state["target_depth"] = d_val
        arrow_state["movetime"] = mt_val

    def _on_rgb_color_picked(self, new_color: QColor):
        arrow_state["qcolor"] = new_color
        self.arrow_preview.set_color(new_color)
        if _OVERLAY_INSTANCE is not None:
            _OVERLAY_INSTANCE.update()

    def _on_color_changed(self, color_name: str):
        if color_name in COLOR_PRESETS:
            self.active_color_name = color_name
            for name, sw in self.swatches.items():
                sw.set_active(name == color_name)
            self._on_rgb_color_picked(COLOR_PRESETS[color_name])

    def _on_side_changed(self, side: str):
        arrow_state["side"] = side

    def _toggle_theme(self):
        global _CURRENT_THEME
        _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
        self.setStyleSheet(_build_qss(_CURRENT_THEME))
        self._update_brand_logo()
        self._update_theme_icon()
        self._update_logout_icon()
        self.pro_lbl.set_data(self._key_tier_wordmark(), _CURRENT_THEME)
        self.status_card.theme = _CURRENT_THEME
        self.engine_card.set_theme(_CURRENT_THEME)
        self.color_btn.set_theme(_CURRENT_THEME)
        self.arrow_preview.set_theme(_CURRENT_THEME)
        self._last_rendered_sig = None
        self._sync_live_status()
        self.update()

    def _toggle_assist(self):
        arrow_state["enabled"] = not arrow_state["enabled"]
        if not arrow_state["enabled"]:
            arrow_state["show"] = False
            if _OVERLAY_INSTANCE is not None:
                _OVERLAY_INSTANCE.update()
            self.action_btn.setObjectName("MainActionBtnActivate")
            self.action_btn.setText("ACTIVATE")
        else:
            if _OVERLAY_INSTANCE is not None:
                _OVERLAY_INSTANCE.showFullScreen()
                _OVERLAY_INSTANCE.update()
            self.action_btn.setObjectName("MainActionBtnDeactivate")
            self.action_btn.setText("DEACTIVATE")

        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)
        self._last_rendered_sig = None
        self._sync_live_status()

    def _sync_live_status(self):
        now = time.time()
        is_connected = (now - arrow_state.get("last_ping", 0.0) <= 2.5)
        is_showing_move = arrow_state.get("show", False) and (now - arrow_state.get("last_seen", 0.0) <= 1.5) and bool(arrow_state.get("move", ""))

        current_sig = (
            arrow_state.get("enabled", True),
            is_showing_move,
            arrow_state.get("move", "") if is_showing_move else "",
            arrow_state.get("depth", "") if is_showing_move else "",
            arrow_state.get("eval", "") if is_showing_move else "",
            arrow_state.get("ponder", "") if is_showing_move else "",
            arrow_state.get("piece", "") if is_showing_move else "",
            is_connected,
            _CURRENT_THEME,
        )
        if self._last_rendered_sig == current_sig:
            return
        self._last_rendered_sig = current_sig

        if not arrow_state["enabled"]:
            self.status_card.show_deactivated()
            self.action_btn.setObjectName("MainActionBtnActivate")
            self.action_btn.setText("ACTIVATE")
        elif is_showing_move:
            m = arrow_state["move"].upper()
            from_sq = m[:2]
            to_sq = m[2:4]
            if len(m) >= 5:
                to_sq += f"={m[4]}"
            ev = arrow_state.get("eval") or "+0.00"
            pc = arrow_state.get("piece", "")
            side_txt = "White" if pc.isupper() else ("Black" if pc.islower() else "Piece")
            piece_name = PIECE_NAMES_EN.get(pc.lower(), "Best Move")
            d = arrow_state.get("depth") or str(arrow_state["target_depth"])

            self.status_card.show_live_move(from_sq, to_sq, ev, f"{side_txt} {piece_name}", d)
            self.action_btn.setObjectName("MainActionBtnDeactivate")
            self.action_btn.setText("DEACTIVATE")
        else:
            self.status_card.show_waiting(is_connected=is_connected)
            self.action_btn.setObjectName("MainActionBtnDeactivate")
            self.action_btn.setText("DEACTIVATE")

        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)


# ================= MODERN LUXURY ALERT MODAL DIALOG =================
class AlertIconWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 52)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer soft glow circle
        painter.setPen(QPen(QColor(239, 68, 68, 80), 1.5))
        painter.setBrush(QBrush(QColor(239, 68, 68, 30)))
        painter.drawEllipse(2, 2, 48, 48)

        # Inner red circle
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(239, 68, 68, 220)))
        painter.drawEllipse(8, 8, 36, 36)

        # Vector exclamation mark
        pen = QPen(QColor(255, 255, 255), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(26, 17, 26, 27)
        painter.drawPoint(26, 34)


class ModernAlertDialog(QDialog):
    def __init__(self, title: str = "Invalid Key", message: str = "Invalid Key", is_dark: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        bg = "#0d121e" if is_dark else "#ffffff"
        border = "#1e293b" if is_dark else "#cbd5e1"
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
        """)

        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(20, 20, 20, 18)
        c_layout.setSpacing(10)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = AlertIconWidget()
        c_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)

        t_lbl = QLabel(title)
        t_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t_lbl.setStyleSheet(f"color: {'#f8fafc' if is_dark else '#0f172a'}; border: none;")
        t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(t_lbl)

        if message and message.strip() != title.strip():
            m_lbl = QLabel(message)
            m_lbl.setFont(QFont("Segoe UI", 12))
            m_lbl.setStyleSheet(f"color: {'#94a3b8' if is_dark else '#64748b'}; border: none;")
            m_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            m_lbl.setWordWrap(True)
            c_layout.addWidget(m_lbl)

        ok_btn = QPushButton("Dismiss")
        btn_bg = "#161e2e" if is_dark else "#f1f5f9"
        btn_color = "#f8fafc" if is_dark else "#0f172a"
        btn_border = "#283548" if is_dark else "#cbd5e1"
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_color};
                border: 1px solid {btn_border};
                border-radius: 10px;
                min-height: 38px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 24px;
            }}
            QPushButton:hover {{
                border: 1px solid #ef4444;
                color: #ef4444;
                background-color: rgba(239, 68, 68, 0.1);
            }}
        """)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        c_layout.addWidget(ok_btn)

        layout.addWidget(card)


class ActivationWindow(QWidget):
    def __init__(self, hwid: str, on_activated_cb=None):
        super().__init__()
        self.hwid = hwid
        self.on_activated_cb = on_activated_cb
        self._activated = False
        self.theme = _CURRENT_THEME

        self.setWindowTitle("Chess Stealth — Key Login")
        self.setFixedSize(840, 520)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos = None

        self._theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._theme_shortcut.activated.connect(self._toggle_theme)

        self.bg_dark_pix = QPixmap(get_asset_path("activation_bg_dark.png"))
        if not self.bg_dark_pix.isNull():
            self.bg_dark_pix.setDevicePixelRatio(self.bg_dark_pix.width() / 840.0)
        self.bg_light_pix = QPixmap(get_asset_path("activation_bg_light.png"))
        if not self.bg_light_pix.isNull():
            self.bg_light_pix.setDevicePixelRatio(self.bg_light_pix.width() / 840.0)

        self._build_ui()
        self._apply_theme()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos") and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def closeEvent(self, event):
        event.accept()
        if not self._activated:
            app = QApplication.instance()
            if app:
                app.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)
        painter.setClipPath(path)
        pix = self.bg_dark_pix if self.theme == "dark" else self.bg_light_pix
        if not pix.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), pix)
        else:
            painter.fillRect(self.rect(), QColor("#08090d" if self.theme == "dark" else "#f5f5f7"))
        painter.setClipping(False)

        border_pen = QPen(QColor(255, 255, 255, 28) if self.theme == "dark" else QColor(0, 0, 0, 24), 1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 16, 16)

    def _update_logo(self):
        icon_name = "queen_light.png" if self.theme == "dark" else "queen_dark.png"
        icon_path = get_asset_path(icon_name)
        if hasattr(self, "logo_lbl") and os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_lbl.setPixmap(pix)

    def _toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self._update_logo()
        self._apply_theme()
        self.update()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 22)
        root.setSpacing(6)

        # 1. Integrated Title Bar
        titlebar = QHBoxLayout()
        titlebar.setContentsMargins(4, 0, 0, 0)
        titlebar.setSpacing(8)

        self.logo_lbl = QLabel()
        self._update_logo()
        titlebar.addWidget(self.logo_lbl)

        self.brand_title = QLabel("Chess Stealth — Key Login")
        self.brand_title.setObjectName("BrandTitle")
        titlebar.addWidget(self.brand_title)

        titlebar.addStretch()

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("WindowCtrlBtn")
        self.min_btn.setFixedSize(28, 26)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.showMinimized)
        titlebar.addWidget(self.min_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("WindowCloseBtn")
        self.close_btn.setFixedSize(28, 26)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close)
        titlebar.addWidget(self.close_btn)

        root.addLayout(titlebar)

        # 2. Main Body Area
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(12, 8, 8, 0)
        body_layout.setSpacing(24)

        # Left Pane: Clean so 3D pieces artwork is completely visible
        left_pane = QVBoxLayout()
        left_pane.setContentsMargins(0, 0, 0, 0)
        left_pane.addStretch()
        body_layout.addLayout(left_pane, 1)

        # Right Pane: Frosted Card
        self.card = QFrame()
        self.card.setObjectName("FrostedCard")
        self.card.setFixedWidth(400)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 24, 28, 26)
        card_layout.setSpacing(14)

        # Top link: "Get 24h free key"
        top_link_row = QHBoxLayout()
        top_link_row.addStretch()
        self.get_key_link = QPushButton("Get 24h free key")
        self.get_key_link.setObjectName("TextLink")
        self.get_key_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.get_key_link.clicked.connect(lambda: os.startfile(WEB_GET_KEY_URL))
        top_link_row.addWidget(self.get_key_link)
        card_layout.addLayout(top_link_row)

        self.title_lbl = QLabel("Key Login")
        self.title_lbl.setObjectName("ActivateTitle")
        card_layout.addWidget(self.title_lbl)

        key_sec = QVBoxLayout()
        key_sec.setSpacing(6)
        self.key_sec_lbl = QLabel("License key")
        self.key_sec_lbl.setObjectName("FieldLabel")
        key_sec.addWidget(self.key_sec_lbl)

        self.key_input = QLineEdit()
        self.key_input.setObjectName("KeyInput")
        self.key_input.setPlaceholderText("FREE24H-XXXXXX-XXXXXXXX")
        self.key_input.returnPressed.connect(self.handle_activate)
        key_sec.addWidget(self.key_input)
        card_layout.addLayout(key_sec)

        hwid_sec = QVBoxLayout()
        hwid_sec.setSpacing(6)
        self.hwid_sec_lbl = QLabel("Device ID (HWID)")
        self.hwid_sec_lbl.setObjectName("FieldLabel")
        hwid_sec.addWidget(self.hwid_sec_lbl)

        hwid_row = QHBoxLayout()
        hwid_row.setSpacing(8)
        self.hwid_display = QLabel(self.hwid)
        self.hwid_display.setObjectName("HwidDisplay")
        hwid_row.addWidget(self.hwid_display, 1)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("CopyPillBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        def copy_hwid():
            QApplication.clipboard().setText(self.hwid)
            self.copy_btn.setText("Copied")
        self.copy_btn.clicked.connect(copy_hwid)
        hwid_row.addWidget(self.copy_btn)
        hwid_sec.addLayout(hwid_row)
        card_layout.addLayout(hwid_sec)

        self.sub_info_lbl = QLabel("Supports 24-hour, 30-day, and lifetime keys")
        self.sub_info_lbl.setObjectName("SubInfoLabel")
        card_layout.addWidget(self.sub_info_lbl)

        buy_link_row = QHBoxLayout()
        buy_link_row.addStretch()
        self.buy_link = QPushButton("Buy lifetime key")
        self.buy_link.setObjectName("TextLink")
        self.buy_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.buy_link.clicked.connect(lambda: os.startfile(BUY_LIFE_URL))
        buy_link_row.addWidget(self.buy_link)
        card_layout.addLayout(buy_link_row)

        self.act_btn = QPushButton("ACTIVATE")
        self.act_btn.setObjectName("ActivateBarBtn")
        self.act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_btn.clicked.connect(self.handle_activate)
        card_layout.addWidget(self.act_btn)

        body_layout.addWidget(self.card)
        root.addLayout(body_layout)

    def _apply_theme(self):
        if self.theme == "dark":
            self.setStyleSheet("""
            QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
            QLabel#BrandTitle { color: #f5f5f7; font-size: 14px; font-weight: 700; }
            QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
                background-color: transparent;
                color: #a1a1a6;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#WindowCtrlBtn:hover { background-color: rgba(255, 255, 255, 0.10); color: #ffffff; }
            QPushButton#WindowCloseBtn:hover { background-color: rgba(255, 255, 255, 0.16); color: #ffffff; }
            
            QFrame#FrostedCard {
                background-color: rgba(12, 14, 20, 0.78);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }
            QLabel#ActivateTitle {
                color: #ffffff; font-size: 38px; font-weight: 800; letter-spacing: -0.03em;
            }
            QLabel#FieldLabel {
                color: #98989f; font-size: 12px; font-weight: 600;
            }
            QLineEdit#KeyInput {
                background-color: rgba(255, 255, 255, 0.05); color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 11px;
                padding: 10px 14px; font-family: 'Consolas', monospace; font-size: 13px; font-weight: 600;
            }
            QLineEdit#KeyInput:focus {
                border: 1.5px solid #0a84ff; background-color: rgba(255, 255, 255, 0.08);
            }
            QLabel#HwidDisplay {
                color: #ffffff; font-family: 'Consolas', monospace; font-size: 13px; font-weight: 600;
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 9px;
                padding: 8px 12px;
            }
            QPushButton#CopyPillBtn {
                background-color: rgba(255, 255, 255, 0.10); color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 9px;
                padding: 8px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton#CopyPillBtn:hover {
                background-color: #0a84ff; border-color: #0a84ff;
            }
            QLabel#SubInfoLabel {
                color: #86868b; font-size: 11px; font-weight: 500;
            }
            QPushButton#TextLink {
                background: transparent; color: #a1a1a6; border: none; font-size: 12px; font-weight: 500;
                text-decoration: underline; padding: 2px 0;
            }
            QPushButton#TextLink:hover { color: #0a84ff; }
            
            QPushButton#ActivateBarBtn {
                background-color: #ffffff; color: #000000;
                border: none; border-radius: 12px;
                min-height: 48px; font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
            }
            QPushButton#ActivateBarBtn:hover { background-color: #f2f2f7; }
            QPushButton#ActivateBarBtn:pressed { background-color: #e5e5ea; }
            """)
        else:
            self.setStyleSheet("""
            QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
            QLabel#BrandTitle { color: #1d1d1f; font-size: 14px; font-weight: 700; }
            QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
                background-color: transparent;
                color: #71717A;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#WindowCtrlBtn:hover { background-color: rgba(0, 0, 0, 0.06); color: #090B10; }
            QPushButton#WindowCloseBtn:hover { background-color: rgba(0, 0, 0, 0.10); color: #090B10; }
            
            QFrame#FrostedCard {
                background-color: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(0, 0, 0, 0.09);
                border-radius: 20px;
            }
            QLabel#ActivateTitle {
                color: #1d1d1f; font-size: 38px; font-weight: 800; letter-spacing: -0.03em;
            }
            QLabel#FieldLabel {
                color: #48484a; font-size: 12px; font-weight: 600;
            }
            QLineEdit#KeyInput {
                background-color: rgba(255, 255, 255, 0.95); color: #1d1d1f;
                border: 1px solid #c7c7cc; border-radius: 11px;
                padding: 10px 14px; font-family: 'Consolas', monospace; font-size: 13px; font-weight: 600;
            }
            QLineEdit#KeyInput:focus {
                border: 1.5px solid #0071e3; background-color: #ffffff;
            }
            QLabel#HwidDisplay {
                color: #1d1d1f; font-family: 'Consolas', monospace; font-size: 13px; font-weight: 600;
                background-color: rgba(0, 0, 0, 0.03);
                border: 1px solid #d1d1d6; border-radius: 9px;
                padding: 8px 12px;
            }
            QPushButton#CopyPillBtn {
                background-color: rgba(0, 0, 0, 0.06); color: #1d1d1f;
                border: 1px solid #c7c7cc; border-radius: 9px;
                padding: 8px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton#CopyPillBtn:hover {
                background-color: #0071e3; color: #ffffff; border-color: #0071e3;
            }
            QLabel#SubInfoLabel {
                color: #6e6e73; font-size: 11px; font-weight: 500;
            }
            QPushButton#TextLink {
                background: transparent; color: #48484a; border: none; font-size: 12px; font-weight: 500;
                text-decoration: underline; padding: 2px 0;
            }
            QPushButton#TextLink:hover { color: #0071e3; }
            
            QPushButton#ActivateBarBtn {
                background-color: #1d1d1f; color: #ffffff;
                border: none; border-radius: 12px;
                min-height: 48px; font-size: 13px; font-weight: 800; letter-spacing: 0.08em;
            }
            QPushButton#ActivateBarBtn:hover { background-color: #0071e3; }
            QPushButton#ActivateBarBtn:pressed { background-color: #005bb5; }
            """)

    def handle_activate(self):
        k = self.key_input.text().strip()
        if not k:
            dlg = ModernAlertDialog("Missing Key", "Please enter your License Key.", is_dark=(self.theme == "dark"), parent=self)
            dlg.exec()
            return
        valid, msg = activate_or_verify_key(API_BASE_URL, k, self.hwid)
        if valid:
            self._activated = True
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(k)
            except Exception:
                pass
            self.close()
            if self.on_activated_cb:
                self.on_activated_cb(k)
        else:
            dlg = ModernAlertDialog("Invalid Key", "Invalid Key", is_dark=(self.theme == "dark"), parent=self)
            dlg.exec()


def main():
    global _CURRENT_THEME
    install_scripts_and_extension()
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
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    ctrl_window = None

    def open_control_center(k: str):
        nonlocal ctrl_window
        ctrl_window = ControlCenterWindow(k, hwid)
        _ACTIVE_WINDOWS.append(ctrl_window)
        ctrl_window.show()

    # Nếu key đã lưu hợp lệ thì mở thẳng Control Center
    if saved_key:
        valid, _ = activate_or_verify_key(API_BASE_URL, saved_key, hwid)
        if valid:
            open_control_center(saved_key)
            app.exec()
            return

    # Chưa có key: Mở màn hình kích hoạt Split-pane 3D
    act_win = ActivationWindow(hwid, on_activated_cb=open_control_center)
    _ACTIVE_WINDOWS.append(act_win)
    act_win.show()

    if url_scheme_key:
        act_win.key_input.setText(url_scheme_key)
        QTimer.singleShot(250, act_win.handle_activate)

    app.exec()


if __name__ == "__main__":
    main()
