# Credential-free allocation follow-up

Date: 2026-10-11.

This run measures the bounded runner's field-family allocation on the existing
100-company development input. It uses the verified normalized identity
universe, no saved enrichment response map, no model, no paid search and a
200-attempt cap. The output is a local development measurement, not an official
Builderr score.

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/coverage-allocation-100/profiles.jsonl \
  --output ROOT/runs/coverage-allocation-100/envelopes.jsonl \
  --report ROOT/runs/coverage-allocation-100/report.json \
  --run-id next-agent-100 --expected-count 100 --workers 8 \
  --deadline-seconds 180 --max-requests 200
```

## Result

| Measurement | Result |
|---|---:|
| Inputs / terminal outputs | 100 / 100 |
| Elapsed time | 86.392 seconds |
| Reserved HTTP attempts | 200 / 200 |
| Declared third-party cost | USD 0 |
| Validation | Passed |
| Unattributed requests | 0 |

The runner now records request and task attribution by field family. The 200
attempts were attributed as follows:

| Field family | Planned | Started | Completed | Skipped | HTTP attempts |
|---|---:|---:|---:|---:|---:|
| Live identity | 100 | 100 | 100 | 0 | 101 |
| Registry website | 100 | 17 | 100 | 0 | 56 |
| Annual accounts | 100 | 45 | 45 | 55 | 43 |
| Leadership | 100 | 0 | 0 | 100 | 0 |
| Hiring extraction | 100 | 100 | 100 | 0 | 0 |
| Activity extraction | 100 | 100 | 100 | 0 | 0 |
| Registered workplaces | 100 | 0 | 0 | 100 | 0 |
| Group | 100 | 0 | 0 | 100 | 0 |

Hiring and activity extraction ran locally for all 100 companies after the
website pass, even after the HTTP allowance was exhausted. It uses captured
replay documents and does not require another request or model call.

## Coverage outcome

- 100 identity-backed terminal envelopes.
- 41 available annual-account sections.
- 5 exact/corroborated websites.
- 1 company-owned profile.
- 0 published hiring items.
- 0 published dated-activity items.
- Website outcomes: 5 available, 11 ambiguous, 1 blocked and 83 not available.
- Hiring/activity had 99 `not_available` and 1 `blocked` outcome each; the
  blocked state came from the unavailable website source, not an assertion that
  no company hiring/activity exists.

This change improves measurement and preserves supported local extraction under
request exhaustion. It does not promote legal-name discovery or claim a net
recall improvement from this single development allocation.
