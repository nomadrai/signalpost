# Crawl policy

The main batch uses deterministic registry enrichment first and bounded best-effort HTTP enrichment second. The default website path is synchronous and does not require Scrapy or browser binaries.

## Limits

- Only `http` and `https` are accepted.
- Hostnames and redirect targets are resolved and private, loopback, link-local, multicast, reserved, and metadata addresses are rejected.
- Robots rules are checked before ordinary site requests. The user agent must identify Signalpost and a contact address when configured.
- Static HTML, JSON-LD, OpenGraph, microdata, and readable text are preferred. Targeted same-host pages are followed only when their link text or path indicates contact, about, leadership, locations, news, or activity.
- Response content is bounded by the website byte limit. Redirects, content types, retry count, per-company work, and global deadline are bounded.
- Directory, registry, marketplace, social, and parked hosts are candidate or discovery sources, not official company websites.
- Browser rendering is optional. A JavaScript shell remains `blocked` or `not_available` when the optional browser extra is not installed.
- Legal-name domain candidates are opt-in (`--discover-websites`) and are allocated only after stronger official field families. They cannot be published from name similarity alone.

## Runtime controls

`RUN_DEADLINE_SECONDS` sets the total run limit; `RUN_DEADLINE_SAFETY_SECONDS` reserves time to flush terminal output; `COMPANY_TIMEOUT_SECONDS` is the per-company best-effort budget. The batch continues deterministically when the deadline or an optional API budget is exhausted.

Every request contributes to the run report with request count, bytes, latency, status, and source hash. Generated crawl events and run output belong outside the repository or under ignored output directories.
