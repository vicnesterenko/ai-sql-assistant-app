from pathlib import Path

from app.db.pool import get_pool


async def init_schema() -> None:
    schema_sql = Path(__file__).with_name("schema.sql").read_text()

    async with get_pool().acquire() as conn:
        await conn.execute(schema_sql)