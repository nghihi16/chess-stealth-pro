from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import cv2
import numpy as np

from vision_core.chess_rules import (
    START_FEN,
    ChessBoardState,
    piece_side,
    screen_rc_to_sq,
    sq_to_screen_rc,
)


@dataclass(frozen=True)
class BoardBounds:
    """Detected chessboard bounding square in physical screen pixels."""

    x: int
    y: int
    size: int
    light_bgr: tuple[float, float, float]
    dark_bgr: tuple[float, float, float]
    confidence: float

    @property
    def sq_size(self) -> float:
        return self.size / 8.0

    def square_rect(self, row: int, col: int) -> tuple[int, int, int, int]:
        sq = self.size / 8.0
        x0 = self.x + round(col * sq)
        y0 = self.y + round(row * sq)
        x1 = self.x + round((col + 1) * sq)
        y1 = self.y + round((row + 1) * sq)
        return x0, y0, x1, y1

    def to_qt_coords(self, dpr: float = 1.0) -> tuple[float, float, float]:
        scale = max(0.5, float(dpr))
        return self.x / scale, self.y / scale, self.size / scale


@dataclass
class DetectionResult:
    """Result of inspecting one screen frame for a chessboard and position."""

    status: str  # "ok", "no_board", "need_start_pos"
    bounds: BoardBounds | None = None
    fen: str | None = None
    flipped: bool = False
    board_key: str = ""
    turn: str = "w"
    last_move: str = ""
    source: str = ""  # "start", "steady", "move", "highlight", "resync"


# Win32 GDI structures for sub-millisecond BitBlt ROI capture
class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


_WIN32_GDI_CACHE: tuple[ctypes.WinDLL, ctypes.WinDLL] | None = None


def _win32_gdi() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    """Return private user32/gdi32 DLL handles with 64-bit-safe signatures."""
    global _WIN32_GDI_CACHE
    if _WIN32_GDI_CACHE is not None:
        return _WIN32_GDI_CACHE

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int

    _WIN32_GDI_CACHE = (user32, gdi32)
    return _WIN32_GDI_CACHE


def get_primary_screen_size() -> tuple[int, int]:
    user32, _ = _win32_gdi()
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def capture_screen_bgr(roi: tuple[int, int, int, int] | None = None) -> np.ndarray | None:
    """Capture desktop pixels (or ROI (x, y, w, h)) into a contiguous BGR uint8 array."""
    user32, gdi32 = _win32_gdi()
    if roi is None:
        x, y = 0, 0
        w, h = get_primary_screen_size()
    else:
        x, y, w, h = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
    if w <= 0 or h <= 0:
        return None

    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        return None
    hdc_mem = None
    hbmp = None
    old_obj = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        if not hdc_mem or not hbmp:
            return None
        old_obj = gdi32.SelectObject(hdc_mem, hbmp)
        ok = gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020)  # SRCCOPY
        if not ok:
            return None

        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # Top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        buf = np.empty((h, w, 4), dtype=np.uint8)
        rows = gdi32.GetDIBits(
            hdc_mem,
            hbmp,
            0,
            h,
            ctypes.c_void_p(int(buf.ctypes.data)),
            ctypes.byref(bmi),
            0,
        )
        if rows != h:
            return None
        return np.ascontiguousarray(buf[:, :, :3])
    finally:
        if old_obj and hdc_mem:
            gdi32.SelectObject(hdc_mem, old_obj)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)


def _sample_board_corner_colors(img_bgr: np.ndarray, bx: int, by: int, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Sample clean tile colors from all 64 squares using outer corner patches (unoccluded by pieces)."""
    h, w = img_bgr.shape[:2]
    if bx < 0 or by < 0 or bx + size > w or by + size > h or size < 160:
        return np.empty((0, 3)), np.empty((0, 3))
    sq = size / 8.0
    m0 = max(2, int(round(sq * 0.05)))
    m1 = max(m0 + 2, int(round(sq * 0.16)))
    evens: list[np.ndarray] = []
    odds: list[np.ndarray] = []
    for r in range(8):
        y0 = by + round(r * sq)
        y1 = by + round((r + 1) * sq)
        for c in range(8):
            x0 = bx + round(c * sq)
            x1 = bx + round((c + 1) * sq)
            # Sample top-right corner strip away from col-0 digits and row-7 file letters
            p = img_bgr[y0 + m0 : y0 + m1, x1 - m1 : x1 - m0]
            if p.size == 0:
                continue
            med = p.reshape(-1, 3).mean(axis=0)
            if (r + c) % 2 == 0:
                evens.append(med)
            else:
                odds.append(med)
    return np.asarray(evens, dtype=np.float32), np.asarray(odds, dtype=np.float32)


def _verify_board_bounds(img_bgr: np.ndarray, bx: int, by: int, size: int) -> BoardBounds | None:
    """Strictly verify 8x8 tile parity consistency and outer border termination."""
    evens, odds = _sample_board_corner_colors(img_bgr, bx, by, size)
    if len(evens) < 28 or len(odds) < 28:
        return None
    l_med = np.median(evens, axis=0)
    d_med = np.median(odds, axis=0)
    sep = float(np.linalg.norm(l_med - d_med))
    if sep < 28.0:
        return None

    even_err = np.linalg.norm(evens - l_med, axis=1)
    odd_err = np.linalg.norm(odds - d_med, axis=1)
    good_even = int(np.sum(even_err < max(26.0, sep * 0.35)))
    good_odd = int(np.sum(odd_err < max(26.0, sep * 0.35)))
    if good_even < 26 or good_odd < 26:
        return None

    spread = float(np.percentile(even_err, 60) + np.percentile(odd_err, 60))
    if spread > sep * 0.45:
        return None

    # Verify outer board does not keep extending as a checkerboard beyond the 8x8 perimeter
    h, w = img_bgr.shape[:2]
    sq = size / 8.0
    m0 = max(2, int(round(sq * 0.05)))
    m1 = max(m0 + 2, int(round(sq * 0.16)))
    pad_half = max(6, int(round(sq * 0.3)))
    outside_parity_matches = 0
    outside_checks = 0
    for c in range(0, 8, 2):
        cx = bx + round((c + 0.5) * sq)
        if by - pad_half >= 0:
            p = img_bgr[by - pad_half : by - 2, max(0, cx - m1) : min(w, cx + m1)]
            if p.size:
                med = np.median(p.reshape(-1, 3), axis=0)
                exp = d_med if (c % 2 == 0) else l_med
                outside_checks += 1
                if float(np.linalg.norm(med - exp)) < max(18.0, sep * 0.22):
                    outside_parity_matches += 1
        if by + size + pad_half <= h:
            p = img_bgr[by + size + 2 : by + size + pad_half, max(0, cx - m1) : min(w, cx + m1)]
            if p.size:
                med = np.median(p.reshape(-1, 3), axis=0)
                exp = l_med if ((7 + c) % 2 == 0) else d_med
                outside_checks += 1
                if float(np.linalg.norm(med - exp)) < max(18.0, sep * 0.22):
                    outside_parity_matches += 1
    if outside_checks >= 4 and outside_parity_matches >= max(3, int(outside_checks * 0.7)):
        return None

    confidence = min(1.0, (good_even + good_odd) / 64.0 * max(0.2, 1.0 - spread / max(1.0, sep)))
    return BoardBounds(
        x=int(bx),
        y=int(by),
        size=int(size),
        light_bgr=(float(l_med[0]), float(l_med[1]), float(l_med[2])),
        dark_bgr=(float(d_med[0]), float(d_med[1]), float(d_med[2])),
        confidence=confidence,
    )


def _refine_bounds_1px(img_bgr: np.ndarray, approx_x: int, approx_y: int, approx_size: int) -> BoardBounds | None:
    """Refine coarse candidate to exact 1px grid coordinates using alternating band seams."""
    h, w = img_bgr.shape[:2]
    csq = approx_size / 8.0
    pad = max(20, int(round(csq * 0.38)))
    rx0 = max(0, approx_x - pad)
    ry0 = max(0, approx_y - pad)
    rx1 = min(w, approx_x + approx_size + pad)
    ry1 = min(h, approx_y + approx_size + pad)
    if rx1 - rx0 < 200 or ry1 - ry0 < 200:
        return None

    roi_gray = cv2.cvtColor(img_bgr[ry0:ry1, rx0:rx1], cv2.COLOR_BGR2GRAY).astype(np.float32)

    # First check light vs dark polarity sign at coarse guess
    init_bounds = _verify_board_bounds(img_bgr, approx_x, approx_y, approx_size)
    # Determine expected sign of (light - dark) gray intensity
    if init_bounds is not None:
        l_g = 0.114 * init_bounds.light_bgr[0] + 0.587 * init_bounds.light_bgr[1] + 0.299 * init_bounds.light_bgr[2]
        d_g = 0.114 * init_bounds.dark_bgr[0] + 0.587 * init_bounds.dark_bgr[1] + 0.299 * init_bounds.dark_bgr[2]
        sign_ld = 1.0 if l_g >= d_g else -1.0
    else:
        sign_ld = 1.0

    # Sample top-corner clear horizontal bands of all 8 rows to align X grid borders down to 1px
    x_bands = []
    for r in range(8):
        by_local = (approx_y - ry0) + r * csq
        sy0 = max(0, int(round(by_local + csq * 0.05)))
        sy1 = min(roi_gray.shape[0], int(round(by_local + csq * 0.18)))
        if sy1 > sy0:
            row_sig = np.mean(roi_gray[sy0:sy1, :], axis=0)
            x_bands.append((r, row_sig))

    best_ox = float(approx_x - rx0)
    best_sqx = csq
    if len(x_bands) >= 6:
        band_mat = np.stack([b for _, b in x_bands], axis=0)
        band_signs = np.array([(1.0 if r % 2 == 0 else -1.0) * sign_ld for r, _ in x_bands], dtype=np.float32)[:, None]
        grad_x = np.zeros_like(band_mat)
        grad_x[:, 1:-1] = band_mat[:, 2:] - band_mat[:, :-2]

        k_arr = np.arange(1, 8, dtype=np.float32)  # interior grid lines 1..7
        k_signs = np.where((np.arange(1, 8) % 2) == 1, -1.0, 1.0).astype(np.float32)
        aligned_x = band_signs * grad_x
        best_score = -1e18
        rw = roi_gray.shape[1]
        ox_base = approx_x - rx0
        margin_x = min(28, max(14, int(round(csq * 0.42))))
        ox_vals = np.arange(max(2, ox_base - margin_x), min(rw - 160, ox_base + margin_x + 1), dtype=np.float32)
        sq_vals = np.linspace(max(24.0, csq - 6.0), csq + 6.0, 49, dtype=np.float32)
        for sq_f in sq_vals:
            max_ox = rw - 3 - 8.0 * sq_f
            valid_ox = ox_vals[ox_vals <= max_ox]
            if len(valid_ox) == 0:
                continue
            pos = np.rint(valid_ox[:, None] + k_arr[None, :] * sq_f).astype(np.int32)
            vals = aligned_x[:, pos]  # (nrows, nox, 7)
            scores = (vals * k_signs[None, None, :]).sum(axis=(0, 2))
            idx = int(np.argmax(scores))
            if float(scores[idx]) > best_score:
                best_score = float(scores[idx])
                best_ox = float(valid_ox[idx])
                best_sqx = float(sq_f)

    # Sample side-margin clear vertical strips of all 8 cols to align Y grid borders down to 1px
    y_bands = []
    for c in range(8):
        bx_local = best_ox + c * best_sqx
        sx0 = max(0, int(round(bx_local + best_sqx * 0.82)))
        sx1 = min(roi_gray.shape[1], int(round(bx_local + best_sqx * 0.95)))
        if sx1 > sx0:
            col_sig = np.mean(roi_gray[:, sx0:sx1], axis=1)
            y_bands.append((c, col_sig))

    best_oy = float(approx_y - ry0)
    best_sqy = best_sqx
    if len(y_bands) >= 6:
        band_mat = np.stack([b for _, b in y_bands], axis=0)
        band_signs = np.array([(1.0 if c % 2 == 0 else -1.0) * sign_ld for c, _ in y_bands], dtype=np.float32)[:, None]
        grad_y = np.zeros_like(band_mat)
        grad_y[:, 1:-1] = band_mat[:, 2:] - band_mat[:, :-2]

        k_arr = np.arange(1, 8, dtype=np.float32)
        k_signs = np.where((np.arange(1, 8) % 2) == 1, -1.0, 1.0).astype(np.float32)
        aligned_y = band_signs * grad_y
        best_score = -1e18
        rh = roi_gray.shape[0]
        oy_base = approx_y - ry0
        margin_y = min(28, max(14, int(round(best_sqx * 0.42))))
        oy_vals = np.arange(max(2, oy_base - margin_y), min(rh - 160, oy_base + margin_y + 1), dtype=np.float32)
        sq_vals = np.linspace(max(24.0, best_sqx - 1.5), best_sqx + 1.5, 13, dtype=np.float32)
        for sq_f in sq_vals:
            max_oy = rh - 3 - 8.0 * sq_f
            valid_oy = oy_vals[oy_vals <= max_oy]
            if len(valid_oy) == 0:
                continue
            pos = np.rint(valid_oy[:, None] + k_arr[None, :] * sq_f).astype(np.int32)
            vals = aligned_y[:, pos]
            scores = (vals * k_signs[None, None, :]).sum(axis=(0, 2))
            idx = int(np.argmax(scores))
            if float(scores[idx]) > best_score:
                best_score = float(scores[idx])
                best_oy = float(valid_oy[idx])
                best_sqy = float(sq_f)

    final_x = int(round(rx0 + best_ox))
    final_y = int(round(ry0 + best_oy))
    final_sq = 0.5 * (best_sqx + best_sqy) if abs(best_sqx - best_sqy) <= 1.25 else best_sqx
    final_size = int(round(final_sq * 8.0))
    return _verify_board_bounds(img_bgr, final_x, final_y, final_size)


def locate_board_bgr(img_bgr: np.ndarray, hint_bounds: BoardBounds | None = None) -> BoardBounds | None:
    """Locate an 8x8 chessboard in physical pixel coordinates in ~10-25ms."""
    if img_bgr is None or img_bgr.size == 0:
        return None
    h, w = img_bgr.shape[:2]
    if h < 240 or w < 240:
        return None

    # 1. Fast ROI hint verification (< 1ms)
    if hint_bounds is not None:
        verified = _verify_board_bounds(img_bgr, hint_bounds.x, hint_bounds.y, hint_bounds.size)
        if verified is not None:
            return verified
        refined = _refine_bounds_1px(img_bgr, hint_bounds.x, hint_bounds.y, hint_bounds.size)
        if refined is not None:
            return refined

    # 2. Vectorized 1/8-resolution integral checkerboard comb scan (~5-15ms across full 1920x1080)
    scale = 8 if min(w, h) >= 480 else 4
    dw, dh = w // scale, h // scale
    if dw < 40 or dh < 40:
        return None
    sub = img_bgr[::2, ::2] if scale == 8 else img_bgr
    ds_gray = cv2.resize(
        cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY),
        (dw, dh),
        interpolation=cv2.INTER_AREA,
    ).astype(np.float32)
    integ = cv2.integral(ds_gray)  # (dh+1, dw+1)

    q_min = max(4, 32 // scale)
    q_max = min(19 if scale == 8 else 36, (min(dw, dh) - 2) // 8)
    candidates: list[tuple[float, int, int, int]] = []

    for q in range(q_min, q_max + 1):
        tile = (integ[q:, q:] - integ[:-q, q:] - integ[q:, :-q] + integ[:-q, :-q]) / float(q * q)
        if tile.shape[0] <= 7 * q or tile.shape[1] <= 7 * q:
            continue
        c_diff = tile[:-q, :-q] + tile[q:, q:] - tile[:-q, q:] - tile[q:, :-q]
        ch, cw = c_diff.shape
        if ch <= 6 * q or cw <= 6 * q:
            continue

        hx = c_diff[:, : cw - 6 * q].copy()
        for j in range(1, 7):
            start = j * q
            end = cw - (6 - j) * q
            if j & 1:
                hx -= c_diff[:, start:end]
            else:
                hx += c_diff[:, start:end]

        vy = hx[: ch - 6 * q, :].copy()
        for i in range(1, 7):
            start = i * q
            end = ch - (6 - i) * q
            if i & 1:
                vy -= hx[start:end, :]
            else:
                vy += hx[start:end, :]

        energy = np.abs(vy)
        max_idx = int(np.argmax(energy))
        py, px = divmod(max_idx, energy.shape[1])
        peak = float(energy[py, px])
        if peak > 380.0:
            candidates.append((peak, px * scale, py * scale, q * 8 * scale))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    tested_regions: list[tuple[int, int, int]] = []
    for _, cx, cy, csize in candidates[:8]:
        if any(abs(cx - tx) < 16 and abs(cy - ty) < 16 and abs(csize - ts) < 24 for tx, ty, ts in tested_regions):
            continue
        tested_regions.append((cx, cy, csize))
        refined = _refine_bounds_1px(img_bgr, cx, cy, csize)
        if refined is not None:
            return refined

    return None


@dataclass
class _SquareObs:
    row: int
    col: int
    sq_idx: int
    occupied: bool
    occluded: bool
    fg_frac: float
    fg_bgr: np.ndarray
    fg_lum: float
    highlight_score: float
    patch_bgr: np.ndarray  # normalized 28x28 BGR


def _build_board_arrow_mask(bounds: BoardBounds, arrow_px: tuple[float, float, float, float, float] | None) -> np.ndarray | None:
    """Return 255/0 mask inside bounds (0 marks overlay arrow pixels to exclude)."""
    if arrow_px is None or len(arrow_px) < 4:
        return None
    ax1, ay1, ax2, ay2 = arrow_px[0], arrow_px[1], arrow_px[2], arrow_px[3]
    width_hint = arrow_px[4] if len(arrow_px) >= 5 else bounds.sq_size
    lx1, ly1 = ax1 - bounds.x, ay1 - bounds.y
    lx2, ly2 = ax2 - bounds.x, ay2 - bounds.y
    s = bounds.size
    if (max(lx1, lx2) < -30 or min(lx1, lx2) > s + 30) and (max(ly1, ly2) < -30 or min(ly1, ly2) > s + 30):
        return None

    mask = np.full((s, s), 255, dtype=np.uint8)
    sq_ref = bounds.sq_size
    shaft_thick = max(10, int(round(sq_ref * 0.24)))
    head_radius = max(14, int(round(sq_ref * 0.26)))
    cv2.line(mask, (round(lx1), round(ly1)), (round(lx2), round(ly2)), 0, thickness=shaft_thick)
    cv2.circle(mask, (round(lx2), round(ly2)), head_radius, 0, -1)
    return mask


def _extract_square_observations(
    img_bgr: np.ndarray,
    bounds: BoardBounds,
    flipped: bool,
    arrow_mask: np.ndarray | None,
) -> list[_SquareObs]:
    """Extract piece occupancy, foreground color, normalized patch, and highlight metric per square."""
    board_crop = img_bgr[bounds.y : bounds.y + bounds.size, bounds.x : bounds.x + bounds.size]
    sq_f = bounds.size / 8.0
    l_bg = np.array(bounds.light_bgr, dtype=np.float32)
    d_bg = np.array(bounds.dark_bgr, dtype=np.float32)

    raw_local_bgs: list[np.ndarray] = []
    has_measured_bg: list[bool] = []
    parities: list[int] = []
    obs_list: list[_SquareObs] = []

    for r in range(8):
        y0 = round(r * sq_f)
        y1 = round((r + 1) * sq_f)
        sh = y1 - y0
        cy0 = max(y0, y0 + int(round(sh * 0.17)))
        cy1 = min(y1, y0 + int(round(sh * 0.83)))
        by0_top = y0 + max(1, int(round(sh * 0.04)))
        by1_top = y0 + max(3, int(round(sh * 0.13)))
        by0_bot = y1 - max(3, int(round(sh * 0.13)))
        by1_bot = y1 - max(1, int(round(sh * 0.04)))

        for c in range(8):
            x0 = round(c * sq_f)
            x1 = round((c + 1) * sq_f)
            sw = x1 - x0
            cx0 = max(x0, x0 + int(round(sw * 0.17)))
            cx1 = min(x1, x0 + int(round(sw * 0.83)))
            bx0_right = x1 - max(3, int(round(sw * 0.14)))
            bx1_right = x1 - max(1, int(round(sw * 0.04)))

            sq_idx = screen_rc_to_sq(r, c, flipped=flipped)
            parity = (r + c) % 2
            parities.append(parity)

            center_bgr = board_crop[cy0:cy1, cx0:cx1]
            # Sample right-side corner bands away from coordinate letters on a-file and rank-1
            tr_patch = board_crop[by0_top:by1_top, bx0_right:bx1_right]
            br_patch = board_crop[by0_bot:by1_bot, bx0_right:bx1_right]

            if arrow_mask is not None:
                c_mask = arrow_mask[cy0:cy1, cx0:cx1] > 0
                tr_mask = arrow_mask[by0_top:by1_top, bx0_right:bx1_right] > 0
                br_mask = arrow_mask[by0_bot:by1_bot, bx0_right:bx1_right] > 0
                valid_center_px = center_bgr[c_mask]
                bg_parts = []
                if tr_mask.any():
                    bg_parts.append(tr_patch[tr_mask])
                if br_mask.any():
                    bg_parts.append(br_patch[br_mask])
            else:
                valid_center_px = center_bgr.reshape(-1, 3)
                bg_parts = [tr_patch.reshape(-1, 3), br_patch.reshape(-1, 3)]

            total_center_px = max(1, center_bgr.shape[0] * center_bgr.shape[1])
            valid_ratio = len(valid_center_px) / float(total_center_px)
            if arrow_mask is not None:
                iy0 = max(y0, y0 + int(round(sh * 0.28)))
                iy1 = min(y1, y0 + int(round(sh * 0.72)))
                ix0 = max(x0, x0 + int(round(sw * 0.28)))
                ix1 = min(x1, x0 + int(round(sw * 0.72)))
                core_mask = arrow_mask[iy0:iy1, ix0:ix1] > 0
                core_valid_ratio = float(np.mean(core_mask)) if core_mask.size else 1.0
            else:
                core_valid_ratio = 1.0
            occluded = (valid_ratio < 0.30) or (core_valid_ratio < 0.35)

            bg_samples = np.concatenate(bg_parts, axis=0) if bg_parts else np.empty((0, 3), dtype=np.uint8)
            expected_bg = l_bg if parity == 0 else d_bg
            if len(bg_samples) >= 4:
                local_bg = np.median(bg_samples.astype(np.float32), axis=0)
                has_measured_bg.append(True)
            else:
                local_bg = expected_bg
                has_measured_bg.append(False)
            raw_local_bgs.append(local_bg)

            if len(valid_center_px) >= 12:
                px_f = valid_center_px.astype(np.float32)
                delta_local = np.abs(px_f - local_bg)
                dist_local = delta_local.mean(axis=1)
                max_local = delta_local.max(axis=1)
                if np.linalg.norm(local_bg - expected_bg) < 16.0:
                    delta_par = np.abs(px_f - expected_bg)
                    dist_mean = np.minimum(dist_local, delta_par.mean(axis=1))
                    dist_max = np.minimum(max_local, delta_par.max(axis=1))
                else:
                    dist_mean = dist_local
                    dist_max = max_local
                fg_mask = (dist_mean > 15.0) | (dist_max > 22.0)
                fg_frac = float(np.mean(fg_mask))
                occupied = fg_frac >= 0.12
                if np.any(fg_mask):
                    fg_bgr = np.median(px_f[fg_mask], axis=0)
                else:
                    fg_bgr = local_bg
            else:
                fg_frac = 0.0
                occupied = False
                fg_bgr = local_bg

            fg_lum = float(0.114 * fg_bgr[0] + 0.587 * fg_bgr[1] + 0.299 * fg_bgr[2])
            patch_28 = cv2.resize(center_bgr, (28, 28), interpolation=cv2.INTER_AREA)

            obs_list.append(
                _SquareObs(
                    row=r,
                    col=c,
                    sq_idx=sq_idx,
                    occupied=occupied,
                    occluded=occluded,
                    fg_frac=fg_frac,
                    fg_bgr=fg_bgr,
                    fg_lum=fg_lum,
                    highlight_score=0.0,
                    patch_bgr=patch_28,
                )
            )

    # Compute highlight scores relative to same-parity squares using corner samples
    # (corner bands stay clear of center arrow shafts/heads, preserving (e2, e4) highlights).
    for par in (0, 1):
        bgs = [raw_local_bgs[i] for i in range(64) if parities[i] == par and has_measured_bg[i]]
        if len(bgs) >= 8:
            par_med = np.median(np.stack(bgs, axis=0), axis=0)
            for i in range(64):
                if parities[i] == par and has_measured_bg[i]:
                    obs_list[i].highlight_score = float(np.linalg.norm(raw_local_bgs[i] - par_med))

    return obs_list


class BoardDetector:
    """Stateful screen-vision detector combining start calibration, FIDE rules, and early highlights."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.bounds: BoardBounds | None = None
        self.calibrated: bool = False
        self.flipped: bool = False
        self.state: ChessBoardState | None = None
        self._prev_state: ChessBoardState | None = None
        self._awaiting_first_move_verify: bool = False
        self._white_fg_bgr: np.ndarray | None = None
        self._black_fg_bgr: np.ndarray | None = None
        self._prev_patches: dict[int, np.ndarray] = {}
        self._piece_patches: dict[str, np.ndarray] = {}  # canonical 28x28 piece appearance per FEN char

    @staticmethod
    def _is_start_occupancy(obs: list[_SquareObs]) -> bool:
        top_occ = sum(1 for o in obs if o.row in (0, 1) and (o.occupied or o.occluded))
        bot_occ = sum(1 for o in obs if o.row in (6, 7) and (o.occupied or o.occluded))
        mid_occ = sum(1 for o in obs if o.row in (2, 3, 4, 5) and o.occupied and not o.occluded)
        return top_occ >= 14 and bot_occ >= 14 and mid_occ == 0

    def _calibrate_start(self, img_bgr: np.ndarray, bounds: BoardBounds, obs: list[_SquareObs]) -> DetectionResult:
        top_fgs = [o.fg_bgr for o in obs if o.row in (0, 1) and o.occupied and not o.occluded]
        bot_fgs = [o.fg_bgr for o in obs if o.row in (6, 7) and o.occupied and not o.occluded]
        top_lum = float(np.median([0.114 * b[0] + 0.587 * b[1] + 0.299 * b[2] for b in top_fgs])) if top_fgs else 0.0
        bot_lum = float(np.median([0.114 * b[0] + 0.587 * b[1] + 0.299 * b[2] for b in bot_fgs])) if bot_fgs else 255.0

        flipped = bot_lum < top_lum - 5.0
        self.bounds = bounds
        self.calibrated = True
        self.flipped = flipped
        self.state = ChessBoardState.starting_position()
        self._prev_state = None
        self._awaiting_first_move_verify = True

        self._white_fg_bgr = np.median(np.stack(top_fgs if flipped else bot_fgs, axis=0), axis=0)
        self._black_fg_bgr = np.median(np.stack(bot_fgs if flipped else top_fgs, axis=0), axis=0)
        self._record_patches(obs, flipped)
        self._capture_start_piece_patches(obs, flipped)

        return DetectionResult(
            status="ok",
            bounds=bounds,
            fen=self.state.to_fen(),
            flipped=self.flipped,
            board_key=self._board_key(self.state),
            turn=self.state.turn,
            last_move="",
            source="start",
        )

    def _capture_start_piece_patches(self, obs: list[_SquareObs], flipped: bool) -> None:
        self._piece_patches.clear()
        start = ChessBoardState.starting_position()
        grid = start.to_grid(flipped=flipped)
        for o in obs:
            ch = grid[o.row][o.col]
            if ch and not o.occluded:
                # Normalize lighting slightly for promotion comparison
                self._piece_patches[ch] = o.patch_bgr

    def _record_patches(self, obs: list[_SquareObs], flipped: bool) -> None:
        self._prev_patches.clear()
        for o in obs:
            sq = screen_rc_to_sq(o.row, o.col, flipped=flipped)
            if not o.occluded:
                self._prev_patches[sq] = o.patch_bgr

    @staticmethod
    def _board_key(state: ChessBoardState) -> str:
        return " ".join(state.to_fen().split(" ")[:4])

    def _classify_side(self, o: _SquareObs) -> str:
        if not o.occupied:
            return ""
        if self._white_fg_bgr is None or self._black_fg_bgr is None:
            return "w" if o.fg_lum >= 140.0 else "b"
        dw = float(np.linalg.norm(o.fg_bgr - self._white_fg_bgr))
        db = float(np.linalg.norm(o.fg_bgr - self._black_fg_bgr))
        return "w" if dw <= db else "b"

    def _infer_promotion_piece(self, obs_by_sq: dict[int, _SquareObs], to_sq: int, side: str) -> str:
        o = obs_by_sq.get(to_sq)
        if o is None or o.occluded or not self._piece_patches:
            return "q"
        best_p = "q"
        best_err = 1e18
        for ch_lower in ("q", "n", "r", "b"):
            ch = ch_lower.upper() if side == "w" else ch_lower
            ref = self._piece_patches.get(ch)
            if ref is None:
                continue
            err = float(np.mean(np.abs(o.patch_bgr.astype(np.float32) - ref.astype(np.float32))))
            if err < best_err:
                best_err = err
                best_p = ch_lower
        return best_p

    def _crisp_highlight_pair(self, obs: list[_SquareObs]) -> tuple[int, int] | None:
        hl_sorted = sorted(obs, key=lambda x: x.highlight_score, reverse=True)
        if len(hl_sorted) >= 3:
            s2 = hl_sorted[1].highlight_score
            s3 = hl_sorted[2].highlight_score
            if s2 > 18.0 and s3 < s2 * 0.55:
                sq1 = screen_rc_to_sq(hl_sorted[0].row, hl_sorted[0].col, flipped=self.flipped)
                sq2 = screen_rc_to_sq(hl_sorted[1].row, hl_sorted[1].col, flipped=self.flipped)
                return sq1, sq2
        return None

    @staticmethod
    def _move_matches_highlight(mv: str, hl_pair: tuple[int, int] | None) -> bool:
        if hl_pair is None or len(mv) < 4:
            return True
        from vision_core.chess_rules import parse_sq

        try:
            return {parse_sq(mv[:2]), parse_sq(mv[2:4])} == set(hl_pair)
        except ValueError:
            return True

    def _resolve_2ply(
        self,
        base_state: ChessBoardState,
        first_moves: list[str],
        obs_by_sq: dict[int, _SquareObs],
        expected_sides: dict[int, str],
        hl_pair: tuple[int, int] | None,
        changed_ref: set[int] | None = None,
    ) -> tuple[ChessBoardState, ChessBoardState, str] | None:
        hits: list[tuple[ChessBoardState, ChessBoardState, str]] = []
        for mv1 in first_moves:
            if changed_ref is not None and len(changed_ref) <= 4 and not (base_state.changed_squares_after_move(mv1) & changed_ref):
                continue
            s1 = base_state.push_uci(mv1)
            for mv2 in s1.legal_moves():
                s2 = s1.push_uci(mv2)
                if self._match_state_error(s2, obs_by_sq, self.flipped, expected_sides) == 0:
                    hits.append((s1, s2, mv2))
                    if len(hits) > 8:
                        break
            if len(hits) > 8:
                break
        hl_hits = [p for p in hits if self._move_matches_highlight(p[2], hl_pair)]
        if hl_hits:
            hits = hl_hits
        return hits[0] if len(hits) == 1 else None

    def _refine_promotion(
        self, mv: str, obs_by_sq: dict[int, _SquareObs], side: str
    ) -> str:
        if len(mv) != 5:
            return mv
        from vision_core.chess_rules import parse_sq

        to_sq = parse_sq(mv[2:4])
        return mv[:4] + self._infer_promotion_piece(obs_by_sq, to_sq, side)

    def _commit_transition(
        self,
        next_state: ChessBoardState,
        last_move: str,
        bounds: BoardBounds,
        obs: list[_SquareObs],
        source: str,
        prev_state: ChessBoardState | None = None,
    ) -> DetectionResult:
        self._prev_state = self.state if prev_state is None else prev_state
        self.state = next_state
        self._awaiting_first_move_verify = False
        self._record_patches(obs, self.flipped)
        return DetectionResult(
            status="ok",
            bounds=bounds,
            fen=self.state.to_fen(),
            flipped=self.flipped,
            board_key=self._board_key(self.state),
            turn=self.state.turn,
            last_move=last_move,
            source=source,
        )

    def _match_state_error(
        self,
        candidate: ChessBoardState,
        obs_by_sq: dict[int, _SquareObs],
        flipped: bool,
        expected_sides: dict[int, str],
    ) -> int:
        err = 0
        for sq in range(64):
            o = obs_by_sq[sq]
            if o.occluded:
                continue
            p = candidate.board[sq]
            want_occ = bool(p)
            if o.occupied != want_occ:
                err += 2
                continue
            if want_occ:
                want_side = piece_side(p)
                got_side = expected_sides.get(sq, "")
                if got_side and got_side != want_side:
                    err += 1
        return err

    def process_frame(
        self,
        img_bgr: np.ndarray,
        arrow_px: tuple[float, float, float, float, float] | None = None,
    ) -> DetectionResult:
        bounds = locate_board_bgr(img_bgr, hint_bounds=self.bounds)
        if bounds is None:
            return DetectionResult(status="no_board")

        # Update bounds; keep calibration if user hasn't started a new uncalibrated mid-game
        arrow_mask = _build_board_arrow_mask(bounds, arrow_px)
        tentative_flipped = self.flipped if self.calibrated else False
        obs = _extract_square_observations(img_bgr, bounds, tentative_flipped, arrow_mask)

        # Uncalibrated -> require start position first
        if not self.calibrated or self.state is None:
            if self._is_start_occupancy(obs):
                return self._calibrate_start(img_bgr, bounds, obs)
            self.bounds = bounds
            return DetectionResult(status="need_start_pos", bounds=bounds)

        # If start position reappears after moves were already played, reset cleanly to Move 1
        if self.state.fullmove > 1 or self.state.turn == "b":
            if self._is_start_occupancy(obs):
                return self._calibrate_start(img_bgr, bounds, obs)

        self.bounds = bounds

        # Move 1 orientation auto-verification: White ALWAYS moves first in FIDE chess
        if self._awaiting_first_move_verify and self.state.fullmove == 1 and self.state.turn == "w":
            top_empty = sum(1 for o in obs if o.row in (0, 1) and not o.occupied and not o.occluded)
            top_mid = sum(1 for o in obs if o.row in (2, 3) and o.occupied and not o.occluded)
            bot_empty = sum(1 for o in obs if o.row in (6, 7) and not o.occupied and not o.occluded)
            bot_mid = sum(1 for o in obs if o.row in (4, 5) and o.occupied and not o.occluded)

            if (top_empty >= 1 and top_mid >= 1) and not (bot_empty >= 1 and bot_mid >= 1):
                if not self.flipped:
                    self.flipped = True
                    self._white_fg_bgr, self._black_fg_bgr = self._black_fg_bgr, self._white_fg_bgr
                    obs = _extract_square_observations(img_bgr, bounds, True, arrow_mask)
                    self._record_patches(obs, True)
                    self._capture_start_piece_patches(obs, True)
            elif (bot_empty >= 1 and bot_mid >= 1) and not (top_empty >= 1 and top_mid >= 1):
                if self.flipped:
                    self.flipped = False
                    self._white_fg_bgr, self._black_fg_bgr = self._black_fg_bgr, self._white_fg_bgr
                    obs = _extract_square_observations(img_bgr, bounds, False, arrow_mask)
                    self._record_patches(obs, False)
                    self._capture_start_piece_patches(obs, False)

        obs_by_sq = {screen_rc_to_sq(o.row, o.col, flipped=self.flipped): o for o in obs}
        expected_sides = {sq: self._classify_side(o) for sq, o in obs_by_sq.items()}

        # Detect changed squares relative to current tracked FIDE state
        changed_occ: set[int] = set()
        changed_visual: set[int] = set()
        for sq in range(64):
            o = obs_by_sq[sq]
            if o.occluded:
                continue
            cur_piece = self.state.board[sq]
            want_occ = bool(cur_piece)
            if o.occupied != want_occ:
                changed_occ.add(sq)
                changed_visual.add(sq)
            elif want_occ:
                got_side = expected_sides[sq]
                if got_side and got_side != piece_side(cur_piece):
                    changed_visual.add(sq)
                elif sq in self._prev_patches:
                    # Also flag strong foreground appearance change (e.g. capture / promotion)
                    old_p = self._prev_patches[sq]
                    if old_p.shape == o.patch_bgr.shape:
                        diff = float(np.mean(np.abs(o.patch_bgr.astype(np.float32) - old_p.astype(np.float32))))
                        if diff > 24.0:
                            changed_visual.add(sq)

        hl_pair = self._crisp_highlight_pair(obs)
        hl_mv: str | None = None
        if hl_pair is not None:
            hl_hits = self.state.infer_move_from_highlights(*hl_pair)
            if len(hl_hits) == 1:
                hl_mv = hl_hits[0]

        # 1. Steady state: board already matches self.state completely
        if not changed_occ and not (changed_visual and len(changed_visual) >= 2):
            # Still check crisp 2-square highlights for instantaneous pre-slide speculation!
            if hl_mv is not None:
                return self._commit_transition(self.state.push_uci(hl_mv), hl_mv, bounds, obs, "highlight")

            self._record_patches(obs, self.flipped)
            return DetectionResult(
                status="ok",
                bounds=bounds,
                fen=self.state.to_fen(),
                flipped=self.flipped,
                board_key=self._board_key(self.state),
                turn=self.state.turn,
                last_move="",
                source="steady",
            )

        # 2. Match exact 1-ply FIDE legal move against changed squares + occupancy/sides
        legal = self.state.legal_moves()
        if legal:
            changed_ref = changed_visual if changed_visual else changed_occ
            occ_colors = {sq: expected_sides[sq] for sq in changed_ref if sq in expected_sides}
            exact_hits = self.state.infer_move_for_changed_squares(changed_ref, occ_colors)
            if not exact_hits and changed_occ and changed_occ != changed_ref:
                occ_occ = {sq: expected_sides[sq] for sq in changed_occ if sq in expected_sides}
                exact_hits = self.state.infer_move_for_changed_squares(changed_occ, occ_occ)
            if not exact_hits:
                exact_hits = self.state.infer_move_for_changed_squares(changed_occ or changed_ref)
            exact_mv = exact_hits[0] if len(exact_hits) == 1 else None

            if exact_mv is None:
                # Score all legal 1-ply moves by total unoccluded board error
                best_err = 999
                second_err = 999
                best_mv = None
                for mv in legal:
                    ns = self.state.push_uci(mv)
                    err = self._match_state_error(ns, obs_by_sq, self.flipped, expected_sides)
                    if err < best_err:
                        second_err = best_err
                        best_err = err
                        best_mv = mv
                    elif err < second_err:
                        second_err = err
                if best_mv is not None and best_err == 0 and second_err > 0:
                    exact_mv = best_mv

            # Guard against transient mid-slide mismatch (e.g. e2->e4 crossing e3 while (e2,e4) are lit)
            if hl_mv is not None:
                if exact_mv is not None and exact_mv[:4] != hl_mv[:4]:
                    exact_mv = None
                elif exact_mv is None and changed_occ <= self.state.changed_squares_after_move(hl_mv):
                    ns_hl = self.state.push_uci(hl_mv)
                    if self._match_state_error(ns_hl, obs_by_sq, self.flipped, expected_sides) == 0:
                        exact_mv = hl_mv

            if exact_mv is not None:
                exact_mv = self._refine_promotion(exact_mv, obs_by_sq, self.state.turn)
                return self._commit_transition(self.state.push_uci(exact_mv), exact_mv, bounds, obs, "move")

            # 3. Slip correction against _prev_state (handles transient animation slip or takeback)
            if self._prev_state is not None:
                prev_legal = self._prev_state.legal_moves()
                slip_hits = [
                    mv for mv in prev_legal
                    if self._match_state_error(self._prev_state.push_uci(mv), obs_by_sq, self.flipped, expected_sides) == 0
                ]
                slip_hl = [mv for mv in slip_hits if self._move_matches_highlight(mv, hl_pair)]
                if len(slip_hl) == 1:
                    slip_hits = slip_hl
                if len(slip_hits) == 1:
                    mv = self._refine_promotion(slip_hits[0], obs_by_sq, self._prev_state.turn)
                    return self._commit_transition(
                        self._prev_state.push_uci(mv), mv, bounds, obs, "resync", prev_state=self._prev_state
                    )

                if len(changed_occ) <= 6:
                    rec_prev = self._resolve_2ply(self._prev_state, prev_legal, obs_by_sq, expected_sides, hl_pair)
                    if rec_prev is not None:
                        s1, s2, mv2 = rec_prev
                        return self._commit_transition(s2, mv2, bounds, obs, "resync", prev_state=s1)

            # 4. Forward 2-ply legal recovery (handles user tab-switching back 1 full turn later)
            if len(changed_occ) <= 6:
                rec_fwd = self._resolve_2ply(
                    self.state, legal, obs_by_sq, expected_sides, hl_pair, changed_ref=changed_ref
                )
                if rec_fwd is not None:
                    s1, s2, mv2 = rec_fwd
                    return self._commit_transition(s2, mv2, bounds, obs, "resync", prev_state=s1)

        # Transient animation or unclear frame: keep existing stable state cleanly
        return DetectionResult(
            status="ok",
            bounds=bounds,
            fen=self.state.to_fen(),
            flipped=self.flipped,
            board_key=self._board_key(self.state),
            turn=self.state.turn,
            last_move="",
            source="steady",
        )
