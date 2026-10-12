# Signalpost reference agent

This is a runnable starting point for the Signalpost company-research challenge. It is intentionally a solid baseline, not a winning submission.

The public universe contains 411,160 eligible companies. Run the starter on 100 companies before submitting. Larger local tests, including 1,000 or more companies, are encouraged but their precomputed profiles are not submitted or scored.

## What it already does

- reads a batch of Norwegian organisation numbers;
- anchors identity in the Brønnøysund bulk registry;
- fetches official financials, roles, group links and registered workplaces;
- visits the registry-listed website and rejects weak entity matches;
- emits one terminal JSONL envelope per input;
- records sources, retrieval times, content hashes, request counts and latency;
- supports checkpoint/resume and a deterministic refresh replay;
- includes examples for external-footprint discovery and an evidence-bounded research agent.

## First run: try one saved example

Requires Python 3.12+. Open a terminal inside this extracted folder.

Before downloading company data or running a full crawl, try the bundled public
sample. It uses saved responses: no API key, registry download or live web requests.

```bash
python3 scripts/run_refresh_replay.py \
  --manifest tests/fixtures/refresh-snapshots.json \
  --output out/refresh-demo.json
```

Open `out/refresh-demo.json`. The `events` list shows what changed between two
versions of one company profile and the source evidence for each change. The sample
should find two expected changes, no false changes, and no extra changes when the
same data is checked again.

The report's `qualification_passed` field refers only to this public sample check.
It does not qualify an entry for the competition or prove live information coverage.
The printed request counts are reads from saved responses, not network calls.

## Next: research live companies

Requires Python 3.12+ and `uv`. This step downloads data and makes live requests.
The manifest selector can create a local test batch of any size. Use 100 rows for the recommended smoke test before trying a larger batch.

```bash
uv sync --locked --python 3.12
curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o signalpost-universe.jsonl.gz

uv run python select_entry_batch.py \
  --universe signalpost-universe.jsonl.gz \
  --count 100 \
  --output entry-companies.jsonl

# Use the 100-company batch as your smoke test.
cp entry-companies.jsonl smoke-companies.jsonl

uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/smoke-profiles.jsonl \
  --output out/smoke-envelopes.jsonl \
  --report out/smoke-report.json \
  --run-id smoke-001 \
  --expected-count 100

# You may test at larger scale locally, but Builderr supplies the official batch for scoring.
uv run python scripts/run_competition_batch.py \
  --organisations entry-companies.jsonl \
  --bulk brreg-enheter.csv \
  --profiles-output out/profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000

uv run --no-sync --with pytest pytest -q
```

The current follow-up tree was verified on October 11, 2026 with 135 tests and 5 subtests, followed by deterministic 1,000/1,100-company matching-universe checks that emitted every terminal envelope with zero outbound requests. Runtime candidate `b4b7cd9` also passed a fresh Python 3.12 clean-clone install with `uv sync --locked --python 3.12` and the exact competition-compatible smoke command. The earlier published archive check was 104 tests and 5 subtests plus a one-company live BRREG smoke run.

Increase `--count` and `--expected-count` together for a larger local test. The 100-row smoke test above is practice only; Builderr supplies the companies for every official run.

## The improvement loop

1. Treat the organisation number as the anchor.
2. Generate site/profile candidates from official data, the company site, lawful search providers and named people.
3. Save every candidate and the evidence for or against it.
4. Publish only exact-entity matches. Parent, brand, franchise and similarly named companies are not exact.
5. Crawl static HTML first. Escalate to a browser only when a deterministic completeness check fails.
6. Measure added supported coverage, wrong-company claims, runtime, requests and cost.
7. Promote a strategy only when it improves coverage without weakening the accuracy gates.
8. Freeze strategies and thresholds before the daily evaluation run.

The strongest differentiator is external evidence that remains exact and auditable: official company pages, company-owned profiles, jobs, dated activity, ratings/reviews and permitted public signals. Do not trade accuracy for volume.

## Important source rule

Open-source code does not grant permission to scrape a platform. Follow each source's terms, robots policy, rate limits and licence. LinkedIn, Meta and Indeed are useful identity/discovery targets, but direct automated collection may be restricted. Use permitted APIs, licensed providers, company-owned outbound links, or return `blocked`/`not_available`.

Read `docs/competition-control-loop.md`, `docs/external-connectors.md` and the public source policy before adding connectors.

## Submission contract

Submit a repository with:

- a 100-company smoke-test result or report;
- one documented command that accepts a JSONL batch of organisation numbers;
- exactly one terminal envelope per input;
- pinned dependencies and reproducible setup;
- a previous-snapshot input and material-change output;
- a machine-readable run report with runtime, request count and third-party cost;
- declared models, APIs, licences and source-rights assumptions.

Email the repository URL, exact commit hash, 100-company smoke report, run command, models/APIs/licences, expected cost per official run, agent name and contact details to `submit@builderr.ai`. Builderr supplies the evaluation input at run time; obtaining that batch locally is not a prerequisite for submission. See [runtime and credentials](docs/runtime-and-credentials.md) for supplied inputs and optional search/model keys.

## Deterministic batch interface

The bounded runner accepts the supplied organisation-number file and a plain or gzip-compressed Brønnøysund CSV snapshot or normalized company-universe JSONL. It writes an atomic JSONL checkpoint as soon as the identity pass is complete, then replaces rows as best-effort enrichment finishes. Every valid input receives one terminal envelope, including when the deadline or a source policy prevents enrichment. `scripts/run_competition_batch.py` uses this same runner and preserves the starter's `--organisations` interface.

```bash
PYTHONPATH=src python scripts/run_batch.py \
  --input <organisations.jsonl> \
  --bulk <brreg-enheter.csv> \
  --profiles-output <run>/profiles.jsonl \
  --output <run>/envelopes.jsonl \
  --report <run>/report.json \
  --run-id <run-id>
```

The supported terminal states are `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, and `failed`. Use `--previous-output` to include source-backed refresh changes. The stable claim/snapshot fields are described in `DATA_SCHEMA.md`.

### Shared limits and local snapshots

- The default wall-clock deadline is **2,700 seconds**, including startup and local processing. `--deadline-seconds` or `RUN_DEADLINE_SECONDS` can lower it. Isolated enrichment workers are killed at their task deadline or the run's safety boundary. A POSIX process-group supervisor bounds shutdown and recovers terminal rows from the last atomic checkpoint if the main runner stalls. Zero selects local-only processing and disables enrichment rather than imposing a zero-time file-writing deadline.
- The default shared cap is **2,000 outbound HTTP attempts**. `--max-requests` or `MAX_OUTBOUND_REQUESTS` can lower it. Failed requests, retries, redirects, and robots fetches all reserve a slot before transport. The append-only `<output>.budget.jsonl` ledger records reservations before sending. Domain parsing uses the bundled suffix list and performs no hidden suffix-list download.
- Saved official responses are consumed first when supplied. Live field-family priority is identity, registry-listed websites, accounts, roles, hiring/activity, opt-in website discovery, workplaces, group, and account history. Websites get at most four attempts per task; official modules get at most two, including retries/redirects. Account-history starts retain a shared 2.1-second minimum interval. Unattempted fields have explicit `not_available` states and budget/deadline reasons; an identity-backed result can still be `available`. Conservative legal-name domain discovery is opt-in with `--discover-websites`; it runs after the stronger default fields and is not a search-provider or model integration.
- `--response-snapshot <responses.json>` accepts a saved JSON object with `retrieved_at`, optional `effective_at`, and a `responses` map keyed by official URL. Each value has `status`, and either `body` or `raw_json`. Saved responses are consumed first, retain their source timestamps/hashes, count as `snapshot_reads`, and consume no outbound requests. Missing saved responses may use live HTTP within the cap.
- `--model-assist` enables the optional OpenAI-compatible evidence assistant. It requires `SIGNALPOST_MODEL_API_KEY`, a configured endpoint/model and positive `MAX_LLM_CALLS`, `MAX_LLM_TOKENS` and `MAX_COST_USD` allowances. The model sees only retained exact-company page captures; its output must pass deterministic URL/hash/date/quote validation before publication. Without these settings the run remains deterministic and key-free.
- Normalized universe JSONL is attributed to its published universe source, its exact supplied byte hash, and its local file identifier. It supports identity and the latest-filing-year flag; it supplies no financial amounts, roles, or subunit responses. Local reads have no fabricated HTTP status.
- Monetary reservations share one **USD 10 maximum** across search and models. `MAX_COST_USD` defaults to zero, and search/model call limits default to zero. The batch has no enabled paid connector. A monetary allowance alone enables no provider.
- `--resume` reuses completed modules only when the identity snapshot hash matches, and carries forward the same run's request/cost reservations and elapsed time. If the previous run report is absent, live requests are refused because in-flight usage cannot be reconstructed reliably. Keep the same run ID and report path for a resumed run.

To exercise matching large batches without live requests:

```bash
python scripts/check_batch_limits.py \
  --universe <financial-filer-master-2025.jsonl> \
  --output-dir <runs>/budget-conformance
```

See `reports/bounded-smoke-100.md` for the live capped-run and 1,000/1,100-company verification results, `reports/coverage-allocation-100.md` for field-family request attribution and request-exhaustion behavior, `reports/discovery-allocation-100.md` for the opt-in website-discovery measurement, `reports/final-candidate-smoke-b4b7cd9.md` for the current clean-clone smoke, and `docs/submission.md` for the candidate command and declarations.

The optional model transport and deterministic evidence gate were exercised with
a local provider fixture in `reports/model-assist-integration-100.md`. No real
provider credential is stored in the repository.

Audit a retained checkpoint without resuming it or making network requests:

```bash
PYTHONPATH=src python scripts/audit_batch_checkpoint.py \
  --input <organisations.jsonl> \
  --envelopes <run>/envelopes.jsonl \
  --ledger <run>/envelopes.jsonl.budget.jsonl \
  --universe <financial-filer-master-2025.jsonl>
```

The audit validates terminal rows, claim evidence, input/output identity
matching, and the append-only request ledger. It deliberately does not
reconstruct a missing runner report or make a resumed live request.

Build the dependency-light static viewer without a server or external assets:

```bash
PYTHONPATH=src python scripts/build_viewer.py <run>/envelopes.jsonl <run>/viewer
```

The viewer includes searchable company cards, profile facts with source links and dates, explicit unknown states, a three-column compare page, and change history. See `AGENT.md`, `CRAWLERS.md`, `IDENTITY_RESOLUTION.md`, `REFRESH.md`, `EVAL.md`, and `LIMITATIONS.md` for the operating boundaries.
