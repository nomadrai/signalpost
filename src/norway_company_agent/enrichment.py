from __future__ import annotations

import time

from .budget import request_scope
from .identity import apply_website_identity_gate
from .official import fetch_official_modules
from .snapshots import SnapshotFetcher
from .website import fetch_website
from .discovery import website_candidates
from .company_signals import extract_company_signals
from .evidence import evidence


def enrich_module(task: dict, shared: tuple) -> dict:
    """One field family per task keeps scheduling broad across the batch."""
    budget, saved_responses = shared
    module = task["module"]
    profile = task["profile"]
    started = time.monotonic()
    with request_scope(budget, company_index=task["company_index"],
                       deadline=task["deadline"], max_requests=task["request_limit"]) as scope:
        if module in {"website", "website_discovery"}:
            plan = website_candidates(profile, derived=module == "website_discovery")
            previous = profile.get("evidence", {}).get("website")
            if module == "website_discovery" and ((previous or {}).get("value") or {}).get("identity_assessment", {}).get("publishable"):
                return {"records": {}, "metric": {"requests": 0, "bytes": 0, "latencies_ms": []}}
            attempted = {item["url"] for item in ((previous or {}).get("value") or {}).get("candidate_attempts", [])}
            metric = {"bytes": 0, "latencies_ms": []}
            best = previous
            attempts = []
            for candidate in plan:
                if candidate["url"] in attempted:
                    continue
                record, candidate_metric = fetch_website(candidate["url"], profile=profile, candidate_source=candidate["source"])
                record = apply_website_identity_gate(profile, record)["website"]
                metric["bytes"] += candidate_metric.get("bytes", 0)
                metric["latencies_ms"].extend(candidate_metric.get("latencies_ms", []))
                assessment = (record.get("value") or {}).get("identity_assessment") or {}
                attempts.append({**candidate, "status": record["status"], "assessment": assessment, "note": record.get("note")})
                if best is None or record["status"] == "available":
                    best = record
                if assessment.get("publishable") or record["status"] == "not_fetched":
                    break
            record = best or evidence("website", "not_found", "company_website_candidate", profile.get("website") or "",
                                      note="No crawlable website candidate with independent ownership evidence")
            record.setdefault("value", {})
            if record["value"] is None:
                record["value"] = {}
            record["value"]["candidate_attempts"] = [*((previous or {}).get("value") or {}).get("candidate_attempts", []), *attempts]
            records = {"website": record, **extract_company_signals(profile, record)}
            for page in (record.get("value") or {}).get("pages") or []:
                page.pop("body_gzip_base64", None)
        elif module in {"hiring", "activity"}:
            website = profile.get("evidence", {}).get("website") or {}
            records = extract_company_signals(profile, website)
            metric = {"bytes": 0, "latencies_ms": [], "snapshot_reads": 0}
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
