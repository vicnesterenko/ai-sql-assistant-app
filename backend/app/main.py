"""
https://fastapi.tiangolo.com/advanced/events/#async-context-manager
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, health, history, schema, sessions
from app.core.logger_setup import configure_logging, log_event
from app.core.settings import settings
from app.db.pool import close_pool, init_pool
from app.db.init_db import init_schema

configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await init_schema()
    log_event("app.startup.complete")

    try:
        yield
    finally:
        await close_pool()
        log_event("app.shutdown.complete")

app = FastAPI(
    title="AI SQL Assistant",
    version="0.1.0",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, # type: ignore[arg-type]
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router=health.router, tags=["health"])
app.include_router(router=sessions.router, tags=["sessions"])
app.include_router(router=approvals.router, tags=["approvals"])
app.include_router(router=history.router, tags=["history"])
app.include_router(router=schema.router, tags=["schema"])

