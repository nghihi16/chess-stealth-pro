// ==UserScript==
// @name         Chess.com Zero-DOM Stealth Bridge
// @match        *://www.chess.com/*
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  if (window.__CHESS_STEALTH_BRIDGE_ACTIVE__) return;
  window.__CHESS_STEALTH_BRIDGE_ACTIVE__ = true;

  let isEnabled = true;
  let manualSide = 'auto'; // 'auto' | 'w' | 'b'
  let stockfishWorker = null;
  let lastBoardKey = '';
  let currentBestMove = null;
  let draggedPieceInfo = null;

  // Pixel-perfect viewport-to-screen offset calibrated from pointer/mouse events
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

  // 1. Send screen coordinates to local Stealth Overlay (127.0.0.1:8765)
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
      // Fallback via GET image beacon if CSP blocks fetch
      const q = payload.show
        ? `s=1&x1=${payload.x1}&y1=${payload.y1}&x2=${payload.x2}&y2=${payload.y2}&sz=${payload.size}&t=${Date.now()}`
        : `s=0&t=${Date.now()}`;
      const img = new Image();
      img.src = `http://127.0.0.1:8765/u?${q}`;
    });
  }

  // 2. Compute exact monitor pixel coordinates of a chess square
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

    // Invalidate pointer calibration if window moved or resized
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

  // 3. Initialize Stockfish Web Worker (PV real-time stream)
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

  // Hotkeys:
  // Alt + X: Toggle Stealth Arrow ON / OFF
  // Alt + C: Cycle side (auto -> b -> w)
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

  // 4. Preserve origin square while dragging a piece
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

  // 5. Extract board state into FEN
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

  // 6. Fast 25ms loop to sync position & calculate best move
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
