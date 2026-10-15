# Final candidate smoke report

Date: 2026-10-15.

This check was run from a fresh source clone at `7c51966` with a locked Python
3.12 environment. It validates the current batch interface after the coverage,
structured-signal, synthesis, claim-anchor, and repository-cleanup changes. It
is not an official Builderr score.

## Exact command

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/final-smoke-7c51966/profiles.jsonl \
  --output ROOT/runs/final-smoke-7c51966/envelopes.jsonl \
  --report ROOT/runs/final-smoke-7c51966/report.json \
  --run-id final-smoke-7c51966 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 200
```

## Result

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 34.657 seconds |
| Reserved HTTP attempts / cap | 200 / 200 |
| Declared third-party cost | USD 0 |
| Verified websites | 5 |
| Company-owned profiles | 1 |
| Validation | Passed |
| Unattributed requests | 0 |
| Python source | Fresh clone at `7c51966` |
| Tests | 186 passed, 10 subtests passed |

The request cap was exhausted after live identity, registry website, and part
of annual-account work. Leadership, workplaces, and group work were explicitly
reported as unavailable rather than silently dropped. Hiring and activity ran
as local extraction tasks with zero additional requests. The complete report
is retained at `ROOT/runs/final-smoke-7c51966/report.json`.
