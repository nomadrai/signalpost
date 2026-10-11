# Release conformance follow-up

Date: 2026-10-08.

This report records checks run after the v3 identity and first-party signal
follow-up. The JSONL tooling now
preserves Unicode line separators inside captured page text.

## Verification environment

- Python 3.12.15 provisioned with `uv`.
- Runtime dependencies installed from the frozen `uv.lock`.
- Pytest installed only in the temporary verification environment, as the
  project documents it as an invocation-time test dependency.
- A clean clone at `c19fb4b` was installed in a separate temporary
  environment and produced the same passing test result.

## Checks passed

| Check | Result |
|---|---|
| Full test suite at this checkpoint | 132 passed, 5 subtests passed |
| Matching 1,000-company run | 1,000 available envelopes, 0 requests, validation passed |
| Matching 1,100-company run | 1,100 available envelopes, 0 requests, validation passed |
| Universe attribution | 411,160 rows; SHA-256 `b82d6a3e7231d1759a958c282bc4366b80ec2fab8095053d8ed7fa9cd01bc838` |
| Refresh replay | 2 expected changes, zero false changes, idempotent rerun |
| Evidence validation | Passed for the 1,000-company output, saved wrapper smoke output, and interrupted live checkpoint |
| Static viewer | Built 1,004 files for 1,000 profiles; structural HTML checks passed |
| Deadline regression | Passed after including implementation import time and tightening worker reaping |
| JSONL Unicode regression | Passed in evidence validation and supervisor recovery; physical LF records remain valid when captured text contains U+2028 |
| Saved-response scalability | Synthetic 1,000-company map: 1,000 snapshot reads, 0 requests, validation passed; resume: 0 duplicate reads |

The reproducible large-run artifacts are under the temporary verification
directory used for this check and are not product data. The committed public
coverage reports remain `bounded-smoke-100.md` and
`coverage-follow-up-100.md`.

The clean-clone verification at `c19fb4b` covered the preceding 131-test tree.
The `873ade5` tree added the checkpoint-audit regression test and passed the
full 132-test suite locally. A later credential-free follow-up adds local signal
extraction and module-attribution tests; its 135-test result is recorded in
`reports/coverage-allocation-100.md` and is not a replacement for this dated
historical conformance table.

The saved-response scalability check used a temporary synthetic response map
solely to exercise the supplied-response interface at 1,000 companies. Its
financial values are test fixtures, not official observations, and are not
included as coverage or evidence claims in the product reports.

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

## Retained full-size identity review

The interrupted 1,000-company checkpoint retained 64 fetched website cases:
21 publishable and 43 withheld. Replaying the current deterministic identity
gate against all 64 stored captures reproduced every stored assessment with
zero mismatches.

The 21 published cases were reviewed page by page. Seven had an exact
organisation number in homepage identity evidence; the other 14 had an exact
legal-name match plus registered street and postcode/city corroboration. All
21 had an exact assessment, a proof URL matching the fetched source URL, a
64-character content hash, at least one replayable page document, and no
conflicting organisation number. The cases with blank homepage identity
excerpts were supported by a captured contact/about page or structured/main
page content, including Rana Hundesenter, Fokus Golf, and Tromsøterminalen.

All 43 withheld fetched cases were `ambiguous`, carried no published website
claim, and had no publishable identity assessment. The separate 15 blocked and
25 failed website outcomes had no retained page capture and were not retried;
they remain unresolved until a new authorized live allocation or supplied
response captures are available.

## UI check

The viewer contains a viewport declaration, responsive auto-fit card grids,
search and state filtering, profile source links, comparison controls, and a
change-history page. A generated-output check found 1,000 data rows and
profile pages, 1,000 index cards, three comparison selectors, a viewport
declaration, and no unsafe `javascript:`/`data:` HTML URLs. Playwright
Chromium 151.0.7922.34 then loaded the generated viewer at both required
viewport sizes. Search, state filtering, comparison, profile navigation, and
browser-console checks passed with no page or console errors. Screenshots were
written to `ROOT/runs/ui-screenshots/`:

- `mobile-390x844.png` — 390 × 844 viewport.
- `desktop-1280x900.png` — 1,280 × 900 viewport.

The browser required locally extracted Debian runtime libraries in this
sandbox; no product dependency or viewer code change was needed for the
check.

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

## Fresh bounded full-size live allocation

A separate fresh run used the same 1,000-company conformance input with the
confirmed 2,700-second deadline and 2,000-attempt shared cap. It completed with
all terminal rows and a final runner report:

| Check | Result |
|---|---|
| Input/output | 1,000 / 1,000 unique envelopes |
| Elapsed | 381.61 seconds |
| HTTP attempts | 2,000 reserved; 0 remaining |
| Declared third-party cost | USD 0 |
| Accounts | 661 available, 339 not available |
| Websites | 28 available, 46 ambiguous, 14 blocked, 22 failed |
| Company-owned profiles | 14 available |
| Hiring/activity | 0 published items |
| Evidence validation | Passed |

The run selected identities from the supplied normalized universe and is not an
official Builderr batch. No official response snapshot was supplied, so this
result measures bounded live behavior and accounting rather than final daily-run
coverage. The reproducible artifacts are under
`ROOT/runs/release-live-1000-e276605/`; the network-free audit tool is
`scripts/audit_batch_checkpoint.py`.

## Release follow-up — clarified 2026-10-11

The [published contract](https://builderr.ai/docs/signalpost-evaluation-harness.md)
and [participant brief](https://builderr.ai/starter-briefs/signalpost.md) supply the
official company batch at evaluation time and require a local 100-company smoke
report for submission. An official-batch run is not a pre-submission dependency.
The promised frozen registry snapshot anchors identity; saved accounts, roles,
subunit and website responses are not promised. Earlier wording here incorrectly
treated an official batch or optional response map as a local release blocker.

1. Verify installation, the exact run command and evidence output at the chosen
   final candidate revision, and complete its release package.
2. Improve measured external coverage and request allocation without relying on
   saved enrichment responses. Retained blocked/failed cases can be investigated
   within a new bounded allocation; honest unavailable states remain valid output.
3. Confirm deployment resource/network details and any optional provider access.
   The default runner requires no hosted-model or search-provider credential.

Only an actual official evaluation can establish the score or qualification.
See [runtime and credentials](../docs/runtime-and-credentials.md) for the input
and API-key distinctions.
