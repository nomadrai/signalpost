# Real-provider diagnostic allocation: Groq planner and Firecrawl Search

Date: 2026-10-13. This is a bounded development allocation, not an official
Builderr score. It used the configured Groq and Firecrawl credentials without
printing or persisting key values.

## Command shape

The run used the same 100-company local development input as the paced
allocation, with `--planner-assist`, `--discover-websites`, eight workers,
600-second deadline and 600 outbound-attempt cap. It used the working-tree
Firecrawl start gate of 6.5 seconds, zero declared Firecrawl dollar cost, and a
fresh daily ledger under `ROOT/runs/provider-allocation-100-diagnostics/`.

## Run result

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 332.472 seconds |
| Outbound attempts | 317 / 600 |
| Groq model calls | 100 |
| Reserved model tokens | 235,519 |
| Firecrawl search calls | 35 |
| Estimated third-party cost | USD 0.089376 |
| Daily ledger cost | USD 0.089376 |
| Unattributed attempts | 0 |
| Contract validation | Passed |

Coverage was 6 publishable websites, 3 company-owned profiles, 27 ambiguous
websites, 23 blocked, 8 failed and 36 not available. Hiring and activity had no
published items. All 100 identity sections were available. Search returned no
selected candidate that passed the independent exact-identity publication gate;
this remains a reliability/coverage measurement rather than evidence that
Firecrawl improves recall.

## Failure diagnosis

The new bounded diagnostics were exercised, but this run did not produce a
provider HTTP error to annotate:

- 32 Firecrawl HTTP 200 search responses were retained transiently.
- There were no Firecrawl HTTP 429 or transport-timeout results in this run.
- 97 planner tasks completed and 3 ended as runner-level `company_timeout`
  outcomes. Their provider response details were not available because the
  worker did not finish its planner operation before the 45-second company
  timeout.
- No Groq HTTP 400 was reproduced, so there is still no evidence to distinguish
  request-specific validation from a transient provider failure.

The first paced allocation remains the run that observed one Firecrawl 429,
one Firecrawl timeout and two Groq HTTP 400 responses. The working-tree client
now records bounded status, latency, safe request ID, retry-after seconds,
provider error code and hash/size for a bounded response sample. It does not
persist response bodies, prompts, page content or credentials, and does not add
blind retries or quota bypasses.
