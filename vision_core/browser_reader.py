"""Zero-extension Chromium DevTools Protocol (CDP) direct DOM board reader."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request

from vision_core.chess_rules import ChessBoardState


_READ_BOARD_JS = r"""
(() => {
  const boards = document.querySelectorAll('wc-chess-board, chess-board, #board-single, cg-board, .board');
  let boardEl = null;
  for (const el of boards) {
    const r = el.getBoundingClientRect();
    if (r && r.width >= 120 && r.height >= 120 && Math.abs(r.width - r.height) <= 24) {
      boardEl = el;
      break;
    }
  }
  if (!boardEl && boards.length) boardEl = boards[0];
  if (!boardEl) return null;

  const rect = boardEl.getBoundingClientRect();
  if (!rect || rect.width < 120 || rect.height < 120) return null;

  let flipped = Boolean(
    (boardEl.classList && boardEl.classList.contains('flipped')) ||
    boardEl.getAttribute('flipped') === 'true' ||
    boardEl.hasAttribute('flipped') ||
    (boardEl.closest && boardEl.closest('.orientation-black'))
  );

  let fen = '';
  let turn = '';
  let mySide = '';
  let castling = 'KQkq';
  let ep = '-';

  try {
    const g = boardEl.game;
    if (g) {
      if (typeof g.getFEN === 'function') {
        const gf = g.getFEN();
        if (typeof gf === 'string' && gf.includes('/')) fen = gf.trim();
      }
      if (!fen && typeof g.getFen === 'function') {
        const gf = g.getFen();
        if (typeof gf === 'string' && gf.includes('/')) fen = gf.trim();
      }
      if (typeof g.getTurn === 'function') {
        const t = g.getTurn();
        if (t === 1 || t === 'w' || t === 'white') turn = 'w';
        else if (t === 2 || t === 'b' || t === 'black') turn = 'b';
      }
      if (typeof g.getPlayingAs === 'function') {
        const p = g.getPlayingAs();
        if (p === 1 || p === 'w' || p === 'white') mySide = 'w';
        else if (p === 2 || p === 'b' || p === 'black') mySide = 'b';
      }
      if (typeof g.getPositionInfo === 'function') {
        const info = g.getPositionInfo();
        if (info && info.flipped !== undefined) flipped = Boolean(info.flipped);
      }
    }
  } catch (_e) {}

  let hasWK = false, hasBK = false;
  const grid = Array.from({ length: 8 }, () => Array(8).fill(''));
  let domCount = 0;

  // 1. Chess.com .piece.wp.square-52 DOM pieces
  const root = boardEl.shadowRoot || boardEl;
  const ccPieces = root.querySelectorAll('.piece, [class*="piece "]');
  const sqSamples = [];
  for (const pel of ccPieces) {
    const cl = pel.classList;
    if (!cl || cl.contains('animating')) continue;
    let pt = '', sqStr = '';
    for (const cls of cl) {
      if (/^[wb][prnbqk]$/.test(cls)) pt = cls;
      else if (/^square-\d\d$/.test(cls)) sqStr = cls.slice(7);
    }
    if (!pt || !sqStr) continue;
    const file = parseInt(sqStr[0], 10) - 1;
    const rank = parseInt(sqStr[1], 10) - 1;
    if (file < 0 || file > 7 || rank < 0 || rank > 7) continue;
    const ch = pt[0] === 'w' ? pt[1].toUpperCase() : pt[1].toLowerCase();
    grid[7 - rank][file] = ch;
    domCount++;
    if (ch === 'K') hasWK = true;
    if (ch === 'k') hasBK = true;
    if (!cl.contains('dragging')) {
      const pr = pel.getBoundingClientRect();
      if (pr.width > 12 && Math.abs(pr.width - pr.height) <= 4) {
        sqSamples.push({ file, rank, rect: pr });
      }
    }
  }

  // Verify flipped directly from DOM piece screen positions when >= 2 samples differ in file/rank
  if (sqSamples.length >= 2) {
    const s0 = sqSamples[0];
    for (let i = 1; i < sqSamples.length; i++) {
      const s1 = sqSamples[i];
      if (s1.rank !== s0.rank && Math.abs(s1.rect.top - s0.rect.top) > 10) {
        flipped = ((s1.rect.top - s0.rect.top) * (s1.rank - s0.rank)) > 0;
        break;
      }
      if (s1.file !== s0.file && Math.abs(s1.rect.left - s0.rect.left) > 10) {
        flipped = ((s1.rect.left - s0.rect.left) * (s1.file - s0.file)) < 0;
        break;
      }
    }
  }

  // 2. Lichess cg-board fallback (<piece class="white knight">)
  if (domCount === 0 && boardEl.tagName && boardEl.tagName.toLowerCase() === 'cg-board') {
    const sqSize = rect.width / 8.0;
    const kindMap = { pawn: 'p', knight: 'n', bishop: 'b', rook: 'r', queen: 'q', king: 'k' };
    for (const pel of boardEl.querySelectorAll('piece')) {
      const cl = pel.classList;
      if (!cl || cl.contains('dragging') || cl.contains('ghost')) continue;
      const isW = cl.contains('white'), isB = cl.contains('black');
      if (!isW && !isB) continue;
      let kCh = '';
      for (const [kName, ch] of Object.entries(kindMap)) {
        if (cl.contains(kName)) { kCh = ch; break; }
      }
      if (!kCh) continue;
      const pr = pel.getBoundingClientRect();
      if (pr.width < 12) continue;
      const col = Math.round((pr.left - rect.left) / sqSize);
      const row = Math.round((pr.top - rect.top) / sqSize);
      if (col < 0 || col > 7 || row < 0 || row > 7) continue;
      const file = flipped ? (7 - col) : col;
      const rank = flipped ? row : (7 - row);
      const ch = isW ? kCh.toUpperCase() : kCh;
      grid[7 - rank][file] = ch;
      domCount++;
      if (ch === 'K') hasWK = true;
      if (ch === 'k') hasBK = true;
    }
  }

  if (!fen) {
    if (!hasWK || !hasBK) return null;
    const ranksOut = grid.map(row => {
      let emp = 0, out = '';
      for (const c of row) {
        if (!c) { emp++; }
        else { if (emp) { out += emp; emp = 0; } out += c; }
      }
      if (emp) out += emp;
      return out;
    });
    if (!turn) {
      // Infer ply parity from move list count when boardEl.game isn't attached
      const nodes = document.querySelectorAll('.move-list-wrapper .node, .vertical-move-list .node, l4x kwdb');
      if (nodes && nodes.length > 0) turn = (nodes.length % 2 === 1) ? 'b' : 'w';
    }
    const cList = [];
    if (grid[7][4] === 'K' && grid[7][7] === 'R') cList.push('K');
    if (grid[7][4] === 'K' && grid[7][0] === 'R') cList.push('Q');
    if (grid[0][4] === 'k' && grid[0][7] === 'r') cList.push('k');
    if (grid[0][4] === 'k' && grid[0][0] === 'r') cList.push('q');
    castling = cList.length ? cList.join('') : '-';
    const useTurn = turn || (flipped ? 'b' : 'w');
    fen = `${ranksOut.join('/')} ${useTurn} ${castling} ${ep} 0 1`;
  } else {
    const parts = fen.split(/\s+/);
    if (parts.length >= 2 && (parts[1] === 'w' || parts[1] === 'b')) turn = parts[1];
  }

  if (!mySide) mySide = flipped ? 'b' : 'w';

  let box = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  if (sqSamples.length > 0) {
    const s0 = sqSamples[0];
    const col = flipped ? (7 - s0.file) : s0.file;
    const row = flipped ? s0.rank : (7 - s0.rank);
    const estW = s0.rect.width * 8;
    if (estW > 120 && Math.abs(estW - rect.width) <= rect.width * 0.15) {
      box = {
        left: s0.rect.left - col * s0.rect.width,
        top: s0.rect.top - row * s0.rect.height,
        width: estW,
        height: estW,
      };
    }
  }

  return {
    fen,
    turn: turn || (flipped ? 'b' : 'w'),
    flipped,
    mySide,
    board: {
      left: box.left,
      top: box.top,
      width: box.width,
      height: box.height,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
    },
  };
})()
"""


class BrowserBoardReader:
    """Reads live Chess.com / Lichess board state directly via Chromium CDP without any browser extension."""

    _WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(
        self,
        ports: tuple[int, ...] = (9229, 9222),
        negative_cache_s: float = 1.5,
        enabled: bool = True,
    ):
        self.ports = tuple(ports)
        self.negative_cache_s = max(0.2, float(negative_cache_s))
        self.enabled = bool(enabled)
        self._neg_cache: dict[int, float] = {}
        self._ws_url: str = ""
        self._sock: socket.socket | None = None
        self._ws_buf = bytearray()
        self._req_id: int = 0

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._ws_url = ""
        self._ws_buf.clear()

    def _fetch_targets(self, port: int) -> list[dict] | None:
        now = time.time()
        if now < self._neg_cache.get(port, 0.0):
            return None
        url = f"http://127.0.0.1:{int(port)}/json"
        try:
            with urllib.request.urlopen(url, timeout=0.06) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except Exception:
            self._neg_cache[port] = now + self.negative_cache_s
        return None

    @staticmethod
    def _pick_chess_target(targets: list[dict]) -> dict | None:
        candidates = []
        for t in targets:
            if not isinstance(t, dict) or t.get("type") != "page":
                continue
            ws_url = t.get("webSocketDebuggerUrl")
            u = str(t.get("url") or "").lower()
            if not ws_url or not ("chess.com" in u or "lichess.org" in u):
                continue
            score = 0
            if "/play" in u or "/game/" in u or "/live" in u:
                score += 2
            if "chess.com" in u:
                score += 1
            candidates.append((score, t))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _connect_ws(self, ws_url: str) -> socket.socket:
        if self._sock is not None and self._ws_url == ws_url:
            return self._sock
        self.close()

        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=0.35)
        sock.settimeout(0.35)
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        sock.sendall(req)

        hdr = bytearray()
        while b"\r\n\r\n" not in hdr:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise ConnectionError("WebSocket handshake closed cleanly by peer")
            hdr.extend(chunk)
            if len(hdr) > 16384:
                sock.close()
                raise ConnectionError("WebSocket handshake header too large")

        sep_idx = hdr.index(b"\r\n\r\n") + 4
        head_str = hdr[:sep_idx].decode("latin-1", errors="ignore")
        if "101" not in head_str.split("\r\n", 1)[0]:
            sock.close()
            raise ConnectionError(f"WebSocket upgrade rejected: {head_str.splitlines()[0]}")
        expected_accept = base64.b64encode(
            hashlib.sha1(sec_key.encode("ascii") + self._WS_GUID).digest()
        ).decode("ascii")
        if expected_accept.lower() not in head_str.lower():
            sock.close()
            raise ConnectionError("WebSocket accept digest mismatch")

        self._ws_url = ws_url
        self._sock = sock
        self._ws_buf = bytearray(hdr[sep_idx:])
        return sock

    @staticmethod
    def _build_ws_frame(payload: bytes, opcode: int = 0x1) -> bytes:
        n = len(payload)
        header = bytearray([0x80 | (opcode & 0x0F)])
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", n))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        return bytes(header) + masked

    def _read_exact(self, sock: socket.socket, n: int) -> bytes:
        while len(self._ws_buf) < n:
            chunk = sock.recv(max(4096, n - len(self._ws_buf)))
            if not chunk:
                raise ConnectionError("WebSocket closed")
            self._ws_buf.extend(chunk)
        out = bytes(self._ws_buf[:n])
        del self._ws_buf[:n]
        return out

    def _recv_ws_text(self, sock: socket.socket) -> str:
        msg_chunks: list[bytes] = []
        while True:
            b0, b1 = self._read_exact(sock, 2)
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._read_exact(sock, 2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._read_exact(sock, 8))
            mask = self._read_exact(sock, 4) if masked else b""
            payload = self._read_exact(sock, length)
            if masked:
                payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))

            if opcode == 0x8:
                raise ConnectionError("WebSocket close frame")
            if opcode == 0x9:
                sock.sendall(self._build_ws_frame(payload, opcode=0xA))
                continue
            if opcode == 0xA:
                continue

            if opcode in (0x1, 0x2, 0x0):
                msg_chunks.append(payload)
                if fin:
                    return b"".join(msg_chunks).decode("utf-8", errors="replace")

    def _eval_cdp_target(self, ws_url: str) -> dict | None:
        self._req_id += 1
        req_id = self._req_id
        req_payload = json.dumps(
            {
                "id": req_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": _READ_BOARD_JS,
                    "returnByValue": True,
                    "awaitPromise": False,
                },
            }
        ).encode("utf-8")

        for attempt in range(2):
            try:
                sock = self._connect_ws(ws_url)
                sock.sendall(self._build_ws_frame(req_payload, opcode=0x1))
                deadline = time.time() + 0.35
                while time.time() < deadline:
                    raw_msg = self._recv_ws_text(sock)
                    msg = json.loads(raw_msg)
                    if msg.get("id") != req_id:
                        continue
                    res = (msg.get("result") or {}).get("result") or {}
                    val = res.get("value")
                    if isinstance(val, dict) and isinstance(val.get("fen"), str):
                        # Validate FEN syntax before returning
                        ChessBoardState.from_fen(val["fen"])
                        return val
                    return None
            except Exception:
                self.close()
                if attempt == 0:
                    continue
        return None

    def read_board(self, ports: tuple[int, ...] | None = None) -> dict | None:
        """Query local Chromium CDP endpoints for an active Chess.com/Lichess board."""
        if not self.enabled:
            return None
        for port in ports or self.ports:
            targets = self._fetch_targets(port)
            if not targets:
                continue
            target = self._pick_chess_target(targets)
            if not target:
                continue
            ws_url = str(target.get("webSocketDebuggerUrl") or "")
            if not ws_url:
                continue
            data = self._eval_cdp_target(ws_url)
            if data is not None:
                return data
        return None
