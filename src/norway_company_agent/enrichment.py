from __future__ import annotations

import time

from .budget import request_scope
from .identity import apply_website_identity_gate
from .official import fetch_official_modules
from .snapshots import SnapshotFetcher
from .website import fetch_website


def enrich_module(task: dict, shared: tuple) -> dict:
    """One field family per task keeps scheduling broad across the batch."""
    budget, saved_responses = shared
    module = task["module"]
    profile = task["profile"]
    started = time.monotonic()
    with request_scope(budget, company_index=task["company_index"],
                       deadline=task["deadline"], max_requests=task["request_limit"]) as scope:
        if module == "website":
            record, metric = fetch_website(profile.get("website"))
            record = apply_website_identity_gate(profile, record)["website"]
            records = {module: record}
        else:
            kwargs = {"fetcher": SnapshotFetcher(saved_responses)} if task.get("saved") else {}
            records, results = fetch_official_modules(profile["organisation_number"], {module}, **kwargs)
            metric = {
                "bytes": sum(result.bytes_received for result in results),
                "latencies_ms": [result.elapsed_ms for result in results],
                "snapshot_reads": len(results) if task.get("saved") else 0,
            }
        metric["requests"] = scope.requests
        metric["runtime_ms"] = round((time.monotonic() - started) * 1000, 3)
    return {"records": records, "metric": metric}
