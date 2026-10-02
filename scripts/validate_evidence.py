#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.schema import validate_claim_evidence  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate claim-to-snapshot references")
    parser.add_argument("envelopes")
    args = parser.parse_args()
    errors = []
    for line_number, line in enumerate(Path(args.envelopes).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        for message in validate_claim_evidence(row):
            errors.append({"line": line_number, "organisation_number": row.get("organisation_number"), "error": message})
    print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
