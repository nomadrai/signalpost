#!/usr/bin/env python3
"""Validate a saved run and export its coverage and budget measurements."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import validate_envelopes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelopes", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.envelopes).read_text().split("\n") if line.strip()]
    report = json.loads(Path(args.report).read_text())
    validation = validate_envelopes(rows, report["expected_count"])
    assert validation["passed"], validation
    assert report["budget"]["outbound_requests"] <= report["budget"]["max_outbound_requests"] <= 2000
    assert report["budget"]["cost_usd"] <= 10
    assert sum(row["operations"].get("requests", 0) for row in rows) == report["operations"]["requests"]
    if report.get("request_ledger"):
        ledger = [json.loads(line) for line in Path(report["request_ledger"]).read_text().splitlines()]
        assert ledger[-1]["outbound_requests"] == report["budget"]["outbound_requests"]
    result = {"run_id": report["run_id"], "started_at": report["started_at"],
              "inputs": report["expected_count"], "outputs": len(rows),
              "status_counts": dict(Counter(row["status"] for row in rows)),
              "section_states": {section: dict(Counter(row["sections"][section]["state"] for row in rows))
                                 for section in rows[0]["sections"]},
              "claims": sum(len(row["claims"]) for row in rows),
              "elapsed_seconds": report["elapsed_seconds"], "operations": report["operations"],
              "budget": report["budget"], "validation": validation,
              "website_identity_cases": [{"organisation_number": row["organisation_number"], "name": row["identity"]["name"],
                                          "state": row["sections"]["website"]["state"],
                                          "url": row["profile"]["evidence"].get("website", {}).get("source_url"),
                                          "assessment": (row["profile"]["evidence"].get("website", {}).get("value") or {}).get("identity_assessment")}
                                         for row in rows if row["profile"].get("website")],
              "manual_identity_review": "not performed for this run"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
