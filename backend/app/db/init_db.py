"""Ініціалізація структури PostgreSQL із SQL-файлу."""

from pathlib import Path

from app.db.pool import get_pool


SCHEMA_FILE = Path(__file__).with_name("schema.sql")


async def init_schema() -> None:
    """Перевіряє наявність schema.sql і виконує його в PostgreSQL."""

    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(
            f"File scheme DB not found: {SCHEMA_FILE}"
        )

    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8").strip()

    # get_pool() повертає створений asyncpg.Pool,
    # acquire() бере з нього одне підключення.
    async with get_pool().acquire() as conn:
        await conn.execute(schema_sql)
