# Coverage-priority follow-up — 100 companies

Date: 2026-10-15

This is a local allocation comparison, not an official Builderr score. Both
runs used the same 100-company input, the same normalized universe snapshot
(SHA-256 `b82d6a3e7231d1759a958c282bc4366b80ec2fab8095053d8ed7fa9cd01bc838`),
the default coverage profile, an 180-second deadline, eight workers, a 600
outbound-attempt cap, and opt-in legal-name website discovery. The follow-up
changes only the default priority so official workplace, group, and account
history modules run before optional website discovery and model signals.

## Result

| Measure | Previous default | Follow-up default |
|---|---:|---:|
| Terminal envelopes | 100/100 | 100/100 |
| Structural validation | passed | passed |
| Identity available | 100 | 100 |
| Accounts available | 99 | 99 |
| Leadership available | 100 | 100 |
| Registered workplaces available | 37 | **100** |
| Verified websites available | 11 | 6 |
| Company-owned profiles available | 5 | 2 |
| Reserved outbound attempts | 600 | 600 |
| Unattributed attempts | 0 | 0 |
| Declared third-party cost | USD 0 | USD 0 |
| Elapsed time | 160.033 s | **106.407 s** |

The change prevents optional discovery from starving the official workplace
module. Website and profile recall is lower in this particular allocation,
which is expected when discovery is enabled under a fixed cap; discovery is
still opt-in and is now the last network-heavy module. The normal default
command does not enable discovery, so it receives the official-category gain
without spending attempts on derived website candidates.

## Reproduction

Previous report:

```text
ROOT/runs/coverage-profile-default-100/report.json
```

Follow-up report:

```text
ROOT/runs/coverage-profile-default-100-followup-discovery/report.json
```

The follow-up was run with:

```bash
PYTHONPATH=src python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/coverage-profile-default-100-followup-discovery/profiles.jsonl \
  --output ROOT/runs/coverage-profile-default-100-followup-discovery/envelopes.jsonl \
  --report ROOT/runs/coverage-profile-default-100-followup-discovery/report.json \
  --run-id coverage-profile-default-100-followup-discovery \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 600 \
  --coverage-profile default \
  --discover-websites
```

The output report passed exact-count, terminal-state, evidence, and
request-attribution validation. No claim-precision regression was observed in
the structural checks; official evaluation remains the authority for recall
and precision scoring.
