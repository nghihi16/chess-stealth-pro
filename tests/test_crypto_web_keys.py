# -*- coding: utf-8 -*-
import os
import sys
import hmac
import hashlib
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import WEB24H_HMAC_SECRET, ensure_web24h_key_in_db, get_connection
from license_core.verifier import activate_or_verify_key


def generate_test_key(prefix: str, token_id: str, exp_sec: int | None) -> str:
    if exp_sec is None or prefix == "LIFEVIP":
        exp_hex = "FFFFFFFF"
    else:
        exp_hex = f"{exp_sec:08X}"
    msg = f"KEY:{token_id}:{exp_hex}".encode("utf-8")
    sig = hmac.new(WEB24H_HMAC_SECRET, msg, hashlib.sha256).hexdigest()[:6].upper()
    return f"{prefix}-{token_id}-{exp_hex}-{sig}"


def test_hmac_key_prefixes_activation():
    hwid = "TEST-HWID-AA11-BB22"
    now = int(time.time())

    # 1. FREE24H key
    free_key = generate_test_key("FREE24H", "TKN001", now + 86400)
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", free_key, hwid)
    assert valid is True
    assert "Activated" in msg or "valid" in msg.lower()

    # 2. PRO07D (7-day key)
    week_key = generate_test_key("PRO07D", "TKN002", now + 7 * 86400)
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", week_key, hwid)
    assert valid is True

    # 3. PRO30D (30-day key)
    month_key = generate_test_key("PRO30D", "TKN003", now + 30 * 86400)
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", month_key, hwid)
    assert valid is True

    # 4. LIFEVIP (Lifetime key)
    life_key = generate_test_key("LIFEVIP", "TKN004", None)
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", life_key, hwid)
    assert valid is True


def test_invalid_key_returns_clean_invalid_key_message():
    hwid = "TEST-HWID-AA11-BB22"
    now = int(time.time())

    # Tampered signature
    valid_key = generate_test_key("PRO30D", "BAD001", now + 30 * 86400)
    tampered = valid_key[:-2] + ("00" if valid_key[-2:] != "00" else "FF")
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", tampered, hwid)
    assert valid is False
    assert msg == "Invalid Key"

    # Completely bogus key
    valid, msg = activate_or_verify_key("http://127.0.0.1:8766", "INVALID-KEY-STRING-1234", hwid)
    assert valid is False
    assert msg == "Invalid Key"


def test_modern_alert_dialog_import():
    from main import ModernAlertDialog
    assert ModernAlertDialog is not None
