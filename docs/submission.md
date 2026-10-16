# Submission candidate

This document records the reproducible release procedure for the current
candidate. Builderr supplies the official organisation-number batch and frozen
identity registry snapshot at evaluation time. The local smoke run is evidence
that the command produces one terminal envelope per input; it is not an official
score.

## Current candidate

- Repository: `https://github.com/nomadrai/signalpost`
- Runtime behavior smoke baseline: `aded677`
- Submission package commit: record the final pushed commit in the submission email
- Runtime: Python 3.12+
- Dependency installer: `uv`
- Submitted primary model: OpenAI `gpt-5.6-sol`
- Submitted search provider: Firecrawl Search
- Cheaper alternative: Groq `openai/gpt-oss-120b` + Firecrawl Search
- Declared maximum third-party cost: USD 10 per official run

The runtime smoke was run at `aded677`. Submit the later packaging commit that
contains the provider integration and this documentation update so the
repository link, documentation, and runtime code are all covered by one exact
revision.

## Clean installation

From a fresh clone at the exact commit sent to Builderr:

```bash
git clone https://github.com/nomadrai/signalpost.git
cd signalpost
git checkout <exact-commit-sent-to-builderr>
uv sync --locked --python 3.12
```

The `--locked` flag prevents the installer from changing `uv.lock`. The Python
3.12 selector matches the declared release environment; the project requires
Python 3.12 or newer.

## Evaluator command

This is the one-command batch interface. Builderr supplies the two input paths
at evaluation time:

Concise form:

```bash
uv run --no-sync python scripts/run.py <organisations.jsonl> <frozen-registry-snapshot.csv-or-jsonl>
```

It derives the expected input count and creates output files under a timestamped
`out/` directory. The fully explicit form below is available when fixed output
paths are required:

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations <organisations.jsonl> \
  --bulk <frozen-registry-snapshot.csv-or-jsonl> \
  --profiles-output <run>/profiles.jsonl \
  --output <run>/envelopes.jsonl \
  --report <run>/report.json \
  --run-id <run-id> \
  --expected-count <input-count> \
  --planner-assist \
  --discover-websites
```

The `--bulk` input may be plain/gzip Brønnøysund CSV or normalized universe
JSONL/gzip. The command emits exactly one terminal envelope per input and keeps
best-effort enrichment from preventing terminal output.

## Local smoke command used for this candidate

The reproducible smoke input and verified public universe are outside the
repository. The clean-clone command used for the checked runtime was:

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/final-smoke-aded677/profiles.jsonl \
  --output ROOT/runs/final-smoke-aded677/envelopes.jsonl \
  --report ROOT/runs/final-smoke-aded677/report.json \
  --run-id final-smoke-aded677 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 200
```

The exact final-commit measurement at `aded677` produced 100/100 terminal
envelopes in 65.898 seconds, used 200/200 reserved HTTP attempts,
declared USD 0, passed structural validation, and reconciled all requests to
field families with zero unattributed attempts. See
`reports/final-candidate-smoke-aded677.md`.

## Tests and network-free checks

```bash
uv run --no-sync --with pytest pytest -q
uv run --no-sync python scripts/check_batch_limits.py \
  --universe <universe.jsonl> \
  --output-dir <runs>/budget-conformance
```

The current tree passes 190 tests plus 10 subtests. The large zero-request checks
produce 1,000 and 1,100 available terminal envelopes with exact identity/source
attribution. A submitted run should also retain its JSON report, evidence output
and request ledger for audit.

## Declarations for submission

```text
Models: OpenAI native `gpt-5.6-sol` for the submitted primary profile.
        Groq `openai/gpt-oss-120b` + Firecrawl is the cheaper alternative.
APIs: Public Brønnøysundregistrene endpoints, direct permitted public
      company-page HTTP/HTTPS retrieval, OpenAI-compatible model endpoint,
      and Firecrawl Search when provider credentials and allowances are set.
Search provider: Firecrawl Search, bounded to the shared request/cost budget.
Licences: Original repository code and documentation are MIT-licensed in
          LICENSE. Dependency and source rights are listed in MANIFEST.md,
          LIMITATIONS.md and docs/external-connectors.md.
Expected third-party cost per official run: bounded by `MAX_COST_USD`, with a
          declared maximum of USD 10; actual use depends on the supplied batch
          and provider reservations.
Secrets: OpenAI/Groq and Firecrawl credentials are injected server-side by the
         evaluator environment and are never committed or written to output.
```

Configure the submitted primary profile with `SIGNALPOST_MODEL_PROVIDER=openai`,
`OPENAI_API_KEY`, `OPENAI_MODEL=gpt-5.6-sol`, `FIRECRAWL_API_KEY`, positive
`MAX_LLM_CALLS`, `MAX_LLM_TOKENS`, `MAX_SEARCH_CALLS`, `MAX_COST_USD`, and an
explicit `SIGNALPOST_MODEL_COST_PER_CALL_USD`. The cheaper alternative switches
to `SIGNALPOST_MODEL_PROVIDER=groq`, `GROQ_API_KEY`, and
`GROQ_MODEL=openai/gpt-oss-120b`. The model only chooses bounded website
actions; deterministic identity and publication gates remain authoritative.

`--planner-assist --discover-websites` is the submitted website path. The planner
prefers allowed registry/legal-name candidates and can invoke one transient
Firecrawl search under the shared search/request/cost budgets. Raw Firecrawl
search results are discarded and independently fetched pages remain the only
publication evidence.

The model transport integration is covered by
`reports/model-assist-integration-100.md`; that check uses a local provider
fixture because no real credential is stored in the repository. The real model
key must be injected into the evaluator environment.
