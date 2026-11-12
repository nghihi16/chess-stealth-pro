import os
import sys
import tempfile
import time
import hmac
import hashlib
import json
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.server import app
from db.migrate import run_migrations
import license_core.verifier as verifier_mod

os.environ.setdefault("CHESSPRO_WEBHOOK_SECRET", "SECURE_TEST_WEBHOOK_SECRET_2026")


@pytest.fixture
def clean_env():
    """Preserves os.environ before test execution and restores it on teardown."""
    original_env = os.environ.copy()
    yield os.environ
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def clean_security_state():
    """Ensures watchdog and clock guard state are completely clean before and after every test."""
    from license_core.watchdog import reset_watchdog_for_testing
    from license_core.verifier import reset_clock_guard_for_testing
    reset_watchdog_for_testing()
    reset_clock_guard_for_testing()
    yield
    reset_watchdog_for_testing()
    reset_clock_guard_for_testing()


@pytest.fixture
def isolated_db(clean_env):
    """Allocates an ephemeral SQLite database file and executes migrations."""
    fd, temp_db = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ["CHESSPRO_DB_PATH"] = temp_db
    os.environ.setdefault("CHESSPRO_WEBHOOK_SECRET", "SECURE_TEST_WEBHOOK_SECRET_2026")
    run_migrations(seed_defaults=True)
    yield temp_db
    try:
        os.remove(temp_db)
    except OSError:
        pass


@pytest.fixture
def test_client(isolated_db):
    """Yields a FastAPI TestClient bound to the isolated test database."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def qapp():
    """Provides a singleton QApplication instance for GUI and widget tests."""
    from PySide6.QtWidgets import QApplication
    app_instance = QApplication.instance()
    if app_instance is None:
        app_instance = QApplication(["", "-platform", "offscreen"])
    return app_instance


@pytest.fixture
def sign_webhook():
    """Helper fixture to compute HMAC-SHA256 signature for webhook raw payload."""
    def _signer(raw_body: bytes, secret: str | None = None) -> str:
        sec = secret or os.environ.get("CHESSPRO_WEBHOOK_SECRET", "SECURE_TEST_WEBHOOK_SECRET_2026")
        return hmac.new(sec.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return _signer


@pytest.fixture
def clock_controller(monkeypatch):
    """Controllable monotonic and wall clock fixture for anti-rollback verification."""
    class ControllableClock:
        def __init__(self, initial_wall: float = 1770000000.0, initial_mono: float = 1000.0):
            self.wall = initial_wall
            self.mono = initial_mono

        def advance(self, seconds: float):
            self.wall += seconds
            self.mono += seconds

        def rollback_wall(self, seconds: float):
            self.wall -= seconds

        def now_wall(self) -> float:
            return self.wall

        def now_mono(self) -> float:
            return self.mono

    clock = ControllableClock()
    monkeypatch.setattr(time, "time", clock.now_wall)
    monkeypatch.setattr(time, "monotonic", clock.now_mono)
    return clock


@pytest.fixture(autouse=True)
def isolate_verifier_state():
    """Isolates verifier clock state, nonce store, and offline cache files per test."""
    temp_dir = tempfile.mkdtemp(prefix="chess_test_state_")
    clock_file = os.path.join(temp_dir, "clock_state.json")
    nonce_file = os.path.join(temp_dir, "used_nonces.json")
    cache_file = os.path.join(temp_dir, "verified_session.json")

    os.environ["CHESSPRO_CLOCK_GUARD_PATH"] = clock_file
    os.environ["CHESSPRO_NONCE_STORE_PATH"] = nonce_file
    os.environ["CHESSPRO_CACHE_PATH"] = cache_file
    orig_cache = verifier_mod.CACHE_FILE
    verifier_mod.CACHE_FILE = cache_file

    verifier_mod.reset_clock_guard_for_testing()
    verifier_mod.reset_nonce_store_for_testing()
    verifier_mod._ACTIVE_SESSION_PAYLOAD = None
    verifier_mod._ACTIVE_SESSION_SIGNATURE = ""

    yield temp_dir

    verifier_mod.CACHE_FILE = orig_cache
    verifier_mod._ACTIVE_SESSION_PAYLOAD = None
    verifier_mod._ACTIVE_SESSION_SIGNATURE = ""
    verifier_mod.reset_clock_guard_for_testing()
    verifier_mod.reset_nonce_store_for_testing()

    os.environ.pop("CHESSPRO_CACHE_PATH", None)
    os.environ.pop("CHESSPRO_CLOCK_GUARD_PATH", None)
    os.environ.pop("CHESSPRO_NONCE_STORE_PATH", None)

    for f in (clock_file, nonce_file, cache_file):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass


@pytest.fixture
def cf_worker_env():
    """Mock execution context for Cloudflare Worker environment and KV store."""
    class MockKV:
        def __init__(self):
            self.store = {}
        def get(self, key):
            return self.store.get(key)
        def put(self, key, value):
            self.store[key] = value
        def delete(self, key):
            self.store.pop(key, None)

    class MockWorkerContext:
        def __init__(self):
            self.env = {
                "ADMIN_PASSWORD": "ValidConfiguredAdminPass2026!",
                "SECRET_KEY": "TEST_HMAC_SECRET_2026",
                "ADMIN_SLUG": "admin-sec-slug-8877",
            }
            self.kv = MockKV()
    return MockWorkerContext()


WORKER_PATH = os.path.join(PROJECT_ROOT, "server_worker.js")


@pytest.fixture(scope="session")
def run_worker_request():
    """Executes a real HTTP request against the production server_worker.js using Node.js."""
    import subprocess

    def _execute(url: str, method: str = "GET", headers: dict = None, body: dict | str = None, env: dict = None):
        headers = headers or {}
        env = env if env is not None else {
            "ADMIN_PASSWORD": "ConfiguredTestPass2026!",
            "SECRET_KEY": "TEST_HMAC_SECRET_KEY_2026",
            "ADMIN_PATH": "admin-788a9acf0094e887",
            "FRONTEND_URL": "https://nghihi16.github.io/chess-stealth-pro",
        }
        worker_file_url = f"file:///{WORKER_PATH.replace(os.sep, '/')}"

        req_options = {
            "method": method,
            "headers": headers,
        }
        if body is not None:
            req_options["body"] = json.dumps(body) if isinstance(body, dict) else body

        node_script = f"""
        import('{worker_file_url}').then(async (mod) => {{
            try {{
                const env = {json.dumps(env)};
                const req = new Request('{url}', {json.dumps(req_options)});
                const res = await mod.default.fetch(req, env);
                const text = await res.text();
                let jsonBody = null;
                try {{ jsonBody = JSON.parse(text); }} catch (e) {{}}

                const resHeaders = {{}};
                for (const [k, v] of res.headers.entries()) {{
                    resHeaders[k.toLowerCase()] = v;
                }}

                console.log(JSON.stringify({{
                    status: res.status,
                    headers: resHeaders,
                    body: text,
                    json: jsonBody
                }}));
            }} catch (err) {{
                console.error(err);
                process.exit(1);
            }}
        }}).catch(err => {{
            console.error(err);
            process.exit(1);
        }});
        """
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", node_script],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(proc.stdout.strip())

    return _execute


@pytest.fixture(scope="module")
def overlay_ipc_server():
    """
    Spins up the actual StealthOverlayServer on an OS-assigned ephemeral port (0).
    Allows true end-to-end HTTP request testing without port collisions.
    """
    import threading
    from http.server import ThreadingHTTPServer
    import main

    test_token = "e2e_test_secret_token_abcdef123456"
    main.SESSION_TOKEN = test_token
    if hasattr(main.StealthOverlayServer, "SESSION_TOKEN"):
        main.StealthOverlayServer.SESSION_TOKEN = test_token

    server = ThreadingHTTPServer(("127.0.0.1", 0), main.StealthOverlayServer)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield {"base_url": base_url, "port": port, "token": test_token, "server": server}

    server.shutdown()
    server.server_close()


@pytest.fixture
def mock_win32_api(monkeypatch):
    """Provides controllable mocks for Windows debugging and hooking APIs."""
    class Win32State:
        def __init__(self):
            self.is_debugger_present = False
            self.is_remote_debugger_present = False
            self.api_prologues = {
                "IsDebuggerPresent": b"\x48\x83\xec\x28",  # normal prologue
                "CheckRemoteDebuggerPresent": b"\x48\x89\x5c\x24",
            }

        def set_debugger_present(self, val: bool):
            self.is_debugger_present = val

        def set_remote_debugger_present(self, val: bool):
            self.is_remote_debugger_present = val

        def set_jmp_hook(self, func_name: str):
            self.api_prologues[func_name] = b"\xe9\x12\x34\x56\x78"  # JMP hook

        def set_int3_hook(self, func_name: str):
            self.api_prologues[func_name] = b"\xcc\x90\x90\x90"  # INT3 breakpoint

    return Win32State()
