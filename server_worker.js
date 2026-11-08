/**
 * Cloudflare Worker: Chess Stealth Pro Key Generator, Anti-Bypass & Admin Dashboard
 * Supports 24H, 30-Day, and Lifetime VIP keys with server-side HMAC validation and KV tracking.
 */

const DEFAULT_SECRET = "CHESS_STEALTH_PRO_WEB24H_SECRET_2026";
const DEFAULT_FRONTEND = "https://nghihi16.github.io/chess-stealth-pro";
const DEFAULT_ADMIN_PW = "admin_chess_pro_2026";
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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    const url = new URL(request.url);
    const secret = env.SECRET_KEY || DEFAULT_SECRET;
    const frontendUrl = (env.FRONTEND_URL || DEFAULT_FRONTEND).replace(/\/+$/, "");
    const adminPassword = (env.ADMIN_PASSWORD || DEFAULT_ADMIN_PW).trim();
    const validPasses = [adminPassword, DEFAULT_ADMIN_PW];
    const adminSlug = (env.ADMIN_PATH || DEFAULT_ADMIN_SLUG).replace(/^\/+|\/+$/g, "");
    const adminBasePath = `/${adminSlug}`;
    const nowSec = Math.floor(Date.now() / 1000);

    // 1. Health check
    if (url.pathname === "/api/health") {
      return new Response(JSON.stringify({ status: "ok", time: nowSec }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    // 2. Check Key API: Decodes and inspects 24H, 30D, and Lifetime keys
    if (url.pathname === "/api/check-key") {
      const keyQuery = (url.searchParams.get("key") || "").trim().toUpperCase();
      const parts = keyQuery.split("-");
      if (parts.length !== 4) {
        return new Response(JSON.stringify({ valid: false, error: "Định dạng mã key không hợp lệ (cần 4 đoạn phân tách bởi dấu -)" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      const [prefix, tokenId, expHex, providedSig] = parts;
      if (!["FREE24H", "PRO30D", "LIFEVIP"].includes(prefix)) {
        return new Response(JSON.stringify({ valid: false, error: "Tiền tố key không hợp lệ (chỉ chấp nhận FREE24H, PRO30D, LIFEVIP)" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      const expectedSig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
      const isSigValid = providedSig === expectedSig;

      let isRevoked = false;
      if (env.KEYS_KV) {
        const revoked = await env.KEYS_KV.get(`revoked:${keyQuery}`);
        if (revoked) isRevoked = true;
      }

      if (prefix === "LIFEVIP") {
        const isFormatValid = expHex === "FFFFFFFF";
        const isValid = isSigValid && isFormatValid && !isRevoked;
        return new Response(
          JSON.stringify({
            valid: isValid,
            key: keyQuery,
            type: "lifetime",
            typeName: "Vĩnh Viễn (Lifetime VIP)",
            signatureValid: isSigValid,
            isLifetime: true,
            expired: false,
            revoked: isRevoked,
            remainingSec: null,
            hoursLeft: "Vĩnh viễn",
            minutesLeft: null,
            expiresAt: null,
            currentTime: new Date(nowSec * 1000).toISOString(),
          }),
          { headers: { "Content-Type": "application/json", ...corsHeaders } }
        );
      }

      const expSec = parseInt(expHex, 16);
      const remainingSec = Math.max(0, expSec - nowSec);
      const isExpired = remainingSec === 0;
      const type = prefix === "PRO30D" ? "30d" : "24h";
      const typeName = prefix === "PRO30D" ? "Bản Quyền 30 Ngày" : "Bản Quyền 24 Giờ";

      const hoursLeft = (remainingSec / 3600).toFixed(1);
      const minutesLeft = Math.floor(remainingSec / 60);

      return new Response(
        JSON.stringify({
          valid: isSigValid && !isExpired && !isRevoked,
          key: keyQuery,
          type: type,
          typeName: typeName,
          signatureValid: isSigValid,
          isLifetime: false,
          expired: isExpired,
          revoked: isRevoked,
          remainingSec,
          hoursLeft: parseFloat(hoursLeft),
          minutesLeft,
          expiresAt: new Date(expSec * 1000).toISOString(),
          currentTime: new Date(nowSec * 1000).toISOString(),
        }),
        { headers: { "Content-Type": "application/json", ...corsHeaders } }
      );
    }

    // 3. Step 1 Callback (Shortlink Step 1 redirects here)
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

    // 4. Step 2 Callback (Shortlink Step 2 redirects here)
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
      const prov = parts[0] || "link4m";

      if (env.KEYS_KV) {
        try {
          const record = {
            key: licenseKey,
            type: "24h",
            provider: prov,
            createdAt: nowSec,
            expSec: expSec,
            status: "active",
          };
          await env.KEYS_KV.put(`key:${licenseKey}`, JSON.stringify(record), {
            expiration: expSec,
          });
        } catch (_) {}
      }

      const finalUrl = `${frontendUrl}/?token=${encodeURIComponent(urlToken)}&key=${encodeURIComponent(licenseKey)}`;

      const headers = new Headers(corsHeaders);
      headers.set("Location", finalUrl);
      headers.set(
        "Set-Cookie",
        "csp_step1_grant=deleted; Path=/; Max-Age=0; Secure; SameSite=Lax"
      );
      return new Response(null, { status: 302, headers });
    }

    // 5. Admin API: List all active keys in JSON
    if (url.pathname === "/api/admin/keys" || url.pathname === `${adminBasePath}/api/keys`) {
      const auth = url.searchParams.get("auth") || request.headers.get("Authorization")?.replace("Bearer ", "");
      if (!auth || !validPasses.includes(auth.trim())) {
        return new Response(JSON.stringify({ error: "Unauthorized: Mật khẩu quản trị viên không chính xác" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      const keysList = [];
      if (env.KEYS_KV) {
        try {
          const list = await env.KEYS_KV.list({ prefix: "key:" });
          for (const item of list.keys) {
            const val = await env.KEYS_KV.get(item.name);
            if (val) {
              try {
                const data = JSON.parse(val);
                if (data.type === "lifetime" || data.expSec === null) {
                  data.isLifetime = true;
                  data.remainingSec = null;
                  data.hoursLeft = "Vĩnh viễn";
                } else {
                  data.isLifetime = false;
                  const rem = Math.max(0, data.expSec - nowSec);
                  data.remainingSec = rem;
                  data.hoursLeft = (rem / 3600).toFixed(1);
                }
                keysList.push(data);
              } catch (_) {}
            }
          }
        } catch (_) {}
      }

      keysList.sort((a, b) => b.createdAt - a.createdAt);
      return new Response(JSON.stringify({ success: true, count: keysList.length, keys: keysList }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    // 6. Admin API: Revoke a key
    if ((url.pathname === "/api/admin/revoke" || url.pathname === `${adminBasePath}/api/revoke`) && request.method === "POST") {
      const auth = url.searchParams.get("auth") || request.headers.get("Authorization")?.replace("Bearer ", "");
      if (!auth || !validPasses.includes(auth.trim())) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      try {
        const body = await request.json();
        const targetKey = (body.key || "").trim().toUpperCase();
        if (targetKey && env.KEYS_KV) {
          await env.KEYS_KV.delete(`key:${targetKey}`);
          await env.KEYS_KV.put(`revoked:${targetKey}`, "1", { expirationTtl: 86400 * 365 });
          return new Response(JSON.stringify({ success: true, revoked: targetKey }), {
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }
        return new Response(JSON.stringify({ error: "Thiếu mã key" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    // 7. Admin API: Generate Key manually (24h, 30d, lifetime)
    if ((url.pathname === "/api/admin/generate" || url.pathname === `${adminBasePath}/api/generate`) && request.method === "POST") {
      const auth = url.searchParams.get("auth") || request.headers.get("Authorization")?.replace("Bearer ", "");
      if (!auth || !validPasses.includes(auth.trim())) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      let keyType = "24h";
      try {
        const body = await request.json();
        if (body.type) keyType = body.type.toLowerCase();
      } catch (_) {
        const queryType = url.searchParams.get("type");
        if (queryType) keyType = queryType.toLowerCase();
      }

      const tokenId = randomHex(6);
      let prefix = "FREE24H";
      let expSec = null;
      let expHex = "FFFFFFFF";
      let kvTtl = null;

      if (keyType === "30d" || keyType === "monthly") {
        prefix = "PRO30D";
        expSec = nowSec + (30 * 86400);
        expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        kvTtl = expSec;
      } else if (keyType === "lifetime" || keyType === "vip") {
        prefix = "LIFEVIP";
        expSec = null;
        expHex = "FFFFFFFF";
        kvTtl = null;
      } else {
        keyType = "24h";
        prefix = "FREE24H";
        expSec = nowSec + 86400;
        expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        kvTtl = expSec;
      }

      const keySig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
      const licenseKey = `${prefix}-${tokenId}-${expHex}-${keySig}`;

      if (env.KEYS_KV) {
        try {
          const record = {
            key: licenseKey,
            type: keyType,
            provider: "admin",
            createdAt: nowSec,
            expSec: expSec,
            status: "active",
          };
          const putOptions = kvTtl ? { expiration: kvTtl } : {};
          await env.KEYS_KV.put(`key:${licenseKey}`, JSON.stringify(record), putOptions);
        } catch (_) {}
      }

      return new Response(JSON.stringify({
        success: true,
        key: licenseKey,
        type: keyType,
        expSec: expSec,
        isLifetime: keyType === "lifetime"
      }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    // 8. Admin Web UI: Minimalist, intuitive, high-contrast, zero-emoji, responsive
    if (url.pathname === adminBasePath || url.pathname === `${adminBasePath}/`) {
      const html = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Quản Lý Key — Chess Stealth Pro</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --card-muted: #162032;
      --border: #1f293d;
      --border-focus: #38bdf8;
      --text: #f8fafc;
      --text-sub: #94a3b8;
      --text-muted: #64748b;
      --primary: #0284c7;
      --primary-hover: #0369a1;
      --cyan: #38bdf8;
      --green: #10b981;
      --green-bg: rgba(16, 185, 129, 0.12);
      --amber: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.12);
      --purple: #a855f7;
      --purple-bg: rgba(168, 85, 247, 0.12);
      --red: #f43f5e;
      --red-bg: rgba(244, 63, 94, 0.12);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      padding: 24px 16px;
      display: flex;
      justify-content: center;
      line-height: 1.5;
    }
    .wrapper {
      width: 100%;
      max-width: 960px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .svg-icon {
      width: 18px;
      height: 18px;
      display: inline-block;
      vertical-align: middle;
      stroke-width: 2;
      stroke: currentColor;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    /* Top Navigation Header */
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--card);
      border: 1px solid var(--border);
      padding: 16px 20px;
      border-radius: 12px;
      gap: 16px;
      flex-wrap: wrap;
    }
    .brand-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 17px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.01em;
    }
    .brand-badge {
      font-size: 11px;
      font-weight: 600;
      background: var(--green-bg);
      color: var(--green);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 3px 8px;
      border-radius: 6px;
      letter-spacing: 0.02em;
    }

    /* Login Modal Overlay */
    .login-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(9, 13, 22, 0.92);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 16px;
    }
    .login-box {
      width: 100%;
      max-width: 420px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 32px 28px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.5);
    }
    .login-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: rgba(56, 189, 248, 0.12);
      color: var(--cyan);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 4px;
    }
    .login-icon svg { width: 24px; height: 24px; }
    .login-title { font-size: 20px; font-weight: 800; color: #fff; }
    .login-desc { font-size: 13px; color: var(--text-sub); }
    .login-err {
      font-size: 13px;
      color: var(--red);
      background: var(--red-bg);
      border: 1px solid rgba(244, 63, 94, 0.3);
      padding: 8px 12px;
      border-radius: 8px;
      display: none;
    }
    .remember-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-sub);
      cursor: pointer;
    }
    .remember-row input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--cyan);
      cursor: pointer;
    }

    input[type="password"], input[type="text"] {
      background: #0f172a;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
      min-height: 44px;
      width: 100%;
    }
    input[type="password"]:focus, input[type="text"]:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: var(--primary);
      color: #ffffff;
      border: 1px solid transparent;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      min-height: 44px;
      min-width: 44px;
      transition: all 0.15s ease;
    }
    .btn:hover {
      background: var(--primary-hover);
      box-shadow: 0 2px 8px rgba(2, 132, 199, 0.35);
    }
    .btn-secondary {
      background: #1e293b;
      color: var(--text);
      border-color: #334155;
    }
    .btn-secondary:hover {
      background: #334155;
      box-shadow: none;
    }
    .btn-amber {
      background: #b45309;
      color: #ffffff;
    }
    .btn-amber:hover {
      background: #d97706;
      box-shadow: 0 2px 8px rgba(217, 119, 6, 0.35);
    }
    .btn-purple {
      background: #7e22ce;
      color: #ffffff;
    }
    .btn-purple:hover {
      background: #9333ea;
      box-shadow: 0 2px 8px rgba(147, 51, 234, 0.35);
    }
    .btn-emerald {
      background: #047857;
      color: #ffffff;
    }
    .btn-emerald:hover {
      background: #059669;
      box-shadow: 0 2px 8px rgba(5, 150, 105, 0.35);
    }
    .btn-danger {
      background: var(--red-bg);
      color: var(--red);
      border: 1px solid rgba(244, 63, 94, 0.3);
      padding: 6px 12px;
      font-size: 12px;
      min-height: 36px;
    }
    .btn-danger:hover {
      background: #e11d48;
      color: #ffffff;
    }
    .btn-copy {
      background: #1e293b;
      color: var(--cyan);
      border: 1px solid #334155;
      padding: 6px 10px;
      font-size: 12px;
      border-radius: 6px;
      min-height: 36px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 500;
      transition: all 0.15s ease;
    }
    .btn-copy:hover {
      background: #0f172a;
      border-color: var(--cyan);
    }

    /* Summary Stat Cards */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    @media (max-width: 768px) {
      .stats-grid { grid-template-columns: 1fr; }
    }
    .stat-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .stat-label {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-sub);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .stat-number {
      font-size: 26px;
      font-weight: 800;
      color: var(--text);
      font-feature-settings: "tnum";
      font-variant-numeric: tabular-nums;
    }
    .stat-desc {
      font-size: 12px;
      color: var(--text-muted);
    }

    /* Generator Action Row */
    .gen-actions-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .gen-buttons-group {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    /* Key Inspector Box */
    .inspector-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .card-heading {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .inspector-input-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .inspector-input-row input {
      flex: 1;
      min-width: 240px;
    }
    .inspect-result {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      display: none;
      font-size: 13px;
      line-height: 1.6;
    }

    /* Main Keys Table Container */
    .table-container {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .table-header-tools {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-input-box {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0b1120;
      border: 1px solid var(--border);
      padding: 0 12px;
      border-radius: 8px;
      flex: 1;
      max-width: 380px;
      min-height: 44px;
    }
    .search-input-box input {
      background: transparent;
      border: none;
      color: var(--text);
      outline: none;
      width: 100%;
      font-size: 13px;
      padding: 0;
      min-height: auto;
    }
    .filter-pills {
      display: flex;
      gap: 6px;
      align-items: center;
    }
    .filter-pill {
      background: #1e293b;
      color: var(--text-sub);
      border: 1px solid #334155;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .filter-pill.active {
      background: var(--cyan);
      color: #090d16;
      border-color: var(--cyan);
    }

    /* Table & Rows */
    .table-scroll {
      overflow-x: auto;
      width: 100%;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }
    th {
      background: #0b1120;
      color: var(--text-sub);
      font-weight: 600;
      padding: 12px 18px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    td {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }
    tr:last-child td {
      border-bottom: none;
    }
    tr:hover td {
      background-color: rgba(56, 189, 248, 0.02);
    }
    .key-badge {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-weight: 700;
      font-size: 13px;
      color: #ffffff;
      letter-spacing: 0.02em;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .tag-24h {
      background: rgba(56, 189, 248, 0.12);
      color: var(--cyan);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .tag-30d {
      background: var(--purple-bg);
      color: #c084fc;
      border: 1px solid rgba(168, 85, 247, 0.3);
    }
    .tag-lifetime {
      background: var(--green-bg);
      color: var(--green);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .countdown-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 13px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 6px;
      font-feature-settings: "tnum";
      font-variant-numeric: tabular-nums;
    }
    .countdown-good {
      background: var(--green-bg);
      color: var(--green);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .countdown-warning {
      background: var(--amber-bg);
      color: var(--amber);
      border: 1px solid rgba(245, 158, 11, 0.25);
    }
    .countdown-danger {
      background: var(--red-bg);
      color: var(--red);
      border: 1px solid rgba(244, 63, 94, 0.25);
    }
    .countdown-life {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .time-sub {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 3px;
    }

    .empty-state {
      padding: 48px 24px;
      text-align: center;
      color: var(--text-muted);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }
    .empty-state svg {
      width: 40px;
      height: 40px;
      stroke: var(--text-muted);
      opacity: 0.5;
    }
    .toast-msg {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #0f172a;
      color: #fff;
      border: 1px solid var(--cyan);
      padding: 12px 18px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      display: none;
      z-index: 1001;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    }
  </style>
</head>
<body>
  <!-- Login Screen Overlay -->
  <div class="login-overlay" id="login-overlay">
    <div class="login-box">
      <div class="login-icon">
        <svg class="svg-icon" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      </div>
      <div>
        <h2 class="login-title">Đăng Nhập Quản Trị</h2>
        <p class="login-desc">Nhập mật khẩu quản trị viên để mở khóa bảng điều khiển key.</p>
      </div>
      <div class="login-err" id="login-err">Mật khẩu quản trị viên không chính xác!</div>
      <div style="display:flex; flex-direction:column; gap:8px;">
        <input type="password" id="modal-pw-input" placeholder="Nhập Admin Password..."/>
      </div>
      <label class="remember-row">
        <input type="checkbox" id="modal-remember" checked/>
        <span>Ghi nhớ phiên đăng nhập trên trình duyệt này</span>
      </label>
      <button class="btn" id="modal-login-btn">
        <svg class="svg-icon" viewBox="0 0 24 24"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/></svg>
        <span>Xác Nhận & Đăng Nhập</span>
      </button>
    </div>
  </div>

  <div class="wrapper">
    <!-- Header -->
    <header class="top-bar">
      <div class="brand-title">
        <svg class="svg-icon" viewBox="0 0 24 24"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        <span>Chess Stealth Pro</span>
        <span class="brand-badge">Trang Quản Trị Key</span>
      </div>
      <div class="auth-actions" id="auth-actions">
        <span style="font-size:12px; color:var(--text-sub);">Quản trị viên: <b style="color:var(--green);" id="auth-status-txt">Đã kết nối</b></span>
        <button class="btn btn-secondary" onclick="logout()" style="padding:6px 12px; min-height:36px; font-size:12px;">
          <svg class="svg-icon" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>
          <span>Đăng xuất</span>
        </button>
      </div>
    </header>

    <!-- Stat Summary Cards -->
    <section class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">
          <svg class="svg-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <span>Key Đang Tồn Tại</span>
        </div>
        <div class="stat-number" id="stat-count">0</div>
        <div class="stat-desc">Đang lưu trữ trên Cloudflare KV</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">
          <svg class="svg-icon" viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
          <span>Các Gói Bản Quyền</span>
        </div>
        <div class="stat-number" style="color:var(--cyan); font-size: 20px; font-weight:700;">24H • 30 Ngày • VIP</div>
        <div class="stat-desc">Xác thực mã hóa HMAC mật</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">
          <svg class="svg-icon" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <span>Cơ Chế Bảo Mật</span>
        </div>
        <div class="stat-number" style="color:var(--green); font-size:20px; font-weight:700;">Auto-TTL & Vĩnh Viễn</div>
        <div class="stat-desc">Tự động xóa key hết hạn</div>
      </div>
    </section>

    <!-- Fast Generator Bar -->
    <section class="gen-actions-card">
      <div style="font-size: 14px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 8px;">
        <svg class="svg-icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <span>Tạo Mã Key Mới Ngay:</span>
      </div>
      <div class="gen-buttons-group">
        <button class="btn btn-amber" onclick="createKey('24h')">
          <svg class="svg-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span>Tạo Key 24 Giờ</span>
        </button>
        <button class="btn btn-purple" onclick="createKey('30d')">
          <svg class="svg-icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          <span>Tạo Key 30 Ngày</span>
        </button>
        <button class="btn btn-emerald" onclick="createKey('lifetime')">
          <svg class="svg-icon" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
          <span>Tạo Key Lifetime (Vĩnh Viễn)</span>
        </button>
      </div>
    </section>

    <!-- Key Inspector Tool -->
    <section class="inspector-card">
      <div class="card-heading">
        <svg class="svg-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <span>Tra cứu / Kiểm tra thời hạn của bất kỳ Key nào</span>
      </div>
      <div class="inspector-input-row">
        <input type="text" id="inspect-input" placeholder="Dán mã key cần kiểm tra (FREE24H-..., PRO30D-..., LIFEVIP-...)..."/>
        <button class="btn btn-secondary" id="inspect-btn">
          <span>Kiểm tra</span>
        </button>
      </div>
      <div class="inspect-result" id="inspect-result"></div>
    </section>

    <!-- Active Keys Table -->
    <section class="table-container">
      <div class="table-header-tools">
        <div class="search-input-box">
          <svg class="svg-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" id="search-input" placeholder="Lọc theo mã key hoặc loại..."/>
        </div>
        <div class="filter-pills">
          <button class="filter-pill active" data-filter="all">Tất cả</button>
          <button class="filter-pill" data-filter="24h">24 Giờ</button>
          <button class="filter-pill" data-filter="30d">30 Ngày</button>
          <button class="filter-pill" data-filter="lifetime">Lifetime</button>
          <button class="btn btn-secondary" id="refresh-btn" style="min-height:36px; padding:6px 12px; margin-left:8px;">
            <svg class="svg-icon" viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            <span>Làm mới</span>
          </button>
        </div>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Mã Key Bản Quyền</th>
              <th>Gói Bản Quyền</th>
              <th>Thời Gian Cấp & Hết Hạn</th>
              <th>Thời Gian Còn Lại</th>
              <th>Trạng Thái</th>
              <th>Thao Tác</th>
            </tr>
          </thead>
          <tbody id="keys-tbody">
            <tr>
              <td colspan="6">
                <div class="empty-state">
                  <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  <span>Chưa có dữ liệu key.</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <div class="toast-msg" id="toast"></div>

  <script>
    let rawKeysData = [];
    let countdownInterval = null;
    let currentFilterType = 'all';

    const loginOverlay = document.getElementById('login-overlay');
    const modalPwInput = document.getElementById('modal-pw-input');
    const modalRemember = document.getElementById('modal-remember');
    const modalLoginBtn = document.getElementById('modal-login-btn');
    const loginErr = document.getElementById('login-err');

    const refreshBtn = document.getElementById('refresh-btn');
    const tbody = document.getElementById('keys-tbody');
    const statCount = document.getElementById('stat-count');
    const searchInput = document.getElementById('search-input');
    const inspectInput = document.getElementById('inspect-input');
    const inspectBtn = document.getElementById('inspect-btn');
    const inspectResult = document.getElementById('inspect-result');
    const toast = document.getElementById('toast');

    function showToast(msg) {
      toast.textContent = msg;
      toast.style.display = 'block';
      setTimeout(() => { toast.style.display = 'none'; }, 2500);
    }

    function getStoredPw() {
      return localStorage.getItem('csp_admin_pw') || sessionStorage.getItem('csp_admin_pw') || '';
    }

    function savePw(pw, remember) {
      if (remember) {
        localStorage.setItem('csp_admin_pw', pw);
        sessionStorage.removeItem('csp_admin_pw');
      } else {
        sessionStorage.setItem('csp_admin_pw', pw);
        localStorage.removeItem('csp_admin_pw');
      }
    }

    function logout() {
      localStorage.removeItem('csp_admin_pw');
      sessionStorage.removeItem('csp_admin_pw');
      // Remove ?auth= param from URL if present
      if (window.location.search) {
        window.history.replaceState({}, document.title, window.location.pathname);
      }
      modalPwInput.value = '';
      loginErr.style.display = 'none';
      loginOverlay.style.display = 'flex';
      tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><span>Vui lòng đăng nhập để xem danh sách key.</span></div></td></tr>';
      statCount.textContent = '0';
      if (countdownInterval) clearInterval(countdownInterval);
    }

    async function tryLogin(pw, remember) {
      loginErr.style.display = 'none';
      modalLoginBtn.disabled = true;
      modalLoginBtn.style.opacity = '0.7';

      try {
        const res = await fetch('${adminBasePath}/api/keys?auth=' + encodeURIComponent(pw));
        if (!res.ok) {
          loginErr.textContent = 'Mật khẩu quản trị viên không chính xác!';
          loginErr.style.display = 'block';
          modalLoginBtn.disabled = false;
          modalLoginBtn.style.opacity = '1';
          loginOverlay.style.display = 'flex';
          return false;
        }

        savePw(pw, remember);
        loginOverlay.style.display = 'none';
        modalLoginBtn.disabled = false;
        modalLoginBtn.style.opacity = '1';

        // Clean up URL if auth param was passed
        if (window.location.search.includes('auth=')) {
          window.history.replaceState({}, document.title, window.location.pathname);
        }

        const data = await res.json();
        rawKeysData = data.keys || [];
        statCount.textContent = rawKeysData.length;
        renderKeysTable();
        startLiveCountdown();
        return true;
      } catch (err) {
        loginErr.textContent = 'Lỗi kết nối tới Cloudflare: ' + err.message;
        loginErr.style.display = 'block';
        modalLoginBtn.disabled = false;
        modalLoginBtn.style.opacity = '1';
        return false;
      }
    }

    async function loadKeys() {
      const pw = getStoredPw();
      if (!pw) {
        loginOverlay.style.display = 'flex';
        return;
      }
      try {
        const res = await fetch('${adminBasePath}/api/keys?auth=' + encodeURIComponent(pw));
        if (!res.ok) {
          logout();
          return;
        }
        const data = await res.json();
        rawKeysData = data.keys || [];
        statCount.textContent = rawKeysData.length;
        renderKeysTable();
        startLiveCountdown();
      } catch (_) {}
    }

    function formatTimeRemaining(sec, isLife) {
      if (isLife) {
        return {
          str: 'VĨNH VIỄN',
          readable: 'Bản quyền trọn đời (VIP)',
          class: 'countdown-life'
        };
      }
      if (sec <= 0) return { str: 'Đã hết hạn', readable: 'Hết hiệu lực', class: 'countdown-danger' };
      const d = Math.floor(sec / 86400);
      const h = Math.floor((sec % 86400) / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      let cls = 'countdown-good';
      if (d === 0 && h < 3) cls = 'countdown-danger';
      else if (d === 0 && h < 12) cls = 'countdown-warning';

      let str = '';
      let readable = '';
      if (d > 0) {
        str = \`\${d}d \${h.toString().padStart(2, '0')}:\${m.toString().padStart(2, '0')}:\${s.toString().padStart(2, '0')}\`;
        readable = \`Còn \${d} ngày \${h} giờ\`;
      } else {
        str = \`\${h.toString().padStart(2, '0')}:\${m.toString().padStart(2, '0')}:\${s.toString().padStart(2, '0')}\`;
        readable = \`Còn \${h} giờ \${m} phút\`;
      }

      return { str, readable, class: cls };
    }

    function renderKeysTable() {
      const search = (searchInput.value || '').toLowerCase().trim();
      const filtered = rawKeysData.filter(k => {
        const keyUpper = (k.key || '').toUpperCase();
        let matchesFilter = true;
        if (currentFilterType === '24h') matchesFilter = keyUpper.startsWith('FREE24H') || k.type === '24h';
        else if (currentFilterType === '30d') matchesFilter = keyUpper.startsWith('PRO30D') || k.type === '30d';
        else if (currentFilterType === 'lifetime') matchesFilter = keyUpper.startsWith('LIFEVIP') || k.type === 'lifetime' || k.isLifetime;

        if (!matchesFilter) return false;
        if (!search) return true;
        return k.key.toLowerCase().includes(search) || (k.provider || '').toLowerCase().includes(search) || (k.type || '').toLowerCase().includes(search);
      });

      if (filtered.length === 0) {
        tbody.innerHTML = \`<tr><td colspan="6"><div class="empty-state"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><span>\${rawKeysData.length === 0 ? "Hiện tại chưa có key nào trong Cloudflare KV. Bấm các nút phía trên để tạo key mới." : "Không tìm thấy key nào khớp với bộ lọc."}</span></div></td></tr>\`;
        return;
      }

      const now = Math.floor(Date.now() / 1000);
      tbody.innerHTML = filtered.map(k => {
        const isLife = k.type === 'lifetime' || k.isLifetime || (k.key && k.key.startsWith('LIFEVIP'));
        const is30D = k.type === '30d' || (k.key && k.key.startsWith('PRO30D'));
        const remSec = isLife ? null : Math.max(0, k.expSec - now);
        const rem = formatTimeRemaining(remSec, isLife);
        const createdDate = new Date(k.createdAt * 1000).toLocaleString('vi-VN');
        const expDate = isLife ? 'Không giới hạn (Vĩnh viễn)' : new Date(k.expSec * 1000).toLocaleString('vi-VN');

        let tagHtml = '<span class="tag tag-24h">24 GIỜ</span>';
        if (isLife) {
          tagHtml = '<span class="tag tag-lifetime">LIFETIME VIP</span>';
        } else if (is30D) {
          tagHtml = '<span class="tag tag-30d">30 NGÀY</span>';
        }

        return \`
          <tr id="row-\${k.key}">
            <td>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="key-badge">\${k.key}</span>
                <button class="btn-copy" onclick="copyKey('\${k.key}')" title="Sao chép key">
                  <svg class="svg-icon" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>Chép</span>
                </button>
              </div>
            </td>
            <td>
              \${tagHtml}
              <div class="time-sub">Nguồn: \${(k.provider || 'ADMIN').toUpperCase()}</div>
            </td>
            <td>
              <div>\${createdDate}</div>
              <div class="time-sub">Hết hạn: \${expDate}</div>
            </td>
            <td>
              <span class="countdown-pill \${rem.class}" id="timer-\${k.key}">\${rem.str}</span>
              <div class="time-sub" id="subtimer-\${k.key}">\${rem.readable}</div>
            </td>
            <td>
              <span class="tag" style="background:var(--green-bg); color:var(--green); border:1px solid rgba(16,185,129,0.3);">
                HOẠT ĐỘNG
              </span>
            </td>
            <td>
              <button class="btn btn-danger" onclick="revokeKey('\${k.key}')" title="Thu hồi / Khóa key">
                <svg class="svg-icon" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                <span>Khóa key</span>
              </button>
            </td>
          </tr>
        \`;
      }).join('');
    }

    function startLiveCountdown() {
      if (countdownInterval) clearInterval(countdownInterval);
      countdownInterval = setInterval(() => {
        const now = Math.floor(Date.now() / 1000);
        rawKeysData.forEach(k => {
          const isLife = k.type === 'lifetime' || k.isLifetime || (k.key && k.key.startsWith('LIFEVIP'));
          if (isLife) return;
          const remSec = Math.max(0, k.expSec - now);
          const rem = formatTimeRemaining(remSec, false);
          const el = document.getElementById('timer-' + k.key);
          const subEl = document.getElementById('subtimer-' + k.key);
          if (el) {
            el.textContent = rem.str;
            el.className = 'countdown-pill ' + rem.class;
          }
          if (subEl) {
            subEl.textContent = rem.readable;
          }
        });
      }, 1000);
    }

    function copyKey(k) {
      navigator.clipboard.writeText(k);
      showToast('Đã sao chép: ' + k);
    }

    async function revokeKey(key) {
      if (!confirm('XÁC NHẬN KHÓA KEY:\\nBạn có chắc chắn muốn hủy kích hoạt mã key này ngay lập tức?\\n\\n' + key)) return;
      const pw = getStoredPw();
      try {
        const res = await fetch('${adminBasePath}/api/revoke?auth=' + encodeURIComponent(pw), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key })
        });
        const d = await res.json();
        if (d.success) {
          showToast('Đã khóa và hủy key thành công');
          loadKeys();
        } else {
          alert('Lỗi: ' + (d.error || 'Không thể khóa key'));
        }
      } catch (err) {
        alert('Lỗi mạng: ' + err.message);
      }
    }

    async function createKey(type) {
      const pw = getStoredPw();
      if (!pw) { alert('Vui lòng đăng nhập mật khẩu Admin trước!'); return; }
      try {
        const res = await fetch('${adminBasePath}/api/generate?auth=' + encodeURIComponent(pw), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type })
        });
        const d = await res.json();
        if (d.success) {
          showToast('Tạo thành công key ' + type.toUpperCase() + ': ' + d.key);
          loadKeys();
        } else {
          alert('Lỗi: ' + (d.error || 'Không tạo được key'));
        }
      } catch (err) {
        alert('Lỗi: ' + err.message);
      }
    }

    async function inspectKey() {
      const keyVal = inspectInput.value.trim().toUpperCase();
      if (!keyVal) { alert('Vui lòng dán mã key cần kiểm tra!'); return; }
      inspectResult.style.display = 'block';
      inspectResult.innerHTML = 'Đang kiểm tra chữ ký số và dữ liệu...';
      try {
        const res = await fetch('/api/check-key?key=' + encodeURIComponent(keyVal));
        const d = await res.json();
        if (!res.ok) {
          inspectResult.innerHTML = \`<div style="color:var(--red);"><b>Không hợp lệ:</b> \${d.error || 'Sai định dạng'}</div>\`;
          return;
        }

        const expDate = d.isLifetime ? 'Vĩnh viễn (Không giới hạn)' : new Date(d.expiresAt).toLocaleString('vi-VN');
        const statusHtml = d.valid
          ? \`<span style="color:var(--green); font-weight:700;">HỢP LỆ (Đang hoạt động)</span>\`
          : (d.expired ? \`<span style="color:var(--red); font-weight:700;">HẾT HẠN</span>\` : \`<span style="color:var(--red); font-weight:700;">ĐÃ BỊ KHÓA / SAI CHỮ KÝ</span>\`);

        const timeInfo = d.isLifetime
          ? '<b style="color:var(--green);">Bản Quyền Vĩnh Viễn (Lifetime VIP)</b>'
          : \`<b style="color:var(--cyan);">\${d.hoursLeft} Giờ</b> (\${d.minutesLeft} phút)\`;

        inspectResult.innerHTML = \`
          <div><b>Mã Key:</b> <span style="font-family:monospace; color:#fff;">\${d.key}</span></div>
          <div><b>Gói Bản Quyền:</b> <span style="font-weight:700; color:var(--cyan);">\${d.typeName}</span></div>
          <div><b>Trạng Thái:</b> \${statusHtml}</div>
          <div><b>Thời Gian Còn Lại:</b> \${timeInfo}</div>
          <div><b>Thời Điểm Hết Hạn:</b> \${expDate}</div>
          <div><b>Chữ Ký Mật HMAC:</b> \${d.signatureValid ? '<span style="color:var(--green)">Chuẩn xác (Server gốc)</span>' : '<span style="color:var(--red)">Giả mạo</span>'}</div>
        \`;
      } catch (e) {
        inspectResult.innerHTML = \`<div style="color:var(--red);">Lỗi: \${e.message}</div>\`;
      }
    }

    modalLoginBtn.addEventListener('click', () => {
      const pw = modalPwInput.value.trim();
      if (!pw) {
        loginErr.textContent = 'Vui lòng nhập mật khẩu quản trị!';
        loginErr.style.display = 'block';
        return;
      }
      tryLogin(pw, modalRemember.checked);
    });

    modalPwInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') modalLoginBtn.click();
    });

    refreshBtn.addEventListener('click', loadKeys);
    searchInput.addEventListener('input', renderKeysTable);
    inspectBtn.addEventListener('click', inspectKey);

    document.querySelectorAll('.filter-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentFilterType = e.target.getAttribute('data-filter');
        renderKeysTable();
      });
    });

    // Initial check: if auth param in URL or stored in browser
    const urlParams = new URLSearchParams(window.location.search);
    const paramAuth = urlParams.get('auth');
    const existingPw = getStoredPw();

    if (paramAuth) {
      tryLogin(paramAuth, true);
    } else if (existingPw) {
      tryLogin(existingPw, true);
    } else {
      loginOverlay.style.display = 'flex';
    }
  </script>
</body>
</html>`;
      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // Redirect /admin to secret slug
    if (url.pathname === "/admin" || url.pathname === "/admin/") {
      const target = new URL(`${url.origin}${adminBasePath}`);
      url.searchParams.forEach((v, k) => target.searchParams.set(k, v));
      return Response.redirect(target.toString(), 302);
    }

    // Default: Redirect to frontend
    return Response.redirect(frontendUrl, 302);
  },
};
