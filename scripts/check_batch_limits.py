#!/usr/bin/env python3
"""Reproducible large-batch local checks against matching universe identities."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.sampling import iter_bulk, snapshot_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--counts", default="1000,1100")
    parser.add_argument("--seed", type=int, default=20261008)
    args = parser.parse_args()
    counts = [int(value) for value in args.counts.split(",")]
    maximum = max(counts)
    rng = random.Random(args.seed)
    sample = []
    population = 0
    for population, record in enumerate(iter_bulk(args.universe), 1):
        if len(sample) < maximum:
            sample.append(record)
        else:
            position = rng.randrange(population)
            if position < maximum:
                sample[position] = record
    if len(sample) < maximum:
        parser.error("Universe contains fewer rows than the requested batch")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"seed": args.seed, "universe_rows": population,
               "universe_sha256": snapshot_sha256(args.universe), "runs": []}
    for count in counts:
        directory = output_dir / str(count)
        directory.mkdir(exist_ok=True)
        selected = sample[:count]
        input_path = directory / "input.jsonl"
        input_path.write_text("".join(json.dumps({"organisation_number": row["organisation_number"]}) + "\n" for row in selected))
        command = [sys.executable, str(ROOT / "scripts" / "run_batch.py"), "--input", str(input_path),
                   "--bulk", args.universe, "--output", str(directory / "envelopes.jsonl"),
                   "--profiles-output", str(directory / "profiles.jsonl"), "--report", str(directory / "report.json"),
                   "--run-id", f"local-limits-{count}", "--expected-count", str(count), "--max-requests", "0",
                   "--deadline-seconds", "60"]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=65)
        report = json.loads((directory / "report.json").read_text())
        envelopes = [json.loads(line) for line in (directory / "envelopes.jsonl").read_text().splitlines()]
        expected = {row["organisation_number"]: row for row in selected}
        assert report["validation"]["passed"]
        assert report["registry"]["selected"] == count
        assert report["registry"]["missing"] == 0
        assert report["operations"]["requests"] == 0
        assert report["budget"]["outbound_requests"] == 0
        assert len(envelopes) == count
        for envelope in envelopes:
            org = envelope["organisation_number"]
            assert envelope["status"] == "available"
            assert envelope["identity"]["name"] == expected[org]["name"]
            assert envelope["profile"]["evidence"]["registry"]["source_type"] == "local_company_universe"
            assert all(not claim["field"].startswith("accounts.") for claim in envelope["claims"])
        summary["runs"].append({"count": count, "matching_registry_rows": count,
                                "elapsed_seconds": report["elapsed_seconds"],
                                "states": dict(Counter(row["status"] for row in envelopes)),
                                "requests": report["operations"]["requests"],
                                "validation_passed": report["validation"]["passed"]})
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
