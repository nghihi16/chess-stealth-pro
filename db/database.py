import os
import secrets
import sqlite3
import sys
import time
from typing import Optional

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DB_PATH = os.path.join(BASE_DIR, "db", "licenses.sqlite3")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")

EMBEDDED_SCHEMA_SQL = """
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
"""


def get_db_path() -> str:
    return os.environ.get("CHESSPRO_DB_PATH", DEFAULT_DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
    with get_connection() as conn:
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        else:
            conn.executescript(EMBEDDED_SCHEMA_SQL)
        conn.commit()


def cleanup_expired_records(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    conn.execute(
        """
        UPDATE licenses
        SET status = 'expired'
        WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?
        """,
        (now,),
    )
    conn.execute(
        """
        DELETE FROM free_key_claims
        WHERE expires_at <= ?
        """,
        (now,),
    )
    conn.commit()


def generate_formatted_key(license_type: str) -> str:
    prefix_map = {
        "trial_24h": "FREE24H",
        "monthly": "PRO30D",
        "lifetime": "LIFEVIP",
    }
    prefix = prefix_map.get(license_type, "KEY")
    p1 = secrets.token_hex(2).upper()
    p2 = secrets.token_hex(2).upper()
    p3 = secrets.token_hex(2).upper()
    return f"{prefix}-{p1}-{p2}-{p3}"


def create_license_record(
    conn: sqlite3.Connection,
    license_type: str,
    custom_key: Optional[str] = None,
    hwid: Optional[str] = None,
    activate_immediately: bool = False,
) -> dict:
    now = int(time.time())
    key_str = custom_key or generate_formatted_key(license_type)

    activated_at = now if activate_immediately else None
    expires_at = None
    if activate_immediately:
        if license_type == "trial_24h":
            expires_at = now + 86400
        elif license_type == "monthly":
            expires_at = now + (30 * 86400)

    cursor = conn.execute(
        """
        INSERT INTO licenses (key, type, status, hwid, hwid_reset_count, created_at, activated_at, expires_at)
        VALUES (?, ?, 'active', ?, 0, ?, ?, ?)
        """,
        (key_str, license_type, hwid, now, activated_at, expires_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM licenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)
