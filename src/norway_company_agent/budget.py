from __future__ import annotations

import os
import math
import multiprocessing
import json
import hashlib
import re
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - the evaluator runs on POSIX
    fcntl = None

from .model_credentials import ModelKeyPool


class DailyCostLedger:
    """Atomic UTC-day spend and per-key request ledger.

    The file contains only hashed credential identifiers, never API keys. A
    malformed or inaccessible ledger fails closed so a configured daily cap
    cannot silently turn into an unlimited allowance.
    """

    def __init__(self, path: str | None, *, max_cost_usd: float = 0.0,
                 max_requests_per_key: int = 0):
        self.path = Path(path).expanduser() if path else None
        self.lock_path = Path(f"{self.path}.lock") if self.path else None
        self.max_cost_microdollars = self._cost_units(max_cost_usd)
        if self.max_cost_microdollars > 10_000_000:
            raise ValueError("Daily cost cap cannot exceed USD 10")
        self.max_requests_per_key = max(0, int(max_requests_per_key))

    @staticmethod
    def _cost_units(value: float) -> int:
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError("Daily provider cost must be finite and nonnegative")
        return int((Decimal(str(value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))

    @staticmethod
    def _day() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    @staticmethod
    def _key_id(key: str | None) -> str | None:
        if not key:
            return None
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def _empty(self, day: str) -> dict:
        return {"day": day, "cost_microdollars": 0,
                "requests": 0, "requests_by_key": {}}

    def _read(self) -> dict:
        day = self._day()
        if not self.path or not self.path.exists():
            return self._empty(day)
        value = json.loads(self.path.read_text(encoding="utf-8"))
        required = {"day", "cost_microdollars", "requests", "requests_by_key"}
        if not isinstance(value, dict) or not required <= value.keys():
            raise ValueError("daily cost ledger is incomplete")
        stored_day = value["day"]
        if (not isinstance(stored_day, str) or date.fromisoformat(stored_day).isoformat() != stored_day
                or stored_day > day):
            raise ValueError("daily cost ledger has an invalid or future date")
        counts = [value["cost_microdollars"], value["requests"]]
        keys = value["requests_by_key"]
        if not isinstance(keys, dict) or any(not re.fullmatch(r"[0-9a-f]{16}", key) for key in keys):
            raise ValueError("daily cost ledger key counts are invalid")
        if any(type(count) is not int or count < 0 for count in [*counts, *keys.values()]):
            raise ValueError("daily cost ledger counters must be nonnegative integers")
        if sum(keys.values()) > value["requests"]:
            raise ValueError("daily cost ledger request counters disagree")
        # Validate old state before rollover; corruption must never reset usage.
        if stored_day < day:
            return self._empty(day)
        return value

    def _write(self, value: dict) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.",
                                         suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @contextmanager
    def _locked(self):
        if not self.path or not self.lock_path or fcntl is None:
            raise RuntimeError("a persistent daily ledger path is required")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            expires = time.monotonic() + 0.5
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= expires:
                        raise RuntimeError("daily ledger lock unavailable")
                    time.sleep(0.005)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def reserve(self, cost_usd: float = 0.0, *, key: str | None = None) -> bool:
        cost = self._cost_units(cost_usd)
        if not self.path:
            return False
        try:
            with self._locked():
                state = self._read()
                key_id = self._key_id(key)
                key_requests = state["requests_by_key"]
                if (self.max_requests_per_key and key_id and
                        int(key_requests.get(key_id, 0)) >= self.max_requests_per_key):
                    return False
                if int(state["cost_microdollars"]) + cost > self.max_cost_microdollars:
                    return False
                state["cost_microdollars"] = int(state["cost_microdollars"]) + cost
                state["requests"] = int(state["requests"]) + 1
                if key_id:
                    key_requests[key_id] = int(key_requests.get(key_id, 0)) + 1
                self._write(state)
                return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError):
            return False

    def report(self) -> dict[str, float | int | str | None]:
        if not self.path:
            return {"path": None, "day": self._day(), "cost_usd": 0.0,
                    "requests": 0, "remaining_cost_usd": None}
        try:
            with self._locked():
                state = self._read()
            cost = int(state["cost_microdollars"])
            remaining = (self.max_cost_microdollars - cost) / 1_000_000
            return {"path": str(self.path), "day": state["day"],
                    "cost_usd": cost / 1_000_000, "requests": int(state["requests"]),
                    "remaining_cost_usd": max(0.0, remaining)}
        except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError):
            return {"path": str(self.path), "day": self._day(), "cost_usd": None,
                    "requests": None, "remaining_cost_usd": None,
                    "status": "unreadable"}


@dataclass
class BudgetGovernor:
    max_llm_calls: int = 0
    max_llm_tokens: int = 0
    max_search_calls: int = 0
    max_cost_usd: float = 0.0
    llm_calls: int = 0
    llm_tokens: int = 0
    search_calls: int = 0
    cost_usd: float = 0.0
    daily_cost_cap_usd: float = 0.0
    daily_cost_ledger_path: str = ""
    model_requests_per_key_per_day: int = 0

    @classmethod
    def from_environment(cls) -> "BudgetGovernor":
        def integer(name: str) -> int:
            try:
                return max(0, int(os.environ.get(name, "0")))
            except ValueError:
                return 0

        try:
            cost = max(0.0, float(os.environ.get("MAX_COST_USD", "0")))
        except ValueError:
            cost = 0.0
        try:
            daily_cost = float(os.environ.get("SIGNALPOST_DAILY_COST_CAP_USD", "10"))
        except ValueError:
            daily_cost = float("nan")  # runner validation rejects invalid caps
        try:
            per_key = max(0, int(os.environ.get("SIGNALPOST_MODEL_REQUESTS_PER_KEY_PER_DAY", "0")))
        except ValueError:
            per_key = 0
        return cls(
            max_llm_calls=integer("MAX_LLM_CALLS"),
            max_llm_tokens=integer("MAX_LLM_TOKENS"),
            max_search_calls=integer("MAX_SEARCH_CALLS"),
            max_cost_usd=cost,
            daily_cost_cap_usd=daily_cost,
            daily_cost_ledger_path=(os.environ.get("SIGNALPOST_DAILY_COST_LEDGER") or
                                    "~/.cache/signalpost/daily-cost.json").strip(),
            model_requests_per_key_per_day=per_key,
        )

    def reserve_llm(self, tokens: int, cost_usd: float = 0.0) -> bool:
        tokens = max(0, int(tokens))
        cost_usd = max(0.0, float(cost_usd))
        if self.llm_calls + 1 > self.max_llm_calls:
            return False
        if self.llm_tokens + tokens > self.max_llm_tokens:
            return False
        if self.cost_usd + cost_usd > self.max_cost_usd:
            return False
        self.llm_calls += 1
        self.llm_tokens += tokens
        self.cost_usd += cost_usd
        return True

    def reserve_search(self) -> bool:
        if self.search_calls + 1 > self.max_search_calls:
            return False
        self.search_calls += 1
        return True

    def report(self) -> dict[str, float | int]:
        return {
            "llm_calls": self.llm_calls,
            "llm_tokens": self.llm_tokens,
            "search_calls": self.search_calls,
            "cost_usd": round(self.cost_usd, 8),
            "remaining_llm_calls": max(0, self.max_llm_calls - self.llm_calls),
            "remaining_llm_tokens": max(0, self.max_llm_tokens - self.llm_tokens),
            "remaining_search_calls": max(0, self.max_search_calls - self.search_calls),
            "remaining_cost_usd": round(max(0.0, self.max_cost_usd - self.cost_usd), 8),
        }


class BudgetExceeded(RuntimeError):
    """An HTTP attempt was refused before entering the transport."""


class RunBudget:
    """Shared, atomic reservations across all worker processes in one run.

    Requests are charged before sending, including failed attempts. Provider
    costs are upper-bound reservations in microdollars and are never refunded.
    No provider is enabled by a nonzero monetary cap alone.
    """

    def __init__(self, *, max_requests: int = 2000, deadline: float = math.inf,
                 companies: int = 0, governor: BudgetGovernor | None = None,
                 context=None, ledger_path: str | None = None, run_id: str | None = None,
                 modules: tuple[str, ...] = (), model_keys: tuple[str, ...] = (),
                 model_requests_per_key: int = 0):
        context = context or multiprocessing.get_context("spawn")
        governor = governor or BudgetGovernor()
        self.max_requests = max(0, int(max_requests))
        self.deadline = deadline
        self.max_llm_calls = governor.max_llm_calls
        self.max_llm_tokens = governor.max_llm_tokens
        self.max_search_calls = governor.max_search_calls
        self.max_cost_microdollars = self._cost_units(governor.max_cost_usd)
        self.lock = context.RLock()
        self.ledger_path = ledger_path
        self.run_id = run_id
        self.requests = context.Value("q", 0, lock=False)
        self.company_requests = context.Array("q", companies, lock=False)
        # Invocation-local attribution is separate from the cumulative quota
        # restored on resume. Charge it before a response can be lost to timeout.
        self.module_indices = {name: index for index, name in enumerate(dict.fromkeys(modules))}
        self.module_requests = context.Array("q", len(self.module_indices), lock=False)
        self.unattributed_requests = context.Value("q", 0, lock=False)
        self.llm_calls = context.Value("q", 0, lock=False)
        self.llm_tokens = context.Value("q", 0, lock=False)
        self.search_calls = context.Value("q", 0, lock=False)
        self.cost = context.Value("q", 0, lock=False)
        self.history_next_start = context.Value("d", 0.0, lock=False)
        self.search_next_start = context.Value("d", 0.0, lock=False)
        daily_cap = float(getattr(governor, "daily_cost_cap_usd", 0.0))
        daily_path = str(getattr(governor, "daily_cost_ledger_path", "") or "")
        daily_key_cap = max(0, int(getattr(governor, "model_requests_per_key_per_day", 0)))
        self.daily_ledger = (DailyCostLedger(
            daily_path, max_cost_usd=daily_cap,
            max_requests_per_key=daily_key_cap
        ) if daily_path or daily_cap or daily_key_cap else None)
        self.model_key_pool = ModelKeyPool(
            tuple(model_keys), context=context,
            max_requests_per_key=max(0, int(model_requests_per_key or daily_key_cap))
        ) if model_keys else None

    def reserve_history_start(self) -> float:
        if not self.lock.acquire(timeout=max(0.001, min(1.0, self.deadline - time.monotonic()))):
            raise BudgetExceeded("request_gate_unavailable")
        try:
            now = time.monotonic()
            start = max(now, self.history_next_start.value)
            self.history_next_start.value = start + 2.1
            return max(0, start - now)
        finally:
            self.lock.release()

    def reserve_search_start(self, interval_seconds: float) -> float:
        """Reserve a shared start slot for a rate-limited search provider."""
        interval = float(interval_seconds)
        if not math.isfinite(interval) or interval <= 0:
            return 0.0
        if not self.lock.acquire(timeout=max(0.001, min(1.0, self.deadline - time.monotonic()))):
            raise BudgetExceeded("search_gate_unavailable")
        try:
            now = time.monotonic()
            start = max(now, self.search_next_start.value)
            self.search_next_start.value = start + interval
            return max(0.0, start - now)
        finally:
            self.lock.release()

    @staticmethod
    def _cost_units(value: float) -> int:
        if not math.isfinite(value) or value < 0:
            raise ValueError("Provider cost must be finite and nonnegative")
        return int((Decimal(str(value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))

    def reserve_request(self, company_index: int | None = None, *, module: str | None = None) -> None:
        # A terminated process can leave a multiprocessing lock held. Refuse
        # attempts rather than waiting indefinitely on an abandoned gate.
        if not self.lock.acquire(timeout=max(0.001, min(1.0, self.deadline - time.monotonic()))):
            raise BudgetExceeded("request_gate_unavailable")
        try:
            if time.monotonic() >= self.deadline:
                raise BudgetExceeded("run_deadline")
            if self.requests.value >= self.max_requests:
                raise BudgetExceeded("outbound_request_cap")
            self._record(outbound_requests=self.requests.value + 1,
                         remaining_outbound_requests=self.max_requests - self.requests.value - 1,
                         company_index=company_index, module=module)
            self.requests.value += 1
            if company_index is not None:
                self.company_requests[company_index] += 1
            if module in self.module_indices:
                self.module_requests[self.module_indices[module]] += 1
            else:
                self.unattributed_requests.value += 1
        finally:
            self.lock.release()

    def reserve_llm(self, tokens: int, cost_usd: float = 0.0, *, key_id: str | None = None) -> bool:
        tokens = max(0, int(tokens))
        cost = self._cost_units(cost_usd)
        if not self.lock.acquire(timeout=max(0.001, min(1.0, self.deadline - time.monotonic()))):
            return False
        try:
            if (time.monotonic() >= self.deadline or
                self.llm_calls.value >= self.max_llm_calls or
                self.llm_tokens.value + tokens > self.max_llm_tokens or
                self.cost.value + cost > self.max_cost_microdollars):
                return False
            if self.daily_ledger and not self.daily_ledger.reserve(cost_usd, key=key_id):
                return False
            self.llm_calls.value += 1
            self.llm_tokens.value += tokens
            self.cost.value += cost
            self._record()
            return True
        finally:
            self.lock.release()

    def reserve_search(self, cost_usd: float = 0.0) -> bool:
        cost = self._cost_units(cost_usd)
        if not self.lock.acquire(timeout=max(0.001, min(1.0, self.deadline - time.monotonic()))):
            return False
        try:
            if (time.monotonic() >= self.deadline or
                self.search_calls.value >= self.max_search_calls or
                self.cost.value + cost > self.max_cost_microdollars):
                return False
            if self.daily_ledger and not self.daily_ledger.reserve(cost_usd):
                return False
            self.search_calls.value += 1
            self.cost.value += cost
            self._record()
            return True
        finally:
            self.lock.release()

    def report(self, *, include_daily: bool = True) -> dict:
        # Read after workers are reaped. Lock-free reads also allow reporting
        # when a hard-killed worker died during a reservation.
        result = {
            "outbound_requests": self.requests.value,
            "max_outbound_requests": self.max_requests,
            "remaining_outbound_requests": max(0, self.max_requests - self.requests.value),
            "llm_calls": self.llm_calls.value,
            "llm_tokens": self.llm_tokens.value,
            "search_calls": self.search_calls.value,
            "cost_usd": self.cost.value / 1_000_000,
            "remaining_cost_usd": (self.max_cost_microdollars - self.cost.value) / 1_000_000,
        }
        if include_daily and self.daily_ledger:
            result["daily"] = self.daily_ledger.report()
        return result

    def _record(self, **changes):
        if self.ledger_path:
            with open(self.ledger_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"run_id": self.run_id, **self.report(include_daily=False), **changes}, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


@dataclass
class RequestScope:
    budget: RunBudget
    company_index: int | None
    deadline: float
    max_requests: int
    module: str | None = None
    requests: int = 0


_scope: ContextVar[RequestScope | None] = ContextVar("outbound_request_scope", default=None)


@contextmanager
def request_scope(budget: RunBudget, *, company_index: int | None = None,
                  deadline: float = math.inf, max_requests: int = 2000,
                  module: str | None = None):
    token = _scope.set(RequestScope(budget, company_index, min(deadline, budget.deadline), max_requests, module))
    try:
        yield _scope.get()
    finally:
        _scope.reset(token)


def reserve_http_attempt(url: str = "") -> None:
    scope = _scope.get()
    if scope is None:
        return
    if time.monotonic() >= scope.deadline:
        raise BudgetExceeded("company_deadline")
    if scope.requests >= scope.max_requests:
        raise BudgetExceeded("module_request_cap")
    if "/regnskapsregisteret/regnskap/aarsregnskap/kopi/" in url and url.endswith("/aar"):
        bounded_sleep(scope.budget.reserve_history_start())
        if time.monotonic() >= scope.deadline:
            raise BudgetExceeded("company_deadline")
    scope.budget.reserve_request(scope.company_index, module=scope.module)
    scope.requests += 1


def bounded_timeout(timeout: float) -> float:
    scope = _scope.get()
    if scope is None:
        return timeout
    remaining = scope.deadline - time.monotonic()
    if remaining <= 0:
        raise BudgetExceeded("company_deadline")
    return min(timeout, remaining)


def bounded_sleep(seconds: float) -> None:
    scope = _scope.get()
    if scope is not None and time.monotonic() + seconds >= scope.deadline:
        raise BudgetExceeded("company_deadline")
    time.sleep(seconds)
