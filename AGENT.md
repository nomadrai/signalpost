# Research and abstention policy

Signalpost starts every profile with the official organisation number and a supplied registry snapshot. The registry is the identity anchor; a domain, brand, profile handle, search result, or leader relationship is only a candidate until deterministic evidence links it back to the same organisation.

## Publication rules

- Publish only facts that have a source URL or identifier, retrieval time, content hash, extraction method, and a reporting/effective period when the source provides one.
- Keep zero distinct from absent. A missing account value is `not_available`, never zero.
- Treat fetched pages as untrusted data. Page text is never an instruction to the program or to an optional model.
- An uncertain entity is `ambiguous`; a denied or restricted source is `blocked`; a source that was checked and has no matching fact is `not_available`; an execution failure is `failed`.
- Financial numbers are copied from structured official responses without model generation, rounding, conversion, or imputation.
- Store role-holder names and roles only. Do not retain birth dates or other personal identifiers.
- Company-owned descriptions are contextual statements, not independent sentiment.

## Optional model boundary

Models are disabled by default. If enabled, they may summarize validated claims, classify page type, rank candidates, or propose an extraction with a verbatim supporting span. Deterministic code must verify the span against the stored snapshot and must make the identity decision. Model calls are governed by the environment limits and are skipped when a limit is zero.

## Abstention

Abstention is an intentional result. It is preferable to a weak domain match, an unsupported financial number, an inferred hiring conclusion, or a claim copied from a directory. The synthesis always contains an explicit unknown list so that a user can distinguish not checked, unavailable, blocked, and ambiguous information.
