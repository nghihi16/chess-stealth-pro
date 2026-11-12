import json
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

# ============================================================================
# Ed25519 ASYMMETRIC DIGITAL SIGNATURE (CLIENT VERIFICATION ONLY)
# - Client (ChessPro.exe / C++ binary) CHỈ sở hữu ED25519_PUBLIC_KEY_HEX.
# - Tuyệt đối không chứa Private Key, Private Seed hoặc logic ký trên Client.
# - Mọi chữ ký phản hồi từ Server (/verify & /activate) phải được xác thực
#   bằng Public Key này.
# ============================================================================

# Public Key (32 bytes = 64 hex chars) nhúng cứng vào Client binary
ED25519_PUBLIC_KEY_HEX: str = (
    "abd5d4934a91b05849989d32e4532c14838c002adc024bcebb67990c96d73600"
)


def canonicalize_payload(data: dict) -> bytes:
    """Chuẩn hóa các trường quan trọng của response thành chuỗi byte bất biến để xác thực."""
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


def verify_signature(
    message: bytes, signature_bytes: bytes, public_key_bytes: bytes
) -> bool:
    """Xác thực chữ ký Ed25519 nguyên bản từ bytes."""
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pub.verify(signature_bytes, message)
        return True
    except (ValueError, InvalidSignature):
        return False


def verify_response_signature(
    data: dict, signature_hex: str, public_key_hex: str = ED25519_PUBLIC_KEY_HEX
) -> bool:
    """[DÙNG TRÊN CLIENT] Xác thực chữ ký Ed25519 của Server bằng Public Key nhúng cứng."""
    if not signature_hex or len(signature_hex) != 128:
        return False
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        msg = canonicalize_payload(data)
        return verify_signature(msg, sig_bytes, pub_bytes)
    except (ValueError, InvalidSignature):
        return False
