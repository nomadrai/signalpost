from __future__ import annotations

import multiprocessing
import math
import time
from dataclasses import dataclass, field
from contextlib import contextmanager


@dataclass(frozen=True)
class KeyLease:
    index: int
    key: str = field(repr=False)


class ModelKeyPool:
    """Process-shared, non-secret rotation state for model credentials.

    A key is temporarily withheld after a provider rate-limit response. The
    pool never logs or serializes the key values in its public state. The
    daily persistent request limit is enforced by ``RunBudget`` before a
    leased key is sent to the provider.
    """

    def __init__(self, keys: tuple[str, ...] | list[str], *, context=None,
                 max_requests_per_key: int = 0):
        context = context or multiprocessing.get_context("spawn")
        unique: list[str] = []
        for key in keys:
            key = str(key).strip()
            if key and key not in unique:
                unique.append(key)
        self.keys = tuple(unique)
        self.max_requests_per_key = max(0, int(max_requests_per_key))
        self.lock = context.RLock()
        self.next_index = context.Value("q", 0, lock=False)
        self.uses = context.Array("q", len(self.keys), lock=False)
        self.cooldown_until = context.Array("d", len(self.keys), lock=False)
        self.provider_next_start = context.Value("d", 0.0, lock=False)
        # Some providers, including Groq, apply quotas at organization scope.
        # This shared gate prevents another credential from being used to
        # bypass a provider-wide 429 cooldown.
        self.provider_cooldown_until = context.Value("d", 0.0, lock=False)

    @contextmanager
    def _locked(self):
        if not self.lock.acquire(timeout=0.5):
            raise RuntimeError("model credential gate unavailable")
        try:
            yield
        finally:
            self.lock.release()

    def acquire(self) -> KeyLease | None:
        if not self.keys:
            return None
        now = time.monotonic()
        with self._locked():
            if self.provider_cooldown_until.value > now:
                return None
            start = self.next_index.value % len(self.keys)
            for offset in range(len(self.keys)):
                index = (start + offset) % len(self.keys)
                if self.cooldown_until[index] > now:
                    continue
                if (self.max_requests_per_key and
                        self.uses[index] >= self.max_requests_per_key):
                    continue
                self.uses[index] += 1
                self.next_index.value = index + 1
                return KeyLease(index, self.keys[index])
        return None

    def reserve_provider_delay(self, interval_seconds: float) -> float:
        """Reserve the next shared provider start slot across worker processes."""
        interval = float(interval_seconds)
        if not math.isfinite(interval) or interval <= 0:
            return 0.0
        with self._locked():
            now = time.monotonic()
            start = max(now, self.provider_next_start.value)
            self.provider_next_start.value = start + interval
            return max(0.0, start - now)

    def release(self, lease: KeyLease) -> None:
        with self._locked():
            if 0 <= lease.index < len(self.uses) and self.uses[lease.index] > 0:
                self.uses[lease.index] -= 1

    def mark_rate_limited(self, lease: KeyLease, retry_after_seconds: float = 60.0,
                          *, provider_wide: bool = False) -> None:
        delay = float(retry_after_seconds)
        delay = max(1.0, delay) if math.isfinite(delay) else 60.0
        with self._locked():
            if 0 <= lease.index < len(self.cooldown_until):
                self.cooldown_until[lease.index] = max(
                    self.cooldown_until[lease.index], time.monotonic() + delay
                )
            if provider_wide:
                self.provider_cooldown_until.value = max(
                    self.provider_cooldown_until.value, time.monotonic() + delay
                )

    def report(self) -> dict[str, int]:
        with self._locked():
            return {
                "configured_keys": len(self.keys),
                "active_keys": sum(
                    1 for index in range(len(self.keys))
                    if not self.max_requests_per_key or
                    self.uses[index] < self.max_requests_per_key
                ),
                "reserved_key_attempts": sum(self.uses),
                "per_key_request_limit": self.max_requests_per_key,
            }
