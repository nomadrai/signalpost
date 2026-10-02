# Data schema

Every output line is a versioned envelope with `schema_version: "1.0"` and exactly one `organisation_number` from the input.

## Envelope

- `run_id`, `organisation_number`, and terminal `status` (`available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, or `failed`).
- `identity` contains the organisation number, legal name when available, and identity claim IDs.
- `sections` contains `identity`, `accounts`, `leadership`, `workplaces`, `website`, `profiles`, `hiring`, and `activity`. Each has a state and claim IDs.
- `claims` contains stable `claim_id`, field, value, state, evidence references, retrieval time, reporting/effective period, extraction method, identity tier, and confidence.
- `snapshots` contains requested/final URL, HTTP status, redirect chain, retrieval time, content SHA-256, parser version, source class, and access policy.
- `synthesis` contains text, sentences with claim IDs, and an explicit unknown list.
- `refresh` contains the previous run ID and material changes with old/new values and evidence references.
- `errors` contains a code, message, and stage. `operations` contains requests, bytes, latency summary, and declared third-party cost.

`profile`, `modules`, and top-level timestamps remain as compatibility fields for the starter consumer. They do not replace the versioned fields.

## Claim identity

A claim ID is the SHA-256 prefix of organisation number, field, normalized value, and source key. The source key includes URL and content hash. Re-running against the same snapshot therefore preserves claim IDs and does not create duplicate facts.

## Availability

`not_available` means a checked source did not return the requested fact or the source was not present. `blocked` means access policy or robots rules prevented the request. `ambiguous` means evidence exists but does not establish the exact entity. `failed` is reserved for execution or required identity-anchor failures. None of these states means numeric zero.
