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
| Discover website candidates | Opt-in bounded planner with transient Brave search; standalone experiment also available | Model credentials plus `BRAVE_SEARCH_API_KEY`, declared search price and search allowance |
| Extract hiring/activity or select a research action | Optional evidence assistant and single-action planner; current answers/synthesis remain deterministic | `GROQ_API_KEY(S)` or `SIGNALPOST_MODEL_API_KEY(S)` with `--model-assist` or `--planner-assist` |

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

Groq documentation reviewed on 2026-10-13:

- [GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b)
  supports JSON object/schema modes, tool use and browser search. Published
  prices are **$0.15/M input tokens and $0.60/M output tokens**.
- [Rate limits](https://console.groq.com/docs/rate-limits) are organization-wide.
  The published free-plan example is 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD;
  the account limits page is authoritative for the configured organization.
  Groq 429s set a shared cooldown across this run's workers and credentials;
  another key does not grant additional organization quota.
- [Browser search](https://console.groq.com/docs/tool-use/built-in-tools/browser-search)
  uses Exa and is incompatible with structured outputs.

The first hosted-model integration test is the point at which a model key is
needed in development. At runtime it is needed only when that optional stage is
called, for example after fetching evidence for extraction or after validating
claims for synthesis. The optional planner calls a model before website
retrieval. Exact-company publication remains deterministic.

`--planner-assist` enables that bounded planner explicitly. It receives the
identity snapshot and an allow-list of deterministic website candidates, then
returns one `fetch_url`, `search_company`, or `stop` action. The controller
rejects arbitrary URLs and malformed searches. If Brave credentials and a
positive `MAX_SEARCH_CALLS` allowance and declared search price are present, one transient search may
produce a candidate URL; raw search results are discarded before the profile is
written. The website crawler independently fetches and identity-gates the URL.
This is one model action per company, followed by at most one search and the
bounded website task. `stop` ends planner work; other requested deterministic
modules still run. `--discover-websites` makes legal-name candidates available
to the planner. Planner tasks precede website tasks, so model/search attempts
consume the same allocation that would otherwise be available to enrichment.

### GPT-assisted evidence mode

The repository includes an optional OpenAI-compatible evidence assistant. Enable
it explicitly with `--model-assist`. The model receives only replayable pages
already fetched from a verified first-party company site and proposes hiring or
dated-activity items. Deterministic validation requires the retained page URL,
exact content hash, same-host item URL, source date and a verbatim evidence quote
before a claim can enter the envelope. Page content is treated as untrusted data,
not as instructions to the model.

Example configuration for Groq's OpenAI-compatible endpoint:

```bash
export GROQ_API_KEY='your-server-side-key'
export SIGNALPOST_MODEL_ENDPOINT='https://api.groq.com/openai/v1/chat/completions'
export SIGNALPOST_MODEL='openai/gpt-oss-120b'
export MAX_LLM_CALLS=100
export MAX_LLM_TOKENS=250000
export MAX_COST_USD=10
# Zero here selects the built-in Groq price, not free Groq inference.
export SIGNALPOST_MODEL_COST_PER_CALL_USD=0
export SIGNALPOST_DAILY_COST_CAP_USD=10
export SIGNALPOST_DAILY_COST_LEDGER="$HOME/.cache/signalpost/daily-cost.json"
```

`GROQ_API_KEYS` accepts a comma-separated pool. Only one credential namespace
is selected: explicit `SIGNALPOST_MODEL_API_KEY(S)`, otherwise Groq, OpenAI,
then the generic AI alias. Keys from different providers are never combined.
The selected namespace supplies its endpoint default; an explicit
`SIGNALPOST_MODEL_ENDPOINT` overrides that default. Pools distribute calls
across credentials; generic providers may fail over once after a 429, while
Groq applies the shared cooldown above. Other HTTP failures do not trigger
credential failover. Credential-bearing requests refuse redirects.

For Groq GPT-OSS 120B, reservations use UTF-8 input bytes plus a chat-framing
allowance as a conservative input-token bound, and reserve the full configured
completion allowance (including reasoning). An explicit per-call price can
raise this bound. Other provider/model pairs require an explicit
`SIGNALPOST_MODEL_COST_PER_CALL_USD`; zero declares a genuinely free fixture or
allocation. Missing or invalid pricing disables those model calls. Reservations
are not refunded after failure, so reports represent a cost upper bound rather
than an invoice. Every retry reserves fresh request/token/cost allowances.

Search additionally requires `BRAVE_SEARCH_API_KEY`, positive `MAX_SEARCH_CALLS`
and an explicit finite `SIGNALPOST_SEARCH_COST_PER_CALL_USD` for the selected
plan. Zero is allowed only as a declaration of a free allocation. Search prices
and retention rights depend on that plan; a key does not establish either.

The existing standalone Brave script remains a separate experiment. The
`--planner-assist` adapter uses the shared HTTP request ledger, monetary
reservations, deadlines and terminal output, but is not part of the default
bounded run. Setting the Brave environment variable alone does not add search
to `run_batch.py`.

Groq's built-in browser search is also not the active evidence connector:
provider documentation says it is incompatible with structured outputs, and
its final answer contains provider-selected web snippets rather than the
replayable page captures required by the Signalpost evidence contract. The
bounded planner therefore uses the transient Brave adapter only when explicitly
enabled and retains no raw search response; independently fetched pages remain
the only publication evidence.

`MAX_LLM_CALLS`, `MAX_LLM_TOKENS`, `MAX_SEARCH_CALLS` and `MAX_COST_USD` configure
allowance/reservation machinery. They default to zero. A provider key alone does
not enable model calls; an opt-in stage and allowances are required. The runner
defaults to a separate **USD 10 UTC-calendar-day** cap at
`~/.cache/signalpost/daily-cost.json`. `SIGNALPOST_DAILY_COST_CAP_USD` can lower
it (zero refuses paid reservations). `SIGNALPOST_DAILY_COST_LEDGER` selects a
shared persistent path, which must remain the same across invocations and be
preserved across container restarts. This is not a rolling 24-hour window.

The ledger uses bounded POSIX file locking, atomic replacement and filesystem
sync, stores hashed key identifiers, and refuses malformed, inaccessible or
future-dated state. `SIGNALPOST_MODEL_REQUESTS_PER_KEY_PER_DAY` adds an optional
local request cap; it is not the provider's organization quota. Model and search
reservations share this ledger as well as the per-run cost cap.
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

### Local credential file

From the product repository directory (the directory containing `pyproject.toml`),
create a private local copy of the placeholder template if one does not exist:

```bash
cp -n .env.example .env.local
chmod 600 .env.local
```

Edit `.env.local` in your editor. Set `GROQ_API_KEY` to one Groq key; keep the
generic `SIGNALPOST_MODEL_API_KEY(S)` variables empty so they do not take
precedence. Keep the Groq endpoint and `openai/gpt-oss-120b` model from the
template. Set positive `MAX_LLM_CALLS`, `MAX_LLM_TOKENS` and `MAX_COST_USD`
allowances using the example above. A single key is sufficient; multiple Groq
keys do not increase organization-wide quotas.

For search, also set `BRAVE_SEARCH_API_KEY`, positive `MAX_SEARCH_CALLS` and
the chosen plan's USD-per-request `SIGNALPOST_SEARCH_COST_PER_CALL_USD`. Without
search, leave the Brave key empty and `MAX_SEARCH_CALLS=0`. Public registry
requests and direct company-page retrieval need no API key.

Load the file into the same Bash session that runs the batch:

```bash
set -a
source ./.env.local
set +a
```

Then add `--model-assist` for captured-page extraction and/or `--planner-assist`
for bounded candidate selection to the documented batch command. Loading keys
alone does not enable either stage.

The repository ignores `.env` and `.env.*`, with an explicit exception for the
tracked `.env.example`. Keep actual keys in `.env.local`, not `.env.example` or
Python files. Verify the rule without printing any credentials:

```bash
git check-ignore -v .env.local
```

The release install uses `uv sync --locked --python 3.12`; `uv run --no-sync`
then executes the already-installed locked environment without rewriting the
lockfile. Runtime candidate `21b5452` passed this procedure.
