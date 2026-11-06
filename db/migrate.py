import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import create_license_record, get_connection, get_db_path, init_db


def run_migrations(seed_defaults: bool = True) -> None:
    init_db()
    if not seed_defaults:
        return

    with get_connection() as conn:
        # Tạo sẵn 3 loại Key mẫu trong Database để test ngay
        sample_keys = [
            ("FREE-TEST-1DAY", "trial_24h"),
            ("PRO30D-TEST-MONTH", "monthly"),
            ("LIFE-VIP-9999", "lifetime"),
        ]
        for key_code, ltype in sample_keys:
            existing = conn.execute(
                "SELECT id FROM licenses WHERE key = ?", (key_code,)
            ).fetchone()
            if not existing:
                create_license_record(conn, ltype, custom_key=key_code)

    print(f"[+] Migration hoàn tất tại: {get_db_path()}")


if __name__ == "__main__":
    run_migrations(seed_defaults=True)
