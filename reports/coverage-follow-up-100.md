# Verified coverage follow-up

Date: 2026-10-08.

This follow-up adds deterministic first-party signal extraction and a stricter website publication gate. It does not enable paid search or model calls.

## Live capped run

The run used the existing 100-company input, the verified normalized universe, the official live identity endpoint, registry-linked websites, and a shared 200-attempt cap.

```bash
python scripts/run_batch.py \
  --input ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/coverage-live-100-v5/profiles.jsonl \
  --output ROOT/runs/coverage-live-100-v5/envelopes.jsonl \
  --report ROOT/runs/coverage-live-100-v5/report.json \
  --run-id coverage-live-100-v5 --expected-count 100 --workers 8 \
  --deadline-seconds 180 --max-requests 200
```

| Measurement | Result |
|---|---:|
| Inputs / terminal outputs | 100 / 100 |
| Identity-backed available envelopes | 100 |
| Elapsed time | 61.388 seconds |
| Reserved attempts / cap | 200 / 200 |
| Declared external API cost | USD 0 |
| Claims | 1,545 |
| Evidence validation | Passed |

| Section | Available | Not available | Ambiguous | Blocked | Failed |
|---|---:|---:|---:|---:|---:|
| Identity | 100 | 0 | 0 | 0 | 0 |
| Annual accounts | 42 | 58 | 0 | 0 | 0 |
| Leadership | 0 | 100 | 0 | 0 | 0 |
| Official website | 5 | 83 | 9 | 1 | 2 |
| Company-owned profiles | 1 | 99 | 0 | 0 | 0 |
| Hiring | 0 | 99 | 0 | 0 | 1 |
| Dated activity | 0 | 99 | 0 | 0 | 1 |

The allocation deliberately runs official identity before website verification so pages can be corroborated with registered address data. Five sites passed the v3 gate: exact organisation-number proof or exact legal name plus registered street/postcode/city. A parent/group site with a conflicting organisation number was quarantined as `ambiguous`; name-only pages remained unpublishable. The earlier 25-row manual review is not reused as a current precision estimate.

Hiring and activity extraction is now source-backed and first-party-only. It accepts same-host JSON-LD `JobPosting`/article records and dated HTML articles, verifies employer/publisher, page host, source date, expiry, and evidence locator, and publishes no item in this sample because no supported item was found within the fetched verified pages. The `failed` states reflect website fetch failures, not a claim that hiring or activity is absent.

## Deterministic signal and identity tests

- A synthetic first-party page fixture produced hiring and activity claims with stable claim IDs, page-specific source URLs, effective dates, and valid snapshot references.
- Expired jobs, off-host job links, conflicting organisation numbers, ambiguous websites, parent pages, parked pages, and directory/social hosts are rejected or quarantined.
- The full suite passed **129 tests and 5 subtests**.

## Large-batch conformance

The final matching-universe check selected rows from all 411,160 supplied identities and ran with zero outbound allowance:

| Inputs | Outputs | Elapsed | Attempts |
|---|---:|---:|---:|
| 1,000 | 1,000 `available` | 3.003 s | 0 |
| 1,100 | 1,100 `available` | 3.161 s | 0 |

Both runs passed exact-count, source-attribution, no-fabricated-financial-values, and evidence validation checks. The uncompressed universe hash remained `b82d6a3e7231d1759a958c282bc4366b80ec2fab8095053d8ed7fa9cd01bc838`.

## Allocation decision

`--discover-websites` is now opt-in. It tries conservative legal-name `.no`/`.com` candidates only after stronger field families and never publishes from name similarity alone. The default official allocation does not spend the shared request cap on speculative domains before identity, accounts, roles, and registry-linked website work.

Final candidate packaging and verification at the selected commit remain. A fresh bounded 1,000-company live allocation completed in 381.61 seconds at 2,000 attempts and USD 0; it is recorded in the release-conformance report but is not an official daily result. The pinned clean-clone installation passed; Playwright Chromium checks also passed at 390×844 and 1280×900, with artifacts recorded in `ROOT/runs/ui-screenshots/`. The public requirements reviewed on 2026-10-11 supply the official input at evaluation time and do not require a local official-batch run before submission or promise saved enrichment responses.
