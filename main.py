import ctypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
import urllib.parse

from api.server import start_background_api_server
from license_core.hwid import get_hwid
from license_core.url_scheme import parse_url_scheme_arg, register_custom_url_scheme
from license_core.verifier import activate_or_verify_key, derive_arrow_scale_factor

# ================= CẤU HÌNH HỆ THỐNG =================
API_BASE_URL = os.environ.get("CHESSPRO_API_URL", "http://127.0.0.1:8766")
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

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", "black")
    root.attributes("-alpha", 0.86)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{sw}x{sh}+0+0")

    canvas = tk.Canvas(root, width=sw, height=sh, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    if not hwnd:
        hwnd = root.winfo_id()

    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(
        hwnd,
        GWL_EXSTYLE,
        ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
    )
    ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

    def render_loop():
        canvas.delete("all")
        now = time.time()

        # [CHỐNG CRACK RẢI RÁC] Hệ số tỷ lệ lấy trực tiếp từ việc xác thực chữ ký Ed25519 trong RAM
        gate_scale = derive_arrow_scale_factor()

        if gate_scale > 0.0 and arrow_state["show"] and (now - arrow_state["last_seen"] <= 1.8):
            x1 = arrow_state["x1"]
            y1 = arrow_state["y1"] + arrow_state["offset_y"]
            x2 = arrow_state["x2"]
            y2 = arrow_state["y2"] + arrow_state["offset_y"]
            sq = max(32, arrow_state["size"]) * gate_scale

            dx = x2 - x1
            dy = y2 - y1
            dist = math.hypot(dx, dy)
            if dist > 6:
                ux, uy = dx / dist, dy / dist
                px, py = -uy, ux

                shaft_w = sq * 0.22
                head_w = sq * 0.50
                head_l = sq * 0.38
                offset = sq * 0.12

                sx, sy = x1 + ux * offset, y1 + uy * offset
                nx, ny = x2 - ux * head_l, y2 - uy * head_l

                pts = [
                    sx + px * (shaft_w / 2),
                    sy + py * (shaft_w / 2),
                    nx + px * (shaft_w / 2),
                    ny + py * (shaft_w / 2),
                    nx + px * (head_w / 2),
                    ny + py * (head_w / 2),
                    x2,
                    y2,
                    nx - px * (head_w / 2),
                    ny - py * (head_w / 2),
                    nx - px * (shaft_w / 2),
                    ny - py * (shaft_w / 2),
                    sx - px * (shaft_w / 2),
                    sy - py * (shaft_w / 2),
                ]
                canvas.create_polygon(pts, fill="#ffaa00", outline="")

        if (ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) and (
            ctypes.windll.user32.GetAsyncKeyState(0x51) & 0x8000
        ):
            root.destroy()
            sys.exit(0)

        root.after(20, render_loop)

    render_loop()
    root.mainloop()


# ================= POPUP CHỌN TRÌNH DUYỆT =================
def show_browser_selector(license_info: str, active_key: str, hwid: str):
    sel_root = tk.Tk()
    sel_root.title("Chess Stealth Pro - Chon Trinh Duyet")
    sel_root.geometry("380x270")
    sel_root.configure(bg="#18181b")
    sel_root.resizable(False, False)
    sel_root.eval("tk::PlaceWindow . center")

    tk.Label(
        sel_root,
        text="CHỌN TRÌNH DUYỆT SỬ DỤNG",
        fg="#f59e0b",
        bg="#18181b",
        font=("Segoe UI", 12, "bold"),
    ).pack(pady=(16, 4))

    tk.Label(
        sel_root,
        text=f"{license_info}",
        fg="#22c55e",
        bg="#18181b",
        font=("Segoe UI", 9),
    ).pack(pady=(0, 10))

    browser_var = tk.StringVar(value="min")

    options_frame = tk.Frame(sel_root, bg="#27272a", padx=16, pady=10)
    options_frame.pack(fill="x", padx=24)

    browsers = [
        ("Min Browser (Tự động cài & mở)", "min"),
        ("Brave Browser (Tự động nạp & mở)", "brave"),
        ("Google Chrome (Tự động nạp & mở)", "chrome"),
        ("Chỉ bật Overlay (Đã mở sẵn trình duyệt)", "other"),
    ]

    for label_text, val in browsers:
        tk.Radiobutton(
            options_frame,
            text=label_text,
            variable=browser_var,
            value=val,
            fg="#f4f4f5",
            bg="#27272a",
            selectcolor="#18181b",
            activebackground="#27272a",
            activeforeground="#f59e0b",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=2)

    def start_app():
        chosen = browser_var.get()
        sel_root.destroy()
        launch_stealth_engine(chosen, active_key, hwid)

    tk.Button(
        sel_root,
        text="BẮT ĐẦU (ALT+X: ẨN/HIỆN | ALT+Q: THOÁT)",
        command=start_app,
        bg="#f59e0b",
        fg="#18181b",
        activebackground="#d97706",
        activeforeground="#18181b",
        font=("Segoe UI", 9, "bold"),
        width=38,
        relief="flat",
        cursor="hand2",
        pady=7,
    ).pack(pady=14)

    sel_root.mainloop()


# ================= POPUP BẮT BUỘC NHẬP KEY KHI MỞ .EXE =================
def main():
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

    root = tk.Tk()
    root.title("Chess Stealth Pro - Kich Hoat Key")
    root.geometry("410x280")
    root.configure(bg="#18181b")
    root.resizable(False, False)
    root.eval("tk::PlaceWindow . center")

    tk.Label(
        root,
        text="CHESS STEALTH PRO (Ed25519 Verified)",
        fg="#f59e0b",
        bg="#18181b",
        font=("Segoe UI", 12, "bold"),
    ).pack(pady=(16, 4))

    hwid_frame = tk.Frame(root, bg="#18181b")
    hwid_frame.pack(pady=(0, 8))

    tk.Label(
        hwid_frame,
        text=f"HWID: {hwid}",
        fg="#a1a1aa",
        bg="#18181b",
        font=("Consolas", 9),
    ).pack(side="left", padx=(0, 6))

    def copy_hwid():
        root.clipboard_clear()
        root.clipboard_append(hwid)
        copy_btn.config(text="Đã chép", fg="#22c55e")

    copy_btn = tk.Button(
        hwid_frame,
        text="Copy HWID",
        command=copy_hwid,
        bg="#27272a",
        fg="#e4e4e7",
        font=("Segoe UI", 8),
        relief="flat",
        padx=6,
        pady=1,
        cursor="hand2",
    )
    copy_btn.pack(side="left")

    tk.Label(
        root,
        text="Nhập License Key (24h / 30 Ngày / Lifetime):",
        fg="#e4e4e7",
        bg="#18181b",
        font=("Segoe UI", 9),
    ).pack()

    key_entry = tk.Entry(
        root,
        width=32,
        font=("Consolas", 11, "bold"),
        bg="#27272a",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
        justify="center",
    )
    key_entry.pack(pady=8, ipady=6)
    if saved_key:
        key_entry.insert(0, saved_key)
    key_entry.focus_set()

    def handle_activate(event=None):
        k = key_entry.get().strip()
        if not k:
            messagebox.showwarning("Thiếu Key", "Vui lòng nhập mã License Key!")
            return

        valid, msg = activate_or_verify_key(API_BASE_URL, k, hwid)
        if valid:
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(k)
            except Exception:
                pass
            root.destroy()
            show_browser_selector(msg, k, hwid)
        else:
            messagebox.showerror("Xác thực thất bại", msg)

    root.bind("<Return>", handle_activate)

    tk.Button(
        root,
        text="XÁC NHẬN & TIẾP TỤC",
        command=handle_activate,
        bg="#22c55e",
        fg="#ffffff",
        activebackground="#16a34a",
        activeforeground="#ffffff",
        font=("Segoe UI", 10, "bold"),
        width=32,
        relief="flat",
        cursor="hand2",
        pady=6,
    ).pack(pady=(4, 10))

    sub_frame = tk.Frame(root, bg="#18181b")
    sub_frame.pack(pady=2)

    def open_dynamic_get_key():
        target_url = f"{API_BASE_URL.rstrip('/')}/get-link?hwid={urllib.parse.quote(hwid)}"
        os.startfile(target_url)

    tk.Button(
        sub_frame,
        text="Lấy Key 24h (Vượt Link)",
        command=open_dynamic_get_key,
        bg="#27272a",
        fg="#f59e0b",
        font=("Segoe UI", 9),
        width=18,
        relief="flat",
        cursor="hand2",
        pady=4,
    ).grid(row=0, column=0, padx=4)

    tk.Button(
        sub_frame,
        text="Mua 30 Ngày / Lifetime",
        command=lambda: os.startfile(BUY_LIFE_URL),
        bg="#27272a",
        fg="#38bdf8",
        font=("Segoe UI", 9),
        width=18,
        relief="flat",
        cursor="hand2",
        pady=4,
    ).grid(row=0, column=1, padx=4)

    # Nếu được gọi tự động từ trình duyệt qua `chesspro://activate?key=XXX`, tự kích hoạt ngay
    if url_scheme_key:
        root.after(250, handle_activate)

    root.mainloop()


if __name__ == "__main__":
    main()
