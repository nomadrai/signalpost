# Website discovery recall follow-up

Date: 2026-10-14.

This is a bounded development measurement on the same frozen 100-company input
used by the earlier discovery allocation. It is not an official Builderr score.
The run used no model, search provider, saved response map or paid API.

## Changes under test

- The runner no longer skips the website task when only `registry_live` has a
  website URL.
- Opt-in legal-name discovery keeps a bounded eight-candidate frontier instead
  of truncating registry/live URLs and the two original guesses. It considers
  compact, hyphenated and initial-based labels, with `.no` candidates first.
- A live registry name can contribute candidates when it differs from the
  frozen snapshot name.
- Exact legal-name plus registered-address evidence can publish a derived
  domain. Name-only derived matches remain quarantined.
- Search results can contribute up to three URL-only branded-domain candidates
  for independent crawling. Raw titles, snippets, ranks and queries remain
  transient. A branded search result without hostname or registered-identity
  corroboration cannot publish on organisation-number evidence alone.
- Identity-oriented proof-page links include common Norwegian/English variants
  and bare-domain/`www` equivalents while the registered-domain boundary and
  page/request caps remain in force.

## Candidate-frontier measurement

The frozen 100-company input had the following deterministic candidate counts,
comparing the previous three-item implementation with the new bounded frontier:

| Measurement | Previous | Current |
|---|---:|---:|
| Candidate URLs | 143 | 311 |
| Legal-name-domain candidates | 126 | 294 |
| URLs available only in the current strategy | — | 162 |
| Candidate frontier maximum per company | 3 | 8 |

These counts measure discovery opportunity, not verified publication. Every
candidate still passes the existing public-URL, robots, exact-company identity
and ownership gates.

## Frozen live allocation

Command:

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/discovery-recall-100-v7/profiles.jsonl \
  --output ROOT/runs/discovery-recall-100-v7/envelopes.jsonl \
  --report ROOT/runs/discovery-recall-100-v7/report.json \
  --run-id discovery-recall-v7 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 600 \
  --discover-websites
```

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 175.347 seconds |
| Reserved outbound attempts | 503 / 600 |
| Discovery tasks started / completed | 70 / 61 |
| Discovery attempts | 143 |
| Verified websites | 10 |
| Company-owned profiles | 5 |
| Declared third-party cost | USD 0 |
| Unattributed attempts | 0 |
| Contract validation | Passed |

The previous comparable 600-attempt allocation published 8 websites and 4
company-owned profiles. The current run published 10 and 5 respectively. The
result is directional: DNS, remote-site latency and the shared 180-second
deadline affect how many discovery tasks start. The broader frontier also
caused later locations/group work to be skipped in this opt-in allocation; the
default submission command does not enable discovery.

The run retained no provider snippets or credentials. Search candidates remain
opt-in and independently identity-gated; the default submission path still
uses no model or paid search provider.
