// ==UserScript==
// @name         Chess.com Instant-PV Arrow & Toggle GUI
// @match        *://www.chess.com/*
// @run-at       document-end
// ==/UserScript==

(function () {
  'use strict';

  function initAssistant() {
    if (document.getElementById('ca-panel-container')) return;

    let isEnabled = true;          // Trạng thái Bật / Tắt
    let isMinimized = false;       // Trạng thái Thu gọn GUI
    let stockfishWorker = null;
    let lastBoardKey = '';
    let currentBestMove = null;
    let draggedPieceInfo = null;
    let searchId = 0;              // Đồng bộ phiên suy nghĩ

    // 1. Khởi tạo Stockfish Worker với cơ chế đọc luồng suy nghĩ tức thì (PV Stream)
    function setupEngine() {
      try {
        const workerCode = `importScripts('https://cdnjs.cloudflare.com/ajax/libs/stockfish.js/10.0.2/stockfish.js');`;
        const blob = new Blob([workerCode], { type: 'application/javascript' });
        stockfishWorker = new Worker(URL.createObjectURL(blob));

        stockfishWorker.onmessage = function (event) {
          if (!isEnabled) return;
          const line = typeof event.data === 'string' ? event.data : '';

          // BẮT NGAY NƯỚC ĐI TRONG LÚC ĐANG SUY NGHĨ (Từ Depth 1 -> Depth 13)
          if (line.startsWith('info') && line.includes(' pv ')) {
            const pvMatch = line.match(/ pv ([a-h][1-8][a-h][1-8][qrbn]?)/);
            const depthMatch = line.match(/depth (\d+)/);
            if (pvMatch && pvMatch[1]) {
              const liveMove = pvMatch[1];
              const depth = depthMatch ? depthMatch[1] : '?';
              currentBestMove = liveMove;

              const boardEl = document.querySelector('wc-chess-board, .board');
              if (boardEl) {
                drawChessComArrow(boardEl, liveMove);
                updateStatus(`⚡ <b style="color:#ffaa00; font-size:14px;">${liveMove.substring(0, 2)} ➔ ${liveMove.substring(2, 4)}</b> <span style="font-size:11px; color:#aaa;">(D${depth})</span>`);
              }
            }
          }

          // Khi suy nghĩ xong hoàn toàn
          if (line.startsWith('bestmove')) {
            const move = line.split(' ')[1];
            if (move && move !== '(none)' && move.length >= 4) {
              currentBestMove = move;
              const boardEl = document.querySelector('wc-chess-board, .board');
              if (boardEl) {
                drawChessComArrow(boardEl, move);
                updateStatus(`🎯 <b style="color:#00e676; font-size:14px;">${move.substring(0, 2)} ➔ ${move.substring(2, 4)}</b> <span style="font-size:11px; color:#81b64c;">(Chốt)</span>`);
              }
            }
          }
        };

        stockfishWorker.postMessage('uci');
        stockfishWorker.postMessage('setoption name Skill Level value 20');
        stockfishWorker.postMessage('isready');
      } catch (e) {
        console.error('Lỗi Worker:', e);
      }
    }

    setupEngine();

    // 2. Thiết kế GUI có nút Bật/Tắt và Thu gọn
    const panel = document.createElement('div');
    panel.id = 'ca-panel-container';
    panel.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 999999;
      background: #262421; color: #fff; padding: 10px 12px; border-radius: 10px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: 0 6px 20px rgba(0,0,0,0.6); border: 1px solid #403d39; width: 230px;
      user-select: none; transition: all 0.2s ease;
    `;
    panel.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-weight:bold; color:#ffaa00; font-size:13px;">♟️ Chess Assist</span>
          <span style="font-size:10px; color:#888;">(Alt+X)</span>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <button id="ca-toggle-btn" style="background:#81b64c; color:#fff; border:none; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold; cursor:pointer;">
            ON
          </button>
          <button id="ca-min-btn" style="background:#3d3b38; color:#ccc; border:none; padding:2px 6px; border-radius:4px; font-size:11px; cursor:pointer;" title="Thu gọn">
            _
          </button>
        </div>
      </div>

      <div id="ca-body" style="margin-top:8px; border-top:1px solid #3d3b38; padding-top:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:11px; color:#ccc;">
          <span>Phe của bạn:</span>
          <select id="ca-my-color" style="background:#3d3b38; color:#fff; border:1px solid #555; padding:2px 4px; border-radius:4px; font-size:11px;">
            <option value="auto" selected>Tự động (Góc nhìn)</option>
            <option value="b">Quân Đen</option>
            <option value="w">Quân Trắng</option>
          </select>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; font-size:11px; color:#ccc;">
          <span>Màu mũi tên:</span>
          <select id="ca-arrow-color" style="background:#3d3b38; color:#fff; border:1px solid #555; padding:2px 4px; border-radius:4px; font-size:11px;">
            <option value="rgba(255, 170, 0, 0.85)" selected>Cam (Chess.com)</option>
            <option value="rgba(115, 192, 60, 0.85)">Xanh lá</option>
            <option value="rgba(235, 97, 80, 0.85)">Đỏ</option>
            <option value="rgba(82, 176, 220, 0.85)">Xanh dương</option>
          </select>
        </div>
        <div id="ca-status" style="font-size:12px; color:#00e676; font-weight:bold; margin-top:4px;">
          🟢 Sẵn sàng...
        </div>
      </div>
    `;
    document.body.appendChild(panel);

    function updateStatus(html) {
      const el = document.getElementById('ca-status');
      if (el) el.innerHTML = html;
    }

    // Xử lý nút Bật / Tắt (ON / OFF)
    function toggleAssistant() {
      isEnabled = !isEnabled;
      const btn = document.getElementById('ca-toggle-btn');
      if (isEnabled) {
        btn.innerText = 'ON';
        btn.style.background = '#81b64c';
        lastBoardKey = ''; // Ép quét lại ngay lập tức
        updateStatus('🟢 Đã bật lại...');
      } else {
        btn.innerText = 'OFF';
        btn.style.background = '#d9534f';
        if (stockfishWorker) stockfishWorker.postMessage('stop');
        currentBestMove = null;
        clearArrow();
        updateStatus('<span style="color:#aaa;">🔴 Đã tạm dừng</span>');
      }
    }

    document.getElementById('ca-toggle-btn').addEventListener('click', toggleAssistant);

    // Phím tắt Alt + X để Bật / Tắt nhanh
    window.addEventListener('keydown', (e) => {
      if (e.altKey && e.key.toLowerCase() === 'x') {
        toggleAssistant();
      }
    });

    // Xử lý nút Thu gọn (_)
    document.getElementById('ca-min-btn').addEventListener('click', () => {
      isMinimized = !isMinimized;
      const bodyEl = document.getElementById('ca-body');
      const minBtn = document.getElementById('ca-min-btn');
      if (isMinimized) {
        bodyEl.style.display = 'none';
        minBtn.innerText = '+';
        panel.style.width = '185px';
      } else {
        bodyEl.style.display = 'block';
        minBtn.innerText = '_';
        panel.style.width = '230px';
      }
    });

    // 3. Giữ tọa độ khi nhấc cờ
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

    function getPlayerSide(boardEl) {
      const manual = document.getElementById('ca-my-color').value;
      if (manual !== 'auto') return manual;
      return (boardEl.classList.contains('flipped') || boardEl.classList.contains('board-flipped')) ? 'b' : 'w';
    }

    // 4. Trích xuất bàn cờ
    function extractBoard() {
      const boardEl = document.querySelector('wc-chess-board, .board');
      if (!boardEl) return null;

      const grid = Array(8).fill(null).map(() => Array(8).fill(''));
      const pieces = boardEl.querySelectorAll('.piece');
      if (pieces.length === 0) return null;

      let whiteKing = false;
      let blackKing = false;

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

      const mySide = getPlayerSide(boardEl);
      const boardPart = fenRows.join('/');

      return {
        boardEl,
        mySide,
        boardPart,
        fen: `${boardPart} ${mySide} KQkq - 0 1`
      };
    }

    // 5. Vẽ mũi tên chuẩn Chess.com
    function clearArrow() {
      const oldSvg = document.getElementById('ca-arrow-overlay');
      if (oldSvg) oldSvg.remove();
    }

    function drawChessComArrow(boardEl, move) {
      if (!isEnabled || !boardEl || !move || move.length < 4) return;

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

      const ux = dx / len;
      const uy = dy / len;
      const px = -uy;
      const py = ux;

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

      const arrowColor = document.getElementById('ca-arrow-color')?.value || 'rgba(255, 170, 0, 0.85)';

      svg.innerHTML = `<polygon points="${p1} ${p2} ${p3} ${p4} ${p5} ${p6} ${p7}" fill="${arrowColor}" />`;
    }

    document.getElementById('ca-arrow-color').addEventListener('change', () => {
      const boardEl = document.querySelector('wc-chess-board, .board');
      if (boardEl && currentBestMove) drawChessComArrow(boardEl, currentBestMove);
    });

    document.getElementById('ca-my-color').addEventListener('change', () => {
      lastBoardKey = ''; // Tính lại ngay khi đổi màu quân
    });

    // 6. Vòng lặp kiểm tra liên tục
    setInterval(() => {
      if (!isEnabled || !stockfishWorker) return;

      const state = extractBoard();
      if (!state) return;

      // Luôn giữ mũi tên hiển thị trên mặt bàn cờ nếu DOM của Chess.com xóa mất
      if (currentBestMove) {
        const svg = document.getElementById('ca-arrow-overlay');
        if (!svg || !state.boardEl.contains(svg)) {
          drawChessComArrow(state.boardEl, currentBestMove);
        }
      }

      const currentKey = `${state.boardPart}_${state.mySide}`;
      if (currentKey === lastBoardKey) return;

      // Thế cờ đã thay đổi -> Bắt đầu phiên tính mới ngay lập tức
      lastBoardKey = currentKey;
      searchId++;

      stockfishWorker.postMessage('stop');
      stockfishWorker.postMessage('position fen ' + state.fen);
      stockfishWorker.postMessage('go depth 13 movetime 180');
    }, 25);
  }

  if (document.body) initAssistant();
  else window.addEventListener('DOMContentLoaded', initAssistant);
})();