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


def _build_qss(theme: str) -> str:
    if theme == "light":
        return """
        QWidget#Root { background-color: #f1f5f9; color: #0f172a; font-family: 'Segoe UI'; }
        QFrame#Card { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 16px; }
        QLabel#BrandChess { color: #0f172a; font-size: 16px; font-weight: 800; }
        QLabel#BrandStealth { color: #0284c7; font-size: 10px; font-weight: 800; }
        QLabel#SectionTitle { color: #334155; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
        QLineEdit {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
        }
        QLineEdit:focus { border: 2px solid #0284c7; background-color: #ffffff; }
        QPushButton#PrimaryBtn {
            background-color: #0284c7; color: #ffffff;
            border: none; border-radius: 10px;
            min-height: 44px; font-size: 13px; font-weight: 700;
        }
        QPushButton#PrimaryBtn:hover { background-color: #0369a1; }
        QPushButton#SecondaryBtn {
            background-color: #ffffff; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 10px;
            min-height: 38px; font-size: 12px; font-weight: 600; padding: 0 12px;
        }
        QPushButton#SecondaryBtn:hover { border: 1px solid #0284c7; background-color: #f8fafc; }
        QPushButton#ToggleBtnActive {
            background-color: #059669; color: #ffffff;
            border: 2px solid #10b981; border-radius: 12px;
            min-height: 48px; font-size: 14px; font-weight: 800; letter-spacing: 0.04em;
        }
        QPushButton#ToggleBtnActive:hover { background-color: #047857; }
        QPushButton#ToggleBtnPaused {
            background-color: #dc2626; color: #ffffff;
            border: 2px solid #ef4444; border-radius: 12px;
            min-height: 48px; font-size: 14px; font-weight: 800; letter-spacing: 0.04em;
        }
        QPushButton#ToggleBtnPaused:hover { background-color: #b91c1c; }
        QPushButton.BrowserCard {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 12px;
            min-height: 46px; font-size: 12px; font-weight: 700;
            text-align: left; padding: 6px 12px;
        }
        QPushButton.BrowserCard:hover { border: 1px solid #0284c7; background-color: #eef2f6; }
        QFrame#SubControlContainer {
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
        }
        QPushButton.SegmentBtn {
            background-color: transparent;
            color: #64748b;
            font-size: 11px;
            font-weight: 600;
            border: none;
            border-radius: 6px;
            padding: 5px 10px;
            min-height: 22px;
        }
        QPushButton.SegmentBtn:hover {
            background-color: #e2e8f0;
            color: #0f172a;
        }
        QPushButton.SegmentBtnActive {
            background-color: #0284c7;
            color: #ffffff;
            font-size: 11px;
            font-weight: 800;
            border: none;
            border-radius: 6px;
            padding: 5px 10px;
            min-height: 22px;
        }
        QPushButton.StepperBtn {
            background-color: #e2e8f0;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
            min-height: 24px;
            padding: 0 4px;
        }
        QPushButton.StepperBtn:hover {
            background-color: #cbd5e1;
            border: 1px solid #0284c7;
        }
        QLabel#StepperVal {
            color: #0f172a;
            font-family: 'Consolas';
            font-size: 12px;
            font-weight: 800;
            min-width: 44px;
        }
        QComboBox {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 8px;
            padding: 6px 12px; font-size: 12px; font-weight: 600;
        }
        QComboBox:hover { border: 1px solid #0284c7; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox QAbstractItemView {
            background-color: #ffffff; color: #0f172a;
            border: 1px solid #cbd5e1; selection-background-color: #e2e8f0;
            selection-color: #0284c7;
        }
        """
    return """
    QWidget#Root { background-color: #060911; color: #f8fafc; font-family: 'Segoe UI'; }
    QFrame#Card { background-color: #0d121e; border: 1px solid #1e293b; border-radius: 16px; }
    QLabel#BrandChess { color: #f8fafc; font-size: 16px; font-weight: 800; }
    QLabel#BrandStealth { color: #22d3ee; font-size: 10px; font-weight: 800; }
    QLabel#SectionTitle { color: #94a3b8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
    QLineEdit {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 10px;
        padding: 10px 12px; font-family: 'Consolas'; font-size: 14px; font-weight: 700;
    }
    QLineEdit:focus { border: 2px solid #22d3ee; background-color: #1a2436; }
    QPushButton#PrimaryBtn {
        background-color: #22d3ee; color: #060911;
        border: none; border-radius: 10px;
        min-height: 44px; font-size: 13px; font-weight: 800;
    }
    QPushButton#PrimaryBtn:hover { background-color: #38bdf8; }
    QPushButton#SecondaryBtn {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 10px;
        min-height: 38px; font-size: 12px; font-weight: 600; padding: 0 12px;
    }
    QPushButton#SecondaryBtn:hover { border: 1px solid #22d3ee; background-color: #1e293b; }
    QPushButton#ToggleBtnActive {
        background-color: #059669; color: #f8fafc;
        border: 2px solid #34d399; border-radius: 12px;
        min-height: 48px; font-size: 14px; font-weight: 800; letter-spacing: 0.04em;
    }
    QPushButton#ToggleBtnActive:hover { background-color: #10b981; }
    QPushButton#ToggleBtnPaused {
        background-color: #7f1d1d; color: #fca5a5;
        border: 2px solid #ef4444; border-radius: 12px;
        min-height: 48px; font-size: 14px; font-weight: 800; letter-spacing: 0.04em;
    }
    QPushButton#ToggleBtnPaused:hover { background-color: #991b1b; }
    QPushButton.BrowserCard {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 12px;
        min-height: 46px; font-size: 12px; font-weight: 700;
        text-align: left; padding: 6px 12px;
    }
    QPushButton.BrowserCard:hover { border: 1px solid #22d3ee; background-color: #1e293b; }
    QFrame#SubControlContainer {
        background-color: #161e2e;
        border: 1px solid #283548;
        border-radius: 8px;
    }
    QPushButton.SegmentBtn {
        background-color: transparent;
        color: #94a3b8;
        font-size: 11px;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        padding: 5px 10px;
        min-height: 22px;
    }
    QPushButton.SegmentBtn:hover {
        background-color: #1e293b;
        color: #f8fafc;
    }
    QPushButton.SegmentBtnActive {
        background-color: #22d3ee;
        color: #060911;
        font-size: 11px;
        font-weight: 800;
        border: none;
        border-radius: 6px;
        padding: 5px 10px;
        min-height: 22px;
    }
    QPushButton.StepperBtn {
        background-color: #1e293b;
        color: #f8fafc;
        border: 1px solid #334155;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
        min-height: 24px;
        padding: 0 4px;
    }
    QPushButton.StepperBtn:hover {
        background-color: #283548;
        border: 1px solid #22d3ee;
    }
    QLabel#StepperVal {
        color: #f8fafc;
        font-family: 'Consolas';
        font-size: 12px;
        font-weight: 800;
        min-width: 44px;
    }
    QComboBox {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 8px;
        padding: 6px 12px; font-size: 12px; font-weight: 600;
    }
    QComboBox:hover { border: 1px solid #22d3ee; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background-color: #0d121e; color: #f8fafc;
        border: 1px solid #1e293b; selection-background-color: #1e293b;
        selection-color: #22d3ee;
    }
    """


# ================= COLOR SWATCH PALETTE COMPONENT =================
class ColorSwatch(QPushButton):
    def __init__(self, name: str, qcolor: QColor, on_select, parent=None):
        super().__init__(parent)
        self.name = name
        self.qcolor = qcolor
        self.on_select = on_select
        self.is_active = False
        self.is_hovered = False

        self.setFixedSize(38, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.clicked.connect(lambda: self.on_select(self.name))

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        cx = rect.center().x()
        cy = rect.center().y()
        r = 13.0

        is_dark = (_CURRENT_THEME == "dark")

        if self.is_active:
            # Soft glowing halo
            halo_pen = QPen(QColor(self.qcolor.red(), self.qcolor.green(), self.qcolor.blue(), 100), 5.0)
            painter.setPen(halo_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - 16, cy - 16, 32, 32)

            # Sharp outer contrast ring
            ring_color = QColor(255, 255, 255, 240) if is_dark else QColor(15, 23, 42, 220)
            ring_pen = QPen(ring_color, 2.2)
            painter.setPen(ring_pen)
            painter.drawEllipse(cx - 16, cy - 16, 32, 32)
        elif self.is_hovered:
            hover_color = QColor(255, 255, 255, 140) if is_dark else QColor(0, 0, 0, 90)
            hover_pen = QPen(hover_color, 1.8)
            painter.setPen(hover_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - 15, cy - 15, 30, 30)
            r = 13.5

        # Inner color fill
        painter.setPen(QPen(QColor(0, 0, 0, 35), 1.0))
        painter.setBrush(QBrush(self.qcolor))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # High-contrast vector checkmark for selected state
        if self.is_active:
            lum = 0.299 * self.qcolor.red() + 0.587 * self.qcolor.green() + 0.114 * self.qcolor.blue()
            check_color = QColor(15, 23, 42) if lum > 165 else QColor(255, 255, 255)

            pen = QPen(check_color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(cx - 4.5, cy - 0.5, cx - 1.5, cy + 3.0)
            painter.drawLine(cx - 1.5, cy + 3.0, cx + 5.0, cy - 3.5)


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
        c_layout.addWidget(ok_btn, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(card)


# ================= BẢNG ĐIỀU KHIỂN CHÍNH (CONTROL CENTER LUÔN MỞ SẴN CHO NGƯỜI DÙNG) =================
class ControlCenterWindow(QWidget):
    def __init__(self, active_key: str, hwid: str):
        super().__init__()
        self.active_key = active_key
        self.hwid = hwid
        self.setObjectName("Root")
        self.setWindowTitle("CHESS STEALTH — Control Center")
        self.setWindowIcon(app_icon())
        self.setFixedSize(500, 615)
        self.setStyleSheet(_build_qss(_CURRENT_THEME))

        self.active_color_name = "Orange (Classic)"
        self.swatches = {}
        self.side_btns = {}

        ensure_overlay_running(active_key, hwid)
        install_scripts_and_extension()

        self._build_ui()

        # Timer liên tục cập nhật nước cờ và trạng thái
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._sync_live_status)
        self.status_timer.start(50)

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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Top Bar
        top = QHBoxLayout()
        top.addWidget(build_brand_header())
        top.addStretch()

        self.theme_btn = QPushButton("Theme")
        self.theme_btn.setObjectName("SecondaryBtn")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top.addWidget(self.theme_btn)
        layout.addLayout(top)

        # 1. NÚT BẬT / TẮT TRỰC TIẾP (TOGGLE BUTTON THAY VÌ PHÍM TẮT)
        self.toggle_btn = QPushButton("STEALTH ASSIST: ACTIVE (ON)")
        self.toggle_btn.setObjectName("ToggleBtnActive")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_assist)
        layout.addWidget(self.toggle_btn)

        # 2. KHUNG HIỂN THỊ NƯỚC ĐI TỨC THÌ (ZERO-DOM LIVE FEEDBACK)
        live_card = QFrame()
        live_card.setObjectName("Card")
        live_layout = QVBoxLayout(live_card)
        live_layout.setContentsMargins(16, 12, 16, 12)
        live_layout.setSpacing(10)

        live_title = QLabel("LIVE MOVE (ZERO-DOM OVERLAY)")
        live_title.setObjectName("SectionTitle")
        live_layout.addWidget(live_title)

        self.move_lbl = QLabel("READY • WAITING FOR CHESS.COM")
        self.move_lbl.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.move_lbl.setStyleSheet("color: #22d3ee;")
        self.move_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        live_layout.addWidget(self.move_lbl)

        # Arrow Color Palette Header
        palette_header = QHBoxLayout()
        palette_lbl = QLabel("Arrow Palette:")
        palette_lbl.setObjectName("SectionTitle")
        palette_header.addWidget(palette_lbl)
        palette_header.addStretch()

        self.color_badge = QLabel()
        palette_header.addWidget(self.color_badge)
        live_layout.addLayout(palette_header)

        # Visual Color Swatches Row
        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        swatches_row.setContentsMargins(0, 0, 0, 0)

        for name, qc in COLOR_PRESETS.items():
            s = ColorSwatch(name, qc, self._on_color_changed)
            self.swatches[name] = s
            swatches_row.addWidget(s)

        swatches_row.addStretch()
        live_layout.addLayout(swatches_row)

        # Settings sub-row: Side & Y-Nudge
        sub_row = QHBoxLayout()
        sub_row.setSpacing(14)

        # Side View Segmented Pill Switcher
        side_col = QVBoxLayout()
        side_col.setSpacing(4)
        s_lbl = QLabel("Side:")
        s_lbl.setObjectName("SectionTitle")
        side_col.addWidget(s_lbl)

        side_box = QFrame()
        side_box.setObjectName("SubControlContainer")
        side_layout = QHBoxLayout(side_box)
        side_layout.setContentsMargins(3, 3, 3, 3)
        side_layout.setSpacing(2)

        side_items = [("Auto", "auto"), ("White", "w"), ("Black", "b")]
        for label, val in side_items:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("class", "SegmentBtn")
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, v=val: self._on_side_changed(v))
            self.side_btns[val] = btn
            side_layout.addWidget(btn)

        side_col.addWidget(side_box)
        sub_row.addLayout(side_col)

        # Y-Nudge Stepper
        y_col = QVBoxLayout()
        y_col.setSpacing(4)
        y_lbl = QLabel("Y-Nudge:")
        y_lbl.setObjectName("SectionTitle")
        y_col.addWidget(y_lbl)

        nudge_box = QFrame()
        nudge_box.setObjectName("SubControlContainer")
        nudge_layout = QHBoxLayout(nudge_box)
        nudge_layout.setContentsMargins(3, 3, 3, 3)
        nudge_layout.setSpacing(2)

        up_btn = QPushButton("▲ -4")
        up_btn.setProperty("class", "StepperBtn")
        up_btn.setFixedSize(38, 28)
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.y_val_lbl = QLabel(f"{arrow_state['offset_y']}px")
        self.y_val_lbl.setObjectName("StepperVal")
        self.y_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        down_btn = QPushButton("▼ +4")
        down_btn.setProperty("class", "StepperBtn")
        down_btn.setFixedSize(38, 28)
        down_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def nudge(delta: int):
            arrow_state["offset_y"] += delta
            self.y_val_lbl.setText(f"{arrow_state['offset_y']}px")

        up_btn.clicked.connect(lambda: nudge(-4))
        down_btn.clicked.connect(lambda: nudge(4))

        nudge_layout.addWidget(up_btn)
        nudge_layout.addWidget(self.y_val_lbl)
        nudge_layout.addWidget(down_btn)

        y_col.addWidget(nudge_box)
        sub_row.addLayout(y_col)

        live_layout.addLayout(sub_row)
        layout.addWidget(live_card)

        # 3. DANH SÁCH CÁC TRÌNH DUYỆT (BẤM VÀO MỞ RA VÀ APP VẪN MỞ NGUYÊN ĐÓ)
        browser_card = QFrame()
        browser_card.setObjectName("Card")
        b_layout = QVBoxLayout(browser_card)
        b_layout.setContentsMargins(14, 12, 14, 12)
        b_layout.setSpacing(8)

        b_title = QLabel("LAUNCH CHESS.COM (WINDOW STAYS OPEN)")
        b_title.setObjectName("SectionTitle")
        b_layout.addWidget(b_title)

        grid = QGridLayout()
        grid.setSpacing(8)

        browsers = [
            ("Google Chrome", "chrome", "chrome"),
            ("Microsoft Edge", "edge", "edge"),
            ("Brave Browser", "brave", "brave"),
            ("Cốc Cốc", "coccoc", "coccoc"),
            ("Opera / GX", "opera", "opera"),
            ("Mozilla Firefox", "firefox", "firefox"),
            ("Min Browser", "min", "min"),
            ("Only Overlay", "other", "pawn"),
        ]

        for idx, (label_text, val, logo_key) in enumerate(browsers):
            btn = QPushButton(f"  {label_text}")
            btn.setProperty("class", "BrowserCard")
            btn.setIcon(QIcon(pixmap_from_data_uri(LOGOS[logo_key], 22)))
            btn.setIconSize(QSize(22, 22))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, v=val, l=label_text: self._launch_browser(v, l))
            grid.addWidget(btn, idx // 2, idx % 2)

        b_layout.addLayout(grid)
        layout.addWidget(browser_card)

        self._on_color_changed(self.active_color_name)
        self._on_side_changed(arrow_state.get("side", "auto"))

    def _toggle_theme(self):
        global _CURRENT_THEME
        _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
        self.setStyleSheet(_build_qss(_CURRENT_THEME))
        self._on_color_changed(self.active_color_name)
        self._on_side_changed(arrow_state.get("side", "auto"))
        for s in self.swatches.values():
            s.update()

    def _toggle_assist(self):
        arrow_state["enabled"] = not arrow_state["enabled"]
        if arrow_state["enabled"]:
            self.toggle_btn.setObjectName("ToggleBtnActive")
            self.toggle_btn.setText("STEALTH ASSIST: ACTIVE (ON)")
        else:
            self.toggle_btn.setObjectName("ToggleBtnPaused")
            self.toggle_btn.setText("STEALTH ASSIST: PAUSED (OFF)")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)

    def _on_color_changed(self, name: str):
        if name not in COLOR_PRESETS:
            return
        self.active_color_name = name
        qc = COLOR_PRESETS[name]
        arrow_state["qcolor"] = qc

        for n, s in self.swatches.items():
            s.is_active = (n == name)
            s.update()

        hex_c = f"#{qc.red():02x}{qc.green():02x}{qc.blue():02x}"
        self.move_lbl.setStyleSheet(f"color: {hex_c};")
        self.color_badge.setText(name.upper())
        self.color_badge.setStyleSheet(f"""
            color: {hex_c};
            background-color: rgba({qc.red()}, {qc.green()}, {qc.blue()}, 0.15);
            border: 1px solid rgba({qc.red()}, {qc.green()}, {qc.blue()}, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
        """)

    def _on_side_changed(self, val: str = None):
        if val is None:
            val = arrow_state.get("side", "auto")
        arrow_state["side"] = val
        for v, btn in self.side_btns.items():
            if v == val:
                btn.setProperty("class", "SegmentBtnActive")
            else:
                btn.setProperty("class", "SegmentBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _launch_browser(self, browser_type: str, label_text: str):
        if browser_type != "other":
            launch_browser_for_chess(browser_type)
        self.move_lbl.setText(f"OPENED {label_text.upper()}")

    def _sync_live_status(self):
        now = time.time()
        if not arrow_state["enabled"]:
            self.move_lbl.setText("ASSIST PAUSED")
            self.move_lbl.setStyleSheet("color: #ef4444;")
            return

        if arrow_state["show"] and (now - arrow_state["last_seen"] <= 2.0) and arrow_state["move"]:
            m = arrow_state["move"].upper()
            d = arrow_state["depth"]
            move_fmt = f"{m[:2]} → {m[2:4]}"
            if d:
                move_fmt += f"  (Depth {d})"
            if arrow_state.get("auto_aligned"):
                move_fmt += " • AUTO-SNAP"
            self.move_lbl.setText(move_fmt)
            self.move_lbl.setStyleSheet("color: #34d399;")
        elif now - arrow_state["last_seen"] > 2.0:
            self.move_lbl.setText("ACTIVE • AUTO-SNAP READY")
            qc = arrow_state.get("qcolor", COLOR_PRESETS["Orange (Classic)"])
            hex_c = f"#{qc.red():02x}{qc.green():02x}{qc.blue():02x}"
            self.move_lbl.setStyleSheet(f"color: {hex_c};")


# ================= 3D SPLIT-PANE ACTIVATION WINDOW =================
class ActivationWindow(QWidget):
    def __init__(self, hwid: str, on_activated_cb=None):
        super().__init__()
        self.hwid = hwid
        self.on_activated_cb = on_activated_cb
        self._activated = False
        self.theme = _CURRENT_THEME

        self.setWindowTitle("Chess Stealth Pro — License Activation")
        self.setFixedSize(840, 520)
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._theme_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._theme_shortcut.activated.connect(self._toggle_theme)

        self.bg_dark_pix = QPixmap(get_asset_path("activation_bg_dark.png"))
        self.bg_light_pix = QPixmap(get_asset_path("activation_bg_light.png"))

        self._build_ui()
        self._apply_theme()

    def closeEvent(self, event):
        event.accept()
        if not self._activated:
            app = QApplication.instance()
            if app:
                app.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        pix = self.bg_dark_pix if self.theme == "dark" else self.bg_light_pix
        if not pix.isNull():
            painter.drawPixmap(0, 0, self.width(), self.height(), pix)
        else:
            painter.fillRect(self.rect(), QColor("#08090d" if self.theme == "dark" else "#f5f5f7"))

    def _build_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(36, 28, 32, 28)
        root_layout.setSpacing(28)

        # ----------------- LEFT PANE -----------------
        left_pane = QVBoxLayout()
        left_pane.setContentsMargins(0, 0, 0, 0)
        left_pane.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)

        self.logo_lbl = QLabel()
        self._update_logo()
        brand_row.addWidget(self.logo_lbl)

        self.brand_title = QLabel("Chess Stealth")
        self.brand_title.setObjectName("BrandTitle")
        brand_row.addWidget(self.brand_title)

        self.brand_badge = QLabel("PRO")
        self.brand_badge.setObjectName("ProBadge")
        brand_row.addWidget(self.brand_badge)
        brand_row.addStretch()
        left_pane.addLayout(brand_row)

        left_pane.addStretch()

        bottom_left_row = QHBoxLayout()
        bottom_left_row.setSpacing(10)
        self.theme_btn = QPushButton("Theme: Dark" if self.theme == "dark" else "Theme: Light")
        self.theme_btn.setObjectName("ThemeSwitchBtn")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        bottom_left_row.addWidget(self.theme_btn)

        self.ver_lbl = QLabel("v2.2 Stealth")
        self.ver_lbl.setObjectName("VerLabel")
        bottom_left_row.addWidget(self.ver_lbl)

        bottom_left_row.addStretch()
        left_pane.addLayout(bottom_left_row)

        root_layout.addLayout(left_pane, 1)

        # ----------------- RIGHT PANE (FROSTED CARD) -----------------
        self.card = QFrame()
        self.card.setObjectName("FrostedCard")
        self.card.setFixedWidth(400)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 24, 28, 26)
        card_layout.setSpacing(14)

        top_link_row = QHBoxLayout()
        top_link_row.addStretch()
        self.get_key_link = QPushButton("Get 24h free key")
        self.get_key_link.setObjectName("TextLink")
        self.get_key_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.get_key_link.clicked.connect(lambda: os.startfile(WEB_GET_KEY_URL))
        top_link_row.addWidget(self.get_key_link)
        card_layout.addLayout(top_link_row)

        self.title_lbl = QLabel("Activate")
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
        self.copy_btn.clicked.connect(self._copy_hwid)
        hwid_row.addWidget(self.copy_btn)
        hwid_sec.addLayout(hwid_row)
        card_layout.addLayout(hwid_sec)

        self.sub_info_lbl = QLabel("Supports 24-hour, 30-day, and lifetime keys")
        self.sub_info_lbl.setObjectName("SubInfoLabel")
        card_layout.addWidget(self.sub_info_lbl)

        buy_row = QHBoxLayout()
        self.buy_link = QPushButton("Buy lifetime key")
        self.buy_link.setObjectName("TextLink")
        self.buy_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.buy_link.clicked.connect(lambda: os.startfile(BUY_LIFE_URL))
        buy_row.addWidget(self.buy_link)
        buy_row.addStretch()
        card_layout.addLayout(buy_row)

        card_layout.addStretch()

        self.act_btn = QPushButton("ACTIVATE")
        self.act_btn.setObjectName("ActivateBarBtn")
        self.act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_btn.clicked.connect(self.handle_activate)
        card_layout.addWidget(self.act_btn)

        root_layout.addWidget(self.card)

    def _update_logo(self):
        icon_name = "queen_dark.png" if self.theme == "dark" else "queen_light.png"
        icon_path = get_asset_path(icon_name)
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_lbl.setPixmap(pix)

    def _copy_hwid(self):
        QApplication.clipboard().setText(self.hwid)
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy"))

    def _toggle_theme(self):
        global _CURRENT_THEME
        self.theme = "light" if self.theme == "dark" else "dark"
        _CURRENT_THEME = self.theme
        self._apply_theme()
        self.update()

    def _apply_theme(self):
        self._update_logo()
        self.theme_btn.setText("Theme: Dark" if self.theme == "dark" else "Theme: Light")
        if self.theme == "dark":
            self.setStyleSheet("""
            QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
            QLabel#BrandTitle { color: #ffffff; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; }
            QLabel#ProBadge {
                background-color: #242734; color: #a1a1a6;
                border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 700;
            }
            QLabel#VerLabel {
                color: #55555c; font-size: 11px; font-weight: 500;
            }
            QPushButton#ThemeSwitchBtn {
                background-color: rgba(255, 255, 255, 0.08); color: #a1a1a6;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 9px;
                padding: 6px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton#ThemeSwitchBtn:hover { background-color: rgba(255, 255, 255, 0.15); color: #ffffff; }
            
            QFrame#FrostedCard {
                background-color: rgba(12, 14, 20, 0.78);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 20px;
            }
            QLabel#ActivateTitle {
                color: #ffffff; font-size: 38px; font-weight: 800; letter-spacing: -0.03em;
            }
            QLabel#FieldLabel {
                color: #a1a1a6; font-size: 12px; font-weight: 600;
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
            QLabel#BrandTitle { color: #1d1d1f; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; }
            QLabel#ProBadge {
                background-color: #e5e5ea; color: #48484a;
                border-radius: 6px; padding: 2px 6px; font-size: 10px; font-weight: 700;
            }
            QLabel#VerLabel {
                color: #a1a1a6; font-size: 11px; font-weight: 500;
            }
            QPushButton#ThemeSwitchBtn {
                background-color: rgba(0, 0, 0, 0.05); color: #1d1d1f;
                border: 1px solid rgba(0, 0, 0, 0.12); border-radius: 9px;
                padding: 6px 14px; font-size: 12px; font-weight: 600;
            }
            QPushButton#ThemeSwitchBtn:hover { background-color: rgba(0, 0, 0, 0.08); color: #000000; }
            
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
