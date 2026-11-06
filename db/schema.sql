-- ============================================================================
-- CHESS STEALTH PRO — DATABASE SCHEMA (SQLite / PostgreSQL Compatible)
-- ============================================================================

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('trial_24h', 'monthly', 'lifetime')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    hwid TEXT DEFAULT NULL,
    hwid_reset_count INTEGER NOT NULL DEFAULT 0,
    hwid_last_reset_at INTEGER DEFAULT NULL,
    created_at INTEGER NOT NULL,
    activated_at INTEGER DEFAULT NULL,
    expires_at INTEGER DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key);
CREATE INDEX IF NOT EXISTS idx_licenses_hwid ON licenses(hwid);

CREATE TABLE IF NOT EXISTS activation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id INTEGER NOT NULL,
    hwid TEXT NOT NULL,
    ip TEXT NOT NULL,
    app_version TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'verify',
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activation_logs_license_id ON activation_logs(license_id);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    method TEXT NOT NULL,
    webhook_ref TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'refunded')),
    created_at INTEGER NOT NULL,
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS free_key_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    hwid TEXT DEFAULT NULL,
    license_id INTEGER DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'claimed', 'expired')),
    claimed_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_free_key_claims_ip ON free_key_claims(ip, claimed_at);
CREATE INDEX IF NOT EXISTS idx_free_key_claims_token ON free_key_claims(token);
