"""Circuit breaker per external platform API (Render-safe, in-memory)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Literal

CircuitState = Literal["closed", "open", "half_open"]

_STATE: Dict[str, "PlatformCircuitBreaker"] = {}


@dataclass
class PlatformCircuitBreaker:
    platform: str
    failure_threshold: int = 5
    recovery_seconds: float = 60.0
    half_open_max_calls: int = 2
    failures: int = 0
    state: CircuitState = "closed"
    opened_at: float = 0.0
    half_open_calls: int = 0

    def allow_request(self) -> bool:
        now = time.monotonic()
        if self.state == "open":
            if now - self.opened_at >= self.recovery_seconds:
                self.state = "half_open"
                self.half_open_calls = 0
            else:
                return False
        if self.state == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                return False
            self.half_open_calls += 1
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
        self.half_open_calls = 0

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == "half_open":
            self._open()
            return
        if self.failures >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = "open"
        self.opened_at = time.monotonic()
        self.half_open_calls = 0


def get_circuit_breaker(platform: str) -> PlatformCircuitBreaker:
    key = platform.lower()
    if key not in _STATE:
        _STATE[key] = PlatformCircuitBreaker(platform=key)
    return _STATE[key]
