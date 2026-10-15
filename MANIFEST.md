# Dependency and source manifest

## Runtime

- Python 3.12+
- `beautifulsoup4`, `extruct`, `lxml`, `pydantic`, `pypdf`, `tldextract`, and `trafilatura` as declared in `pyproject.toml` and locked in `uv.lock`.
- Release installation: `uv sync --locked --python 3.12`; run commands use `uv run --no-sync`. Runtime behavior was verified at `7c51966`; the latest pushed source baseline is `dcdd288`.
- Scrapy and scrapy-playwright are optional crawl extras. Browser binaries are not required for the deterministic batch path.

## Sources

- Brønnøysundregistrene Enhetsregisteret: legal identity, addresses, industry, employees, roles, group structure, and subunits.
- Brønnøysundregistrene Regnskapsregisteret: structured annual accounts and available filing years.
- Registry-linked company pages: company-controlled descriptions, declared profiles, contacts, and dated public pages after identity verification.

## Models and APIs

No model or paid API is called by the default batch. Optional model, search, and licensed connectors must declare provider, model/version, acquisition mode, source rights, retention policy, and per-run budget before they can publish claims. The optional OpenAI-compatible/Groq model path is enabled only with `--model-assist`, server-side `GROQ_API_KEY(S)` or generic model credentials, positive shared allowances, and the configured persistent daily ledger. The bounded planner is separately enabled with `--planner-assist`; it can use transient Firecrawl Search with an explicit search allowance. The repository contains only variable names in `.env.example`; real credentials belong in the environment or an agent-only environment file. The credential pool stores only hashed key identifiers in its daily ledger and honors provider-wide Groq cooldowns rather than using multiple keys to bypass organization limits.

See [runtime and credentials](docs/runtime-and-credentials.md) for the distinction between local viewer search, deterministic research, the standalone Brave experiment, and future hosted-model integration.

## Cost declaration

The deterministic default declares USD 0 third-party API cost. Actual runtime cost is the sum of explicitly enabled provider calls and is recorded per envelope and run report. A zero-budget run must still emit complete terminal envelopes.
