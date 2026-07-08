import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
from faker import Faker

from app.core.settings import settings

fake = Faker()
CHANNELS = ['organic', 'paid_search', 'facebook_ads', 'referral', 'partner', 'email', 'affiliate']
LOAN_STATUSES = ['submitted', 'approved', 'rejected', 'cancelled']
TX_STATUSES = ['success', 'failed', 'pending', 'refunded']
CATEGORIES = ['grocery', 'electronics', 'travel', 'fuel', 'restaurant', 'utilities', 'health', 'education']
MERCHANTS = ['Silpo', 'Rozetka', 'WOG', 'OKKO', 'NovaPay', 'Bolt', 'Uklon', 'Epicentr', 'Megamarket', 'Comfy']


def random_dt(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


async def main() -> None:
    conn = await asyncpg.connect(settings.database_url)
    schema_sql = Path(__file__).with_name('schema.sql').read_text()
    await conn.execute(schema_sql)

    existing = await conn.fetchval('SELECT count(*) FROM users')
    if existing and existing > 0:
        print(f'Database already seeded with {existing} users. Skipping.')
        await conn.close()
        return

    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 12, 31, tzinfo=timezone.utc)

    users = []
    for i in range(5000):
        is_test = i < 75
        email = f'test{i}@example.com' if is_test else fake.unique.email()
        users.append((email, fake.name(), random.choice(CHANNELS), random_dt(start, end), is_test, False))

    user_rows = await conn.fetch(
        '''
        INSERT INTO users(email, full_name, acquisition_channel, created_at, is_test_account, is_deleted)
        SELECT * FROM UNNEST($1::text[], $2::text[], $3::text[], $4::timestamptz[], $5::boolean[], $6::boolean[])
        RETURNING id, created_at
        ''',
        [u[0] for u in users], [u[1] for u in users], [u[2] for u in users],
        [u[3] for u in users], [u[4] for u in users], [u[5] for u in users],
    )
    user_ids = [row['id'] for row in user_rows]

    loans = []
    for _ in range(7000):
        user_id = random.choice(user_ids)
        submitted = random_dt(start, end)
        status = random.choices(LOAN_STATUSES, weights=[15, 45, 35, 5])[0]
        decided = None
        approved_amount = None
        rejection_reason = None
        requested = Decimal(random.randint(1000, 200000))
        if status in {'approved', 'rejected'}:
            decided = submitted + timedelta(hours=random.randint(2, 24 * 21))
        if status == 'approved':
            approved_amount = requested * Decimal(random.uniform(0.6, 1.0)).quantize(Decimal('0.01'))
        if status == 'rejected':
            rejection_reason = random.choice(['low_score', 'insufficient_income', 'fraud_risk', 'missing_documents'])
        loans.append((user_id, requested, approved_amount, status, submitted, decided, rejection_reason))

    await conn.executemany(
        '''
        INSERT INTO loan_applications(user_id, requested_amount, approved_amount, status, submitted_at, decided_at, rejection_reason)
        VALUES($1, $2, $3, $4, $5, $6, $7)
        ''',
        loans,
    )

    txs = []
    for _ in range(15000):
        txs.append((
            random.choice(user_ids),
            random.choice(MERCHANTS),
            random.choice(CATEGORIES),
            Decimal(random.randint(20, 50000)) / Decimal('1.00'),
            'UAH',
            random.choices(TX_STATUSES, weights=[82, 8, 5, 5])[0],
            random_dt(start, end),
        ))
    await conn.executemany(
        '''
        INSERT INTO transactions(user_id, merchant_name, merchant_category, amount, currency, status, created_at)
        VALUES($1, $2, $3, $4, $5, $6, $7)
        ''',
        txs,
    )

    await conn.close()
    print('Seed complete: users=5000, loan_applications=7000, transactions=15000')


if __name__ == '__main__':
    asyncio.run(main())
