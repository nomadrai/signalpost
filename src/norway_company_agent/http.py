from __future__ import annotations

import json
import hashlib
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .budget import BudgetExceeded, bounded_sleep, bounded_timeout, reserve_http_attempt


class BudgetRequestHandler(urllib.request.BaseHandler):
    """urllib runs request processors again for every redirected HTTP attempt."""

    def http_request(self, request):
        reserve_http_attempt(request.full_url)
        if hasattr(request, "attempt_counter"):
            request.attempt_counter["requests"] += 1
        return request

    https_request = http_request


COUNTED_OPENER = urllib.request.build_opener(BudgetRequestHandler())


class ProviderRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Credential-bearing provider requests must not follow redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


PROVIDER_OPENER = urllib.request.build_opener(ProviderRedirectHandler())


_SAFE_PROVIDER_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")


def provider_error_diagnostics(error: urllib.error.HTTPError, started: float) -> dict[str, Any]:
    """Return bounded, secret-safe diagnostics for a provider HTTP error.

    Provider response bodies are never retained. A bounded body sample is hashed
    for correlation, while only conservative machine-readable error codes and
    request identifiers are copied from the response.
    """
    details: dict[str, Any] = {
        "provider_status": int(getattr(error, "code", 0) or 0),
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    headers = getattr(error, "headers", None)
    if headers is not None:
        def header(name: str):
            value = headers.get(name)
            if value is not None:
                return value
            for key, candidate in getattr(headers, "items", lambda: ())():
                if str(key).casefold() == name.casefold():
                    return candidate
            return None

        for name in ("x-request-id", "request-id", "cf-ray"):
            value = header(name)
            if isinstance(value, str) and _SAFE_PROVIDER_TOKEN.fullmatch(value.strip()):
                details["provider_request_id"] = value.strip()
                break
        retry_after = header("Retry-After")
        try:
            retry_after_value = float(retry_after)
        except (TypeError, ValueError):
            retry_after_value = -1.0
        if math.isfinite(retry_after_value) and retry_after_value >= 0:
            details["retry_after_seconds"] = retry_after_value
    try:
        sample = error.read(65_536)
    except OSError:
        sample = b""
    if isinstance(sample, str):
        sample = sample.encode("utf-8", errors="replace")
    if sample:
        details["provider_body_sample_bytes"] = len(sample)
        details["provider_body_sample_sha256"] = hashlib.sha256(sample).hexdigest()
        try:
            payload = json.loads(sample)
        except (TypeError, ValueError):
            payload = None
        error_payload = payload.get("error") if isinstance(payload, dict) else None
        code = error_payload.get("code") if isinstance(error_payload, dict) else None
        if isinstance(code, str) and _SAFE_PROVIDER_TOKEN.fullmatch(code):
            details["provider_error_code"] = code
    return details


@dataclass
class FetchResult:
    url: str
    status: int
    elapsed_ms: int
    bytes_received: int
    body: Any = None
    error: str | None = None
    content_sha256: str | None = None
    retrieved_at: str | None = None
    effective_at: str | None = None
    budget_exhausted: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, *, timeout: float = 20.0, attempts: int = 3) -> FetchResult:
    last_error = "request failed"
    for attempt in range(attempts):
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "builderr-signalpost-poc/0.1 (+https://builderr.ai)"},
        )
        try:
            with COUNTED_OPENER.open(request, timeout=bounded_timeout(timeout)) as response:
                raw = response.read()
                elapsed = int((time.monotonic() - started) * 1000)
                return FetchResult(url, response.status, elapsed, len(raw), json.loads(raw), content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
        except BudgetExceeded as exc:
            return FetchResult(url, 0, 0, 0, error=str(exc), retrieved_at=_utc_now(), budget_exhausted=True)
        except urllib.error.HTTPError as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            raw = exc.read()
            if exc.code in {404, 410}:
                return FetchResult(url, exc.code, elapsed, len(raw), error=f"HTTP {exc.code}", content_sha256=hashlib.sha256(raw).hexdigest(), retrieved_at=_utc_now())
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        if attempt + 1 < attempts:
            try:
                bounded_sleep(0.4 * (2**attempt))
            except BudgetExceeded as exc:
                return FetchResult(url, 0, 0, 0, error=str(exc), retrieved_at=_utc_now(), budget_exhausted=True)
    return FetchResult(url, 0, 0, 0, error=last_error, retrieved_at=_utc_now())
