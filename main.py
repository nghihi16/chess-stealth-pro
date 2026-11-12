import base64
import ctypes
from ctypes import wintypes
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

try:
    from api.server import start_background_api_server
except ImportError:
    start_background_api_server = None
from license_core.hwid import get_hwid
from license_core.url_scheme import parse_url_scheme_arg, register_custom_url_scheme
from license_core.verifier import (
    activate_or_verify_key,
    derive_arrow_scale_factor,
    get_crypto_verification_state,
)
from logo_assets import LOGOS

API_BASE_URL = os.environ.get("CHESSPRO_API_URL", "http://127.0.0.1:8766")
WEB_GET_KEY_URL = os.environ.get(
    "CHESSPRO_GET_KEY_URL", "https://nghihi16.github.io/chess-stealth-pro/"
)
YOUTUBE_URL = os.environ.get("CHESSPRO_YOUTUBE_URL", "")
DISCORD_URL = os.environ.get("CHESSPRO_DISCORD_URL", "")

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
// @namespace    https://chessstealthpro.local
// @version      2.2.0
// @description  Zero-DOM Chess assist engine for all browsers
// @author       Chess Stealth Pro
// @match        *://*.chess.com/*
// @match        *://chess.com/*
// @include      *://*.chess.com/*
// @include      *://chess.com/*
// @run-at       document-end
// @grant        none
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
  let currentEval = '';
  let currentPonder = '';
  let draggedPieceInfo = null;

  // Real-time viewport offset calibration (mouse-independent, supports Min Browser & custom scaling)
  let calibratedOffsetX = null;
  let calibratedOffsetY = null;
  let lastWinX = window.screenX ?? 0;
  let lastWinY = window.screenY ?? 0;
  let calTimer = null;

  function sendCursorCal(e) {
    if (!e || typeof e.clientX !== 'number' || typeof e.clientY !== 'number') return;
    const dpr = window.devicePixelRatio || 1;
    const tokenStr = (typeof SESSION_TOKEN !== 'undefined' && SESSION_TOKEN) ? SESSION_TOKEN : '';
    const q = `cx=${e.clientX}&cy=${e.clientY}&dpr=${dpr}&iw=${window.innerWidth}&ih=${window.innerHeight}&ow=${window.outerWidth}&oh=${window.outerHeight}&wx=${window.screenX ?? 0}&wy=${window.screenY ?? 0}&token=${encodeURIComponent(tokenStr)}&t=${Date.now()}`;
    const authHeaders = tokenStr ? { 'Authorization': 'Bearer ' + tokenStr } : {};
    if (typeof chrome !== 'undefined' && chrome && chrome.runtime && chrome.runtime.sendMessage) {
      try {
        chrome.runtime.sendMessage({ type: 'OVERLAY_CAL', query: q }, () => {
          if (chrome.runtime.lastError) {
            fetch(`http://127.0.0.1:8765/cal?${q}`, { headers: authHeaders }).catch(() => {});
          }
        });
        return;
      } catch (_) {}
    }
    fetch(`http://127.0.0.1:8765/cal?${q}`, { headers: authHeaders }).catch(() => {});
  }

  function updateCalibration(e) {
    if (typeof e.screenX === 'number' && typeof e.clientX === 'number') {
      const dpr = window.devicePixelRatio || 1;
      const offY1 = e.screenY - e.clientY;
      const offY2 = Math.round(e.screenY / dpr - e.clientY);
      const wY = window.screenY ?? 0;

      // Filter: only accept offsets that correspond to a real browser header/tabs height (35..240px)
      if (offY1 >= wY + 35 && offY1 <= wY + 240) {
        calibratedOffsetY = offY1;
        calibratedOffsetX = e.screenX - e.clientX;
      } else if (offY2 >= wY + 35 && offY2 <= wY + 240) {
        calibratedOffsetY = offY2;
        calibratedOffsetX = Math.round(e.screenX / dpr - e.clientX);
      }
      lastWinX = window.screenX ?? 0;
      lastWinY = window.screenY ?? 0;
    }
    if (e && e.type === 'pointerdown') {
      sendCursorCal(e);
    } else if (e) {
      if (calTimer) clearTimeout(calTimer);
      calTimer = setTimeout(() => sendCursorCal(e), 40);
    }
  }

  window.addEventListener('pointermove', updateCalibration, { passive: true, capture: true });
  window.addEventListener('pointerdown', updateCalibration, { passive: true, capture: true });

  function getBoardElement() {
    const primary = document.querySelectorAll('wc-chess-board, chess-board, #board-single');
    for (const el of primary) {
      const r = el.getBoundingClientRect();
      if (r.width >= 120 && r.height >= 120 && Math.abs(r.width - r.height) <= 16) {
        return el;
      }
    }
    const candidates = document.querySelectorAll('.board');
    for (const el of candidates) {
      const r = el.getBoundingClientRect();
      if (r.width >= 120 && r.height >= 120 && Math.abs(r.width - r.height) <= 16) {
        return el;
      }
    }
    return primary[0] || candidates[0] || null;
  }

  function sendToOverlay(payload) {
    if (typeof chrome !== 'undefined' && chrome && chrome.runtime && chrome.runtime.sendMessage) {
      try {
        chrome.runtime.sendMessage({ type: 'OVERLAY_UPDATE', payload: payload }, (res) => {
          if (chrome.runtime.lastError) {
            fallbackSend(payload);
          } else if (res) {
            if (typeof res.enabled === 'boolean') isEnabled = res.enabled;
            if (res.side) manualSide = res.side;
          }
        });
        return;
      } catch (_) {}
    }
    fallbackSend(payload);
  }

  function fallbackSend(payload) {
    const tokenStr = (typeof SESSION_TOKEN !== 'undefined' && SESSION_TOKEN) ? SESSION_TOKEN : '';
    const authHeaders = tokenStr ? { 'Authorization': 'Bearer ' + tokenStr } : {};
    fetch('http://127.0.0.1:8765/update', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders),
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
      const pcParam = payload.piece ? `&pc=${encodeURIComponent(payload.piece)}` : '';
      const tokenParam = tokenStr ? `&token=${encodeURIComponent(tokenStr)}` : '';
      const q = payload.show
        ? `s=1&x1=${payload.x1}&y1=${payload.y1}&x2=${payload.x2}&y2=${payload.y2}&sz=${payload.size}&m=${payload.move || ''}&d=${payload.depth || ''}${bParams}${pcParam}${tokenParam}&t=${Date.now()}`
        : `s=0${tokenParam}&t=${Date.now()}`;
      const img = new Image();
      img.src = `http://127.0.0.1:8765/u?${q}`;
    });
  }

  function updateOverlayCoords(boardEl, move, depth, grid, gridRect, flippedOverride) {
    if (!isEnabled || document.hidden || !boardEl || !move || move.length < 4) {
      sendToOverlay({ show: false });
      return;
    }

    const rect = gridRect || boardEl.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) {
      sendToOverlay({ show: false });
      return;
    }

    const isFlipped = typeof flippedOverride === 'boolean'
      ? flippedOverride
      : (boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped') || boardEl.getAttribute('flipped') === 'true' || boardEl.hasAttribute('flipped'));
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

    let pieceChar = '';
    if (grid && move.length >= 2) {
      const fCol = move.charCodeAt(0) - 97;
      const fRank = parseInt(move[1], 10);
      const fRow = 8 - fRank;
      if (fRow >= 0 && fRow < 8 && fCol >= 0 && fCol < 8) {
        pieceChar = grid[fRow][fCol] || '';
      }
    }

    sendToOverlay({
      show: true,
      board: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        outerWidth: window.outerWidth,
        outerHeight: window.outerHeight,
        screenX: window.screenX ?? window.screenLeft ?? 0,
        screenY: window.screenY ?? window.screenTop ?? 0,
        dpr: window.devicePixelRatio || 1,
        calX: calibratedOffsetX,
        calY: calibratedOffsetY
      },
      flipped: isFlipped,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      size: Math.round(sqSize),
      move: move,
      depth: depth || '',
      eval: currentEval || '',
      ponder: currentPonder || '',
      piece: pieceChar
    });
  }

  function setupEngine() {
    function setupWorkerEvents(worker) {
      worker.onmessage = function (event) {
        if (!isEnabled) return;
        const line = typeof event.data === 'string' ? event.data : '';

        if (line.startsWith('info') && line.includes(' pv ')) {
          const pvMatch = line.match(/ pv ([a-h][1-8][a-h][1-8][qrbn]?)(?:\s+([a-h][1-8][a-h][1-8][qrbn]?))?/);
          const depthMatch = line.match(/depth (\d+)/);
          const cpMatch = line.match(/score cp (-?\d+)/);
          const mateMatch = line.match(/score mate (-?\d+)/);
          if (pvMatch && pvMatch[1]) {
            currentBestMove = pvMatch[1];
            if (pvMatch[2]) currentPonder = pvMatch[2];
            currentDepth = depthMatch ? depthMatch[1] : '';
            if (mateMatch) {
              const m = parseInt(mateMatch[1], 10);
              currentEval = (m > 0 ? '+M' : '-M') + Math.abs(m);
            } else if (cpMatch) {
              const cp = parseInt(cpMatch[1], 10) / 100.0;
              currentEval = (cp >= 0 ? '+' : '') + cp.toFixed(1);
            }
            const curState = extractBoard();
            if (curState) updateOverlayCoords(curState.boardEl, currentBestMove, currentDepth, curState.grid, curState.gridRect, curState.isFlipped);
          }
        }

        if (line.startsWith('bestmove')) {
          const parts = line.split(' ');
          const move = parts[1];
          const ponderIdx = parts.indexOf('ponder');
          if (ponderIdx !== -1 && parts[ponderIdx + 1]) {
            currentPonder = parts[ponderIdx + 1];
          }
          if (move && move !== '(none)' && move.length >= 4) {
            currentBestMove = move;
            const curState = extractBoard();
            if (curState) updateOverlayCoords(curState.boardEl, currentBestMove, currentDepth, curState.grid, curState.gridRect, curState.isFlipped);
          }
        }
      };

      worker.postMessage('uci');
      worker.postMessage('setoption name Skill Level value 20');
      worker.postMessage('isready');
    }

    function bindInlineEngine() {
      if (typeof self !== 'undefined' && typeof self.__sfCommand === 'function') {
        const inlineWorker = {
          postMessage: function (cmd) { self.__sfCommand(cmd); },
          onmessage: null
        };
        self.__sfPrint = function (line) {
          if (inlineWorker.onmessage) inlineWorker.onmessage({ data: line });
        };
        setupWorkerEvents(inlineWorker);
        stockfishWorker = inlineWorker;
        return true;
      }
      return false;
    }

    function initWorker(scriptTextOrUrl, isCode) {
      if (isCode) {
        try {
          (0, eval)(scriptTextOrUrl);
          if (bindInlineEngine()) return;
        } catch (_) {}
      }
      try {
        let blob;
        if (isCode) {
          blob = new Blob([scriptTextOrUrl], { type: 'application/javascript' });
        } else {
          blob = new Blob([`importScripts('${scriptTextOrUrl}');`], { type: 'application/javascript' });
        }
        stockfishWorker = new Worker(URL.createObjectURL(blob));
        setupWorkerEvents(stockfishWorker);
      } catch (err) {
        console.warn('Stockfish worker init error:', err);
      }
    }

    function loadEngine() {
      if (bindInlineEngine()) return;
      if (typeof chrome !== 'undefined' && chrome && chrome.runtime && chrome.runtime.getURL) {
        fetch(chrome.runtime.getURL('stockfish.js'))
          .then(r => r.text())
          .then(code => {
            if (code && code.length > 1000) {
              initWorker(code, true);
            } else {
              fallbackFetch();
            }
          })
          .catch(() => fallbackFetch());
        return;
      }
      fallbackFetch();
    }

    function fallbackFetch() {
      fetch('http://127.0.0.1:8765/stockfish.js')
        .then(r => r.text())
        .then(code => {
          if (code && code.length > 1000) {
            initWorker(code, true);
          } else {
            initWorker('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js', false);
          }
        })
        .catch(() => {
          initWorker('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js', false);
        });
    }

    loadEngine();
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
    const curState = extractBoard();
    if (curState && currentBestMove) updateOverlayCoords(curState.boardEl, currentBestMove, currentDepth, curState.grid, curState.gridRect, curState.isFlipped);
  });

  window.addEventListener('scroll', () => {
    const curState = extractBoard();
    if (curState && currentBestMove) updateOverlayCoords(curState.boardEl, currentBestMove, currentDepth, curState.grid, curState.gridRect, curState.isFlipped);
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
    const boardEl = getBoardElement();
    if (!boardEl) return null;

    const grid = Array(8).fill(null).map(() => Array(8).fill(''));
    const root = boardEl.shadowRoot || boardEl;
    const pieces = root.querySelectorAll('.piece, [class*="piece "]');
    if (pieces.length === 0) return null;

    let whiteKing = false, blackKing = false;
    const stationaryPieces = [];

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
          if (!classes.includes('dragging')) {
            const pRect = p.getBoundingClientRect();
            if (pRect.width > 12 && Math.abs(pRect.width - pRect.height) <= 4) {
              stationaryPieces.push({ file: col, rank: parseInt(sq[1], 10) - 1, rect: pRect });
            }
          }
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

    let isFlipped = boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped') || boardEl.getAttribute('flipped') === 'true' || boardEl.hasAttribute('flipped');
    if (stationaryPieces.length >= 2) {
      const pA = stationaryPieces[0];
      for (let i = 1; i < stationaryPieces.length; i++) {
        const pB = stationaryPieces[i];
        if (pB.rank !== pA.rank && Math.abs(pB.rect.top - pA.rect.top) > 10) {
          isFlipped = (pB.rect.top - pA.rect.top) * (pB.rank - pA.rank) > 0;
          break;
        }
      }
    }

    const bRect = boardEl.getBoundingClientRect();
    let gridRect = { left: bRect.left, top: bRect.top, width: bRect.width, height: bRect.height };
    if (stationaryPieces.length > 0) {
      const sp = stationaryPieces[0];
      const visCol = isFlipped ? (7 - sp.file) : sp.file;
      const visRow = isFlipped ? sp.rank : (7 - sp.rank);
      const derivedLeft = sp.rect.left - visCol * sp.rect.width;
      const derivedTop = sp.rect.top - visRow * sp.rect.height;
      const derivedSize = sp.rect.width * 8;
      if (derivedSize > 120 && Math.abs(derivedSize - bRect.width) <= bRect.width * 0.15) {
        gridRect = { left: derivedLeft, top: derivedTop, width: derivedSize, height: derivedSize };
      }
    }

    const mySide = manualSide !== 'auto' ? manualSide : (isFlipped ? 'b' : 'w');
    const boardPart = fenRows.join('/');

    return {
      boardEl,
      gridRect,
      isFlipped,
      mySide,
      boardPart,
      grid,
      fen: `${boardPart} ${mySide} KQkq - 0 1`
    };
  }

  let lastEmptyPing = 0;
  let lastCoordPush = 0;
  setInterval(() => {
    if (document.hidden) return;
    if (!isEnabled) {
      const now = Date.now();
      if (now - lastEmptyPing > 500) {
        lastEmptyPing = now;
        lastBoardKey = '';
        sendToOverlay({ show: false });
      }
      return;
    }

    const state = extractBoard();
    if (!state) {
      const now = Date.now();
      if (now - lastEmptyPing > 400) {
        lastEmptyPing = now;
        lastBoardKey = '';
        sendToOverlay({ show: false });
      }
      return;
    }

    if (!stockfishWorker) return;

    const now = Date.now();
    if (currentBestMove && (now - lastCoordPush > 100)) {
      lastCoordPush = now;
      updateOverlayCoords(state.boardEl, currentBestMove, currentDepth, state.grid, state.gridRect, state.isFlipped);
    }

    const currentKey = `${state.boardPart}_${state.mySide}`;
    if (currentKey === lastBoardKey) return;

    lastBoardKey = currentKey;
    currentBestMove = null;
    currentDepth = '';
    currentEval = '';
    currentPonder = '';
    stockfishWorker.postMessage('stop');
    stockfishWorker.postMessage('position fen ' + state.fen);
    stockfishWorker.postMessage('go depth 11 movetime 150');
  }, 40);
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
    # Prefer newly generated luxury Queen icon
    for p in [get_asset_path("app_icon.ico"), os.path.join(APP_DIR, "app_icon.ico"), get_asset_path("queen_light.png")]:
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


def create_windows_shortcut(
    target_path: str,
    shortcut_path: str,
    arguments: str = "",
    icon_path: str = "",
    work_dir: str = "",
    desc: str = "",
) -> bool:
    try:
        import uuid
        import tempfile
        vbs_code = [
            'Set oWS = CreateObject("WScript.Shell")',
            f'Set oLink = oWS.CreateShortcut("{shortcut_path}")',
            f'oLink.TargetPath = "{target_path}"',
        ]
        if arguments:
            vbs_args = arguments.replace('"', '""')
            vbs_code.append(f'oLink.Arguments = "{vbs_args}"')
        if icon_path:
            vbs_code.append(f'oLink.IconLocation = "{icon_path}"')
        if work_dir:
            vbs_code.append(f'oLink.WorkingDirectory = "{work_dir}"')
        if desc:
            vbs_code.append(f'oLink.Description = "{desc}"')
        vbs_code.append('oLink.Save')

        tf = os.path.join(tempfile.gettempdir(), f"lnk_{uuid.uuid4().hex}.vbs")
        with open(tf, "w", encoding="utf-8") as f:
            f.write("\r\n".join(vbs_code))
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        subprocess.run(["cscript", "//nologo", tf], check=True, creationflags=creation_flags)
        if os.path.exists(tf):
            os.remove(tf)
        return True
    except Exception:
        return False


def install_scripts_and_extension() -> str:
    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop", "ChessStealthPro")
    os.makedirs(desktop_folder, exist_ok=True)
    sf_src = get_asset_path("stockfish.js")
    sf_code = ""
    if os.path.exists(sf_src):
        try:
            with open(sf_src, "r", encoding="utf-8") as sf_f:
                sf_code = sf_f.read() + "\n"
        except Exception:
            sf_code = ""

    # 1. Min Browser:
    min_userscripts_dir = os.path.join(os.getenv("APPDATA", ""), "Min", "userscripts")
    min_settings_file = os.path.join(os.getenv("APPDATA", ""), "Min", "settings.json")
    try:
        os.makedirs(min_userscripts_dir, exist_ok=True)
        target_js = os.path.join(min_userscripts_dir, "chess-assist.js")
        with open(target_js, "w", encoding="utf-8") as f:
            f.write(sf_code + STEALTH_USERSCRIPT_CODE)

        if os.path.exists(sf_src):
            import shutil
            shutil.copy2(sf_src, os.path.join(min_userscripts_dir, "stockfish.js"))

        if os.path.exists(min_settings_file):
            with open(min_settings_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not cfg.get("userscriptsEnabled"):
                cfg["userscriptsEnabled"] = True
                with open(min_settings_file, "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
    except Exception:
        pass

    # 2. Universal Userscript for Tampermonkey / Violentmonkey on ANY browser
    userscript_paths = [
        os.path.join(APP_DIR, "chess-assist.user.js"),
        os.path.join(desktop_folder, "chess-assist.user.js"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess-assist.user.js"),
    ]
    for up in userscript_paths:
        try:
            with open(up, "w", encoding="utf-8") as f:
                f.write(STEALTH_USERSCRIPT_CODE)
        except Exception:
            pass

    # 3. Chromium Extension (Chrome, Brave, Edge, Cốc Cốc, Opera)
    ext_dir = os.path.join(APP_DIR, "browser-extension")
    desktop_ext_dir = os.path.join(desktop_folder, "browser-extension")
    workspace_ext_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser-extension")
    all_ext_dirs = [ext_dir, desktop_ext_dir, workspace_ext_dir]

    try:
        manifest = {
            "manifest_version": 3,
            "name": "Chess Stealth Zero-DOM",
            "version": "2.5.0",
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
            "web_accessible_resources": [
                {
                    "resources": ["stockfish.js"],
                    "matches": ["*://*.chess.com/*", "*://chess.com/*"]
                }
            ]
        }
        for target_dir in all_ext_dirs:
            os.makedirs(target_dir, exist_ok=True)
            with open(os.path.join(target_dir, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            with open(os.path.join(target_dir, "content.js"), "w", encoding="utf-8") as f:
                f.write(f"const SESSION_TOKEN = '{SESSION_TOKEN}';\n" + sf_code + STEALTH_USERSCRIPT_CODE)
            with open(os.path.join(target_dir, "background.js"), "w", encoding="utf-8") as f:
                f.write(
                    f"const SESSION_TOKEN = '{SESSION_TOKEN}';\n"
                    "let sfReady = false;\n"
                    "let currentBestMove = '';\n"
                    "let currentDepth = '';\n"
                    "let currentEval = '';\n"
                    "let currentPonder = '';\n"
                    "let lastBoardKey = '';\n"
                    "let latestPayload = null;\n"
                    "let serverConfig = { ok: true, enabled: true, side: 'auto', skill: 20, target_depth: 12 };\n"
                    "let lastPushTime = 0;\n\n"
                    "self.__sfPrint = function(line) {\n"
                    "  if (typeof line !== 'string') return;\n"
                    "  if (line.startsWith('info') && line.includes(' pv ')) {\n"
                    "    const pvMatch = line.match(/ pv ([a-h][1-8][a-h][1-8][qrbn]?)(?:\\s+([a-h][1-8][a-h][1-8][qrbn]?))?/);\n"
                    "    const depthMatch = line.match(/depth (\\d+)/);\n"
                    "    const cpMatch = line.match(/score cp (-?\\d+)/);\n"
                    "    const mateMatch = line.match(/score mate (-?\\d+)/);\n"
                    "    if (pvMatch && pvMatch[1]) {\n"
                    "      currentBestMove = pvMatch[1];\n"
                    "      if (pvMatch[2]) currentPonder = pvMatch[2];\n"
                    "      if (depthMatch) currentDepth = depthMatch[1];\n"
                    "      if (mateMatch) {\n"
                    "        const m = parseInt(mateMatch[1], 10);\n"
                    "        currentEval = (m > 0 ? '+M' : '-M') + Math.abs(m);\n"
                    "      } else if (cpMatch) {\n"
                    "        const cp = parseInt(cpMatch[1], 10) / 100.0;\n"
                    "        currentEval = (cp >= 0 ? '+' : '') + cp.toFixed(1);\n"
                    "      }\n"
                    "      pushBestMoveToServer();\n"
                    "    }\n"
                    "  } else if (line.startsWith('bestmove')) {\n"
                    "    const parts = line.split(' ');\n"
                    "    const move = parts[1];\n"
                    "    const ponderIdx = parts.indexOf('ponder');\n"
                    "    if (ponderIdx !== -1 && parts[ponderIdx + 1]) {\n"
                    "      currentPonder = parts[ponderIdx + 1];\n"
                    "    }\n"
                    "    if (move && move !== '(none)' && move.length >= 4) {\n"
                    "      currentBestMove = move;\n"
                    "      pushBestMoveToServer();\n"
                    "    }\n"
                    "  }\n"
                    "};\n\n"
                    "function uci(cmd) {\n"
                    "  try {\n"
                    "    if (typeof onmessage === 'function') {\n"
                    "      onmessage({ data: cmd });\n"
                    "    } else if (typeof Module !== 'undefined' && Module.ccall) {\n"
                    "      Module.ccall('uci_command', 'number', ['string'], [cmd]);\n"
                    "    }\n"
                    "  } catch (e) {}\n"
                    "}\n\n"
                    "try {\n"
                    "  importScripts('stockfish.js');\n"
                    "  uci('uci');\n"
                    "  uci('setoption name Skill Level value 20');\n"
                    "  uci('isready');\n"
                    "  sfReady = true;\n"
                    "} catch (e) {\n"
                    "  console.error('Stockfish service worker init error:', e);\n"
                    "}\n\n"
                    "function pushBestMoveToServer() {\n"
                    "  if (!latestPayload || !currentBestMove || currentBestMove.length < 4) return;\n"
                    "  const b = latestPayload.board;\n"
                    "  if (!b || b.width < 40 || b.height < 40) return;\n"
                    "  const isFlipped = Boolean(latestPayload.flipped);\n"
                    "  const sqSize = b.width / 8;\n"
                    "  const screenOffsetX = latestPayload.screenOffsetX || 0;\n"
                    "  const screenOffsetY = latestPayload.screenOffsetY || 0;\n\n"
                    "  function sqToScreen(sq) {\n"
                    "    const file = sq.charCodeAt(0) - 97;\n"
                    "    const rank = parseInt(sq[1], 10) - 1;\n"
                    "    const col = isFlipped ? (7 - file) : file;\n"
                    "    const row = isFlipped ? rank : (7 - rank);\n"
                    "    return {\n"
                    "      x: Math.round(screenOffsetX + b.left + (col + 0.5) * sqSize),\n"
                    "      y: Math.round(screenOffsetY + b.top + (row + 0.5) * sqSize)\n"
                    "    };\n"
                    "  }\n\n"
                    "  const from = sqToScreen(currentBestMove.substring(0, 2));\n"
                    "  const to = sqToScreen(currentBestMove.substring(2, 4));\n"
                    "  let pieceChar = '';\n"
                    "  const grid = latestPayload.grid;\n"
                    "  if (grid && currentBestMove.length >= 2) {\n"
                    "    const fCol = currentBestMove.charCodeAt(0) - 97;\n"
                    "    const fRank = parseInt(currentBestMove[1], 10);\n"
                    "    const fRow = 8 - fRank;\n"
                    "    if (fRow >= 0 && fRow < 8 && fCol >= 0 && fCol < 8 && grid[fRow]) {\n"
                    "      pieceChar = grid[fRow][fCol] || '';\n"
                    "    }\n"
                    "  }\n\n"
                    "  const updateData = {\n"
                    "    show: true,\n"
                    "    board: b,\n"
                    "    flipped: isFlipped,\n"
                    "    x1: from.x,\n"
                    "    y1: from.y,\n"
                    "    x2: to.x,\n"
                    "    y2: to.y,\n"
                    "    size: Math.round(sqSize),\n"
                    "    move: currentBestMove,\n"
                    "    depth: currentDepth || '',\n"
                    "    eval: currentEval || '',\n"
                    "    ponder: currentPonder || '',\n"
                    "    piece: pieceChar\n"
                    "  };\n\n"
                    "  lastPushTime = Date.now();\n"
                    "  fetch('http://127.0.0.1:8765/update', {\n"
                    "    method: 'POST',\n"
                    "    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + SESSION_TOKEN },\n"
                    "    body: JSON.stringify(updateData)\n"
                    "  })\n"
                    "  .then(r => r.json())\n"
                    "  .then(data => {\n"
                    "    if (data) serverConfig = Object.assign(serverConfig, data);\n"
                    "  })\n"
                    "  .catch(() => {});\n"
                    "}\n\n"
                    "function pingServer() {\n"
                    "  fetch('http://127.0.0.1:8765/ping', {\n"
                    "    headers: { 'Authorization': 'Bearer ' + SESSION_TOKEN }\n"
                    "  })\n"
                    "    .then(r => r.json())\n"
                    "    .then(data => {\n"
                    "      if (data) serverConfig = Object.assign(serverConfig, data);\n"
                    "    })\n"
                    "    .catch(() => {});\n"
                    "}\n"
                    "pingServer();\n"
                    "setInterval(pingServer, 1200);\n\n"
                    "chrome.runtime.onMessage.addListener((m, sender, sendResponse) => {\n"
                    "  if (m && m.type === 'OVERLAY_BOARD' && m.payload) {\n"
                    "    latestPayload = m.payload;\n"
                    "    if (m.payload.boardKey !== lastBoardKey) {\n"
                    "      lastBoardKey = m.payload.boardKey;\n"
                    "      currentBestMove = '';\n"
                    "      currentDepth = '';\n"
                    "      currentEval = '';\n"
                    "      currentPonder = '';\n"
                    "      if (sfReady) {\n"
                    "        const skill = serverConfig.skill ?? 20;\n"
                    "        const depth = Math.min(Math.max(serverConfig.target_depth ?? 11, 5), 13);\n"
                    "        uci('stop');\n"
                    "        uci('setoption name Skill Level value ' + skill);\n"
                    "        uci('position fen ' + m.payload.fen);\n"
                    "        uci('go depth ' + depth);\n"
                    "      }\n"
                    "    } else if (currentBestMove && (Date.now() - lastPushTime > 60)) {\n"
                    "      pushBestMoveToServer();\n"
                    "    }\n"
                    "    sendResponse(serverConfig);\n"
                    "    return false;\n"
                    "  }\n"
                    "  if (m && m.type === 'OVERLAY_UPDATE' && m.payload) {\n"
                    "    if (!m.payload.show) {\n"
                    "      lastBoardKey = '';\n"
                    "      currentBestMove = '';\n"
                    "    }\n"
                    "    fetch('http://127.0.0.1:8765/update', {\n"
                    "      method: 'POST',\n"
                    "      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + SESSION_TOKEN },\n"
                    "      body: JSON.stringify(m.payload)\n"
                    "    })\n"
                    "    .then(r => r.json())\n"
                    "    .then(data => {\n"
                    "      if (data) serverConfig = Object.assign(serverConfig, data);\n"
                    "      sendResponse(serverConfig);\n"
                    "    })\n"
                    "    .catch(() => sendResponse({ ok: false }));\n"
                    "    return true;\n"
                    "  }\n"
                    "  if (m && m.type === 'OVERLAY_CAL' && m.query) {\n"
                    "    fetch('http://127.0.0.1:8765/cal?' + m.query, {\n"
                    "      headers: { 'Authorization': 'Bearer ' + SESSION_TOKEN }\n"
                    "    })\n"
                    "      .then(() => sendResponse({ ok: true }))\n"
                    "      .catch(() => sendResponse({ ok: false }));\n"
                    "    return true;\n"
                    "  }\n"
                    "});\n"
                )
            if os.path.exists(sf_src):
                import shutil
                shutil.copy2(sf_src, os.path.join(target_dir, "stockfish.js"))

        cache_bat = os.path.join(desktop_folder, "Refresh-Icon-Cache.bat")
        with open(cache_bat, "w", encoding="utf-8") as f:
            f.write(
                '@echo off\r\n'
                'echo Refreshing Windows Explorer Icon Cache...\r\n'
                'taskkill /f /im explorer.exe >nul 2>&1\r\n'
                'timeout /t 1 /nobreak >nul\r\n'
                'del /f /q "%LOCALAPPDATA%\\IconCache.db" >nul 2>&1\r\n'
                'del /f /q "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache*" >nul 2>&1\r\n'
                'start explorer.exe\r\n'
                'echo Done! Windows icon cache refreshed.\r\n'
            )

        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        app_icon_path = get_asset_path("app_icon.ico")
        if not os.path.exists(app_icon_path):
            app_icon_path = os.path.join(desktop_folder, "app_icon.ico")

        # Main App Shortcut
        create_windows_shortcut(
            target_path=os.path.join(desktop_folder, "ChessPro.exe"),
            shortcut_path=os.path.join(desktop_dir, "Chess Stealth PRO.lnk"),
            icon_path=f"{app_icon_path},0",
            work_dir=desktop_folder,
            desc="Chess Stealth PRO - Universal AI Engine Assist",
        )
        create_windows_shortcut(
            target_path=os.path.join(desktop_folder, "ChessPro.exe"),
            shortcut_path=os.path.join(desktop_folder, "Chess Stealth PRO.lnk"),
            icon_path=f"{app_icon_path},0",
            work_dir=desktop_folder,
            desc="Chess Stealth PRO - Universal AI Engine Assist",
        )

        # Clean up any legacy extra "(Stealth).lnk" shortcuts
        for clean_dir in (desktop_dir, desktop_folder):
            if os.path.isdir(clean_dir):
                for fn in os.listdir(clean_dir):
                    if fn.lower().endswith("(stealth).lnk"):
                        try:
                            os.remove(os.path.join(clean_dir, fn))
                        except Exception:
                            pass

        # Automatically hook user's existing normal browser shortcuts (Desktop, Taskbar, Start Menu)
        # so opening their normal browser automatically loads the Stealth extension on their default profile
        hook_user_browser_shortcuts(ext_dir)
    except Exception:
        pass
    return ext_dir


def hook_user_browser_shortcuts(ext_dir: str):
    """
    Silently hooks the user's existing browser shortcuts (.lnk on Desktop, Taskbar, Start Menu)
    and HKCU StartMenuInternet commands so when the user opens Brave, Chrome, Edge, Opera, or Cốc Cốc
    normally, the Stealth extension is already loaded on their default profile with zero buttons needed.
    """
    if sys.platform != "win32" or "PYTEST_CURRENT_TEST" in os.environ:
        return
    try:
        import tempfile
        import uuid

        appdata = os.getenv("APPDATA", "")
        progdata = os.getenv("PROGRAMDATA", r"C:\ProgramData")
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            r"C:\Users\Public\Desktop",
            os.path.join(appdata, "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"),
            os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(progdata, "Microsoft", "Windows", "Start Menu", "Programs"),
        ]
        lnk_files = []
        for d in search_dirs:
            if os.path.isdir(d):
                for root_d, _, files in os.walk(d):
                    for fn in files:
                        if fn.lower().endswith(".lnk") and "chess stealth" not in fn.lower():
                            lnk_files.append(os.path.join(root_d, fn))

        target_exes = ("brave.exe", "chrome.exe", "msedge.exe", "opera.exe", "browser.exe", "coccoc.exe", "vivaldi.exe")
        ext_arg = f'--load-extension="{ext_dir}" --disable-features=DisableLoadExtensionCommandLineSwitch'

        vbs_lines = ['On Error Resume Next', 'Set oWS = CreateObject("WScript.Shell")']
        for lp in lnk_files:
            safe_lp = lp.replace('"', '""')
            vbs_lines.extend([
                f'Set oLink = oWS.CreateShortcut("{safe_lp}")',
                'tPath = LCase(oLink.TargetPath)',
                'isBrowser = False',
            ])
            for tex in target_exes:
                vbs_lines.append(f'If Right(tPath, {len(tex)}) = "{tex}" Then isBrowser = True')
            vbs_lines.extend([
                'If isBrowser Then',
                '  curArgs = oLink.Arguments',
                '  If InStr(1, curArgs, "--load-extension=", 1) = 0 Then',
                f'    If Len(Trim(curArgs)) > 0 Then oLink.Arguments = curArgs & " {ext_arg.replace(chr(34), chr(34)*2)}" Else oLink.Arguments = "{ext_arg.replace(chr(34), chr(34)*2)}"',
                '    oLink.Save',
                '  End If',
                'End If',
            ])

        tf = os.path.join(tempfile.gettempdir(), f"hook_lnk_{uuid.uuid4().hex}.vbs")
        with open(tf, "w", encoding="utf-8") as f:
            f.write("\r\n".join(vbs_lines))
        subprocess.run(["cscript", "//nologo", tf], check=False, creationflags=0x08000000, timeout=5)
        if os.path.exists(tf):
            os.remove(tf)
    except Exception:
        pass

    # Also hook HKCU\Software\Clients\StartMenuInternet open commands for current user
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Clients\StartMenuInternet") as smi:
            idx = 0
            subkeys = []
            while True:
                try:
                    subkeys.append(winreg.EnumKey(smi, idx))
                    idx += 1
                except OSError:
                    break
            for sk in subkeys:
                cmd_key_path = f"Software\\Clients\\StartMenuInternet\\{sk}\\shell\\open\\command"
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmd_key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as ck:
                        val, vtype = winreg.QueryValueEx(ck, "")
                        val_l = str(val).lower()
                        if any(x in val_l for x in ("brave.exe", "chrome.exe", "msedge.exe", "opera.exe", "browser.exe")):
                            if "--load-extension=" not in val_l:
                                new_val = f'{val} --load-extension="{ext_dir}" --disable-features=DisableLoadExtensionCommandLineSwitch'
                                winreg.SetValueEx(ck, "", 0, vtype, new_val)
                except Exception:
                    pass
    except Exception:
        pass


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
        os.path.join(os.getenv("LOCALAPPDATA", ""), "CocCoc", "Browser", "Application", "coccoc.exe"),
        r"C:\Program Files\CocCoc\Browser\Application\coccoc.exe",
        r"C:\Program Files (x86)\CocCoc\Browser\Application\coccoc.exe",
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


KNOWN_BROWSERS = {
    "chrome.exe": ("Google Chrome", "chrome"),
    "msedge.exe": ("Microsoft Edge", "edge"),
    "brave.exe": ("Brave", "brave"),
    "opera.exe": ("Opera", "opera"),
    "opera_gx.exe": ("Opera GX", "opera"),
    "browser.exe": ("Cốc Cốc", "coccoc"),
    "coccoc.exe": ("Cốc Cốc", "coccoc"),
    "firefox.exe": ("Mozilla Firefox", "firefox"),
    "min.exe": ("Min Browser", "min"),
    "vivaldi.exe": ("Vivaldi", "vivaldi"),
    "arc.exe": ("Arc", "arc"),
}


def get_browser_from_hwnd(hwnd: int) -> tuple[str, str]:
    if not hwnd:
        return ("", "")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.IsWindow(hwnd):
        return ("", "")
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return ("", "")
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h_proc:
        return ("", "")
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            exe_name = os.path.basename(buf.value).lower()
            if exe_name in KNOWN_BROWSERS:
                return KNOWN_BROWSERS[exe_name]
    finally:
        kernel32.CloseHandle(h_proc)
    return ("", "")


def get_windows_default_browser() -> str:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0].lower()
            if "chrome" in prog_id:
                return "chrome"
            if "edge" in prog_id or "msedge" in prog_id:
                return "edge"
            if "brave" in prog_id:
                return "brave"
            if "opera" in prog_id:
                return "opera"
            if "firefox" in prog_id:
                return "firefox"
            if "coccoc" in prog_id:
                return "coccoc"
            if "min" in prog_id:
                return "min"
    except Exception:
        pass
    return "chrome"


def detect_active_chess_browser() -> dict | None:
    """
    Detects which browser window is actively viewing Chess.com or Lichess.
    Returns: {"name": "Google Chrome", "key": "chrome", "hwnd": hwnd, "title": title}
    """
    user32 = ctypes.windll.user32
    my_pid = os.getpid()

    def check_window(h):
        l = user32.GetWindowTextLengthW(h)
        if l <= 0:
            return None
        b = ctypes.create_unicode_buffer(l + 1)
        user32.GetWindowTextW(h, b, l + 1)
        title = b.value
        title_lower = title.lower()
        if any(ign in title_lower for ign in ("chess stealth", "setup", "installer", "cài đặt")):
            return None
        if not ("chess" in title_lower or "lichess" in title_lower):
            return None
        disp_name, key_name = get_browser_from_hwnd(h)
        if not disp_name or not key_name:
            return None
        return {"name": disp_name, "key": key_name, "hwnd": h, "title": title}

    fg = user32.GetForegroundWindow()
    if fg:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if pid.value != my_pid:
            info = check_window(fg)
            if info:
                return info

    detected = []
    def enum_cb(h, _):
        if h != fg and user32.IsWindowVisible(h) and not user32.IsIconic(h):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value != my_pid:
                info = check_window(h)
                if info:
                    detected.append(info)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if detected:
        return detected[0]
    return None


def find_browser_exe(browser_type: str) -> str | None:
    for p in BROWSER_PATHS.get(browser_type, []):
        if p and os.path.exists(p):
            return p
    return None


def get_available_browsers() -> list[tuple[str, str, str]]:
    """Returns list of (key, display_name, exe_path) for installed browsers on this machine."""
    order = [
        ("chrome", "Chrome"),
        ("brave", "Brave"),
        ("edge", "Edge"),
        ("coccoc", "Cốc Cốc"),
        ("opera", "Opera"),
        ("firefox", "Firefox"),
    ]
    avail = []
    for key, name in order:
        exe = find_browser_exe(key)
        if exe:
            avail.append((key, name, exe))
    return avail


def launch_browser_for_chess(browser_type: str = "auto"):
    ext_dir = install_scripts_and_extension()
    chess_url = "https://www.chess.com/play/computer"
    
    if browser_type == "auto":
        # 1. Prefer currently detected chess browser on screen
        active_b = detect_active_chess_browser()
        if active_b and active_b.get("key") in BROWSER_PATHS:
            browser_type = active_b["key"]
        else:
            # 2. Check Windows default browser
            default_b = get_windows_default_browser()
            if find_browser_exe(default_b):
                browser_type = default_b
            else:
                for b in ("chrome", "edge", "brave", "coccoc", "opera", "firefox", "min"):
                    if find_browser_exe(b):
                        browser_type = b
                        break
        if browser_type == "auto":
            browser_type = "chrome"

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


_AUTO_HOOK_HIST: dict[str, float] = {}
_CALIBRATED_VP: dict = {"left_qt": None, "top_qt": None, "sig": None, "ts": 0.0}


def auto_hook_running_browser(detected_info: dict) -> bool:
    """
    If the user opened a Chromium browser (Brave, Chrome, Edge, Opera, Cốc Cốc) on Chess.com
    before its shortcut was hooked, seamlessly reloads the browser session in-place with
    --restore-last-session --load-extension="<ext_dir>" on the user's normal default profile.
    Never restarts a browser that already has --load-extension or has already connected.
    """
    if sys.platform != "win32" or "PYTEST_CURRENT_TEST" in os.environ:
        return False
    if not detected_info:
        return False
    if arrow_state.get("last_ping", 0.0) > 0.0:
        return False
    b_key = detected_info.get("key", "")
    hwnd = detected_info.get("hwnd", 0)
    if b_key not in ("chrome", "edge", "brave", "coccoc", "opera", "vivaldi"):
        return False
    if b_key in _AUTO_HOOK_HIST:
        return False

    exe_path = None
    if hwnd:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
            if h_proc:
                try:
                    buf = ctypes.create_unicode_buffer(512)
                    size = wintypes.DWORD(512)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        exe_path = buf.value
                finally:
                    kernel32.CloseHandle(h_proc)

    if not exe_path or not os.path.exists(exe_path):
        exe_path = find_browser_exe(b_key)
    if not exe_path or not os.path.exists(exe_path):
        return False

    _AUTO_HOOK_HIST[b_key] = time.time()
    ext_dir = os.path.join(APP_DIR, "browser-extension")
    if not os.path.exists(os.path.join(ext_dir, "manifest.json")):
        ext_dir = install_scripts_and_extension()

    def _reload_worker():
        try:
            exe_name = os.path.basename(exe_path)
            if arrow_state.get("last_ping", 0.0) > 0.0:
                return

            user32 = ctypes.windll.user32
            if hwnd and user32.IsWindow(hwnd):
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE for clean session save
            time.sleep(0.4)
            subprocess.run(
                ["taskkill", "/F", "/IM", exe_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                timeout=4,
            )
            time.sleep(0.3)
            subprocess.Popen(
                [
                    exe_path,
                    "--restore-last-session",
                    f"--load-extension={ext_dir}",
                    "--disable-features=DisableLoadExtensionCommandLineSwitch",
                ],
                creationflags=0x08000000,
            )
        except Exception:
            pass

    threading.Thread(target=_reload_worker, daemon=True).start()
    return True


def _get_overlay_dpr(hwnd: int = 0) -> float:
    try:
        if _OVERLAY_INSTANCE is not None:
            dpr = float(_OVERLAY_INSTANCE.devicePixelRatioF())
            if dpr >= 0.5:
                return dpr
    except Exception:
        pass
    if hwnd:
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd) or 96
            return max(1.0, float(dpi) / 96.0)
        except Exception:
            pass
    return 1.0


def _get_visible_window_rect_qt(hwnd: int) -> tuple[float, float, float, float, bool]:
    """
    Returns (vis_left_qt, vis_top_qt, vis_right_qt, vis_bottom_qt, is_maximized)
    in exact QtStealthOverlay logical coordinates.
    """
    user32 = ctypes.windll.user32
    overlay_dpr = _get_overlay_dpr(hwnd)
    is_maximized = bool(user32.IsZoomed(hwnd))

    if is_maximized:
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        crect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(crect))
        if crect.right > 200 and crect.bottom > 200:
            return (
                pt.x / overlay_dpr,
                pt.y / overlay_dpr,
                (pt.x + crect.right) / overlay_dpr,
                (pt.y + crect.bottom) / overlay_dpr,
                True,
            )

    dwm_rect = wintypes.RECT()
    try:
        res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd,
            9,  # DWMWA_EXTENDED_FRAME_BOUNDS
            ctypes.byref(dwm_rect),
            ctypes.sizeof(dwm_rect),
        )
        if res == 0 and (dwm_rect.right - dwm_rect.left) > 200:
            return (
                dwm_rect.left / overlay_dpr,
                dwm_rect.top / overlay_dpr,
                dwm_rect.right / overlay_dpr,
                dwm_rect.bottom / overlay_dpr,
                is_maximized,
            )
    except Exception:
        pass

    wrect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wrect))
    return (
        wrect.left / overlay_dpr,
        wrect.top / overlay_dpr,
        wrect.right / overlay_dpr,
        wrect.bottom / overlay_dpr,
        is_maximized,
    )


def find_browser_viewport(board_dict: dict | None = None) -> tuple[float, float, float, float, int] | None:
    """
    Automatically detects 100% accurate browser Viewport coordinates (Chrome, Edge, Brave, Opera, Firefox...)
    in QtStealthOverlay logical coordinates (dpi=96 so dpi_scale=1.0).
    """
    user32 = ctypes.windll.user32
    my_pid = os.getpid()

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

    def _win_title(h):
        l = user32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(l + 1)
        user32.GetWindowTextW(h, b, l + 1)
        return b.value.lower()

    chess_windows = [h for h in windows_to_check if "chess" in _win_title(h) and "chess stealth" not in _win_title(h)]
    other_windows = [h for h in windows_to_check if h not in chess_windows]
    ordered_windows = chess_windows + other_windows

    for hwnd in ordered_windows:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            continue

        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        if "chess stealth" in title:
            continue

        cname = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cname, 256)
        cls = cname.value.lower()

        is_chromium = ("chrome_widgetwin_1" in cls)
        is_firefox = ("mozillawindowclass" in cls)
        has_chess_in_title = ("chess" in title)

        if not (is_chromium or is_firefox or has_chess_in_title):
            continue

        vis_l, vis_t, vis_r, vis_b, is_max = _get_visible_window_rect_qt(hwnd)
        vis_w = vis_r - vis_l
        vis_h = vis_b - vis_t
        if vis_w < 250 or vis_h < 250:
            continue

        b_name, _ = get_browser_from_hwnd(hwnd)
        arrow_state["detected_browser"] = b_name

        overlay_dpr = _get_overlay_dpr(hwnd)
        js_dpr = float(board_dict.get("dpr", 0.0)) if board_dict else 0.0
        zoom_scale = (js_dpr / overlay_dpr) if (js_dpr > 0.2 and abs(js_dpr - overlay_dpr) > 0.04) else 1.0

        inner_w = float(board_dict.get("innerWidth", 0.0)) if board_dict else 0.0
        inner_h = float(board_dict.get("innerHeight", 0.0)) if board_dict else 0.0

        # 1. Check hardware cursor calibration lock for this exact window & viewport geometry
        cal_sig = (hwnd, round(vis_l), round(vis_t), round(vis_w), round(vis_h), round(inner_w), round(inner_h))
        if (
            _CALIBRATED_VP.get("sig") == cal_sig
            and _CALIBRATED_VP.get("left_qt") is not None
            and _CALIBRATED_VP.get("top_qt") is not None
        ):
            return (
                float(_CALIBRATED_VP["left_qt"]),
                float(_CALIBRATED_VP["top_qt"]),
                inner_w * zoom_scale if inner_w > 0 else vis_w,
                inner_h * zoom_scale if inner_h > 0 else vis_h,
                96,
            )

        # 2. Exact Visible Bottom minus innerHeight * zoom_scale (works immediately with zero mouse movement!)
        if inner_w > 200 and inner_h > 200:
            vp_w_qt = inner_w * zoom_scale
            vp_h_qt = inner_h * zoom_scale
            diff_w = max(0.0, vis_w - vp_w_qt)
            if is_max and diff_w <= 4.0:
                border_x = 0.0
                border_bottom = 0.0
            elif diff_w <= 24.0:
                border_x = diff_w / 2.0
                border_bottom = 0.0 if is_max else min(8.0, border_x)
            else:
                # Left sidebar open (e.g., Brave vertical tabs / Opera sidebar)
                border_x = diff_w
                border_bottom = 0.0 if is_max else 1.0

            vp_left_qt = vis_l + border_x
            vp_top_qt = max(vis_t + 36.0, vis_b - border_bottom - vp_h_qt)
            return (vp_left_qt, vp_top_qt, vp_w_qt, vp_h_qt, 96)

        # 3. Check native RenderWidgetHostHWND if present and below browser toolbar
        vp = []

        def child_cb(chwnd, _):
            cc = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(chwnd, cc, 256)
            c_name = cc.value
            if c_name in ["Chrome_RenderWidgetHostHWND", "MozillaContentWindowClass"]:
                cr = wintypes.RECT()
                user32.GetWindowRect(chwnd, ctypes.byref(cr))
                w, h = (cr.right - cr.left) / overlay_dpr, (cr.bottom - cr.top) / overlay_dpr
                c_left, c_top = cr.left / overlay_dpr, cr.top / overlay_dpr
                if w > 250 and h > 250 and c_top >= vis_t + 36.0:
                    vp.append((c_left, c_top, w, h, 96))
            return True

        user32.EnumChildWindows(
            hwnd,
            ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(child_cb),
            0,
        )
        if vp:
            vp.sort(key=lambda item: item[2] * item[3], reverse=True)
            return vp[0]

        # 4. Fallback when called without board_dict
        return (vis_l, vis_t + 82.0, vis_w, max(200.0, vis_h - 82.0), 96)

    return None


def compute_auto_aligned_arrow(
    board_dict: dict, move_str: str, flipped_flag: bool
) -> tuple[int, int, int, int, int] | None:
    if not board_dict or not move_str or len(move_str) < 4:
        return None
    try:
        vp = find_browser_viewport(board_dict)
        if not vp:
            return None

        vp_left, vp_top, vp_w, vp_h, dpi = vp
        dpi_scale = max(1.0, dpi / 96.0)

        vp_left_logical = vp_left / dpi_scale
        vp_top_logical = vp_top / dpi_scale

        overlay_dpr = _get_overlay_dpr()
        js_dpr = float(board_dict.get("dpr", 0.0))
        zoom_scale = (js_dpr / overlay_dpr) if (js_dpr > 0.2 and abs(js_dpr - overlay_dpr) > 0.04) else 1.0

        board_left = vp_left_logical + float(board_dict.get("left", 0)) * zoom_scale
        board_top = vp_top_logical + float(board_dict.get("top", 0)) * zoom_scale
        board_w = float(board_dict.get("width", 480)) * zoom_scale
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


def _load_or_create_persistent_session_token() -> str:
    token_file = os.path.join(APP_DIR, "session.token")
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        if os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if len(saved) >= 32:
                    return saved
        new_token = secrets.token_hex(24)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(new_token)
        return new_token
    except Exception:
        return secrets.token_hex(24)


SESSION_TOKEN = _load_or_create_persistent_session_token()


def generate_session_token() -> str:
    global SESSION_TOKEN
    SESSION_TOKEN = _load_or_create_persistent_session_token()
    return SESSION_TOKEN


class StealthOverlayServer(BaseHTTPRequestHandler):
    SESSION_TOKEN: str = SESSION_TOKEN
    ALLOWED_ORIGINS = {
        "https://www.chess.com",
        "https://lichess.org",
        "http://localhost",
        "http://127.0.0.1",
    }

    def _send_cors(self, status=200):
        self.send_response(status)
        origin = self.headers.get("Origin", "")
        if origin:
            if origin in self.ALLOWED_ORIGINS or origin.startswith("chrome-extension://") or origin.startswith("moz-extension://"):
                self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors(200)

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        expected = getattr(self, "SESSION_TOKEN", SESSION_TOKEN)
        if not expected:
            return False
        if auth.startswith("Bearer "):
            bearer_token = auth[7:].strip()
            if bearer_token and hmac.compare_digest(bearer_token, expected):
                return True
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        token_in_query = params.get("token", [""])[0]
        if token_in_query and hmac.compare_digest(token_in_query, expected):
            return True
        return False

    def do_GET(self):
        global arrow_state, _CALIBRATED_VP
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/stockfish.js":
            sf_file = get_asset_path("stockfish.js")
            if os.path.exists(sf_file):
                with open(sf_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                origin = self.headers.get("Origin", "")
                if origin and (origin in self.ALLOWED_ORIGINS or origin.startswith("chrome-extension://") or origin.startswith("moz-extension://")):
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(content)
                return

        if parsed.path in ("/chess-assist.user.js", "/script.js"):
            token_val = getattr(self, "SESSION_TOKEN", SESSION_TOKEN)
            content = f"// Chess Stealth Pro Userscript\nconst SESSION_TOKEN = '{token_val}';\n{STEALTH_USERSCRIPT_CODE}".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            origin = self.headers.get("Origin", "")
            if origin and (origin in self.ALLOWED_ORIGINS or origin.startswith("chrome-extension://") or origin.startswith("moz-extension://")):
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
            return

        if parsed.path == "/ping":
            if not self._check_auth():
                self._send_cors(401)
                self.wfile.write(b'{"error": "Unauthorized: Invalid or missing bearer token"}')
                return
            self._send_cors(200)
            self.wfile.write(json.dumps({"ok": True, "ping": "pong", "time": time.time()}).encode())
            return

        if parsed.path == "/cal":
            if not self._check_auth():
                self._send_cors(401)
                self.wfile.write(b'{"error": "Unauthorized: Invalid or missing bearer token"}')
                return
            try:
                params = urllib.parse.parse_qs(parsed.query)
                cx = float(params.get("cx", [0])[0])
                cy = float(params.get("cy", [0])[0])
                js_dpr = float(params.get("dpr", [0])[0])
                iw = float(params.get("iw", [0])[0])
                ih = float(params.get("ih", [0])[0])
                qpt = QCursor.pos()
                det = detect_active_chess_browser()
                hwnd = det["hwnd"] if det else ctypes.windll.user32.GetForegroundWindow()
                if hwnd and cx > 0 and cy > 0:
                    vis_l, vis_t, vis_r, vis_b, _ = _get_visible_window_rect_qt(hwnd)
                    vis_w, vis_h = vis_r - vis_l, vis_b - vis_t
                    overlay_dpr = _get_overlay_dpr(hwnd)
                    zoom_scale = (js_dpr / overlay_dpr) if (js_dpr > 0.2 and abs(js_dpr - overlay_dpr) > 0.04) else 1.0
                    vp_l = float(qpt.x()) - cx * zoom_scale
                    vp_t = float(qpt.y()) - cy * zoom_scale
                    if (vis_t + 25.0) <= vp_t <= (vis_t + 260.0) and (vis_l - 20.0) <= vp_l <= (vis_r - 100.0):
                        _CALIBRATED_VP = {
                            "left_qt": vp_l,
                            "top_qt": vp_t,
                            "sig": (hwnd, round(vis_l), round(vis_t), round(vis_w), round(vis_h), round(iw), round(ih)),
                            "ts": time.time(),
                        }
            except Exception:
                pass
            self._send_cors(200)
            self.wfile.write(b'{"ok":true}')
            return

        params = urllib.parse.parse_qs(parsed.query)
        arrow_state["last_ping"] = time.time()
        if not self._check_auth():
            self._send_cors(401)
            self.wfile.write(b'{"error": "Unauthorized: Invalid or missing bearer token"}')
            return

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
                    if "pc" in params and params["pc"]:
                        arrow_state["piece"] = params["pc"][0]
                except Exception:
                    pass
        self._send_cors(200)
        resp = json.dumps(
            {
                "ok": True,
                "enabled": arrow_state["enabled"],
                "side": arrow_state["side"],
                "skill": arrow_state.get("skill", 20),
                "target_depth": arrow_state.get("target_depth", 12),
            }
        ).encode()
        self.wfile.write(resp)

    def do_POST(self):
        global arrow_state
        length = int(self.headers.get("Content-Length", 0))
        if not self._check_auth():
            if length > 0:
                try:
                    self.rfile.read(length)
                except Exception:
                    pass
            err_body = b'{"error": "Unauthorized: Invalid or missing bearer token"}'
            self.send_response(401)
            origin = self.headers.get("Origin", "")
            if origin and (origin in self.ALLOWED_ORIGINS or origin.startswith("chrome-extension://")):
                self.send_header("Access-Control-Allow-Origin", origin)
            else:
                self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            try:
                body = self.rfile.read(length).decode("utf-8")
                data = json.loads(body)
                arrow_state["show"] = bool(data.get("show", False))
                arrow_state["last_seen"] = time.time()
                arrow_state["last_ping"] = time.time()
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
                    if "eval" in data and data["eval"]:
                        arrow_state["eval"] = str(data["eval"])
                    if "ponder" in data and data["ponder"]:
                        arrow_state["ponder"] = str(data["ponder"])
                    if "piece" in data and data["piece"]:
                        arrow_state["piece"] = str(data["piece"])
            except Exception:
                pass
        self._send_cors()
        resp = json.dumps(
            {
                "ok": True,
                "enabled": arrow_state["enabled"],
                "side": arrow_state["side"],
                "skill": arrow_state.get("skill", 20),
                "target_depth": arrow_state.get("target_depth", 12),
            }
        ).encode()
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
        crypto_state = get_crypto_verification_state()
        effective_scale = gate_scale * crypto_state

        if (
            not arrow_state["enabled"]
            or effective_scale <= 0.0
            or not arrow_state["show"]
            or (now - arrow_state["last_seen"] > 1.8)
        ):
            return

        x1 = float(arrow_state["x1"])
        y1 = float(arrow_state["y1"] + arrow_state["offset_y"])
        x2 = float(arrow_state["x2"])
        y2 = float(arrow_state["y2"] + arrow_state["offset_y"])

        # Cryptographic coordinate gating: mathematical intertwining with scale & crypto state
        dx = (x2 - x1) * effective_scale
        dy = (y2 - y1) * effective_scale
        x2_eff = x1 + dx
        y2_eff = y1 + dy
        sq = max(32.0, float(arrow_state["size"])) * effective_scale

        dist = math.hypot(dx, dy)
        if dist <= 6:
            return

        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux

        shaft_w = sq * 0.22 * effective_scale
        head_w = sq * 0.50 * effective_scale
        head_l = sq * 0.38 * effective_scale
        offset = sq * 0.12 * effective_scale

        sx, sy = x1 + ux * offset, y1 + uy * offset
        nx, ny = x2_eff - ux * head_l, y2_eff - uy * head_l

        poly = QPolygonF(
            [
                QPointF(sx + px * (shaft_w / 2), sy + py * (shaft_w / 2)),
                QPointF(nx + px * (shaft_w / 2), ny + py * (shaft_w / 2)),
                QPointF(nx + px * (head_w / 2), ny + py * (head_w / 2)),
                QPointF(x2_eff, y2_eff),
                QPointF(nx - px * (head_w / 2), ny - py * (head_w / 2)),
                QPointF(nx - px * (shaft_w / 2), ny - py * (shaft_w / 2)),
                QPointF(sx - px * (shaft_w / 2), sy - py * (shaft_w / 2)),
            ]
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = arrow_state.get("qcolor", QColor(245, 158, 11, 230))
        border_pen = QPen(QColor(0, 0, 0, 120), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(border_pen)
        painter.setBrush(color)
        painter.drawPolygon(poly)


def ensure_overlay_running(active_key: str, hwid: str):
    global _OVERLAY_INSTANCE
    if _OVERLAY_INSTANCE is not None:
        return

    try:
        from license_core.watchdog import start_watchdog
        start_watchdog(poll_interval=1.0)
    except Exception:
        pass

    def run_http():
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", 8765), StealthOverlayServer)
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
    queen_ic = get_asset_path("queen_light.png")
    if os.path.exists(queen_ic):
        logo_lbl.setPixmap(QPixmap(queen_ic).scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    else:
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
  <path d='M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4'/>
  <polyline points='16 17 21 12 16 7'/>
  <line x1='21' y1='12' x2='9' y2='12'/>
</svg>"""

PALETTE_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
  <circle cx='13.5' cy='6.5' r='.5' fill='currentColor'/>
  <circle cx='17.5' cy='10.5' r='.5' fill='currentColor'/>
  <circle cx='8.5' cy='7.5' r='.5' fill='currentColor'/>
  <circle cx='6.5' cy='12.5' r='.5' fill='currentColor'/>
  <path d='M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z'/>
</svg>"""

CHEVRON_DOWN_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>
  <path d='m6 9 6 6 6-6'/>
</svg>"""

CHEVRON_UP_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>
  <path d='m18 15-6-6-6 6'/>
</svg>"""

CHECKMARK_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>
  <polyline points='20 6 9 17 4 12'/>
</svg>"""

PLUS_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>
  <line x1='12' y1='5' x2='12' y2='19'/>
  <line x1='5' y1='12' x2='19' y2='12'/>
</svg>"""

YOUTUBE_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='currentColor'>
  <path d='M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z'/>
</svg>"""

DISCORD_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='currentColor'>
  <path d='M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z'/>
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
        QFrame#StatusCard:hover {{
            background-color: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.22);
        }}
        QLabel#StatusPill[state="connected"] {{
            background-color: rgba(34, 197, 94, 0.16);
            color: #4ADE80;
            border: 1px solid rgba(34, 197, 94, 0.38);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="detected"] {{
            background-color: rgba(59, 130, 246, 0.16);
            color: #60A5FA;
            border: 1px solid rgba(59, 130, 246, 0.38);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="live"], QLabel#StatusPill[state="analyzing"] {{
            background-color: #0d1117;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="waiting"] {{
            background-color: #0d1117;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="offline"] {{
            background-color: rgba(239, 68, 68, 0.15);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.28);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#MetaText {{
            color: #8B949E;
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
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#ReadyBig[state="deactivated"] {{
            color: #F87171;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#EvalChip {{
            background-color: rgba(255, 255, 255, 0.08);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.16);
            border-radius: 8px;
            padding: 3px 14px;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
        }}
        QLabel#SubDetail {{
            color: #8B949E;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
        }}
        QFrame#QuickLaunchBar {{
            background-color: rgba(255, 255, 255, 0.035);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
        }}
        QLabel#QuickLaunchTitle {{
            color: #8B949E;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
        }}
        QLabel#QuickLaunchHint {{
            color: #484F58;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
        }}
        QPushButton#QuickBrowserBtn {{
            background-color: rgba(255, 255, 255, 0.06);
            color: #F0F6FC;
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 600;
            padding: 0 10px;
        }}
        QPushButton#QuickBrowserBtn:hover {{
            background-color: rgba(255, 255, 255, 0.14);
            border-color: rgba(255, 255, 255, 0.35);
            color: #FFFFFF;
        }}
        QPushButton#QuickBrowserBtn:pressed {{
            background-color: rgba(255, 255, 255, 0.22);
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
            color: #8B949E;
        }}
        QPushButton#MainActionBtnDeactivate {{
            background-color: rgba(255, 255, 255, 0.04);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.20);
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnDeactivate:hover {{
            background-color: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.35);
            color: #FFFFFF;
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
        QFrame#StatusCard:hover {{
            background-color: #F8FAFC;
            border: 1px solid rgba(0, 0, 0, 0.20);
        }}
        QLabel#StatusPill[state="connected"] {{
            background-color: #ECFDF5;
            color: #16A34A;
            border: 1px solid rgba(22, 163, 74, 0.32);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="detected"] {{
            background-color: #EFF6FF;
            color: #2563EB;
            border: 1px solid rgba(37, 99, 235, 0.32);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="live"], QLabel#StatusPill[state="analyzing"] {{
            background-color: #090B10;
            color: #FFFFFF;
            border: 1px solid #090B10;
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="waiting"] {{
            background-color: #090B10;
            color: #FFFFFF;
            border: 1px solid #090B10;
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#StatusPill[state="offline"] {{
            background-color: #FEF2F2;
            color: #DC2626;
            border: 1px solid rgba(220, 38, 38, 0.25);
            border-radius: 9999px;
            padding: 2px 10px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.6px;
        }}
        QLabel#MetaText {{
            color: #57606A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 500;
        }}
        QLabel#SquareBadge {{
            background-color: #F6F8FA;
            border: 1px solid #D0D7DE;
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
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#ReadyBig[state="deactivated"] {{
            color: #DC2626;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
        }}
        QLabel#EvalChip {{
            background-color: #FFFFFF;
            color: #090B10;
            border: 1px solid #D0D7DE;
            border-radius: 8px;
            padding: 3px 14px;
            font-family: -apple-system, "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 16px;
            font-weight: 700;
        }}
        QLabel#SubDetail {{
            color: #57606A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
        }}
        QFrame#QuickLaunchBar {{
            background-color: #F6F8FA;
            border: 1px solid #D0D7DE;
            border-radius: 12px;
        }}
        QLabel#QuickLaunchTitle {{
            color: #57606A;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.8px;
        }}
        QLabel#QuickLaunchHint {{
            color: #8C959F;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 10px;
        }}
        QPushButton#QuickBrowserBtn {{
            background-color: #FFFFFF;
            color: #24292F;
            border: 1px solid #D0D7DE;
            border-radius: 8px;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 11px;
            font-weight: 600;
            padding: 0 10px;
        }}
        QPushButton#QuickBrowserBtn:hover {{
            background-color: #F3F4F6;
            border-color: #0969DA;
            color: #0969DA;
        }}
        QPushButton#QuickBrowserBtn:pressed {{
            background-color: #E5E7EB;
        }}
        QLabel#SectionHeader {{
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 12px;
            font-weight: 600;
            color: #27272A;
        }}
        QFrame#EngineCard {{
            background-color: #FFFFFF;
            border: 1px solid #E1E4E8;
            border-radius: 12px;
        }}
        QFrame#EngineCard:hover {{
            background-color: #F6F8FA;
            border: 1px solid #D0D7DE;
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
            color: #57606A;
        }}
        QPushButton#MainActionBtnDeactivate {{
            background-color: #FFFFFF;
            color: #090B10;
            border: 1.5px solid #090B10;
            font-family: -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            border-radius: 12px;
        }}
        QPushButton#MainActionBtnDeactivate:hover {{
            background-color: #F8FAFC;
            border-color: #000000;
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
        self.setToolTip("Universal Stealth Engine: Automatically detects any browser open to Chess.com")
        self._build_ui()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        self.status_pill = QLabel("• ANALYZING")
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setProperty("state", "analyzing")
        top_row.addWidget(self.status_pill)
        top_row.addStretch()

        self.meta_lbl = QLabel("Depth 15 • 0.3s")
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

        self.ready_big = QLabel("ACTIVE")
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

    def show_live_move(self, from_sq: str, to_sq: str, eval_str: str, piece: str, depth: str, browser_name: str | None = None):
        self.from_sq.show()
        self.arrow_sym.show()
        self.to_sq.show()
        self.eval_chip.show()
        self.ready_big.hide()

        self.from_sq.setText(from_sq.upper())
        self.to_sq.setText(to_sq.upper())
        self.eval_chip.setText(eval_str)
        self.status_pill.setText("• ANALYZING")
        self.status_pill.setProperty("state", "analyzing")
        if browser_name:
            self.meta_lbl.setText(f"{browser_name} • Depth {depth} • 0.3s")
        else:
            self.meta_lbl.setText(f"Depth {depth} • 0.3s")
        self.sub_lbl.setText(f"{piece} • Recommended Move")
        self._refresh_styles()

    def show_waiting(self, is_connected: bool = True, browser_name: str | None = None, was_closed: bool = False):
        self.from_sq.hide()
        self.arrow_sym.hide()
        self.to_sq.hide()
        self.eval_chip.hide()
        self.ready_big.show()

        self.ready_big.setText("READY")
        self.ready_big.setProperty("state", "ready")
        if is_connected:
            b_label = f"●  CONNECTED ({browser_name.upper()})" if browser_name else "●  CONNECTED"
            self.status_pill.setText(b_label)
            self.status_pill.setProperty("state", "connected")
            self.meta_lbl.setText(f"{browser_name} • Ready" if browser_name else "Chess.com Engine")
            self.sub_lbl.setText("Connected to Chess.com • Start game to analyze moves")
        elif browser_name:
            self.status_pill.setText(f"●  DETECTED ({browser_name.upper()})")
            self.status_pill.setProperty("state", "detected")
            self.meta_lbl.setText("Chess.com")
            self.sub_lbl.setText("Detected")
        elif was_closed:
            self.status_pill.setText("●  WAITING FOR BROWSER")
            self.status_pill.setProperty("state", "waiting")
            self.meta_lbl.setText("All Browsers")
            self.sub_lbl.setText("Waiting for browser")
        else:
            self.status_pill.setText("●  WAITING FOR CHESS.COM")
            self.status_pill.setProperty("state", "waiting")
            self.meta_lbl.setText("Chess.com")
            self.sub_lbl.setText("Waiting for chess.com")
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
        self.sub_lbl.setText("Click ACTIVATE below to start detection")
        self._refresh_styles()

    def _refresh_styles(self):
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.ready_big.style().unpolish(self.ready_big)
        self.ready_big.style().polish(self.ready_big)


class QuickLaunchBar(QFrame):
    def __init__(self, on_launch_cb=None, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.on_launch_cb = on_launch_cb
        self.theme = theme
        self.setObjectName("QuickLaunchBar")
        self._build_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)

        title = QLabel("1-CLICK LAUNCH & PLAY")
        title.setObjectName("QuickLaunchTitle")
        head_row.addWidget(title)
        head_row.addStretch()

        hint = QLabel("Auto-loads Stealth Extension • 0 Setup")
        hint.setObjectName("QuickLaunchHint")
        head_row.addWidget(hint)
        lay.addLayout(head_row)

        btns_row = QHBoxLayout()
        btns_row.setContentsMargins(0, 0, 0, 0)
        btns_row.setSpacing(6)

        avail = get_available_browsers()
        if not avail:
            avail = [("chrome", "Chrome", ""), ("brave", "Brave", ""), ("edge", "Edge", "")]

        for b_key, b_name, _ in avail:
            btn = QPushButton(b_name)
            btn.setObjectName("QuickBrowserBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"1-Click: Mở {b_name} kèm tiện ích Stealth vào Chess.com (0 cần cài đặt)")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, k=b_key: self.on_launch_cb(k) if self.on_launch_cb else None)
            btns_row.addWidget(btn)

        lay.addLayout(btns_row)


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


BASIC_COLORS = [
    "#FF8080", "#FFFF80", "#80FF80", "#00FF80", "#80FFFF", "#0080FF", "#FF80C0", "#FF80FF",
    "#FF0000", "#FFFF00", "#80FF00", "#00FF40", "#00FFFF", "#0080C0", "#8080C0", "#FF00FF",
    "#804040", "#FF8040", "#00FF00", "#008080", "#004080", "#8080FF", "#800040", "#FF0080",
    "#800000", "#FF8000", "#008000", "#008040", "#0000FF", "#0000A0", "#800080", "#8000FF",
    "#400000", "#804000", "#004000", "#004040", "#000080", "#000040", "#400040", "#400080",
    "#000000", "#808000", "#808040", "#808080", "#408080", "#C0C0C0", "#804080", "#FFFFFF",
]

CUSTOM_SLOTS = ["#FFFFFF"] * 16


class ColorSpectrumWidget(QWidget):
    color_selected = Signal(int, int)  # hue, sat

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(170, 140)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.hue = 37
        self.sat = 244
        self.val = 245
        self._base_img = None
        self._init_base_image()

    def _init_base_image(self):
        w, h = 170, 140
        self._base_img = QImage(w, h, QImage.Format.Format_RGB32)
        for x in range(w):
            hue_val = int(x / float(w) * 359)
            for y in range(h):
                sat_val = int((1.0 - y / float(h)) * 255)
                self._base_img.setPixelColor(x, y, QColor.fromHsv(hue_val, sat_val, 255))

    def set_hsv(self, h: int, s: int, v: int):
        self.hue = max(0, min(359, h))
        self.sat = max(0, min(255, s))
        self.val = max(0, min(255, v))
        self.update()

    def mousePressEvent(self, event):
        self._handle_mouse(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_mouse(event)

    def _handle_mouse(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        x = max(0.0, min(float(self.width() - 1), float(pos.x())))
        y = max(0.0, min(float(self.height() - 1), float(pos.y())))
        self.hue = int(x / float(self.width()) * 359)
        self.sat = int((1.0 - y / float(self.height())) * 255)
        self.update()
        self.color_selected.emit(self.hue, self.sat)

    def paintEvent(self, event):
        p = QPainter(self)
        if self._base_img:
            p.drawImage(0, 0, self._base_img)

        darkness = 255 - self.val
        if darkness > 0:
            p.fillRect(0, 0, self.width(), self.height(), QColor(0, 0, 0, darkness))

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = int(self.hue / 359.0 * self.width())
        cy = int((1.0 - self.sat / 255.0) * self.height())

        p.setPen(QPen(QColor(0, 0, 0, 220), 2.5))
        p.drawLine(cx - 7, cy, cx + 7, cy)
        p.drawLine(cx, cy - 7, cx, cy + 7)

        p.setPen(QPen(QColor(255, 255, 255, 255), 1.2))
        p.drawLine(cx - 6, cy, cx + 6, cy)
        p.drawLine(cx, cy - 6, cx, cy + 6)
        p.end()


class ValueBarWidget(QWidget):
    val_selected = Signal(int)

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedSize(24, 140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hue = 37
        self.sat = 244
        self.val = 245

    def set_hsv(self, h: int, s: int, v: int):
        self.hue = h
        self.sat = s
        self.val = v
        self.update()

    def mousePressEvent(self, event):
        self._handle_mouse(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._handle_mouse(event)

    def _handle_mouse(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        y = max(0.0, min(float(self.height() - 1), float(pos.y())))
        self.val = int((1.0 - y / float(self.height())) * 255)
        self.update()
        self.val_selected.emit(self.val)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bar_w = 14
        grad = QLinearGradient(0, 0, 0, self.height())
        top_c = QColor.fromHsv(self.hue, self.sat, 255)
        grad.setColorAt(0.0, top_c)
        grad.setColorAt(1.0, QColor(0, 0, 0))

        p.setPen(QPen(QColor(0, 0, 0, 80), 1))
        p.setBrush(grad)
        p.drawRect(0, 0, bar_w, self.height())

        pointer_y = (1.0 - self.val / 255.0) * (self.height() - 1)
        poly = QPolygonF([
            QPointF(bar_w + 1, pointer_y),
            QPointF(self.width() - 1, pointer_y - 5),
            QPointF(self.width() - 1, pointer_y + 5),
        ])
        p.setPen(QPen(QColor(0, 0, 0, 180), 1))
        p.setBrush(QColor(255, 255, 255) if self.theme == "dark" else QColor(15, 23, 42))
        p.drawPolygon(poly)
        p.end()


class ColorBoxPreview(QWidget):
    def __init__(self, color: QColor, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.color = color
        self.theme = theme
        self.setFixedSize(50, 72)

    def set_color(self, color: QColor):
        self.color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)

        tile = 8.0
        for x in range(0, self.width(), int(tile)):
            for y in range(0, self.height(), int(tile)):
                is_light = ((x // int(tile)) + (y // int(tile))) % 2 == 0
                p.fillRect(x, y, int(tile), int(tile), QColor(240, 240, 240) if is_light else QColor(200, 200, 200))

        p.setBrush(self.color)
        p.setPen(QPen(QColor(255, 255, 255, 40) if self.theme == "dark" else QColor(0, 0, 0, 40), 1.5))
        p.drawRoundedRect(rect, 4, 4)
        p.end()


class ModernWindowsColorDialog(QDialog):
    def __init__(self, initial_color: QColor, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.current_color = QColor(initial_color)
        self.theme = theme
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(480, 360)
        self._drag_pos = None

        self._updating = False
        self._build_ui()
        self._sync_all_from_color(self.current_color)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        is_dark = (self.theme == "dark")
        card = QFrame()
        card.setObjectName("WindowColorCard")
        bg_card = "#12151e" if is_dark else "#ffffff"
        border_card = "rgba(255, 255, 255, 0.16)" if is_dark else "rgba(0, 0, 0, 0.16)"
        text_primary = "#f5f5f7" if is_dark else "#1d1d1f"
        text_muted = "#98989f" if is_dark else "#6e6e73"

        card.setStyleSheet(f"""
            QFrame#WindowColorCard {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 12px;
            }}
            QLabel {{
                color: {text_primary};
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
                font-size: 11px;
            }}
            QSpinBox {{
                background-color: {'rgba(255, 255, 255, 0.06)' if is_dark else '#ffffff'};
                color: {text_primary};
                border: 1px solid {'rgba(255, 255, 255, 0.15)' if is_dark else '#cbd5e1'};
                border-radius: 4px;
                padding: 1px 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: 600;
                min-height: 20px;
            }}
            QSpinBox:focus {{
                border: 1px solid {'#0a84ff' if is_dark else '#0071e3'};
            }}
        """)
        root.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 12)
        card_layout.setSpacing(8)

        # Title bar
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        title_lbl = QLabel("Choose Arrow Color (RGB)")
        title_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {text_primary};")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {text_muted};
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.1)' if is_dark else 'rgba(0, 0, 0, 0.08)'};
                color: {text_primary};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        card_layout.addLayout(title_row)

        # Body layout: 2 Columns matching Windows dialog
        body = QHBoxLayout()
        body.setSpacing(14)

        # Left Column: Basic Colors & Custom Colors
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        lbl_basic = QLabel("Basic colors")
        lbl_basic.setFont(QFont("Segoe UI", 9))
        left_col.addWidget(lbl_basic)

        # 48 Basic Colors Grid (8 cols x 6 rows)
        basic_grid = QGridLayout()
        basic_grid.setSpacing(2)
        basic_grid.setContentsMargins(0, 0, 0, 0)

        for i, hex_c in enumerate(BASIC_COLORS):
            btn = QPushButton()
            btn.setFixedSize(19, 17)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_c};
                    border: 1px solid {'rgba(255, 255, 255, 0.2)' if is_dark else 'rgba(0, 0, 0, 0.25)'};
                    border-radius: 1px;
                }}
                QPushButton:hover {{
                    border: 1.5px solid {'#ffffff' if is_dark else '#000000'};
                }}
            """)
            btn.clicked.connect(lambda _, c=hex_c: self._pick_hex(c))
            basic_grid.addWidget(btn, i // 8, i % 8)
        left_col.addLayout(basic_grid)

        # Pick Screen Color Button
        self.pick_screen_btn = QPushButton("Pick Screen Color")
        self.pick_screen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pick_screen_btn.setFixedHeight(24)
        self.pick_screen_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'rgba(255, 255, 255, 0.06)' if is_dark else '#f1f5f9'};
                color: {text_primary};
                border: 1px solid {'rgba(255, 255, 255, 0.12)' if is_dark else '#cbd5e1'};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.12)' if is_dark else '#e2e8f0'};
            }}
        """)
        left_col.addWidget(self.pick_screen_btn)

        # Custom Colors Label
        lbl_custom = QLabel("Custom colors")
        lbl_custom.setFont(QFont("Segoe UI", 9))
        left_col.addWidget(lbl_custom)

        # 16 Custom Colors Grid (8 cols x 2 rows)
        self.custom_btns = []
        custom_grid = QGridLayout()
        custom_grid.setSpacing(2)
        custom_grid.setContentsMargins(0, 0, 0, 0)

        for i in range(16):
            btn = QPushButton()
            btn.setFixedSize(19, 17)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {CUSTOM_SLOTS[i]};
                    border: 1px solid {'rgba(255, 255, 255, 0.2)' if is_dark else 'rgba(0, 0, 0, 0.25)'};
                    border-radius: 1px;
                }}
                QPushButton:hover {{
                    border: 1.5px solid {'#ffffff' if is_dark else '#000000'};
                }}
            """)
            btn.clicked.connect(lambda _, idx=i: self._pick_custom_slot(idx))
            custom_grid.addWidget(btn, i // 8, i % 8)
            self.custom_btns.append(btn)
        left_col.addLayout(custom_grid)

        # Add to Custom Colors Button
        self.add_custom_btn = QPushButton("Add to Custom Colors")
        self.add_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_custom_btn.setFixedHeight(24)
        self.add_custom_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'rgba(255, 255, 255, 0.06)' if is_dark else '#f1f5f9'};
                color: {text_primary};
                border: 1px solid {'rgba(255, 255, 255, 0.12)' if is_dark else '#cbd5e1'};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.12)' if is_dark else '#e2e8f0'};
            }}
        """)
        self.add_custom_btn.clicked.connect(self._add_to_custom)
        left_col.addWidget(self.add_custom_btn)

        body.addLayout(left_col)

        # Right Column: Spectrum + Sliders & Spinboxes
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # Spectrum + Value Bar Row
        spec_row = QHBoxLayout()
        spec_row.setSpacing(4)
        self.spectrum = ColorSpectrumWidget()
        self.spectrum.color_selected.connect(self._on_spectrum_selected)
        spec_row.addWidget(self.spectrum)

        self.val_bar = ValueBarWidget(theme=self.theme)
        self.val_bar.val_selected.connect(self._on_val_bar_selected)
        spec_row.addWidget(self.val_bar)
        right_col.addLayout(spec_row)

        # Preview + Spinboxes Row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)

        self.color_preview = ColorBoxPreview(self.current_color, theme=self.theme)
        controls_row.addWidget(self.color_preview)

        spin_grid = QGridLayout()
        spin_grid.setSpacing(4)
        spin_grid.setContentsMargins(0, 0, 0, 0)

        spin_grid.addWidget(QLabel("Hue:"), 0, 0)
        self.sp_hue = QSpinBox()
        self.sp_hue.setRange(0, 359)
        self.sp_hue.setFixedWidth(50)
        self.sp_hue.valueChanged.connect(self._on_hsv_spin_changed)
        spin_grid.addWidget(self.sp_hue, 0, 1)

        spin_grid.addWidget(QLabel("Red:"), 0, 2)
        self.sp_red = QSpinBox()
        self.sp_red.setRange(0, 255)
        self.sp_red.setFixedWidth(50)
        self.sp_red.valueChanged.connect(self._on_rgb_spin_changed)
        spin_grid.addWidget(self.sp_red, 0, 3)

        spin_grid.addWidget(QLabel("Sat:"), 1, 0)
        self.sp_sat = QSpinBox()
        self.sp_sat.setRange(0, 255)
        self.sp_sat.setFixedWidth(50)
        self.sp_sat.valueChanged.connect(self._on_hsv_spin_changed)
        spin_grid.addWidget(self.sp_sat, 1, 1)

        spin_grid.addWidget(QLabel("Green:"), 1, 2)
        self.sp_green = QSpinBox()
        self.sp_green.setRange(0, 255)
        self.sp_green.setFixedWidth(50)
        self.sp_green.valueChanged.connect(self._on_rgb_spin_changed)
        spin_grid.addWidget(self.sp_green, 1, 3)

        spin_grid.addWidget(QLabel("Val:"), 2, 0)
        self.sp_val = QSpinBox()
        self.sp_val.setRange(0, 255)
        self.sp_val.setFixedWidth(50)
        self.sp_val.valueChanged.connect(self._on_hsv_spin_changed)
        spin_grid.addWidget(self.sp_val, 2, 1)

        spin_grid.addWidget(QLabel("Blue:"), 2, 2)
        self.sp_blue = QSpinBox()
        self.sp_blue.setRange(0, 255)
        self.sp_blue.setFixedWidth(50)
        self.sp_blue.valueChanged.connect(self._on_rgb_spin_changed)
        spin_grid.addWidget(self.sp_blue, 2, 3)

        spin_grid.addWidget(QLabel("Alpha channel:"), 3, 0, 1, 2)
        self.sp_alpha = QSpinBox()
        self.sp_alpha.setRange(0, 255)
        self.sp_alpha.setFixedWidth(50)
        self.sp_alpha.valueChanged.connect(self._on_alpha_spin_changed)
        spin_grid.addWidget(self.sp_alpha, 3, 2, 1, 2)

        self.slider_r = self.sp_red
        self.slider_g = self.sp_green
        self.slider_b = self.sp_blue
        self.slider_a = self.sp_alpha

        controls_row.addLayout(spin_grid)
        right_col.addLayout(controls_row)

        # HTML / Hex Code Row
        html_row = QHBoxLayout()
        html_row.setSpacing(6)
        html_lbl = QLabel("HTML:")
        html_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        html_row.addWidget(html_lbl)

        self.html_input = QLineEdit()
        self.html_input.setFixedHeight(22)
        self.html_input.setMaxLength(9)
        self.html_input.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.html_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {'rgba(255, 255, 255, 0.06)' if is_dark else '#ffffff'};
                color: {text_primary};
                border: 1px solid {'rgba(255, 255, 255, 0.15)' if is_dark else '#cbd5e1'};
                border-radius: 4px;
                padding: 1px 6px;
            }}
            QLineEdit:focus {{
                border: 1px solid {'#0a84ff' if is_dark else '#0071e3'};
            }}
        """)
        self.html_input.textEdited.connect(self._on_html_edited)
        html_row.addWidget(self.html_input)
        right_col.addLayout(html_row)

        body.addLayout(right_col)
        card_layout.addLayout(body)

        # Bottom Row: OK / Cancel Buttons
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setFixedSize(74, 28)
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'#0a84ff' if is_dark else '#0071e3'};
                color: #ffffff;
                border: none;
                border-radius: 5px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {'#0071e3' if is_dark else '#005bb5'};
            }}
        """)
        self.ok_btn.clicked.connect(self.accept)
        bottom_row.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(74, 28)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'rgba(255, 255, 255, 0.08)' if is_dark else '#f1f5f9'};
                color: {text_primary};
                border: 1px solid {'rgba(255, 255, 255, 0.15)' if is_dark else '#cbd5e1'};
                border-radius: 5px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.14)' if is_dark else '#e2e8f0'};
            }}
        """)
        self.cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(self.cancel_btn)

        card_layout.addLayout(bottom_row)

    def _sync_all_from_color(self, color: QColor):
        if self._updating:
            return
        self._updating = True

        h, s, v, _ = color.getHsv()
        if h < 0:
            h = 0
        r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()

        self.spectrum.set_hsv(h, s, v)
        self.val_bar.set_hsv(h, s, v)
        self.color_preview.set_color(color)

        self.sp_hue.setValue(h)
        self.sp_sat.setValue(s)
        self.sp_val.setValue(v)

        self.sp_red.setValue(r)
        self.sp_green.setValue(g)
        self.sp_blue.setValue(b)
        self.sp_alpha.setValue(a)

        self.html_input.setText(f"#{r:02x}{g:02x}{b:02x}")
        self._updating = False

    def _on_spectrum_selected(self, hue: int, sat: int):
        v = self.sp_val.value()
        a = self.sp_alpha.value()
        c = QColor.fromHsv(hue, sat, v)
        c.setAlpha(a)
        self.current_color = c
        self._sync_all_from_color(c)

    def _on_val_bar_selected(self, val: int):
        h = self.sp_hue.value()
        s = self.sp_sat.value()
        a = self.sp_alpha.value()
        c = QColor.fromHsv(h, s, val)
        c.setAlpha(a)
        self.current_color = c
        self._sync_all_from_color(c)

    def _on_rgb_spin_changed(self):
        if self._updating:
            return
        r = self.sp_red.value()
        g = self.sp_green.value()
        b = self.sp_blue.value()
        a = self.sp_alpha.value()
        self.current_color = QColor(r, g, b, a)
        self._sync_all_from_color(self.current_color)

    def _on_slider_changed(self):
        self._on_rgb_spin_changed()

    def _on_hsv_spin_changed(self):
        if self._updating:
            return
        h = self.sp_hue.value()
        s = self.sp_sat.value()
        v = self.sp_val.value()
        a = self.sp_alpha.value()
        c = QColor.fromHsv(h, s, v)
        c.setAlpha(a)
        self.current_color = c
        self._sync_all_from_color(c)

    def _on_alpha_spin_changed(self, val: int):
        if self._updating:
            return
        self.current_color.setAlpha(val)
        self.color_preview.set_color(self.current_color)

    def _on_html_edited(self, text: str):
        if self._updating:
            return
        t = text.strip()
        if not t.startswith("#"):
            t = "#" + t
        if len(t) == 7:
            try:
                c = QColor(t)
                if c.isValid():
                    c.setAlpha(self.sp_alpha.value())
                    self.current_color = c
                    self._sync_all_from_color(c)
            except Exception:
                pass

    def _pick_hex(self, hex_c: str):
        c = QColor(hex_c)
        c.setAlpha(self.sp_alpha.value())
        self.current_color = c
        self._sync_all_from_color(c)

    def _pick_quick_color(self, hex_c: str):
        self._pick_hex(hex_c)

    def _on_hex_edited(self, text: str):
        self._on_html_edited(text)

    def _pick_custom_slot(self, idx: int):
        c = QColor(CUSTOM_SLOTS[idx])
        c.setAlpha(self.sp_alpha.value())
        self.current_color = c
        self._sync_all_from_color(c)

    def _add_to_custom(self):
        hex_val = f"#{self.current_color.red():02X}{self.current_color.green():02X}{self.current_color.blue():02X}"
        target_idx = 0
        for i, s in enumerate(CUSTOM_SLOTS):
            if s.upper() == "#FFFFFF":
                target_idx = i
                break
        CUSTOM_SLOTS[target_idx] = hex_val
        self.custom_btns[target_idx].setStyleSheet(f"""
            QPushButton {{
                background-color: {hex_val};
                border: 1px solid {'rgba(255, 255, 255, 0.2)' if self.theme == 'dark' else 'rgba(0, 0, 0, 0.25)'};
                border-radius: 1px;
            }}
            QPushButton:hover {{
                border: 1.5px solid {'#ffffff' if self.theme == 'dark' else '#000000'};
            }}
        """)

    @classmethod
    def get_color(cls, initial_color: QColor, theme: str = "dark", parent=None) -> QColor | None:
        dlg = cls(initial_color, theme=theme, parent=parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.current_color
        return None


# Backward-compatible alias
ModernColorPickerDialog = ModernWindowsColorDialog
ModernColorDialog = ModernWindowsColorDialog


class ModernLogoutDialog(QDialog):
    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(360, 210)
        self._drag_pos = None
        self.confirmed = False

        self._build_ui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        is_dark = (self.theme == "dark")
        card = QFrame()
        card.setObjectName("LogoutModalCard")

        bg_card = "#11131a" if is_dark else "#ffffff"
        border_card = "#202433" if is_dark else "#e2e8f0"
        text_primary = "#ffffff" if is_dark else "#0f172a"
        text_secondary = "#94a3b8" if is_dark else "#475569"
        btn_cancel_bg = "rgba(255, 255, 255, 0.08)" if is_dark else "#f1f5f9"
        btn_cancel_border = "rgba(255, 255, 255, 0.12)" if is_dark else "#cbd5e1"
        btn_cancel_hover = "rgba(255, 255, 255, 0.14)" if is_dark else "#e2e8f0"

        card.setStyleSheet(f"""
            QFrame#LogoutModalCard {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 16px;
            }}
        """)
        root.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        # Top row: Danger Icon Badge + Close button
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        icon_badge = QFrame()
        icon_badge.setFixedSize(38, 38)
        badge_bg = "rgba(239, 68, 68, 0.15)" if is_dark else "rgba(220, 38, 38, 0.10)"
        icon_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            border-radius: 10px;
            border: 1px solid {'rgba(239, 68, 68, 0.25)' if is_dark else 'rgba(220, 38, 38, 0.20)'};
        """)
        badge_layout = QVBoxLayout(icon_badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ic_lbl = QLabel()
        ic_col = "#ef4444" if is_dark else "#dc2626"
        ic_lbl.setPixmap(render_svg_icon(LOGOUT_KEY_SVG, 20, ic_col))
        badge_layout.addWidget(ic_lbl)
        top_row.addWidget(icon_badge)

        top_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {text_secondary};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {'rgba(255, 255, 255, 0.1)' if is_dark else 'rgba(0, 0, 0, 0.06)'};
                color: {text_primary};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        top_row.addWidget(close_btn)
        card_layout.addLayout(top_row)

        # Content text
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel("Log Out License Key?")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {text_primary};")
        text_col.addWidget(title_lbl)

        desc_lbl = QLabel("Are you sure you want to log out of your current license key? Your active session will be cleared and you will return to the activation screen.")
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont("Segoe UI", 9))
        desc_lbl.setStyleSheet(f"color: {text_secondary}; line-height: 1.4;")
        text_col.addWidget(desc_lbl)
        card_layout.addLayout(text_col)

        card_layout.addStretch()

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_cancel_bg};
                color: {text_secondary};
                border: 1px solid {btn_cancel_border};
                border-radius: 8px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {btn_cancel_hover};
                color: {text_primary};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn, 1)

        confirm_btn = QPushButton("Log Out")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {'#ef4444' if is_dark else '#dc2626'};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {'#dc2626' if is_dark else '#b91c1c'};
            }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(confirm_btn, 1)

        card_layout.addLayout(btn_row)

    def _on_confirm(self):
        self.confirmed = True
        self.accept()

    @classmethod
    def ask_logout(cls, parent=None, theme: str = "dark") -> bool:
        dlg = cls(theme=theme, parent=parent)
        if parent:
            geo = parent.geometry()
            dlg.move(
                geo.center().x() - dlg.width() // 2,
                geo.center().y() - dlg.height() // 2,
            )
        dlg.setWindowOpacity(0.0)
        dlg.show()
        anim = QPropertyAnimation(dlg, b"windowOpacity")
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        dlg._anim = anim
        anim.start()
        dlg.exec()
        return dlg.confirmed


class LuxurySplashScreen(QWidget):
    def __init__(self, on_finish=None):
        super().__init__()
        self.on_finish = on_finish
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(440, 230)
        self._progress_val = 0
        self._timer = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("SplashCard")
        card.setStyleSheet("""
            QFrame#SplashCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0B0D14, stop:1 #131722);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 18px;
            }
        """)
        root.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Queen Logo
        self.logo_lbl = QLabel()
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = get_asset_path("queen_light.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_lbl.setPixmap(pix)
        layout.addWidget(self.logo_lbl)

        # 2. Title + PRO Badge
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.setSpacing(8)

        title = QLabel("CHESS STEALTH")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.ExtraBold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 1.5px;")
        title_row.addWidget(title)

        pro_badge = MetallicWordmarkLabel("PRO", "dark")
        title_row.addWidget(pro_badge)
        layout.addLayout(title_row)

        layout.addSpacing(6)

        # 3. Animated Glowing Progress Bar (Rounded Pure White Luxury)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.12);
                border: none;
                border-radius: 3px;
                min-height: 6px;
                max-height: 6px;
            }
            QProgressBar::chunk {
                background-color: #FFFFFF;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # 4. Status message with progress indicator
        self.status_lbl = QLabel("Starting... 0%")
        self.status_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.status_lbl.setStyleSheet("color: #94A3B8;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 18, 18)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor("#0B0D14"))
        p.end()

    def update_progress(self, val: int, text: str):
        self._progress_val = val
        self.progress_bar.setValue(val)
        self.status_lbl.setText(f"{text}  {val}%")

    def _fade_out(self):
        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out_anim.setDuration(180)
        self._fade_out_anim.setStartValue(1.0)
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        def _on_done():
            self.close()
            if self.on_finish:
                self.on_finish()
        self._fade_out_anim.finished.connect(_on_done)
        self._fade_out_anim.start()

    def _step_progress(self):
        self._progress_val += 2
        val = min(self._progress_val, 100)
        self.progress_bar.setValue(val)
        if val < 35:
            self.status_lbl.setText(f"Loading engine... {val}%")
        elif val < 70:
            self.status_lbl.setText(f"Starting services... {val}%")
        elif val < 95:
            self.status_lbl.setText(f"Verifying license... {val}%")
        else:
            self.status_lbl.setText("Ready  100%")

        if self._progress_val >= 100:
            if self._timer is not None:
                self._timer.stop()
            self._fade_out()

    def start(self, auto_step: bool = True):
        app = QApplication.instance()
        if app and app.primaryScreen():
            geo = app.primaryScreen().geometry()
            self.move(
                (geo.width() - self.width()) // 2,
                (geo.height() - self.height()) // 2,
            )
        self.setWindowOpacity(1.0)
        self.show()

        if auto_step:
            self._timer = QTimer(self)
            self._timer.setInterval(12)
            self._timer.timeout.connect(self._step_progress)
            self._timer.start()


class ColorPickerButton(QPushButton):
    def __init__(self, color: QColor, on_color_changed=None, theme: str = "dark", parent=None):
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
        new_color = ModernWindowsColorDialog.get_color(
            self.current_color,
            theme=self.theme,
            parent=self.window(),
        )
        if new_color and new_color.isValid():
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
        self.qcolor = color  # alias for backwards compatibility
        self.on_click = on_click
        self.is_active = False
        self.is_hovered = False
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.clicked.connect(self._handle_click)

    def _handle_click(self):
        if self.on_click:
            self.on_click(self.name)

    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        cx, cy = rect.center().x(), rect.center().y()
        r = 13.0
        is_dark = (_CURRENT_THEME == "dark")

        if self.is_active:
            glow_pen = QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), 120), 4.0)
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - 15, cy - 15, 30, 30)

            contrast_ring = QColor(255, 255, 255, 240) if is_dark else QColor(15, 23, 42, 220)
            p.setPen(QPen(contrast_ring, 2.0))
            p.drawEllipse(cx - 15, cy - 15, 30, 30)
        elif self.is_hovered:
            hover_pen = QPen(QColor(255, 255, 255, 120) if is_dark else QColor(0, 0, 0, 70), 1.8)
            p.setPen(hover_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - 15, cy - 15, 30, 30)
            r = 13.5

        # Inner color fill
        p.setPen(QPen(QColor(0, 0, 0, 40), 1.0))
        p.setBrush(self.color)
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # White checkmark if active
        if self.is_active:
            p.setPen(QPen(QColor(255, 255, 255, 250), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawLine(cx - 4, cy, cx - 1, cy + 3)
            p.drawLine(cx - 1, cy + 3, cx + 4, cy - 3)
        p.end()


class EngineItemWidget(QFrame):
    clicked = Signal(dict)

    def __init__(self, engine_data: dict, is_selected: bool = False, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.engine_data = engine_data
        self.is_selected = is_selected
        self.theme = theme
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 12, 6)
        layout.setSpacing(10)

        # Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(32, 32)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic_p = get_asset_path(engine_data["icon"])
        if os.path.exists(ic_p):
            self.icon_lbl.setPixmap(QPixmap(ic_p).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(self.icon_lbl)

        # Text col
        t_col = QVBoxLayout()
        t_col.setContentsMargins(0, 0, 0, 0)
        t_col.setSpacing(2)

        self.name_lbl = QLabel(engine_data["name"])
        self.name_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        t_col.addWidget(self.name_lbl)

        self.sub_lbl = QLabel(engine_data["details"])
        self.sub_lbl.setFont(QFont("Segoe UI", 8))
        t_col.addWidget(self.sub_lbl)
        layout.addLayout(t_col, 1)

        # Checkmark
        self.check_lbl = QLabel()
        self.check_lbl.setFixedSize(18, 18)
        self.check_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.is_selected:
            chk_color = "#38BDF8" if self.theme == "dark" else "#0F172A"
            self.check_lbl.setPixmap(render_svg_icon(CHECKMARK_SVG, 16, chk_color))
        layout.addWidget(self.check_lbl)

        self._apply_style(False)

    def _apply_style(self, is_hover: bool):
        if self.theme == "dark":
            if self.is_selected:
                bg = "rgba(56, 189, 248, 0.12)" if is_hover else "rgba(255, 255, 255, 0.06)"
                border = "rgba(56, 189, 248, 0.35)" if is_hover else "rgba(255, 255, 255, 0.14)"
            else:
                bg = "rgba(255, 255, 255, 0.08)" if is_hover else "transparent"
                border = "rgba(255, 255, 255, 0.10)" if is_hover else "transparent"
            name_col = "#FFFFFF"
            sub_col = "#94A3B8"
        else:
            if self.is_selected:
                bg = "#E2E8F0" if is_hover else "#F1F5F9"
                border = "#94A3B8" if is_hover else "#CBD5E1"
            else:
                bg = "#F1F5F9" if is_hover else "transparent"
                border = "#E2E8F0" if is_hover else "transparent"
            name_col = "#0F172A"
            sub_col = "#64748B"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        self.name_lbl.setStyleSheet(f"color: {name_col};")
        self.sub_lbl.setStyleSheet(f"color: {sub_col};")

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            # Postpone emit to next event loop tick so Qt finishes event processing cleanly
            eng_data = self.engine_data
            QTimer.singleShot(0, lambda: self.clicked.emit(eng_data))
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)


class EngineDropdownPopup(QWidget):
    def __init__(self, parent_card, engines: list, current_engine_id: str, on_select, theme: str = "dark"):
        parent_win = parent_card.window() if (parent_card and hasattr(parent_card, "window")) else None
        super().__init__(parent_win, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.parent_card = parent_card
        self.engines = engines
        self.current_engine_id = current_engine_id
        self.on_select = on_select
        self.theme = theme

        self.setFixedWidth(344)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("DropdownCard")
        bg = "#11141C" if self.theme == "dark" else "#FFFFFF"
        border = "rgba(255, 255, 255, 0.16)" if self.theme == "dark" else "#CBD5E1"
        thumb_bg = "rgba(255, 255, 255, 0.22)" if self.theme == "dark" else "#94A3B8"
        thumb_hover = "rgba(255, 255, 255, 0.40)" if self.theme == "dark" else "#64748B"

        card.setStyleSheet(f"""
            QFrame#DropdownCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 6px 3px 6px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {thumb_bg};
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {thumb_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(4, 6, 4, 6)
        card_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(3)

        self.items = []
        for eng in self.engines:
            is_sel = (eng.get("id") == self.current_engine_id or eng.get("name") == self.current_engine_id)
            item = EngineItemWidget(eng, is_selected=is_sel, theme=self.theme, parent=scroll_content)
            item.clicked.connect(self._handle_select)
            content_layout.addWidget(item)
            self.items.append(item)

        scroll.setWidget(scroll_content)
        card_layout.addWidget(scroll)
        root.addWidget(card)

        # Giới hạn chiều cao hiển thị 248px (~5 items), kéo cuộn mượt mà khi danh sách dài
        item_count = len(self.engines)
        total_items_height = item_count * 51 + 16
        popup_height = min(total_items_height, 248)
        self.setFixedHeight(popup_height)

    def _update_selected_item(self):
        for item in getattr(self, "items", []):
            item.is_selected = (item.engine_data.get("id") == self.current_engine_id or item.engine_data.get("name") == self.current_engine_id)
            if item.is_selected:
                chk_color = "#38BDF8" if self.theme == "dark" else "#0F172A"
                item.check_lbl.setPixmap(render_svg_icon(CHECKMARK_SVG, 16, chk_color))
            else:
                item.check_lbl.setPixmap(QPixmap())
            item._apply_style(False)

    def _handle_select(self, eng_data: dict):
        self.current_engine_id = eng_data.get("id") or eng_data.get("name")
        self._update_selected_item()
        if self.on_select:
            self.on_select(eng_data)
        self.hide()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.parent_card:
            self.parent_card._on_dropdown_hidden()


class EngineCard(QFrame):
    def __init__(self, engine_name: str = "Stockfish 16", details: str = "Level 20 • ~3500 ELO (Maximum)", icon_file: str = "icon_engine_stockfish.png", on_select=None, theme: str = "light", parent=None):
        super().__init__(parent)
        self.setObjectName("EngineCard")
        self.engine_name = engine_name
        self.details = details
        self.icon_file = icon_file
        self.on_select = on_select
        self.theme = theme
        self.current_engine_id = "sf_20"
        self._dropdown = None
        self._last_close_time = 0.0
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
        if self._dropdown is not None:
            self._dropdown.hide()
            self._dropdown.deleteLater()
            self._dropdown = None
        self._update_assets()

    def _update_assets(self):
        chev_color = "#52525B" if self.theme == "light" else "#9CA3AF"
        chev_svg = CHEVRON_UP_SVG if (self._dropdown is not None and self._dropdown.isVisible()) else CHEVRON_DOWN_SVG
        chev_pix = render_svg_icon(chev_svg, 12, chev_color)
        self.chevron_lbl.setPixmap(chev_pix)

        icon_p = get_asset_path(self.icon_file)
        if os.path.exists(icon_p):
            pix = QPixmap(icon_p).scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_box.setPixmap(pix)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            now = time.time()
            if self._dropdown is not None and self._dropdown.isVisible():
                self._dropdown.hide()
                return
            if now - self._last_close_time < 0.28:
                return
            self._toggle_popup()
            return
        super().mousePressEvent(event)

    def _toggle_popup(self):
        if self._dropdown is None:
            self._dropdown = EngineDropdownPopup(
                parent_card=self,
                engines=AVAILABLE_ENGINES,
                current_engine_id=self.current_engine_id,
                on_select=self._on_engine_picked,
                theme=self.theme,
            )
        else:
            self._dropdown.current_engine_id = self.current_engine_id
            self._dropdown._update_selected_item()

        self._update_assets()

        # Always open directly below the engine card
        card_pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        self._dropdown.move(card_pos)
        self._dropdown.setWindowOpacity(1.0)
        self._dropdown.show()
        self._dropdown.raise_()
        self._dropdown.activateWindow()

    def _on_dropdown_hidden(self):
        self._last_close_time = time.time()
        self._update_assets()
        if self.window():
            self.window().raise_()
            self.window().activateWindow()

    def _on_engine_picked(self, target_eng: dict):
        self.current_engine_id = target_eng.get("id", self.current_engine_id)
        self.set_data(target_eng["name"], target_eng["details"], target_eng["icon"])
        if self.on_select:
            self.on_select(target_eng)


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
        self.status_card.setToolTip("Chess.com connection status & engine best moves")
        self.setStyleSheet(_build_qss(_CURRENT_THEME))
        self.adjustSize()

        self._last_rendered_sig = None
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._sync_live_status)
        self.status_timer.start(250)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_has_faded_in", False):
            self._has_faded_in = True
            self.setWindowOpacity(0.0)
            anim = QPropertyAnimation(self, b"windowOpacity")
            anim.setDuration(280)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._in_anim = anim
            anim.start()

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
        if not getattr(self, "_logging_out", False):
            app = QApplication.instance()
            if app:
                app.quit()

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
        icon_pix = render_svg_icon(LOGOUT_KEY_SVG, 16, col)
        self.logout_btn.setIcon(QIcon(icon_pix))
        self.logout_btn.setIconSize(QSize(16, 16))

    def _logout_key(self):
        if not ModernLogoutDialog.ask_logout(parent=self, theme=_CURRENT_THEME):
            return
        try:
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            cache_f = os.path.join(APP_DIR, "verified_session.json")
            if os.path.exists(cache_f):
                os.remove(cache_f)
        except Exception:
            pass
        self._logging_out = True
        self.close()

        def open_control_center(k: str):
            ctrl = ControlCenterWindow(k, self.hwid)
            _ACTIVE_WINDOWS.append(ctrl)
            ctrl.show()

        def show_activation():
            win = ActivationWindow(self.hwid, open_control_center)
            _ACTIVE_WINDOWS.append(win)
            win.setWindowOpacity(0.0)
            win.show()
            fade_in = QPropertyAnimation(win, b"windowOpacity")
            fade_in.setDuration(220)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            win._fade_in = fade_in
            fade_in.start()

        splash = LuxurySplashScreen(on_finish=show_activation)
        _ACTIVE_WINDOWS.append(splash)
        splash.start()

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
        self.logout_btn.setToolTip("Log Out License Key")
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
        if hasattr(self, "arrow_preview"):
            self.arrow_preview.set_color(new_color)
        if hasattr(self, "color_btn"):
            self.color_btn.set_color(new_color)
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
        if hasattr(self, "color_btn"):
            self.color_btn.set_theme(_CURRENT_THEME)
        if hasattr(self, "arrow_preview"):
            self.arrow_preview.set_theme(_CURRENT_THEME)
        if hasattr(self, "quick_launch"):
            self.quick_launch.set_theme(_CURRENT_THEME)
        for sw in self.swatches.values():
            sw.update()
        self._last_rendered_sig = None
        self._sync_live_status()
        self.update()

    def _on_quick_launch_browser(self, browser_key: str):
        self.status_card.sub_lbl.setText(f"Launching {browser_key.title()} (1-Click Zero Setup)...")
        launch_browser_for_chess(browser_key)

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
        is_connected = (now - arrow_state.get("last_ping", 0.0) <= 4.0)

        detected = detect_active_chess_browser()
        if detected:
            b_name = detected["name"]
            arrow_state["detected_browser"] = b_name
            self._has_seen_browser = True
        else:
            b_name = None
            arrow_state["detected_browser"] = None
            arrow_state["show"] = False

        was_closed = getattr(self, "_has_seen_browser", False) and (b_name is None)
        effective_connected = is_connected and (b_name is not None)
        is_showing_move = (
            arrow_state.get("show", False)
            and (now - arrow_state.get("last_seen", 0.0) <= 3.0)
            and bool(arrow_state.get("move", ""))
            and (b_name is not None)
        )

        if arrow_state.get("enabled", True) and not effective_connected and arrow_state.get("last_ping", 0.0) == 0.0 and detected:
            if getattr(self, "_unconnected_detect_since", None) is None:
                self._unconnected_detect_since = now
            elif now - self._unconnected_detect_since >= 3.5:
                self._unconnected_detect_since = now
                auto_hook_running_browser(detected)
        else:
            self._unconnected_detect_since = None

        current_sig = (
            arrow_state.get("enabled", True),
            is_showing_move,
            arrow_state.get("move", "") if is_showing_move else "",
            arrow_state.get("depth", "") if is_showing_move else "",
            arrow_state.get("eval", "") if is_showing_move else "",
            arrow_state.get("ponder", "") if is_showing_move else "",
            arrow_state.get("piece", "") if is_showing_move else "",
            effective_connected,
            b_name,
            was_closed,
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

            self.status_card.show_live_move(from_sq, to_sq, ev, f"{side_txt} {piece_name}", d, browser_name=b_name)
            self.action_btn.setObjectName("MainActionBtnDeactivate")
            self.action_btn.setText("DEACTIVATE")
        else:
            self.status_card.show_waiting(is_connected=effective_connected, browser_name=b_name, was_closed=was_closed)
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

    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim = anim
        anim.start()


class LuxuryFrostedCard(QFrame):
    """
    Luxury Frosted Glass Card Container with dynamic glassmorphism,
    subtle dot-matrix texture, and specular highlight edge refraction.
    """
    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("FrostedCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_theme(self, t: str):
        self.theme = t
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        # 1. Clip strictly to 24px rounded card
        path = QPainterPath()
        path.addRoundedRect(rect, 24.0, 24.0)
        p.setClipPath(path)

        if self.theme == "dark":
            # 2. Smoked Obsidian Glass Base
            p.fillRect(self.rect(), QColor(14, 18, 26, 180))

            # 3. Soft internal ambient WHITE luminous glow (strictly monochrome, zero blue)
            glow = QRadialGradient(QPointF(w * 0.85, h * 0.16), w * 0.75)
            glow.setColorAt(0.0, QColor(255, 255, 255, 46))   # Pure white ambient glow
            glow.setColorAt(0.45, QColor(255, 255, 255, 16))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(self.rect(), QBrush(glow))

            # Lower-left soft white/silver ambient glow
            glow2 = QRadialGradient(QPointF(w * 0.15, h * 0.88), w * 0.65)
            glow2.setColorAt(0.0, QColor(255, 255, 255, 30))  # Luminous white contour
            glow2.setColorAt(0.5, QColor(255, 255, 255, 10))
            glow2.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(self.rect(), QBrush(glow2))

            # 4. Diagonal Glass Sheen (135-degree light bounce)
            glass_sheen = QLinearGradient(0, 0, w, h)
            glass_sheen.setColorAt(0.0, QColor(255, 255, 255, 36))
            glass_sheen.setColorAt(0.4, QColor(255, 255, 255, 12))
            glass_sheen.setColorAt(1.0, QColor(255, 255, 255, 16))
            p.fillRect(self.rect(), QBrush(glass_sheen))

            # 5. Micro-Dot Grid Matrix (monochrome white)
            dot_pen = QPen(QColor(255, 255, 255, 38))
            dot_pen.setWidthF(1.4)
            p.setPen(dot_pen)
            step = 18
            for x in range(18, int(w) - 10, step):
                for y in range(18, int(h) - 10, step):
                    p.drawPoint(QPointF(x, y))

            # 6. Top Specular Glint Line
            p.setPen(QPen(QColor(255, 255, 255, 105), 1.0))
            p.drawLine(QPointF(24, 1.2), QPointF(w - 24, 1.2))

            # 7. Luminous Specular Border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 120)) # Bright highlight top-left
            border_grad.setColorAt(0.45, QColor(255, 255, 255, 42))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 18))  # Soft bottom-right
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)

        else:
            # Light Mode Frosted Glass - Ambient black/grey/charcoal depth
            p.fillRect(self.rect(), QColor(255, 255, 255, 215))

            # Ambient black / smoky grey depth in top-right
            glow = QRadialGradient(QPointF(w * 0.85, h * 0.16), w * 0.75)
            glow.setColorAt(0.0, QColor(15, 23, 42, 28))   # Slate-black depth
            glow.setColorAt(0.5, QColor(100, 116, 139, 14)) # Neutral grey
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(self.rect(), QBrush(glow))

            # Lower-left soft charcoal contour
            glow2 = QRadialGradient(QPointF(w * 0.15, h * 0.88), w * 0.65)
            glow2.setColorAt(0.0, QColor(15, 23, 42, 20))
            glow2.setColorAt(0.5, QColor(100, 116, 139, 10))
            glow2.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillRect(self.rect(), QBrush(glow2))

            # Micro-dot grid in light mode (charcoal/slate grey)
            dot_pen = QPen(QColor(15, 23, 42, 22))
            dot_pen.setWidthF(1.3)
            p.setPen(dot_pen)
            step = 18
            for x in range(18, int(w) - 10, step):
                for y in range(18, int(h) - 10, step):
                    p.drawPoint(QPointF(x, y))

            # Specular top highlight
            p.setPen(QPen(QColor(255, 255, 255, 255), 1.0))
            p.drawLine(QPointF(24, 1.2), QPointF(w - 24, 1.2))

            # Outer crisp border
            p.setClipping(False)
            border_grad = QLinearGradient(0, 0, w, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            border_grad.setColorAt(0.5, QColor(15, 23, 42, 45))
            border_grad.setColorAt(1.0, QColor(15, 23, 42, 22))
            p.setPen(QPen(QBrush(border_grad), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 24.0, 24.0)


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
        if hasattr(self, "card") and hasattr(self.card, "set_theme"):
            self.card.set_theme(self.theme)
        self._update_logo()
        self._update_social_icons()
        self._apply_theme()
        self.update()

    def _update_social_icons(self):
        if not hasattr(self, "yt_btn") or not hasattr(self, "discord_btn"):
            return
        col = "#FFFFFF" if self.theme == "dark" else "#1D1D1F"
        yt_pix = render_svg_icon(YOUTUBE_SVG, 18, col)
        self.yt_btn.setIcon(QIcon(yt_pix))
        self.yt_btn.setIconSize(QSize(18, 18))

        dc_pix = render_svg_icon(DISCORD_SVG, 18, col)
        self.discord_btn.setIcon(QIcon(dc_pix))
        self.discord_btn.setIconSize(QSize(18, 18))

    def _open_youtube(self):
        if YOUTUBE_URL:
            try:
                os.startfile(YOUTUBE_URL)
            except Exception:
                pass

    def _open_discord(self):
        if DISCORD_URL:
            try:
                os.startfile(DISCORD_URL)
            except Exception:
                pass

    def _open_get_key(self):
        try:
            os.startfile(WEB_GET_KEY_URL)
        except Exception:
            pass

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

        self.brand_title = QLabel("Chess Stealth")
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

        # Right Pane: Luxury Frosted Glass Card
        self.card = LuxuryFrostedCard(theme=self.theme)
        self.card.setFixedWidth(410)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(14)

        # 1. Card Header: Key Login + Social Icons (YouTube & Discord)
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel("Key Login")
        self.title_lbl.setObjectName("ActivateTitle")
        head_row.addWidget(self.title_lbl)
        head_row.addStretch()

        social_box = QHBoxLayout()
        social_box.setSpacing(8)

        self.yt_btn = QPushButton()
        self.yt_btn.setObjectName("SocialIconBtn")
        self.yt_btn.setFixedSize(38, 38)
        self.yt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yt_btn.setToolTip("YouTube Channel")
        self.yt_btn.clicked.connect(self._open_youtube)
        social_box.addWidget(self.yt_btn)

        self.discord_btn = QPushButton()
        self.discord_btn.setObjectName("SocialIconBtn")
        self.discord_btn.setFixedSize(38, 38)
        self.discord_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discord_btn.setToolTip("Discord Server")
        self.discord_btn.clicked.connect(self._open_discord)
        social_box.addWidget(self.discord_btn)

        head_row.addLayout(social_box)
        card_layout.addLayout(head_row)

        # 2. License Key input section
        key_sec = QVBoxLayout()
        key_sec.setSpacing(6)
        self.key_sec_lbl = QLabel("License key")
        self.key_sec_lbl.setObjectName("FieldLabel")
        key_sec.addWidget(self.key_sec_lbl)

        self.key_input = QLineEdit()
        self.key_input.setObjectName("KeyInput")
        self.key_input.setPlaceholderText("Enter your license key...")
        self.key_input.returnPressed.connect(self.handle_activate)
        key_sec.addWidget(self.key_input)
        card_layout.addLayout(key_sec)

        # 3. Device ID (HWID) section
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
            self.copy_btn.setText("Copied!")
            self.copy_btn.setStyleSheet("background-color: #10B981 !important; color: #FFFFFF !important; border-color: #10B981 !important;")
            def _reset_copy():
                self.copy_btn.setText("Copy")
                self._apply_theme()
            QTimer.singleShot(1600, _reset_copy)
        self.copy_btn.clicked.connect(copy_hwid)
        hwid_row.addWidget(self.copy_btn)
        hwid_sec.addLayout(hwid_row)
        card_layout.addLayout(hwid_sec)

        card_layout.addSpacing(6)

        # 4. Action Bars: ACTIVATE & GET KEY
        actions_col = QVBoxLayout()
        actions_col.setSpacing(10)

        self.act_btn = QPushButton("ACTIVATE")
        self.act_btn.setObjectName("ActivateBarBtn")
        self.act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.act_btn.clicked.connect(self.handle_activate)
        actions_col.addWidget(self.act_btn)

        self.get_key_btn = QPushButton("GET KEY")
        self.get_key_btn.setObjectName("GetKeyBarBtn")
        self.get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.get_key_btn.clicked.connect(self._open_get_key)
        actions_col.addWidget(self.get_key_btn)

        card_layout.addLayout(actions_col)

        body_layout.addWidget(self.card)
        root.addLayout(body_layout)
        self._update_social_icons()

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
                background-color: transparent;
                border: none;
            }
            QLabel#ActivateTitle {
                color: #ffffff; font-size: 32px; font-weight: 800; letter-spacing: -0.02em;
            }
            QLabel#FieldLabel {
                color: #94A3B8; font-size: 12px; font-weight: 600;
            }
            QLineEdit#KeyInput {
                background-color: rgba(255, 255, 255, 0.06); color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 22px;
                padding: 0 18px; min-height: 44px; max-height: 44px;
                font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
            }
            QLineEdit#KeyInput:focus {
                border: 1.5px solid rgba(255, 255, 255, 0.55); background-color: rgba(255, 255, 255, 0.10);
            }
            QLabel#HwidDisplay {
                color: #E2E8F0; font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 20px;
                min-height: 40px; max-height: 40px;
                padding: 0 16px;
            }
            QPushButton#CopyPillBtn {
                background-color: rgba(255, 255, 255, 0.10); color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 20px;
                min-height: 40px; max-height: 40px;
                padding: 0 18px; font-size: 12px; font-weight: 700;
            }
            QPushButton#CopyPillBtn:hover {
                background-color: rgba(255, 255, 255, 0.22); color: #ffffff; border-color: rgba(255, 255, 255, 0.60);
            }
            QPushButton#CopyPillBtn:pressed {
                background-color: rgba(255, 255, 255, 0.12); color: #ffffff;
            }
            QPushButton#SocialIconBtn {
                background-color: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 19px;
            }
            QPushButton#SocialIconBtn:hover {
                background-color: rgba(255, 255, 255, 0.16);
                border-color: rgba(255, 255, 255, 0.40);
            }
            QPushButton#SocialIconBtn:pressed {
                background-color: rgba(255, 255, 255, 0.04);
            }
            
            QPushButton#ActivateBarBtn {
                background-color: #ffffff; color: #090B10;
                border: none; border-radius: 23px;
                min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.09em;
            }
            QPushButton#ActivateBarBtn:hover { background-color: #F1F5F9; }
            QPushButton#ActivateBarBtn:pressed { background-color: #E2E8F0; }

            QPushButton#GetKeyBarBtn {
                background-color: rgba(255, 255, 255, 0.06);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 23px;
                min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.09em;
            }
            QPushButton#GetKeyBarBtn:hover {
                background-color: rgba(255, 255, 255, 0.14);
                border-color: rgba(255, 255, 255, 0.38);
                color: #ffffff;
            }
            QPushButton#GetKeyBarBtn:pressed {
                background-color: rgba(255, 255, 255, 0.03);
            }
            """)
        else:
            self.setStyleSheet("""
            QWidget { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif; }
            QLabel#BrandTitle { color: #090B10; font-size: 14px; font-weight: 700; }
            QPushButton#WindowCtrlBtn, QPushButton#WindowCloseBtn {
                background-color: transparent;
                color: #64748B;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#WindowCtrlBtn:hover { background-color: rgba(0, 0, 0, 0.07); color: #090B10; }
            QPushButton#WindowCloseBtn:hover { background-color: rgba(239, 68, 68, 0.15); color: #EF4444; }
            
            QFrame#FrostedCard {
                background-color: transparent;
                border: none;
            }
            QLabel#ActivateTitle {
                color: #0F172A; font-size: 32px; font-weight: 800; letter-spacing: -0.02em;
            }
            QLabel#FieldLabel {
                color: #475569; font-size: 12px; font-weight: 700;
            }
            QLineEdit#KeyInput {
                background-color: #FFFFFF; color: #0F172A;
                border: 1.5px solid #CBD5E1; border-radius: 22px;
                padding: 0 18px; min-height: 44px; max-height: 44px;
                font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
            }
            QLineEdit#KeyInput:focus {
                border: 2px solid #0F172A; background-color: #FFFFFF;
            }
            QLabel#HwidDisplay {
                color: #0F172A; font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;
                background-color: #F1F5F9;
                border: 1.5px solid #CBD5E1; border-radius: 20px;
                min-height: 40px; max-height: 40px;
                padding: 0 16px;
            }
            QPushButton#CopyPillBtn {
                background-color: #0F172A; color: #FFFFFF;
                border: 1px solid #0F172A; border-radius: 20px;
                min-height: 40px; max-height: 40px;
                padding: 0 18px; font-size: 12px; font-weight: 700;
            }
            QPushButton#CopyPillBtn:hover {
                background-color: #334155; color: #FFFFFF; border-color: #334155;
            }
            QPushButton#CopyPillBtn:pressed {
                background-color: #0F172A; color: #FFFFFF;
            }
            QPushButton#SocialIconBtn {
                background-color: #FFFFFF;
                border: 1.5px solid #CBD5E1;
                border-radius: 19px;
            }
            QPushButton#SocialIconBtn:hover {
                background-color: #F8FAFC;
                border-color: #0F172A;
            }
            QPushButton#SocialIconBtn:pressed {
                background-color: #E2E8F0;
            }
            
            QPushButton#ActivateBarBtn {
                background-color: #0F172A; color: #FFFFFF;
                border: none; border-radius: 23px;
                min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.09em;
            }
            QPushButton#ActivateBarBtn:hover { background-color: #1E293B; }
            QPushButton#ActivateBarBtn:pressed { background-color: #334155; }

            QPushButton#GetKeyBarBtn {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1.5px solid #CBD5E1;
                border-radius: 23px;
                min-height: 46px; max-height: 46px; font-size: 13px; font-weight: 800; letter-spacing: 0.09em;
            }
            QPushButton#GetKeyBarBtn:hover {
                background-color: #F8FAFC;
                border-color: #0F172A;
                color: #0F172A;
            }
            QPushButton#GetKeyBarBtn:pressed {
                background-color: #E2E8F0;
            }
            """)

        if hasattr(self, "card"):
            shadow = QGraphicsDropShadowEffect(self.card)
            if self.theme == "dark":
                shadow.setBlurRadius(42)
                shadow.setOffset(0, 14)
                shadow.setColor(QColor(0, 0, 0, 180))
            else:
                shadow.setBlurRadius(36)
                shadow.setOffset(0, 12)
                shadow.setColor(QColor(0, 0, 0, 36))
            self.card.setGraphicsEffect(shadow)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_has_faded_in", False):
            self._has_faded_in = True
            self.setWindowOpacity(0.0)
            anim = QPropertyAnimation(self, b"windowOpacity")
            anim.setDuration(280)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._in_anim = anim
            anim.start()

    def handle_activate(self):
        k = self.key_input.text().strip()
        if not k:
            dlg = ModernAlertDialog("Missing Key", "Please enter your license key.", is_dark=(self.theme == "dark"), parent=self)
            dlg.exec()
            return

        self.act_btn.setEnabled(False)
        self.act_btn.setText("VERIFYING...")

        def _do_verify():
            valid, msg = activate_or_verify_key(API_BASE_URL, k, self.hwid)
            if valid:
                self._activated = True
                try:
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        f.write(k)
                except Exception:
                    pass
                self.act_btn.setText("ACCESS GRANTED ✓")
                self.act_btn.setStyleSheet("""
                    QPushButton#ActivateBarBtn {
                        background-color: #10B981 !important;
                        color: #FFFFFF !important;
                        border: none;
                        border-radius: 12px;
                        min-height: 48px;
                        font-size: 13px;
                        font-weight: 800;
                        letter-spacing: 0.08em;
                    }
                """)
                # Smooth cross-fade transition to Control Center
                self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity")
                self._fade_out_anim.setDuration(280)
                self._fade_out_anim.setStartValue(1.0)
                self._fade_out_anim.setEndValue(0.0)
                self._fade_out_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
                def _on_faded():
                    self.hide()
                    self.close()
                    if self.on_activated_cb:
                        self.on_activated_cb(k)
                self._fade_out_anim.finished.connect(_on_faded)
                self._fade_out_anim.start()
            else:
                self.act_btn.setEnabled(True)
                self.act_btn.setText("ACTIVATE")
                self._apply_theme()
                dlg = ModernAlertDialog("Invalid Key", "The license key entered is invalid or has expired.", is_dark=(self.theme == "dark"), parent=self)
                dlg.exec()

        QTimer.singleShot(60, _do_verify)


def main():
    global _CURRENT_THEME
    if sys.platform == "win32" and "PYTEST_CURRENT_TEST" not in os.environ:
        my_pid = os.getpid()
        parent_pid = os.getppid()
        try:
            subprocess.run(
                [
                    "taskkill",
                    "/F",
                    "/FI",
                    "IMAGENAME eq ChessPro.exe",
                    "/FI",
                    f"PID ne {my_pid}",
                    "/FI",
                    f"PID ne {parent_pid}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                timeout=3,
            )
            time.sleep(0.15)
        except Exception:
            pass

        try:
            from license_core.watchdog import start_watchdog
            start_watchdog(poll_interval=1.0)
        except Exception:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    ctrl_window = None

    def open_control_center(k: str, hwid_val: str):
        nonlocal ctrl_window
        ctrl_window = ControlCenterWindow(k, hwid_val)
        _ACTIVE_WINDOWS.append(ctrl_window)
        ctrl_window.setWindowOpacity(0.0)
        ctrl_window.show()
        fade_in = QPropertyAnimation(ctrl_window, b"windowOpacity")
        fade_in.setDuration(220)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        ctrl_window._fade_in = fade_in
        fade_in.start()

    splash = LuxurySplashScreen()
    _ACTIVE_WINDOWS.append(splash)
    splash.start(auto_step=False)

    hwid = ""
    saved_key = ""
    url_scheme_key = ""

    def step1_engine():
        splash.update_progress(25, "Loading engine...")
        try:
            install_scripts_and_extension()
            register_custom_url_scheme("chesspro")
        except Exception:
            pass
        QTimer.singleShot(40, step2_services)

    def step2_services():
        splash.update_progress(55, "Starting services...")
        if start_background_api_server is not None:
            try:
                start_background_api_server("127.0.0.1", 8766)
            except Exception:
                pass
        QTimer.singleShot(40, step3_license)

    def step3_license():
        nonlocal hwid, saved_key, url_scheme_key
        splash.update_progress(85, "Verifying license...")
        try:
            hwid = get_hwid()
            url_scheme_key = parse_url_scheme_arg(sys.argv)
            saved_key = url_scheme_key or ""
            if not saved_key and os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        saved_key = f.read().strip()
                except Exception:
                    pass
        except Exception:
            pass
        QTimer.singleShot(40, step4_ready)

    def step4_ready():
        splash.update_progress(100, "Ready")

        is_active = False
        if saved_key and hwid:
            try:
                valid, _ = activate_or_verify_key(API_BASE_URL, saved_key, hwid)
                if valid:
                    is_active = True
            except Exception:
                pass

        def _launch_next():
            splash.close()
            if is_active:
                open_control_center(saved_key, hwid)
            else:
                act_win = ActivationWindow(hwid, on_activated_cb=lambda k: open_control_center(k, hwid))
                _ACTIVE_WINDOWS.append(act_win)
                act_win.setWindowOpacity(0.0)
                act_win.show()
                fade_in = QPropertyAnimation(act_win, b"windowOpacity")
                fade_in.setDuration(220)
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
                act_win._fade_in = fade_in
                fade_in.start()

                if url_scheme_key:
                    act_win.key_input.setText(url_scheme_key)
                    QTimer.singleShot(250, act_win.handle_activate)

        QTimer.singleShot(120, _launch_next)

    QTimer.singleShot(20, step1_engine)
    app.exec()


if __name__ == "__main__":
    main()
