from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norway_company_agent.budget import RunBudget, request_scope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.llm import ModelClient, ModelConfig  # noqa: E402
from norway_company_agent.model_signals import extract_model_signals  # noqa: E402
from norway_company_agent.planner import plan_next_action, validate_action  # noqa: E402
from norway_company_agent.schema import build_contract_envelope, validate_claim_evidence  # noqa: E402


ORG = "993578843"
PAGE_URL = "https://example.no/jobs"
PAGE_HASH = hashlib.sha256(PAGE_URL.encode()).hexdigest()


class StubClient:
    config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions", model="test-model")

    def complete_json(self, *, system: str, user: str):
        assert "organisation_number" in user
        return {
            "items": [{
                "family": "hiring",
                "page_url": PAGE_URL,
                "page_sha256": PAGE_HASH,
                "url": PAGE_URL,
                "title": "Senior engineer",
                "date": "2026-08-01",
                "employer_or_publisher": "Example AS",
                "evidence_quote": "Senior engineer",
            }]
        }, {"status": "available", "model": "test-model", "reserved_tokens": 100}


def _profile() -> dict:
    page = {
        "url": PAGE_URL,
        "content_sha256": PAGE_HASH,
        "retrieved_at": "2026-09-15T00:00:00Z",
        "identity_text_excerpt": "Example AS",
        "main_text_excerpt": "Senior engineer",
        "source_document": {"jsonld": [{"@type": "JobPosting", "title": "Senior engineer"}], "articles": []},
    }
    website = evidence(
        "website", "available", "company_owned_website", "https://example.no/",
        value={"final_url": "https://example.no/", "identity_assessment": {"publishable": True}, "pages": [page]},
        content_sha256="a" * 64, retrieved_at="2026-09-15T00:00:00Z",
    )
    return {"organisation_number": ORG, "name": "Example AS", "evidence": {"website": website}}


def test_model_signal_requires_retained_page_hash_and_quote():
    profile = _profile()
    records = extract_model_signals(profile, profile["evidence"]["website"], StubClient())
    assert records["hiring"]["status"] == "available"
    assert records["hiring"]["value"]["items"][0]["method"] == "model_assisted_evidence_extraction_v1"
    profile["evidence"].update(records)
    envelope = build_contract_envelope(profile, run_id="model", started_at="2026-09-15T00:00:00Z",
                                       completed_at="2026-09-15T00:00:01Z", requested_modules=["website", "hiring"])
    assert any(claim["field"] == "hiring.item" for claim in envelope["claims"])
    assert not validate_claim_evidence(envelope)


def test_model_client_respects_shared_model_budget(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return json.dumps({"choices": [{"message": {"content": '{"items": []}'}}]}).encode()

    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open", lambda request, timeout: Response())
    config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions", model="test-model",
                         max_output_tokens=10, cost_per_call_usd=0.1)
    budget = RunBudget(max_requests=1, governor=type("Governor", (), {
        "max_llm_calls": 1, "max_llm_tokens": 100, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",))
    with request_scope(budget, module="model_signals", max_requests=1):
        result, operation = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result == {"items": []}
    assert operation["status"] == "available"
    assert budget.report()["llm_calls"] == 1
    assert budget.report()["outbound_requests"] == 1


def test_model_config_discovers_groq_key_pool(monkeypatch):
    for name in ("SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_API_KEY", "OPENAI_API_KEYS",
                 "OPENAI_API_KEY", "AI_API_KEY", "SIGNALPOST_MODEL_ENDPOINT", "GROQ_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEYS", "groq-one, groq-two")
    config = ModelConfig.from_environment()
    assert config.credentials == ("groq-one", "groq-two")
    assert config.endpoint == "https://api.groq.com/openai/v1/chat/completions"
    assert config.model == "openai/gpt-oss-120b"


def test_model_config_supports_openai_primary_openrouter_and_groq_profiles(monkeypatch):
    for name in (
        "SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_API_KEY", "SIGNALPOST_MODEL_ENDPOINT",
        "SIGNALPOST_MODEL", "SIGNALPOST_MODEL_COST_PER_CALL_USD", "OPENAI_API_KEYS", "OPENAI_API_KEY",
        "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENROUTER_API_KEYS", "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL", "OPENROUTER_MODEL", "GROQ_API_KEYS", "GROQ_API_KEY",
        "GROQ_BASE_URL", "GROQ_MODEL", "SIGNALPOST_MODEL_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("SIGNALPOST_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-fixture")
    monkeypatch.setenv("SIGNALPOST_MODEL_COST_PER_CALL_USD", "0.25")
    openai = ModelConfig.from_environment()
    assert openai.provider == "openai"
    assert openai.credentials == ("openai-fixture",)
    assert openai.endpoint == "https://api.openai.com/v1/chat/completions"
    assert openai.model == "gpt-5.6-sol"
    monkeypatch.setenv("SIGNALPOST_MODEL_COST_PER_CALL_USD", "")
    assert not ModelConfig.from_environment().configured
    monkeypatch.setenv("SIGNALPOST_MODEL_COST_PER_CALL_USD", "0.25")

    monkeypatch.setenv("SIGNALPOST_MODEL_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-fixture")
    openrouter = ModelConfig.from_environment()
    assert openrouter.provider == "openrouter"
    assert openrouter.credentials == ("openrouter-fixture",)
    assert openrouter.endpoint == "https://openrouter.ai/api/v1/chat/completions"
    assert openrouter.model == "openai/gpt-5.6-sol"

    monkeypatch.setenv("SIGNALPOST_MODEL_PROVIDER", "groq")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY", "groq-fixture")
    monkeypatch.delenv("SIGNALPOST_MODEL_COST_PER_CALL_USD")
    groq = ModelConfig.from_environment()
    assert groq.provider == "groq"
    assert groq.credentials == ("groq-fixture",)
    assert groq.model == "openai/gpt-oss-120b"
    assert groq.reservation_cost_usd(4000) > 0

    conflict = ModelConfig(
        api_key="openai-fixture", endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="gpt-5.6-sol", provider="openai", cost_per_call_usd=0.25,
    )
    assert not conflict.configured


def test_groq_gpt_oss_published_price_is_used_when_no_override_is_set():
    config = ModelConfig(
        api_key="test", endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="openai/gpt-oss-120b", max_output_tokens=1200,
    )
    assert config.reservation_cost_usd(4000) == (4000 * 0.15 + 1200 * 0.60) / 1_000_000


def test_model_client_rotates_after_provider_rate_limit(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return json.dumps({"choices": [{"message": {"content": '{"items": []}'}}]}).encode()

    requests = []
    rate_limited = urllib.error.HTTPError(
        "https://model.example/v1/chat/completions", 429, "Too Many Requests",
        {"Retry-After": "1"}, io.BytesIO(b"rate limited")
    )

    def urlopen(request, timeout):
        requests.append(request)
        if len(requests) == 1:
            raise rate_limited
        return Response()

    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open", urlopen)
    config = ModelConfig(api_key="key-one", api_keys=("key-two",),
                         endpoint="https://model.example/v1/chat/completions", model="test-model",
                         max_output_tokens=10)
    budget = RunBudget(max_requests=2, governor=type("Governor", (), {
        "max_llm_calls": 2, "max_llm_tokens": 1000, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",), model_keys=config.credentials,
                       model_requests_per_key=1000)
    with request_scope(budget, module="model_signals", max_requests=2):
        result, operation = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result == {"items": []}
    assert operation["attempts"] == 2
    assert [request.get_header("Authorization") for request in requests] == [
        "Bearer key-one", "Bearer key-two"
    ]
    assert budget.report()["outbound_requests"] == 2


def test_groq_rate_limit_is_provider_wide_and_does_not_fail_over_to_another_key(monkeypatch):
    error = urllib.error.HTTPError(
        "https://api.groq.com/openai/v1/chat/completions", 429, "Too Many Requests",
        {"retry-after": "10"}, io.BytesIO(b"rate limited")
    )
    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open", lambda request, timeout: (_ for _ in ()).throw(error))
    config = ModelConfig(
        api_key="key-one", api_keys=("key-two",),
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="openai/gpt-oss-120b", max_output_tokens=10,
    )
    budget = RunBudget(max_requests=2, governor=type("Governor", (), {
        "max_llm_calls": 2, "max_llm_tokens": 100, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",), model_keys=config.credentials)
    with request_scope(budget, module="model_signals", max_requests=2):
        result, operation = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
        second, cooldown = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result is None
    assert second is None and cooldown["attempts"] == 0
    assert operation["provider_scope"] == "organization"
    assert operation["attempts"] == 1
    assert budget.report()["outbound_requests"] == 1


def test_model_http_failure_keeps_bounded_provider_diagnostics(monkeypatch):
    error = urllib.error.HTTPError(
        "https://model.example/v1/chat/completions", 400, "Bad Request",
        {"X-Request-ID": "request-123", "Retry-After": "4"},
        io.BytesIO(b'{"error":{"code":"invalid_request","message":"private body"}}'),
    )
    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open",
                        lambda request, timeout: (_ for _ in ()).throw(error))
    config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions",
                         model="test-model", max_output_tokens=10)
    budget = RunBudget(max_requests=1, governor=type("Governor", (), {
        "max_llm_calls": 1, "max_llm_tokens": 100, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",))
    with request_scope(budget, module="model_signals", max_requests=1):
        result, operation = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result is None
    assert operation["provider_status"] == 400
    assert operation["provider_request_id"] == "request-123"
    assert operation["provider_error_code"] == "invalid_request"
    assert operation["retry_after_seconds"] == 4
    assert operation["provider_body_sample_bytes"] > 0
    assert "private body" not in json.dumps(operation)


def test_groq_request_uses_provider_json_mode_and_completion_token_field(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b'{"choices":[{"message":{"content":"{\\"items\\":[]}"}}]}'

    captured = {}

    def urlopen(request, timeout):
        captured.update(json.loads(request.data))
        return Response()

    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open", urlopen)
    config = ModelConfig(
        api_key="test", endpoint="https://api.groq.com/openai/v1/chat/completions",
        model="openai/gpt-oss-120b", max_output_tokens=10,
    )
    budget = RunBudget(max_requests=1, governor=type("Governor", (), {
        "max_llm_calls": 1, "max_llm_tokens": 100, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",))
    with request_scope(budget, module="model_signals", max_requests=1):
        result, _ = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result == {"items": []}
    assert captured["max_completion_tokens"] == 10
    assert "max_tokens" not in captured
    assert captured["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "provider,model,referer,expected_referer",
    [("openai", "gpt-5.6-sol", "", None),
     ("openrouter", "openai/gpt-5.6-sol", "https://github.com/nomadrai/signalpost", "https://github.com/nomadrai/signalpost")],
)
def test_openai_family_requests_use_json_completion_contract(monkeypatch, provider, model, referer, expected_referer):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b'{"choices":[{"message":{"content":"{\\"items\\":[]}"}}]}'

    captured = {}

    def urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["referer"] = request.headers.get("Http-referer")
        return Response()

    monkeypatch.setattr("norway_company_agent.llm.PROVIDER_OPENER.open", urlopen)
    config = ModelConfig(
        api_key="test", endpoint="https://model.example/v1/chat/completions", model=model,
        provider=provider, max_output_tokens=10, cost_per_call_usd=0.1,
        openrouter_http_referer=referer,
    )
    budget = RunBudget(max_requests=1, governor=type("Governor", (), {
        "max_llm_calls": 1, "max_llm_tokens": 100, "max_search_calls": 0, "max_cost_usd": 1.0
    })(), modules=("model_signals",))
    with request_scope(budget, module="model_signals", max_requests=1):
        result, _ = ModelClient(config, budget).complete_json(system="Return JSON", user="{}")
    assert result == {"items": []}
    assert captured["body"]["max_completion_tokens"] == 10
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert "max_tokens" not in captured["body"]
    assert captured["referer"] == expected_referer


def test_planner_rejects_unapproved_urls_and_accepts_exact_candidates():
    profile = {"organisation_number": ORG, "name": "Example AS", "municipality": "Oslo"}
    candidates = [{"url": "https://example.no/", "source": "registry_snapshot"}]
    assert validate_action({"action": "fetch_url", "url": "https://attacker.example/"}, profile, candidates)["status"] == "rejected"
    assert validate_action({"action": "search_company", "query": "Example AS"}, profile, candidates)["status"] == "rejected"
    accepted = validate_action({"action": "fetch_url", "url": "https://example.no/", "reason": "registry candidate"}, profile, candidates)
    assert accepted == {
        "status": "accepted", "action": "fetch_url", "url": "https://example.no/",
        "source": "registry_snapshot", "reason": "registry candidate",
    }


def test_planner_returns_bounded_action_without_publishing_claims():
    class PlannerStub:
        config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions", model="planner-model")

        def complete_json(self, *, system: str, user: str):
            assert "allowed_candidates" in user
            return {"action": "fetch_url", "url": "https://example.no/", "reason": "exact registry candidate"}, {
                "status": "available", "model": "planner-model", "reserved_tokens": 80,
            }

    profile = {"organisation_number": ORG, "name": "Example AS", "website": "https://example.no/"}
    result = plan_next_action(profile, PlannerStub())
    assert result["planner"]["status"] == "available"
    assert result["planner"]["value"]["action"]["url"] == "https://example.no/"
    assert "claims" not in result["planner"]["value"]


def test_planner_search_result_is_deterministically_gated(monkeypatch):
    class PlannerStub:
        config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions", model="planner-model")
        budget = object()

        def complete_json(self, *, system: str, user: str):
            return {
                "action": "search_company",
                 "query": '"Example AS" 993578843 Oslo',
                "reason": "registry website is absent",
            }, {"status": "available", "model": "planner-model"}

    monkeypatch.setattr(
        "norway_company_agent.planner.search_company",
        lambda profile, budget, query=None: ([{
            "url": "https://example.no/", "title": "Example AS",
            "snippet": "993578843", "rank": 1, "provider": "brave_search_api",
        }], {"status": "available", "candidate_count": 1, "raw": "must not persist"}),
    )
    profile = {"organisation_number": ORG, "name": "Example AS", "municipality": "Oslo"}
    result = plan_next_action(profile, PlannerStub())
    action = result["planner"]["value"]["action"]
    assert action["candidate_url"] == "https://example.no/"
    assert action["candidate_urls"] == ["https://example.no/"]
    assert "raw" not in result["planner"]["value"]["search"]


def test_planner_retains_bounded_search_url_frontier_only(monkeypatch):
    class PlannerStub:
        config = ModelConfig(api_key="test", endpoint="https://model.example/v1/chat/completions", model="planner-model")
        budget = object()

        def complete_json(self, *, system: str, user: str):
            return {"action": "search_company", "query": '"Example AS" 993578843 Oslo'}, {"status": "available", "model": "planner-model"}

    monkeypatch.setattr(
        "norway_company_agent.planner.search_company",
        lambda profile, budget, query=None: ([
            {"url": "https://brand.example/", "title": "Example AS", "snippet": "993578843", "rank": 1, "provider": "fixture", "query": "secret"},
            {"url": "https://second.example/", "title": "Example AS", "snippet": "993578843", "rank": 2, "provider": "fixture", "query": "secret"},
        ], {"status": "available", "candidate_count": 2}),
    )
    result = plan_next_action(
        {"organisation_number": ORG, "name": "Example AS", "municipality": "Oslo"},
        PlannerStub(),
    )
    action = result["planner"]["value"]["action"]
    assert action["candidate_urls"] == ["https://brand.example/", "https://second.example/"]
    assert "secret" not in json.dumps(result)
