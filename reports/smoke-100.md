# 100-company smoke report

Date: 2026-10-02

## Command

```bash
PYTHONPATH=src python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/runs/phase0/baseline-registry-subset.csv.gz \
  --profiles-output ROOT/runs/current-100-v2/profiles.jsonl \
  --output ROOT/runs/current-100-v2/envelopes.jsonl \
  --report ROOT/runs/current-100-v2/report.json \
  --run-id current-100-v2 --expected-count 100 --workers 8 --deadline-seconds 180
```

The sample contains 100 seeded public-universe rows. The registry input is a local gzip CSV subset made from those same rows; official modules and registry-linked websites were requested from live endpoints. This keeps the report reproducible without committing a large registry file.

## Counts and states

- Inputs: 100
- Terminal envelopes: 100
- Equal input/output count: yes
- Envelope status: 100 `available`
- Legacy terminal state: 100 `complete`
- Pass-1 envelopes: 100
- Pass-2 completed: 100
- Pass-2 errors: 0
- Evidence validation errors: 0
- Declared third-party cost: USD 0

Section states:

| Section | Available | Not available | Ambiguous | Blocked |
|---|---:|---:|---:|---:|
| Identity | 100 | 0 | 0 | 0 |
| Annual accounts | 99 | 1 | 0 | 0 |
| Leadership | 100 | 0 | 0 | 0 |
| Registered workplaces | 100 | 0 | 0 | 0 |
| Official website | 7 | 83 | 9 | 1 |
| Company-owned profiles | 2 | 98 | 0 | 0 |
| Hiring | 0 | 100 | 0 | 0 |
| Dated activity | 0 | 100 | 0 | 0 |

The website section counts only sites that pass the identity gate; fetched but uncertain sites remain `ambiguous` and are not published. An unavailable hiring or activity source does not mean that no hiring or activity exists.

## Runtime and operations

- Wall runtime: 126.826 seconds
- Company runtime p50/p95: 8,095.103 / 19,491.518 ms
- Request latency p50/p95: 1,632 / 2,051 ms
- Requests: 600
- Response bytes: 17,810,586
- Peak RSS: 192,540 KiB
- Claims: 3,303
- Stable claim evidence check: passed

## Identity review

A hand-check of 25 rows from the sampled output found 0 wrong-company publications. Seven accepted websites, nine uncertain/related/review sites, and nine rows without a fetched site were reviewed. This is a small manual check, not a population precision estimate.

## Baseline comparison

| Metric | Starter baseline | Current runner |
|---|---:|---:|
| Inputs / outputs | 100 / 100 | 100 / 100 |
| Wall runtime | 140.48 s | 126.826 s |
| Requests | 600 | 600 |
| Accounts available | 99 | 99 |
| Roles available | 100 | 100 |
| Workplaces available | 100 | 100 |
| Website identity accepted | 7 | 7 |
| Wrong-company publications in 25-row check | 0 | 0 |
| Claim-level evidence validation | not emitted | passed |
| Explicit envelope availability state | no | yes |

The runtime comparison is directional because the two runs were made at different times against live services. The current run adds typed envelopes, stable claims, snapshots, synthesis, unknowns, evidence validation, incremental output, and deadline reporting without changing the starter's deterministic endpoint selection.
