from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .budget import BudgetExceeded, bounded_sleep, bounded_timeout, reserve_http_attempt
from .model_credentials import ModelKeyPool
from .http import PROVIDER_OPENER, provider_error_diagnostics


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if math.isfinite(value) and value >= 0 else default


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _secret_values(*names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = os.environ.get(name, "")
        for value in re.split(r"[,\n;]", raw):
            value = value.strip()
            if value and value not in values:
                values.append(value)
    return values


@dataclass(frozen=True)
class ModelConfig:
    """OpenAI-compatible chat configuration; credentials never enter profiles."""

    api_key: str = field(repr=False)
    endpoint: str
    model: str
    provider: str = "custom"
    timeout_seconds: float = 30.0
    max_input_chars: int = 18_000
    max_output_tokens: int = 1_200
    cost_per_call_usd: float = 0.0
    api_keys: tuple[str, ...] = field(default=(), repr=False)
    requests_per_key_per_day: int = 0
    provider_min_interval_seconds: float = 0.0
    openrouter_http_referer: str = ""
    openrouter_app_title: str = "Signalpost"

    @classmethod
    def from_environment(cls) -> "ModelConfig":
        # Select one explicit provider namespace. Never mix credentials from
        # different providers into a pool sent to one endpoint.
        provider = (os.environ.get("SIGNALPOST_MODEL_PROVIDER") or "").strip().casefold()
        if provider not in {"", "openai", "openrouter", "groq", "custom"}:
            provider = "custom"
        if not provider:
            if _secret_values("SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_API_KEY"):
                provider = "custom"
            elif _secret_values("GROQ_API_KEYS", "GROQ_API_KEY"):
                provider = "groq"
            elif _secret_values("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"):
                provider = "openrouter"
            elif _secret_values("OPENAI_API_KEYS", "OPENAI_API_KEY"):
                provider = "openai"
            else:
                provider = "custom"

        provider_keys = {
            "openai": ("OPENAI_API_KEYS", "OPENAI_API_KEY"),
            "openrouter": ("OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"),
            "groq": ("GROQ_API_KEYS", "GROQ_API_KEY"),
            "custom": ("SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_API_KEY", "AI_API_KEY"),
        }[provider]
        keys = _secret_values(*provider_keys)
        if not keys and provider != "custom":
            keys = _secret_values("SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_API_KEY")
        base_defaults = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "groq": "https://api.groq.com/openai/v1",
            "custom": os.environ.get("AI_BASE_URL") or "https://api.openai.com/v1",
        }
        base_names = {
            "openai": "OPENAI_BASE_URL",
            "openrouter": "OPENROUTER_BASE_URL",
            "groq": "GROQ_BASE_URL",
            "custom": "AI_BASE_URL",
        }
        base = os.environ.get(base_names[provider]) or base_defaults[provider]
        api_key = keys[0] if keys else ""
        endpoint = (os.environ.get("SIGNALPOST_MODEL_ENDPOINT") or base).strip()
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        model_defaults = {
            "openai": "gpt-5.6-sol",
            "openrouter": "openai/gpt-5.6-sol",
            "groq": "openai/gpt-oss-120b",
            "custom": "openai/gpt-oss-120b",
        }
        model_names = {
            "openai": "OPENAI_MODEL",
            "openrouter": "OPENROUTER_MODEL",
            "groq": "GROQ_MODEL",
            "custom": "AI_MODEL",
        }
        model = (os.environ.get("SIGNALPOST_MODEL") or os.environ.get(model_names[provider])
                 or model_defaults[provider]).strip()
        host = (urllib.parse.urlparse(endpoint).hostname or "").casefold()
        known_price = provider == "groq" and (host == "api.groq.com" or host.endswith(".groq.com")) and model == "openai/gpt-oss-120b"
        price_name = "SIGNALPOST_MODEL_COST_PER_CALL_USD"
        # Unknown provider/model pricing must be explicitly supplied. A blank
        # template value must not accidentally declare a zero-cost call.
        price_default = 0.0 if known_price else float("nan")
        interval_default = 2.1 if provider == "groq" else 0.0
        return cls(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            provider=provider,
            timeout_seconds=_float_env("SIGNALPOST_MODEL_TIMEOUT_SECONDS", 30.0),
            max_input_chars=_int_env("SIGNALPOST_MODEL_MAX_INPUT_CHARS", 18_000),
            max_output_tokens=_int_env("SIGNALPOST_MODEL_MAX_OUTPUT_TOKENS", 1_200),
            cost_per_call_usd=_float_env(price_name, price_default),
            api_keys=tuple(keys[1:]),
            requests_per_key_per_day=_int_env("SIGNALPOST_MODEL_REQUESTS_PER_KEY_PER_DAY", 0),
            provider_min_interval_seconds=_float_env(
                "SIGNALPOST_MODEL_MIN_INTERVAL_SECONDS", interval_default
            ),
            openrouter_http_referer=(os.environ.get("OPENROUTER_HTTP_REFERER") or "").strip(),
            openrouter_app_title=(os.environ.get("OPENROUTER_APP_TITLE") or "Signalpost").strip(),
        )

    @property
    def configured(self) -> bool:
        host = (urllib.parse.urlparse(self.endpoint).hostname or "").casefold()
        known_hosts = {
            "openai": host == "api.openai.com" or host.endswith(".openai.com"),
            "openrouter": host == "openrouter.ai" or host.endswith(".openrouter.ai"),
            "groq": host == "api.groq.com" or host.endswith(".groq.com"),
        }
        endpoint_conflict = self.provider != "custom" and any(
            known_hosts.get(other, False) and other != self.provider
            for other in ("openai", "openrouter", "groq")
        )
        return bool(self.credentials and self.endpoint and self.model and self.max_output_tokens
                    and not endpoint_conflict
                    and math.isfinite(self.cost_per_call_usd) and self.cost_per_call_usd >= 0
                    and math.isfinite(self.provider_min_interval_seconds)
                    and self.provider_min_interval_seconds >= 0)

    @property
    def credentials(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(key for key in (self.api_key, *self.api_keys) if key))

    @property
    def provider_rate_limits_shared(self) -> bool:
        host = (urllib.parse.urlparse(self.endpoint).hostname or "").casefold()
        return self.provider == "groq" or host == "api.groq.com" or host.endswith(".groq.com")

    def reservation_cost_usd(self, input_tokens: int) -> float:
        """Return a conservative upper bound for one provider reservation.

        An explicit per-call value may raise the bound. Groq's GPT-OSS 120B price
        is used when that exact provider/model pair is selected; unknown
        providers must declare their own cost instead of being guessed.
        """
        host = (urllib.parse.urlparse(self.endpoint).hostname or "").casefold()
        if (self.provider == "groq" or host == "api.groq.com" or host.endswith(".groq.com")) and self.model == "openai/gpt-oss-120b":
            published = (max(0, int(input_tokens)) * 0.15 + self.max_output_tokens * 0.60) / 1_000_000
            return max(self.cost_per_call_usd, published)
        return self.cost_per_call_usd


def _json_content(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("model response must be an object")
    choices = payload.get("choices") or []
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("model response has no choices")
    message = choices[0].get("message") or {}
    if not isinstance(message, dict):
        raise ValueError("model message must be an object")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("model response has no text content")
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model response was not valid JSON") from exc
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("model JSON root must be an object")
    return value


class ModelClient:
    """Small stdlib-only client for OpenAI-compatible JSON chat endpoints."""

    def __init__(self, config: ModelConfig, budget):
        self.config = config
        self.budget = budget
        pool = getattr(budget, "model_key_pool", None)
        if pool is None or pool.keys != config.credentials:
            pool = ModelKeyPool(config.credentials,
                                max_requests_per_key=config.requests_per_key_per_day)
        self.key_pool = pool

    def complete_json(self, *, system: str, user: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        config = self.config
        input_chars = len(system) + len(user)
        if not config.configured:
            return None, {"status": "disabled", "reason": "model credentials or configuration are absent"}
        if input_chars > config.max_input_chars:
            user = user[: max(0, config.max_input_chars - len(system))]
            input_chars = len(system) + len(user)
        # GPT-OSS uses a byte-level tokenizer. UTF-8 bytes plus a chat-framing
        # allowance bound input tokens; chars/4 is only an average and can
        # undercharge Norwegian, markup, or adversarial text substantially.
        estimated_input_tokens = len(system.encode("utf-8")) + len(user.encode("utf-8")) + 64
        estimated_tokens = estimated_input_tokens + config.max_output_tokens
        reservation_cost_usd = config.reservation_cost_usd(estimated_input_tokens)
        attempts = 0
        last_reason = "model_key_unavailable"
        while attempts < len(config.credentials):
            try:
                provider_delay = self.key_pool.reserve_provider_delay(
                    config.provider_min_interval_seconds if config.provider_rate_limits_shared else 0
                )
                if provider_delay:
                    bounded_sleep(provider_delay)
            except BudgetExceeded as exc:
                return None, {"status": "budget_exhausted", "reason": str(exc),
                              "attempts": attempts, "key_count": len(config.credentials)}
            lease = self.key_pool.acquire()
            if lease is None:
                return None, {"status": "budget_exhausted", "reason": last_reason,
                              "key_count": len(config.credentials), "attempts": attempts}
            reserved_transport = False
            started = time.monotonic()
            try:
                if not self.budget.reserve_llm(estimated_tokens, reservation_cost_usd,
                                               key_id=lease.key):
                    return None, {"status": "budget_exhausted", "reason": "model call/token/cost allowance exhausted",
                                  "key_count": len(config.credentials), "attempts": attempts}
                reserve_http_attempt(config.endpoint)
                reserved_transport = True
                body_payload = {
                    "model": config.model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0,
                }
                known_openai_compatible = config.provider in {"openai", "openrouter", "groq"} or config.provider_rate_limits_shared
                if known_openai_compatible:
                    body_payload["max_completion_tokens"] = config.max_output_tokens
                    body_payload["response_format"] = {"type": "json_object"}
                else:
                    body_payload["max_tokens"] = config.max_output_tokens
                body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {lease.key}",
                    "User-Agent": "builderr-signalpost-agent/1.0 (+https://builderr.ai)",
                }
                if config.provider == "openrouter":
                    if config.openrouter_http_referer:
                        headers["HTTP-Referer"] = config.openrouter_http_referer
                    if config.openrouter_app_title:
                        headers["X-Title"] = config.openrouter_app_title
                request = urllib.request.Request(config.endpoint, data=body, method="POST", headers=headers)
                with PROVIDER_OPENER.open(request, timeout=bounded_timeout(config.timeout_seconds)) as response:
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError("model response exceeded the response-size limit")
                payload = json.loads(raw)
                return _json_content(payload), {
                    "status": "available",
                    "model": config.model,
                    "response_bytes": len(raw),
                    "reserved_tokens": estimated_tokens,
                    "reserved_cost_usd": reservation_cost_usd,
                    "attempts": attempts + 1,
                    "key_count": len(config.credentials),
                }
            except urllib.error.HTTPError as exc:
                diagnostics = provider_error_diagnostics(exc, started)
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After", "60") if exc.headers else "60"
                    try:
                        retry_after = float(retry_after)
                    except (TypeError, ValueError):
                        retry_after = 60.0
                    self.key_pool.mark_rate_limited(
                        lease, retry_after,
                        provider_wide=config.provider_rate_limits_shared,
                    )
                    last_reason = "provider_rate_limited"
                    if config.provider_rate_limits_shared:
                        return None, {**diagnostics, "status": "failed", "reason": "provider_rate_limited",
                                      "attempts": attempts + 1, "key_count": len(config.credentials),
                                      "reserved_cost_usd": reservation_cost_usd,
                                      "provider_scope": "organization"}
                    if attempts + 1 >= len(config.credentials):
                        return None, {**diagnostics, "status": "failed", "reason": "http_429",
                                      "attempts": attempts + 1, "key_count": len(config.credentials)}
                    attempts += 1
                    continue
                return None, {**diagnostics, "status": "failed", "reason": f"http_{exc.code}",
                              "attempts": attempts + 1, "key_count": len(config.credentials)}
            except BudgetExceeded as exc:
                return None, {"status": "budget_exhausted", "reason": str(exc),
                              "attempts": attempts, "key_count": len(config.credentials)}
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                operation = {"status": "failed", "reason": type(exc).__name__,
                             "attempts": attempts + 1, "key_count": len(config.credentials)}
                if isinstance(exc, TimeoutError):
                    operation.update({"latency_ms": int((time.monotonic() - started) * 1000),
                                      "timeout_seconds": config.timeout_seconds})
                return None, operation
            finally:
                if not reserved_transport:
                    self.key_pool.release(lease)
            attempts += 1
        return None, {"status": "failed", "reason": last_reason,
                      "attempts": attempts, "key_count": len(config.credentials)}
