import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import create_license_record, get_connection, get_db_path, init_db


def run_migrations(seed_defaults: bool = True) -> None:
    init_db()
    if not seed_defaults:
        return

    with get_connection() as conn:
        sample_keys = [
            ("FREE-TEST-1DAY", "trial_24h"),
            ("PRO30D-TEST-MONTH", "monthly"),
            ("PEO30D-TEST-MONTH", "monthly"),
            ("LIFE-VIP-9999", "lifetime"),
        ]
        for key_code, ltype in sample_keys:
            existing = conn.execute(
                "SELECT id FROM licenses WHERE key = ?", (key_code,)
            ).fetchone()
            if not existing:
                create_license_record(conn, ltype, custom_key=key_code)


if __name__ == "__main__":
    run_migrations(seed_defaults=True)
    print(f"[+] Migration hoàn tất tại: {get_db_path()}")
