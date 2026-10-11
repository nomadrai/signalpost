# Shared-budget verification

Date: 2026-10-08 (live run timestamps are recorded in UTC on 2026-10-07).

## Live 100-company run

Used the same seeded 100-company input as the earlier smoke report, with the original verified normalized universe as the identity snapshot. Paid search and models were disabled.

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/bounded-live-100/profiles.jsonl \
  --output ROOT/runs/bounded-live-100/envelopes.jsonl \
  --report ROOT/runs/bounded-live-100/report.json \
  --run-id bounded-live-100 --expected-count 100 --workers 8 \
  --deadline-seconds 180 --max-requests 200
```

| Measurement | Result |
|---|---:|
| Inputs / terminal outputs | 100 / 100 |
| Identity-backed `available` envelopes | 100 |
| Elapsed time | 50.484 seconds |
| HTTP attempts / configured cap | 200 / 200 |
| Declared external API cost | USD 0 |
| Claims | 2,957 |
| Structural evidence errors | 0 |
| Worker/task errors | 0 |

The request count includes retries, redirects, and robots. The reservation ledger's final count and the sum of per-company request counts both match the run report. This run deliberately uses one tenth of the daily maximum to exercise exhaustion.

| Section | Available | Not available | Ambiguous | Blocked | Failed |
|---|---:|---:|---:|---:|---:|
| Identity | 100 | 0 | 0 | 0 | 0 |
| Accounts | 99 | 1 | 0 | 0 | 0 |
| Leadership | 40 | 60 | 0 | 0 | 0 |
| Workplaces | 0 | 100 | 0 | 0 | 0 |
| Website | 6 | 83 | 9 | 1 | 1 |
| Company-owned profiles | 2 | 98 | 0 | 0 | 0 |
| Hiring | 0 | 100 | 0 | 0 | 0 |
| Dated activity | 0 | 100 | 0 | 0 | 0 |

Coverage reflects the new allocation and stricter 200-attempt cap; it is not an equal-budget coverage comparison with the earlier 600-request run. The legacy exact-identity gate is retained. A fresh manual identity audit was not performed for this run; the earlier 25-row review is not reused as evidence of current precision.

Machine-readable results: `bounded-smoke-100.json`. It includes website identity decisions and explicitly records the missing manual audit.

## Matching large-batch local checks

`scripts/check_batch_limits.py` selected a seeded reservoir from all 411,160 universe rows, then ran both sizes against the original complete file with `--max-requests 0` and a 60-second deadline.

| Inputs | Matching identities | Terminal outputs | Elapsed | Outbound attempts |
|---|---:|---:|---:|---:|
| 1,000 | 1,000 | 1,000 `available` | 2.959 s | 0 |
| 1,100 | 1,100 | 1,100 `available` | 3.037 s | 0 |

Both passed envelope/evidence validation, preserved exact names and universe attribution, and published no financial amounts from the filing-year flag. The universe byte hash remained `b82d6a3e7231d1759a958c282bc4366b80ec2fab8095053d8ed7fa9cd01bc838`.

## Automated boundary checks

- Independent local-server counters verify retries, redirects, and robots accounting.
- Concurrent worker processes exhaust a shared allowance without overshoot.
- A stuck in-flight task is killed; its request reservation remains counted and identity-backed output is preserved.
- The process-group supervisor can emit failed terminal rows when startup exceeds a tiny positive deadline.
- Saved official responses enrich accounts with zero outbound allowance.
- Concurrent search/model reservations share one monetary cap.

The retained full-size identity review, pinned clean-clone installation, and browser screenshot checks are now recorded in `release-conformance-2026-10-08.md`. Final candidate packaging and verification at the selected commit remain. The public requirements reviewed on 2026-10-11 supply the official batch at evaluation time; it is not a prerequisite for local submission preparation. Saved response maps are optional.
