"""Zentraler Token-Bucket je externer Quelle (SPEC §13)."""

from __future__ import annotations

import time


class RateLimitedError(RuntimeError):
    pass


class TokenBucket:
    def __init__(self, capacity: int, per_seconds: float) -> None:
        self.capacity = capacity
        self.refill_rate = capacity / per_seconds
        self.tokens = float(capacity)
        self.updated = time.monotonic()

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(float(self.capacity), self.tokens + elapsed * self.refill_rate)
        self.updated = now

    def try_acquire(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_BUCKETS: dict[str, TokenBucket] = {
    # Tagesschau: höchstens 60 Abrufe pro Stunde
    "tagesschau": TokenBucket(capacity=60, per_seconds=3600),
    # MediathekViewWeb (Community-Projekt): sparsam, höchstens 30 pro Stunde
    "mediathekviewweb": TokenBucket(capacity=30, per_seconds=3600),
    "ntfy": TokenBucket(capacity=30, per_seconds=3600),
}


def acquire(source: str) -> None:
    bucket = _BUCKETS.get(source)
    if bucket is None:
        raise KeyError(f"Kein Ratelimit für Quelle {source!r} definiert.")
    if not bucket.try_acquire():
        raise RateLimitedError(f"Ratelimit für {source} erreicht.")
