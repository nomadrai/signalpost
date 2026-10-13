from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .budget import BudgetExceeded, bounded_sleep, bounded_timeout, reserve_http_attempt
from .discovery import build_company_search_query
from .http import PROVIDER_OPENER, provider_error_diagnostics


FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/search"


def _cost_from_environment() -> float:
    try:
        value = float(os.environ.get("FIRECRAWL_SEARCH_COST_PER_CALL_USD", "0"))
    except ValueError as exc:
        raise ValueError("Firecrawl search price must be finite and nonnegative") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError("Firecrawl search price must be finite and nonnegative")
    return value


def _interval_from_environment() -> float:
    try:
        value = float(os.environ.get("FIRECRAWL_SEARCH_MIN_INTERVAL_SECONDS", "6.5"))
    except ValueError as exc:
        raise ValueError("Firecrawl search interval must be finite and nonnegative") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError("Firecrawl search interval must be finite and nonnegative")
    return value


def _parse_results(payload: Any, *, query: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise ValueError("invalid Firecrawl response envelope")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("web", []), list):
        raise ValueError("invalid Firecrawl web result shape")
    parsed = []
    for rank, result in enumerate(data["web"], start=1):
        if not isinstance(result, dict) or not isinstance(result.get("url"), str):
            continue
        parsed.append({
            "url": result["url"],
            "title": result.get("title") or "",
            "snippet": result.get("description") or "",
            "rank": result.get("position") or rank,
            "provider": "firecrawl_search_api",
            "query": query,
        })
    return parsed


def search_company(profile: dict[str, Any], budget, *, timeout: float = 15.0,
                   count: int = 10, cost_per_call_usd: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Perform one bounded Firecrawl search; raw results remain transient."""
    query = build_company_search_query(profile)
    count = max(1, min(10, int(count)))
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    if cost_per_call_usd is None:
        cost_per_call_usd = _cost_from_environment()
    try:
        bounded_sleep(budget.reserve_search_start(_interval_from_environment()))
    except BudgetExceeded as exc:
        return [], {"status": "budget_exhausted", "reason": str(exc), "query_sha256": query_hash}
    if not budget.reserve_search(cost_per_call_usd):
        return [], {"status": "budget_exhausted", "query_sha256": query_hash}
    body = json.dumps({
        "query": query,
        "limit": count,
        "country": "NO",
        "location": "Norway",
        "safe": True,
        "highlights": False,
    }, ensure_ascii=False).encode("utf-8")
    endpoint = (os.environ.get("FIRECRAWL_ENDPOINT") or FIRECRAWL_ENDPOINT).strip()
    parsed_endpoint = urllib.parse.urlparse(endpoint)
    local_fixture = parsed_endpoint.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed_endpoint.scheme != "https" and not local_fixture:
        return [], {"status": "disabled", "reason": "Firecrawl endpoint must use HTTPS",
                    "query_sha256": query_hash}
    started = time.monotonic()
    try:
        reserve_http_attempt(endpoint)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)",
        }
        api_key = (os.environ.get("FIRECRAWL_API_KEY") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(endpoint, data=body, method="POST", headers=headers)
        with PROVIDER_OPENER.open(request, timeout=bounded_timeout(timeout)) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Firecrawl response exceeded the response-size limit")
            payload = json.loads(raw)
        results = _parse_results(payload, query=query)
        return results, {
            "status": "available",
            "provider_status": response.status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "bytes": len(raw),
            "query_sha256": query_hash,
            "candidate_count": len(results),
            "credits_used": payload.get("creditsUsed") if isinstance(payload, dict) else None,
        }
    except BudgetExceeded as exc:
        return [], {"status": "budget_exhausted", "reason": str(exc), "query_sha256": query_hash}
    except urllib.error.HTTPError as exc:
        return [], {**provider_error_diagnostics(exc, started),
                    "status": "failed", "query_sha256": query_hash,
                    "reason": type(exc).__name__}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        operation = {
            "status": "failed",
            "provider_status": getattr(exc, "code", 0),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "query_sha256": query_hash,
            "reason": type(exc).__name__,
        }
        if isinstance(exc, TimeoutError):
            operation["timeout_seconds"] = timeout
        return [], operation
