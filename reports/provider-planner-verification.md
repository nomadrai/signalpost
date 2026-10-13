# Provider and planner follow-up verification

Working-tree follow-up to `523cf7d`, reviewed 2026-10-13. This report records
local regression and fixture verification, not a real-provider coverage result
or an official Builderr score.

## Automated verification

```bash
uv run --no-sync --with pytest pytest -q
git diff --check
```

Result: **159 tests passed, plus 5 subtests**; whitespace checks passed.

The provider/planner tests cover:

- Groq environment aliases, namespace isolation, JSON mode, completion-token
  request fields, and published GPT-OSS 120B pricing.
- Generic 429 credential failover and a Groq organization-wide cooldown that
  blocks further calls through a second client sharing the run budget.
- Firecrawl Search response parsing, optional Authorization handling, Norwegian
  country targeting, credit reporting, and keyless-request behavior.
- Credential-bearing redirect rejection, with a local HTTP server confirming
  that no redirected request occurs.
- Daily cost accounting shared by independent budget objects and independent
  processes. Twenty concurrent USD 0.01 reservations against a USD 0.05 ledger
  allow exactly five. These are simulated costs with no paid requests.
- Corrupt/incomplete ledger rejection, invalid counters, future-date rejection,
  UTC-day rollover, per-key limits, and a zero daily monetary allowance.
- Planner URL allow-listing, malformed action/query rejection, transient search
  retention, key-free fallback, and terminal output after a planner worker error.

## End-to-end local provider fixtures

`tests/test_provider_planner.py` runs the actual batch implementation with local
Groq-compatible model and Firecrawl-compatible search HTTP endpoints and a captured-page fixture. The website identity
gate and envelope validation are the production implementations. The captured
page fixture reserves a request but does not contact a public website.

| Case | Terminal website state | Reserved requests | Simulated cost |
|---|---|---:|---:|
| Model selects an allowed legal-name candidate | Available | 2 | USD 0.02 |
| Model requests search, then independently gated page | Available | 3 | USD 0.03 |
| Search candidate's page identifies a different owner | Ambiguous | 3 | USD 0.03 |
| Planner worker raises an exception | Not available | 0 | USD 0 |

All cases emit a valid terminal envelope. Request attribution reconciles with
zero unattributed attempts. Resuming completed successful/ambiguous fixture
cases makes zero additional requests. Fixture credentials and search snippets
are absent from emitted profiles, envelopes, reports and the daily ledger.

## 100-company local-only smoke

The existing seeded input and original verified universe were reused in place.
Outputs are outside the product repository under
`ROOT/runs/firecrawl-followup-local-100/`.

```bash
MAX_LLM_CALLS=0 MAX_LLM_TOKENS=0 MAX_SEARCH_CALLS=0 MAX_COST_USD=0 \
SIGNALPOST_DAILY_COST_LEDGER=ROOT/runs/provider-followup-local-100/daily.json \
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/firecrawl-followup-local-100/profiles.jsonl \
  --output ROOT/runs/firecrawl-followup-local-100/envelopes.jsonl \
  --report ROOT/runs/firecrawl-followup-local-100/report.json \
  --run-id firecrawl-followup-local-100 --expected-count 100 --workers 8 \
  --deadline-seconds 30 --max-requests 0
```

Replace `ROOT` with the workspace parent of the product repository.

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Identity-backed available envelopes | 100 |
| Elapsed time | 5.462 seconds |
| Outbound / model / search requests | 0 / 0 / 0 |
| Third-party cost | USD 0 |
| Terminal and claim-evidence validation | Passed |
| Unattributed requests | 0 |

This checks default-module output under zero HTTP allowance. It does not measure
live enrichment recall or replace the previous live 100-company smoke report.
## Live provider probes

The configured `.env.local` contains two Groq credentials; their values were
never printed or persisted. A direct Groq GPT-OSS 120B JSON request succeeded:

| Measurement | Result |
|---|---:|
| Model | `openai/gpt-oss-120b` |
| Provider requests | 1 |
| Response | Valid JSON: `{"ok": true}` |
| Reserved tokens | 1,345 |
| Estimated reserved cost | USD 0.00074175 |
| Credential pool size | 2 |

A keyless Firecrawl Search request previously reached the official endpoint but
returned **HTTP 403**. After the user configured a Firecrawl API key, the live
adapter probe succeeded:

| Measurement | Result |
|---|---:|
| Endpoint | `https://api.firecrawl.dev/v2/search` |
| HTTP status | 200 |
| Query | Exact company name, organisation number and municipality |
| Results | 3 candidate URLs |
| Firecrawl credits | 2 |
| Reserved outbound attempts | 1 |
| Declared USD cost | 0 (credit quota, not a USD reservation) |

The full one-company runner then used the configured Groq planner and selected
an allow-listed legal-name URL directly. It emitted one valid terminal envelope
in 16.873 seconds, used 5 outbound attempts, reserved 2,410 model tokens and
USD 0.000902, and passed validation. Since the model selected `fetch_url`, that
particular runner invocation did not consume a Firecrawl search call; the live
Firecrawl adapter probe above exercised the search path directly. Firecrawl's
published pricing says Search costs 2 credits per 10 results, with 1,000 free
monthly credits and a 10-searches-per-minute free-plan limit.

Real-provider coverage comparison and final candidate packaging remain open.
The Firecrawl/Groq changes are still uncommitted.
