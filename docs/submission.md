# Submission candidate

This document records the reproducible release procedure for the current
candidate. Builderr supplies the official organisation-number batch and frozen
identity registry snapshot at evaluation time. The local smoke run is evidence
that the command produces one terminal envelope per input; it is not an official
score.

## Current candidate

- Repository: `https://github.com/nomadrai/signalpost`
- Runtime candidate revision verified locally: `b4b7cd9`
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
git checkout b4b7cd9
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
  --profiles-output ROOT/runs/final-smoke-b4b7cd9/profiles.jsonl \
  --output ROOT/runs/final-smoke-b4b7cd9/envelopes.jsonl \
  --report ROOT/runs/final-smoke-b4b7cd9/report.json \
  --run-id final-smoke-b4b7cd9 \
  --expected-count 100 \
  --workers 8 \
  --deadline-seconds 180 \
  --max-requests 200
```

The current clean-clone measurement at `b4b7cd9` produced 100/100 terminal
envelopes in 70.473 seconds, used 200/200 reserved HTTP attempts, declared USD 0, passed
structural validation, and reconciled all requests to field families with zero
unattributed attempts. See `reports/final-candidate-smoke-b4b7cd9.md`.

## Tests and network-free checks

```bash
uv run --no-sync --with pytest pytest -q
uv run --no-sync python scripts/check_batch_limits.py \
  --universe <universe.jsonl> \
  --output-dir <runs>/budget-conformance
```

The current tree passes 135 tests plus 5 subtests. The large zero-request checks
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

The standalone Brave experiment requires `BRAVE_SEARCH_API_KEY` but is not part
of the default bounded command. A hosted AI model key is not needed unless an
optional model connector is enabled; Builderr states that a scoring key can be
requested if one is needed.
