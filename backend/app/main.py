from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.infrastructure.db.seed import ensure_demo_engineers, reindex_knowledge, seed_if_empty
from app.infrastructure.db.session import AsyncSessionLocal, init_db
from app.interfaces.api.routes import auth, automation, dashboard, metrics, stack, tickets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


async def _sla_breach_cron_loop(stop: asyncio.Event) -> None:
    """Background Cron: Find Expired SLA → Notify Manager → Escalate → Create RCA Task."""
    from app.infrastructure.automation.sla_breach_workflow import sla_breach_workflow

    interval = max(30, int(settings.sla_breach_cron_seconds or 0))
    while not stop.is_set():
        try:
            async with AsyncSessionLocal() as session:
                result = await sla_breach_workflow.run(session)
            if result.get("processed_count"):
                logger.info(
                    "SLA Breach cron: expired=%s processed=%s",
                    result.get("expired_count"),
                    result.get("processed_count"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SLA Breach cron failed: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_if_empty(session)
        await ensure_demo_engineers(session)
        await reindex_knowledge(session)
    stop = asyncio.Event()
    cron_task = None
    if settings.sla_breach_cron_seconds and settings.sla_breach_cron_seconds > 0:
        cron_task = asyncio.create_task(_sla_breach_cron_loop(stop))
        logger.info("SLA Breach cron enabled every %ss", settings.sla_breach_cron_seconds)
    logger.info("ServiceNow Agentic AIOps ready on port %s", settings.port)
    yield
    stop.set()
    if cron_task:
        cron_task.cancel()
        try:
            await cron_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = settings.api_prefix
app.include_router(auth.router, prefix=api)
app.include_router(tickets.router, prefix=api)
app.include_router(dashboard.router, prefix=api)
app.include_router(automation.router, prefix=api)
app.include_router(stack.router, prefix=api)
app.include_router(metrics.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "port": settings.port}


@app.get(f"{api}/health")
async def api_health() -> dict:
    """API-prefixed health check (used by probes that expect /api/v1/health)."""
    return {"status": "ok", "service": settings.app_name, "port": settings.port}


_STATIC_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "frontend" / "dist",  # repo root/frontend/dist
    Path(__file__).resolve().parents[1] / "frontend" / "dist",  # docker /app/frontend/dist
]
STATIC_DIR = next((p for p in _STATIC_CANDIDATES if p.exists()), _STATIC_CANDIDATES[0])

# Paths the SPA catch-all must never claim (unknown API routes should 404 as JSON).
_SPA_RESERVED_PREFIXES = ("api/", "metrics", "health", "docs", "redoc", "openapi.json")


if STATIC_DIR.exists():
    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        normalized = (full_path or "").lstrip("/")
        if normalized.startswith(_SPA_RESERVED_PREFIXES) or normalized in {
            "metrics",
            "health",
            "docs",
            "redoc",
            "openapi.json",
        }:
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
