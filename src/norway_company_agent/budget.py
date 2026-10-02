from __future__ import annotations

import os
from dataclasses import dataclass


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
