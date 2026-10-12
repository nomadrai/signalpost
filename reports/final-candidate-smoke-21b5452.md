# Final candidate smoke report

Date: 2026-10-12.

This smoke run was executed from a fresh clone at runtime candidate revision
`21b5452` after installing the frozen dependency set. It used the existing
seeded 100-company development input and the verified normalized public
universe. It is not an official Builderr score.

## Exact command

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/final-smoke-21b5452/profiles.jsonl \
  --output ROOT/runs/final-smoke-21b5452/envelopes.jsonl \
  --report ROOT/runs/final-smoke-21b5452/report.json \
  --run-id final-smoke-21b5452 --expected-count 100 --workers 8 \
  --deadline-seconds 180 --max-requests 200
```

## Result

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 99.769 seconds |
| Reserved HTTP attempts / cap | 200 / 200 |
| Declared third-party cost | USD 0 |
| Validation | Passed |
| Unattributed HTTP attempts | 0 |
| Python environment | Clean clone, Python 3.12.3, locked install |

| Section | Available | Not available | Ambiguous | Blocked | Failed |
|---|---:|---:|---:|---:|---:|
| Identity | 100 | 0 | 0 | 0 | 0 |
| Annual accounts | 40 | 60 | 0 | 0 | 0 |
| Leadership | 0 | 100 | 0 | 0 | 0 |
| Website | 5 | 83 | 10 | 1 | 1 |
| Company-owned profiles | 1 | 99 | 0 | 0 | 0 |
| Hiring | 0 | 98 | 0 | 1 | 1 |
| Dated activity | 0 | 98 | 0 | 1 | 1 |

The output passed terminal-envelope, claim-evidence and exact-count validation.
The 200 attempts reconciled to 102 live-identity, 56 registry-website and 42
annual-account requests. Hiring/activity ran as 100 local tasks each after the
HTTP allowance was exhausted; they made zero additional requests. The optional
model stage was not enabled.
