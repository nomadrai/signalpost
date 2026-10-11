# Component decisions

The official challenge path is a bounded Python batch agent, not a hosted
always-on service. The evaluator supplies organisation numbers and a frozen
identity registry snapshot at run time. The current submission path must work
without a model key, search-provider key, browser binary or saved enrichment
responses.

## Selected POC stack

| Need | Component | Decision |
|---|---|---|
| Batch scheduling | Python bounded runner | Process-isolated workers, shared request/cost ledger, deadlines, checkpoints and one terminal envelope per input |
| Crawl scheduling | Synchronous bounded website path | Default official path; Scrapy remains an optional separate crawler experiment |
| JavaScript fallback | Playwright via scrapy-playwright (Apache-2) | Optional experiment only when static extraction detects an incomplete JavaScript shell |
| Structured metadata | extruct (BSD-3) | Parse JSON-LD, microdata, RDFa, and OpenGraph before heuristics |
| Main text | Trafilatura (Apache-2) | Boilerplate-reduced Norwegian/English text extraction |
| Schema validation | Pydantic (MIT) | Typed claims, explicit nullable fields, and reject/abstain behavior |
| Difficult PDFs | Docling (MIT; model licences checked separately) | Only after plain PDF extraction fails on layout or tables |
| Entity matching | Exact organisation number, then RapidFuzz (MIT) | Organisation number is authoritative; fuzzy matching only queues unresolved candidates |
| Storage | JSONL checkpoints and immutable evidence snapshots | Dependency-light evaluator artifact; generated runs stay outside tracked source |

The current bounded runner reserves every HTTP attempt before transport,
including retries, redirects and robots requests. It kills stalled workers,
preserves atomic checkpoints, carries usage through resume, and keeps exact
identity decisions in deterministic code. A local 1,000-company live allocation
completed within the configured request/deadline limits, but local coverage is
not an official Builderr score.

## Rejected as the foundation

- LLM-first and browser-agent crawlers: too costly and nondeterministic for bulk evidence collection.
- Firecrawl as the core: capable, but its AGPL core/managed extras add unnecessary licensing and stack
  constraints for this POC. It can be a separately measured managed fallback.
- Crawl4AI as the scheduler: useful in an extraction bake-off, but younger and less deterministic than
  Scrapy for queues, retries, and provenance.
- Public LinkedIn, Meta, Indeed, or Glassdoor scrapers: source terms and reproducibility make them an
  unsuitable foundation. Record outbound profile URLs from company sites; use registry or licensed
  sources for employee counts.
- Generic sentiment on company marketing pages: structurally biased. No sentiment score ships before a
  labelled Norwegian news/social evaluation.

## Bake-off contract

Freeze 100 companies, 500 pages, and 30 PDFs across size, legal form, industry, and site technology.
Compare:

1. Scrapy + extruct + Trafilatura.
2. The same stack with a Playwright fallback.
3. Crawl4AI on the identical corpus.
4. A managed Firecrawl run only if its licence/cost is acceptable.
5. An LLM extractor only on deterministic-baseline failures.

Report correct-domain rate, wrong-domain rate, static/JS success, pages per minute, p50/p95 latency,
field precision/recall, evidence-span validity, retry rate, RAM peak, and cost per company. A component
advances only when it improves its target without worsening wrong-company or unsupported-claim rates.
