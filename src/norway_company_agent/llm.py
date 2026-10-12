from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .budget import BudgetExceeded, bounded_timeout, reserve_http_attempt


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


@dataclass(frozen=True)
class ModelConfig:
    """OpenAI-compatible chat configuration; credentials never enter profiles."""

    api_key: str
    endpoint: str
    model: str
    timeout_seconds: float = 30.0
    max_input_chars: int = 18_000
    max_output_tokens: int = 1_200
    cost_per_call_usd: float = 0.0

    @classmethod
    def from_environment(cls) -> "ModelConfig":
        api_key = (
            os.environ.get("SIGNALPOST_MODEL_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("AI_API_KEY")
            or ""
        ).strip()
        endpoint = (
            os.environ.get("SIGNALPOST_MODEL_ENDPOINT")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("AI_BASE_URL")
            or "https://api.openai.com/v1/chat/completions"
        ).strip()
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        return cls(
            api_key=api_key,
            endpoint=endpoint,
            model=(os.environ.get("SIGNALPOST_MODEL") or os.environ.get("OPENAI_MODEL")
                   or os.environ.get("AI_MODEL") or "openai/gpt-oss-120b").strip(),
            timeout_seconds=_float_env("SIGNALPOST_MODEL_TIMEOUT_SECONDS", 30.0),
            max_input_chars=_int_env("SIGNALPOST_MODEL_MAX_INPUT_CHARS", 18_000),
            max_output_tokens=_int_env("SIGNALPOST_MODEL_MAX_OUTPUT_TOKENS", 1_200),
            cost_per_call_usd=_float_env("SIGNALPOST_MODEL_COST_PER_CALL_USD", 0.0),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.endpoint and self.model and self.max_output_tokens)


def _json_content(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ValueError("model response has no choices")
    message = choices[0].get("message") or {}
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

    def complete_json(self, *, system: str, user: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        config = self.config
        input_chars = len(system) + len(user)
        if not config.configured:
            return None, {"status": "disabled", "reason": "model credentials or configuration are absent"}
        if input_chars > config.max_input_chars:
            user = user[: max(0, config.max_input_chars - len(system))]
            input_chars = len(system) + len(user)
        estimated_tokens = math.ceil(input_chars / 4) + config.max_output_tokens
        if not self.budget.reserve_llm(estimated_tokens, config.cost_per_call_usd):
            return None, {"status": "budget_exhausted", "reason": "model call/token/cost allowance exhausted"}
        try:
            reserve_http_attempt(config.endpoint)
            body = json.dumps({
                "model": config.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0,
                "max_tokens": config.max_output_tokens,
            }, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(config.endpoint, data=body, method="POST", headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
                "User-Agent": "builderr-signalpost-agent/1.0 (+https://builderr.ai)",
            })
            with urllib.request.urlopen(request, timeout=bounded_timeout(config.timeout_seconds)) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("model response exceeded the response-size limit")
            payload = json.loads(raw)
            return _json_content(payload), {
                "status": "available",
                "model": config.model,
                "response_bytes": len(raw),
                "reserved_tokens": estimated_tokens,
            }
        except BudgetExceeded as exc:
            return None, {"status": "budget_exhausted", "reason": str(exc)}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return None, {"status": "failed", "reason": type(exc).__name__}
