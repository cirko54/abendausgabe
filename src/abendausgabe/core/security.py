"""Gerätetoken, PIN-Hashing und Begrenzung von Fehlversuchen."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

PIN_ITERATIONS = 200_000


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_salt() -> str:
    return secrets.token_hex(16)


def hash_pin(pin: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), PIN_ITERATIONS)
    return digest.hex()


def verify_pin(pin: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_pin(pin, salt), expected_hash)


class AttemptLimiter:
    """Höchstens max_attempts Fehlversuche pro Schlüssel im Zeitfenster."""

    def __init__(self, max_attempts: int = 5, window_s: float = 600.0) -> None:
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        failures = self._failures[key]
        while failures and now - failures[0] > self.window_s:
            failures.popleft()
        return failures

    def allowed(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return len(self._prune(key, now)) < self.max_attempts

    def record_failure(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
