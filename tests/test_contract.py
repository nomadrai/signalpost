from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from norway_company_agent.batch import read_organisation_inputs, valid_norwegian_organisation_number  # noqa: E402
from norway_company_agent.budget import BudgetGovernor  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.sampling import iter_bulk  # noqa: E402
from norway_company_agent.schema import build_contract_envelope, stable_claim_id  # noqa: E402
from norway_company_agent.viewer import build_viewer  # noqa: E402
from audit_batch_checkpoint import audit_checkpoint  # noqa: E402
from run_batch import recover_checkpoint  # noqa: E402


VALID_ORG = "993578843"


def _profile() -> dict:
    registry = evidence(
        "registry",
        "available",
        "official_registry_bulk",
        "https://registry.example/entity/993578843",
        value={"navn": "Example AS"},
        content_sha256="a" * 64,
        source_row_key=VALID_ORG,
        retrieved_at="2026-10-02T00:00:00Z",
    )
    return {
        "organisation_number": VALID_ORG,
        "name": "Example AS",
        "legal_form": "AS",
        "employees": 0,
        "municipality": "OSLO",
        "evidence": {
            "registry": registry,
            "accounting_obligation": evidence("accounting_obligation", "available", "official_rule", "https://registry.example/rules", value={"classification": "required_by_legal_form"}),
        },
    }


def test_zero_budget_governor_abstains_without_consuming():
    governor = BudgetGovernor()
    assert not governor.reserve_llm(20, 0.01)
    assert not governor.reserve_search()
    assert governor.report()["cost_usd"] == 0.0


def test_mod11_accepts_known_value_and_rejects_bad_check_digit():
    assert valid_norwegian_organisation_number(VALID_ORG)
    assert not valid_norwegian_organisation_number(VALID_ORG[:-1] + "4")
    with pytest.raises(ValueError, match="checksum"):
        read_organisation_inputs(_write_text("123456789\n"))


def _write_text(text: str) -> Path:
    path = ROOT.parent / "runs" / "test-contract-input.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_iter_bulk_accepts_plain_csv(tmp_path: Path):
    path = tmp_path / "registry.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["organisasjonsnummer", "navn"], delimiter=";")
        writer.writeheader()
        writer.writerow({"organisasjonsnummer": VALID_ORG, "navn": "Example AS"})
    rows = list(iter_bulk(path))
    assert rows[0]["organisation_number"] == VALID_ORG
    assert rows[0]["name"] == "Example AS"


def test_contract_has_stable_claims_snapshots_and_unknowns():
    first = build_contract_envelope(_profile(), run_id="run-1", started_at="2026-10-02T00:00:00Z", completed_at="2026-10-02T00:00:01Z", requested_modules=["registry", "website"])
    second = build_contract_envelope(_profile(), run_id="run-2", started_at="2026-10-03T00:00:00Z", completed_at="2026-10-03T00:00:01Z", requested_modules=["registry", "website"])
    assert first["status"] == "available"
    assert first["claims"]
    assert first["claims"] == [{**claim, "retrieved_at": claim["retrieved_at"]} for claim in second["claims"]]
    assert first["snapshots"]
    assert first["synthesis"]["unknowns"]
    assert stable_claim_id(VALID_ORG, "identity.name", "Example AS", "source") == stable_claim_id(VALID_ORG, "identity.name", "Example AS", "source")


def test_batch_runner_emits_one_available_row_at_zero_deadline(tmp_path: Path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(VALID_ORG + "\n", encoding="utf-8")
    bulk_path = tmp_path / "registry.csv"
    with bulk_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["organisasjonsnummer", "navn", "organisasjonsform.kode", "antallAnsatte"], delimiter=";")
        writer.writeheader()
        writer.writerow({"organisasjonsnummer": VALID_ORG, "navn": "Example AS", "organisasjonsform.kode": "AS", "antallAnsatte": "0"})
    output = tmp_path / "envelopes.jsonl"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_batch.py"),
        "--input",
        str(input_path),
        "--bulk",
        str(bulk_path),
        "--profiles-output",
        str(tmp_path / "profiles.jsonl"),
        "--output",
        str(output),
        "--report",
        str(tmp_path / "report.json"),
        "--run-id",
        "test-run",
    ]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "RUN_DEADLINE_SECONDS": "0"}
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert "\"passed\": true" in result.stdout
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["organisation_number"] == VALID_ORG
    assert rows[0]["status"] == "available"
    assert rows[0]["errors"][0]["code"] == "deadline_pass2_skipped"


def test_batch_report_attributes_zero_request_local_signal_work(tmp_path: Path):
    input_path = tmp_path / "input.txt"
    input_path.write_text(VALID_ORG + "\n", encoding="utf-8")
    bulk_path = tmp_path / "universe.jsonl"
    bulk_path.write_text(json.dumps({"organisation_number": VALID_ORG, "name": "Example AS", "legal_form": "AS"}) + "\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_batch.py"),
        "--input", str(input_path),
        "--bulk", str(bulk_path),
        "--profiles-output", str(tmp_path / "profiles.jsonl"),
        "--output", str(tmp_path / "envelopes.jsonl"),
        "--report", str(report_path),
        "--run-id", "local-attribution",
        "--modules", "registry_live,hiring,activity",
        "--max-requests", "0",
        "--deadline-seconds", "15",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["validation"]["passed"] is True
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["module_operations"]["hiring"]["local_tasks"] == 1
    assert report["module_operations"]["activity"]["local_tasks"] == 1
    assert report["module_operations"]["hiring"]["requests"] == 0
    assert report["request_attribution"]["reconciled"] is True


def test_viewer_escapes_fetched_text_and_builds_compare_and_changes(tmp_path: Path):
    row = build_contract_envelope(_profile(), run_id="run-1", started_at="2026-10-02T00:00:00Z", completed_at="2026-10-02T00:00:01Z", requested_modules=["registry"])
    row["identity"]["name"] = "<img src=x onerror=alert(1)>"
    row["claims"][0]["value"] = "<script>alert(1)</script>"
    source = tmp_path / "envelopes.jsonl"
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out = tmp_path / "viewer"
    report = build_viewer(source, out)
    assert report["profiles"] == 1
    index = (out / "index.html").read_text(encoding="utf-8")
    profile = (out / f"company-{VALID_ORG}.html").read_text(encoding="utf-8")
    assert "<img src=x onerror=alert(1)>" not in index
    assert "&lt;img src=x onerror=alert(1)&gt;" in index
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in profile
    assert (out / "compare.html").exists()
    assert (out / "changes.html").exists()
    assert "src=\"http" not in index
    assert "—" not in index
    assert "—" not in profile
    assert "signalpost-data" not in profile
    assert "Ask about this company" in profile
    assert "View evidence record" in profile
    assert "max-width: 1380px" in index


def test_validate_evidence_preserves_unicode_line_separators_in_jsonl(tmp_path: Path):
    row = build_contract_envelope(_profile(), run_id="unicode", started_at="2026-10-02T00:00:00Z",
                                  completed_at="2026-10-02T00:00:01Z", requested_modules=["registry"])
    row["claims"][0]["value"] = "captured page text\u2028with a separator"
    source = tmp_path / "envelopes.jsonl"
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_evidence.py"), str(source)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["passed"] is True


def test_supervisor_recovery_reads_unicode_line_separators_in_jsonl(tmp_path: Path):
    row = build_contract_envelope(_profile(), run_id="recovery", started_at="2026-10-02T00:00:00Z",
                                  completed_at="2026-10-02T00:00:01Z", requested_modules=["registry"])
    row["claims"][0]["value"] = "captured page text\u2028with a separator"
    output = tmp_path / "envelopes.jsonl"
    output.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    inputs = tmp_path / "organisations.txt"
    inputs.write_text(VALID_ORG + "\n", encoding="utf-8")
    args = SimpleNamespace(
        output=str(output),
        input=str(inputs),
        organisations=None,
        profiles_output=str(tmp_path / "profiles.jsonl"),
        report=str(tmp_path / "report.json"),
        run_id="recovery",
    )
    recover_checkpoint(args, time.monotonic())
    recovered = json.loads(output.read_text(encoding="utf-8").split("\n")[0])
    assert recovered["organisation_number"] == VALID_ORG
    assert recovered["claims"][0]["value"] == "captured page text\u2028with a separator"


def test_checkpoint_audit_validates_complete_output_without_reconstructing_report(tmp_path: Path):
    row = build_contract_envelope(_profile(), run_id="audit", started_at="2026-10-02T00:00:00Z",
                                  completed_at="2026-10-02T00:00:01Z", requested_modules=["registry"])
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(json.dumps({"organisation_number": VALID_ORG}) + "\n", encoding="utf-8")
    envelopes_path = tmp_path / "envelopes.jsonl"
    envelopes_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    ledger_path = tmp_path / "envelopes.jsonl.budget.jsonl"
    ledger_path.write_text(json.dumps({"run_id": "audit", "outbound_requests": 7,
                                       "remaining_outbound_requests": 1993, "cost_usd": 0.0}) + "\n",
                           encoding="utf-8")
    universe_path = tmp_path / "universe.jsonl"
    universe_path.write_text(json.dumps({"organisation_number": VALID_ORG, "name": "Example AS"}) + "\n",
                             encoding="utf-8")
    result = audit_checkpoint(input_path, envelopes_path, ledger_path, universe_path)
    assert result["validation"]["passed"] is True
    assert result["input_output_match"] is True
    assert result["reserved_outbound_requests"] == 7
    assert result["final_report_present"] is False
    assert result["classification"] == "complete terminal checkpoint audit; not a final run report"
