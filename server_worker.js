/**
 * Cloudflare Worker: Hệ Thống Tạo URL Nhận Key Duy Nhất & Tự Xóa Sau 24 Giờ
 *
 * Cơ chế chống gian lận 4 lớp:
 * 1. Mỗi lượt bấm "Lấy Key 1 Ngày" trong ChessPro.exe sẽ gửi kèm HWID tới `/get-link?hwid=...`
 *    -> Server tạo ra 1 URL duy nhất: `/key/<SESSION_ID>-<HWID_TAG>-<EXP_HEX>-<URL_SIG>`
 *    -> Lưu vào Cloudflare KV với `expirationTtl: 86400` (Tự động xóa sạch khỏi DB sau 24 giờ).
 *    -> Tự động gọi API Rút Gọn Link (Link4m / Yeumoney / Work.ink) để bọc URL duy nhất đó thành link vượt mã.
 * 2. Chống F5 / Reload trang:
 *    -> Thời điểm hết hạn (`EXP_HEX`) và mã Key được gắn cố định vào URL ngay từ lúc tạo phiên.
 *    -> Dù người dùng nhấn F5 1.000 lần, trang vẫn chỉ hiện đúng 1 mã Key cũ và thời gian đếm ngược tiếp tục giảm, tuyệt đối không sinh Key mới.
 * 3. Chống sửa đổi URL:
 *    -> Toàn bộ tham số trên URL được ký bằng HMAC-SHA256 (`URL_SIG`). Sửa 1 ký tự bất kỳ trên URL sẽ bị chặn ngay lập tức (403 Forbidden).
 * 4. Tự động hủy sau 24 giờ & Khóa cứng HWID:
 *    -> Sau 24h, KV tự xóa bản ghi và chữ ký thời gian hết hạn -> Truy cập lại URL cũ sẽ báo 410 Gone (Đã xóa).
 *    -> Key sinh ra (`FREE-1D-<HWID_TAG>-<EXP_HEX>-<KEY_SIG>`) chỉ kích hoạt được trên đúng máy tính đã bấm Lấy Key.
 */

const SECRET_SIGNING_KEY = "CHESS_STEALTH_PRO_MASTER_SECRET_2026_V1";

// Cấu hình API rút gọn link (Điền API Key của bạn vào biến môi trường trên Cloudflare hoặc điền trực tiếp tại đây)
// Hỗ trợ: 'NONE' (Chuyển thẳng để test), 'LINK4M', 'YEUMONEY'
const SHORTENER_PROVIDER = "NONE";
const SHORTENER_API_KEY = "";

async function hmacHex(secret, message, length = 16) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const buf = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
    .slice(0, length);
}

async function sha256Prefix(text, length = 6) {
  const enc = new TextEncoder();
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(text));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
    .slice(0, length);
}

function randomSessionId() {
  const arr = new Uint8Array(6);
  crypto.getRandomValues(arr);
  return Array.from(arr)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const secret = env?.SECRET_SIGNING_KEY || SECRET_SIGNING_KEY;

    // =========================================================================
    // 1. TẠO URL DUY NHẤT CHO MỖI LƯỢT VƯỢT LINK: GET /get-link?hwid=XXXX
    // =========================================================================
    if (url.pathname === "/get-link") {
      const rawHwid = (url.searchParams.get("hwid") || "").trim().toUpperCase();
      const hwidTag = rawHwid ? await sha256Prefix(rawHwid, 6) : "ANY000";

      const sessionId = randomSessionId();
      const nowSec = Math.floor(Date.now() / 1000);
      const expSec = nowSec + 86400; // Đúng 24 giờ
      const expHex = expSec.toString(16).toUpperCase().padStart(8, "0");

      // Ký bảo mật URL để không ai tự chế hoặc sửa đổi được URL
      const urlSig = await hmacHex(secret, `URL:${sessionId}:${hwidTag}:${expHex}`, 12);
      const tokenPath = `${sessionId}-${hwidTag}-${expHex}-${urlSig}`;
      const uniqueDestUrl = `${url.origin}/key/${tokenPath}`;

      // Tạo sẵn Key cố định cho phiên này
      const keyPayload = hwidTag === "ANY000" ? `1D:${expHex}` : `1D:${hwidTag}:${expHex}`;
      const keySig = await hmacHex(secret, keyPayload, 8);
      const fixedKey =
        hwidTag === "ANY000"
          ? `FREE-1D-${expHex}-${keySig}`
          : `FREE-1D-${hwidTag}-${expHex}-${keySig}`;

      // Nếu gắn Cloudflare KV -> Lưu URL & tự động xóa vật lý sau 86400 giây (24h)
      if (env?.LICENSES_KV) {
        await env.LICENSES_KV.put(
          `SES_${sessionId}`,
          JSON.stringify({ key: fixedKey, exp: expSec, hwidTag }),
          { expirationTtl: 86400 }
        );
      }

      // Nếu bật tích hợp API rút gọn link (Link4m / Yeumoney) -> Tự bọc uniqueDestUrl
      const provider = env?.SHORTENER_PROVIDER || SHORTENER_PROVIDER;
      const apiKey = env?.SHORTENER_API_KEY || SHORTENER_API_KEY;

      if (provider === "LINK4M" && apiKey) {
        try {
          const apiUrl = `https://link4m.co/api-shorten/v2?api=${encodeURIComponent(apiKey)}&url=${encodeURIComponent(uniqueDestUrl)}`;
          const res = await fetch(apiUrl);
          const data = await res.json();
          if (data.status === "success" && data.shortenedUrl) {
            return Response.redirect(data.shortenedUrl, 302);
          }
        } catch (_) {}
      } else if (provider === "YEUMONEY" && apiKey) {
        try {
          const apiUrl = `https://yeumoney.com/QL_api.php?token=${encodeURIComponent(apiKey)}&format=json&url=${encodeURIComponent(uniqueDestUrl)}`;
          const res = await fetch(apiUrl);
          const data = await res.json();
          if (data.status === "success" && data.shortenedUrl) {
            return Response.redirect(data.shortenedUrl, 302);
          }
        } catch (_) {}
      }

      // Mặc định: Chuyển tới URL duy nhất vừa sinh ra
      return Response.redirect(uniqueDestUrl, 302);
    }

    // =========================================================================
    // 2. TRANG HIỂN THỊ KEY DUY NHẤT: GET /key/<SESSION_ID>-<HWID_TAG>-<EXP_HEX>-<URL_SIG>
    // =========================================================================
    if (url.pathname.startsWith("/key/")) {
      const token = url.pathname.replace("/key/", "").trim().toUpperCase();
      const parts = token.split("-");

      if (parts.length !== 4) {
        return renderErrorPage(
          403,
          "URL Không Hợp Lệ",
          "Đường dẫn nhận Key không đúng định dạng hoặc đã bị thay đổi. Vui lòng mở ChessPro.exe và bấm Lấy Key 1 Ngày."
        );
      }

      const [sessionId, hwidTag, expHex, urlSig] = parts;
      const expectedUrlSig = await hmacHex(secret, `URL:${sessionId}:${hwidTag}:${expHex}`, 12);

      // Chống sửa đổi URL (Đổi 1 ký tự bất kỳ sẽ lệch chữ ký HMAC)
      if (urlSig !== expectedUrlSig) {
        return renderErrorPage(
          403,
          "Phát Hiện Can Thiệp URL",
          "Chữ ký bảo mật của URL không khớp. Bạn không thể tự ý chỉnh sửa đường dẫn nhận Key!"
        );
      }

      const expSec = parseInt(expHex, 16);
      const nowSec = Math.floor(Date.now() / 1000);

      // Tự động vô hiệu hóa / xóa sau 24 giờ
      if (isNaN(expSec) || nowSec >= expSec) {
        if (env?.LICENSES_KV) {
          await env.LICENSES_KV.delete(`SES_${sessionId}`);
        }
        return renderErrorPage(
          410,
          "URL Đã Tự Động Xóa (Quá 24 Giờ)",
          "Đường dẫn nhận Key này đã hết hạn 24 giờ và đã bị hệ thống xóa vĩnh viễn. Vui lòng quay lại ChessPro.exe để tạo lượt lấy Key mới."
        );
      }

      // Kiểm tra trong KV nếu có cấu hình KV
      if (env?.LICENSES_KV) {
        const kvRecord = await env.LICENSES_KV.get(`SES_${sessionId}`);
        if (!kvRecord) {
          return renderErrorPage(
            410,
            "URL Không Tồn Tại Hoặc Đã Bị Xóa",
            "Phiên nhận Key này không tồn tại hoặc đã tự hủy sau 24 giờ."
          );
        }
      }

      // Tính lại đúng mã Key duy nhất của phiên này (Reload F5 bao nhiêu lần cũng giữ nguyên 1 Key & cùng mốc hết hạn)
      const keyPayload = hwidTag === "ANY000" ? `1D:${expHex}` : `1D:${hwidTag}:${expHex}`;
      const keySig = await hmacHex(secret, keyPayload, 8);
      const fixedKey =
        hwidTag === "ANY000"
          ? `FREE-1D-${expHex}-${keySig}`
          : `FREE-1D-${hwidTag}-${expHex}-${keySig}`;

      return renderKeyPage(fixedKey, expSec, sessionId, hwidTag);
    }

    return new Response(
      "Chess Stealth Pro Dynamic Key Server Active. Use /get-link?hwid=YOUR_HWID",
      { status: 200 }
    );
  },
};

function renderErrorPage(status, title, message) {
  const html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${title} — Chess Stealth Pro</title>
  <style>
    body { min-height:100vh; background:#09090b; color:#f4f4f5; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:flex; align-items:center; justify-content:center; padding:24px 16px; margin:0; }
    .card { width:100%; max-width:460px; background:#18181b; border:1px solid #ef4444; border-radius:16px; padding:32px 24px; text-align:center; box-shadow:0 16px 40px rgba(0,0,0,0.65); }
    .badge { display:inline-block; background:rgba(239,68,68,0.15); color:#ef4444; font-size:12px; font-weight:700; padding:6px 12px; border-radius:999px; margin-bottom:16px; }
    h1 { font-size:20px; margin:0 0 12px 0; color:#f4f4f5; }
    p { font-size:14px; color:#a1a1aa; line-height:1.6; margin:0; }
  </style>
</head>
<body>
  <main class="card">
    <div class="badge">MÃ LỖI ${status}</div>
    <h1>${title}</h1>
    <p>${message}</p>
  </main>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function renderKeyPage(key, expSec, sessionId, hwidTag) {
  const html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Key Phiên #${sessionId} — Chess Stealth Pro</title>
  <style>
    body { min-height:100vh; background:#09090b; color:#f4f4f5; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; display:flex; align-items:center; justify-content:center; padding:24px 16px; margin:0; }
    .card { width:100%; max-width:480px; background:#18181b; border:1px solid #3f3f46; border-radius:16px; padding:32px 24px; box-shadow:0 16px 40px rgba(0,0,0,0.65); }
    .badge { display:inline-flex; align-items:center; gap:6px; background:rgba(34,197,94,0.14); color:#22c55e; font-size:12px; font-weight:600; padding:6px 12px; border-radius:999px; margin-bottom:16px; }
    h1 { font-size:22px; margin:0 0 8px 0; }
    .sub { font-size:13px; color:#a1a1aa; margin:0 0 20px 0; line-height:1.5; }
    .key-box { background:#09090b; border:1px solid #3f3f46; border-radius:12px; padding:16px; text-align:center; margin-bottom:16px; }
    .key-label { font-size:11px; color:#a1a1aa; text-transform:uppercase; letter-spacing:0.08em; display:block; margin-bottom:8px; }
    .key-val { font-family:Consolas,monospace; font-size:19px; font-weight:700; color:#22c55e; letter-spacing:0.04em; user-select:all; word-break:break-all; }
    button { width:100%; min-height:48px; background:#f59e0b; color:#18181b; border:none; border-radius:10px; font-size:15px; font-weight:700; cursor:pointer; transition:background 0.15s ease; }
    button:hover { background:#d97706; }
    .meta { margin-top:16px; padding-top:16px; border-top:1px solid #27272a; display:flex; justify-content:space-between; font-size:13px; color:#a1a1aa; }
    .timer { font-family:Consolas,monospace; font-weight:700; color:#f59e0b; }
  </style>
</head>
<body>
  <main class="card">
    <div class="badge">URL Duy Nhất: #${sessionId} (Khóa thiết bị: ${hwidTag})</div>
    <h1>Mã Key 24 Giờ Của Bạn</h1>
    <p class="sub">URL này gắn cố định với mã Key bên dưới và sẽ <strong>tự động xóa vĩnh viễn</strong> khi đồng hồ đếm ngược về 00:00:00 (Tải lại trang sẽ không tạo Key mới).</p>
    <div class="key-box">
      <span class="key-label">License Key (Khóa cứng HWID)</span>
      <div id="k" class="key-val">${key}</div>
    </div>
    <button id="copy-btn" type="button">SAO CHÉP MÃ KEY</button>
    <div class="meta">
      <span>Tự động xóa URL & Key sau:</span>
      <span id="cd" class="timer">--:--:--</span>
    </div>
  </main>
  <script>
    const expSec = ${expSec};
    const cd = document.getElementById('cd');
    const btn = document.getElementById('copy-btn');
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(document.getElementById('k').innerText);
      btn.innerText = 'ĐÃ SAO CHÉP VÀO CLIPBOARD';
      setTimeout(() => btn.innerText = 'SAO CHÉP MÃ KEY', 2000);
    });
    function tick() {
      const rem = expSec - Math.floor(Date.now() / 1000);
      if (rem <= 0) {
        location.reload();
        return;
      }
      const h = String(Math.floor(rem / 3600)).padStart(2, '0');
      const m = String(Math.floor((rem % 3600) / 60)).padStart(2, '0');
      const s = String(rem % 60).padStart(2, '0');
      cd.textContent = h + ':' + m + ':' + s;
    }
    tick();
    setInterval(tick, 1000);
  </script>
</body>
</html>`;
  return new Response(html, {
    status: 200,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}
