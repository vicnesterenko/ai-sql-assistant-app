import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.core.settings import settings

_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def check_session_rate_limit(session_id: str) -> None:
    """
        Enforce a per-session sliding-window rate limit.

        Each session has its own bucket. The bucket stores timestamps of requests
        made during the last 60 seconds.

        On every request:
        1. Remove timestamps older than 60 seconds.
        2. Check how many requests remain in the bucket.
        3. If the count is greater than or equal to the configured limit, reject
           the request with HTTP 429.
        4. Otherwise, add the current request timestamp to the bucket.

        This is a simple in-memory rate limiter.
    """
    now = time.time()
    window_start = now - 60
    bucket = _BUCKETS[session_id]
    while bucket and bucket[0] < window_start:
        bucket.popleft()
    if len(bucket) >= settings.request_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 20 requests per minute per session")
    bucket.append(now)
