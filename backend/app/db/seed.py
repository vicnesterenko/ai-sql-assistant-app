"""Генерація та завантаження тестових даних у PostgreSQL."""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
from faker import Faker

from app.core.logger_setup import logger
from app.core.settings import settings
from app.db.utils import (
    CATEGORIES,
    CHANNELS,
    LOAN_STATUSES,
    MERCHANTS,
    TX_STATUSES,
)
from app.resources.sql_query import (
    COUNT_USERS_SQL,
    INSERT_LOAN_APPLICATIONS_SQL,
    INSERT_TRANSACTIONS_SQL,
    INSERT_USERS_SQL,
)


fake = Faker()

USERS_COUNT = 5_000
TEST_USERS_COUNT = 75
LOANS_COUNT = 7_000
TRANSACTIONS_COUNT = 10_000

START_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)
END_DATE_EXCLUSIVE = datetime(2026, 1, 1, tzinfo=timezone.utc)

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def random_dt(
    start: datetime,
    end_exclusive: datetime,
) -> datetime:
    """Повертає випадкову дату до виключної верхньої межі."""

    total_seconds = int(
        (end_exclusive - start).total_seconds()
    )

    if total_seconds <= 0:
        raise ValueError(
            "The end date must be later than the start date."
        )

    seconds = random.randrange(total_seconds)

    return start + timedelta(seconds=seconds)


def build_users(
    start: datetime,
    end_exclusive: datetime,
) -> list[tuple[Any, ...]]:
    """Генерує користувачів, зокрема тестові акаунти."""

    users: list[tuple[Any, ...]] = []

    for index in range(USERS_COUNT):
        is_test = index < TEST_USERS_COUNT

        email = (
            f"test{index}@example.com"
            if is_test
            else fake.unique.email()
        )

        users.append(
            (
                email,
                fake.name(),
                random.choice(CHANNELS),
                random_dt(start, end_exclusive),
                is_test,
                False,
            )
        )

    return users


def build_loans(
    user_ids: list[Any],
    start: datetime,
    end_exclusive: datetime,
) -> list[tuple[Any, ...]]:
    """Генерує кредитні заявки з датами в межах 2023–2025 років."""

    loans: list[tuple[Any, ...]] = []

    for _ in range(LOANS_COUNT):
        user_id = random.choice(user_ids)

        status = random.choices(
            LOAN_STATUSES,
            weights=[15, 45, 35, 5],
        )[0]

        # Для заявок із рішенням залишаємо щонайменше дві години
        # до верхньої межі, щоб decided_at не потрапив у 2026 рік.
        submitted_end = (
            end_exclusive - timedelta(hours=2)
            if status in {"approved", "rejected"}
            else end_exclusive
        )

        submitted = random_dt(start, submitted_end)

        requested = Decimal(
            random.randint(1_000, 200_000)
        )

        decided = None
        approved_amount = None
        rejection_reason = None

        if status in {"approved", "rejected"}:
            remaining_hours = int(
                (end_exclusive - submitted).total_seconds() // 3600
            )

            max_delay_hours = min(
                24 * 21,
                remaining_hours,
            )

            decision_delay_hours = random.randint(
                2,
                max_delay_hours,
            )

            decided = submitted + timedelta(
                hours=decision_delay_hours
            )

        if status == "approved":
            approval_percentage = (
                Decimal(random.randint(60, 100))
                / Decimal("100")
            )

            approved_amount = (
                requested * approval_percentage
            ).quantize(Decimal("0.01"))

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
    user_ids: list[Any],
    start: datetime,
    end_exclusive: datetime,
) -> list[tuple[Any, ...]]:
    """Генерує транзакції з датами в межах 2023–2025 років."""

    transactions: list[tuple[Any, ...]] = []

    for _ in range(TRANSACTIONS_COUNT):
        transactions.append(
            (
                random.choice(user_ids),
                random.choice(MERCHANTS),
                random.choice(CATEGORIES),
                Decimal(random.randint(20, 50_000)),
                "UAH",
                random.choices(
                    TX_STATUSES,
                    weights=[82, 8, 5, 5],
                )[0],
                random_dt(start, end_exclusive),
            )
        )

    return transactions


def read_schema_sql() -> str:
    """Перевіряє наявність schema.sql і повертає його вміст."""

    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(
            f"Database schema file was not found: {SCHEMA_FILE}"
        )

    if not SCHEMA_FILE.is_file():
        raise RuntimeError(
            f"Expected an SQL file, but the path is not a file: "
            f"{SCHEMA_FILE}"
        )

    schema_sql = SCHEMA_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not schema_sql:
        raise RuntimeError(
            f"Database schema file is empty: {SCHEMA_FILE}"
        )

    return schema_sql


async def main() -> None:
    """Створює схему та одноразово заповнює базу тестовими даними."""

    conn = await asyncpg.connect(settings.database_url)

    try:
        schema_sql = read_schema_sql()
        await conn.execute(schema_sql)

        existing_users = await conn.fetchval(
            COUNT_USERS_SQL
        )

        if existing_users and existing_users > 0:
            logger.info(
                "Database already seeded with %s users. Skipping.",
                existing_users,
            )
            return

        users = build_users(
            START_DATE,
            END_DATE_EXCLUSIVE,
        )

        async with conn.transaction():
            user_rows = await conn.fetch(
                INSERT_USERS_SQL,
                [user[0] for user in users],
                [user[1] for user in users],
                [user[2] for user in users],
                [user[3] for user in users],
                [user[4] for user in users],
                [user[5] for user in users],
            )

            user_ids = [
                row["id"]
                for row in user_rows
            ]

            loans = build_loans(
                user_ids,
                START_DATE,
                END_DATE_EXCLUSIVE,
            )

            await conn.executemany(
                INSERT_LOAN_APPLICATIONS_SQL,
                loans,
            )

            transactions = build_transactions(
                user_ids,
                START_DATE,
                END_DATE_EXCLUSIVE,
            )

            await conn.executemany(
                INSERT_TRANSACTIONS_SQL,
                transactions,
            )

        logger.info(
            "Database seeded successfully: "
            "%s users, %s loan applications, "
            "%s transactions, including %s test users.",
            USERS_COUNT,
            LOANS_COUNT,
            TRANSACTIONS_COUNT,
            TEST_USERS_COUNT,
        )

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
