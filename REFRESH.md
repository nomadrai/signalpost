# Refresh and material changes

A refresh uses the same input membership and organisation-number anchors as the previous run. Registry and source response bytes remain immutable through their content hashes. Stable claims are compared by field and normalized value.

The same snapshot is an idempotent no-op: it keeps the same claim IDs and produces no duplicate change rows. A changed supported value emits the previous value, current value, retrieval/effective metadata, old/new hashes, and a materiality label. Failed best-effort work does not overwrite the last supported claim; it is recorded in `errors` and leaves the field explicitly unavailable for the current run.

The batch command accepts `--previous-output <path>` for the prior envelope JSONL. The `refresh.changes` list is included in each current envelope and the static viewer exposes it on the change-history page.

For a saved-response check:

```bash
python3 scripts/run_refresh_replay.py --manifest tests/fixtures/refresh-snapshots.json --output /tmp/signalpost-refresh.json
```

The replay uses immutable saved responses and verifies expected changes, evidence completeness, and an identical rerun.
