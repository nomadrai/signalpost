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

from .budget import BudgetExceeded, bounded_timeout, reserve_http_attempt
from .discovery import build_company_search_query, parse_brave_web_results
from .http import PROVIDER_OPENER


BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _cost_from_environment() -> float:
    try:
        value = float(os.environ["SIGNALPOST_SEARCH_COST_PER_CALL_USD"])
    except (ValueError, KeyError) as exc:
        raise ValueError("search price must be explicitly configured") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError("search price must be finite and nonnegative")
    return value


def search_company(profile: dict[str, Any], budget, *, timeout: float = 15.0,
                   count: int = 10, cost_per_call_usd: float | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Perform one bounded, transient Brave search.

    Only parsed candidate metadata is returned to the caller. Raw provider
    responses and the query text are never placed in profile evidence.
    """
    api_key = (os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()
    if not api_key:
        return [], {"status": "disabled", "reason": "search credentials are absent"}
    query = build_company_search_query(profile)
    count = max(1, min(20, int(count)))
    url = BRAVE_ENDPOINT + "?" + urllib.parse.urlencode({
        "q": query,
        "count": count,
        "country": "no",
        "search_lang": "nb",
        "safesearch": "moderate",
        "spellcheck": "0",
    })
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
    try:
        if cost_per_call_usd is None:
            cost_per_call_usd = _cost_from_environment()
        if not math.isfinite(cost_per_call_usd) or cost_per_call_usd < 0:
            raise ValueError("invalid search price")
    except ValueError:
        return [], {"status": "disabled", "reason": "search pricing is absent or invalid"}
    if not budget.reserve_search(cost_per_call_usd):
        return [], {"status": "budget_exhausted", "query_sha256": query_hash}
    started = time.monotonic()
    try:
        reserve_http_attempt(url)
        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache",
            "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)",
            "X-Subscription-Token": api_key,
        })
        with PROVIDER_OPENER.open(request, timeout=bounded_timeout(timeout)) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("search response exceeded the response-size limit")
            payload = json.loads(raw)
            if (not isinstance(payload, dict) or not isinstance(payload.get("web", {}), dict)
                    or not isinstance(payload.get("web", {}).get("results", []), list)):
                raise ValueError("invalid search result shape")
            results = parse_brave_web_results(payload, query=query)
        return results, {
            "status": "available",
            "provider_status": response.status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "bytes": len(raw),
            "query_sha256": query_hash,
            "candidate_count": len(results),
        }
    except BudgetExceeded as exc:
        return [], {"status": "budget_exhausted", "reason": str(exc), "query_sha256": query_hash}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], {
            "status": "failed",
            "provider_status": getattr(exc, "code", 0),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "query_sha256": query_hash,
            "reason": type(exc).__name__,
        }
