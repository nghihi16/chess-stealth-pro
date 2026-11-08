/**
 * Cloudflare Worker: Chess Stealth Pro Key Generator & Anti-Bypass + Admin Management Portal
 * Protects SECRET_KEY on server-side, cryptographically verifies 2-step shortener flow,
 * and provides full Admin Key Management Dashboard via unguessable secret URL slug.
 */

const DEFAULT_SECRET = "CHESS_STEALTH_PRO_WEB24H_SECRET_2026";
const DEFAULT_FRONTEND = "https://nghihi16.github.io/chess-stealth-pro";
const DEFAULT_ADMIN_PASS = "admin_chess_pro_2026";
const DEFAULT_ADMIN_SLUG = "admin-788a9acf0094e887";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

const enc = new TextEncoder();

async function hmacSha256(msg, secret) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sigBuf = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(msg));
  return Array.from(new Uint8Array(sigBuf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

function randomHex(length = 6) {
  const bytes = new Uint8Array(Math.ceil(length / 2));
  crypto.getRandomValues(bytes);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
    .slice(0, length);
}

function parseCookies(cookieHeader) {
  const list = {};
  if (!cookieHeader) return list;
  cookieHeader.split(";").forEach((cookie) => {
    let [name, ...rest] = cookie.split("=");
    name = name?.trim();
    if (!name) return;
    const value = rest.join("=").trim();
    list[name] = decodeURIComponent(value);
  });
  return list;
}

function verifyAdmin(request, env) {
  const expectedPass = env.ADMIN_PASSWORD || DEFAULT_ADMIN_PASS;
  const authHeader = request.headers.get("Authorization");
  if (authHeader) {
    if (authHeader.startsWith("Bearer ") && authHeader.slice(7) === expectedPass) {
      return true;
    }
  }
  const cookies = parseCookies(request.headers.get("Cookie") || "");
  if (cookies["csp_admin_session"] === expectedPass) {
    return true;
  }
  return false;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    const secret = env.SECRET_KEY || DEFAULT_SECRET;
    const frontendUrl = (env.FRONTEND_URL || DEFAULT_FRONTEND).replace(/\/+$/, "");
    const nowSec = Math.floor(Date.now() / 1000);

    const adminSlug = (env.ADMIN_PATH || DEFAULT_ADMIN_SLUG).replace(/^\/+|\/+$/g, "");
    const adminBasePath = `/${adminSlug}`;

    // 1. Health check
    if (url.pathname === "/api/health") {
      return new Response(JSON.stringify({ status: "ok", time: nowSec }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    // 2. Step 1 Callback (Shortlink Step 1 redirects here)
    if (url.pathname === "/callback/step1") {
      const provider = (url.searchParams.get("provider") || "link4m").toLowerCase();
      const nonce = randomHex(8);
      const expSec = nowSec + 1200; // 20 minutes to complete Step 2
      const payloadStr = `${provider}:${nowSec}:${expSec}:${nonce}`;
      const sig = (await hmacSha256(`STEP2:${payloadStr}`, secret)).slice(0, 16);
      const token = `${btoa(payloadStr)}.${sig}`;

      const redirectTarget = `${frontendUrl}/?step=2&token=${encodeURIComponent(token)}&provider=${encodeURIComponent(provider)}`;
      
      const headers = new Headers(corsHeaders);
      headers.set("Location", redirectTarget);
      headers.set(
        "Set-Cookie",
        `csp_step1_grant=${encodeURIComponent(token)}; Path=/; Max-Age=1200; Secure; SameSite=Lax`
      );
      return new Response(null, { status: 302, headers });
    }

    // 3. Step 2 Callback (Shortlink Step 2 redirects here)
    if (url.pathname === "/callback/step2") {
      const cookies = parseCookies(request.headers.get("Cookie") || "");
      const tokenParam = url.searchParams.get("token");
      const token = tokenParam || cookies["csp_step1_grant"];

      if (!token || !token.includes(".")) {
        return Response.redirect(`${frontendUrl}/?error=step1_required`, 302);
      }

      const [payloadB64, providedSig] = token.split(".");
      let payloadStr = "";
      try {
        payloadStr = atob(payloadB64);
      } catch (_) {
        return Response.redirect(`${frontendUrl}/?error=invalid_token`, 302);
      }

      const expectedSig = (await hmacSha256(`STEP2:${payloadStr}`, secret)).slice(0, 16);
      if (providedSig !== expectedSig) {
        return Response.redirect(`${frontendUrl}/?error=invalid_signature`, 302);
      }

      const parts = payloadStr.split(":");
      if (parts.length < 3) {
        return Response.redirect(`${frontendUrl}/?error=invalid_token_format`, 302);
      }

      const tokenExp = parseInt(parts[2], 10);
      if (isNaN(tokenExp) || nowSec > tokenExp) {
        return Response.redirect(`${frontendUrl}/?error=token_expired`, 302);
      }

      // Validated! Generate the 24-hour key
      const tokenId = randomHex(6);
      const expSec = nowSec + 86400;
      const expHex = expSec.toString(16).toUpperCase().padStart(8, "0");

      const keySig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
      const urlSig = (await hmacSha256(`URL:${tokenId}:${expHex}`, secret)).slice(0, 10);

      const licenseKey = `FREE24H-${tokenId}-${expHex}-${keySig}`;
      const urlToken = `${tokenId}-${expHex}-${urlSig}`;

      const finalUrl = `${frontendUrl}/?token=${encodeURIComponent(urlToken)}&key=${encodeURIComponent(licenseKey)}`;

      const headers = new Headers(corsHeaders);
      headers.set("Location", finalUrl);
      headers.set(
        "Set-Cookie",
        "csp_step1_grant=deleted; Path=/; Max-Age=0; Secure; SameSite=Lax"
      );
      return new Response(null, { status: 302, headers });
    }

    // 4. JSON API: /api/verify-step2 (if frontend calls via AJAX)
    if (url.pathname === "/api/verify-step2" && request.method === "POST") {
      try {
        const body = await request.json();
        const token = body.token;
        if (!token || !token.includes(".")) {
          return new Response(JSON.stringify({ error: "Missing or invalid token" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const [payloadB64, providedSig] = token.split(".");
        const payloadStr = atob(payloadB64);
        const expectedSig = (await hmacSha256(`STEP2:${payloadStr}`, secret)).slice(0, 16);
        if (providedSig !== expectedSig) {
          return new Response(JSON.stringify({ error: "Invalid token signature" }), {
            status: 403,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const parts = payloadStr.split(":");
        const tokenExp = parseInt(parts[2], 10);
        if (isNaN(tokenExp) || nowSec > tokenExp) {
          return new Response(JSON.stringify({ error: "Token expired" }), {
            status: 403,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const tokenId = randomHex(6);
        const expSec = nowSec + 86400;
        const expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        const keySig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
        const urlSig = (await hmacSha256(`URL:${tokenId}:${expHex}`, secret)).slice(0, 10);

        return new Response(
          JSON.stringify({
            success: true,
            licenseKey: `FREE24H-${tokenId}-${expHex}-${keySig}`,
            urlToken: `${tokenId}-${expHex}-${urlSig}`,
            expSec,
          }),
          { headers: { "Content-Type": "application/json", ...corsHeaders } }
        );
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // ==========================================
    // 5. OBFUSCATED ADMIN MANAGEMENT APIS
    // ==========================================

    // Admin Login API
    if (url.pathname === `${adminBasePath}/api/login` && request.method === "POST") {
      try {
        const body = await request.json();
        const expectedPass = env.ADMIN_PASSWORD || DEFAULT_ADMIN_PASS;
        if (!body.password || body.password !== expectedPass) {
          return new Response(JSON.stringify({ error: "Mật khẩu quản trị không chính xác" }), {
            status: 401,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const headers = new Headers(corsHeaders);
        headers.set("Content-Type", "application/json");
        headers.set(
          "Set-Cookie",
          `csp_admin_session=${encodeURIComponent(expectedPass)}; Path=${adminBasePath}; Max-Age=86400; HttpOnly; Secure; SameSite=Strict`
        );
        return new Response(JSON.stringify({ success: true, message: "Đăng nhập thành công" }), {
          status: 200,
          headers,
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // Admin Logout API
    if (url.pathname === `${adminBasePath}/api/logout` && request.method === "POST") {
      const headers = new Headers(corsHeaders);
      headers.set("Content-Type", "application/json");
      headers.set(
        "Set-Cookie",
        `csp_admin_session=deleted; Path=${adminBasePath}; Max-Age=0; HttpOnly; Secure; SameSite=Strict`
      );
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers,
      });
    }

    // Admin Key Generator API
    if (url.pathname === `${adminBasePath}/api/generate` && request.method === "POST") {
      if (!verifyAdmin(request, env)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      try {
        const body = await request.json();
        const type = body.type || "trial_24h";
        let durationSec = 86400;
        let prefix = "FREE24H";

        if (type === "trial_24h") {
          durationSec = 86400;
          prefix = "FREE24H";
        } else if (type === "week_7d") {
          durationSec = 7 * 86400;
          prefix = "PRO07D";
        } else if (type === "monthly_30d") {
          durationSec = 30 * 86400;
          prefix = "PRO30D";
        } else if (type === "lifetime") {
          durationSec = 100 * 365 * 86400;
          prefix = "LIFEVIP";
        }

        const expSec = nowSec + durationSec;
        const expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        const tokenId = randomHex(6);
        const keySig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
        const licenseKey = `${prefix}-${tokenId}-${expHex}-${keySig}`;

        return new Response(
          JSON.stringify({
            success: true,
            key: licenseKey,
            type,
            prefix,
            expSec,
            expDate: new Date(expSec * 1000).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }),
          }),
          { headers: { "Content-Type": "application/json", ...corsHeaders } }
        );
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // Admin Key Inspector / Verifier API
    if (url.pathname === `${adminBasePath}/api/verify` && request.method === "POST") {
      if (!verifyAdmin(request, env)) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      try {
        const body = await request.json();
        const cleanKey = (body.key || "").trim().toUpperCase();
        const parts = cleanKey.split("-");

        if (parts.length !== 4) {
          return new Response(JSON.stringify({
            valid: false,
            error: "Định dạng Key không hợp lệ (Phải có dạng PREFIX-ID-EXP-SIG)",
          }), {
            status: 200,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const [prefix, tokenId, expHex, providedSig] = parts;
        if (tokenId.length !== 6 || expHex.length !== 8 || providedSig.length !== 6) {
          return new Response(JSON.stringify({
            valid: false,
            error: "Độ dài tham số Key không hợp lệ",
          }), {
            status: 200,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const expSec = parseInt(expHex, 16);
        if (isNaN(expSec)) {
          return new Response(JSON.stringify({
            valid: false,
            error: "Mốc thời gian hết hạn không đọc được",
          }), {
            status: 200,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const expectedSig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
        if (providedSig !== expectedSig) {
          return new Response(JSON.stringify({
            valid: false,
            error: "Chữ ký HMAC không khớp! Key này là giả mạo hoặc sai Secret Key",
          }), {
            status: 200,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const isExpired = nowSec >= expSec;
        const remainingSec = Math.max(0, expSec - nowSec);

        return new Response(JSON.stringify({
          valid: !isExpired,
          isExpired,
          prefix,
          tokenId,
          expSec,
          remainingSec,
          expDate: new Date(expSec * 1000).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }),
          message: isExpired ? "Key này đã hết hạn sử dụng!" : "Key hoàn toàn hợp lệ và có chữ ký bảo mật chuẩn!",
        }), {
          status: 200,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // ==========================================
    // 6. OBFUSCATED ADMIN HTML USER INTERFACE
    // ==========================================
    if (url.pathname === adminBasePath || url.pathname === `${adminBasePath}/`) {
      const isAuthenticated = verifyAdmin(request, env);
      if (!isAuthenticated) {
        return new Response(renderAdminLoginPage(adminBasePath), {
          status: 200,
          headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
        });
      }
      return new Response(renderAdminDashboardPage(env, frontendUrl, adminBasePath), {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
      });
    }

    // Convenient redirect: /admin -> obfuscated secret admin slug
    if (url.pathname === "/admin" || url.pathname === "/admin/") {
      return Response.redirect(`${url.origin}${adminBasePath}`, 302);
    }

    // Default: Redirect to frontend (bounces scanner URLs)
    return Response.redirect(frontendUrl, 302);
  },
};

// ==========================================
// HTML RENDERING FUNCTIONS
// ==========================================

function renderAdminLoginPage(adminBasePath) {
  return `<!DOCTYPE html>
<html lang="vi" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chess Stealth Pro — Quản Trị Viên</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=JetBrains+Mono:wght@600;700&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      background: #09090b;
      color: #f4f4f5;
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 16px;
    }
    .login-card {
      width: 100%;
      max-width: 420px;
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 20px;
      padding: 36px 28px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7);
    }
    .header-logo {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 24px;
    }
    .logo-badge {
      width: 44px;
      height: 44px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #10b981;
    }
    h1 { font-size: 20px; font-weight: 800; color: #f4f4f5; letter-spacing: -0.02em; }
    p.subtitle { font-size: 13px; color: #a1a1aa; line-height: 1.5; margin-top: 2px; }
    .form-group { margin-top: 24px; }
    label { font-size: 13px; font-weight: 600; color: #d4d4d8; display: block; margin-bottom: 8px; }
    .input-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }
    input {
      width: 100%;
      height: 48px;
      background: #09090b;
      border: 1px solid #3f3f46;
      border-radius: 12px;
      padding: 0 16px;
      color: #f4f4f5;
      font-size: 15px;
      font-family: inherit;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    input:focus {
      outline: none;
      border-color: #10b981;
      box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
    }
    button.submit-btn {
      width: 100%;
      height: 48px;
      background: #10b981;
      color: #09090b;
      border: none;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.15s, transform 0.05s;
    }
    button.submit-btn:hover { background: #059669; }
    button.submit-btn:active { transform: scale(0.98); }
    .error-msg {
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #f87171;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 13px;
      margin-top: 16px;
      display: none;
    }
    .footer-note {
      text-align: center;
      font-size: 12px;
      color: #71717a;
      margin-top: 24px;
    }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="header-logo">
      <div class="logo-badge">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
      </div>
      <div>
        <h1>Chess Stealth Pro</h1>
        <p class="subtitle">Cổng Quản Trị Key & Bảo Mật</p>
      </div>
    </div>

    <form id="loginForm">
      <div class="form-group">
        <label for="password">Mật khẩu quản trị (ADMIN_PASSWORD)</label>
        <div class="input-wrap">
          <input type="password" id="password" required placeholder="Nhập mật khẩu quản trị..." autofocus />
        </div>
      </div>
      <div id="errMsg" class="error-msg"></div>
      <button type="submit" class="submit-btn" id="btnSubmit">
        <span>Mở Khóa Quản Trị</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
      </button>
    </form>
    <div class="footer-note">Cloudflare Edge Enforced • Unguessable Route Protected</div>
  </div>

  <script>
    const form = document.getElementById('loginForm');
    const pwdInput = document.getElementById('password');
    const errMsg = document.getElementById('errMsg');
    const btn = document.getElementById('btnSubmit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errMsg.style.display = 'none';
      btn.disabled = true;
      btn.style.opacity = '0.7';

      try {
        const res = await fetch('${adminBasePath}/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwdInput.value })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          window.location.reload();
        } else {
          errMsg.textContent = data.error || 'Mật khẩu không hợp lệ';
          errMsg.style.display = 'block';
        }
      } catch (err) {
        errMsg.textContent = 'Lỗi kết nối máy chủ Cloudflare: ' + err.message;
        errMsg.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    });
  </script>
</body>
</html>`;
}

function renderAdminDashboardPage(env, frontendUrl, adminBasePath) {
  return `<!DOCTYPE html>
<html lang="vi" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Chess Stealth Pro — Quản Lý Key</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=JetBrains+Mono:wght@600;700&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      background: #09090b;
      color: #f4f4f5;
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      padding: 32px 16px;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
    }
    .top-nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid #27272a;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      width: 44px;
      height: 44px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #10b981;
    }
    .brand-title { font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }
    .brand-badge {
      font-size: 11px;
      font-weight: 700;
      color: #10b981;
      background: rgba(16, 185, 129, 0.14);
      padding: 2px 8px;
      border-radius: 999px;
      margin-left: 8px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .logout-btn {
      height: 40px;
      padding: 0 16px;
      background: #27272a;
      color: #d4d4d8;
      border: 1px solid #3f3f46;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .logout-btn:hover { background: #3f3f46; color: #fff; }

    /* Tabs */
    .tab-bar {
      display: flex;
      gap: 8px;
      margin-bottom: 24px;
    }
    .tab-btn {
      height: 44px;
      padding: 0 20px;
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 12px;
      color: #a1a1aa;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .tab-btn.active {
      background: rgba(16, 185, 129, 0.14);
      border-color: #10b981;
      color: #10b981;
    }
    .tab-btn:hover:not(.active) {
      background: #27272a;
      color: #f4f4f5;
    }

    /* Cards */
    .card {
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 16px;
      padding: 28px;
      margin-bottom: 24px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
    }
    .card-title {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .card-desc {
      font-size: 13px;
      color: #a1a1aa;
      margin-bottom: 24px;
      line-height: 1.5;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .form-label {
      font-size: 13px;
      font-weight: 600;
      color: #d4d4d8;
      display: block;
      margin-bottom: 8px;
    }
    select, input[type="text"] {
      width: 100%;
      height: 48px;
      background: #09090b;
      border: 1px solid #3f3f46;
      border-radius: 12px;
      padding: 0 16px;
      color: #f4f4f5;
      font-size: 14px;
      font-family: inherit;
    }
    select:focus, input[type="text"]:focus {
      outline: none;
      border-color: #10b981;
      box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
    }
    .action-btn {
      height: 48px;
      padding: 0 24px;
      background: #10b981;
      color: #09090b;
      border: none;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .action-btn:hover { background: #059669; }

    /* Key Result Display Box */
    .result-box {
      margin-top: 24px;
      background: #09090b;
      border: 1px solid #3f3f46;
      border-radius: 14px;
      padding: 20px;
      display: none;
    }
    .result-label {
      font-size: 12px;
      color: #a1a1aa;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
      display: block;
    }
    .key-text {
      font-family: 'JetBrains Mono', monospace;
      font-size: 18px;
      font-weight: 700;
      color: #10b981;
      word-break: break-all;
      margin-bottom: 16px;
      user-select: all;
    }
    .btn-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .btn-sub {
      height: 40px;
      padding: 0 16px;
      background: #27272a;
      color: #f4f4f5;
      border: 1px solid #3f3f46;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn-sub:hover { background: #3f3f46; }

    /* Verify details table */
    .verify-details {
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid #27272a;
      display: none;
    }
    .detail-row {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      padding: 8px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .detail-label { color: #a1a1aa; }
    .detail-val { font-weight: 600; color: #f4f4f5; font-family: 'JetBrains Mono', monospace; }

    /* Info cards */
    .info-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
    }
    .info-card {
      background: #09090b;
      border: 1px solid #27272a;
      border-radius: 12px;
      padding: 16px;
    }
    .info-val { font-size: 15px; font-weight: 700; color: #f4f4f5; margin-top: 6px; }
  </style>
</head>
<body>
  <div class="container">
    <header class="top-nav">
      <div class="brand">
        <div class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2L15 8L20 5L18 14H6L4 5L9 8L12 2Z"></path>
            <path d="M5 16H19V18C19 18.55 18.55 19 18 19H6C5.45 19 5 18.55 5 18V16Z"></path>
          </svg>
        </div>
        <div>
          <span class="brand-title">Chess Stealth Pro</span>
          <span class="brand-badge">Admin</span>
        </div>
      </div>
      <button class="logout-btn" id="btnLogout">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
          <polyline points="16 17 21 12 16 7"></polyline>
          <line x1="21" y1="12" x2="9" y2="12"></line>
        </svg>
        <span>Đăng Xuất</span>
      </button>
    </header>

    <div class="tab-bar">
      <button class="tab-btn active" id="tabGenBtn" onclick="switchTab('gen')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 2l-2 2m-1-1l-3 3m2 2l-6 6a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l6-6m2-2l-3-3"></path>
        </svg>
        <span>Tạo Key Mới</span>
      </button>
      <button class="tab-btn" id="tabVerifyBtn" onclick="switchTab('verify')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span>Kiểm Tra Key</span>
      </button>
      <button class="tab-btn" id="tabSysBtn" onclick="switchTab('sys')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
          <line x1="6" y1="6" x2="6.01" y2="6"></line>
          <line x1="6" y1="18" x2="6.01" y2="18"></line>
        </svg>
        <span>Hệ Thống</span>
      </button>
    </div>

    <!-- TAB 1: GENERATE KEY -->
    <div id="tabGen" class="tab-content">
      <div class="card">
        <h2 class="card-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          Tạo Mã Bản Quyền (License Key)
        </h2>
        <p class="card-desc">Tạo mã kích hoạt chuẩn ký số HMAC-SHA256, tương thích 100% với ứng dụng máy tính ChessPro.exe.</p>

        <form id="genForm">
          <div class="form-grid">
            <div>
              <label class="form-label">Loại gói / Thời hạn</label>
              <select id="keyType">
                <option value="trial_24h">Dùng thử 24 Giờ (FREE24H)</option>
                <option value="week_7d">Gói Tuần 7 Ngày (PRO07D)</option>
                <option value="monthly_30d" selected>Gói Tháng 30 Ngày (PRO30D)</option>
                <option value="lifetime">Gói Vĩnh Viễn (LIFEVIP)</option>
              </select>
            </div>
            <div>
              <label class="form-label">Ghi chú khách hàng (Tùy chọn)</label>
              <input type="text" id="keyNote" placeholder="Ví dụ: Anh Nam Telegram..." />
            </div>
          </div>

          <button type="submit" class="action-btn" id="btnGen">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            <span>Tạo Key Ngay</span>
          </button>
        </form>

        <div id="genResultBox" class="result-box">
          <span class="result-label">Mã Key Tạo Thành Công</span>
          <div class="key-text" id="genKeyText"></div>
          <div style="font-size: 13px; color: #a1a1aa; margin-bottom: 16px;">
            Hết hạn vào: <strong id="genKeyExp" style="color: #f4f4f5;"></strong>
          </div>
          <div class="btn-row">
            <button class="btn-sub" onclick="copyKey('genKeyText', this)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
              <span>Sao Chép Key</span>
            </button>
            <a id="btnActivateProtocol" href="#" class="btn-sub" style="text-decoration: none; color: #10b981; border-color: rgba(16, 185, 129, 0.4);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
              <span>Kích Hoạt Trực Tiếp Vào ChessPro</span>
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: VERIFY KEY -->
    <div id="tabVerify" class="tab-content" style="display: none;">
      <div class="card">
        <h2 class="card-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          Kiểm Tra & Giải Mã Key
        </h2>
        <p class="card-desc">Kiểm tra tính hợp lệ, nguồn gốc chữ ký bảo mật và hạn dùng của bất kỳ License Key nào.</p>

        <form id="verifyForm">
          <div style="margin-bottom: 16px;">
            <label class="form-label">Dán mã License Key cần kiểm tra</label>
            <input type="text" id="verifyInput" required placeholder="FREE24H-XXXXXX-XXXXXXXX-XXXXXX" style="font-family: 'JetBrains Mono', monospace;" />
          </div>
          <button type="submit" class="action-btn" style="background: #38bdf8;" id="btnVerify">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            <span>Kiểm Tra Key</span>
          </button>
        </form>

        <div id="verifyResultBox" class="result-box">
          <div id="verifyStatusBadge" style="display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; margin-bottom: 12px;"></div>
          <div id="verifyMsg" style="font-size: 14px; color: #d4d4d8; line-height: 1.5;"></div>

          <div id="verifyDetails" class="verify-details">
            <div class="detail-row">
              <span class="detail-label">Loại Bản Quyền</span>
              <span class="detail-val" id="detType"></span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Mã Phiên (Token ID)</span>
              <span class="detail-val" id="detToken"></span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Thời Hạn Hết Hạn</span>
              <span class="detail-val" id="detExp"></span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Thời Gian Còn Lại</span>
              <span class="detail-val" id="detRemain"></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: SYSTEM INFO -->
    <div id="tabSys" class="tab-content" style="display: none;">
      <div class="card">
        <h2 class="card-title">Trạng Thái Hệ Thống & Máy Chủ</h2>
        <p class="card-desc">Thông số máy chủ Edge Cloudflare và cấu hình mã hóa bảo mật hiện tại.</p>

        <div class="info-grid">
          <div class="info-card">
            <div style="font-size: 12px; color: #a1a1aa;">Edge Server Status</div>
            <div class="info-val" style="color: #10b981;">🟢 Hoạt Động (200 OK)</div>
          </div>
          <div class="info-card">
            <div style="font-size: 12px; color: #a1a1aa;">Bảo Vệ Chữ Ký</div>
            <div class="info-val">HMAC-SHA256</div>
          </div>
          <div class="info-card">
            <div style="font-size: 12px; color: #a1a1aa;">Web Lấy Key (Frontend)</div>
            <div class="info-val" style="font-size: 13px; word-break: break-all;">${frontendUrl}</div>
          </div>
          <div class="info-card">
            <div style="font-size: 12px; color: #a1a1aa;">Thời Gian Máy Chủ</div>
            <div class="info-val" id="serverClock">--:--:--</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

      if (name === 'gen') {
        document.getElementById('tabGenBtn').classList.add('active');
        document.getElementById('tabGen').style.display = 'block';
      } else if (name === 'verify') {
        document.getElementById('tabVerifyBtn').classList.add('active');
        document.getElementById('tabVerify').style.display = 'block';
      } else if (name === 'sys') {
        document.getElementById('tabSysBtn').classList.add('active');
        document.getElementById('tabSys').style.display = 'block';
      }
    }

    // Logout
    document.getElementById('btnLogout').addEventListener('click', async () => {
      await fetch('${adminBasePath}/api/logout', { method: 'POST' });
      window.location.reload();
    });

    // Generate Key
    document.getElementById('genForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btnGen');
      btn.disabled = true;
      btn.style.opacity = '0.7';

      try {
        const type = document.getElementById('keyType').value;
        const res = await fetch('${adminBasePath}/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          document.getElementById('genKeyText').textContent = data.key;
          document.getElementById('genKeyExp').textContent = data.expDate;
          document.getElementById('btnActivateProtocol').href = 'chesspro://activate?key=' + encodeURIComponent(data.key);
          document.getElementById('genResultBox').style.display = 'block';
        } else {
          alert(data.error || 'Lỗi khi tạo key');
        }
      } catch (err) {
        alert('Lỗi kết nối: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    });

    // Verify Key
    document.getElementById('verifyForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btnVerify');
      const box = document.getElementById('verifyResultBox');
      const badge = document.getElementById('verifyStatusBadge');
      const msg = document.getElementById('verifyMsg');
      const details = document.getElementById('verifyDetails');

      btn.disabled = true;
      btn.style.opacity = '0.7';

      try {
        const key = document.getElementById('verifyInput').value;
        const res = await fetch('${adminBasePath}/api/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key })
        });
        const data = await res.json();
        box.style.display = 'block';

        if (data.valid) {
          badge.style.background = 'rgba(16, 185, 129, 0.14)';
          badge.style.color = '#10b981';
          badge.textContent = 'KEY HỢP LỆ VÀ ĐANG HOẠT ĐỘNG';
          msg.textContent = data.message;
          details.style.display = 'block';
          document.getElementById('detType').textContent = data.prefix;
          document.getElementById('detToken').textContent = data.tokenId;
          document.getElementById('detExp').textContent = data.expDate;
          const h = Math.floor(data.remainingSec / 3600);
          const m = Math.floor((data.remainingSec % 3600) / 60);
          document.getElementById('detRemain').textContent = h + ' giờ ' + m + ' phút';
        } else {
          badge.style.background = 'rgba(239, 68, 68, 0.14)';
          badge.style.color = '#ef4444';
          badge.textContent = data.isExpired ? 'KEY ĐÃ HẾT HẠN' : 'KEY KHÔNG HỢP LỆ';
          msg.textContent = data.error || data.message;
          details.style.display = 'none';
        }
      } catch (err) {
        alert('Lỗi kiểm tra: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    });

    // Copy helper
    async function copyKey(elementId, btn) {
      const text = document.getElementById(elementId).textContent;
      try {
        await navigator.clipboard.writeText(text);
        const original = btn.innerHTML;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg><span style="color:#10b981">Đã Sao Chép!</span>';
        setTimeout(() => { btn.innerHTML = original; }, 2000);
      } catch (_) {
        alert('Đã chọn key, vui lòng nhấn Ctrl+C để copy');
      }
    }

    // Live Clock
    setInterval(() => {
      document.getElementById('serverClock').textContent = new Date().toLocaleTimeString('vi-VN');
    }, 1000);
  </script>
</body>
</html>`;
}
