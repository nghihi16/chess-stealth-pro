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
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
        QComboBox {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 8px;
            padding: 6px 10px; font-size: 12px; font-weight: 600;
        }
        """
    return """
    QWidget#Root { background-color: #060911; color: #f8fafc; font-family: 'Segoe UI'; }
    QFrame#Card { background-color: #0d121e; border: 1px solid #1e293b; border-radius: 16px; }
    QLabel#BrandChess { color: #f8fafc; font-size: 16px; font-weight: 800; }
    QLabel#BrandStealth { color: #22d3ee; font-size: 10px; font-weight: 800; }
    QLabel#SectionTitle { color: #94a3b8; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
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
    QComboBox {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 8px;
        padding: 6px 10px; font-size: 12px; font-weight: 600;
    }
    """


# ================= BẢNG ĐIỀU KHIỂN CHÍNH (CONTROL CENTER LUÔN MỞ SẴN CHO NGƯỜI DÙNG) =================
class ControlCenterWindow(QWidget):
    def __init__(self, active_key: str, hwid: str):
        super().__init__()
        self.active_key = active_key
        self.hwid = hwid
        self.setObjectName("Root")
        self.setWindowTitle("CHESS STEALTH — Control Center")
        self.setWindowIcon(app_icon())
        self.setFixedSize(500, 520)
        self.setStyleSheet(_build_qss(_CURRENT_THEME))

        ensure_overlay_running(active_key, hwid)
        install_scripts_and_extension()

        self._build_ui()

        # Timer liên tục cập nhật nước cờ và trạng thái
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._sync_live_status)
        self.status_timer.start(50)

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
        live_layout.setSpacing(6)

        live_title = QLabel("LIVE MOVE (ZERO-DOM OVERLAY)")
        live_title.setObjectName("SectionTitle")
        live_layout.addWidget(live_title)

        self.move_lbl = QLabel("READY • WAITING FOR CHESS.COM")
        self.move_lbl.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.move_lbl.setStyleSheet("color: #22d3ee;")
        self.move_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        live_layout.addWidget(self.move_lbl)

        # Settings sub-row: Color & Side
        sub_row = QHBoxLayout()
        sub_row.setSpacing(12)

        color_col = QVBoxLayout()
        color_col.setSpacing(4)
        c_lbl = QLabel("Arrow Color:")
        c_lbl.setObjectName("SectionTitle")
        color_col.addWidget(c_lbl)

        self.color_combo = QComboBox()
        for name in COLOR_PRESETS:
            self.color_combo.addItem(name)
        self.color_combo.currentTextChanged.connect(self._on_color_changed)
        color_col.addWidget(self.color_combo)
        sub_row.addLayout(color_col)

        side_col = QVBoxLayout()
        side_col.setSpacing(4)
        s_lbl = QLabel("Side:")
        s_lbl.setObjectName("SectionTitle")
        side_col.addWidget(s_lbl)

        self.side_combo = QComboBox()
        self.side_combo.addItem("Auto (Board View)", "auto")
        self.side_combo.addItem("White", "w")
        self.side_combo.addItem("Black", "b")
        self.side_combo.currentIndexChanged.connect(self._on_side_changed)
        side_col.addWidget(self.side_combo)
        sub_row.addLayout(side_col)

        # Nudge Vertical Offset (Hiệu chỉnh cao độ mũi tên)
        y_col = QVBoxLayout()
        y_col.setSpacing(4)
        y_lbl = QLabel("Y-Nudge:")
        y_lbl.setObjectName("SectionTitle")
        y_col.addWidget(y_lbl)

        y_btn_row = QHBoxLayout()
        y_btn_row.setSpacing(4)

        up_btn = QPushButton("▲ -4")
        up_btn.setObjectName("SecondaryBtn")
        up_btn.setFixedWidth(44)
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.y_val_lbl = QLabel(f"{arrow_state['offset_y']}px")
        self.y_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.y_val_lbl.setStyleSheet("font-weight: bold; min-width: 42px; font-family: 'Consolas';")

        down_btn = QPushButton("▼ +4")
        down_btn.setObjectName("SecondaryBtn")
        down_btn.setFixedWidth(44)
        down_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def nudge(delta: int):
            arrow_state["offset_y"] += delta
            self.y_val_lbl.setText(f"{arrow_state['offset_y']}px")

        up_btn.clicked.connect(lambda: nudge(-4))
        down_btn.clicked.connect(lambda: nudge(4))

        y_btn_row.addWidget(up_btn)
        y_btn_row.addWidget(self.y_val_lbl)
        y_btn_row.addWidget(down_btn)
        y_col.addLayout(y_btn_row)
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

    def _toggle_theme(self):
        global _CURRENT_THEME
        _CURRENT_THEME = "light" if _CURRENT_THEME == "dark" else "dark"
        self.setStyleSheet(_build_qss(_CURRENT_THEME))

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
        if name in COLOR_PRESETS:
            arrow_state["qcolor"] = COLOR_PRESETS[name]

    def _on_side_changed(self):
        arrow_state["side"] = self.side_combo.currentData()

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
            self.move_lbl.setStyleSheet("color: #22d3ee;")


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

    # Chưa có key: Mở màn hình kích hoạt
    win = QWidget()
    _ACTIVE_WINDOWS.append(win)
    win.setObjectName("Root")
    win.setWindowTitle("CHESS STEALTH")
    win.setWindowIcon(app_icon())
    win.setFixedSize(440, 300)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
    top.setSpacing(10)
    top.addWidget(build_brand_header())
    top.addStretch()

    copy_hwid_btn = QPushButton("Copy HWID")
    copy_hwid_btn.setObjectName("SecondaryBtn")
    copy_hwid_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def copy_hwid():
        QApplication.clipboard().setText(hwid)
        copy_hwid_btn.setText("Copied")

    copy_hwid_btn.clicked.connect(copy_hwid)
    top.addWidget(copy_hwid_btn)

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

    key_input = QLineEdit()
    key_input.setPlaceholderText("Enter License Key...")
    key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.addWidget(key_input)

    act_btn = QPushButton("ACTIVATE")
    act_btn.setObjectName("PrimaryBtn")
    act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    card_layout.addWidget(act_btn)
    layout.addWidget(card)

    bottom = QHBoxLayout()
    bottom.setSpacing(10)

    get_key_btn = QPushButton("Get 24h Key")
    get_key_btn.setObjectName("SecondaryBtn")
    get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    get_key_btn.clicked.connect(lambda: os.startfile(WEB_GET_KEY_URL))
    bottom.addWidget(get_key_btn)

    buy_btn = QPushButton("Buy VIP Key")
    buy_btn.setObjectName("SecondaryBtn")
    buy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    buy_btn.clicked.connect(lambda: os.startfile(BUY_LIFE_URL))
    bottom.addWidget(buy_btn)
    layout.addLayout(bottom)

    def handle_activate():
        k = key_input.text().strip()
        if not k:
            QMessageBox.warning(win, "Missing Key", "Please enter your License Key.")
            return
        valid, msg = activate_or_verify_key(API_BASE_URL, k, hwid)
        if valid:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(k)
            except Exception:
                pass
            win.close()
            open_control_center(k)
        else:
            QMessageBox.critical(win, "Error", msg)

    act_btn.clicked.connect(handle_activate)
    key_input.returnPressed.connect(handle_activate)

    win.show()
    if url_scheme_key:
        QTimer.singleShot(250, handle_activate)

    app.exec()


if __name__ == "__main__":
    main()
