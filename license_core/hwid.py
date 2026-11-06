import hashlib
import os
import subprocess
import winreg


def _wmi_query(wmic_class: str, prop: str) -> str:
    try:
        cmd = f'powershell -NoProfile -Command "(Get-CimInstance {wmic_class} | Select-Object -First 1).{prop}"'
        out = (
            subprocess.check_output(
                cmd,
                shell=True,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000,
                timeout=3,
            )
            .decode("utf-8", errors="ignore")
            .strip()
        )
        return out or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _get_machine_guid() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(val).strip()
    except Exception:
        return os.getenv("COMPUTERNAME", "DEFAULT_GUID")


_CACHED_HWID = None


def get_hwid() -> str:
    """
    Tạo HWID Fingerprint kết hợp từ 4 thông số phần cứng độc lập:
    1. CPU ProcessorId (Win32_Processor)
    2. Motherboard SerialNumber (Win32_BaseBoard)
    3. Disk Drive SerialNumber (Win32_DiskDrive)
    4. Windows Registry MachineGuid (HKLM\\SOFTWARE\\Microsoft\\Cryptography)
    """
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    cpu_id = _wmi_query("Win32_Processor", "ProcessorId")
    board_serial = _wmi_query("Win32_BaseBoard", "SerialNumber")
    disk_serial = _wmi_query("Win32_DiskDrive", "SerialNumber")
    machine_guid = _get_machine_guid()

    raw_composite = f"CPU:{cpu_id}|MB:{board_serial}|DISK:{disk_serial}|GUID:{machine_guid}|SALT:CSP_2026"
    digest = hashlib.sha256(raw_composite.encode("utf-8")).hexdigest().upper()
    _CACHED_HWID = f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"
    return _CACHED_HWID
