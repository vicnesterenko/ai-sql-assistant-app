"""
    Обмеження кількості запитів для кожної чат-сесії.
    Redis
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.core.settings import settings

# _BUCKETS — це словник, де ключем є session_id, а значенням — черга часових міток запитів:
# _BUCKETS = {
#     "session-1": deque([10:00:01, 10:00:10, 10:00:35]), -> [session_id: time.time()]
#     "session-2": deque([10:00:20]),
# }
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


async def check_session_rate_limit(session_id: str) -> None:
    """
    Перевіряє ліміт запитів для сесії за останні 60 секунд.

    Для кожної сесії зберігається черга часових міток запитів.
    Застарілі мітки видаляються, а при перевищенні ліміту
    повертається помилка HTTP 429.
    """

    now = time.time()
    window_start = now - 60

    bucket = _BUCKETS[session_id]

    while bucket and bucket[0] < window_start:
        bucket.popleft()

    limit = settings.request_rate_limit_per_minute

    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: maximum "
                f"{limit} requests per minute per session"
            ),
        )

    bucket.append(now)
