import asyncio
import hashlib
import hmac
import json
import os
import random
import secrets
import time
import urllib.parse
import urllib.request
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from api.schemas import (
    ActivateRequest,
    ClaimFreeKeyRequest,
    ClaimFreeKeyResponse,
    PaymentWebhookRequest,
    PaymentWebhookResponse,
    ResetHwidRequest,
    ResetHwidResponse,
    SignedLicenseResponse,
    VerifyRequest,
)
from db.database import (
    cleanup_expired_records,
    create_license_record,
    ensure_web24h_key_in_db,
    get_connection,
)
from license_core.crypto_ed25519 import sign_response_payload
from payment_webhooks.handlers import process_payment_webhook, verify_webhook_signature

router = APIRouter()

MAX_HWID_RESETS_PER_MONTH = 2
URL_HMAC_SECRET = b"CHESS_STEALTH_PRO_URL_TOKEN_SECRET_2026"
SHORTENER_PROVIDER = os.environ.get("SHORTENER_PROVIDER", "NONE")
SHORTENER_API_KEY = os.environ.get("SHORTENER_API_KEY", "")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _build_signed_response(
    *,
    valid: bool,
    key: str,
    ltype: str | None,
    status: str,
    hwid: str | None,
    expires_at: int | None,
    message: str,
    nonce: str,
) -> SignedLicenseResponse:
    now = int(time.time())
    payload = {
        "valid": valid,
        "key": key,
        "type": ltype,
        "status": status,
        "hwid": hwid,
        "expires_at": expires_at,
        "message": message,
        "server_time": now,
        "nonce": nonce,
    }
    payload["signature"] = sign_response_payload(payload)
    return SignedLicenseResponse(**payload)


def _log_audit(
    conn, license_id: int, hwid: str, ip: str, app_version: str, action: str
) -> None:
    conn.execute(
        """
        INSERT INTO activation_logs (license_id, hwid, ip, app_version, action, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (license_id, hwid, ip, app_version, action, int(time.time())),
    )
    conn.commit()


# ============================================================================
# 1. POST /verify — Kiểm tra License & trả về phản hồi có chữ ký số Ed25519
# ============================================================================
@router.post("/verify", response_model=SignedLicenseResponse)
async def verify_license(req: VerifyRequest, request: Request):
    key_clean = req.key.strip().upper()
    hwid_clean = req.hwid.strip().upper()
    ip = _client_ip(request)

    with get_connection() as conn:
        cleanup_expired_records(conn)
        ensure_web24h_key_in_db(conn, key_clean)
        row = conn.execute(
            "SELECT * FROM licenses WHERE key = ?", (key_clean,)
        ).fetchone()

        if not row:
            # Delay ngẫu nhiên & thông báo mập mờ chống brute-force dò key
            await asyncio.sleep(random.uniform(0.05, 0.15))
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=None,
                status="invalid",
                hwid=None,
                expires_at=None,
                message="ERR_AUTH_0x1A: Xác thực bản quyền không thành công.",
                nonce=req.nonce,
            )

        if row["status"] != "active":
            await asyncio.sleep(random.uniform(0.05, 0.12))
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=row["type"],
                status=row["status"],
                hwid=row["hwid"],
                expires_at=row["expires_at"],
                message=f"ERR_STATE_0x2B: Mã bản quyền hiện ở trạng thái {row['status']}.",
                nonce=req.nonce,
            )

        if not row["hwid"]:
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=row["type"],
                status="unactivated",
                hwid=None,
                expires_at=row["expires_at"],
                message="Mã Key chưa được kích hoạt lần đầu.",
                nonce=req.nonce,
            )

        if row["hwid"] != hwid_clean:
            await asyncio.sleep(random.uniform(0.05, 0.15))
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=row["type"],
                status="hwid_mismatch",
                hwid=row["hwid"],
                expires_at=row["expires_at"],
                message="ERR_HWID_0x3C: Mã bản quyền đã gắn với thiết bị phần cứng khác.",
                nonce=req.nonce,
            )

        _log_audit(conn, row["id"], hwid_clean, ip, req.app_version, "verify")

        rem_msg = "Vĩnh viễn (Lifetime)"
        if row["expires_at"]:
            rem = max(0, int(row["expires_at"]) - int(time.time()))
            rem_msg = f"Còn {rem // 3600}h {(rem % 3600) // 60}p"

        return _build_signed_response(
            valid=True,
            key=key_clean,
            ltype=row["type"],
            status="active",
            hwid=hwid_clean,
            expires_at=row["expires_at"],
            message=f"Hợp lệ ({row['type']} — {rem_msg})",
            nonce=req.nonce,
        )


# ============================================================================
# 2. POST /activate — Kích hoạt lần đầu & khóa cứng HWID vào License
# ============================================================================
@router.post("/activate", response_model=SignedLicenseResponse)
async def activate_license(req: ActivateRequest, request: Request):
    key_clean = req.key.strip().upper()
    hwid_clean = req.hwid.strip().upper()
    ip = _client_ip(request)
    now = int(time.time())

    with get_connection() as conn:
        cleanup_expired_records(conn)
        ensure_web24h_key_in_db(conn, key_clean)
        row = conn.execute(
            "SELECT * FROM licenses WHERE key = ?", (key_clean,)
        ).fetchone()

        if not row:
            await asyncio.sleep(random.uniform(0.05, 0.15))
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=None,
                status="invalid",
                hwid=None,
                expires_at=None,
                message="ERR_AUTH_0x1A: Mã bản quyền không tồn tại.",
                nonce=req.nonce,
            )

        if row["status"] != "active":
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=row["type"],
                status=row["status"],
                hwid=row["hwid"],
                expires_at=row["expires_at"],
                message=f"ERR_STATE_0x2B: Mã bản quyền đã {row['status']}.",
                nonce=req.nonce,
            )

        if row["hwid"] and row["hwid"] != hwid_clean:
            return _build_signed_response(
                valid=False,
                key=key_clean,
                ltype=row["type"],
                status="hwid_mismatch",
                hwid=row["hwid"],
                expires_at=row["expires_at"],
                message="ERR_HWID_0x3C: Mã Key này đã được kích hoạt trên máy tính khác.",
                nonce=req.nonce,
            )

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
                (hwid_clean, activated_at, expires_at, row["id"]),
            )
            conn.commit()

        _log_audit(conn, row["id"], hwid_clean, ip, req.app_version, "activate")

        label_map = {
            "trial_24h": "Key 24 Giờ",
            "monthly": "Key 30 Ngày",
            "lifetime": "Key Vĩnh Viễn (Lifetime)",
        }
        return _build_signed_response(
            valid=True,
            key=key_clean,
            ltype=row["type"],
            status="active",
            hwid=hwid_clean,
            expires_at=expires_at,
            message=f"Kích hoạt thành công: {label_map.get(row['type'], row['type'])}",
            nonce=req.nonce,
        )


# ============================================================================
# 3. POST /reset-hwid — Đổi thiết bị (Giới hạn tối đa 2 lần / 30 ngày)
# ============================================================================
@router.post("/reset-hwid", response_model=ResetHwidResponse)
async def reset_hwid(req: ResetHwidRequest, request: Request):
    key_clean = req.key.strip().upper()
    old_hwid = req.old_hwid.strip().upper()
    new_hwid = req.new_hwid.strip().upper()
    now = int(time.time())

    with get_connection() as conn:
        cleanup_expired_records(conn)
        ensure_web24h_key_in_db(conn, key_clean)
        row = conn.execute(
            "SELECT * FROM licenses WHERE key = ?", (key_clean,)
        ).fetchone()

        if not row or row["status"] != "active":
            raise HTTPException(status_code=404, detail="Key không hợp lệ hoặc đã hết hạn.")

        if row["hwid"] != old_hwid:
            raise HTTPException(status_code=403, detail="HWID cũ không khớp với thiết bị đang đăng ký.")

        reset_count = int(row["hwid_reset_count"] or 0)
        last_reset = row["hwid_last_reset_at"]

        # Reset lại bộ đếm nếu đã qua chu kỳ 30 ngày
        if last_reset and (now - int(last_reset)) >= (30 * 86400):
            reset_count = 0

        if reset_count >= MAX_HWID_RESETS_PER_MONTH:
            return ResetHwidResponse(
                success=False,
                key=key_clean,
                new_hwid=None,
                reset_count=reset_count,
                remaining_resets_this_month=0,
                message=f"Đã đạt giới hạn đổi máy ({MAX_HWID_RESETS_PER_MONTH} lần/tháng).",
            )

        new_count = reset_count + 1
        conn.execute(
            """
            UPDATE licenses
            SET hwid = ?, hwid_reset_count = ?, hwid_last_reset_at = ?
            WHERE id = ?
            """,
            (new_hwid, new_count, now, row["id"]),
        )
        conn.commit()
        _log_audit(conn, row["id"], new_hwid, _client_ip(request), "2.0.0", "reset_hwid")

        return ResetHwidResponse(
            success=True,
            key=key_clean,
            new_hwid=new_hwid,
            reset_count=new_count,
            remaining_resets_this_month=MAX_HWID_RESETS_PER_MONTH - new_count,
            message="Đổi thiết bị (HWID) thành công.",
        )


# ============================================================================
# 4. POST /claim-free-key & GET /get-link & GET /key/{token}
#    Luồng vượt link 24h: Chống farm theo IP + 1 Key = 1 URL duy nhất tự xóa sau 24h
# ============================================================================
def _sign_url_token(token_id: str, exp_ts: int) -> str:
    msg = f"{token_id}:{exp_ts}".encode("utf-8")
    return hmac.new(URL_HMAC_SECRET, msg, hashlib.sha256).hexdigest().upper()[:12]


def _create_or_fetch_daily_claim(conn, ip: str, hwid: str | None, base_url: str) -> dict:
    cleanup_expired_records(conn)
    now = int(time.time())

    # Chống farm Key 24h theo IP: Kiểm tra xem IP này đã lấy key trong 24h qua chưa
    recent = conn.execute(
        """
        SELECT c.*, l.key as license_key
        FROM free_key_claims c
        LEFT JOIN licenses l ON c.license_id = l.id
        WHERE c.ip = ? AND c.expires_at > ?
        ORDER BY c.id DESC LIMIT 1
        """,
        (ip, now),
    ).fetchone()

    if recent and recent["license_key"]:
        token_str = recent["token"]
        claim_url = f"{base_url.rstrip('/')}/key/{token_str}"
        return {
            "already_claimed": True,
            "token": token_str,
            "claim_url": claim_url,
            "key": recent["license_key"],
            "expires_at": recent["expires_at"],
        }

    exp_ts = now + 86400
    token_id = secrets.token_hex(4).upper()
    sig = _sign_url_token(token_id, exp_ts)
    full_token = f"{token_id}-{exp_ts:08X}-{sig}"

    lic = create_license_record(
        conn,
        license_type="trial_24h",
        hwid=hwid.strip().upper() if hwid else None,
        activate_immediately=bool(hwid),
    )
    if not lic["expires_at"]:
        conn.execute("UPDATE licenses SET expires_at = ? WHERE id = ?", (exp_ts, lic["id"]))

    conn.execute(
        """
        INSERT INTO free_key_claims (ip, token, hwid, license_id, status, claimed_at, expires_at)
        VALUES (?, ?, ?, ?, 'claimed', ?, ?)
        """,
        (ip, full_token, hwid, lic["id"], now, exp_ts),
    )
    conn.commit()

    claim_url = f"{base_url.rstrip('/')}/key/{full_token}"
    return {
        "already_claimed": False,
        "token": full_token,
        "claim_url": claim_url,
        "key": lic["key"],
        "expires_at": exp_ts,
    }


@router.post("/claim-free-key", response_model=ClaimFreeKeyResponse)
async def claim_free_key(req: ClaimFreeKeyRequest, request: Request):
    ip = _client_ip(request)
    base_url = str(request.base_url).rstrip("/")

    with get_connection() as conn:
        info = _create_or_fetch_daily_claim(conn, ip, req.hwid, base_url)
        shortened = info["claim_url"]

        if SHORTENER_PROVIDER == "LINK4M" and SHORTENER_API_KEY:
            try:
                api_u = f"https://link4m.co/api-shorten/v2?api={urllib.parse.quote(SHORTENER_API_KEY)}&url={urllib.parse.quote(info['claim_url'])}"
                with urllib.request.urlopen(api_u, timeout=5) as res:
                    d = json.loads(res.read().decode("utf-8"))
                    if d.get("status") == "success" and d.get("shortenedUrl"):
                        shortened = d["shortenedUrl"]
            except Exception:
                pass

        return ClaimFreeKeyResponse(
            success=True,
            token=info["token"],
            claim_url=info["claim_url"],
            shortened_url=shortened,
            key=info["key"],
            expires_at=info["expires_at"],
            message="Đã khởi tạo URL nhận Key 24h duy nhất.",
        )


@router.get("/get-link")
async def get_link_redirect(request: Request, hwid: str = ""):
    ip = _client_ip(request)
    base_url = str(request.base_url).rstrip("/")
    with get_connection() as conn:
        info = _create_or_fetch_daily_claim(conn, ip, hwid or None, base_url)
        return RedirectResponse(url=info["claim_url"], status_code=302)


@router.get("/key/{token}", response_class=HTMLResponse)
async def view_unique_key_page(token: str):
    parts = token.strip().upper().split("-")
    if len(parts) != 3:
        return HTMLResponse(
            content=_render_error_html(403, "URL Không Hợp Lệ", "Đường dẫn nhận Key đã bị thay đổi cấu trúc."),
            status_code=403,
        )

    token_id, exp_hex, sig = parts
    try:
        exp_ts = int(exp_hex, 16)
    except ValueError:
        return HTMLResponse(
            content=_render_error_html(403, "URL Lỗi Định Dạng", "Tham số thời gian không hợp lệ."),
            status_code=403,
        )

    expected_sig = _sign_url_token(token_id, exp_ts)
    if not hmac.compare_digest(sig, expected_sig):
        return HTMLResponse(
            content=_render_error_html(
                403,
                "Phát Hiện Đổi URL Trái Phép",
                "Chữ ký bảo mật của URL không khớp! Mỗi Key gắn với 1 URL duy nhất và không thể chỉnh sửa.",
            ),
            status_code=403,
        )

    with get_connection() as conn:
        cleanup_expired_records(conn)
        row = conn.execute(
            """
            SELECT c.*, l.key as license_key
            FROM free_key_claims c
            JOIN licenses l ON c.license_id = l.id
            WHERE c.token = ?
            """,
            (token.strip().upper(),),
        ).fetchone()

        if not row or int(time.time()) >= int(row["expires_at"]):
            return HTMLResponse(
                content=_render_error_html(
                    410,
                    "URL Đã Tự Động Xóa (Quá 24 Giờ)",
                    "URL duy nhất này và mã Key 24h đi kèm đã tự động bị xóa vĩnh viễn sau 24 giờ.",
                ),
                status_code=410,
            )

        return HTMLResponse(
            content=_render_key_html(row["license_key"], int(row["expires_at"]), token_id),
            status_code=200,
        )


# ============================================================================
# 5. POST /webhook/payment — Tự động sinh Key 30 ngày / Lifetime khi thanh toán
# ============================================================================
@router.post("/webhook/payment", response_model=PaymentWebhookResponse)
async def payment_webhook(
    payload: PaymentWebhookRequest,
    request: Request,
    x_webhook_signature: str | None = Header(default=None),
):
    if x_webhook_signature:
        raw_body = await request.body()
        if not verify_webhook_signature(raw_body, x_webhook_signature):
            raise HTTPException(status_code=401, detail="Chữ ký Webhook không hợp lệ.")

    with get_connection() as conn:
        res = process_payment_webhook(
            conn=conn,
            amount=payload.amount,
            currency=payload.currency,
            method=payload.method,
            webhook_ref=payload.webhook_ref,
            plan_override=payload.plan,
        )
        return PaymentWebhookResponse(
            success=True,
            payment_id=res["payment_id"],
            license_key=res["license_key"],
            license_type=res["license_type"],
            already_processed=res["already_processed"],
            message=f"Đã tạo tự động mã Key gói {res['license_type']}.",
        )


def _render_error_html(code: int, title: str, msg: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — Chess Stealth Pro</title>
  <style>
    body {{ min-height:100vh; background:#09090b; color:#f4f4f5; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:flex; align-items:center; justify-content:center; padding:24px 16px; margin:0; }}
    .card {{ width:100%; max-width:460px; background:#18181b; border:1px solid #ef4444; border-radius:16px; padding:32px 24px; text-align:center; box-shadow:0 16px 40px rgba(0,0,0,0.65); }}
    .badge {{ display:inline-block; background:rgba(239,68,68,0.15); color:#ef4444; font-size:12px; font-weight:700; padding:6px 12px; border-radius:999px; margin-bottom:16px; }}
    h1 {{ font-size:20px; margin:0 0 12px 0; }}
    p {{ font-size:14px; color:#a1a1aa; line-height:1.6; margin:0; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="badge">MÃ BẢO MẬT {code}</div>
    <h1>{title}</h1>
    <p>{msg}</p>
  </main>
</body>
</html>"""


def _render_key_html(key: str, exp_sec: int, token_id: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>URL Duy Nhất #{token_id} — Chess Stealth Pro</title>
  <style>
    body {{ min-height:100vh; background:#09090b; color:#f4f4f5; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:flex; align-items:center; justify-content:center; padding:24px 16px; margin:0; }}
    .card {{ width:100%; max-width:480px; background:#18181b; border:1px solid #3f3f46; border-radius:16px; padding:32px 24px; box-shadow:0 16px 40px rgba(0,0,0,0.65); }}
    .badge {{ display:inline-block; background:rgba(34,197,94,0.14); color:#22c55e; font-size:12px; font-weight:600; padding:6px 12px; border-radius:999px; margin-bottom:16px; }}
    h1 {{ font-size:22px; margin:0 0 8px 0; }}
    .sub {{ font-size:13px; color:#a1a1aa; margin:0 0 20px 0; line-height:1.5; }}
    .key-box {{ background:#09090b; border:1px solid #3f3f46; border-radius:12px; padding:16px; text-align:center; margin-bottom:16px; }}
    .key-label {{ font-size:11px; color:#a1a1aa; text-transform:uppercase; letter-spacing:0.08em; display:block; margin-bottom:8px; }}
    .key-val {{ font-family:Consolas,monospace; font-size:20px; font-weight:700; color:#22c55e; letter-spacing:0.04em; user-select:all; }}
    .btn {{ width:100%; min-height:46px; border:none; border-radius:10px; font-size:14px; font-weight:700; cursor:pointer; display:flex; align-items:center; justify-content:center; text-decoration:none; margin-bottom:10px; }}
    .btn-amber {{ background:#f59e0b; color:#18181b; }}
    .btn-green {{ background:#22c55e; color:#09090b; }}
    .meta {{ margin-top:12px; padding-top:14px; border-top:1px solid #27272a; display:flex; justify-content:space-between; font-size:13px; color:#a1a1aa; }}
    .timer {{ font-family:Consolas,monospace; font-weight:700; color:#f59e0b; }}
  </style>
</head>
<body>
  <main class="card">
    <div class="badge">URL Duy Nhất #{token_id} (Chống F5 • Tự Xóa Sau 24h)</div>
    <h1>Mã Key 24 Giờ Của Bạn</h1>
    <p class="sub">Mỗi Key gắn cố định với 1 URL duy nhất và tự xóa sau 24 giờ. Nhấn F5 sẽ không tạo Key mới.</p>
    <div class="key-box">
      <span class="key-label">License Key (24 Hours)</span>
      <div id="k" class="key-val">{key}</div>
    </div>
    <button id="copy-btn" class="btn btn-amber" type="button">SAO CHÉP MÃ KEY</button>
    <a href="chesspro://activate?key={key}" class="btn btn-green">MỞ APP & TỰ ĐỘNG ĐIỀN KEY</a>
    <div class="meta">
      <span>Tự động xóa URL & Key sau:</span>
      <span id="cd" class="timer">--:--:--</span>
    </div>
  </main>
  <script>
    const expSec = {exp_sec};
    const cd = document.getElementById('cd');
    const btn = document.getElementById('copy-btn');
    btn.addEventListener('click', () => {{
      navigator.clipboard.writeText(document.getElementById('k').innerText);
      btn.innerText = 'ĐÃ SAO CHÉP VÀO CLIPBOARD';
      setTimeout(() => btn.innerText = 'SAO CHÉP MÃ KEY', 2000);
    }});
    function tick() {{
      const rem = expSec - Math.floor(Date.now() / 1000);
      if (rem <= 0) {{ location.reload(); return; }}
      const h = String(Math.floor(rem / 3600)).padStart(2, '0');
      const m = String(Math.floor((rem % 3600) / 60)).padStart(2, '0');
      const s = String(rem % 60).padStart(2, '0');
      cd.textContent = h + ':' + m + ':' + s;
    }}
    tick();
    setInterval(tick, 1000);
  </script>
</body>
</html>"""
