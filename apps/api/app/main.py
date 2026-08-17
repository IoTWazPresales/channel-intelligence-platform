from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session import AsyncSessionLocal

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.cip_dev_celery_dispatch == "in_process_thread":
        DEV_CELERY_LOGGER.warning(
            "STARTUP: CIP_DEV_CELERY_DISPATCH=in_process_thread is ACTIVE — DEV ONLY. "
            "Product Master commits run in API daemon threads (no Celery worker/Redis for that path). "
            "Do not use in production. For broker-backed commits unset this and run a worker."
        )
    from app.services.report_schedule_runner import spawn_report_schedule_poller

    spawn_report_schedule_poller()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def add_no_store_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health():
    """Liveness — process is up (no dependency checks)."""
    return {"status": "ok", "service": "cip-api"}


@app.get("/health/ready")
async def health_ready():
    """Readiness — Postgres reachable."""
    db_name = None
    try:
        async with AsyncSessionLocal() as session:
            db_name = await session.scalar(text("SELECT current_database()"))
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — surface as not-ready
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": db_name,
                "error": type(exc).__name__,
            },
        )
    return {
        "status": "ready",
        "database": db_name,
        "ok": True,
    }
