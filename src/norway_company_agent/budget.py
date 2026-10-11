from __future__ import annotations

import os
import math
import multiprocessing
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING


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
        return cls(
            max_llm_calls=integer("MAX_LLM_CALLS"),
            max_llm_tokens=integer("MAX_LLM_TOKENS"),
            max_search_calls=integer("MAX_SEARCH_CALLS"),
            max_cost_usd=cost,
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
                 modules: tuple[str, ...] = ()):
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

    def reserve_llm(self, tokens: int, cost_usd: float = 0.0) -> bool:
        tokens = max(0, int(tokens))
        cost = self._cost_units(cost_usd)
        with self.lock:
            if (time.monotonic() >= self.deadline or
                self.llm_calls.value >= self.max_llm_calls or
                self.llm_tokens.value + tokens > self.max_llm_tokens or
                self.cost.value + cost > self.max_cost_microdollars):
                return False
            self.llm_calls.value += 1
            self.llm_tokens.value += tokens
            self.cost.value += cost
            self._record()
            return True

    def reserve_search(self, cost_usd: float = 0.0) -> bool:
        cost = self._cost_units(cost_usd)
        with self.lock:
            if (time.monotonic() >= self.deadline or
                self.search_calls.value >= self.max_search_calls or
                self.cost.value + cost > self.max_cost_microdollars):
                return False
            self.search_calls.value += 1
            self.cost.value += cost
            self._record()
            return True

    def report(self) -> dict:
        # Read after workers are reaped. Lock-free reads also allow reporting
        # when a hard-killed worker died during a reservation.
        return {
            "outbound_requests": self.requests.value,
            "max_outbound_requests": self.max_requests,
            "remaining_outbound_requests": max(0, self.max_requests - self.requests.value),
            "llm_calls": self.llm_calls.value,
            "llm_tokens": self.llm_tokens.value,
            "search_calls": self.search_calls.value,
            "cost_usd": self.cost.value / 1_000_000,
            "remaining_cost_usd": (self.max_cost_microdollars - self.cost.value) / 1_000_000,
        }

    def _record(self, **changes):
        if self.ledger_path:
            with open(self.ledger_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"run_id": self.run_id, **self.report(), **changes}, separators=(",", ":")) + "\n")
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
