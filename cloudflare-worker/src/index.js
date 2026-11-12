/**
 * Cloudflare Worker: Chess Stealth Pro Key Generator & Admin Portal (Hardened Edition)
 * Full KV Key Management Dashboard (24H, 30D, Lifetime VIP) with:
 * - Zero ?auth= query leakage (HttpOnly Secure Cookie + Bearer session token)
 * - Replay-attack prevention via KV single-use nonce tracking on 2-step shortener callback
 * - DOM XSS mitigation via HTML entity sanitization
 * - IP-based rate limiting on admin authentication
 * - Constant-time string comparison for HMAC signatures and secrets
 */

const DEFAULT_SECRET = "CHESS_STEALTH_PRO_WEB24H_SECRET_2026";
const DEFAULT_FRONTEND = "https://nghihi16.github.io/chess-stealth-pro";
const DEFAULT_ADMIN_SLUG = "admin-788a9acf0094e887";

const SHORTENER_LINKS = {
  link4m: {
    step1: "https://link4m.org/np1nkMU3",
    step2: "https://link4m.org/B8IuTLZ",
  },
  shrinkme: {
    step1: "https://shrinkme.click/ChessProStep1v2",
    step2: "https://shrinkme.click/ChessProStep2v2",
  },
  lootlabs: {
    step1: "https://lootdest.org/s?kLgPRTNZ",
    step2: "https://lootdest.org/s?jqvjbGLG",
  },
  linkvertise: {
    step1: "https://link4m.org/np1nkMU3",
    step2: "https://link4m.org/B8IuTLZ",
  },
};

const securityHeaders = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https:; frame-ancestors 'none';",
};

const publicCorsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
  ...securityHeaders,
};

function getAdminCorsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowedFrontend = (env.FRONTEND_URL || DEFAULT_FRONTEND).replace(/\/+$/, "");
  const requestUrl = new URL(request.url);
  const allowedOrigins = [allowedFrontend, requestUrl.origin];
  const headers = { ...securityHeaders };
  if (origin && allowedOrigins.includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization";
    headers["Access-Control-Allow-Credentials"] = "true";
    headers["Vary"] = "Origin";
  }
  return headers;
}

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

function timingSafeEqualStr(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const bufA = enc.encode(a);
  const bufB = enc.encode(b);
  const len = Math.max(bufA.byteLength, bufB.byteLength);
  let c = bufA.byteLength ^ bufB.byteLength;
  for (let i = 0; i < len; i++) {
    const byteA = i < bufA.byteLength ? bufA[i] : 0;
    const byteB = i < bufB.byteLength ? bufB[i] : 0;
    c |= byteA ^ byteB;
  }
  return c === 0;
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

async function verifyAdminSession(request, env, secret, expectedPass) {
  if (!expectedPass || typeof expectedPass !== "string" || expectedPass.trim() === "") {
    return false; // Fail closed if admin password is unset
  }
  const sessionToken = await hmacSha256("ADMIN_SESSION:" + expectedPass, secret);
  const validTokens = [sessionToken];

  // 1. Check HttpOnly cookie
  const cookies = parseCookies(request.headers.get("Cookie") || "");
  const sessionCookie = cookies["csp_admin_session"];
  if (sessionCookie) {
    for (const vt of validTokens) {
      if (timingSafeEqualStr(sessionCookie, vt)) return true;
    }
  }

  // 2. Check Authorization header: Bearer <sessionToken or expectedPass>
  const authHeader = request.headers.get("Authorization");
  if (authHeader && authHeader.startsWith("Bearer ")) {
    const bearer = authHeader.slice(7).trim();
    for (const vt of validTokens) {
      if (timingSafeEqualStr(bearer, vt)) return true;
    }
    if (timingSafeEqualStr(bearer, expectedPass)) {
      return true;
    }
  }

  return false;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const secret = env.SECRET_KEY || DEFAULT_SECRET;
    const frontendUrl = (env.FRONTEND_URL || DEFAULT_FRONTEND).replace(/\/+$/, "");
    const adminPassword = (env.ADMIN_PASSWORD || "").trim();
    const adminSlug = (env.ADMIN_PATH || DEFAULT_ADMIN_SLUG).replace(/^\/+|\/+$/g, "");
    const adminBasePath = `/${adminSlug}`;
    const nowSec = Math.floor(Date.now() / 1000);

    const isAdminRoute = url.pathname === adminBasePath || url.pathname.startsWith(adminBasePath + "/") ||
                         url.pathname === "/admin" || url.pathname.startsWith("/admin/") ||
                         url.pathname.startsWith("/api/admin");

    if (request.method === "OPTIONS") {
      if (isAdminRoute) {
        return new Response(null, { headers: getAdminCorsHeaders(request, env) });
      }
      return new Response(null, { headers: publicCorsHeaders });
    }

    // Block /admin, /admin/, and /api/admin/* with 404 to prevent administrative path leakage
    if (url.pathname === "/admin" || url.pathname === "/admin/" || url.pathname.startsWith("/api/admin")) {
      return new Response(JSON.stringify({ error: "Not Found" }), {
        status: 404,
        headers: { "Content-Type": "application/json", ...securityHeaders },
      });
    }

    // 1. Health check
    if (url.pathname === "/api/health") {
      return new Response(JSON.stringify({ status: "ok", time: nowSec }), {
        headers: { "Content-Type": "application/json", ...publicCorsHeaders },
      });
    }

    // 2. Check Key API: Decodes and inspects 24H, 7D, 30D, and Lifetime keys
    if (url.pathname === "/api/check-key") {
      const cleanKey = (url.searchParams.get("key") || "").trim().toUpperCase();
      const parts = cleanKey.split("-");

      if (parts.length !== 4) {
        return new Response(
          JSON.stringify({
            valid: false,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      const [prefix, tokenId, expHex, providedSig] = parts;
      if (
        !["FREE24H", "PRO07D", "PRO30D", "LIFEVIP"].includes(prefix) ||
        tokenId.length !== 6 ||
        expHex.length !== 8 ||
        providedSig.length !== 6
      ) {
        return new Response(
          JSON.stringify({
            valid: false,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      const expectedSig = (await hmacSha256(`KEY:${tokenId}:${expHex}`, secret)).slice(0, 6);
      const isSigValid = timingSafeEqualStr(providedSig, expectedSig);
      if (!isSigValid) {
        return new Response(
          JSON.stringify({
            valid: false,
            signatureValid: false,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      let isRevoked = false;
      let kvRecord = null;
      let boundHwid = null;
      if (env.KEYS_KV) {
        try {
          const revoked = await env.KEYS_KV.get(`revoked:${cleanKey}`);
          if (revoked) isRevoked = true;
          const rawRecord = await env.KEYS_KV.get(`key:${cleanKey}`);
          if (rawRecord) {
            kvRecord = JSON.parse(rawRecord);
            boundHwid = kvRecord.hwid || null;
          }
        } catch (_) {}
      }

      if (isRevoked) {
        return new Response(
          JSON.stringify({
            valid: false,
            revoked: true,
            isRevoked: true,
            signatureValid: true,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      const reqHwid = (url.searchParams.get("hwid") || "").trim().toUpperCase();
      if (boundHwid && reqHwid && boundHwid !== reqHwid) {
        return new Response(
          JSON.stringify({
            valid: false,
            hwidMismatch: true,
            error: "HWID Mismatch: Key đã được kích hoạt trên thiết bị khác",
            message: `Key này đã được khóa vào thiết bị khác (${boundHwid}).`,
            hwid: boundHwid,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }
      if (!boundHwid && reqHwid && kvRecord && env.KEYS_KV) {
        try {
          kvRecord.hwid = reqHwid;
          const putOptions = kvRecord.expSec ? { expiration: kvRecord.expSec } : {};
          await env.KEYS_KV.put(`key:${cleanKey}`, JSON.stringify(kvRecord), putOptions);
          boundHwid = reqHwid;
        } catch (_) {}
      }

      if (prefix === "LIFEVIP" || expHex === "FFFFFFFF") {
        const isFormatValid = expHex === "FFFFFFFF";
        if (!isFormatValid) {
          return new Response(
            JSON.stringify({
              valid: false,
              error: "Invalid Key",
              message: "Invalid Key",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json", ...publicCorsHeaders },
            }
          );
        }
        return new Response(
          JSON.stringify({
            valid: true,
            key: cleanKey,
            type: "lifetime",
            typeName: "Vĩnh Viễn (Lifetime VIP)",
            signatureValid: true,
            isLifetime: true,
            hwid: boundHwid,
            expired: false,
            revoked: false,
            remainingSec: null,
            hoursLeft: "Vĩnh viễn",
            minutesLeft: null,
            expiresAt: null,
            currentTime: new Date(nowSec * 1000).toISOString(),
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      const expSec = parseInt(expHex, 16);
      if (isNaN(expSec)) {
        return new Response(
          JSON.stringify({
            valid: false,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      const remainingSec = Math.max(0, expSec - nowSec);
      const isExpired = remainingSec === 0;
      if (isExpired) {
        return new Response(
          JSON.stringify({
            valid: false,
            expired: true,
            isExpired: true,
            error: "Invalid Key",
            message: "Invalid Key",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json", ...publicCorsHeaders },
          }
        );
      }

      let type = "24h";
      let typeName = "Bản Quyền 24 Giờ";
      if (prefix === "PRO30D") {
        type = "30d";
        typeName = "Bản Quyền 30 Ngày";
      } else if (prefix === "PRO07D") {
        type = "7d";
        typeName = "Bản Quyền 7 Ngày";
      }

      const hoursLeft = parseFloat((remainingSec / 3600).toFixed(1));
      const minutesLeft = Math.floor(remainingSec / 60);

      return new Response(
        JSON.stringify({
          valid: true,
          key: cleanKey,
          type: type,
          typeName: typeName,
          signatureValid: true,
          isLifetime: false,
          hwid: boundHwid,
          expired: false,
          revoked: false,
          remainingSec,
          hoursLeft,
          minutesLeft,
          expiresAt: new Date(expSec * 1000).toISOString(),
          currentTime: new Date(nowSec * 1000).toISOString(),
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json", ...publicCorsHeaders },
        }
      );
    }

    // 2b. Shortener Redirect Routes (/go/step1 & /go/step2)
    if (url.pathname === "/go/step1") {
      const provider = (url.searchParams.get("provider") || "link4m").toLowerCase();
      const target = (SHORTENER_LINKS[provider] || SHORTENER_LINKS.link4m).step1;
      return Response.redirect(target, 302);
    }

    if (url.pathname === "/go/step2") {
      const provider = (url.searchParams.get("provider") || "link4m").toLowerCase();
      const token = url.searchParams.get("token") || "";
      const target = (SHORTENER_LINKS[provider] || SHORTENER_LINKS.link4m).step2;
      const headers = new Headers(publicCorsHeaders);
      headers.set("Location", target);
      if (token) {
        headers.set(
          "Set-Cookie",
          `csp_step1_grant=${encodeURIComponent(token)}; Path=/; Max-Age=1200; Secure; SameSite=Lax`
        );
      }
      return new Response(null, { status: 302, headers });
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

      const headers = new Headers(publicCorsHeaders);
      headers.set("Location", redirectTarget);
      headers.set(
        "Set-Cookie",
        `csp_step1_grant=${encodeURIComponent(token)}; Path=/; Max-Age=1200; Secure; SameSite=Lax`
      );
      return new Response(null, { status: 302, headers });
    }

    // 4. Step 2 Callback with Replay-Attack Hardening
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
      if (!timingSafeEqualStr(providedSig, expectedSig)) {
        return Response.redirect(`${frontendUrl}/?error=invalid_signature`, 302);
      }

      const parts = payloadStr.split(":");
      if (parts.length < 4) {
        return Response.redirect(`${frontendUrl}/?error=invalid_token_format`, 302);
      }

      const tokenExp = parseInt(parts[2], 10);
      if (isNaN(tokenExp) || nowSec > tokenExp) {
        return Response.redirect(`${frontendUrl}/?error=token_expired`, 302);
      }

      // Replay Attack Protection: Ensure nonce is strictly single-use
      const nonce = parts[3];
      if (env.KEYS_KV && nonce) {
        const alreadyConsumed = await env.KEYS_KV.get(`consumed_nonce:${nonce}`);
        if (alreadyConsumed) {
          return Response.redirect(`${frontendUrl}/?error=token_already_consumed`, 302);
        }
        await env.KEYS_KV.put(`consumed_nonce:${nonce}`, "1", { expirationTtl: 1200 });
      }

      // Validated single-use! Generate the 24-hour key
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
            hwid: null,
            createdAt: nowSec,
            expSec: expSec,
            status: "active",
          };
          await env.KEYS_KV.put(`key:${licenseKey}`, JSON.stringify(record), {
            expiration: expSec,
          });
        } catch (_) {}
      }

      const redirectTarget = `${frontendUrl}/?key=${encodeURIComponent(licenseKey)}&token=${encodeURIComponent(urlToken)}&provider=${encodeURIComponent(prov)}`;
      const headers = new Headers(publicCorsHeaders);
      headers.set("Location", redirectTarget);
      headers.set(
        "Set-Cookie",
        "csp_step1_grant=deleted; Path=/; Max-Age=0; Secure; SameSite=Lax"
      );
      return new Response(null, { status: 302, headers });
    }

    // ==========================================
    // 5. HARDENED ADMIN AUTHENTICATION & APIS
    // ==========================================

    // Admin Login API (Rate limiting + Secure HttpOnly Cookie + Session Token)
    if (url.pathname === `${adminBasePath}/api/login` && request.method === "POST") {
      if (!adminPassword) {
        return new Response(
          JSON.stringify({
            success: false,
            error: "Quản trị viên chưa được cấu hình mật khẩu bảo mật trong Worker secrets.",
          }),
          {
            status: 500,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          }
        );
      }

      const clientIp = request.headers.get("CF-Connecting-IP") || "0.0.0.0";
      const rateKey = `rate_login:${clientIp}`;
      let fails = 0;

      if (env.KEYS_KV) {
        const stored = await env.KEYS_KV.get(rateKey);
        if (stored) fails = parseInt(stored, 10) || 0;
      }

      if (fails >= 5) {
        return new Response(
          JSON.stringify({
            error: "Tài khoản bị tạm khóa 15 phút do nhập sai mật khẩu quá 5 lần để chống tấn công brute-force.",
          }),
          {
            status: 429,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          }
        );
      }

      try {
        const body = await request.json();
        const inputPw = (body.password || "").trim();

        if (!inputPw) {
          return new Response(
            JSON.stringify({
              success: false,
              error: "Vui lòng nhập mật khẩu",
            }),
            {
              status: 400,
              headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
            }
          );
        }

        const isMatch = timingSafeEqualStr(inputPw, adminPassword);
        if (!isMatch) {
          fails += 1;
          if (env.KEYS_KV) {
            await env.KEYS_KV.put(rateKey, fails.toString(), { expirationTtl: 900 });
          }
          return new Response(
            JSON.stringify({
              success: false,
              error: `Mật khẩu quản trị viên không chính xác! (Còn ${Math.max(0, 5 - fails)} lần thử)`,
            }),
            {
              status: 401,
              headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
            }
          );
        }

        if (env.KEYS_KV && fails > 0) {
          await env.KEYS_KV.delete(rateKey);
        }

        const sessionToken = await hmacSha256("ADMIN_SESSION:" + adminPassword, secret);
        const headers = new Headers();
        headers.set("Content-Type", "application/json");
        const adminCors = getAdminCorsHeaders(request, env);
        for (const [k, v] of Object.entries(adminCors)) {
          headers.set(k, v);
        }
        headers.set(
          "Set-Cookie",
          `csp_admin_session=${sessionToken}; Path=/; Max-Age=86400; HttpOnly; Secure; SameSite=Lax`
        );
        return new Response(
          JSON.stringify({
            success: true,
            token: sessionToken,
            message: "Đăng nhập thành công",
          }),
          {
            status: 200,
            headers,
          }
        );
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }
    }

    // Admin Logout API
    if (url.pathname === `${adminBasePath}/api/logout` && request.method === "POST") {
      const headers = new Headers();
      headers.set("Content-Type", "application/json");
      const adminCors = getAdminCorsHeaders(request, env);
      for (const [k, v] of Object.entries(adminCors)) {
        headers.set(k, v);
      }
      headers.set(
        "Set-Cookie",
        "csp_admin_session=deleted; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"
      );
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers,
      });
    }

    // Admin API: List all active keys
    if (url.pathname === `${adminBasePath}/api/keys`) {
      if (!adminPassword) {
        return new Response(JSON.stringify({ error: "Unauthorized: Quản trị viên chưa cấu hình mật khẩu" }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      const isAuth = await verifyAdminSession(request, env, secret, adminPassword);
      if (!isAuth) {
        return new Response(JSON.stringify({ error: "Unauthorized: Phiên đăng nhập quản trị không hợp lệ" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
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
                data.hwid = data.hwid || null;
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

      keysList.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
      return new Response(JSON.stringify({ success: true, count: keysList.length, keys: keysList }), {
        status: 200,
        headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
      });
    }

    // Admin API: Revoke a key
    if (url.pathname === `${adminBasePath}/api/revoke` && request.method === "POST") {
      if (!adminPassword) {
        return new Response(JSON.stringify({ error: "Unauthorized: Quản trị viên chưa cấu hình mật khẩu" }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      const isAuth = await verifyAdminSession(request, env, secret, adminPassword);
      if (!isAuth) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      try {
        const body = await request.json();
        const targetKey = (body.key || "").trim().toUpperCase();
        if (targetKey && env.KEYS_KV) {
          await env.KEYS_KV.delete(`key:${targetKey}`);
          await env.KEYS_KV.put(`revoked:${targetKey}`, "1", { expirationTtl: 86400 * 365 });
          return new Response(JSON.stringify({ success: true, revoked: targetKey }), {
            status: 200,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          });
        }
        return new Response(JSON.stringify({ error: "Thiếu mã key" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }
    }

    // Admin API: Generate Key manually (24h, 30d, lifetime)
    if (url.pathname === `${adminBasePath}/api/generate` && request.method === "POST") {
      if (!adminPassword) {
        return new Response(JSON.stringify({ error: "Unauthorized: Quản trị viên chưa cấu hình mật khẩu" }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      const isAuth = await verifyAdminSession(request, env, secret, adminPassword);
      if (!isAuth) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      let keyType = "24h";
      let keyNote = "";
      let keyHwid = null;
      try {
        const body = await request.json();
        if (body.type) keyType = body.type.toLowerCase();
        if (body.note) keyNote = String(body.note).slice(0, 100);
        if (body.hwid && typeof body.hwid === "string") {
          keyHwid = body.hwid.trim().toUpperCase().slice(0, 64) || null;
        }
      } catch (_) {}

      const tokenId = randomHex(6);
      let prefix = "FREE24H";
      let expSec = null;
      let expHex = "FFFFFFFF";
      let kvTtl = null;

      if (keyType === "30d" || keyType === "monthly") {
        keyType = "30d";
        prefix = "PRO30D";
        expSec = nowSec + 30 * 86400;
        expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        kvTtl = expSec;
      } else if (keyType === "7d" || keyType === "weekly") {
        keyType = "7d";
        prefix = "PRO07D";
        expSec = nowSec + 7 * 86400;
        expHex = expSec.toString(16).toUpperCase().padStart(8, "0");
        kvTtl = expSec;
      } else if (keyType === "lifetime" || keyType === "vip") {
        keyType = "lifetime";
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
            note: keyNote,
            hwid: keyHwid || null,
            createdAt: nowSec,
            expSec: expSec,
            status: "active",
          };
          const putOptions = kvTtl ? { expiration: kvTtl } : {};
          await env.KEYS_KV.put(`key:${licenseKey}`, JSON.stringify(record), putOptions);
        } catch (_) {}
      }

      return new Response(
        JSON.stringify({
          success: true,
          key: licenseKey,
          type: keyType,
          hwid: keyHwid || null,
          expSec: expSec,
          isLifetime: keyType === "lifetime",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        }
      );
    }

    // Admin API: Bind or unbind HWID for a key
    if (url.pathname === `${adminBasePath}/api/bind-hwid` && request.method === "POST") {
      if (!adminPassword) {
        return new Response(JSON.stringify({ error: "Unauthorized: Quản trị viên chưa cấu hình mật khẩu" }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      const isAuth = await verifyAdminSession(request, env, secret, adminPassword);
      if (!isAuth) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }

      try {
        const body = await request.json();
        const targetKey = (body.key || "").trim().toUpperCase();
        if (!targetKey) {
          return new Response(JSON.stringify({ error: "Thiếu mã key" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          });
        }

        const newHwid = body.hwid ? String(body.hwid).trim().toUpperCase().slice(0, 64) : null;
        if (!env.KEYS_KV) {
          return new Response(JSON.stringify({ error: "KV storage không khả dụng" }), {
            status: 500,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          });
        }

        const raw = await env.KEYS_KV.get(`key:${targetKey}`);
        if (!raw) {
          return new Response(JSON.stringify({ error: "Không tìm thấy key trong hệ thống" }), {
            status: 404,
            headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
          });
        }

        const record = JSON.parse(raw);
        record.hwid = newHwid || null;
        const putOptions = record.expSec ? { expiration: record.expSec } : {};
        await env.KEYS_KV.put(`key:${targetKey}`, JSON.stringify(record), putOptions);

        return new Response(JSON.stringify({ success: true, key: targetKey, hwid: record.hwid }), {
          status: 200,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...getAdminCorsHeaders(request, env) },
        });
      }
    }

    // ==========================================
    // 6. ADMIN HTML USER INTERFACE (Full KV Key Management Dashboard)
    // ==========================================
    if (url.pathname === adminBasePath || url.pathname === `${adminBasePath}/`) {
      if (!adminPassword) {
        return new Response(
          "Cảnh báo bảo mật: ADMIN_PASSWORD chưa được thiết lập trong Worker secrets. Cổng quản trị bị khóa an toàn.",
          {
            status: 500,
            headers: { "Content-Type": "text/plain; charset=utf-8", ...securityHeaders },
          }
        );
      }
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
    .hwid-badge {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      font-weight: 600;
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: var(--cyan);
      padding: 3px 8px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      letter-spacing: 0.02em;
    }
    .hwid-empty {
      font-size: 12px;
      color: var(--text-muted);
      font-style: italic;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn-hwid {
      background: #1e293b;
      color: var(--text-sub);
      border: 1px solid #334155;
      padding: 4px 8px;
      font-size: 11px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-weight: 500;
      transition: all 0.15s ease;
    }
    .btn-hwid:hover {
      background: #334155;
      color: #ffffff;
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
      flex-wrap: wrap;
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
      <div style="display:flex; flex-direction:column; gap:6px;">
        <div style="font-size: 14px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 8px;">
          <svg class="svg-icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Tạo Mã Key Mới:</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <input type="text" id="gen-hwid" placeholder="Gán HWID máy khách (tùy chọn)..." style="max-width: 290px; min-height:36px; padding:6px 10px; font-size:12px; font-family:monospace;"/>
        </div>
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
          <input type="text" id="search-input" placeholder="Tìm theo Mã Key, HWID (máy), loại gói..."/>
        </div>
        <div class="filter-pills">
          <button class="filter-pill active" data-filter="all">Tất cả</button>
          <button class="filter-pill" data-filter="24h">24 Giờ</button>
          <button class="filter-pill" data-filter="30d">30 Ngày</button>
          <button class="filter-pill" data-filter="lifetime">Lifetime</button>
          <button class="filter-pill" data-filter="has-hwid">Đã gắn máy</button>
          <button class="filter-pill" data-filter="no-hwid">Chưa gắn</button>
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
              <th>Thiết Bị (HWID Máy)</th>
              <th>Thời Gian Cấp & Hết Hạn</th>
              <th>Thời Gian Còn Lại</th>
              <th>Trạng Thái</th>
              <th>Thao Tác</th>
            </tr>
          </thead>
          <tbody id="keys-tbody">
            <tr>
              <td colspan="7">
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
    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

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

    function getStoredToken() {
      return localStorage.getItem('csp_admin_token') || sessionStorage.getItem('csp_admin_token') || '';
    }

    function saveToken(token, remember) {
      if (!token) return;
      if (remember) {
        localStorage.setItem('csp_admin_token', token);
        sessionStorage.removeItem('csp_admin_token');
      } else {
        sessionStorage.setItem('csp_admin_token', token);
        localStorage.removeItem('csp_admin_token');
      }
    }

    function clearStoredToken() {
      localStorage.removeItem('csp_admin_token');
      sessionStorage.removeItem('csp_admin_token');
      localStorage.removeItem('csp_admin_pw');
      sessionStorage.removeItem('csp_admin_pw');
    }

    function getAuthHeaders() {
      const headers = { 'Content-Type': 'application/json' };
      const token = getStoredToken();
      if (token) {
        headers['Authorization'] = 'Bearer ' + token;
      }
      return headers;
    }

    async function logout() {
      clearStoredToken();
      await fetch('${adminBasePath}/api/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
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
        const res = await fetch('${adminBasePath}/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ password: pw })
        });
        const data = await res.json();

        if (!res.ok || !data.success) {
          loginErr.textContent = data.error || 'Mật khẩu quản trị viên không chính xác!';
          loginErr.style.display = 'block';
          modalLoginBtn.disabled = false;
          modalLoginBtn.style.opacity = '1';
          loginOverlay.style.display = 'flex';
          return false;
        }

        if (data.token) {
          saveToken(data.token, remember !== false);
        }
        loginOverlay.style.display = 'none';
        modalLoginBtn.disabled = false;
        modalLoginBtn.style.opacity = '1';
        modalPwInput.value = '';

        await loadKeys();
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
      try {
        const res = await fetch('${adminBasePath}/api/keys', {
          headers: getAuthHeaders(),
          credentials: 'same-origin'
        });
        if (res.status === 401) {
          loginOverlay.style.display = 'flex';
          return;
        }
        if (!res.ok) {
          showToast('Lỗi tải danh sách key từ server');
          return;
        }
        loginOverlay.style.display = 'none';
        const data = await res.json();
        rawKeysData = data.keys || [];
        statCount.textContent = rawKeysData.length;
        renderKeysTable();
        startLiveCountdown();
      } catch (_) {
        loginOverlay.style.display = 'flex';
      }
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
        else if (currentFilterType === 'has-hwid') matchesFilter = Boolean(k.hwid);
        else if (currentFilterType === 'no-hwid') matchesFilter = !k.hwid;

        if (!matchesFilter) return false;
        if (!search) return true;
        return k.key.toLowerCase().includes(search) || 
               (k.hwid || '').toLowerCase().includes(search) ||
               (k.provider || '').toLowerCase().includes(search) || 
               (k.type || '').toLowerCase().includes(search);
      });

      if (filtered.length === 0) {
        tbody.innerHTML = \`<tr><td colspan="7"><div class="empty-state"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg><span>\${rawKeysData.length === 0 ? "Hiện tại chưa có key nào trong Cloudflare KV. Bấm các nút phía trên để tạo key mới." : "Không tìm thấy key nào khớp với bộ lọc."}</span></div></td></tr>\`;
        return;
      }

      const now = Math.floor(Date.now() / 1000);
      tbody.innerHTML = filtered.map(k => {
        const safeKey = escapeHtml(k.key);
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

        let hwidHtml = '';
        if (k.hwid) {
          const rawHwid = String(k.hwid);
          const shortHwid = rawHwid.length > 22 ? rawHwid.slice(0, 10) + '...' + rawHwid.slice(-8) : rawHwid;
          hwidHtml = \`
            <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start;">
              <div class="hwid-badge" title="\${escapeHtml(rawHwid)}">
                <svg class="svg-icon" style="width:12px; height:12px;" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                <span>\${escapeHtml(shortHwid)}</span>
              </div>
              <div style="display:flex; gap:6px;">
                <button class="btn-hwid" onclick="copyKey('\${escapeHtml(rawHwid)}')" title="Sao chép HWID máy">
                  <svg class="svg-icon" style="width:11px; height:11px;" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>Chép</span>
                </button>
                <button class="btn-hwid" onclick="bindHwidPrompt('\${safeKey}', '\${escapeHtml(rawHwid)}')" title="Đổi hoặc gỡ HWID">
                  <svg class="svg-icon" style="width:11px; height:11px;" viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                  <span>Đổi</span>
                </button>
              </div>
            </div>
          \`;
        } else {
          hwidHtml = \`
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="hwid-empty">Chưa gắn máy</span>
              <button class="btn-hwid" onclick="bindHwidPrompt('\${safeKey}', '')" title="Gán HWID máy cho key này">
                <svg class="svg-icon" style="width:11px; height:11px;" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                <span>Gán máy</span>
              </button>
            </div>
          \`;
        }

        return \`
          <tr id="row-\${safeKey}">
            <td>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="key-badge">\${safeKey}</span>
                <button class="btn-copy" onclick="copyKey('\${safeKey}')" title="Sao chép key">
                  <svg class="svg-icon" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>Chép</span>
                </button>
              </div>
            </td>
            <td>
              \${tagHtml}
              <div class="time-sub">Nguồn: \${escapeHtml((k.provider || 'ADMIN').toUpperCase())}</div>
            </td>
            <td>
              \${hwidHtml}
            </td>
            <td>
              <div>\${escapeHtml(createdDate)}</div>
              <div class="time-sub">Hết hạn: \${escapeHtml(expDate)}</div>
            </td>
            <td>
              <span class="countdown-pill \${rem.class}" id="timer-\${safeKey}">\${rem.str}</span>
              <div class="time-sub" id="subtimer-\${safeKey}">\${rem.readable}</div>
            </td>
            <td>
              <span class="tag" style="background:var(--green-bg); color:var(--green); border:1px solid rgba(16,185,129,0.3);">
                HOẠT ĐỘNG
              </span>
            </td>
            <td>
              <button class="btn btn-danger" onclick="revokeKey('\${safeKey}')" title="Thu hồi / Khóa key">
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
      navigator.clipboard.writeText(k).catch(() => {});
      showToast('Đã sao chép: ' + k);
    }

    async function revokeKey(key) {
      if (!confirm('XÁC NHẬN KHÓA KEY:\\nBạn có chắc chắn muốn hủy kích hoạt mã key này ngay lập tức?\\n\\n' + key)) return;
      try {
        const res = await fetch('${adminBasePath}/api/revoke', {
          method: 'POST',
          headers: getAuthHeaders(),
          credentials: 'same-origin',
          body: JSON.stringify({ key })
        });
        if (res.status === 401) {
          loginOverlay.style.display = 'flex';
          return;
        }
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

    async function bindHwidPrompt(key, currentHwid) {
      const input = prompt(
        "Nhập HWID máy (Hardware ID) cho key:\n" + key + "\n\n(Lưu ý: Để trống và bấm OK nếu muốn hủy gán máy để cho phép máy khác kích hoạt)",
        currentHwid || ""
      );
      if (input === null) return;
      const targetHwid = input.trim();
      try {
        const res = await fetch('${adminBasePath}/api/bind-hwid', {
          method: 'POST',
          headers: getAuthHeaders(),
          credentials: 'same-origin',
          body: JSON.stringify({ key, hwid: targetHwid })
        });
        if (res.status === 401) {
          loginOverlay.style.display = 'flex';
          return;
        }
        const d = await res.json();
        if (d.success) {
          showToast(targetHwid ? 'Đã gán HWID thành công!' : 'Đã hủy gán máy (Unbind HWID) thành công!');
          loadKeys();
        } else {
          alert('Lỗi: ' + (d.error || 'Không thể cập nhật HWID'));
        }
      } catch (err) {
        alert('Lỗi mạng: ' + err.message);
      }
    }

    async function createKey(type) {
      const hwidVal = (document.getElementById('gen-hwid')?.value || '').trim();
      try {
        const res = await fetch('${adminBasePath}/api/generate', {
          method: 'POST',
          headers: getAuthHeaders(),
          credentials: 'same-origin',
          body: JSON.stringify({ type, hwid: hwidVal })
        });
        if (res.status === 401) {
          loginOverlay.style.display = 'flex';
          return;
        }
        const d = await res.json();
        if (d.success) {
          navigator.clipboard.writeText(d.key).catch(() => {});
          const hwidNote = d.hwid ? ' (Đã gắn HWID: ' + d.hwid + ')' : '';
          showToast('Đã tạo & sao chép key ' + type.toUpperCase() + ': ' + d.key + hwidNote);
          const genHwidInput = document.getElementById('gen-hwid');
          if (genHwidInput) genHwidInput.value = '';
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
      inspectResult.innerHTML = 'Đang kiểm tra...';
      try {
        const res = await fetch('/api/check-key?key=' + encodeURIComponent(keyVal));
        const d = await res.json();
        if (!res.ok || !d.valid) {
          inspectResult.innerHTML = '<div style="color:var(--red); font-weight:700; font-size:14px;">Invalid Key</div>';
          return;
        }

        const expDate = d.isLifetime ? 'Vĩnh viễn (Không giới hạn)' : new Date(d.expiresAt).toLocaleString('vi-VN');
        const statusHtml = '<span style="color:var(--green); font-weight:700;">HỢP LỆ (Đang hoạt động)</span>';
        const timeInfo = d.isLifetime
          ? '<b style="color:var(--green);">Bản Quyền Vĩnh Viễn (Lifetime VIP)</b>'
          : \`<b style="color:var(--cyan);">\${escapeHtml(d.hoursLeft)} Giờ</b> (\${escapeHtml(d.minutesLeft)} phút)\`;
        const hwidInfo = d.hwid
          ? \`<span style="font-family:monospace; color:var(--cyan); font-weight:700;">\${escapeHtml(d.hwid)}</span>\`
          : \`<span style="color:var(--text-muted); font-style:italic;">Chưa gắn máy (Tự động nhận diện & khóa máy đầu tiên kích hoạt)</span>\`;

        inspectResult.innerHTML = \`
          <div><b>Mã Key:</b> <span style="font-family:monospace; color:#fff;">\${escapeHtml(d.key)}</span></div>
          <div><b>Gói Bản Quyền:</b> <span style="font-weight:700; color:var(--cyan);">\${escapeHtml(d.typeName)}</span></div>
          <div><b>Thiết Bị (HWID Máy):</b> \${hwidInfo}</div>
          <div><b>Trạng Thái:</b> \${statusHtml}</div>
          <div><b>Thời Gian Còn Lại:</b> \${timeInfo}</div>
          <div><b>Thời Điểm Hết Hạn:</b> \${escapeHtml(expDate)}</div>
          <div><b>Chữ Ký Mật HMAC:</b> <span style="color:var(--green)">Chuẩn xác (Server gốc)</span></div>
        \`;
      } catch (e) {
        inspectResult.innerHTML = '<div style="color:var(--red); font-weight:700; font-size:14px;">Invalid Key</div>';
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
    inspectInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') inspectKey();
    });

    document.querySelectorAll('.filter-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentFilterType = e.target.getAttribute('data-filter');
        renderKeysTable();
      });
    });

    window.addEventListener('DOMContentLoaded', loadKeys);
  </script>
</body>
</html>`;
      return new Response(html, {
        headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", ...securityHeaders },
      });
    }

    // Default: Redirect to frontend
    const fallbackHeaders = new Headers(securityHeaders);
    fallbackHeaders.set("Location", frontendUrl);
    return new Response(null, { status: 302, headers: fallbackHeaders });
  },
};
