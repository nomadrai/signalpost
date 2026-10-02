#!/usr/bin/env bash
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INPUT=${1:?usage: verify_clean_install.sh INPUT BULK OUTPUT_DIR}
BULK=${2:?usage: verify_clean_install.sh INPUT BULK OUTPUT_DIR}
OUT=${3:?usage: verify_clean_install.sh INPUT BULK OUTPUT_DIR}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 -m venv "$TMP/venv"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$TMP/venv/bin/python" -e "$REPO"
else
  "$TMP/venv/bin/python" -m pip install --disable-pip-version-check -e "$REPO"
fi
mkdir -p "$OUT"
PYTHONPATH="$REPO/src:$REPO" RUN_DEADLINE_SECONDS="${RUN_DEADLINE_SECONDS:-30}" "$TMP/venv/bin/python" "$REPO/scripts/run_batch.py" \
  --input "$INPUT" --bulk "$BULK" \
  --profiles-output "$OUT/profiles.jsonl" --output "$OUT/envelopes.jsonl" \
  --report "$OUT/report.json" --run-id clean-install --expected-count "$(grep -cve '^$' "$INPUT")"
"$TMP/venv/bin/python" - "$OUT/envelopes.jsonl" "$(grep -cve '^$' "$INPUT")" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
expected = int(sys.argv[2])
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
assert len(rows) == expected, (len(rows), expected)
allowed = {"available", "not_available", "blocked", "not_applicable", "ambiguous", "failed"}
assert all(row.get("status") in allowed for row in rows)
print(f"clean install verified: {len(rows)} terminal envelopes")
PY
