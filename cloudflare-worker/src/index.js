/**
 * Cloudflare Worker: Chess Stealth Pro Key Generator & Anti-Bypass
 * Protects SECRET_KEY on server-side and cryptographically verifies 2-step shortener flow.
 */

const DEFAULT_SECRET = "CHESS_STEALTH_PRO_WEB24H_SECRET_2026";
const DEFAULT_FRONTEND = "https://nghihi16.github.io/chess-stealth-pro";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
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
    const nowSec = Math.floor(Date.now() / 1000);

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

    // Default: Redirect to frontend
    return Response.redirect(frontendUrl, 302);
  },
};
