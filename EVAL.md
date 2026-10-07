# Measurement guide

The product reports terminal coverage, exact-entity publication, claim evidence completeness, refresh correctness, runtime p50/p95, request count, bytes, and declared third-party cost.

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

## Promotion gate

A change is retained only when it adds supported coverage without a new wrong-company publication, preserves evidence completeness, keeps financial values source-derived, and stays within the configured runtime/request budget. Test identity collisions, parent/group pages, parked domains, directories, redirects, missing websites, empty accounts, and malformed inputs.

The checked-in smoke report is generated from the exact command and records measured values rather than estimates.
