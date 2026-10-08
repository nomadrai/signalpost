#!/usr/bin/env python3
"""Audit a bounded batch checkpoint without resuming or making network calls."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import read_organisation_inputs, validate_envelopes  # noqa: E402
from norway_company_agent.sampling import snapshot_sha256  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def _timestamp(row: dict[str, Any], field: str) -> datetime | None:
    value = row.get(field) or (row.get("run") or {}).get(field)
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def audit_checkpoint(
    input_path: str | Path,
    envelopes_path: str | Path,
    ledger_path: str | Path,
    universe_path: str | Path,
    *,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a retained checkpoint and summarize its known accounting.

    This function intentionally does not reconstruct a missing runner report and
    never changes the checkpoint or its budget. It is safe to use when resume
    must fail closed because the original report is unavailable.
    """
    input_file = Path(input_path)
    envelopes_file = Path(envelopes_path)
    ledger_file = Path(ledger_path)
    universe_file = Path(universe_path)
    inputs = read_organisation_inputs(input_file)
    envelopes = _read_jsonl(envelopes_file)
    ledger = _read_jsonl(ledger_file)
    if not ledger:
        raise ValueError("Checkpoint budget ledger is empty")
    run_ids = {str(item.get("run_id") or "") for item in ledger}
    if len(run_ids) != 1 or "" in run_ids:
        raise ValueError("Checkpoint budget ledger contains multiple or missing run IDs")
    run_id = next(iter(run_ids))
    envelope_run_ids = {str(item.get("run_id") or (item.get("run") or {}).get("run_id") or "") for item in envelopes}
    if envelope_run_ids != {run_id}:
        raise ValueError("Checkpoint envelope run IDs do not match its budget ledger")

    expected_orgs = [item["organisation_number"] for item in inputs]
    output_orgs = [str(item.get("organisation_number") or "") for item in envelopes]
    validation = validate_envelopes(envelopes, len(expected_orgs))
    input_output_match = expected_orgs == output_orgs
    validation = {
        **validation,
        "passed": validation["passed"] and input_output_match,
        "checks": {**validation["checks"], "input_output_match": input_output_match},
    }
    started = next((value for value in (_timestamp(row, "started_at") for row in envelopes) if value), None)
    completed_values = [value for value in (_timestamp(row, "completed_at") for row in envelopes) if value]
    completed = max(completed_values) if completed_values else None
    section_names = sorted({section for row in envelopes for section in (row.get("sections") or {})})
    section_states = {
        section: dict(Counter((row.get("sections") or {}).get(section, {}).get("state") for row in envelopes))
        for section in section_names
    }
    claim_counts = Counter(
        claim.get("field")
        for row in envelopes
        for claim in row.get("claims") or []
        if claim.get("field")
    )
    latest_budget = ledger[-1]
    default_report = envelopes_file.with_name("report.json")
    final_report = Path(report_path) if report_path else default_report
    audit = {
        "schema_version": "1.0",
        "run_id": run_id,
        "input_path": str(input_file),
        "envelopes_path": str(envelopes_file),
        "ledger_path": str(ledger_file),
        "universe_path": str(universe_file),
        "final_report_present": final_report.exists(),
        "input_count": len(expected_orgs),
        "output_count": len(envelopes),
        "unique_output_organisation_numbers": len(set(output_orgs)),
        "input_output_match": input_output_match,
        "validation": validation,
        "status_counts": dict(Counter(row.get("status") for row in envelopes)),
        "section_state_counts": section_states,
        "claim_counts": dict(claim_counts),
        "started_at": started.isoformat().replace("+00:00", "Z") if started else None,
        "last_envelope_completed_at": completed.isoformat().replace("+00:00", "Z") if completed else None,
        "checkpoint_elapsed_seconds": round((completed - started).total_seconds(), 3) if started and completed else None,
        "budget_ledger_entries": len(ledger),
        "reserved_outbound_requests": latest_budget.get("outbound_requests", 0),
        "remaining_outbound_requests": latest_budget.get("remaining_outbound_requests"),
        "declared_cost_usd": latest_budget.get("cost_usd", 0.0),
        "universe_sha256": snapshot_sha256(universe_file),
        "classification": (
            "complete terminal checkpoint audit; runner report present"
            if validation["passed"] and len(envelopes) == len(expected_orgs) and final_report.exists()
            else "complete terminal checkpoint audit; not a final run report"
            if validation["passed"] and len(envelopes) == len(expected_orgs)
            else "incomplete or invalid checkpoint audit"
        ),
    }
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Original organisation-number input")
    parser.add_argument("--envelopes", required=True, help="Retained envelope JSONL checkpoint")
    parser.add_argument("--ledger", required=True, help="Retained budget ledger JSONL")
    parser.add_argument("--universe", required=True, help="Registry/universe snapshot used by the run")
    parser.add_argument("--output", help="Optional JSON audit output path")
    args = parser.parse_args()
    result = audit_checkpoint(args.input, args.envelopes, args.ledger, args.universe)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["validation"]["passed"] else 1)


if __name__ == "__main__":
    main()
