# Submission candidate

This document records the reproducible release procedure for the current
candidate. Builderr supplies the official organisation-number batch and frozen
identity registry snapshot at evaluation time. The local smoke run is evidence
that the command produces one terminal envelope per input; it is not an official
score.

## Current candidate

- Repository: `https://github.com/nomadrai/signalpost`
- Runtime source candidate revision verified locally: `afa5cc3a7a3b63dc814c60a53ca7e303a85839b8`
- Runtime: Python 3.12+
- Dependency installer: `uv`
- Default models: none
- Default paid APIs: none
- Default declared third-party cost: USD 0

## Clean installation

From a fresh clone at the exact candidate revision:

```bash
git clone https://github.com/nomadrai/signalpost.git
cd signalpost
git checkout 21b5452
uv sync --locked --python 3.12
```

The `--locked` flag prevents the installer from changing `uv.lock`. The Python
3.12 selector matches the declared release environment; the project requires
Python 3.12 or newer.

## Evaluator command

This is the one-command batch interface. Builderr supplies the two input paths
at evaluation time:

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations <organisations.jsonl> \
  --bulk <frozen-registry-snapshot.csv-or-jsonl> \
  --profiles-output <run>/profiles.jsonl \
  --output <run>/envelopes.jsonl \
  --report <run>/report.json \
  --run-id <run-id> \
  --expected-count <input-count>
```

The `--bulk` input may be plain/gzip Brønnøysund CSV or normalized universe
JSONL/gzip. The command emits exactly one terminal envelope per input and keeps
best-effort enrichment from preventing terminal output.

## Local smoke command used for this candidate

The reproducible smoke input and verified public universe are outside the
repository in the handoff workspace. The clean-clone command used for the
current candidate was:

```bash
uv run --no-sync python scripts/run_competition_batch.py \
  --organisations ROOT/runs/phase0/baseline-organisations.jsonl \
  --bulk ROOT/signalpost-company-universe-2025.jsonl/financial-filer-master-2025.jsonl \
  --profiles-output ROOT/runs/final-smoke-21b5452/profiles.jsonl \
  --output ROOT/runs/final-smoke-21b5452/envelopes.jsonl \
  --report ROOT/runs/final-smoke-21b5452/report.json \
  --run-id final-smoke-21b5452 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 200
```

The current clean-source-clone measurement at `afa5cc3` produced 100/100
terminal envelopes in 78.312 seconds, used 200/200 reserved HTTP attempts,
declared USD 0, passed structural validation, and reconciled all requests to
field families with zero unattributed attempts. See
`reports/final-candidate-smoke-afa5cc3.md`.
The later packaging commits only record this report and pin the submission
metadata; runtime source behavior is unchanged.

## Tests and network-free checks

```bash
uv run --no-sync --with pytest pytest -q
uv run --no-sync python scripts/check_batch_limits.py \
  --universe <universe.jsonl> \
  --output-dir <runs>/budget-conformance
```

The current tree passes 172 tests plus 5 subtests. The large zero-request checks
produce 1,000 and 1,100 available terminal envelopes with exact identity/source
attribution. A submitted run should also retain its JSON report, evidence output
and request ledger for audit.

## Declarations for submission

```text
Models: None in the default batch.
APIs: Public Brønnøysundregistrene endpoints and direct permitted public
      company-page HTTP/HTTPS retrieval.
Search provider: None enabled in the default batch.
Licences: Dependencies and source rights are listed in MANIFEST.md,
          LIMITATIONS.md and docs/external-connectors.md.
Expected third-party cost per official run: USD 0 for the default batch.
Secrets: None required by the default batch; optional provider credentials are
         server-side environment variables only.
```

The default bounded command does not enable Firecrawl Search. A hosted AI model key is not needed unless an
optional model connector is enabled; Builderr states that a scoring key can be
requested if one is needed. The optional GPT-assisted command adds
`--model-assist` after configuring `GROQ_API_KEY(S)` or the generic model-key
aliases, the compatible endpoint/model, `MAX_LLM_CALLS`, `MAX_LLM_TOKENS`,
`MAX_COST_USD`, the per-call upper-bound cost and the persistent daily ledger.
The model only extracts claims from retained verified-site evidence;
deterministic identity and publication gates remain in force.

`--planner-assist` is an additional development experiment, not part of the
default submission command. It can select an allow-listed website candidate or
invoke one transient Firecrawl search under the shared search/request/cost budgets;
raw Firecrawl search results are discarded and independently fetched pages remain the
only publication evidence. The default submission declaration therefore still
lists no model or search provider.

The model transport integration is covered by
`reports/model-assist-integration-100.md`; that check uses a local provider
fixture because no real credential is stored in the repository. The real model
key must be injected into the evaluator environment.
