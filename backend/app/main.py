from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, health, history, schema, sessions
from app.core.logger_setup import configure_logging, log_event
from app.core.settings import settings
from app.db.pool import close_pool, get_pool, init_pool

configure_logging()

app = FastAPI(
    title="AI SQL Assistant",
    version="0.1.0",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
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


@app.on_event("startup")
async def on_startup() -> None:
    await init_pool()
    schema_sql = Path(__file__).parent / "db" / "schema.sql"
    async with get_pool().acquire() as conn:
        await conn.execute(schema_sql.read_text())
    log_event("app.startup.complete")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_pool()
    log_event("app.shutdown.complete")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
