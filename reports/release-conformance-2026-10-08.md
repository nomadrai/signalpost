# Release conformance follow-up

Date: 2026-10-08.

This report records checks run after the v3 identity and first-party signal
follow-up. The latest local commit is `a2a1f04`; the pushed baseline is
`c06d9fa`. The JSONL tooling now preserves Unicode line separators inside
captured page text.

## Verification environment

- Python 3.12.15 provisioned with `uv`.
- Runtime dependencies installed from the frozen `uv.lock`.
- Pytest installed only in the temporary verification environment, as the
  project documents it as an invocation-time test dependency.
- A clean clone was installed in a separate temporary environment. Applying
  the working-tree correction there produced the same passing test result.

## Checks passed

| Check | Result |
|---|---|
| Full test suite | 131 passed, 5 subtests passed |
| Matching 1,000-company run | 1,000 available envelopes, 0 requests, validation passed |
| Matching 1,100-company run | 1,100 available envelopes, 0 requests, validation passed |
| Universe attribution | 411,160 rows; SHA-256 `b82d6a3e7231d1759a958c282bc4366b80ec2fab8095053d8ed7fa9cd01bc838` |
| Refresh replay | 2 expected changes, zero false changes, idempotent rerun |
| Evidence validation | Passed for the 1,000-company output, saved wrapper smoke output, and interrupted live checkpoint |
| Static viewer | Built 1,004 files for 1,000 profiles; structural HTML checks passed |
| Deadline regression | Passed after including implementation import time and tightening worker reaping |
| JSONL Unicode regression | Passed in evidence validation and supervisor recovery; physical LF records remain valid when captured text contains U+2028 |

The reproducible large-run artifacts are under the temporary verification
directory used for this check and are not product data. The committed public
coverage reports remain `bounded-smoke-100.md` and
`coverage-follow-up-100.md`.

## Website identity evidence review

The current saved 100-company coverage report contains 17 recorded website
identity cases:

- 5 `available`; all five were publishable and each had exact organisation
  number or exact legal-name plus registered-address corroboration.
- 9 `ambiguous`; none was publishable.
- 1 `blocked`; no claim was published.
- 2 `failed`; no claim was published.

The 17-case metadata review found no available publication backed only by a
name similarity, and no ambiguous/blocked/failed case marked publishable. A
bounded manual fetch review of the 5 published pages confirmed:

| Organisation | Page evidence reviewed | Result |
|---|---|---|
| 987796154 — Byggmester Ulf Johannessen AS | Exact company name; Midtveien 1A, 1526 Moss | Corroborated |
| 980807568 — Stiftelsen Skansehytta Askim | Skansehytta Askim; Lierveien 222, 1814 Askim | Corroborated |
| 965558268 — Hako Elektro AS | Exact company name, address, and organisation number `965558268` | Exact |
| 920186114 — Johan Edvard Devold Møllers stiftelse | Exact name, purpose, domain contact, and organisation number `920 186 114` | Exact |
| 919378875 — Grønsand Gjestegård AS | Grønsand Gjestegård; Grønsandveien 9, 3475 Sætre; company footer | Corroborated |

The 9 ambiguous pages were also checked for a publication upgrade. Sjøloftet,
Ekberg Lous, Vitagile, Kongsvinger IL Ishockey, OBF, Autorisert Landmåler,
CRUX, Bate, and Kiman Woman each lacked exact organisation-number or
registered-address evidence for the requested organisation; OBF and Bate
were clearly parent/service sites, and CRUX exposed conflicting ownership
evidence. They remain withheld. This is a current manual identity audit of
the 14 fetched cases; the two failed and one blocked cases were not retried.

## UI check

The viewer contains a viewport declaration, responsive auto-fit card grids,
search and state filtering, profile source links, comparison controls, and a
change-history page. A generated-output check found 1,000 data rows and
profile pages, 1,000 index cards, three comparison selectors, a viewport
declaration, and no unsafe `javascript:`/`data:` HTML URLs. Playwright and
Chromium were installed in the temporary
verification area, but Chromium could not launch because the sandbox image
lacks `libglib-2.0.so.0`. Therefore 390px and 1280px screenshots were not
produced in this environment.

## Interrupted full-size live allocation

A 1,000-company live allocation was started with the confirmed 2,000-attempt
cap. It wrote 1,000 valid checkpoint envelopes, reserved 1,753 attempts,
left 247 attempts, and declared USD 0 before it was stopped at the user's
request to return to commit/push work. The checkpoint passes evidence
validation and contains 1,000 `available` identity envelopes. No final run
report was written, so this is not a completed full-size coverage result.

The runner correctly fails closed when `--resume` finds checkpoint data but no
matching prior budget report. It must not reset the allowance or infer that
the interrupted run used zero requests. The partial run is therefore retained
as an audit artifact and is not resumed or counted as a submission result.

## Remaining release blockers

1. Complete a full-size live or supplied-response-snapshot allocation. The
   interrupted live attempt is not a final result; no official response
   snapshot contents are currently available, so the completed 1,000/1,100
   checks above remain identity-only and deliberately zero-budget.
2. Perform the fresh page-by-page identity and exact-evidence audit using the
   retained live capture artifacts.
3. Repeat the desktop/mobile screenshot check in an image with the required
   Chromium shared libraries.
4. Push and verify the latest local JSONL-tooling fix before producing a
   submission candidate.
