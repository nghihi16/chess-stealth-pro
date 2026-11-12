# -*- coding: utf-8 -*-
import inspect
import json
import os
import sys
import tempfile
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db.database as db_mod
import keygen
import license_core.crypto_ed25519 as crypto_mod
import license_core.verifier as verifier_mod
from db.database import ensure_web24h_key_in_db, get_connection
from license_core.crypto_ed25519 import (
    ED25519_PUBLIC_KEY_HEX,
    canonicalize_payload,
    verify_response_signature,
    verify_signature,
)
from license_core.verifier import (
    check_anti_rollback,
    derive_arrow_scale_factor,
    is_nonce_used,
    load_valid_offline_cache,
    mark_nonce_used,
    reset_clock_guard_for_testing,
    reset_nonce_store_for_testing,
)


@pytest.fixture(autouse=True)
def isolate_test_state():
    """Tách biệt môi trường file clock guard và nonce store cho từng test."""
    temp_dir = tempfile.mkdtemp(prefix="chess_test_")
    clock_file = os.path.join(temp_dir, "clock_test.json")
    nonce_file = os.path.join(temp_dir, "nonce_test.json")
    cache_file = os.path.join(temp_dir, "verified_session.json")
    db_file = os.path.join(temp_dir, "test_chess.db")

    os.environ["CHESSPRO_CLOCK_GUARD_PATH"] = clock_file
    os.environ["CHESSPRO_NONCE_STORE_PATH"] = nonce_file
    os.environ["CHESSPRO_DB_PATH"] = db_file
    orig_cache = verifier_mod.CACHE_FILE
    verifier_mod.CACHE_FILE = cache_file

    reset_clock_guard_for_testing()
    reset_nonce_store_for_testing()

    yield temp_dir

    verifier_mod.CACHE_FILE = orig_cache
    for f in (clock_file, nonce_file, cache_file):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass


def test_crypto_ed25519_separation_no_private_keys():
    """
    Xác minh Client module license_core/crypto_ed25519.py hoàn toàn KHÔNG chứa
    bất kỳ private key, private seed hay hàm ký nào.
    """
    # 1. Kiểm tra thuộc tính runtime của module
    assert not hasattr(crypto_mod, "_SERVER_PRIVATE_SEED"), "Client crypto module must not contain _SERVER_PRIVATE_SEED"
    assert not hasattr(crypto_mod, "_PRIVATE_KEY"), "Client crypto module must not contain _PRIVATE_KEY"
    assert not hasattr(crypto_mod, "sign_response_payload"), "Client crypto module must not contain sign_response_payload"

    # 2. Kiểm tra thuộc tính public key hợp lệ
    assert hasattr(crypto_mod, "ED25519_PUBLIC_KEY_HEX")
    assert len(crypto_mod.ED25519_PUBLIC_KEY_HEX) == 64
    assert hasattr(crypto_mod, "verify_response_signature")
    assert hasattr(crypto_mod, "verify_signature")

    # 3. Quét tĩnh source code của license_core/crypto_ed25519.py
    src = inspect.getsource(crypto_mod)
    assert "SERVER_MASTER_SEED" not in src
    assert "Ed25519PrivateKey" not in src
    assert ".sign(" not in src


def test_verifier_has_no_self_signing():
    """Xác minh verifier.py không chứa hoặc gọi sign_response_payload."""
    assert not hasattr(verifier_mod, "sign_response_payload")
    src = inspect.getsource(verifier_mod)
    assert "sign_response_payload" not in src


def test_server_signing_isolated_to_keygen():
    """
    Xác minh logic ký được cô lập hoàn toàn trong keygen.py và client
    xác thực chuẩn xác bằng ED25519_PUBLIC_KEY_HEX.
    """
    payload = {
        "valid": True,
        "key": "LIFEVIP-A1B2C3-FFFFFFFF-112233445566",
        "type": "lifetime",
        "status": "active",
        "hwid": "TEST-HWID-001",
        "expires_at": None,
        "server_time": int(time.time()),
        "nonce": "test_nonce_abc123",
    }

    # Ký bằng server key trong keygen
    sig_hex = keygen.sign_response_payload(payload)
    assert len(sig_hex) == 128

    # Client xác thực thành công bằng Public Key
    assert verify_response_signature(payload, sig_hex, ED25519_PUBLIC_KEY_HEX) is True

    # Giả mạo dữ liệu -> Bị từ chối
    tampered = dict(payload)
    tampered["hwid"] = "TAMPERED-HWID"
    assert verify_response_signature(tampered, sig_hex, ED25519_PUBLIC_KEY_HEX) is False

    tampered_valid = dict(payload)
    tampered_valid["valid"] = False
    assert verify_response_signature(tampered_valid, sig_hex, ED25519_PUBLIC_KEY_HEX) is False


def test_anti_rollback_clock_backward_detected():
    """
    Xác minh Anti-Rollback: Khi đồng hồ bị chỉnh lùi về quá khứ so với
    high-water mark đã lưu, hệ thống lập tức từ chối và vô hiệu hóa license.
    """
    now = int(time.time())

    # 1. Trạng thái bình thường
    ok, _ = check_anti_rollback()
    assert ok is True

    # 2. Ghi nhận mốc thời gian cao nhất trong tương lai (giả lập người dùng chỉnh lùi giờ)
    future_time = now + 86400  # 1 ngày sau
    verifier_mod._save_high_water_mark(future_time)

    # 3. Kiểm tra lại: Phát hiện rollback vì system time hiện tại < future_time
    ok, err = check_anti_rollback()
    assert ok is False
    assert "rollback" in err.lower()

    # 4. Kiểm tra derive_arrow_scale_factor trả về 0.0 khi bị rollback
    # Giả sử có active session
    verifier_mod._ACTIVE_SESSION_PAYLOAD = {
        "valid": True,
        "status": "active",
        "expires_at": now + 100000,
    }
    verifier_mod._ACTIVE_SESSION_SIGNATURE = "fake_sig"
    scale = derive_arrow_scale_factor()
    assert scale == 0.0
    assert verifier_mod._ACTIVE_SESSION_PAYLOAD is None


def test_anti_rollback_monotonic_divergence(monkeypatch):
    """
    Xác minh phát hiện lùi giờ hệ thống khi tiến trình đang chạy
    dựa trên chênh lệch giữa time.monotonic() và time.time().
    """
    reset_clock_guard_for_testing()
    # Giả lập thời gian wall clock bị lùi 1000s trong khi monotonic vẫn tiến
    monkeypatch.setattr(time, "time", lambda: verifier_mod._PROCESS_START_WALL - 500)
    ok, err = check_anti_rollback()
    assert ok is False
    assert "monotonic" in err.lower()


def test_single_use_request_nonce_and_replay_prevention():
    """
    Xác minh cơ chế Request Nonce sử dụng 1 lần duy nhất:
    Chống tấn công phát lại (Replay Attack) với cùng một nonce.
    """
    nonce = "NONCE-UNIQUE-TEST-12345"

    assert is_nonce_used(nonce) is False
    mark_nonce_used(nonce)
    assert is_nonce_used(nonce) is True

    # Nonce rỗng phải bị từ chối
    assert is_nonce_used("") is True


def test_offline_hmac_forging_rejected():
    """
    Xác minh các key giả mạo offline bằng HMAC secret cũ bị loại bỏ triệt để.
    """
    assert not hasattr(db_mod, "WEB24H_HMAC_SECRET"), "db.database must not contain WEB24H_HMAC_SECRET"
    db_src = inspect.getsource(db_mod)
    assert "CHESS_STEALTH_PRO_WEB24H_SECRET_2026" not in db_src

    old_secret = b"CHESS_STEALTH_PRO_WEB24H_SECRET_2026"
    import hashlib
    import hmac

    # Sinh key giả mạo offline
    token_id = "ABCDEF"
    exp_hex = "FFFFFFFF"
    sig = hmac.new(old_secret, f"KEY:{token_id}:{exp_hex}".encode(), hashlib.sha256).hexdigest()[:6].upper()
    forged_key = f"LIFEVIP-{token_id}-{exp_hex}-{sig}"

    with get_connection() as conn:
        result = ensure_web24h_key_in_db(conn, forged_key)
        assert result is None, "Forged key must not be accepted by ensure_web24h_key_in_db"


def test_keygen_requires_environment_secret(monkeypatch):
    """
    Xác minh keygen bắt buộc phải có secret từ biến môi trường CHESS_PRO_HMAC_SECRET
    để sinh key HMAC và không sử dụng secret mặc định.
    """
    monkeypatch.delenv("CHESS_PRO_HMAC_SECRET", raising=False)
    with pytest.raises(ValueError, match="CHESS_PRO_HMAC_SECRET"):
        keygen.generate_hmac_license_key("trial_24h")

    # Khi có secret trong env -> sinh thành công
    monkeypatch.setenv("CHESS_PRO_HMAC_SECRET", "SUPER_SECURE_SERVER_SECRET_2026")
    key = keygen.generate_hmac_license_key("lifetime")
    assert key.startswith("LIFEVIP-")
    parts = key.split("-")
    assert len(parts) == 4
    assert len(parts[3]) == 12  # Entropy nâng lên 12 ký tự hex (48 bits)


def test_derive_arrow_scale_factor_integrity():
    """
    Xác minh derive_arrow_scale_factor kiểm tra toàn vẹn chữ ký Ed25519
    và thời hạn sử dụng.
    """
    reset_clock_guard_for_testing()
    now = int(time.time())

    # Chưa có session -> 0.0
    verifier_mod._ACTIVE_SESSION_PAYLOAD = None
    verifier_mod._ACTIVE_SESSION_SIGNATURE = ""
    assert derive_arrow_scale_factor() == 0.0

    # Session hợp lệ có chữ ký Ed25519 thật
    payload = {
        "valid": True,
        "key": "PRO30D-TEST-123",
        "type": "monthly",
        "status": "active",
        "hwid": "HWID-OK",
        "expires_at": now + 3600,
        "server_time": now,
        "nonce": "nonce_scale_ok",
    }
    sig = keygen.sign_response_payload(payload)
    verifier_mod._ACTIVE_SESSION_PAYLOAD = payload
    verifier_mod._ACTIVE_SESSION_SIGNATURE = sig
    assert derive_arrow_scale_factor() == 1.0

    # Session đã hết hạn -> 0.0
    payload_expired = dict(payload)
    payload_expired["expires_at"] = now - 100
    sig_expired = keygen.sign_response_payload(payload_expired)
    verifier_mod._ACTIVE_SESSION_PAYLOAD = payload_expired
    verifier_mod._ACTIVE_SESSION_SIGNATURE = sig_expired
    assert derive_arrow_scale_factor() == 0.0


def test_offline_cache_server_time_anchor_prevents_bypass_on_clock_state_deletion(monkeypatch):
    """
    Xác minh Server Time Anchor trong Offline Cache:
    Kẻ tấn công sao chép cache hợp lệ, xóa clock_state.json và lùi giờ hệ thống về trước server_time:
    load_valid_offline_cache bắt buộc phải phát hiện và từ chối.
    """
    reset_clock_guard_for_testing()
    now = int(time.time())
    hwid = "HWID-ANCHOR-TEST"
    key = "LIFE-VIP-ANCHOR"

    payload = {
        "valid": True,
        "key": key,
        "type": "lifetime",
        "status": "active",
        "hwid": hwid,
        "expires_at": None,
        "server_time": now,
        "nonce": "n_anchor_01",
    }
    sig = keygen.sign_response_payload(payload)
    verifier_mod._save_offline_cache(payload, sig)

    # 1. Với giờ bình thường: nạp cache thành công
    ok, _ = load_valid_offline_cache(key, hwid)
    assert ok is True

    # 2. Xóa clock_state.json và giả lập lùi giờ hệ thống về trước server_time 500s
    reset_clock_guard_for_testing()
    current_wall = now - 500
    verifier_mod._PROCESS_START_WALL = current_wall
    verifier_mod._PROCESS_START_MONOTONIC = time.monotonic()
    monkeypatch.setattr(time, "time", lambda: float(current_wall))
    # clock_state.json đã bị xóa, nhưng server_time trong payload có chữ ký Ed25519 sẽ đóng vai trò neo sàn
    ok, _ = load_valid_offline_cache(key, hwid)
    assert ok is False


def test_high_water_mark_in_memory_caching_and_throttling(monkeypatch):
    """
    Xác minh High-Water Mark được lưu trên RAM và disk updates được throttle:
    Các frame liên tục (60 FPS) không liên tục đọc/ghi đĩa.
    """
    reset_clock_guard_for_testing()
    start_time = int(time.time())
    start_mono = time.monotonic()
    current_time = float(start_time)
    current_mono = float(start_mono)
    monkeypatch.setattr(time, "time", lambda: current_time)
    monkeypatch.setattr(time, "monotonic", lambda: current_mono)
    verifier_mod._PROCESS_START_WALL = current_time
    verifier_mod._PROCESS_START_MONOTONIC = current_mono

    # Frame 1: Khởi tạo
    ok, _ = check_anti_rollback()
    assert ok is True
    disk_hwm_first = verifier_mod._LAST_DISK_HWM
    assert disk_hwm_first == int(start_time)

    # Giả lập 100 frames sau đó (mỗi frame 16ms = 1.6 giây trôi qua)
    current_time += 1.6
    current_mono += 1.6
    ok, _ = check_anti_rollback()
    assert ok is True
    # Disk HWM không bị ghi lại vì chưa đủ 60 giây
    assert verifier_mod._LAST_DISK_HWM == disk_hwm_first
    # Nhưng RAM cache đã cập nhật
    assert verifier_mod._PERSISTED_HIGH_WATER_MARK == int(current_time)

    # Khi tiến thêm >= 60 giây:
    current_time += 65.0
    current_mono += 65.0
    ok, _ = check_anti_rollback()
    assert ok is True
    assert verifier_mod._LAST_DISK_HWM == int(current_time)


def test_atomic_file_writing_integrity(tmp_path):
    """
    Xác minh helper _atomic_write_json ghi file nguyên tử và không để lại file .tmp sót.
    """
    target_file = str(tmp_path / "subfolder" / "atomic_test.json")
    data = {"test_key": "secure_value", "number": 42}
    verifier_mod._atomic_write_json(target_file, data)

    assert os.path.exists(target_file)
    assert not os.path.exists(f"{target_file}.tmp")
    with open(target_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == data

