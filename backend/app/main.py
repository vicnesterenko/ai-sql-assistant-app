from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, health, history, schema, sessions
from app.core.logging import configure_logging, log_event
from app.core.settings import settings
from app.db.pool import close_pool, get_pool, init_pool

configure_logging()

app = FastAPI(title='AI SQL Assistant', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(approvals.router)
app.include_router(history.router)
app.include_router(schema.router)


@app.on_event('startup')
async def on_startup() -> None:
    await init_pool()
    schema_sql = Path(__file__).parent / 'db' / 'schema.sql'
    async with get_pool().acquire() as conn:
        await conn.execute(schema_sql.read_text())
    log_event('app.startup.complete')


@app.on_event('shutdown')
async def on_shutdown() -> None:
    await close_pool()
    log_event('app.shutdown.complete')
