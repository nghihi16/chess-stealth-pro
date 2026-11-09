import json
import os
import secrets
import time
import urllib.error
import urllib.request
from db.database import cleanup_expired_records, ensure_web24h_key_in_db, get_connection
from license_core.crypto_ed25519 import (
    ED25519_PUBLIC_KEY_HEX,
    sign_response_payload,
    verify_response_signature,
)
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


def _direct_local_verify_or_activate(clean_key: str, hwid_val: str, nonce: str) -> dict:
    """
    Xác thực/kích hoạt Key cục bộ bằng SQLite và ký số Ed25519 (Tốc độ 0.001s, không phụ thuộc mạng).
    """
    now = int(time.time())
    with get_connection() as conn:
        cleanup_expired_records(conn)
        ensure_web24h_key_in_db(conn, clean_key)
        row = conn.execute(
            "SELECT * FROM licenses WHERE key = ?", (clean_key,)
        ).fetchone()

        if not row:
            payload = {
                "valid": False,
                "key": clean_key,
                "type": None,
                "status": "invalid",
                "hwid": None,
                "expires_at": None,
                "message": "Invalid license key.",
                "server_time": now,
                "nonce": nonce,
            }
            payload["signature"] = sign_response_payload(payload)
            return payload

        if row["status"] != "active":
            payload = {
                "valid": False,
                "key": clean_key,
                "type": row["type"],
                "status": row["status"],
                "hwid": row["hwid"],
                "expires_at": row["expires_at"],
                "message": f"License key is {row['status']}.",
                "server_time": now,
                "nonce": nonce,
            }
            payload["signature"] = sign_response_payload(payload)
            return payload

        if row["hwid"] and row["hwid"] != hwid_val:
            payload = {
                "valid": False,
                "key": clean_key,
                "type": row["type"],
                "status": "hwid_mismatch",
                "hwid": row["hwid"],
                "expires_at": row["expires_at"],
                "message": "This key is bound to another device.",
                "server_time": now,
                "nonce": nonce,
            }
            payload["signature"] = sign_response_payload(payload)
            return payload

        expires_at = row["expires_at"]
        activated_at = row["activated_at"] or now
        if not row["hwid"]:
            if row["type"] == "trial_24h" and not expires_at:
                expires_at = now + 86400
            elif row["type"] == "monthly" and not expires_at:
                expires_at = now + (30 * 86400)
            elif row["type"] == "lifetime":
                expires_at = None

            conn.execute(
                """
                UPDATE licenses
                SET hwid = ?, activated_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (hwid_val, activated_at, expires_at, row["id"]),
            )
            conn.commit()

        conn.execute(
            """
            INSERT INTO activation_logs (license_id, hwid, ip, app_version, action, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (row["id"], hwid_val, "supabase-client", APP_VERSION, "activate_or_verify", now),
        )
        conn.commit()

        label_map = {
            "trial_24h": "24-Hour Key",
            "monthly": "30-Day Key",
            "lifetime": "Lifetime Key",
        }
        payload = {
            "valid": True,
            "key": clean_key,
            "type": row["type"],
            "status": "active",
            "hwid": hwid_val,
            "expires_at": expires_at,
            "message": f"Activated: {label_map.get(row['type'], row['type'])}",
            "server_time": now,
            "nonce": nonce,
        }
        payload["signature"] = sign_response_payload(payload)
        return payload


def activate_or_verify_key(
    api_base_url: str, key_str: str, hwid: str | None = None
) -> tuple[bool, str]:
    """
    Thực hiện tuần tự:
    1. Gọi POST /verify (hoặc POST /activate nếu key chưa gắn HWID), hoặc kết nối thẳng Supabase Cloud.
    2. Kiểm tra chữ ký số Ed25519 bằng Public Key nhúng cứng + kiểm tra Nonce chống Replay Attack.
    3. Lưu cache có chữ ký Ed25519 nếu thành công.
    """
    global _ACTIVE_SESSION_PAYLOAD, _ACTIVE_SESSION_SIGNATURE
    hwid_val = hwid or get_hwid()
    clean_key = key_str.strip().upper()

    # Khóa sinh từ Web (FREE24H-, PRO07D-, PRO30D-, LIFEVIP-): Xác thực HMAC cục bộ 0.001s
    crypto_prefixes = ("FREE24H-", "PRO07D-", "PRO30D-", "LIFEVIP-")
    if any(clean_key.startswith(p) for p in crypto_prefixes):
        nonce = secrets.token_hex(16)
        resp_data = _direct_local_verify_or_activate(clean_key, hwid_val, nonce)
        if resp_data.get("valid") is True and resp_data.get("hwid") == hwid_val:
            sig = resp_data.get("signature", "")
            _ACTIVE_SESSION_PAYLOAD = resp_data
            _ACTIVE_SESSION_SIGNATURE = sig
            _save_offline_cache(resp_data, sig)
            return True, str(resp_data.get("message", "Activated"))
        return False, "Invalid Key"

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
        resp_data = None
        try:
            with urllib.request.urlopen(req, timeout=3) as res:
                resp_data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                resp_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                continue
        except Exception:
            # Xác thực trực tiếp qua SQLite engine nội bộ
            try:
                resp_data = _direct_local_verify_or_activate(clean_key, hwid_val, nonce)
            except Exception:
                cached_ok, cached_msg = load_valid_offline_cache(clean_key, hwid_val)
                if cached_ok:
                    return True, cached_msg
                return False, "Cannot connect to license server."

        if endpoint == "/verify" and resp_data.get("status") == "unactivated":
            continue

        sig = resp_data.get("signature", "")
        if not verify_response_signature(resp_data, sig, ED25519_PUBLIC_KEY_HEX):
            return False, "Invalid Key"

        if resp_data.get("nonce") != nonce:
            return False, "Invalid Key"

        if resp_data.get("valid") is True and resp_data.get("hwid") == hwid_val:
            _ACTIVE_SESSION_PAYLOAD = resp_data
            _ACTIVE_SESSION_SIGNATURE = sig
            _save_offline_cache(resp_data, sig)
            return True, str(resp_data.get("message", "Activated"))
        else:
            if endpoint == "/verify" and "not activated" in str(resp_data.get("message", "")).lower():
                continue
            return False, "Invalid Key"

    return False, "Invalid Key"


def derive_arrow_scale_factor() -> float:
    """
    [CHỐNG CRACK RẢI RÁC NHIỀM ĐIỂM]
    Hàm này được gọi trực tiếp bên trong công thức toán học vẽ đa giác mũi tên (render_loop).
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
