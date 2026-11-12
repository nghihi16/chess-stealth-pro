import json
import os
import secrets
import time
import urllib.error
import urllib.request
from license_core.crypto_ed25519 import (
    ED25519_PUBLIC_KEY_HEX,
    verify_response_signature,
)
from license_core.hwid import get_hwid

APP_VERSION = "2.0.0"
OFFLINE_CACHE_TTL = 4 * 3600  # Cache hợp lệ trong 4 giờ nếu mất mạng tạm thời

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ChessStealthPro")
os.makedirs(APP_DIR, exist_ok=True)
CACHE_FILE = os.path.join(APP_DIR, "verified_session.json")
CLOCK_GUARD_FILE = os.path.join(APP_DIR, "clock_state.json")
NONCE_STORE_FILE = os.path.join(APP_DIR, "used_nonces.json")

# Biến trạng thái phiên kích hoạt phân tán trong RAM
_ACTIVE_SESSION_PAYLOAD: dict | None = None
_ACTIVE_SESSION_SIGNATURE: str = ""


def _atomic_write_json(file_path: str, data: dict | list) -> None:
    """Ghi file JSON nguyên tử (atomic write) thông qua file .tmp và os.replace."""
    tmp_path = f"{file_path}.tmp"
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


# ============================================================================
# 1. ANTI-CLOCK ROLLBACK (BẢO VỆ CHỐNG LÙI GIỜ HỆ THỐNG GIAN LẬN HẠN DÙNG)
# ============================================================================
_PROCESS_START_MONOTONIC: float = time.monotonic()
_PROCESS_START_WALL: float = time.time()
_LAST_CHECKED_MONOTONIC: float = _PROCESS_START_MONOTONIC
_LAST_CHECKED_WALL: float = _PROCESS_START_WALL

# In-memory High-Water Mark cache để tránh Disk I/O trong render loop (paintEvent 60 FPS)
_PERSISTED_HIGH_WATER_MARK: int = 0
_LAST_DISK_HWM: int = 0
_CACHED_GUARD_PATH: str = ""


def _get_clock_guard_path() -> str:
    return os.environ.get("CHESSPRO_CLOCK_GUARD_PATH", CLOCK_GUARD_FILE)


def _get_persisted_high_water_mark() -> int:
    global _PERSISTED_HIGH_WATER_MARK, _LAST_DISK_HWM, _CACHED_GUARD_PATH
    guard_path = _get_clock_guard_path()
    if _PERSISTED_HIGH_WATER_MARK > 0 and _CACHED_GUARD_PATH == guard_path:
        return _PERSISTED_HIGH_WATER_MARK

    _CACHED_GUARD_PATH = guard_path
    if not os.path.exists(guard_path):
        _PERSISTED_HIGH_WATER_MARK = 0
        _LAST_DISK_HWM = 0
        return 0
    try:
        with open(guard_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        val = int(data.get("high_water_mark", 0))
        _PERSISTED_HIGH_WATER_MARK = val
        _LAST_DISK_HWM = val
        return val
    except Exception:
        _PERSISTED_HIGH_WATER_MARK = 0
        _LAST_DISK_HWM = 0
        return 0


def _save_high_water_mark(ts: int) -> None:
    global _PERSISTED_HIGH_WATER_MARK, _LAST_DISK_HWM, _CACHED_GUARD_PATH
    ts_int = int(ts)
    guard_path = _get_clock_guard_path()
    _CACHED_GUARD_PATH = guard_path
    if ts_int > _PERSISTED_HIGH_WATER_MARK or _PERSISTED_HIGH_WATER_MARK == 0:
        _PERSISTED_HIGH_WATER_MARK = ts_int
    _LAST_DISK_HWM = ts_int
    _atomic_write_json(guard_path, {"high_water_mark": ts_int, "updated_at": int(time.time())})


def check_anti_rollback() -> tuple[bool, str]:
    """
    Kiểm tra chống gian lận quay lui đồng hồ (Anti-Clock Rollback):
    1. Monotonic timer: Phát hiện đồng hồ bị lùi so với thời gian trôi qua thực tế của CPU.
    2. Persistent High-Water Mark: Phát hiện time.time() nhỏ hơn mốc thời gian cao nhất từng ghi nhận.
    """
    global _LAST_CHECKED_MONOTONIC, _LAST_CHECKED_WALL, _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    global _PERSISTED_HIGH_WATER_MARK
    now_wall = time.time()
    now_mono = time.monotonic()

    # 1. Monotonic divergence check
    mono_elapsed = now_mono - _PROCESS_START_MONOTONIC
    wall_elapsed = now_wall - _PROCESS_START_WALL
    if wall_elapsed < (mono_elapsed - 15.0):
        _ACTIVE_SESSION_PAYLOAD = None
        _ACTIVE_SESSION_SIGNATURE = ""
        return False, "Clock rollback detected via monotonic clock tracking"

    # 2. High-water mark check
    hwm = _get_persisted_high_water_mark()
    now_int = int(now_wall)
    if now_int < (hwm - 60):
        _ACTIVE_SESSION_PAYLOAD = None
        _ACTIVE_SESSION_SIGNATURE = ""
        return False, "Clock rollback detected: system time is behind persistent high-water mark"

    # Memory cache update
    if now_int > _PERSISTED_HIGH_WATER_MARK:
        _PERSISTED_HIGH_WATER_MARK = now_int

    # Disk updates to clock_state.json are throttled: only rewrite if now_int >= _LAST_DISK_HWM + 60 or on initial startup
    if now_int >= (_LAST_DISK_HWM + 60) or _LAST_DISK_HWM == 0:
        _save_high_water_mark(now_int)

    _LAST_CHECKED_MONOTONIC = now_mono
    _LAST_CHECKED_WALL = now_wall
    return True, "Clock OK"


def reset_clock_guard_for_testing() -> None:
    """Helper cho unit tests thiết lập lại trạng thái đồng hồ."""
    global _PROCESS_START_MONOTONIC, _PROCESS_START_WALL, _LAST_CHECKED_MONOTONIC, _LAST_CHECKED_WALL
    global _PERSISTED_HIGH_WATER_MARK, _LAST_DISK_HWM, _CACHED_GUARD_PATH
    _PROCESS_START_MONOTONIC = time.monotonic()
    _PROCESS_START_WALL = time.time()
    _LAST_CHECKED_MONOTONIC = _PROCESS_START_MONOTONIC
    _LAST_CHECKED_WALL = _PROCESS_START_WALL
    _PERSISTED_HIGH_WATER_MARK = 0
    _LAST_DISK_HWM = 0
    _CACHED_GUARD_PATH = ""
    guard_path = _get_clock_guard_path()
    if os.path.exists(guard_path):
        try:
            os.remove(guard_path)
        except OSError:
            pass


# ============================================================================
# 2. REQUEST NONCE TRACKING & REPLAY PREVENTION
# ============================================================================
_USED_NONCES: set[str] = set()


def _get_nonce_store_path() -> str:
    return os.environ.get("CHESSPRO_NONCE_STORE_PATH", NONCE_STORE_FILE)


def _load_used_nonces() -> set[str]:
    global _USED_NONCES
    store_path = _get_nonce_store_path()
    if os.path.exists(store_path):
        try:
            with open(store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    _USED_NONCES.update(data)
        except Exception:
            pass
    return _USED_NONCES


def _persist_used_nonce(nonce: str) -> None:
    global _USED_NONCES
    _USED_NONCES.add(nonce)
    store_path = _get_nonce_store_path()
    recent = list(_USED_NONCES)[-5000:]
    _atomic_write_json(store_path, recent)


def is_nonce_used(nonce: str) -> bool:
    """Kiểm tra xem nonce đã từng được sử dụng để chống Replay Attack."""
    if not nonce:
        return True
    if not _USED_NONCES:
        _load_used_nonces()
    return nonce in _USED_NONCES


def mark_nonce_used(nonce: str) -> None:
    """Ghi nhận nonce đã được sử dụng."""
    if nonce:
        _persist_used_nonce(nonce)


def reset_nonce_store_for_testing() -> None:
    """Helper cho unit tests thiết lập lại danh sách nonces."""
    global _USED_NONCES
    _USED_NONCES.clear()
    store_path = _get_nonce_store_path()
    if os.path.exists(store_path):
        try:
            os.remove(store_path)
        except OSError:
            pass


# ============================================================================
# 3. OFFLINE CACHE (ED25519 SIGNED)
# ============================================================================
def _get_cache_path() -> str:
    return os.environ.get("CHESSPRO_CACHE_PATH", CACHE_FILE)


def _save_offline_cache(payload: dict, signature: str) -> None:
    cache_path = _get_cache_path()
    record = {
        "payload": payload,
        "signature": signature,
        "cached_at": int(time.time()),
    }
    _atomic_write_json(cache_path, record)


def load_valid_offline_cache(expected_key: str, hwid: str) -> tuple[bool, str]:
    """
    Kiểm tra bộ nhớ đệm đã ký Ed25519 nếu người dùng tạm thời mất kết nối mạng (< 4 giờ).
    Bắt buộc kiểm tra lại chữ ký Ed25519 từ file cache và kiểm tra anti-rollback.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    clock_ok, _ = check_anti_rollback()
    if not clock_ok:
        return False, ""

    cache_path = _get_cache_path()
    if not os.path.exists(cache_path):
        return False, ""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            record = json.load(f)
        payload = record.get("payload", {})
        sig = record.get("signature", "")
        cached_at = int(record.get("cached_at", 0))
        now = int(time.time())

        # Anti-rollback trên cache: Nếu thời gian hiện tại nhỏ hơn thời điểm cache
        if now < cached_at - 60 or (now - cached_at) > OFFLINE_CACHE_TTL:
            return False, ""

        # Enforce server_time anchor: payload server_time as an immutable high-water mark floor
        # that cannot be bypassed even if clock_state.json was wiped or deleted
        server_time = int(payload.get("server_time", 0))
        if server_time > 0 and now < (server_time - 60):
            return False, ""

        if payload.get("key") != expected_key.strip().upper() or payload.get("hwid") != hwid:
            return False, ""

        exp = payload.get("expires_at")
        if exp is not None and now >= int(exp):
            return False, ""

        # Xác thực chữ ký Ed25519 của Server từ cache
        if not verify_response_signature(payload, sig, ED25519_PUBLIC_KEY_HEX):
            return False, ""

        # Cập nhật high-water mark từ server_time nếu lớn hơn
        if server_time > _get_persisted_high_water_mark():
            _save_high_water_mark(server_time)

        _ACTIVE_SESSION_PAYLOAD = payload
        _ACTIVE_SESSION_SIGNATURE = sig
        return True, f"{payload.get('message', 'Valid')} (Offline Cache)"
    except Exception:
        return False, ""


# ============================================================================
# 4. ACTIVATION & VERIFICATION (VERIFIER ONLY - NO CLIENT SIGNING)
# ============================================================================
def activate_or_verify_key(
    api_base_url: str, key_str: str, hwid: str | None = None
) -> tuple[bool, str]:
    """
    Xác thực/Kích hoạt bản quyền:
    - Client chỉ hoạt động như một Verifier thuần túy.
    - Không chứa Private Key, không tự ký payload cục bộ.
    - Gửi request nonce ngẫu nhiên tới server và yêu cầu chữ ký số Ed25519 đích thực.
    - Chống gian lận quay lui đồng hồ (Anti-rollback) và chống replay attack.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE

    # 1. Kiểm tra Anti-Clock Rollback trước tiên
    clock_ok, clock_err = check_anti_rollback()
    if not clock_ok:
        _ACTIVE_SESSION_PAYLOAD = None
        _ACTIVE_SESSION_SIGNATURE = ""
        return False, f"Invalid Key: {clock_err}"

    hwid_val = hwid or get_hwid()
    clean_key = key_str.strip().upper()

    # 2. Thử liên hệ License Server qua mạng
    for endpoint in ("/verify", "/activate"):
        req_nonce = secrets.token_hex(16)
        req_body = json.dumps(
            {
                "key": clean_key,
                "hwid": hwid_val,
                "app_version": APP_VERSION,
                "nonce": req_nonce,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{api_base_url.rstrip('/')}{endpoint}",
            data=req_body,
            headers={"Content-Type": "application/json", "User-Agent": f"ChessStealthPro/{APP_VERSION}"},
            method="POST",
        )
        resp_data = None
        try:
            with urllib.request.urlopen(req, timeout=3) as res:
                resp_data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                resp_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                # Neu server gap su co 5xx/HTML loi, thu tai Offline Cache truoc khi bo qua
                cached_ok, cached_msg = load_valid_offline_cache(clean_key, hwid_val)
                if cached_ok:
                    return True, cached_msg
                continue
        except Exception:
            # Nếu mất kết nối mạng, thử tải Offline Cache hợp lệ trước đó
            cached_ok, cached_msg = load_valid_offline_cache(clean_key, hwid_val)
            if cached_ok:
                return True, cached_msg
            return False, "Cannot connect to license server."

        if endpoint == "/verify" and resp_data.get("status") == "unactivated":
            continue

        # 3. Xác thực Replay Attack & Request Nonce
        resp_nonce = resp_data.get("nonce")
        if not resp_nonce or resp_nonce != req_nonce:
            return False, "Invalid Key"

        if is_nonce_used(resp_nonce):
            return False, "Invalid Key: Replay attack detected"

        # 4. Xác thực chữ ký Ed25519 của Server bằng Public Key
        sig = resp_data.get("signature", "")
        if not verify_response_signature(resp_data, sig, ED25519_PUBLIC_KEY_HEX):
            return False, "Invalid Key"

        # 5. Phản hồi hợp lệ từ Server
        if resp_data.get("valid") is True and resp_data.get("hwid") == hwid_val:
            mark_nonce_used(resp_nonce)
            # Cập nhật high-water mark từ server_time nếu có
            server_time = int(resp_data.get("server_time", 0))
            if server_time > _get_persisted_high_water_mark():
                _save_high_water_mark(server_time)

            _ACTIVE_SESSION_PAYLOAD = resp_data
            _ACTIVE_SESSION_SIGNATURE = sig
            _save_offline_cache(resp_data, sig)
            return True, str(resp_data.get("message", "Activated"))
        else:
            if endpoint == "/verify" and "not activated" in str(resp_data.get("message", "")).lower():
                continue
            return False, "Invalid Key"

    return False, "Invalid Key"


# ============================================================================
# 5. CRYPTOGRAPHIC GATING & DERIVE ARROW SCALE FACTOR
# ============================================================================
def get_crypto_verification_state() -> float:
    """
    Computes cryptographic verification state directly tied to Ed25519 signature
    and watchdog integrity. Returns 1.0 only if session has a mathematically valid
    Ed25519 signature under ED25519_PUBLIC_KEY_HEX and watchdog reports clean environment.
    Returns 0.0 if signature is missing/invalid or environment is compromised.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    if not _ACTIVE_SESSION_PAYLOAD or not _ACTIVE_SESSION_SIGNATURE:
        return 0.0
    if not verify_response_signature(
        _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE, ED25519_PUBLIC_KEY_HEX
    ):
        return 0.0
    try:
        from license_core import watchdog
        if watchdog.is_environment_compromised():
            return 0.0
        poison = watchdog.get_tamper_poison_factor()
        if poison <= 0.0:
            return 0.0
    except Exception:
        pass
    return 1.0


def derive_arrow_scale_factor() -> float:
    """
    [CHỐNG CRACK RẢI RÁC NHIỀU ĐIỂM & KIỂM TRA TOÀN VẸN CRYPTO & WATCHDOG]
    Được gọi trực tiếp trong render_loop vẽ mũi tên.
    Kiểm tra:
    1. Active session payload & signature tồn tại
    2. Flag 'valid' là True
    3. Status là 'active' hoặc 'trial' (từ chối 'revoked', 'expired', 'hwid_mismatch', 'unactivated')
    4. Chống rollback đồng hồ (Anti-rollback)
    5. Chữ ký Ed25519 của phiên hoạt động
    6. Hạn sử dụng (expires_at)
    7. Watchdog anti-debug & anti-hook integrity & poison factor
    Trả về 1.0 nếu hợp lệ, 0.0 nếu bị can thiệp / hết hạn / quay lui đồng hồ / revoked / mismatch / debugger.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE

    if not _ACTIVE_SESSION_PAYLOAD or not _ACTIVE_SESSION_SIGNATURE:
        return 0.0

    # 1. Chống bypass nghiệp vụ: Flag valid bắt buộc phải là True
    if _ACTIVE_SESSION_PAYLOAD.get("valid") is not True:
        return 0.0

    # 2. Trạng thái bản quyền bắt buộc phải là 'active' hoặc 'trial'
    status = _ACTIVE_SESSION_PAYLOAD.get("status")
    if status in ("revoked", "expired", "hwid_mismatch", "unactivated", "banned"):
        return 0.0
    if status not in ("active", "trial"):
        return 0.0

    # 3. Chống rollback đồng hồ
    clock_ok, _ = check_anti_rollback()
    if not clock_ok:
        _ACTIVE_SESSION_PAYLOAD = None
        _ACTIVE_SESSION_SIGNATURE = ""
        return 0.0

    # 4. Kiểm tra chữ ký Ed25519 và cryptographic verification state
    crypto_factor = get_crypto_verification_state()
    if crypto_factor <= 0.0:
        return 0.0

    # 5. Kiểm tra hạn dùng
    exp = _ACTIVE_SESSION_PAYLOAD.get("expires_at")
    if exp is not None and int(time.time()) > int(exp):
        return 0.0

    # 6. Kiểm tra Watchdog Anti-Debug / Anti-Hook
    try:
        from license_core import watchdog
        if watchdog.is_environment_compromised():
            return 0.0
        poison = watchdog.get_tamper_poison_factor()
        if poison <= 0.0:
            return 0.0
    except Exception:
        poison = 1.0

    return 1.0 * poison * crypto_factor
