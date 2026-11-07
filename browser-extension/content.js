// ==UserScript==
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
