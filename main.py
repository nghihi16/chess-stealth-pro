import base64
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

from PySide6.QtCore import QByteArray, QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
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

_ACTIVE_WINDOWS = []
_CURRENT_THEME = "dark"

# ================= IN-BROWSER GUI + STEALTH OVERLAY BRIDGE =================
STEALTH_USERSCRIPT_CODE = (
    r"""// ==UserScript==
// @name         Chess Stealth Pro — In-Browser GUI & Stealth Bridge
// @match        *://www.chess.com/*
// @match        *://chess.com/*
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  const PAWN_LOGO_DATA_URI = """
    + json.dumps(LOGOS["pawn"])
    + r""";

  function initChessStealth() {
    if (document.getElementById('ca-panel-container')) return;
    if (!document.body) {
      setTimeout(initChessStealth, 100);
      return;
    }

    let isEnabled = true;
    let isMinimized = false;
    let isPanelHidden = false;
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

    // Floating GUI Panel on Browser (Bottom-Right)
    const panel = document.createElement('div');
    panel.id = 'ca-panel-container';
    panel.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;
      background: rgba(11, 15, 25, 0.94); backdrop-filter: blur(14px);
      color: #f8fafc; padding: 12px 14px; border-radius: 14px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: 0 12px 32px rgba(0,0,0,0.75), 0 0 18px rgba(34,211,238,0.18);
      border: 1px solid rgba(34, 211, 238, 0.35); width: 248px;
      user-select: none; transition: all 0.2s ease;
    `;
    panel.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; align-items:center; gap:8px;">
          <img src="${PAWN_LOGO_DATA_URI}" style="width:28px; height:28px; object-fit:contain; filter:drop-shadow(0 0 8px rgba(34,211,238,0.7));" alt="" />
          <div style="display:flex; flex-direction:column; line-height:1.1;">
            <span style="font-weight:800; color:#f8fafc; font-size:12px; letter-spacing:0.16em;">CHESS</span>
            <span style="font-weight:800; color:#22d3ee; font-size:9px; letter-spacing:0.24em;">STEALTH</span>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <button id="ca-toggle-btn" style="background:#10b981; color:#060911; border:none; padding:4px 10px; border-radius:6px; font-size:11px; font-weight:800; cursor:pointer;">
            ON
          </button>
          <button id="ca-min-btn" style="background:#1e293b; color:#cbd5e1; border:1px solid #334155; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:700; cursor:pointer;" title="Minimize">
            _
          </button>
        </div>
      </div>

      <div id="ca-body" style="margin-top:10px; border-top:1px solid rgba(148,163,184,0.18); padding-top:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:12px; color:#cbd5e1;">
          <span>Side:</span>
          <select id="ca-my-color" style="background:#161e2e; color:#f8fafc; border:1px solid #334155; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:600; outline:none;">
            <option value="auto" selected>Auto (Board View)</option>
            <option value="w">White</option>
            <option value="b">Black</option>
          </select>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:12px; color:#cbd5e1;">
          <span>Arrow:</span>
          <select id="ca-arrow-color" style="background:#161e2e; color:#f8fafc; border:1px solid #334155; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:600; outline:none;">
            <option value="rgba(255, 170, 0, 0.88)" selected>Orange</option>
            <option value="rgba(34, 211, 238, 0.88)">Cyan</option>
            <option value="rgba(52, 211, 153, 0.88)">Green</option>
            <option value="rgba(248, 113, 113, 0.88)">Red</option>
            <option value="transparent">Stealth Overlay Only</option>
          </select>
        </div>
        <div id="ca-status" style="font-size:12px; color:#34d399; font-weight:700; margin-top:6px; display:flex; justify-content:space-between; align-items:center;">
          <span>Ready (Alt+X)</span>
        </div>
      </div>
    `;
    document.body.appendChild(panel);

    function updateStatus(html) {
      const el = document.getElementById('ca-status');
      if (el) el.innerHTML = html;
    }

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

    function clearArrow() {
      const oldSvg = document.getElementById('ca-arrow-overlay');
      if (oldSvg) oldSvg.remove();
    }

    function drawChessComArrow(boardEl, move) {
      if (!isEnabled || !boardEl || !move || move.length < 4) return;
      const arrowColor = document.getElementById('ca-arrow-color')?.value || 'rgba(255, 170, 0, 0.88)';
      if (arrowColor === 'transparent') {
        clearArrow();
        return;
      }

      let svg = document.getElementById('ca-arrow-overlay');
      if (!svg || !boardEl.contains(svg)) {
        clearArrow();
        svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.id = 'ca-arrow-overlay';
        svg.setAttribute('viewBox', '0 0 100 100');
        svg.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:999;';
        boardEl.appendChild(svg);
      }

      const isFlipped = boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped');
      function toCoords(sq) {
        const file = sq.charCodeAt(0) - 97;
        const rank = parseInt(sq[1], 10) - 1;
        const x = isFlipped ? (7 - file) + 0.5 : file + 0.5;
        const y = isFlipped ? rank + 0.5 : (7 - rank) + 0.5;
        return { x: x * 12.5, y: y * 12.5 };
      }

      const from = toCoords(move.substring(0, 2));
      const to = toCoords(move.substring(2, 4));
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const len = Math.hypot(dx, dy);
      if (len === 0) return;

      const ux = dx / len, uy = dy / len;
      const px = -uy, py = ux;

      const shaftWidth = 2.75;
      const headWidth = 6.2;
      const headLength = 4.8;
      const startOffset = 1.5;

      const startX = from.x + ux * startOffset;
      const startY = from.y + uy * startOffset;
      const neckX = to.x - ux * headLength;
      const neckY = to.y - uy * headLength;

      const p1 = `${startX + px * (shaftWidth / 2)},${startY + py * (shaftWidth / 2)}`;
      const p2 = `${neckX + px * (shaftWidth / 2)},${neckY + py * (shaftWidth / 2)}`;
      const p3 = `${neckX + px * (headWidth / 2)},${neckY + py * (headWidth / 2)}`;
      const p4 = `${to.x},${to.y}`;
      const p5 = `${neckX - px * (headWidth / 2)},${neckY - py * (headWidth / 2)}`;
      const p6 = `${neckX - px * (shaftWidth / 2)},${neckY - py * (shaftWidth / 2)}`;
      const p7 = `${startX - px * (shaftWidth / 2)},${startY - py * (shaftWidth / 2)}`;

      svg.innerHTML = `<polygon points="${p1} ${p2} ${p3} ${p4} ${p5} ${p6} ${p7}" fill="${arrowColor}" />`;
    }

    function updateOverlayCoords(boardEl, move) {
      if (!isEnabled || document.hidden || !boardEl || !move || move.length < 4) {
        sendToOverlay({ show: false });
        return;
      }

      drawChessComArrow(boardEl, move);

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
            const depthMatch = line.match(/depth (\d+)/);
            if (pvMatch && pvMatch[1]) {
              currentBestMove = pvMatch[1];
              const depth = depthMatch ? depthMatch[1] : '?';
              const boardEl = document.querySelector('wc-chess-board, .board');
              if (boardEl) {
                updateOverlayCoords(boardEl, currentBestMove);
                updateStatus(`<span style="color:#22d3ee; font-size:13px;">${currentBestMove.substring(0, 2).toUpperCase()} &rarr; ${currentBestMove.substring(2, 4).toUpperCase()}</span> <span style="font-size:11px; color:#94a3b8;">Depth ${depth}</span>`);
              }
            }
          }

          if (line.startsWith('bestmove')) {
            const move = line.split(' ')[1];
            if (move && move !== '(none)' && move.length >= 4) {
              currentBestMove = move;
              const boardEl = document.querySelector('wc-chess-board, .board');
              if (boardEl) {
                updateOverlayCoords(boardEl, currentBestMove);
                updateStatus(`<span style="color:#34d399; font-size:13px;">${move.substring(0, 2).toUpperCase()} &rarr; ${move.substring(2, 4).toUpperCase()}</span> <span style="font-size:11px; color:#10b981;">Best</span>`);
              }
            }
          }
        };

        stockfishWorker.postMessage('uci');
        stockfishWorker.postMessage('setoption name Skill Level value 20');
        stockfishWorker.postMessage('isready');
      } catch (_) {}
    }

    setupEngine();

    function toggleAssistant() {
      isEnabled = !isEnabled;
      const btn = document.getElementById('ca-toggle-btn');
      if (isEnabled) {
        btn.innerText = 'ON';
        btn.style.background = '#10b981';
        btn.style.color = '#060911';
        lastBoardKey = '';
        updateStatus('Active');
      } else {
        btn.innerText = 'OFF';
        btn.style.background = '#ef4444';
        btn.style.color = '#ffffff';
        if (stockfishWorker) stockfishWorker.postMessage('stop');
        currentBestMove = null;
        clearArrow();
        sendToOverlay({ show: false });
        updateStatus('<span style="color:#94a3b8;">Paused</span>');
      }
    }

    document.getElementById('ca-toggle-btn').addEventListener('click', toggleAssistant);

    document.getElementById('ca-min-btn').addEventListener('click', () => {
      isMinimized = !isMinimized;
      const bodyEl = document.getElementById('ca-body');
      const minBtn = document.getElementById('ca-min-btn');
      if (isMinimized) {
        bodyEl.style.display = 'none';
        minBtn.innerText = '+';
        panel.style.width = '205px';
      } else {
        bodyEl.style.display = 'block';
        minBtn.innerText = '_';
        panel.style.width = '248px';
      }
    });

    document.getElementById('ca-arrow-color').addEventListener('change', () => {
      const boardEl = document.querySelector('wc-chess-board, .board');
      if (boardEl && currentBestMove) drawChessComArrow(boardEl, currentBestMove);
    });

    document.getElementById('ca-my-color').addEventListener('change', () => {
      lastBoardKey = '';
    });

    window.addEventListener('keydown', (e) => {
      if (e.altKey && e.key.toLowerCase() === 'x') {
        toggleAssistant();
      } else if (e.altKey && e.key.toLowerCase() === 'h') {
        isPanelHidden = !isPanelHidden;
        panel.style.display = isPanelHidden ? 'none' : 'block';
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
      const manualSide = document.getElementById('ca-my-color')?.value || 'auto';
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
  }

  if (document.body) initChessStealth();
  else window.addEventListener('DOMContentLoaded', initChessStealth);
})();
"""
)


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
            "name": "Chess Stealth Pro",
            "version": "2.1.0",
            "description": "In-browser Stockfish GUI and Windows stealth overlay bridge.",
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


def setup_and_launch_browser(browser_type: str):
    ext_dir = install_scripts_and_extension()
    if browser_type == "other":
        return

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


def launch_stealth_engine(browser_type: str, active_key: str, hwid: str):
    setup_and_launch_browser(browser_type)

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

    overlay = QtStealthOverlay()
    _ACTIVE_WINDOWS.append(overlay)
    overlay.showFullScreen()


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
            min-height: 40px; font-size: 12px; font-weight: 600; padding: 0 12px;
        }
        QPushButton#SecondaryBtn:hover { border: 1px solid #0284c7; background-color: #f8fafc; }
        QPushButton.BrowserCard {
            background-color: #f8fafc; color: #0f172a;
            border: 1px solid #cbd5e1; border-radius: 12px;
            min-height: 48px; font-size: 12px; font-weight: 700;
            text-align: left; padding: 6px 12px;
        }
        QPushButton.BrowserCard:hover { border: 1px solid #0284c7; background-color: #eef2f6; }
        QPushButton.BrowserCard[selected="true"] {
            border: 2px solid #0284c7; background-color: #e0f2fe;
        }
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
    QPushButton#PrimaryBtn {
        background-color: #22d3ee; color: #060911;
        border: none; border-radius: 10px;
        min-height: 44px; font-size: 13px; font-weight: 800;
    }
    QPushButton#PrimaryBtn:hover { background-color: #38bdf8; }
    QPushButton#SecondaryBtn {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 10px;
        min-height: 40px; font-size: 12px; font-weight: 600; padding: 0 12px;
    }
    QPushButton#SecondaryBtn:hover { border: 1px solid #22d3ee; background-color: #1e293b; }
    QPushButton.BrowserCard {
        background-color: #161e2e; color: #f8fafc;
        border: 1px solid #283548; border-radius: 12px;
        min-height: 48px; font-size: 12px; font-weight: 700;
        text-align: left; padding: 6px 12px;
    }
    QPushButton.BrowserCard:hover { border: 1px solid #22d3ee; background-color: #1e293b; }
    QPushButton.BrowserCard[selected="true"] {
        border: 2px solid #22d3ee; background-color: #112a38;
    }
    """


def show_browser_selector(_license_info: str, active_key: str, hwid: str):
    global _CURRENT_THEME
    win = QWidget()
    _ACTIVE_WINDOWS.append(win)
    win.setObjectName("Root")
    win.setWindowTitle("CHESS STEALTH — Select Browser")
    win.setWindowIcon(app_icon())
    win.setFixedSize(460, 400)
    win.setStyleSheet(_build_qss(_CURRENT_THEME))

    layout = QVBoxLayout(win)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(14)

    top = QHBoxLayout()
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
    grid = QGridLayout(card)
    grid.setContentsMargins(14, 14, 14, 14)
    grid.setSpacing(10)

    browsers = [
        ("Google Chrome", "chrome", "chrome"),
        ("Microsoft Edge", "edge", "edge"),
        ("Brave Browser", "brave", "brave"),
        ("Cốc Cốc", "coccoc", "coccoc"),
        ("Opera / GX", "opera", "opera"),
        ("Mozilla Firefox", "firefox", "firefox"),
        ("Min Browser", "min", "min"),
        ("Overlay Only", "other", "pawn"),
    ]

    default_val = "chrome"
    for cand in ("chrome", "brave", "edge", "coccoc", "min"):
        if find_browser_exe(cand):
            default_val = cand
            break

    selected_browser = {"val": default_val}
    buttons: dict[str, QPushButton] = {}

    def select_b(val: str):
        selected_browser["val"] = val
        for k, b in buttons.items():
            b.setProperty("selected", "true" if k == val else "false")
            b.style().unpolish(b)
            b.style().polish(b)

    for idx, (label_text, val, logo_key) in enumerate(browsers):
        btn = QPushButton(f"  {label_text}")
        btn.setProperty("class", "BrowserCard")
        btn.setProperty("selected", "true" if val == default_val else "false")
        btn.setIcon(QIcon(pixmap_from_data_uri(LOGOS[logo_key], 24)))
        btn.setIconSize(QSize(24, 24))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, v=val: select_b(v))
        buttons[val] = btn
        grid.addWidget(btn, idx // 2, idx % 2)

    layout.addWidget(card)

    start_btn = QPushButton("LAUNCH CHESS STEALTH")
    start_btn.setObjectName("PrimaryBtn")
    start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def on_start():
        chosen = selected_browser["val"]
        win.hide()
        launch_stealth_engine(chosen, active_key, hwid)

    start_btn.clicked.connect(on_start)
    layout.addWidget(start_btn)

    win.show()


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
    if saved_key:
        key_input.setText(saved_key)
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
            win.hide()
            show_browser_selector(msg, k, hwid)
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
