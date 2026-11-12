# -*- coding: utf-8 -*-
"""
Unit and integration tests for Milestone 3 (M3: Cloudflare Worker & Supabase Security Hardening).

Verifies:
1. Complete eradication of the hardcoded admin backdoor ("admin_chess_pro_2026").
2. Protection of administrative paths: /admin and /admin/ return HTTP 404 (no 302 redirect).
3. Obfuscation of admin APIs: /api/admin/* endpoints return HTTP 404.
4. Fail-closed behavior when ADMIN_PASSWORD is unset or empty (HTTP 500).
5. Constant-time string comparisons (timingSafeEqualStr).
6. Strict CORS policy: admin endpoints never return wildcard '*' for unauthorized origins.
7. Production security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP).
8. Wrangler configuration sanitization: no committed plaintext secrets in wrangler.toml.
9. Supabase PostgreSQL migrations: Row Level Security (RLS) enabled on all tables,
   anon permissions revoked, service_role access granted, and commercial test keys purged.
"""

import json
import os
import re
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_FILES = [
    os.path.join(REPO_ROOT, "server_worker.js"),
    os.path.join(REPO_ROOT, "cloudflare-worker", "src", "index.js"),
]
WRANGLER_FILE = os.path.join(REPO_ROOT, "cloudflare-worker", "wrangler.toml")
MIGRATION_V0 = os.path.join(REPO_ROOT, "supabase", "migrations", "20261106000000_init_license_schema.sql")
MIGRATION_V1 = os.path.join(REPO_ROOT, "supabase", "migrations", "20261106000001_harden_rls_security.sql")


def run_node_worker_eval(script: str) -> dict:
    """Helper to evaluate worker behavior in Node.js runtime."""
    full_script = f"""
    import('./server_worker.js').then(async (m) => {{
        const worker = m.default;
        try {{
            {script}
        }} catch (err) {{
            console.error(err);
            process.exit(1);
        }}
    }});
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", full_script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {proc.returncode}):\n{proc.stderr}\nOutput: {proc.stdout}")
    return json.loads(proc.stdout.strip())


# ==============================================================================
# Task 1: Admin Backdoor Removal & Static Code Inspection
# ==============================================================================

@pytest.mark.parametrize("worker_path", WORKER_FILES)
def test_hardcoded_admin_backdoor_password_purged(worker_path):
    """Verify that DEFAULT_ADMIN_PW and 'admin_chess_pro_2026' are completely eradicated."""
    assert os.path.exists(worker_path), f"Worker file missing: {worker_path}"
    with open(worker_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "DEFAULT_ADMIN_PW" not in content, f"Found DEFAULT_ADMIN_PW in {worker_path}"
    assert "admin_chess_pro_2026" not in content, f"Found backdoor password in {worker_path}"


@pytest.mark.parametrize("worker_path", WORKER_FILES)
def test_constant_time_string_comparison_implemented(worker_path):
    """Verify timingSafeEqualStr exists and enforces constant-time loop over all bytes."""
    with open(worker_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "function timingSafeEqualStr" in content
    assert "byteLength" in content
    assert "^" in content  # XOR byte accumulation


# ==============================================================================
# Task 2: Cloudflare Worker Endpoint & CORS Hardening (Dynamic Node.js Execution)
# ==============================================================================

def test_admin_redirect_leakage_prevented_returns_404():
    """Verify hitting /admin or /admin/ returns 404 rather than 302 redirecting to the secret slug."""
    script = """
    const env = { ADMIN_PASSWORD: 'secure_pwd', ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const r1 = await worker.fetch(new Request('https://edge.worker.dev/admin'), env);
    const r2 = await worker.fetch(new Request('https://edge.worker.dev/admin/'), env);
    console.log(JSON.stringify({
        status1: r1.status,
        status2: r2.status,
        loc1: r1.headers.get('location'),
        loc2: r2.headers.get('location')
    }));
    """
    res = run_node_worker_eval(script)
    assert res["status1"] == 404, f"Expected 404 for /admin, got {res['status1']}"
    assert res["status2"] == 404, f"Expected 404 for /admin/, got {res['status2']}"
    assert res["loc1"] is None, "Should not leak admin slug via Location header"
    assert res["loc2"] is None, "Should not leak admin slug via Location header"


def test_public_admin_api_endpoints_return_404():
    """Verify un-obfuscated /api/admin/* endpoints are blocked with 404."""
    script = """
    const env = { ADMIN_PASSWORD: 'secure_pwd', ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const rKeys = await worker.fetch(new Request('https://edge.worker.dev/api/admin/keys'), env);
    const rRevoke = await worker.fetch(new Request('https://edge.worker.dev/api/admin/revoke', { method: 'POST' }), env);
    const rGen = await worker.fetch(new Request('https://edge.worker.dev/api/admin/generate', { method: 'POST' }), env);
    const rLogin = await worker.fetch(new Request('https://edge.worker.dev/api/admin/login', { method: 'POST' }), env);
    console.log(JSON.stringify({
        statusKeys: rKeys.status,
        statusRevoke: rRevoke.status,
        statusGen: rGen.status,
        statusLogin: rLogin.status
    }));
    """
    res = run_node_worker_eval(script)
    assert res["statusKeys"] == 404
    assert res["statusRevoke"] == 404
    assert res["statusGen"] == 404
    assert res["statusLogin"] == 404


def test_old_backdoor_password_rejected_by_admin_login():
    """Verify attempting to log in with the old backdoor password fails with 401."""
    script = """
    const env = { ADMIN_PASSWORD: 'correct_admin_pass_9988', ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const res = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: 'admin_chess_pro_2026' })
    }), env);
    const body = await res.json();
    console.log(JSON.stringify({
        status: res.status,
        body: body
    }));
    """
    res = run_node_worker_eval(script)
    assert res["status"] == 401
    assert res["body"].get("success") is False


def test_valid_admin_password_accepted():
    """Verify configured ADMIN_PASSWORD succeeds and issues valid session token."""
    script = """
    const env = { ADMIN_PASSWORD: 'correct_admin_pass_9988', ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const res = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: 'correct_admin_pass_9988' })
    }), env);
    const body = await res.json();
    console.log(JSON.stringify({
        status: res.status,
        success: body.success,
        hasToken: !!body.token
    }));
    """
    res = run_node_worker_eval(script)
    assert res["status"] == 200
    assert res["success"] is True
    assert res["hasToken"] is True


def test_unconfigured_admin_password_fails_closed_http_500():
    """Verify that if ADMIN_PASSWORD is empty or unset, all admin endpoints fail closed with HTTP 500."""
    script = """
    const envNoPw = { ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const rLogin = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: 'any_password' })
    }), envNoPw);
    const rPortal = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug'), envNoPw);
    const rKeys = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/keys'), envNoPw);
    console.log(JSON.stringify({
        statusLogin: rLogin.status,
        statusPortal: rPortal.status,
        statusKeys: rKeys.status
    }));
    """
    res = run_node_worker_eval(script)
    assert res["statusLogin"] == 500
    assert res["statusPortal"] == 500
    assert res["statusKeys"] == 500


def test_admin_cors_never_returns_wildcard():
    """Verify CORS on admin endpoints does not grant wildcard * or unauthorized origins."""
    script = """
    const env = {
        ADMIN_PASSWORD: 'pw',
        ADMIN_PATH: 'admin-secret-slug',
        SECRET_KEY: 'secret',
        FRONTEND_URL: 'https://authorized-frontend.com'
    };

    // Attacker GET request
    const rAttacker = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/keys', {
        headers: { 'Origin': 'https://evil-attacker.io' }
    }), env);

    // Attacker OPTIONS preflight
    const rPreflightAttacker = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/keys', {
        method: 'OPTIONS',
        headers: { 'Origin': 'https://evil-attacker.io' }
    }), env);

    // Authorized frontend request
    const rAuth = await worker.fetch(new Request('https://edge.worker.dev/admin-secret-slug/api/keys', {
        headers: { 'Origin': 'https://authorized-frontend.com' }
    }), env);

    console.log(JSON.stringify({
        attackerAcao: rAttacker.headers.get('access-control-allow-origin'),
        attackerPreflightAcao: rPreflightAttacker.headers.get('access-control-allow-origin'),
        authAcao: rAuth.headers.get('access-control-allow-origin')
    }));
    """
    res = run_node_worker_eval(script)
    assert res["attackerAcao"] != "*"
    assert res["attackerAcao"] is None or res["attackerAcao"] != "https://evil-attacker.io"
    assert res["attackerPreflightAcao"] != "*"
    assert res["attackerPreflightAcao"] is None or res["attackerPreflightAcao"] != "https://evil-attacker.io"
    assert res["authAcao"] == "https://authorized-frontend.com"


def test_production_security_headers_present():
    """Verify standard security headers (X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy)."""
    script = """
    const env = { ADMIN_PASSWORD: 'pw', ADMIN_PATH: 'admin-secret-slug', SECRET_KEY: 'secret' };
    const res = await worker.fetch(new Request('https://edge.worker.dev/api/health'), env);
    console.log(JSON.stringify({
        xcto: res.headers.get('x-content-type-options'),
        xfo: res.headers.get('x-frame-options'),
        csp: res.headers.get('content-security-policy'),
        rp: res.headers.get('referrer-policy')
    }));
    """
    res = run_node_worker_eval(script)
    assert res["xcto"] == "nosniff"
    assert res["xfo"] == "DENY"
    assert "default-src" in (res["csp"] or "")
    assert res["rp"] == "strict-origin-when-cross-origin"


# ==============================================================================
# Task 3: Wrangler Configuration Sanitization
# ==============================================================================

def test_wrangler_toml_secrets_sanitized():
    """Verify wrangler.toml does not contain plaintext SECRET_KEY or ADMIN_PASSWORD."""
    assert os.path.exists(WRANGLER_FILE)
    with open(WRANGLER_FILE, "r", encoding="utf-8") as f:
        wrangler_content = f.read()

    assert "CHESS_STEALTH_PRO_WEB24H_SECRET_2026" not in wrangler_content
    # Check that SECRET_KEY is not assigned a string literal value under [vars]
    assert not re.search(r'^\s*SECRET_KEY\s*=', wrangler_content, re.MULTILINE)
    assert "wrangler secret put" in wrangler_content


# ==============================================================================
# Task 4: Supabase Row Level Security (RLS) & Migrations
# ==============================================================================

def test_supabase_init_migration_purged_default_lifetime_keys():
    """Verify 20261106000000_init_license_schema.sql does not seed LIFE-VIP-9999 or PRO30D-TEST-MONTH."""
    assert os.path.exists(MIGRATION_V0)
    with open(MIGRATION_V0, "r", encoding="utf-8") as f:
        content = f.read()

    assert "LIFE-VIP-9999" not in content, "Found active commercial lifetime seed key in init migration"
    assert "PRO30D-TEST-MONTH" not in content, "Found active commercial monthly seed key in init migration"


def test_supabase_rls_hardening_migration_valid():
    """Verify 20261106000001_harden_rls_security.sql enables RLS on all tables and restricts anon role."""
    assert os.path.exists(MIGRATION_V1), f"Missing RLS migration file: {MIGRATION_V1}"
    with open(MIGRATION_V1, "r", encoding="utf-8") as f:
        sql = f.read().upper()

    tables = ["LICENSES", "ACTIVATION_LOGS", "PAYMENTS", "FREE_KEY_CLAIMS"]
    for t in tables:
        assert f"ALTER TABLE PUBLIC.{t} ENABLE ROW LEVEL SECURITY;" in sql, f"RLS not enabled for table {t}"
        assert f"REVOKE ALL ON TABLE PUBLIC.{t} FROM ANON" in sql, f"Anon permissions not revoked for table {t}"
        assert f"GRANT ALL ON TABLE PUBLIC.{t} TO SERVICE_ROLE;" in sql, f"Service role grant missing for table {t}"
        assert f'CREATE POLICY "SERVICE_ROLE_{t}_ALL"' in sql, f"Policy missing for table {t}"

    # Verify purge of commercial test keys
    assert "DELETE FROM PUBLIC.LICENSES WHERE KEY IN ('LIFE-VIP-9999', 'PRO30D-TEST-MONTH');" in sql
