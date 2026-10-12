# Runtime and credentials

Reviewed against the public requirements on 2026-10-11:

- [Challenge page](https://builderr.ai/challenges/signalpost)
- [Participant brief](https://builderr.ai/starter-briefs/signalpost.md)
- [Evaluation contract](https://builderr.ai/docs/signalpost-evaluation-harness.md)
- [Agent playbook](https://builderr.ai/starter-briefs/signalpost-agent-playbook.md)
- [Source policy](https://builderr.ai/starter-briefs/signalpost-sources.md)

## Inputs and release preparation

Local preparation uses the public universe and a local smoke-test batch. The
runtime receives the supplied company-number file and frozen identity registry
snapshot. Those evaluation inputs arrive at run time; receiving them locally is
not a prerequisite for submitting code and the required 100-company smoke report.

The published contract promises an identity registry snapshot. It does not
promise saved accounts, roles, subunit or website responses. `--response-snapshot`
is an optional adapter for declared saved responses; the default live allocation
must work without it. Missing enrichment remains an explicit availability state.

The 2,700-second, 2,000-attempt and USD 10 limits are user-confirmed operating
limits. The public documents reviewed here state that a common resource budget
is supplied, but do not publish those numerical limits. CPU/memory, network policy
and any provider provisioning details still need confirmation for deployment.

## Three meanings of search

| Operation | Current implementation | Credentials |
|---|---|---|
| Find an existing company by name/number | Static viewer filters generated cards in the browser | None |
| Research a company from its number | Batch runner reads the identity snapshot, calls public official endpoints and crawls candidate company pages | No model or paid-search key in the default path |
| Discover candidates through a web search service | Standalone Brave experiment; not integrated into the bounded batch | `BRAVE_SEARCH_API_KEY` for that script |
| Interpret flexible questions or generate model-assisted summaries | Optional OpenAI-compatible evidence mode; current answers/synthesis remain deterministic | `SIGNALPOST_MODEL_API_KEY` only when `--model-assist` is enabled |

The static viewer does not submit new crawl jobs when a visitor types a company
number. On-demand research from the UI would need a backend job endpoint and
result retrieval. That plumbing does not itself require an AI model.

`scripts/ask_agent.py` uses deterministic filtering of existing profile evidence.
Its name does not mean it makes a hosted-model request. Likewise,
`--discover-websites` constructs legal-name domain candidates; it does not enable
Brave search or any model provider.

## Optional provider integration

The challenge page and playbook explicitly offer a model key for scoring on
request. They do not specify the provider/model or promise a web-search key,
model web-search tool access, or development credentials. Confirm those details
before choosing a provider-dependent route. Reproduction must not depend on an
entrant's private service session or account-bound credentials.

The first hosted-model integration test is the point at which a model key is
needed in development. At runtime it is needed only when that optional stage is
called, for example after fetching evidence for extraction or after validating
claims for synthesis. A future natural-language query planner could call a model
earlier, before retrieval. Exact-company publication remains deterministic.

### GPT-assisted evidence mode

The repository includes an optional OpenAI-compatible evidence assistant. Enable
it explicitly with `--model-assist`. The model receives only replayable pages
already fetched from a verified first-party company site and proposes hiring or
dated-activity items. Deterministic validation requires the retained page URL,
exact content hash, same-host item URL, source date and a verbatim evidence quote
before a claim can enter the envelope. Page content is treated as untrusted data,
not as instructions to the model.

Example configuration for an OpenAI-compatible provider:

```bash
export SIGNALPOST_MODEL_API_KEY='...'
export SIGNALPOST_MODEL_ENDPOINT='https://api.openai.com/v1/chat/completions'
export SIGNALPOST_MODEL='openai/gpt-oss-120b'
export MAX_LLM_CALLS=100
export MAX_LLM_TOKENS=250000
export MAX_COST_USD=10
export SIGNALPOST_MODEL_COST_PER_CALL_USD=0
```

Use the actual provider endpoint and model identifier. Set
`SIGNALPOST_MODEL_COST_PER_CALL_USD` to a conservative upper bound when calls
are billable. Each model request reserves one outbound HTTP attempt and appears
under `model_signals` in the run report. Missing credentials, zero allowances,
timeouts or invalid JSON fall back to explicit unavailable states and never
fabricate a claim.

The existing Brave script is a separate experiment. It must be integrated with
the shared HTTP request ledger, monetary reservations, deadlines and terminal
output before becoming part of the default bounded run. Setting its environment
variable alone does not add search to `run_batch.py`.

`MAX_LLM_CALLS`, `MAX_LLM_TOKENS`, `MAX_SEARCH_CALLS` and `MAX_COST_USD` configure
allowance/reservation machinery. They default to zero. A provider key alone does
not enable model calls; `--model-assist` and positive allowances are required.
A new connector needs explicit pricing, a model/version where applicable,
timeouts, usage reporting and a deterministic fallback. Search and model calls
share the monetary cap and consume the common HTTP-attempt budget.

The bounded report now attributes HTTP attempts and local tasks to each requested
field family. This prevents an aggregate no-improvement result from being
misread when a later strategy received no attempts because earlier field families
exhausted the allowance.

Real keys belong in the backend process environment, never generated HTML or
browser JavaScript. `.env.example` lists configuration names; the runner reads
process environment variables and does not automatically load a `.env` file.

The release install uses `uv sync --locked --python 3.12`; `uv run --no-sync`
then executes the already-installed locked environment without rewriting the
lockfile. Runtime candidate `21b5452` passed this procedure.
