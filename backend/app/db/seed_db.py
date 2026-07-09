from app.core.logger_setup import log_event
from app.db.pool import get_pool
from app.resources.sql_query import COUNT_USERS_SQL
from app.db.seed import main as run_seed_main


async def seed_database_if_empty() -> None:
    """Seed demo data only when the database is empty.

    This is used for hosted environments like Render, where the free plan may
    not provide an interactive shell to run `python run_seed.py` manually.
    The function is safe to call on every startup because it checks whether
    demo users already exist before inserting data.
    """
    pool = get_pool()

    async with pool.acquire() as conn:
        users_count = await conn.fetchval(COUNT_USERS_SQL)

    if users_count and users_count > 0:
        log_event(
            "db.seed.skipped",
            reason="database already contains users",
            users_count=users_count,
        )
        return

    await run_seed_main()

    log_event("db.seed.completed")