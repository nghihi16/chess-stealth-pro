import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.server import app
from db.migrate import run_migrations
from license_core.crypto_ed25519 import ED25519_PUBLIC_KEY_HEX, verify_response_signature


@pytest.fixture(autouse=True)
def isolated_test_db():
    fd, temp_db = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ["CHESSPRO_DB_PATH"] = temp_db
    run_migrations(seed_defaults=True)
    yield temp_db
    try:
        os.remove(temp_db)
    except OSError:
        pass


def test_activate_and_verify_with_ed25519_signature():
    client = TestClient(app)
    hwid = "AA11-BB22-CC33-DD44"

    # 1. Trước khi kích hoạt: /verify trả về status = 'unactivated'
    r0 = client.post(
        "/verify",
        json={"key": "LIFE-VIP-9999", "hwid": hwid, "app_version": "2.0.0", "nonce": "n100"},
    )
    assert r0.status_code == 200
    d0 = r0.json()
    assert d0["valid"] is False
    assert d0["status"] == "unactivated"
    assert verify_response_signature(d0, d0["signature"], ED25519_PUBLIC_KEY_HEX) is True

    # 2. Kích hoạt lần đầu qua /activate -> Gắn cứng HWID
    r1 = client.post(
        "/activate",
        json={"key": "LIFE-VIP-9999", "hwid": hwid, "app_version": "2.0.0", "nonce": "n101"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["valid"] is True
    assert d1["type"] == "lifetime"
    assert d1["hwid"] == hwid
    assert d1["expires_at"] is None
    assert verify_response_signature(d1, d1["signature"], ED25519_PUBLIC_KEY_HEX) is True

    # 3. Gọi /verify trên đúng máy đó -> Hợp lệ + Chữ ký Ed25519 chuẩn xác
    r2 = client.post(
        "/verify",
        json={"key": "LIFE-VIP-9999", "hwid": hwid, "app_version": "2.0.0", "nonce": "n102"},
    )
    d2 = r2.json()
    assert d2["valid"] is True
    assert verify_response_signature(d2, d2["signature"], ED25519_PUBLIC_KEY_HEX) is True

    # 4. Chống giả mạo MITM/Proxy: Nếu hacker sửa valid=True trên một phản hồi thất bại
    r_bad = client.post(
        "/verify",
        json={"key": "LIFE-VIP-9999", "hwid": "OTHER-PC-HWID", "app_version": "2.0.0", "nonce": "n103"},
    )
    d_bad = r_bad.json()
    assert d_bad["valid"] is False
    assert d_bad["status"] == "hwid_mismatch"
    # Giả sử Proxy sửa JSON thành valid = True
    tampered = dict(d_bad)
    tampered["valid"] = True
    assert verify_response_signature(tampered, d_bad["signature"], ED25519_PUBLIC_KEY_HEX) is False


def test_hwid_reset_monthly_limit():
    client = TestClient(app)
    hwid_1 = "PC-0001"
    hwid_2 = "PC-0002"
    hwid_3 = "PC-0003"
    hwid_4 = "PC-0004"

    client.post("/activate", json={"key": "PRO30D-TEST-MONTH", "hwid": hwid_1, "nonce": "1"})

    # Đổi máy lần 1 -> Thành công
    res1 = client.post(
        "/reset-hwid",
        json={"key": "PRO30D-TEST-MONTH", "old_hwid": hwid_1, "new_hwid": hwid_2},
    ).json()
    assert res1["success"] is True
    assert res1["remaining_resets_this_month"] == 1

    # Đổi máy lần 2 -> Thành công
    res2 = client.post(
        "/reset-hwid",
        json={"key": "PRO30D-TEST-MONTH", "old_hwid": hwid_2, "new_hwid": hwid_3},
    ).json()
    assert res2["success"] is True
    assert res2["remaining_resets_this_month"] == 0

    # Đổi máy lần 3 trong cùng tháng -> Bị chặn
    res3 = client.post(
        "/reset-hwid",
        json={"key": "PRO30D-TEST-MONTH", "old_hwid": hwid_3, "new_hwid": hwid_4},
    ).json()
    assert res3["success"] is False


def test_claim_free_key_unique_url_and_payment_webhook():
    client = TestClient(app)

    # 1. Tạo lượt lấy key 24h -> Sinh ra URL duy nhất
    c1 = client.post("/claim-free-key", json={"hwid": "MY-HWID-01"}).json()
    assert c1["success"] is True
    assert c1["key"].startswith("FREE24H-")
    token = c1["token"]

    # 2. Mở URL duy nhất lần 1 và F5 lần 2 -> Cùng trả về đúng 1 Key đó
    page1 = client.get(f"/key/{token}")
    page2 = client.get(f"/key/{token}")
    assert page1.status_code == 200
    assert c1["key"] in page1.text
    assert page1.text == page2.text

    # 3. Đổi 1 ký tự trên URL -> Bị chặn 403 Forbidden
    bad_token = token[:-1] + ("A" if token[-1] != "A" else "B")
    page_bad = client.get(f"/key/{bad_token}")
    assert page_bad.status_code == 403

    # 4. Webhook thanh toán tự động tạo Key 30 ngày & Lifetime
    w1 = client.post(
        "/webhook/payment",
        json={"amount": 5.0, "currency": "USD", "method": "stripe", "webhook_ref": "TX_1001"},
    ).json()
    assert w1["success"] is True
    assert w1["license_type"] == "lifetime"
    assert w1["license_key"].startswith("LIFEVIP-")
