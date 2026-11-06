import hashlib
import json
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# ============================================================================
# Ed25519 ASYMMETRIC DIGITAL SIGNATURE (CHỐNG PROXY / MITM / FAKE SERVER)
# - Server giữ Private Key (32 bytes) để ký mọi JSON response của /verify & /activate.
# - Client (ChessPro.exe / C++ binary) CHỈ nhúng cứng ED25519_PUBLIC_KEY_HEX.
# - Dù Cracker dựng server giả trả về {"valid": true}, không có Private Key thì
#   Ed25519 signature sẽ bị từ chối ngay lập tức.
# ============================================================================

_SERVER_PRIVATE_SEED = hashlib.sha256(
    b"CHESS_STEALTH_PRO_ED25519_SERVER_MASTER_SEED_2026_V2"
).digest()

_PRIVATE_KEY = ed25519.Ed25519PrivateKey.from_private_bytes(_SERVER_PRIVATE_SEED)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

# Public Key (32 bytes = 64 hex chars) nhúng cứng vào Client binary
ED25519_PUBLIC_KEY_HEX: str = _PUBLIC_KEY.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
).hex()


def canonicalize_payload(data: dict) -> bytes:
    """Chuẩn hóa các trường quan trọng của response thành chuỗi byte bất biến để ký/xác thực."""
    signed_fields = {
        "valid": bool(data.get("valid", False)),
        "key": str(data.get("key", "")),
        "type": data.get("type"),
        "status": data.get("status"),
        "hwid": data.get("hwid"),
        "expires_at": data.get("expires_at"),
        "server_time": int(data.get("server_time", 0)),
        "nonce": str(data.get("nonce", "")),
    }
    return json.dumps(signed_fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_response_payload(data: dict) -> str:
    """[CHỈ DÙNG TRÊN SERVER] Ký dữ liệu phản hồi bằng Ed25519 Private Key."""
    msg = canonicalize_payload(data)
    sig = _PRIVATE_KEY.sign(msg)
    return sig.hex()


def verify_response_signature(
    data: dict, signature_hex: str, public_key_hex: str = ED25519_PUBLIC_KEY_HEX
) -> bool:
    """[DÙNG TRÊN CLIENT] Xác thực chữ ký Ed25519 của Server bằng Public Key nhúng cứng."""
    if not signature_hex or len(signature_hex) != 128:
        return False
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        msg = canonicalize_payload(data)
        pub.verify(bytes.fromhex(signature_hex), msg)
        return True
    except (ValueError, InvalidSignature):
        return False
