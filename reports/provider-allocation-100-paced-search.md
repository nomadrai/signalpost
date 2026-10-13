# Real-provider allocation: Groq planner and Firecrawl Search

Date: 2026-10-13. This is a bounded development allocation, not an official
Builderr score. The run used the configured server-side Groq key pool and
Firecrawl key; key values were not printed or persisted.

## Command

```bash
set -a; source ./.env.local; set +a
MAX_LLM_CALLS=100 MAX_LLM_TOKENS=250000 MAX_SEARCH_CALLS=100 \
MAX_COST_USD=2 FIRECRAWL_SEARCH_COST_PER_CALL_USD=0 \
FIRECRAWL_SEARCH_MIN_INTERVAL_SECONDS=6.1 \
SIGNALPOST_DAILY_COST_CAP_USD=10 \
SIGNALPOST_DAILY_COST_LEDGER=ROOT/runs/provider-allocation-100-paced-search/daily.json \
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/provider-allocation-100-paced-search/profiles.jsonl \
  --output ROOT/runs/provider-allocation-100-paced-search/envelopes.jsonl \
  --report ROOT/runs/provider-allocation-100-paced-search/report.json \
  --run-id provider-allocation-100-paced-search --expected-count 100 \
  --workers 8 --modules registry --planner-assist --discover-websites \
  --deadline-seconds 600 --max-requests 600
```

## Run result

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Elapsed time | 322.963 seconds |
| Outbound attempts | 312 / 600 |
| Groq model calls | 100 |
| Reserved model tokens | 235,519 |
| Firecrawl search calls | 34 |
| Estimated third-party cost | USD 0.089376 |
| Daily ledger cost | USD 0.089376 |
| Unattributed attempts | 0 |
| Contract validation | Passed |

The shared Groq pacing gate prevented the burst-related provider exhaustion seen
in the first allocation. All 100 planner tasks completed; there were no Groq
`model_key_unavailable` outcomes. There were three explicit planner failures:
one timeout and two HTTP 400 responses. Firecrawl had 32 HTTP 200 responses,
one timeout and one HTTP 429 while this run used a 6.1-second gate. The
working-tree default is now 6.5 seconds; the 429 is retained as a provider-side
reliability gap to diagnose rather than hidden or retried around.

## Output coverage and precision gates

| Section/state | Count |
|---|---:|
| Identity available | 100 |
| Website available and publishable | 6 |
| Website ambiguous | 26 |
| Website not available | 36 |
| Website blocked | 24 |
| Website failed | 8 |
| Company-owned profiles available | 3 |
| Hiring/activity published | 0 |

The six published first-party sites passed the existing deterministic identity
gate. Twenty-six were withheld as ambiguous and 32 were blocked/failed. Search
results did not produce a selected search candidate in this allocation: the
exact-identity candidate gate abstained on the returned directories/aggregators.
The planner selected allow-listed legal-name candidates for the remaining
website work. This means the run proves provider reliability and safe fallback,
but does not yet demonstrate a Firecrawl-specific website-recall improvement.

## Interpretation and next work

- Keep the planner and Firecrawl connector opt-in; do not promote them into the
  default submission path based on this allocation.
- Retain the shared Groq pacing gate and Firecrawl pacing gate. They are needed
  for provider reliability under worker concurrency.
- Investigate the three model failures and one remaining Firecrawl 429 using
  provider response diagnostics, without logging secrets or page content.
- Evaluate a search-query/candidate strategy on a larger frozen identity sample.
  Do not weaken the exact-company publication gate merely to increase recall.

The working-tree follow-up adds bounded, secret-safe provider diagnostics for
future allocations: status, latency, safe request ID, retry-after seconds,
provider error code and a hash/size for a bounded response sample. It does not
retry HTTP 400s or bypass provider-wide 429 cooldowns. The run outputs and
report are outside the product repository under
`ROOT/runs/provider-allocation-100-paced-search/`.
