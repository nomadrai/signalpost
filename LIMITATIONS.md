# Limitations and source rights

- The official registry and annual-account endpoints are used as public Norwegian sources. Their responses are retained with URL, retrieval time, hash, and reporting period. Registry bulk data is used as the identity snapshot.
- Company pages are public but company-controlled. They support descriptions, declared contacts, links, and dated activity only after exact-entity verification. Promotional copy is not independent sentiment evidence.
- Robots rules, terms, rate limits, content size, redirect safety, and server load are respected. A missing or denied source remains visible as a state.
- Restricted platforms such as LinkedIn, Meta services, Glassdoor, and Indeed are not scraped. A permitted API or licensed export would need its own connector, rights declaration, retention policy, and evidence gate.
- Search results are discovery input only. They are not retained as claim evidence unless an independently fetched page passes identity and evidence validation.
- Browser rendering, OCR, heavy language models, and third-party search are optional. The deterministic registry pass continues when these components are absent or their budgets are zero.
- There is no promise that every Norwegian entity has annual accounts, a website, a public role holder, a workplace, a job, or dated activity. Unknown is a valid product result.
- The current identity baseline still includes a legacy legal-name path for starter compatibility. Exact organisation-number evidence is preferred, and stronger independent corroboration is needed before broadening publication.
- The bounded runner currently requires POSIX process groups and interval timers. It is verified on Linux. The final supervisor guard exits with code 124 if checkpoint recovery itself stalls; the last atomic checkpoint remains intact.
- The 1,000/1,100-company checks use matching normalized identity rows with no live requests. The capped live check covers 100 companies. Full-size live coverage under 2,000 attempts has not yet been measured, and depends on which official response snapshots are supplied.
- Killing a stalled task can lose its unreturned response body, but cannot mutate a published parent profile or erase its reserved request count. Byte/latency metrics include returned results; request accounting includes reserved in-flight attempts.
