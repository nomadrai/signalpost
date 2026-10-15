# Coverage profile measurement: default versus workplace diagnostic

Date: 2026-10-15.

This is a development comparison on the same frozen 100-company input. Both
runs used the same 180-second deadline, 600 outbound-attempt cap, eight workers,
deterministic website discovery, no model, no search provider, and USD 0
external cost. The default submission profile was not changed.

## Commands

Default allocation:

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/coverage-profile-default-100/profiles.jsonl \
  --output ROOT/runs/coverage-profile-default-100/envelopes.jsonl \
  --report ROOT/runs/coverage-profile-default-100/report.json \
  --run-id coverage-profile-default-100 \
  --expected-count 100 --workers 8 --deadline-seconds 180 \
  --max-requests 600 --discover-websites --coverage-profile default
```

Workplace diagnostic allocation:

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/coverage-profile-workplace-100/profiles.jsonl \
  --output ROOT/runs/coverage-profile-workplace-100/envelopes.jsonl \
  --report ROOT/runs/coverage-profile-workplace-100/report.json \
  --run-id coverage-profile-workplace-100 \
  --expected-count 100 --workers 8 --deadline-seconds 180 \
  --max-requests 600 --discover-websites \
  --coverage-profile workplace-diagnostic
```

## Result

| Measurement | Default | Workplace diagnostic |
|---|---:|---:|
| Elapsed time | 160.033 s | 127.493 s |
| Requests | 600 | 600 |
| Validation | Passed | Passed |
| Accounts available | 99 | 99 |
| Leadership available | 100 | 100 |
| Workplaces available | 37 | **100** |
| Verified websites | 11 | 10 |
| Ambiguous websites | 35 | 26 |
| Company-owned profiles | 5 | 5 |
| Third-party cost | USD 0 | USD 0 |

## Decision

The diagnostic profile works: it retrieves all 100 workplace sections within
the same deadline and request cap. It also preserves accounts, leadership and
company-owned profile counts in this measurement. Website discovery receives
fewer requests under the diagnostic profile, so its website result should not
replace the default profile for the submission without a scoring decision.

Keep `default` as the submission allocation. Keep
`workplace-diagnostic` as an explicit measurement and troubleshooting option.
The comparison is directional because live endpoint latency and remote content
can vary between runs, but it demonstrates that workplace coverage is a
scheduling issue rather than an AI-provider requirement.
