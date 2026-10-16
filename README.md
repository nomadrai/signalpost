# Signalpost reference agent

Signalpost is a deterministic, evidence-first company-research agent for
Norwegian organisations. It takes organisation numbers and produces one
source-linked JSONL result per input company. The registry organisation number
is always the identity anchor; uncertain facts are withheld instead of guessed.

The repository is a runnable reference implementation for the Signalpost
challenge. A no-key local mode remains available, but the submitted search
profile uses native OpenAI `gpt-5.6-sol` plus Firecrawl. A cheaper Groq
`openai/gpt-oss-120b` plus Firecrawl profile is documented as an alternative.
Builderr supplies the official batch and frozen registry snapshot at evaluation
time; you do not need the official batch to run the project locally or prepare a
submission.

The original code and documentation in this repository are licensed under the
[MIT License](LICENSE). This does not grant permission to copy or redistribute
third-party registry, website, platform, model, or search-provider content; use
those sources according to their own terms and rights.

## What the agent does

- reads a batch of Norwegian organisation numbers;
- anchors identity in the Brønnøysund registry or supplied company universe;
- fetches official accounts, roles, group links, and registered workplaces;
- visits registry-listed websites and publishes only exact-company matches;
- extracts first-party website descriptions, profiles, hiring, and dated activity;
- emits exactly one terminal JSONL envelope per input;
- records sources, retrieval times, content hashes, extraction methods, request
  counts, latency, availability states, and unknowns;
- supports bounded deadlines, shared request budgets, checkpoint/resume, and
  deterministic refresh replay;
- includes a static evidence viewer and a bounded local research endpoint.

## Run it locally from a fresh clone

The commands below assume Linux or macOS and a shell such as Bash. The same
Python commands work on Windows PowerShell after installing Git, Python 3.12,
and `uv`.

### 1. Clone the repository

```bash
git clone https://github.com/nomadrai/signalpost.git
cd signalpost
```

For a submission or reproducibility check, use the exact commit listed in the
submission email instead of `main` before installing dependencies. For ordinary
local development, keep the default branch:

```bash
git checkout main
# Reproducible submission alternative:
# git checkout <exact-commit-sent-to-builderr>
```

### 2. Install `uv` if needed, then create the locked environment

Check whether it is already installed:

```bash
uv --version
```

If the command is missing, install `uv` using the official installer, then open
a new terminal if your shell does not immediately see it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install the exact locked Python environment:

```bash
uv sync --locked --python 3.12
```

The project creates `.venv/` locally. It is ignored by Git and does not need to
be committed.

### 3. Configure the submitted search profile

The submitted configuration accepts provider credentials from the evaluator's
environment. It does not put keys in the repository. Copy the template only if
you are running the provider-backed path locally:

```bash
cp .env.example .env.local
chmod 600 .env.local
```

Set these values in `.env.local` for the submitted OpenAI + Firecrawl path:

```env
SIGNALPOST_MODEL_PROVIDER=openai
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-5.6-sol
FIRECRAWL_API_KEY=your-firecrawl-key
SIGNALPOST_MODEL_COST_PER_CALL_USD=your-conservative-openai-call-reservation
```

Also keep positive `MAX_LLM_CALLS`, `MAX_LLM_TOKENS`, `MAX_SEARCH_CALLS`, and
`MAX_COST_USD` allowances. The runner never guesses OpenAI or OpenRouter
pricing. To use the cheaper alternative, switch the provider block to
`SIGNALPOST_MODEL_PROVIDER=groq`, `GROQ_API_KEY`, and
`GROQ_MODEL=openai/gpt-oss-120b`; its published Groq price is handled by the
runner. Load credentials only into the process that runs the batch:

```bash
set -a
source ./.env.local
set +a
```

The default no-key local mode does not enable provider calls. The submitted
provider-backed command explicitly uses `--planner-assist` and
`--discover-websites`.

### 4. Run the no-network example first

This verifies refresh/change detection using only the checked-in fixture. It
does not download the registry, require credentials, or make live requests.

```bash
uv run python scripts/run_refresh_replay.py \
  --manifest tests/fixtures/refresh-snapshots.json \
  --output out/refresh-demo.json
```

Inspect `out/refresh-demo.json`. Its `events` list shows source-backed changes
between two saved versions of one company profile. The generated `out/` folder
is ignored by Git.

### 5. Run the test suite

```bash
make test
```

The verified release candidate passes 190 tests plus 10 subtests.

### 6. Download the public local input data

This step makes live HTTP requests and downloads public data. Create a local
`data/` directory, which is ignored for downloaded CSV/JSONL data:

```bash
mkdir -p data
curl -fL 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' \
  -o data/brreg-enheter.csv
curl -fL 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' \
  -o data/signalpost-universe.jsonl.gz
```

Select a deterministic 100-company practice batch:

```bash
uv run python select_entry_batch.py \
  --universe data/signalpost-universe.jsonl.gz \
  --count 100 \
  --output data/entry-companies.jsonl
```

### 7. Run the 100-company local smoke test

The smoke command writes profiles, envelopes, a machine-readable report, and a
request ledger below `out/smoke-100/`. The folder is ignored by Git.

```bash
mkdir -p out/smoke-100
uv run python scripts/run_competition_batch.py \
  --organisations data/entry-companies.jsonl \
  --bulk data/brreg-enheter.csv \
  --profiles-output out/smoke-100/profiles.jsonl \
  --output out/smoke-100/envelopes.jsonl \
  --report out/smoke-100/report.json \
  --run-id smoke-100 \
  --expected-count 100
```

Success means the report contains 100 emitted terminal envelopes, passed
validation, and reconciled request attribution. The exact checked-in smoke
measurement is documented in
[`reports/final-candidate-smoke-aded677.md`](reports/final-candidate-smoke-aded677.md).

### 8. Run a larger local batch only if needed

Increase `--count` and `--expected-count` together. Builderr supplies the
official evaluation companies, so local 1,000-company runs are diagnostics,
not a substitute for the official evaluation batch:

```bash
uv run python select_entry_batch.py \
  --universe data/signalpost-universe.jsonl.gz \
  --count 1000 \
  --output data/entry-companies-1000.jsonl

uv run python scripts/run_competition_batch.py \
  --organisations data/entry-companies-1000.jsonl \
  --bulk data/brreg-enheter.csv \
  --profiles-output out/profiles.jsonl \
  --output out/envelopes.jsonl \
  --report out/run-report.json \
  --run-id local-001 \
  --expected-count 1000
```

### 9. Build and view the static evidence UI

After a batch has produced `envelopes.jsonl`, build the dependency-light viewer:

```bash
uv run python scripts/build_viewer.py \
  out/smoke-100/envelopes.jsonl \
  out/smoke-100/viewer
```

To use the bounded local research panel, serve the same output:

```bash
uv run python scripts/serve_viewer.py \
  --source out/smoke-100/envelopes.jsonl \
  --output out/smoke-100/viewer \
  --host 127.0.0.1 \
  --port 8000
```

Open <http://127.0.0.1:8000/>. The panel answers only from retained profile
evidence; it does not start an unbounded crawl or call an LLM.

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
- Saved official responses are consumed first when supplied. Live field-family priority is identity, registry-listed websites, accounts, roles, hiring/activity, workplaces, group, account history, opt-in website discovery, and optional model signals. This keeps official categories from being starved by expensive optional discovery. Websites get at most four attempts per task; official modules get at most two, including retries/redirects. Account-history starts retain a shared 2.1-second minimum interval. Unattempted fields have explicit `not_available` states and budget/deadline reasons; an identity-backed result can still be `available`. Conservative legal-name domain discovery is opt-in with `--discover-websites`; it runs after the stronger default fields and is not a search-provider or model integration.
- `--response-snapshot <responses.json>` accepts a saved JSON object with `retrieved_at`, optional `effective_at`, and a `responses` map keyed by official URL. Each value has `status`, and either `body` or `raw_json`. Saved responses are consumed first, retain their source timestamps/hashes, count as `snapshot_reads`, and consume no outbound requests. Missing saved responses may use live HTTP within the cap.
- `--model-assist` enables the optional OpenAI-compatible evidence assistant. Set `SIGNALPOST_MODEL_PROVIDER=openai` with `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-5.6-sol` for the submitted primary profile, or switch to `openrouter` with `OPENROUTER_API_KEY` and `OPENROUTER_MODEL=openai/gpt-5.6-sol`. Groq's cheaper alternative uses `GROQ_API_KEY` and `GROQ_MODEL=openai/gpt-oss-120b`. The model sees only retained exact-company page captures; its output must pass deterministic URL/hash/date/quote validation before publication.
- `--planner-assist` is the submitted bounded website-planning stage. With `--discover-websites`, it prefers allowed registry/legal-name candidates and can request one transient Firecrawl search when positive `MAX_SEARCH_CALLS` is configured. Search results are discarded except for a bounded URL frontier; the normal crawler and exact-company identity gate still control publication. See [runtime and credentials](docs/runtime-and-credentials.md) for configuration and allocation details.
- Normalized universe JSONL is attributed to its published universe source, its exact supplied byte hash, and its local file identifier. It supports identity and the latest-filing-year flag; it supplies no financial amounts, roles, or subunit responses. Local reads have no fabricated HTTP status.
- Monetary reservations share one **USD 10 maximum** across search and models. `MAX_COST_USD` defaults to zero, and search/model call limits default to zero. `SIGNALPOST_DAILY_COST_CAP_USD` defaults to 10 and `SIGNALPOST_DAILY_COST_LEDGER` defaults to `~/.cache/signalpost/daily-cost.json`, enforcing an additional persistent UTC-day cap across invocations using that same path. An optional local per-key request cap is available. A monetary allowance alone enables no provider.
- `--resume` reuses completed modules only when the identity snapshot hash matches, and carries forward the same run's request/cost reservations and elapsed time. If the previous run report is absent, live requests are refused because in-flight usage cannot be reconstructed reliably. Keep the same run ID and report path for a resumed run.
- `--coverage-profile default` preserves the submission allocation order. Opt-in category profiles are available for `accounts-diagnostic`, `leadership-diagnostic`, `workplaces-diagnostic` (plus the backwards-compatible `workplace-diagnostic` alias), `website-diagnostic`, `hiring-diagnostic`, `activity-diagnostic`, `website-discovery-diagnostic`, `group-diagnostic`, and `financial-history-diagnostic`. They move the selected category earlier while preserving dependencies and the same shared request/deadline controls. They are diagnostic allocations, not part of the default submission command.

To exercise matching large batches without live requests:

```bash
python scripts/check_batch_limits.py \
  --universe <financial-filer-master-2025.jsonl> \
  --output-dir <runs>/budget-conformance
```

See `reports/bounded-smoke-100.md` for the live capped-run and 1,000/1,100-company verification results, `reports/coverage-allocation-100.md` for field-family request attribution and request-exhaustion behavior, `reports/discovery-allocation-100.md` and `reports/discovery-recall-follow-up-100.md` for opt-in website-discovery measurements, `reports/coverage-profile-workplace-100.md` and `reports/coverage-priority-follow-up-100.md` for coverage-priority comparisons, `reports/final-candidate-smoke-aded677.md` for the latest 100-company smoke baseline, and `docs/submission.md` for the provider-backed candidate command and declarations.

The optional model transport and deterministic evidence gate were exercised with
a local provider fixture in `reports/model-assist-integration-100.md`. No real
provider credential is stored in the repository.

Groq configuration, persistent daily budgeting and the opt-in planner are covered
by `reports/provider-planner-verification.md`, including end-to-end local
provider fixtures, wrong-owner rejection, resume and a zero-request 100-company smoke.
The first paced real-provider allocation is recorded in
`reports/provider-allocation-100-paced-search.md`; it is directional development
evidence, not an official score.
The follow-up diagnostic allocation and bounded provider-error handling are
recorded in `reports/provider-allocation-100-diagnostics.md`.

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

The viewer includes searchable company cards, profile facts with source links and dates, explicit unknown states, a field-aligned three-column compare page, change history, per-section freshness, and a bounded evidence question panel. Its visual system uses warm paper, forest green, and marigold accents with consistent outline symbols.

Section availability is run-specific, not a hard-coded default. The profile
view distinguishes verified evidence, ambiguous identity, a missing candidate,
and work that was not fetched before the run deadline or request cap. A
`Not fetched in this run` label means the source task did not execute; it does
not prove that the company has no workplace or website. A website marked
`No candidate in identity snapshot` means the supplied identity data had no
website URL; `Fetched, identity unresolved` means a page was reached but was
withheld by the exact-company identity gate.

To enable the profile question panel, serve the generated viewer through the
small local research endpoint. It answers only from the retained profile
evidence and does not start an unbounded crawl:

```bash
PYTHONPATH=src python scripts/serve_viewer.py \
  --source <run>/envelopes.jsonl \
  --output <run>/viewer \
  --host 127.0.0.1 \
  --port 8000
```

Open `http://127.0.0.1:8000/`. The endpoint accepts bounded `POST` requests at
`/api/research` with an organisation number and a question. The default batch
runner and submission contract remain unchanged.

The question box supports bounded natural-language phrasing locally. For
example, “How much did the company make?”, “Who runs this company?”, “Where is
it based?”, and “Does it have a website?” are mapped to supported evidence
families. This uses a deterministic local topic normalizer, not an LLM, paid
API, or live crawl, so it adds no external cost. Questions outside identity,
financials, roles, locations, websites, social profiles, and employees abstain
with an explanation instead of guessing.
