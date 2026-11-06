import json
import os
import secrets
import time
import urllib.error
import urllib.request
from license_core.crypto_ed25519 import ED25519_PUBLIC_KEY_HEX, verify_response_signature
from license_core.hwid import get_hwid

APP_VERSION = "2.0.0"
OFFLINE_CACHE_TTL = 4 * 3600  # Cache hợp lệ trong 4 giờ nếu mất mạng tạm thời

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ChessStealthPro")
os.makedirs(APP_DIR, exist_ok=True)
CACHE_FILE = os.path.join(APP_DIR, "verified_session.json")

# Biến trạng thái phân tán dùng để kiểm tra rải rác ở nhiều điểm trong code (Chống byte-patch 1 chỗ)
_ACTIVE_SESSION_PAYLOAD: dict | None = None
_ACTIVE_SESSION_SIGNATURE: str = ""


def _save_offline_cache(payload: dict, signature: str) -> None:
    record = {
        "payload": payload,
        "signature": signature,
        "cached_at": int(time.time()),
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(record, f)
    except Exception:
        pass


def load_valid_offline_cache(expected_key: str, hwid: str) -> tuple[bool, str]:
    """
    Kiểm tra bộ nhớ đệm đã ký Ed25519 nếu người dùng tạm thời mất kết nối mạng (< 4 giờ).
    Bắt buộc kiểm tra lại chữ ký Ed25519 từ file cache để chống chỉnh sửa file JSON.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    if not os.path.exists(CACHE_FILE):
        return False, ""
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            record = json.load(f)
        payload = record.get("payload", {})
        sig = record.get("signature", "")
        cached_at = int(record.get("cached_at", 0))
        now = int(time.time())

        # Chống tua ngược đồng hồ máy tính hoặc quá hạn cache 4 giờ
        if now < cached_at - 60 or (now - cached_at) > OFFLINE_CACHE_TTL:
            return False, ""

        if payload.get("key") != expected_key.strip().upper() or payload.get("hwid") != hwid:
            return False, ""

        exp = payload.get("expires_at")
        if exp is not None and now >= int(exp):
            return False, ""

        if not verify_response_signature(payload, sig, ED25519_PUBLIC_KEY_HEX):
            return False, ""

        _ACTIVE_SESSION_PAYLOAD = payload
        _ACTIVE_SESSION_SIGNATURE = sig
        return True, f"{payload.get('message', 'Hợp lệ')} (Offline Cache)"
    except Exception:
        return False, ""


def activate_or_verify_key(
    api_base_url: str, key_str: str, hwid: str | None = None
) -> tuple[bool, str]:
    """
    Thực hiện tuần tự:
    1. Gọi POST /verify (hoặc POST /activate nếu key chưa gắn HWID).
    2. Kiểm tra chữ ký số Ed25519 bằng Public Key nhúng cứng + kiểm tra Nonce chống Replay Attack.
    3. Lưu cache có chữ ký Ed25519 nếu thành công.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    hwid_val = hwid or get_hwid()
    clean_key = key_str.strip().upper()

    for endpoint in ("/verify", "/activate"):
        nonce = secrets.token_hex(16)
        req_body = json.dumps(
            {
                "key": clean_key,
                "hwid": hwid_val,
                "app_version": APP_VERSION,
                "nonce": nonce,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{api_base_url.rstrip('/')}{endpoint}",
            data=req_body,
            headers={"Content-Type": "application/json", "User-Agent": f"ChessStealthPro/{APP_VERSION}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                resp_data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                resp_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                continue
        except Exception:
            # Nếu mất mạng, thử kiểm tra Offline Cache đã ký Ed25519
            cached_ok, cached_msg = load_valid_offline_cache(clean_key, hwid_val)
            if cached_ok:
                return True, cached_msg
            return False, "ERR_NET_UNREACHABLE: Không thể kết nối máy chủ xác thực."

        # Nếu /verify báo key chưa kích hoạt lần đầu -> chuyển sang /activate
        if endpoint == "/verify" and resp_data.get("status") == "unactivated":
            continue

        sig = resp_data.get("signature", "")
        # Xác thực chữ ký Ed25519 + Nonce + HWID (Chống Proxy / MITM / Replay)
        if not verify_response_signature(resp_data, sig, ED25519_PUBLIC_KEY_HEX):
            return False, "ERR_SIG_MISMATCH: Phát hiện can thiệp dữ liệu mạng (MITM/Proxy)!"

        if resp_data.get("nonce") != nonce:
            return False, "ERR_NONCE_REPLAY: Phản hồi mạng không hợp lệ (Replay Attack)!"

        if resp_data.get("valid") is True and resp_data.get("hwid") == hwid_val:
            _ACTIVE_SESSION_PAYLOAD = resp_data
            _ACTIVE_SESSION_SIGNATURE = sig
            _save_offline_cache(resp_data, sig)
            return True, str(resp_data.get("message", "Kích hoạt thành công"))
        else:
            if endpoint == "/verify" and "chưa được kích hoạt" in str(resp_data.get("message", "")).lower():
                continue
            return False, str(resp_data.get("message", "Mã Key không hợp lệ."))

    return False, "Xác thực thất bại."


def derive_arrow_scale_factor() -> float:
    """
    [CHỐNG CRACK RẢI RÁC NHIỀU ĐIỂM]
    Hàm này được gọi trực tiếp bên trong công thức toán học vẽ đa giác mũi tên (render_loop).
    Nếu Cracker dùng x64dbg / byte-patch bỏ qua cửa sổ nhập Key mà không có chữ ký Ed25519 hợp lệ
    trong bộ nhớ, hệ số tỷ lệ sẽ trả về 0.0 -> mũi tên có kích thước bằng 0 (vô hình).
    """
    if not _ACTIVE_SESSION_PAYLOAD or not _ACTIVE_SESSION_SIGNATURE:
        return 0.0
    if not verify_response_signature(
        _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE, ED25519_PUBLIC_KEY_HEX
    ):
        return 0.0
    exp = _ACTIVE_SESSION_PAYLOAD.get("expires_at")
    if exp is not None and int(time.time()) > int(exp):
        return 0.0
    return 1.0
