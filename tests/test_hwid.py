import hashlib
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import license_core.hwid as hwid_mod


def test_get_hwid_uses_single_batch_query_and_matches_composite(monkeypatch):
    hwid_mod._CACHED_HWID = None
    calls = []

    def fake_check_output(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return b"CPU_ID_1|MB_SER_2|DISK_SER_3\n"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(hwid_mod, "_get_machine_guid", lambda: "GUID_4")

    got = hwid_mod.get_hwid()
    raw = "CPU:CPU_ID_1|MB:MB_SER_2|DISK:DISK_SER_3|GUID:GUID_4|SALT:CSP_2026"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    expected = f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"

    assert got == expected
    assert len(calls) == 1
    assert calls[0][1].get("timeout", 0) >= 8
    hwid_mod._CACHED_HWID = None


def test_get_hwid_falls_back_to_individual_queries_with_safe_timeout(monkeypatch):
    hwid_mod._CACHED_HWID = None
    timeouts = []

    def fake_batch():
        raise subprocess.TimeoutExpired(cmd="ps", timeout=8)

    def fake_wmi(cls_name, prop, timeout=8):
        timeouts.append(timeout)
        return {"ProcessorId": "C1", "SerialNumber": "S1"}[prop]

    monkeypatch.setattr(hwid_mod, "_query_hardware_batch", fake_batch)
    monkeypatch.setattr(hwid_mod, "_wmi_query", fake_wmi)
    monkeypatch.setattr(hwid_mod, "_get_machine_guid", lambda: "G1")

    got = hwid_mod.get_hwid()
    raw = "CPU:C1|MB:S1|DISK:S1|GUID:G1|SALT:CSP_2026"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    expected = f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"

    assert got == expected
    assert timeouts and all(t >= 8 for t in timeouts)
    hwid_mod._CACHED_HWID = None
