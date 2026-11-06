import hashlib
import hmac
import os
import sqlite3
import time
from db.database import create_license_record

WEBHOOK_SECRET = os.environ.get("CHESSPRO_WEBHOOK_SECRET", "CSP_WEBHOOK_SECRET_2026")

# Bảng giá quy đổi tự động (Hỗ trợ cả USD cho Stripe/LemonSqueezy và VND cho VietQR SePay/PayOS/Casso)
LIFETIME_MIN_USD = 5.0
LIFETIME_MIN_VND = 100000.0


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    if not signature_header:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header.strip().lower(), expected.lower())


def process_payment_webhook(
    conn: sqlite3.Connection,
    amount: float,
    currency: str,
    method: str,
    webhook_ref: str,
    plan_override: str | None = None,
) -> dict:
    """
    Xử lý Webhook thanh toán tự động (VietQR SePay/Casso/PayOS hoặc Stripe/LemonSqueezy):
    - Chống trùng lặp giao dịch qua `webhook_ref` (Idempotency).
    - Tự động phân loại gói `monthly` (30 ngày) hoặc `lifetime` (vĩnh viễn).
    - Sinh mã License Key vào bảng `licenses` và lưu lịch sử vào bảng `payments`.
    """
    existing = conn.execute(
        """
        SELECT p.*, l.key, l.type
        FROM payments p
        JOIN licenses l ON p.license_id = l.id
        WHERE p.webhook_ref = ?
        """,
        (webhook_ref,),
    ).fetchone()
    if existing:
        return {
            "already_processed": True,
            "payment_id": existing["id"],
            "license_key": existing["key"],
            "license_type": existing["type"],
        }

    if plan_override in ("monthly", "lifetime"):
        license_type = plan_override
    else:
        curr = currency.upper()
        if curr == "VND":
            license_type = "lifetime" if amount >= LIFETIME_MIN_VND else "monthly"
        else:
            license_type = "lifetime" if amount >= LIFETIME_MIN_USD else "monthly"

    license_rec = create_license_record(conn, license_type=license_type)
    now = int(time.time())

    cur = conn.execute(
        """
        INSERT INTO payments (license_id, amount, method, webhook_ref, status, created_at)
        VALUES (?, ?, ?, ?, 'completed', ?)
        """,
        (license_rec["id"], float(amount), method, webhook_ref, now),
    )
    conn.commit()

    return {
        "already_processed": False,
        "payment_id": cur.lastrowid,
        "license_id": license_rec["id"],
        "license_key": license_rec["key"],
        "license_type": license_type,
    }
