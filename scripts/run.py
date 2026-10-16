#!/usr/bin/env python3
"""Short command wrapper for the bounded Signalpost batch runner."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "organisations",
        nargs="?",
        default="data/entry-companies.jsonl",
        help="organisation-number JSONL/text input (default: data/entry-companies.jsonl)",
    )
    parser.add_argument(
        "bulk",
        nargs="?",
        default="data/brreg-enheter.csv",
        help="registry CSV or company-universe JSONL (default: data/brreg-enheter.csv)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="run output directory (default: out/run-<UTC timestamp>)",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--deadline-seconds", type=float, default=None)
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument(
        "--no-planner",
        action="store_true",
        help="use the no-provider local path instead of bounded planner/search assistance",
    )
    args = parser.parse_args()

    organisations = Path(args.organisations)
    bulk = Path(args.bulk)
    for path, label in ((organisations, "organisation input"), (bulk, "registry snapshot")):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")

    try:
        from norway_company_agent.batch import read_organisation_inputs

        expected_count = len(read_organisation_inputs(organisations))
    except Exception as exc:  # pragma: no cover - the underlying CLI reports details
        parser.error(f"could not read organisation input: {exc}")

    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) if args.output_dir else Path("out") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(Path(__file__).with_name("run_competition_batch.py")),
        "--organisations",
        str(organisations),
        "--bulk",
        str(bulk),
        "--profiles-output",
        str(output_dir / "profiles.jsonl"),
        "--output",
        str(output_dir / "envelopes.jsonl"),
        "--report",
        str(output_dir / "report.json"),
        "--run-id",
        run_id,
        "--expected-count",
        str(expected_count),
        "--workers",
        str(args.workers),
    ]
    if args.deadline_seconds is not None:
        command.extend(("--deadline-seconds", str(args.deadline_seconds)))
    if args.max_requests is not None:
        command.extend(("--max-requests", str(args.max_requests)))
    if not args.no_planner:
        command.extend(("--planner-assist", "--discover-websites"))

    completed = subprocess.run(command, cwd=ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
