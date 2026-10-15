# Final candidate smoke report

Date: 2026-10-15.

This check was run from the exact pushed submission commit `aded677` with the
locked Python 3.12 environment. It is a local smoke result, not an official
Builderr score.

## Exact command

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/final-smoke-aded677/profiles.jsonl \
  --output ROOT/runs/final-smoke-aded677/envelopes.jsonl \
  --report ROOT/runs/final-smoke-aded677/report.json \
  --run-id final-smoke-aded677 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 200
```

## Result

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 65.898 seconds |
| Reserved HTTP attempts / cap | 200 / 200 |
| Declared third-party cost | USD 0 |
| Validation | Passed |
| Unattributed requests | 0 |
| Python source | Exact pushed commit `aded677` |
| Tests before smoke | 187 passed, 10 subtests passed |

The report passed exact-count, unique-organisation-number, terminal-state,
claim-evidence, and request-attribution validation. The full machine-readable
report and append-only request ledger are retained outside the repository at:

```text
ROOT/runs/final-smoke-aded677/report.json
ROOT/runs/final-smoke-aded677/envelopes.jsonl
ROOT/runs/final-smoke-aded677/envelopes.jsonl.budget.jsonl
```
