"""
https://fastapi.tiangolo.com/advanced/events/#async-context-manager
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, health, history, schema, sessions
from app.core.logger_setup import configure_logging, log_event
from app.core.settings import settings
from app.db.init_db import init_schema
from app.db.pool import close_pool, init_pool
from app.db.seed_db import seed_database_if_empty

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    await init_schema()

    if settings.auto_seed_on_startup:
        await seed_database_if_empty()

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
    CORSMiddleware,  # type: ignore[arg-type]
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)