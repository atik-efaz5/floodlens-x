"""Rate limits for ingest adapters and user-facing alert/report/share actions."""

from __future__ import annotations

import time

from floodlens.application.platform_store import get_platform_store


class TokenBucket:
    """Simple token bucket used by Open-Meteo and Overpass adapters."""

    def __init__(self, capacity: float, refill_per_second: float):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self._updated = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = max(0.0, now - self._updated)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self._updated = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


INGEST_BUCKET = TokenBucket(capacity=30, refill_per_second=1.0)
OVERPASS_BUCKET = TokenBucket(capacity=10, refill_per_second=0.5)

LIMITS = {
    "alert.create": 40,
    "report.generate": 30,
    "share.create": 30,
    "export": 40,
    "location.create": 50,
    "research.run": 30,
    "research.report": 20,
}


class RateLimitExceeded(Exception):
    def __init__(self, action: str, limit: int):
        super().__init__(f"Rate limit exceeded for {action} ({limit})")
        self.action = action
        self.limit = limit


def check_rate(identity: str, action: str) -> None:
    limit = LIMITS.get(action, 40)
    store = get_platform_store()
    key = f"{identity}:{action}"
    used = int(store.rate_counts.get(key) or 0)
    if used >= limit:
        raise RateLimitExceeded(action, limit)
    store.rate_counts[key] = used + 1
