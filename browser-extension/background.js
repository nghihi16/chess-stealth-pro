const SESSION_TOKEN = '21494df307f8e10c49d900caef7fdedb6cb746f28a54f346';
let sfReady = false;
let currentBestMove = '';
let currentDepth = '';
let currentEval = '';
let currentPonder = '';
let lastBoardKey = '';
let latestPayload = null;
let serverConfig = { ok: true, enabled: true, side: 'auto', skill: 20, target_depth: 12 };
let lastPushTime = 0;

self.__sfPrint = function(line) {
  if (typeof line !== 'string') return;
  if (line.startsWith('info') && line.includes(' pv ')) {
    const pvMatch = line.match(/ pv ([a-h][1-8][a-h][1-8][qrbn]?)(?:\s+([a-h][1-8][a-h][1-8][qrbn]?))?/);
    const depthMatch = line.match(/depth (\d+)/);
    const cpMatch = line.match(/score cp (-?\d+)/);
    const mateMatch = line.match(/score mate (-?\d+)/);
    if (pvMatch && pvMatch[1]) {
      currentBestMove = pvMatch[1];
      if (pvMatch[2]) currentPonder = pvMatch[2];
      if (depthMatch) currentDepth = depthMatch[1];
      if (mateMatch) {
        const m = parseInt(mateMatch[1], 10);
        currentEval = (m > 0 ? '+M' : '-M') + Math.abs(m);
      } else if (cpMatch) {
        const cp = parseInt(cpMatch[1], 10) / 100.0;
        currentEval = (cp >= 0 ? '+' : '') + cp.toFixed(1);
      }
      pushBestMoveToServer();
    }
  } else if (line.startsWith('bestmove')) {
    const parts = line.split(' ');
    const move = parts[1];
    const ponderIdx = parts.indexOf('ponder');
    if (ponderIdx !== -1 && parts[ponderIdx + 1]) {
      currentPonder = parts[ponderIdx + 1];
    }
    if (move && move !== '(none)' && move.length >= 4) {
      currentBestMove = move;
      pushBestMoveToServer();
    }
  }
};

function uci(cmd) {
  try {
    if (typeof onmessage === 'function') {
      onmessage({ data: cmd });
    } else if (typeof Module !== 'undefined' && Module.ccall) {
      Module.ccall('uci_command', 'number', ['string'], [cmd]);
    }
  } catch (e) {}
}

try {
  importScripts('stockfish.js');
  uci('uci');
  uci('setoption name Skill Level value 20');
  uci('isready');
  sfReady = true;
} catch (e) {
  console.error('Stockfish service worker init error:', e);
}

function pushBestMoveToServer() {
  if (!latestPayload || !currentBestMove || currentBestMove.length < 4) return;
  const b = latestPayload.board;
  if (!b || b.width < 40 || b.height < 40) return;
  const isFlipped = Boolean(latestPayload.flipped);
  const sqSize = b.width / 8;
  const screenOffsetX = latestPayload.screenOffsetX || 0;
  const screenOffsetY = latestPayload.screenOffsetY || 0;

  function sqToScreen(sq) {
    const file = sq.charCodeAt(0) - 97;
    const rank = parseInt(sq[1], 10) - 1;
    const col = isFlipped ? (7 - file) : file;
    const row = isFlipped ? rank : (7 - rank);
    return {
      x: Math.round(screenOffsetX + b.left + (col + 0.5) * sqSize),
      y: Math.round(screenOffsetY + b.top + (row + 0.5) * sqSize)
    };
  }

  const from = sqToScreen(currentBestMove.substring(0, 2));
  const to = sqToScreen(currentBestMove.substring(2, 4));
  let pieceChar = '';
  const grid = latestPayload.grid;
  if (grid && currentBestMove.length >= 2) {
    const fCol = currentBestMove.charCodeAt(0) - 97;
    const fRank = parseInt(currentBestMove[1], 10);
    const fRow = 8 - fRank;
    if (fRow >= 0 && fRow < 8 && fCol >= 0 && fCol < 8 && grid[fRow]) {
      pieceChar = grid[fRow][fCol] || '';
    }
  }

  const updateData = {
    show: true,
    board: b,
    flipped: isFlipped,
    x1: from.x,
    y1: from.y,
    x2: to.x,
    y2: to.y,
    size: Math.round(sqSize),
    move: currentBestMove,
    depth: currentDepth || '',
    eval: currentEval || '',
    ponder: currentPonder || '',
    piece: pieceChar
  };

  lastPushTime = Date.now();
  fetch('http://127.0.0.1:8765/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + SESSION_TOKEN },
    body: JSON.stringify(updateData)
  })
  .then(r => r.json())
  .then(data => {
    if (data) serverConfig = Object.assign(serverConfig, data);
  })
  .catch(() => {});
}

function pingServer() {
  fetch('http://127.0.0.1:8765/ping', {
    headers: { 'Authorization': 'Bearer ' + SESSION_TOKEN }
  })
    .then(r => r.json())
    .then(data => {
      if (data) serverConfig = Object.assign(serverConfig, data);
    })
    .catch(() => {});
}
pingServer();
setInterval(pingServer, 1200);

chrome.runtime.onMessage.addListener((m, sender, sendResponse) => {
  if (m && m.type === 'OVERLAY_BOARD' && m.payload) {
    latestPayload = m.payload;
    if (m.payload.boardKey !== lastBoardKey) {
      lastBoardKey = m.payload.boardKey;
      currentBestMove = '';
      currentDepth = '';
      currentEval = '';
      currentPonder = '';
      if (sfReady) {
        const skill = serverConfig.skill ?? 20;
        const depth = Math.min(Math.max(serverConfig.target_depth ?? 11, 5), 13);
        uci('stop');
        uci('setoption name Skill Level value ' + skill);
        uci('position fen ' + m.payload.fen);
        uci('go depth ' + depth);
      }
    } else if (currentBestMove && (Date.now() - lastPushTime > 60)) {
      pushBestMoveToServer();
    }
    sendResponse(serverConfig);
    return false;
  }
  if (m && m.type === 'OVERLAY_UPDATE' && m.payload) {
    if (!m.payload.show) {
      lastBoardKey = '';
      currentBestMove = '';
    }
    fetch('http://127.0.0.1:8765/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + SESSION_TOKEN },
      body: JSON.stringify(m.payload)
    })
    .then(r => r.json())
    .then(data => {
      if (data) serverConfig = Object.assign(serverConfig, data);
      sendResponse(serverConfig);
    })
    .catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (m && m.type === 'OVERLAY_CAL' && m.query) {
    fetch('http://127.0.0.1:8765/cal?' + m.query, {
      headers: { 'Authorization': 'Bearer ' + SESSION_TOKEN }
    })
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
});
