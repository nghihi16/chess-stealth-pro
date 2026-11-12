// ==UserScript==
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
