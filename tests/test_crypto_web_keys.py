# -*- coding: utf-8 -*-
import os
import sys
import hmac
import hashlib
import time
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import ensure_web24h_key_in_db, get_connection
from db.migrate import run_migrations
from license_core.verifier import activate_or_verify_key

OLD_LEAKED_HMAC_SECRET = b"CHESS_STEALTH_PRO_WEB24H_SECRET_2026"


@pytest.fixture(autouse=True)
def isolated_test_db():
    fd, temp_db = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ["CHESSPRO_DB_PATH"] = temp_db

    fd2, temp_cache = tempfile.mkstemp(suffix=".json")
    os.close(fd2)
    os.environ["CHESSPRO_CACHE_PATH"] = temp_cache
    if os.path.exists(temp_cache):
        os.remove(temp_cache)

    run_migrations(seed_defaults=True)
    yield temp_db
    for f in (temp_db, temp_cache):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    os.environ.pop("CHESSPRO_CACHE_PATH", None)
    os.environ.pop("CHESSPRO_DB_PATH", None)


def generate_forged_test_key(prefix: str, token_id: str, exp_sec: int | None) -> str:
    """Tạo key giả mạo offline sử dụng secret cũ đã bị rò rỉ."""
    if exp_sec is None or prefix == "LIFEVIP":
        exp_hex = "FFFFFFFF"
    else:
        exp_hex = f"{exp_sec:08X}"
    msg = f"KEY:{token_id}:{exp_hex}".encode("utf-8")
    sig = hmac.new(OLD_LEAKED_HMAC_SECRET, msg, hashlib.sha256).hexdigest()[:6].upper()
    return f"{prefix}-{token_id}-{exp_hex}-{sig}"


def test_forged_offline_hmac_keys_are_rejected():
    """
    Xác minh các key giả mạo offline bằng secret HMAC cũ bị từ chối triệt để:
    1. Không được tự ý thêm vào SQLite qua ensure_web24h_key_in_db.
    2. activate_or_verify_key từ chối kích hoạt.
    """
    hwid = "TEST-HWID-AA11-BB22"
    now = int(time.time())

    with get_connection() as conn:
        # 1. FREE24H forged key
        free_key = generate_forged_test_key("FREE24H", "TKN001", now + 86400)
        assert ensure_web24h_key_in_db(conn, free_key) is None
        valid, _ = activate_or_verify_key("http://127.0.0.1:8766", free_key, hwid)
        assert valid is False

        # 2. PRO07D (7-day key)
        week_key = generate_forged_test_key("PRO07D", "TKN002", now + 7 * 86400)
        assert ensure_web24h_key_in_db(conn, week_key) is None
        valid, _ = activate_or_verify_key("http://127.0.0.1:8766", week_key, hwid)
        assert valid is False

        # 3. PRO30D (30-day key)
        month_key = generate_forged_test_key("PRO30D", "TKN003", now + 30 * 86400)
        assert ensure_web24h_key_in_db(conn, month_key) is None
        valid, _ = activate_or_verify_key("http://127.0.0.1:8766", month_key, hwid)
        assert valid is False

        # 4. LIFEVIP (Lifetime key)
        life_key = generate_forged_test_key("LIFEVIP", "TKN004", None)
        assert ensure_web24h_key_in_db(conn, life_key) is None
        valid, _ = activate_or_verify_key("http://127.0.0.1:8766", life_key, hwid)
        assert valid is False


def test_invalid_key_returns_clean_invalid_key_message():
    hwid = "TEST-HWID-AA11-BB22"
    now = int(time.time())

    # Tampered signature
    valid_key = generate_forged_test_key("PRO30D", "BAD001", now + 30 * 86400)
    tampered = valid_key[:-2] + ("00" if valid_key[-2:] != "00" else "FF")
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", tampered, hwid)
    assert valid is False
    assert "Invalid Key" in msg or "Cannot connect" in msg

    # Completely bogus key
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", "INVALID-KEY-STRING-1234", hwid)
    assert valid is False
    assert "Invalid Key" in msg or "Cannot connect" in msg


def test_modern_alert_dialog_import():
    from main import ModernAlertDialog
    assert ModernAlertDialog is not None
