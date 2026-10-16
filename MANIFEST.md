# Dependency and source manifest

## Runtime

- Python 3.12, pinned by `.python-version`
- Project code licence: MIT, as provided in [`LICENSE`](LICENSE). This licence covers the repository's original code and documentation; it does not grant rights to third-party registry, website, platform, model, or search-provider data.
- `beautifulsoup4`, `extruct`, `lxml`, `pydantic`, `pypdf`, `tldextract`, and `trafilatura` as declared in `pyproject.toml` and locked in `uv.lock`.
- Release installation: `uv sync --locked --python 3.12`; run commands use `uv run --no-sync`; `make test` is the single offline test command. A Dockerfile provides the same locked runtime in a container. The provider integration and website-planning changes are verified by the current test suite; record the final packaging commit in the submission email.
- Scrapy and scrapy-playwright are optional crawl extras. Browser binaries are not required for the deterministic batch path.

## Sources

- Brønnøysundregistrene Enhetsregisteret: legal identity, addresses, industry, employees, roles, group structure, and subunits.
- Brønnøysundregistrene Regnskapsregisteret: structured annual accounts and available filing years.
- Registry-linked company pages: company-controlled descriptions, declared profiles, contacts, and dated public pages after identity verification.

## Models and APIs

The submitted primary path uses OpenAI native `gpt-5.6-sol` plus bounded Firecrawl Search. The cheaper alternative uses Groq `openai/gpt-oss-120b` plus Firecrawl; OpenRouter `openai/gpt-5.6-sol` is also supported. Provider, model/version, acquisition mode, source rights, retention policy, and per-run budget are declared before calls can publish claims. The repository contains only variable names in `.env.example`; real credentials belong in the evaluator environment or an agent-only environment file. The credential pool stores only hashed key identifiers in its daily ledger and honors provider-wide Groq cooldowns rather than using multiple keys to bypass organization limits.

See [runtime and credentials](docs/runtime-and-credentials.md) for the distinction between local viewer search, deterministic research, the standalone Brave experiment, and future hosted-model integration.

## Cost declaration

The submitted provider profile reserves at most USD 10 per official run through the shared cost cap. Actual runtime cost is the sum of explicitly enabled model/search reservations and is recorded per envelope and run report. The no-key local mode remains available and declares USD 0.
