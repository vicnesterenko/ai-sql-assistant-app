import time
from collections import defaultdict, deque
from fastapi import HTTPException
from app.core.settings import settings

_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def check_session_rate_limit(session_id: str) -> None:
    now = time.time()
    window_start = now - 60
    bucket = _BUCKETS[session_id]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= settings.request_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail='Rate limit exceeded: max 20 requests per minute per session')
    bucket.append(now)
