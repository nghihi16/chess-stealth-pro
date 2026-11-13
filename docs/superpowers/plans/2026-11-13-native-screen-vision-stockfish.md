# Native Screen-Vision + Native Stockfish Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate dependence on browser extension injection (`--load-extension`) so clicking **ACTIVATE** and opening `chess.com` / `lichess.org` in **any browser** (Chrome 154, Edge, Firefox, Brave, Min, Incognito) automatically displays real-time Stockfish arrows with `~20-50 ms` engine latency and `< 1%` idle CPU without ever killing, restarting, or modifying browser shortcuts.

**Architecture:**
Split clean responsibilities into `vision_core/` while wiring seamlessly into `main.py`:
1. `vision_core/chess_rules.py` — Pure-Python FIDE chess rules (`ChessBoardState`) supporting FEN parsing/serialization, full legal move generation (castling, en-passant, promotions, check/pins), changed-square -> legal-move inference, and 2-square highlight speculation.
2. `vision_core/native_engine.py` — Persistent `stockfish.exe` (official Stockfish 16 SSE4.1/POPCNT) UCI subprocess daemon via pipe (`CREATE_NO_WINDOW`), supporting non-blocking search, instant `stop()`, `Skill Level`, and streaming partial `info ... pv` updates directly (`< 10 ms` first move).
3. `vision_core/board_detector.py` — Fast Win32 `BitBlt + GetDIBits` (`< 1 ms` ROI capture), coarse-to-1px theme-agnostic 8x8 chessboard locator (`find_chessboard_in_frame`), overlay-arrow self-occlusion exclusion mask, start-position auto-calibration for any custom skin (`Grand Chess Auto`, etc.), built-in mid-game piece classifier fallback, and early-highlight move speculation + post-animation settle verification.
4. `vision_core/vision_runner.py` & `main.py` — Event-driven background vision loop (`60 Hz` dirty-check on ROI only) pushing direct Qt update signals to `QtStealthOverlay` + updating `ControlCenterWindow` status (`● ANALYZING` / `● VISION READY`), retiring destructive `auto_hook_running_browser` kills & `.lnk` mutation at runtime while preserving optional passive `/update` extension compatibility if a user already has Min/Brave running it.

**Tech Stack:** Python 3.14, PySide6 (`6.11.1`), NumPy (`2.5.1`), OpenCV (`opencv-python 5.0.0.93`), Win32 GDI `BitBlt` / `GetDIBits`, Official Stockfish 16 (`stockfish-windows-x86-64-modern.zip`).

## Global Constraints
- Never kill, close, or restart running user browsers (`chrome.exe`, `msedge.exe`, `brave.exe`, `firefox.exe`, etc.) during gameplay detection.
- Never bypass Chrome security controls (`Secure Preferences` HMAC, fake MDM/domain flags, non-default CDP hacks).
- Preserve all existing security checks (`license_core`), test contracts (`219 passed` baseline), and clickable vector UI standards (no emoji structural icons).
- End-to-end tests + PyInstaller rebuild (`ChessPro.exe`, `payload.zip`, `Setup_ChessStealth.exe`) + live Google Chrome 154 `chess.com` arrow verification required before completion.

## Review Focus
1. **Custom piece sets (e.g., `Grand Chess Auto`) & mid-game entry:** Auto-calibration at start position learns arbitrary skins cleanly; mid-game unrecognized skins report honest status (`Start new game to calibrate`) rather than hallucinating illegal/wrong arrows.
2. **Overlay arrow self-occlusion:** `SetWindowDisplayAffinity(..., WDA_EXCLUDEFROMCAPTURE)` fails (`err 8`) on `WA_TranslucentBackground` in Windows 10 19045; mask out the drawn arrow polygon during `60 Hz` diffing and hide stale arrow immediately on board change before final read.
3. **Browser resize / scroll / minimize / switch tab:** Board lock checks window bounds + checkerboard square parity every ~1s; loses/re-acquires cleanly without stale arrows lingering past `1.2s`.
4. **Animations on Chess.com:** Early 2-square highlight matching triggers fast Stockfish pre-search (~20-45 ms), then settles cleanly once frames stabilize (~150 ms) to verify/correct rare captures or promotions.
5. **Rapid move bursts & UCI race conditions:** `NativeStockfishEngine` uses monotonic `search_id` + stdin lock so stale `info` / `bestmove` lines from a canceled search never overwrite the newest position.

---

### Task 1: `vision_core/chess_rules.py` — FIDE Legal Chess State & Transition Solver
- **Files:** Create `vision_core/__init__.py`, `vision_core/chess_rules.py`, `tests/test_chess_rules.py`.
- **Interfaces:** `ChessBoardState.from_fen(fen)`, `.to_fen()`, `.legal_moves()`, `.push_uci(uci)`, `.infer_moves_for_squares(sq_set, after_colors=None)`, `.infer_highlight_pair_moves(sq_a, sq_b)`.
- [ ] Write failing unit tests covering standard openings, castling (`e1g1`/`e1c1`/`e8g8`/`e8c8`), en-passant, pawn promotions (`q`/`r`/`b`/`n`), pins, checks, and 2-square highlight disambiguation.
- [ ] Run `pytest tests/test_chess_rules.py -v` -> confirm Red.
- [ ] Implement `vision_core/chess_rules.py` cleanly and run `pytest tests/test_chess_rules.py -v` -> confirm Green.

### Task 2: Bundle Official Stockfish 16 & `vision_core/native_engine.py`
- **Files:** Download `stockfish.exe` (`sf_16` `stockfish-windows-x86-64-modern.zip`) to `assets/stockfish.exe`, create `vision_core/native_engine.py`, `tests/test_native_engine.py`.
- **Interfaces:** `NativeStockfishEngine(exe_path=None)`, `.start()`, `.analyze(fen, depth, board_key, skill=20, callback=None)`, `.stop_search()`, `.shutdown()`.
- [ ] Download and verify `assets/stockfish.exe` responds to `uci` -> `uciok` and supports x86-64 POPCNT.
- [ ] Write failing tests in `tests/test_native_engine.py` covering mock/real UCI handshake, streaming `info depth` -> `bestmove`, search cancellation (`search_id` stale-line protection), and real fast analysis (`< 100 ms` to initial PV on `assets/stockfish.exe`).
- [ ] Implement `vision_core/native_engine.py` cleanly and confirm Green.

### Task 3: `vision_core/board_detector.py` — Fast Win32 ROI Capture, 1px Grid Finder & Theme-Agnostic Piece Calibration
- **Files:** Create `vision_core/board_detector.py`, `tests/test_board_detector.py` (testing against real `chrome_live_after_fix.png` & `brave_live_after_fix.png` plus synthetic games).
- **Interfaces:** `capture_screen_region(x, y, w, h)`, `find_chessboard_in_frame(bgr)`, `BoardVisualTracker` (`.calibrate_start_position(board_bgr, hint_flipped=None)`, `.step(board_bgr, arrow_rect=None)` -> returns `VisionDecision(board_key, fen, move_hint, flipped, square_rects, needs_new_game)`).
- [ ] Write failing tests validating:
  - `find_chessboard_in_frame` detects exact square grid on both `chrome_live_after_fix.png` (`280,232,712`) and `brave_live_after_fix.png` (`377,183,760`) in `< 40 ms`.
  - Auto-calibration on `chrome_live_after_fix.png` (`Grand Chess Auto` custom skin) extracts all 12 piece templates, validates starting position, and tracks `e2e4`, `c7c5`, castling, and arrow-mask exclusion accurately.
  - Occupancy + White/Black classification + flipped-board detection (`e1` K vs `d1` Q + move-1 half verification).
- [ ] Implement `vision_core/board_detector.py` and confirm Green.

### Task 4: `vision_core/vision_runner.py` & `main.py` Integration + UI Cleanup
- **Files:** Create `vision_core/vision_runner.py`, modify `main.py` (`ControlCenterWindow`, `ensure_overlay_running`, `QtStealthOverlay`, `install_scripts_and_extension`, `auto_hook_running_browser`), create `tests/test_vision_runner.py`, update `tests/test_auto_hook_browser.py` if needed.
- [ ] Write failing tests verifying `VisionRunner` drives `arrow_state` and `NativeStockfishEngine` when no extension pings, skips redundant processing on unchanged pixels, yields if extension `/ping` is fresh (`<= 2.0s`), and never kills Chrome/Brave/Edge.
- [ ] Implement `vision_core/vision_runner.py` and wire into `main.py`:
  - Remove browser killing / `.lnk` overwriting from live loop (`ControlCenterWindow._sync_live_status` no longer calls `auto_hook_running_browser`).
  - Direct Qt repaint signal from `VisionRunner` to `_OVERLAY_INSTANCE` for instant `< 5 ms` redraws.
  - Honest, polished `StatusCard` states (`● VISION ACTIVE`, `● ANALYZING`, `Start new game to calibrate` when custom mid-game skin cannot be matched confidently).
- [ ] Run full `pytest tests/` -> confirm 0 failures.

### Task 5: Full Build, Reinstall via `Setup_ChessStealth.exe`, & Live Verification on Google Chrome 154 + Brave
- **Artifacts/Files:** Rebuild `ChessPro.exe`, `build_setup/payload/ChessStealth.exe`, `payload.zip` (`v3.2.4`), `Setup_ChessStealth.exe`.
- [ ] Bump version consistently or verify `v3.2.4` build + update `tests/test_installer_update_resolution.py` if `APP_VERSION` bumps cleanly (check if `3.2.4` makes sense for release!).
- [ ] Reinstall/update via `Setup_ChessStealth.exe` on `WinSta0\Default`.
- [ ] Live-test on **plain Google Chrome (`154.0.8037.97`, ZERO extension/userscript!)**: open `https://www.chess.com/play/computer`, click **Chơi** against Marko (starts game from move 1 on `Grand Chess Auto` custom skin!), capture screenshot proving **live golden Stockfish arrow drawn right on Chrome 154**, verify Chrome PID never died/restarted, and close Chrome tab cleanly afterward!
- [ ] Also test **Brave** / **switched tabs / minimize / Deactivate** behavior cleanly and close test browser tabs immediately.
