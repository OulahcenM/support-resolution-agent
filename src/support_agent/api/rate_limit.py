"""In-memory sliding-window rate limiting for public endpoints.

Single-process only: with several API instances, move the counters to Redis.
"""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import HTTPException, Request, status

RATE_LIMITED_MESSAGE = "Too many messages. Please wait a moment and try again."


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float, max_keys: int = 50_000) -> None:
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, now: float | None = None) -> float | None:
        """Record a request. Returns None if allowed, otherwise seconds until a slot frees up."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            if len(self._hits) > self.max_keys:
                self._prune(now)
            return None

    def _prune(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]
        for key in stale:
            del self._hits[key]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def public_rate_limit_dependency(
    per_ip: SlidingWindowRateLimiter, global_cap: SlidingWindowRateLimiter
) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        retry_after = per_ip.hit(client_ip(request))
        if retry_after is None:
            retry_after = global_cap.hit("global")
        if retry_after is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                RATE_LIMITED_MESSAGE,
                headers={"Retry-After": str(math.ceil(retry_after))},
            )

    return dependency
