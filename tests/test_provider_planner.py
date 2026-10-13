from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import threading
import tempfile
import urllib.parse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.budget import BudgetGovernor, DailyCostLedger, RunBudget, request_scope, reserve_http_attempt
from norway_company_agent.evidence import evidence
from norway_company_agent.firecrawl import search_company
from norway_company_agent.llm import ModelClient, ModelConfig
from norway_company_agent.planner import validate_action


def _reserve_in_process(path):
    ledger = DailyCostLedger(path, max_cost_usd=0.05)
    return ledger.reserve(0.01, key="fixture-key")


def test_daily_cap_survives_independent_process_reservations(tmp_path):
    path = str(tmp_path / "daily.json")
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        assert sum(pool.map(_reserve_in_process, [path] * 20)) == 5
    state = json.loads(Path(path).read_text())
    assert state["cost_microdollars"] == 50000
    assert state["requests"] == 5


def test_daily_ledger_validates_before_rollover_and_zero_denies_paid_calls(tmp_path, monkeypatch):
    path = tmp_path / "daily.json"
    ledger = DailyCostLedger(str(path), max_cost_usd=1)
    monkeypatch.setattr(DailyCostLedger, "_day", staticmethod(lambda: "2026-10-13"))
    assert ledger.reserve(1, key="fixture-key")
    assert not ledger.reserve(0.01)
    stored = path.read_text()
    for corruption in ({}, {**json.loads(stored), "day": "bad"},
                       {**json.loads(stored), "cost_microdollars": -1},
                       {**json.loads(stored), "requests": True},
                       {**json.loads(stored), "day": "2026-10-14"}):
        path.write_text(json.dumps(corruption))
        assert not ledger.reserve(0.01)
        assert json.loads(path.read_text()) == corruption
    path.write_text(stored)
    monkeypatch.setattr(DailyCostLedger, "_day", staticmethod(lambda: "2026-10-14"))
    assert ledger.reserve(0.25)
    assert ledger.report()["cost_usd"] == 0.25
    assert not DailyCostLedger(str(tmp_path / "zero.json"), max_cost_usd=0).reserve(0.01)


def test_provider_namespaces_do_not_share_credentials(monkeypatch):
    for name in ("SIGNALPOST_MODEL_API_KEY", "SIGNALPOST_MODEL_API_KEYS", "SIGNALPOST_MODEL_ENDPOINT",
                 "GROQ_API_KEY", "GROQ_BASE_URL", "OPENAI_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEYS", "groq-fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-fixture")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/v1")
    config = ModelConfig.from_environment()
    assert config.credentials == ("groq-fixture",)
    assert config.endpoint == "https://api.groq.com/openai/v1/chat/completions"
    assert "groq-fixture" not in repr(config)


def test_malformed_planner_actions_never_open_arbitrary_urls():
    profile = {"name": "Example AS", "organisation_number": "993578843"}
    candidates = [{"url": "https://example.no/", "source": "registry_snapshot"}]
    for action in (["fetch_url"], {"action": []}, {"action": "fetch_url", "url": "https://[invalid"},
                   {"action": "fetch_url", "url": "http://127.0.0.1/"},
                   {"action": "search_company", "query": "Example AS 19935788430"}):
        assert validate_action(action, profile, candidates)["status"] == "rejected"


def test_firecrawl_keyless_search_uses_no_auth_header_and_discards_result_shape(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return json.dumps({"success": True, "data": {"web": [{
                "url": "https://example.no/", "title": "Example AS",
                "description": "transient snippet", "position": 1,
            }]}, "creditsUsed": 2}).encode()

    captured = {}

    def open_provider(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("norway_company_agent.firecrawl.PROVIDER_OPENER.open", open_provider)
    monkeypatch.setattr("norway_company_agent.firecrawl.FIRECRAWL_ENDPOINT", "http://127.0.0.1:9/search")
    ledger = str(Path(tempfile.mkdtemp(prefix="firecrawl-test-")) / "daily.json")
    budget = RunBudget(max_requests=1, governor=BudgetGovernor(
        max_llm_calls=0, max_llm_tokens=0, max_search_calls=1, max_cost_usd=1,
        daily_cost_cap_usd=1, daily_cost_ledger_path=ledger), modules=("planner",))
    profile = {"organisation_number": "993578843", "name": "Example AS", "municipality": "Oslo"}
    with request_scope(budget, module="planner", max_requests=1):
        results, operation = search_company(profile, budget, count=3)
    assert operation["status"] == "available"
    assert operation["credits_used"] == 2
    assert results[0]["url"] == "https://example.no/"
    assert captured["authorization"] is None
    assert captured["body"]["country"] == "NO"
    assert results[0]["provider"] == "firecrawl_search_api"


@pytest.fixture
def provider_server():
    counts = Counter()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_POST(self):
            counts[self.path] += 1
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/credential-leak")
                self.end_headers()
                return
            if self.path == "/search":
                self.send_json({"success": True, "data": {"web": [{
                    "url": "https://example.no/", "title": "Example AS",
                    "description": "993578843 transient-only-marker", "position": 1,
                }]}, "creditsUsed": 2})
                return
            if body["model"] == "fetch-fixture":
                action = {"action": "fetch_url", "url": "https://example.no/"}
            else:
                action = {"action": "search_company", "query": '"Example AS" 993578843'}
            self.send_json({"choices": [{"message": {"content": json.dumps(action)}}]})

        def do_GET(self):
            counts[urllib.parse.urlsplit(self.path).path] += 1
            self.send_json({"web": {"results": [{
                "url": "https://example.no/", "title": "Example AS",
                "description": "993578843 transient-only-marker",
            }]}})

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provider_redirect_is_not_followed_or_given_credentials(provider_server):
    base, counts = provider_server
    config = ModelConfig("fixture", base + "/redirect", "fixture", max_output_tokens=10)
    budget = RunBudget(max_requests=2, governor=BudgetGovernor(max_llm_calls=2, max_llm_tokens=1000))
    with request_scope(budget):
        result, operation = ModelClient(config, budget).complete_json(system="JSON", user="{}")
    assert result is None and operation["reason"] == "http_302"
    assert counts == {"/redirect": 1}
    assert budget.requests.value == 1


def configure_runner_fixture(base, mode):
    """Real local model/search HTTP with an independently gated page fixture."""
    from norway_company_agent import firecrawl, enrichment
    firecrawl.FIRECRAWL_ENDPOINT = base + "/search"

    def capture(url, **kwargs):
        assert url == "https://example.no/"
        reserve_http_attempt(url)
        owner = "987654325" if mode == "wrong-owner" else "993578843"
        text = f"Example AS org {owner}"
        return evidence("website", "available", "fixture_page", url,
                        value={"title": "Example AS", "identity_text_excerpt": text,
                               "candidate_source": kwargs["candidate_source"], "final_url": url},
                        content_sha256=hashlib.sha256(text.encode()).hexdigest()), {"bytes": 100}

    enrichment.fetch_website = capture
    if mode == "worker-error":
        def fail(*args, **kwargs):
            raise RuntimeError("fixture planner failed")
        enrichment.plan_next_action = fail


@pytest.mark.parametrize("mode", ["search", "fetch", "wrong-owner", "worker-error"])
def test_runner_executes_planner_candidates_and_preserves_identity_gate(tmp_path, provider_server, mode):
    base, counts = provider_server
    inputs = tmp_path / "input.jsonl"
    bulk = tmp_path / "bulk.jsonl"
    inputs.write_text('{"organisation_number":"993578843"}\n')
    bulk.write_text('{"organisation_number":"993578843","name":"Example AS","legal_form":"AS"}\n')
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from scripts import run_batch_impl\n"
        "from test_provider_planner import configure_runner_fixture\n"
        "if __name__ == '__main__':\n"
        f"    configure_runner_fixture({base!r}, {mode!r})\n"
        "    run_batch_impl.main()\n"
    )
    environment = {**os.environ,
                   "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src"), str(ROOT / "tests"))),
                   "SIGNALPOST_MODEL_API_KEY": "fixture-model-secret",
                   "SIGNALPOST_MODEL_API_KEYS": "",
                   "SIGNALPOST_MODEL_ENDPOINT": base + "/chat/completions",
                   "SIGNALPOST_MODEL": "fetch-fixture" if mode == "fetch" else "search-fixture",
                   "SIGNALPOST_MODEL_COST_PER_CALL_USD": "0.02",
                   "FIRECRAWL_API_KEY": "fixture-search-secret", "FIRECRAWL_SEARCH_COST_PER_CALL_USD": "0.01",
                   "MAX_LLM_CALLS": "1", "MAX_LLM_TOKENS": "20000", "MAX_SEARCH_CALLS": "1", "MAX_COST_USD": "1",
                   "SIGNALPOST_DAILY_COST_CAP_USD": "1", "SIGNALPOST_DAILY_COST_LEDGER": str(tmp_path / "daily.json")}
    command = [sys.executable, str(driver), "--input", str(inputs), "--bulk", str(bulk),
               "--output", str(tmp_path / "envelopes.jsonl"), "--profiles-output", str(tmp_path / "profiles.jsonl"),
               "--report", str(tmp_path / "report.json"), "--run-id", "planner-fixture", "--modules", "registry",
               "--planner-assist", "--max-requests", "3", "--deadline-seconds", "15"]
    if mode == "fetch":
        command.append("--discover-websites")
    subprocess.run(command, env=environment, check=True, capture_output=True, timeout=20)
    report = json.loads((tmp_path / "report.json").read_text())
    row = json.loads((tmp_path / "envelopes.jsonl").read_text())
    assert report["validation"]["passed"]
    assert report["request_attribution"]["unattributed_requests"] == 0
    assert row["sections"]["website"]["state"] == (
        "ambiguous" if mode == "wrong-owner" else "not_available" if mode == "worker-error" else "available")
    if mode == "worker-error":
        assert report["module_operations"]["planner"]["failed_tasks"] == 1
        assert counts == {}
        return
    assert counts == ({"/chat/completions": 1} if mode == "fetch" else {"/chat/completions": 1, "/search": 1})
    expected_requests = 2 if mode == "fetch" else 3
    assert report["operations"]["requests"] == expected_requests
    assert report["budget"]["daily"]["cost_usd"] == (0.02 if mode == "fetch" else 0.03)
    for path in (tmp_path / "profiles.jsonl", tmp_path / "envelopes.jsonl", tmp_path / "report.json", tmp_path / "daily.json"):
        text = path.read_text()
        assert "fixture-model-secret" not in text and "fixture-search-secret" not in text
        assert "transient-only-marker" not in text
    subprocess.run(command + ["--resume"], env=environment, check=True, capture_output=True, timeout=20)
    resumed = json.loads((tmp_path / "report.json").read_text())
    assert resumed["operations"]["requests"] == 0
    assert resumed["budget"]["outbound_requests"] == expected_requests
