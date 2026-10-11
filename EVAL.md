# Measurement guide

The product reports terminal coverage, exact-entity publication, claim evidence completeness, refresh correctness, runtime p50/p95, request count, bytes, and declared third-party cost.

Builderr supplies the official organisation-number batch and frozen identity
registry snapshot at evaluation time. A local official batch is not required for
submission preparation; the required local artifact is the 100-company smoke
report. The shared official set may grow, so local checks must not hard-code a
permanent maximum. Saved accounts, roles, workplace and website responses are
optional inputs rather than an assumed evaluator dependency.

## Local checks

- Run the complete Python test suite with `PYTHONPATH=src:. python -m pytest -q`.
- Re-open every published claim's referenced snapshot and confirm its locator supports the value.
- Run the same saved snapshot twice and expect equal claim sets and zero changes.
- Run with `RUN_DEADLINE_SECONDS=0` and expect one terminal envelope per valid input with registry pass-1 data where the snapshot contains the row.
- Run on a 100-row random sample and record equal input/output counts, state counts, field coverage, wrong-company manual review, runtime, requests, bytes, and cost.
- Run on at least 1,000 rows with a short simulated deadline to verify output continuity without requiring live enrichment to finish.
- Run `python scripts/check_batch_limits.py --universe <universe.jsonl> --output-dir <runs>/budget-conformance` to verify 1,000 and 1,100 matching identity rows, exact source attribution, absence of fabricated account values, and zero outbound requests.
- Budget tests use a local HTTP server to count retries, redirects, robots, and concurrent process exhaustion independently of reported metrics. They also kill unreturned work, verify shared monetary reservations, exercise saved responses at zero budget, and force supervisor recovery before identity loading finishes.
- Export a saved run with `python scripts/summarize_run.py --envelopes <envelopes.jsonl> --report <report.json> --output <summary.json>`. This validates envelope evidence references and reconciles per-company request totals and the reservation ledger.
- Verify first-party hiring/activity fixtures with `pytest tests/test_company_signals.py`; these tests must reject expired jobs, off-host links, conflicting organisation numbers, and ambiguous sites while retaining page-specific evidence locators.
- Report the models, APIs, licences, source rights and expected cost for the exact candidate revision. The default batch has no hosted-model or paid-search dependency. A hosted model key is needed only when an optional model connector is actually invoked; a search-provider key is separate.

## Promotion gate

A change is retained only when it adds supported coverage without a new wrong-company publication, preserves evidence completeness, keeps financial values source-derived, and stays within the configured runtime/request budget. Test identity collisions, parent/group pages, parked domains, directories, redirects, missing websites, empty accounts, and malformed inputs.

The checked-in smoke report is generated from the exact command and records measured values rather than estimates. The bounded report includes `module_operations` and `request_attribution`; use these fields to decide whether a discovery strategy actually received attempts before promoting or rejecting it.
