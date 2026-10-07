#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def recover_checkpoint(args, started: float) -> None:
    """Standard-library recovery still works when imports/local parsing stall."""
    output = Path(args.output)
    prior = {}
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("run_id") == args.run_id:
                prior[str(row.get("organisation_number"))] = row
    source = Path(args.input or args.organisations)
    text = source.read_text(encoding="utf-8")
    if source.suffix == ".json":
        body = json.loads(text)
        inputs = body if isinstance(body, list) else body.get("organisation_numbers", [])
    elif source.suffix == ".jsonl":
        inputs = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        inputs = [line for line in text.splitlines() if line.strip()]
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = []
    error = {"code": "supervisor_deadline", "message": "Run process group stopped at the wall-clock boundary; last atomic checkpoint retained.", "stage": "deadline"}
    for item in inputs:
        value = item.get("organisation_number") if isinstance(item, dict) else item
        org = "".join(character for character in str(value) if character.isdigit())
        row = prior.get(org) or {
            "schema_version": "1.0", "run_id": args.run_id, "organisation_number": org,
            "status": "failed", "state": "submission_error", "identity": {"organisation_number": org},
            "claims": [], "snapshots": [], "evidence": [], "profile": {"organisation_number": org},
            "synthesis": {"text": "", "sentences": [], "unknowns": ["Identity snapshot was not completed before the deadline."]},
            "sections": {name: {"state": "failed" if name == "identity" else "not_available", "claim_ids": []}
                         for name in ("identity", "accounts", "leadership", "workplaces", "website", "profiles", "hiring", "activity")},
            "refresh": {"changes": [], "previous_run_id": None}, "modules": {}, "operations": {},
            "run": {"run_id": args.run_id, "terminal_status": "failed"}, "errors": [],
        }
        row["errors"].append(error)
        row["completed_at"] = now
        row["run"]["completed_at"] = now
        rows.append(row)
    ledger_path = output.with_suffix(output.suffix + ".budget.jsonl")
    ledger = ledger_path.read_text(encoding="utf-8").splitlines() if ledger_path.exists() else []
    # An incomplete last reservation line precedes sending and can be ignored.
    budget = {}
    for line in reversed(ledger):
        try:
            candidate = json.loads(line)
            if candidate.get("run_id") == args.run_id:
                budget = candidate
                break
        except json.JSONDecodeError:
            continue
    initial_requests = 0
    company_requests = [0] * len(rows)
    first = True
    for line in ledger:
        try:
            reservation = json.loads(line)
        except json.JSONDecodeError:
            continue
        if reservation.get("run_id") != args.run_id:
            continue
        if first:
            initial_requests = reservation.get("outbound_requests", 0)
            first = False
        index = reservation.get("company_index")
        if isinstance(index, int) and 0 <= index < len(rows):
            company_requests[index] += 1
    for index, row in enumerate(rows):
        row["operations"]["requests"] = company_requests[index]
        row["profile"].setdefault("run_metrics", {})["requests"] = company_requests[index]
        for section in row["sections"].values():
            if section["state"] != "available":
                section.setdefault("reason", "supervisor_deadline")
    _write_rows(output, rows)
    _write_rows(Path(args.profiles_output), [row["profile"] for row in rows])
    report = {"schema_version": "1.0", "run_id": args.run_id, "completed_at": now,
              "elapsed_seconds": round(time.monotonic() - started, 3), "supervisor_stopped": True,
              "expected_count": len(inputs), "emitted_envelopes": len(rows), "budget": budget,
              "operations": {"requests": budget.get("outbound_requests", 0) - initial_requests, "third_party_cost_usd": budget.get("cost_usd", 0)},
              "validation": {"passed": len(rows) == len(inputs) and len({row["organisation_number"] for row in rows}) == len(inputs)}}
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def main() -> None:
    started = time.monotonic()
    parser = argparse.ArgumentParser(add_help=False)
    for name in ("input", "organisations", "output", "profiles-output", "report", "run-id"):
        parser.add_argument("--" + name)
    parser.add_argument("--deadline-seconds", type=float, default=None)
    args, _ = parser.parse_known_args()
    value = args.deadline_seconds if args.deadline_seconds is not None else os.environ.get("RUN_DEADLINE_SECONDS") or "2700"
    try:
        deadline = float(value)
    except ValueError:
        parser.error("RUN_DEADLINE_SECONDS must be a number")
    if not math.isfinite(deadline) or not 0 <= deadline <= 2700:
        parser.error("Deadline must be finite and between 0 and 2700 seconds")
    environment = {**os.environ, "_SIGNALPOST_STARTED_MONOTONIC": str(started)}
    implementation = Path(__file__).resolve().with_name("run_batch_impl.py")
    child = subprocess.Popen([sys.executable, str(implementation), *sys.argv[1:]], env=environment, start_new_session=True)

    def hard_exit(_signum, _frame):
        # Last-resort guard also bounds a stalled recovery write or process
        # join. The last atomic output remains on disk.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os._exit(124)

    if deadline:
        signal.signal(signal.SIGALRM, hard_exit)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - (time.monotonic() - started)))
    try:
        # Zero means a local-only run, preserving the deterministic pass even
        # when network time is unavailable. Positive deadlines bound all work.
        reserve = min(2.0, deadline * 0.1)
        returncode = child.wait(timeout=max(0.001, deadline - reserve - (time.monotonic() - started)) if deadline else None)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=0.25)
        recover_checkpoint(args, started)
        returncode = 0
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=0.25)
        signal.setitimer(signal.ITIMER_REAL, 0)
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
