import os
import sys
import urllib.parse
import winreg


def register_custom_url_scheme(scheme: str = "chesspro") -> bool:
    """
    Đăng ký giao thức URL tùy chỉnh `chesspro://activate?key=XXX` vào Registry của User hiện tại
    (HKCU\\Software\\Classes\\chesspro) — không cần quyền Run as Administrator.
    Khi người dùng vượt link xong trên web và bấm "Mở App & Tự Kích Hoạt", trình duyệt sẽ
    mở thẳng ChessPro.exe và điền sẵn Key.
    """
    try:
        if getattr(sys, "frozen", False):
            exe_cmd = f'"{sys.executable}" "%1"'
        else:
            main_script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
            )
            exe_cmd = f'"{sys.executable}" "{main_script}" "%1"'

        base_key_path = rf"Software\Classes\{scheme}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Chess Stealth Pro Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        cmd_key_path = rf"{base_key_path}\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, exe_cmd)

        return True
    except Exception:
        return False


def parse_url_scheme_arg(argv: list[str]) -> str | None:
    """Trích xuất mã Key nếu ứng dụng được gọi từ URL `chesspro://activate?key=XXXX`."""
    for arg in argv[1:]:
        if arg.lower().startswith("chesspro://"):
            parsed = urllib.parse.urlparse(arg)
            params = urllib.parse.parse_qs(parsed.query)
            if "key" in params and params["key"]:
                return params["key"][0].strip().upper()
    return None
