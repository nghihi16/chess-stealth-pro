from contextlib import asynccontextmanager
import threading
from fastapi import FastAPI
import uvicorn
from api.routes import router
from db.migrate import run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations(seed_defaults=True)
    yield


app = FastAPI(
    title="Chess Stealth Pro — License Server API",
    version="2.0.0",
    description="Hệ thống quản lý License Key (24h Trial / 30d Monthly / Lifetime) ký số Ed25519.",
    lifespan=lifespan,
)

app.include_router(router)


def start_background_api_server(host: str = "127.0.0.1", port: int = 8766) -> None:
    """Khởi chạy FastAPI License Server chạy ngầm phục vụ xác thực Ed25519 và tạo URL nhận Key."""
    run_migrations(seed_defaults=True)

    def _run():
        try:
            config = uvicorn.Config(app, host=host, port=port, log_level="error", log_config=None)
            server = uvicorn.Server(config)
            server.run()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8766)
