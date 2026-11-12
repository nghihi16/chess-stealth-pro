# license_core/watchdog.py
"""
Windows Native Anti-Debug & Anti-Hooking Watchdog Engine.
Detects debuggers, remote debuggers, ntdll debug ports/objects, blacklisted reverse-engineering
processes, and prologue/preamble tampering (hooks/breakpoints) on critical Win32 APIs.
Actively poisons coordinate scaling and invalidates session state upon detection.
"""
import ctypes
from ctypes import wintypes
import sys
import threading
import time

_WATCHDOG_THREAD: threading.Thread | None = None
_WATCHDOG_RUNNING: bool = False
_WATCHDOG_HEARTBEAT: int = 0
_COMPROMISED: bool = False
_COMPROMISE_REASON: str = ""

HOOK_OPCODES = (b"\xe9", b"\xeb", b"\xcc", b"\xff\x25")

PROCESS_BLACKLIST = {
    "x64dbg.exe",
    "x32dbg.exe",
    "ida.exe",
    "ida64.exe",
    "cheatengine-x86_64.exe",
    "cheatengine-i386.exe",
    "cheatengine-x86_64-sse4-avx2.exe",
    "httpdebuggerui.exe",
    "fiddler.exe",
    "processhacker.exe",
    "wireshark.exe",
    "procmon.exe",
    "procmon64.exe",
    "procexp.exe",
    "procexp64.exe",
    "ollydbg.exe",
    "scylla_x64.exe",
    "scylla_x86.exe",
}

if sys.platform == "win32":
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]
else:
    class PROCESSENTRY32W:  # type: ignore[no-redef]
        pass


def check_debugger_present() -> bool:
    """Checks PEB BeingDebugged flag via kernel32.IsDebuggerPresent()."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.kernel32.IsDebuggerPresent())
    except Exception:
        return False


def check_remote_debugger_present() -> bool:
    """Checks remote debugger attachment via kernel32.CheckRemoteDebuggerPresent()."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.CheckRemoteDebuggerPresent.restype = wintypes.BOOL
        kernel32.CheckRemoteDebuggerPresent.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]

        is_debugged = wintypes.BOOL(False)
        h_proc = kernel32.GetCurrentProcess()
        success = kernel32.CheckRemoteDebuggerPresent(h_proc, ctypes.byref(is_debugged))
        return bool(success and is_debugged.value)
    except Exception:
        return False


def check_ntdll_debug_port() -> bool:
    """Queries ntdll.NtQueryInformationProcess for ProcessDebugPort (0x07)."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        ntdll = getattr(ctypes.windll, "ntdll", None)
        if not ntdll or not hasattr(ntdll, "NtQueryInformationProcess"):
            return False

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        ntdll.NtQueryInformationProcess.restype = ctypes.c_long
        ntdll.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]

        h_proc = kernel32.GetCurrentProcess()
        debug_port = ctypes.c_size_t(0)
        ret_len = ctypes.c_ulong(0)

        status = ntdll.NtQueryInformationProcess(
            h_proc,
            7,  # ProcessDebugPort
            ctypes.byref(debug_port),
            ctypes.sizeof(debug_port),
            ctypes.byref(ret_len),
        )
        # NTSTATUS STATUS_SUCCESS is 0; non-zero port value indicates active debugger
        if status == 0 and debug_port.value != 0:
            return True
    except Exception:
        pass
    return False


def check_ntdll_debug_object_handle() -> bool:
    """Queries ntdll.NtQueryInformationProcess for ProcessDebugObjectHandle (0x1E)."""
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        ntdll = getattr(ctypes.windll, "ntdll", None)
        if not ntdll or not hasattr(ntdll, "NtQueryInformationProcess"):
            return False

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        ntdll.NtQueryInformationProcess.restype = ctypes.c_long
        ntdll.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]

        h_proc = kernel32.GetCurrentProcess()
        debug_obj = wintypes.HANDLE(0)
        ret_len = ctypes.c_ulong(0)

        status = ntdll.NtQueryInformationProcess(
            h_proc,
            0x1E,  # ProcessDebugObjectHandle
            ctypes.byref(debug_obj),
            ctypes.sizeof(debug_obj),
            ctypes.byref(ret_len),
        )
        # STATUS_SUCCESS (0) with a valid handle indicates attached debug object
        if status == 0 and debug_obj.value not in (0, None):
            return True
    except Exception:
        pass
    return False


def check_process_blacklist(custom_blacklist: set[str] | None = None) -> tuple[bool, str]:
    """Scans running system processes against reverse engineering tool blacklist."""
    if sys.platform != "win32":
        return False, ""
    blacklist = custom_blacklist if custom_blacklist is not None else PROCESS_BLACKLIST
    try:
        kernel32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x00000002
        h_snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
        if h_snapshot == INVALID_HANDLE_VALUE or not h_snapshot:
            return False, ""

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)

        found = False
        detected_name = ""

        if kernel32.Process32FirstW(h_snapshot, ctypes.byref(entry)):
            while True:
                exe_name = entry.szExeFile.lower()
                if exe_name in blacklist:
                    found = True
                    detected_name = entry.szExeFile
                    break
                if not kernel32.Process32NextW(h_snapshot, ctypes.byref(entry)):
                    break
        kernel32.CloseHandle(h_snapshot)
        if found:
            return True, detected_name
    except Exception:
        pass
    return False, ""


def detect_hook_in_prologue(prologue: bytes) -> tuple[bool, str]:
    """Detects inline JMP hooks, trampolines, and INT3 software breakpoints."""
    if not prologue:
        return False, "clean"
    if prologue.startswith(b"\xe9"):
        return True, "JMP rel32 hook"
    if prologue.startswith(b"\xeb"):
        return True, "JMP rel8 hook"
    if prologue.startswith(b"\xcc"):
        return True, "INT3 breakpoint"
    if prologue.startswith(b"\xff\x25"):
        return True, "Indirect JMP hook"
    if prologue.startswith(b"\x48\xb8") and (b"\xff\xe0" in prologue[:14] or b"\x50\xc3" in prologue[:14]):
        return True, "64-bit register trampoline hook"
    return False, "clean"


def check_api_prologues() -> tuple[bool, str]:
    """Checks function entry points of critical Win32 APIs in kernel32 and kernelbase."""
    if sys.platform != "win32":
        return False, "clean"
    try:
        targets = []
        kernel32 = getattr(ctypes.windll, "kernel32", None)
        if kernel32:
            targets.append(("kernel32", kernel32, ("IsDebuggerPresent", "CheckRemoteDebuggerPresent")))
        kernelbase = getattr(ctypes.windll, "kernelbase", None)
        if kernelbase:
            targets.append(("kernelbase", kernelbase, ("IsDebuggerPresent", "CheckRemoteDebuggerPresent")))

        for mod_name, mod_obj, func_names in targets:
            for func_name in func_names:
                func_ptr = getattr(mod_obj, func_name, None)
                if not func_ptr:
                    continue
                addr = ctypes.cast(func_ptr, ctypes.c_void_p).value
                if not addr:
                    continue
                buf = (ctypes.c_char * 16)()
                ctypes.memmove(buf, addr, 16)
                hooked, hook_type = detect_hook_in_prologue(bytes(buf))
                if hooked:
                    return True, f"{mod_name}!{func_name} hooked with {hook_type}"
    except Exception:
        pass
    return False, "clean"


def trigger_compromise(reason: str) -> None:
    """Sets compromised state and invalidates session credentials in license_core."""
    global _COMPROMISED, _COMPROMISE_REASON
    _COMPROMISED = True
    _COMPROMISE_REASON = reason
    try:
        from license_core import verifier
        verifier._ACTIVE_SESSION_PAYLOAD = None
        verifier._ACTIVE_SESSION_SIGNATURE = ""
    except Exception:
        pass


def watchdog_check_step(
    simulated_debugger: bool = False,
    simulated_hook: bytes | None = None,
    simulated_blacklist: str | None = None,
) -> bool:
    """Executes a single pass of all anti-debug, anti-hook, and blacklist checks."""
    global _WATCHDOG_HEARTBEAT
    _WATCHDOG_HEARTBEAT += 1

    if (
        simulated_debugger
        or check_debugger_present()
        or check_remote_debugger_present()
        or check_ntdll_debug_port()
        or check_ntdll_debug_object_handle()
    ):
        trigger_compromise("Debugger Detected")
        return False

    if simulated_hook is not None:
        hooked, reason = detect_hook_in_prologue(simulated_hook)
        if hooked:
            trigger_compromise(f"API Hook Detected: {reason}")
            return False

    hooked, reason = check_api_prologues()
    if hooked:
        trigger_compromise(reason)
        return False

    if simulated_blacklist is not None:
        trigger_compromise(f"Blacklisted Process Detected: {simulated_blacklist}")
        return False

    bl_found, bl_name = check_process_blacklist()
    if bl_found:
        trigger_compromise(f"Blacklisted Process Detected: {bl_name}")
        return False

    return True


def get_watchdog_heartbeat() -> int:
    return _WATCHDOG_HEARTBEAT


def is_environment_compromised() -> bool:
    return _COMPROMISED


def get_tamper_poison_factor() -> float:
    """
    Returns 1.0 under healthy conditions, or 0.0 when environment is compromised,
    poisoning arrow coordinate scaling and rendering calculations.
    """
    if _COMPROMISED:
        return 0.0
    return 1.0


def reset_watchdog_for_testing() -> None:
    global _WATCHDOG_HEARTBEAT, _COMPROMISED, _COMPROMISE_REASON, _WATCHDOG_RUNNING, _WATCHDOG_THREAD
    _WATCHDOG_HEARTBEAT = 0
    _COMPROMISED = False
    _COMPROMISE_REASON = ""
    _WATCHDOG_RUNNING = False
    _WATCHDOG_THREAD = None


def start_watchdog(poll_interval: float = 1.0, interval: float | None = None) -> threading.Thread:
    global _WATCHDOG_RUNNING, _WATCHDOG_THREAD
    if interval is not None:
        poll_interval = interval
    _WATCHDOG_RUNNING = True

    def _run():
        while _WATCHDOG_RUNNING:
            watchdog_check_step()
            time.sleep(poll_interval)

    _WATCHDOG_THREAD = threading.Thread(target=_run, daemon=True, name="ChessPro-Watchdog")
    _WATCHDOG_THREAD.start()
    return _WATCHDOG_THREAD


def stop_watchdog() -> None:
    global _WATCHDOG_RUNNING
    _WATCHDOG_RUNNING = False
