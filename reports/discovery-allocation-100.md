# Opt-in website discovery allocation

Date: 2026-10-11.

This is a development measurement of the opt-in `--discover-websites` route on
the existing 100-company input. It uses deterministic legal-name `.no`/`.com`
candidates and the same exact-entity publication gate. No search provider, model
or saved response map was used. The run is not an official Builderr score and
uses a larger local request allowance than the 200-attempt smoke report so that
the discovery family actually receives work.

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/discovery-allocation-100/profiles.jsonl \
  --output ROOT/runs/discovery-allocation-100/envelopes.jsonl \
  --report ROOT/runs/discovery-allocation-100/report.json \
  --run-id discovery-600 --expected-count 100 --workers 8 \
  --deadline-seconds 180 --max-requests 600 --discover-websites
```

## Result

| Measurement | Result |
|---|---:|
| Inputs / terminal outputs | 100 / 100 |
| Elapsed time | 175.307 seconds |
| Configured / reserved HTTP attempts | 600 / 470 |
| Discovery tasks started / completed | 100 / 99 |
| Discovery HTTP attempts | 110 |
| Unattributed requests | 0 |
| Declared third-party cost | USD 0 |
| Evidence validation | Passed |

Request attribution was:

| Field family | HTTP attempts |
|---|---:|
| Live identity | 100 |
| Registry website | 56 |
| Annual accounts | 104 |
| Leadership | 100 |
| Hiring/activity extraction | 0; 100 local tasks each |
| Legal-name website discovery | 110 |

One discovery task was left incomplete at the deadline. All 100 terminal
envelopes were still emitted and validation passed.

## Coverage outcome

- 8 verified websites, compared with 5 in the 200-attempt credential-free
  allocation.
- 4 company-owned profiles, compared with 1 in the 200-attempt allocation.
- 99 available annual-account sections.
- 100 available leadership sections.
- 0 published hiring items and 0 published dated-activity items.
- Website outcomes: 8 available, 23 ambiguous, 1 blocked and 68 not available.

The additional verified websites and profiles show that deterministic discovery
can add supported coverage when it receives a real allocation. It remains
opt-in: this run uses 470 attempts for 100 companies, does not establish hidden
corpus recall, and cannot be scaled to an official batch without an allocation
decision under the shared cap. Its publications still depend on independent
page evidence, not search or name similarity alone.
