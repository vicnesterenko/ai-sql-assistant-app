import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
from faker import Faker

from app.core.settings import settings
from app.core.logger_setup import logger
from app.resources.sql_query import (
    COUNT_USERS_SQL,
    INSERT_LOAN_APPLICATIONS_SQL,
    INSERT_TRANSACTIONS_SQL,
    INSERT_USERS_SQL,
)
from app.db.utils import CHANNELS, LOAN_STATUSES, TX_STATUSES, CATEGORIES, MERCHANTS

fake = Faker()


def random_dt(start: datetime, end: datetime) -> datetime:
    delta = end - start
    seconds = random.randint(0, int(delta.total_seconds()))

    return start + timedelta(seconds=seconds)


def build_users(start: datetime, end: datetime) -> list[tuple]:
    users = []

    for index in range(5000):
        is_test = index < 75
        email = f"test{index}@example.com" if is_test else fake.unique.email()

        users.append(
            (
                email,
                fake.name(),
                random.choice(CHANNELS),
                random_dt(start, end),
                is_test,
                False,
            )
        )

    return users


def build_loans(
    user_ids: list,
    start: datetime,
    end: datetime,
) -> list[tuple]:
    loans = []

    for _ in range(7000):
        user_id = random.choice(user_ids)
        submitted = random_dt(start, end)
        status = random.choices(
            LOAN_STATUSES,
            weights=[15, 45, 35, 5],
        )[0]

        decided = None
        approved_amount = None
        rejection_reason = None
        requested = Decimal(random.randint(1000, 200000))

        if status in {"approved", "rejected"}:
            decided = submitted + timedelta(hours=random.randint(2, 24 * 21))

        if status == "approved":
            approved_amount = (requested * Decimal(random.uniform(0.6, 1.0))).quantize(Decimal("0.01"))

        if status == "rejected":
            rejection_reason = random.choice(
                [
                    "low_score",
                    "insufficient_income",
                    "fraud_risk",
                    "missing_documents",
                ]
            )

        loans.append(
            (
                user_id,
                requested,
                approved_amount,
                status,
                submitted,
                decided,
                rejection_reason,
            )
        )

    return loans


def build_transactions(
    user_ids: list,
    start: datetime,
    end: datetime,
) -> list[tuple]:
    transactions = []

    for _ in range(10000):
        transactions.append(
            (
                random.choice(user_ids),
                random.choice(MERCHANTS),
                random.choice(CATEGORIES),
                Decimal(random.randint(20, 50000)) / Decimal("1.00"),
                "UAH",
                random.choices(TX_STATUSES, weights=[82, 8, 5, 5])[0],
                random_dt(start, end),
            )
        )

    return transactions


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url)

    schema_sql = Path(__file__).with_name("schema.sql").read_text()
    await conn.execute(schema_sql)

    existing = await conn.fetchval(COUNT_USERS_SQL)

    if existing and existing > 0:
        logger.info(f"Database already seeded with {existing} users. Skipping.")
        await conn.close()
        return

    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 12, 31, tzinfo=timezone.utc)

    users = build_users(start, end)

    user_rows = await conn.fetch(
        INSERT_USERS_SQL,
        [user[0] for user in users],
        [user[1] for user in users],
        [user[2] for user in users],
        [user[3] for user in users],
        [user[4] for user in users],
        [user[5] for user in users],
    )

    user_ids = [row["id"] for row in user_rows]

    loans = build_loans(user_ids, start, end)
    await conn.executemany(INSERT_LOAN_APPLICATIONS_SQL, loans)

    transactions = build_transactions(user_ids, start, end)
    await conn.executemany(INSERT_TRANSACTIONS_SQL, transactions)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
