# Model-assisted integration check

Date: 2026-10-12.

This is a local integration check of the optional OpenAI-compatible model path.
The development environment did not contain a real provider key, so the test
used a local HTTP server that returned a valid empty JSON result. It verifies
transport, worker, budget, request-ledger, fallback and terminal-envelope
behavior without claiming external model coverage.

The model path was enabled with:

```bash
MAX_LLM_CALLS=100
MAX_LLM_TOKENS=500000
MAX_COST_USD=0
SIGNALPOST_MODEL_COST_PER_CALL_USD=0
--model-assist
```

The local provider returned `{"items": []}` for each call.

| Measurement | Result |
|---|---:|
| Inputs / terminal envelopes | 100 / 100 |
| Verified websites eligible for model stage | 5 |
| Model calls | 5 |
| Model HTTP attempts | 5 |
| Reserved model tokens | 19,604 |
| Declared model cost | USD 0 |
| Unattributed requests | 0 |
| Request attribution reconciled | Yes |
| Envelope/evidence validation | Passed |

The other 95 model tasks were skipped with `model_no_verified_website`. The
model stage cannot run before deterministic exact-company website verification.
An unavailable key, exhausted allowance, timeout or invalid model JSON produces
an explicit skip/failure state and no model-derived claim.

The real `openai/gpt-oss-120b` key should be supplied through
`SIGNALPOST_MODEL_API_KEY` and its actual OpenAI-compatible endpoint. No key is
stored in this repository or in generated output.
