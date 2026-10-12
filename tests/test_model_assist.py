from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norway_company_agent.budget import RunBudget, request_scope  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.llm import ModelClient, ModelConfig  # noqa: E402
from norway_company_agent.model_signals import extract_model_signals  # noqa: E402
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

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
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
