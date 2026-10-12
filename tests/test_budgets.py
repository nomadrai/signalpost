from __future__ import annotations

import gzip
import json
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import profiles_from_bulk, terminal_envelope
from norway_company_agent.budget import BudgetGovernor, RunBudget, request_scope
from norway_company_agent.http import fetch_json
from norway_company_agent.sampling import iter_bulk
from norway_company_agent.workers import BoundedWorkers


ORG = "993578843"


@pytest.fixture
def server():
    counts = Counter()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                counts[self.path] += 1
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/ok")
                self.end_headers()
                return
            self.send_response(503 if self.path == "/retry" else 200)
            self.send_header("Content-Type", "text/plain" if self.path == "/robots.txt" else "application/json")
            self.end_headers()
            self.wfile.write(b"User-agent: *\nAllow: /\n" if self.path == "/robots.txt" else b'{"ok":true}')

        def log_message(self, *_):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}", counts
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def test_redirects_and_retries_are_charged_before_every_attempt(server, monkeypatch):
    url, counts = server
    # Avoid retry backoff while testing transport attempts.
    monkeypatch.setattr("norway_company_agent.http.bounded_sleep", lambda _: None)
    budget = RunBudget(max_requests=4)
    with request_scope(budget):
        assert fetch_json(url + "/redirect").status == 200
        result = fetch_json(url + "/retry")
        assert result.budget_exhausted
        assert fetch_json(url + "/ok").budget_exhausted
    assert counts == {"/redirect": 1, "/ok": 1, "/retry": 2}
    assert budget.report()["outbound_requests"] == 4


def test_request_reservations_attribute_attempts_to_the_active_module(server):
    url, _ = server
    budget = RunBudget(max_requests=2, modules=("website", "financials"))
    with request_scope(budget, module="website"):
        assert fetch_json(url + "/ok", attempts=1).status == 200
    with request_scope(budget, module="financials"):
        assert fetch_json(url + "/ok", attempts=1).status == 200
    assert budget.module_requests[budget.module_indices["website"]] == 1
    assert budget.module_requests[budget.module_indices["financials"]] == 1
    assert budget.unattributed_requests.value == 0


def test_robots_requests_use_the_shared_gate(server, monkeypatch):
    from norway_company_agent.website import _robots_allowed
    url, counts = server
    monkeypatch.setattr("norway_company_agent.website.assert_public_url", lambda _: None)
    budget = RunBudget(max_requests=1)
    with request_scope(budget):
        assert _robots_allowed(url + "/ok", 2)
        assert fetch_json(url + "/ok").budget_exhausted
    assert counts == {"/robots.txt": 1}


def test_homepage_is_preserved_when_secondary_crawl_budget_is_exhausted(server, monkeypatch):
    from norway_company_agent.website import fetch_website
    monkeypatch.setattr("norway_company_agent.website.assert_public_url", lambda _: None)
    # Use a real HTML response from a tiny dedicated server.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'User-agent: *\nAllow: /' if self.path == "/robots.txt" else
                             b'<html><title>Example AS</title><body><p>Example AS organisation 993578843.</p><a href="/contact">Contact</a></body></html>')

        def log_message(self, *_):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    budget = RunBudget(max_requests=2)
    try:
        with request_scope(budget):
            record, _ = fetch_website(f"http://127.0.0.1:{instance.server_port}/")
        assert record["status"] == "available"
        assert record["value"]["title"] == "Example AS"
        assert len(record["value"]["pages"]) == 1
        assert record["value"]["crawl_errors"][0]["error"] == "outbound_request_cap"
        assert budget.requests.value == 2
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def _history_task(task, budget):
    delay = budget.reserve_history_start()
    return time.monotonic() + delay


def test_history_rate_slots_are_shared_across_workers_without_holding_transport_lock():
    budget = RunBudget()
    pool = BoundedWorkers(_history_task, budget, 3)
    try:
        for _ in range(3):
            pool.submit({}, 10)
        results = []
        expires = time.monotonic() + 10
        while pool.active and time.monotonic() < expires:
            results.extend(pool.poll())
        assert len(results) == 3
        assert all(ok for _, ok, _ in results)
        starts = sorted(value for _, _, value in results)
        assert starts[1] - starts[0] >= 2.09
        assert starts[2] - starts[1] >= 2.09
    finally:
        pool.close()
    budget.reserve_request()
    assert budget.requests.value == 1


def _fetch_task(task, budget):
    with request_scope(budget, company_index=0):
        return fetch_json(task["url"], attempts=1).status


def _hang_task(task, shared):
    time.sleep(60)
    return "late"


def _hang_after_reservation(task, shared):
    budget, _ = shared
    budget.reserve_request(task["company_index"])
    time.sleep(60)


def _serve_one(task, shared):
    from norway_company_agent.evidence import evidence
    budget, _ = shared
    with request_scope(budget, company_index=task["company_index"], deadline=task["deadline"]) as scope:
        result = fetch_json(task["profile"]["website"], attempts=1)
        record = evidence(task["module"], "available", "test_response", result.url, value={"records": []}, content_sha256=result.content_sha256)
    return {"records": {task["module"]: record}, "metric": {"requests": scope.requests, "bytes": result.bytes_received}}


def test_resume_preserves_nonzero_request_usage_and_elapsed_time(tmp_path, server):
    url, counts = server
    command = _command(tmp_path)
    source = tmp_path / "universe.jsonl"
    row = json.loads(source.read_text())
    row["website"] = url + "/ok"
    source.write_text(json.dumps(row) + "\n")
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from scripts import run_batch_impl\n"
        "from test_budgets import _serve_one\n"
        "if __name__ == '__main__':\n"
        "    run_batch_impl.enrich_module = _serve_one\n"
        "    run_batch_impl.main()\n"
    )
    command[1] = str(driver)
    command += ["--modules", "registry,financials,roles", "--deadline-seconds", "15", "--max-requests", "1"]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src"), str(ROOT / "tests")))}
    subprocess.run(command, env=env, capture_output=True, check=True, timeout=20)
    first = json.loads((tmp_path / "report.json").read_text())
    assert first["budget"]["outbound_requests"] == 1
    subprocess.run(command + ["--resume"], env=env, capture_output=True, check=True, timeout=20)
    second = json.loads((tmp_path / "report.json").read_text())
    assert second["budget"]["outbound_requests"] == 1
    assert second["operations"]["requests"] == 0
    assert second["elapsed_seconds"] >= first["elapsed_seconds"]
    assert counts == {"/ok": 1}


def test_runner_reaps_inflight_work_and_accounts_for_discarded_results(tmp_path):
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from scripts import run_batch_impl\n"
        "from test_budgets import _hang_after_reservation\n"
        "if __name__ == '__main__':\n"
        "    run_batch_impl.enrich_module = _hang_after_reservation\n"
        "    run_batch_impl.main()\n"
    )
    command = _command(tmp_path)
    command[1] = str(driver)
    command += ["--modules", "registry,financials", "--deadline-seconds", "3"]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src"), str(ROOT / "tests"))),
                   "RUN_DEADLINE_SAFETY_SECONDS": "1"}
    started = time.monotonic()
    subprocess.run(command, env=environment, check=True, capture_output=True, timeout=4)
    assert time.monotonic() - started < 3
    report = json.loads((tmp_path / "report.json").read_text())
    row = json.loads((tmp_path / "envelopes.jsonl").read_text())
    assert report["operations"]["requests"] == 1
    assert row["operations"]["requests"] == 1
    assert row["status"] == "available"
    assert row["sections"]["accounts"]["reason"] == "run_deadline"
    assert row["modules"]["financials"]["state"] == "budget_exhausted"


def test_concurrent_process_exhaustion_cannot_overshoot(server):
    url, counts = server
    context = multiprocessing.get_context("spawn")
    budget = RunBudget(max_requests=17, companies=1, context=context)
    pool = BoundedWorkers(_fetch_task, budget, 4, context=context)
    results = []
    submitted = 0
    expires = time.monotonic() + 15
    try:
        while (submitted < 35 or pool.active) and time.monotonic() < expires:
            while submitted < 35 and pool.active < 4:
                pool.submit({"url": url + "/ok"}, 10)
                submitted += 1
            results.extend(pool.poll())
        assert len(results) == 35
        assert all(ok for _, ok, _ in results)
        assert sum(value == 200 for _, _, value in results) == 17
    finally:
        pool.close()
    assert sum(counts.values()) == 17
    assert budget.requests.value == budget.company_requests[0] == 17


def test_stuck_worker_is_killed_at_task_timeout_and_close_is_bounded():
    pool = BoundedWorkers(_hang_task, None, 2)
    started = time.monotonic()
    pool.submit({"org": ORG}, 0.3)
    pool.submit({"org": ORG}, 60)
    try:
        results = []
        while not results and time.monotonic() - started < 2:
            results = pool.poll()
        assert results[0][1:] == (False, "company_timeout")
    finally:
        incomplete = pool.close()
    assert len(incomplete) == 1
    assert time.monotonic() - started < 2


def test_search_and_model_cost_reservations_share_one_atomic_cap():
    budget = RunBudget(governor=BudgetGovernor(max_llm_calls=100, max_llm_tokens=1000,
                                             max_search_calls=100, max_cost_usd=1))
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(budget.reserve_search, .1) if i % 2 else executor.submit(budget.reserve_llm, 1, .1)
                   for i in range(100)]
        assert sum(future.result() for future in futures) == 10
    assert budget.report()["cost_usd"] == 1
    assert budget.report()["search_calls"] + budget.report()["llm_calls"] == 10
    with pytest.raises(ValueError):
        budget.reserve_search(float("nan"))


def test_daily_cost_ledger_is_shared_across_run_budget_instances(tmp_path):
    ledger = tmp_path / "daily-cost.json"
    governor = BudgetGovernor(
        max_llm_calls=10, max_llm_tokens=1000, max_search_calls=0, max_cost_usd=10,
        daily_cost_cap_usd=0.15, daily_cost_ledger_path=str(ledger),
        model_requests_per_key_per_day=2,
    )
    first = RunBudget(max_requests=10, governor=governor, model_keys=("key-one",))
    second = RunBudget(max_requests=10, governor=governor, model_keys=("key-one",))
    assert first.reserve_llm(1, 0.09, key_id="key-one")
    assert second.reserve_llm(1, 0.02, key_id="key-one")
    assert not first.reserve_llm(1, 0.01, key_id="key-one")  # per-key daily request cap
    assert second.reserve_llm(1, 0.01, key_id="key-two")
    assert not first.reserve_llm(1, 0.04, key_id="key-two")  # shared USD cap
    state = json.loads(ledger.read_text())
    assert state["cost_microdollars"] == 120000
    assert "key-one" not in ledger.read_text()
    assert first.report()["daily"]["remaining_cost_usd"] == pytest.approx(0.03)


def test_daily_cost_ledger_is_atomic_across_independent_budget_objects(tmp_path):
    ledger = tmp_path / "concurrent-daily-cost.json"
    governor = BudgetGovernor(
        max_llm_calls=2, max_llm_tokens=100, max_search_calls=0, max_cost_usd=1,
        daily_cost_cap_usd=0.05, daily_cost_ledger_path=str(ledger),
    )

    def reserve(_):
        budget = RunBudget(max_requests=2, governor=governor)
        return budget.reserve_llm(1, 0.01, key_id="independent")

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = list(executor.map(reserve, range(20)))
    assert sum(outcomes) == 5
    assert json.loads(ledger.read_text())["cost_microdollars"] == 50000


def test_daily_cost_ledger_fails_closed_when_state_is_malformed(tmp_path):
    ledger = tmp_path / "malformed-daily-cost.json"
    ledger.write_text("not-json")
    governor = BudgetGovernor(
        max_llm_calls=1, max_llm_tokens=100, max_search_calls=0, max_cost_usd=1,
        daily_cost_cap_usd=1, daily_cost_ledger_path=str(ledger),
    )
    budget = RunBudget(max_requests=1, governor=governor)
    assert not budget.reserve_llm(1, 0.01, key_id="secret")
    assert ledger.read_text() == "not-json"
    assert budget.report()["daily"]["status"] == "unreadable"


@pytest.mark.parametrize("compressed", [False, True])
def test_universe_snapshot_support_preserves_attribution_and_missing_values(tmp_path, compressed):
    source = tmp_path / ("universe.jsonl.gz" if compressed else "universe.jsonl")
    row = {"organisation_number": ORG, "name": "Example AS", "legal_form": "AS", "employees": None,
           "website": "", "latest_submitted_accounts": "2025"}
    raw = (json.dumps(row) + "\n").encode()
    source.write_bytes(gzip.compress(raw) if compressed else raw)
    assert list(iter_bulk(source))[0]["employees"] is None
    profiles, metadata = profiles_from_bulk(source, [ORG])
    envelope = terminal_envelope(profiles[0], run_id="test", modules=["registry"], started_at="now", completed_at="now")
    registry = profiles[0]["evidence"]["registry"]
    assert registry["source_type"] == "local_company_universe"
    assert registry["source_url"] == "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz"
    assert registry["content_sha256"] == metadata["registry_snapshot_sha256"]
    assert not any(claim["field"].startswith("accounts.") for claim in envelope["claims"])
    assert not any(claim["field"] == "identity.employees" for claim in envelope["claims"])
    assert envelope["snapshots"][0]["http_status"] == 0
    assert envelope["snapshots"][0]["access_policy"] == "local-snapshot"


def _command(tmp_path, script="run_batch.py"):
    inputs = tmp_path / "input.jsonl"
    inputs.write_text(json.dumps({"organisation_number": ORG}) + "\n")
    bulk = tmp_path / "universe.jsonl"
    bulk.write_text(json.dumps({"organisation_number": ORG, "name": "Example AS", "legal_form": "AS"}) + "\n")
    return [sys.executable, str(ROOT / "scripts" / script), "--input", str(inputs), "--bulk", str(bulk),
            "--output", str(tmp_path / "envelopes.jsonl"), "--profiles-output", str(tmp_path / "profiles.jsonl"),
            "--report", str(tmp_path / "report.json"), "--run-id", "bounded-test"]


def test_saved_responses_enrich_at_zero_outbound_budget_and_resume_preserves_allowance(tmp_path):
    snapshot = tmp_path / "responses.json"
    snapshot.write_text(json.dumps({"retrieved_at": "2026-10-03T00:00:00Z", "responses": {
        f"https://data.brreg.no/regnskapsregisteret/regnskap/{ORG}": {"body": [{"valuta": "NOK", "regnskapsperiode": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"}, "resultatregnskapResultat": {"aarsresultat": 42}}]}
    }}))
    command = _command(tmp_path, "run_competition_batch.py") + ["--max-requests", "0", "--response-snapshot", str(snapshot), "--deadline-seconds", "15"]
    subprocess.run(command, check=True, capture_output=True, timeout=20)
    report = json.loads((tmp_path / "report.json").read_text())
    row = json.loads((tmp_path / "envelopes.jsonl").read_text())
    assert report["operations"]["requests"] == 0
    assert report["operations"]["snapshot_reads"] == 1
    assert next(claim for claim in row["claims"] if claim["field"] == "accounts.0.annual_result")["value"] == 42
    assert row["sections"]["leadership"]["reason"] == "outbound_request_cap"
    subprocess.run(command + ["--resume"], check=True, capture_output=True, timeout=20)
    resumed = json.loads((tmp_path / "report.json").read_text())
    assert resumed["budget"]["outbound_requests"] == 0
    assert resumed["operations"]["snapshot_reads"] == 0


def test_planner_assist_without_credentials_is_explicit_and_key_free(tmp_path):
    command = _command(tmp_path) + ["--planner-assist", "--max-requests", "0"]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src"), str(ROOT / "tests")))}
    for name in ("GROQ_API_KEY", "GROQ_API_KEYS", "SIGNALPOST_MODEL_API_KEY", "SIGNALPOST_MODEL_API_KEYS",
                 "OPENAI_API_KEY", "OPENAI_API_KEYS", "AI_API_KEY"):
        environment.pop(name, None)
    subprocess.run(command, env=environment, check=True, capture_output=True, timeout=20)
    report = json.loads((tmp_path / "report.json").read_text())
    row = json.loads((tmp_path / "envelopes.jsonl").read_text())
    assert "planner" in report["modules"]
    assert row["profile"]["evidence"]["planner"]["status"] == "not_fetched"
    assert row["profile"]["evidence"]["planner"]["note"] == "model_not_configured"
    assert report["validation"]["passed"]


def test_supervisor_bounds_entire_run_and_emits_terminal_rows(tmp_path):
    command = _command(tmp_path) + ["--deadline-seconds", "0.15"]
    started = time.monotonic()
    subprocess.run(command, check=True, capture_output=True, timeout=2)
    report = json.loads((tmp_path / "report.json").read_text())
    row = json.loads((tmp_path / "envelopes.jsonl").read_text())
    assert time.monotonic() - started < 1
    assert report["supervisor_stopped"]
    assert row["organisation_number"] == ORG
    assert row["status"] == "failed"
    assert row["errors"][0]["code"] == "supervisor_deadline"
