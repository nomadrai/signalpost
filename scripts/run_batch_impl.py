#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import (  # noqa: E402
    profile_complete_for_modules,
    profile_from_bulk_record,
    read_organisation_inputs,
    terminal_envelope,
    validate_envelopes,
)
from norway_company_agent.budget import BudgetGovernor  # noqa: E402
from norway_company_agent.evidence import evidence, utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.official import fetch_official_modules  # noqa: E402
from norway_company_agent.sampling import iter_bulk  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically replace a JSONL checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def append_progress(path: Path, envelope: dict[str, Any], phase: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"phase": phase, "envelope": envelope}, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _deadline_value(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


def _error(code: str, message: str, stage: str) -> dict[str, str]:
    return {"code": code, "message": message[:500], "stage": stage}


def _missing_profile(org: str, reason: str) -> dict[str, Any]:
    return {
        "organisation_number": org,
        "evidence": {
            "registry": evidence(
                "registry",
                "source_error",
                "official_registry_bulk",
                "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                note=reason,
            )
        },
    }


def _load_previous_profiles(path: Path | None) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None or not path.exists():
        return {}, None
    rows = read_jsonl(path)
    profiles = {}
    for row in rows:
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else row
        org = str(profile.get("organisation_number") or row.get("organisation_number") or "")
        if org:
            profiles[org] = profile
    run_id = next((str(row.get("run_id")) for row in rows if row.get("run_id")), None)
    return profiles, run_id


def _checkpoint(
    output_path: Path,
    journal_path: Path,
    latest: dict[str, dict[str, Any]],
    orgs: list[str],
    phase: str,
) -> None:
    rows = [latest[org] for org in orgs if org in latest]
    write_jsonl(output_path, rows)
    for row in rows[-1:] if rows else []:
        append_progress(journal_path, row, phase)


def _build_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    modules: list[str],
    errors: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    previous_run_id: str | None,
    status_override: str | None = None,
) -> dict[str, Any]:
    return terminal_envelope(
        profile,
        run_id=run_id,
        modules=modules,
        started_at=started_at,
        completed_at=completed_at,
        errors=errors,
        previous=previous,
        previous_run_id=previous_run_id,
        status_override=status_override,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost bounded batch runner")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--organisations", dest="organisations", help="JSON, JSONL, or text organisation-number list")
    input_group.add_argument("--input", dest="organisations", help="Alias for --organisations")
    parser.add_argument("--bulk", required=True, help="Frozen Brreg entity snapshot, plain CSV or gzip CSV")
    parser.add_argument("--output", required=True, help="Final terminal envelope JSONL")
    parser.add_argument("--profiles-output", required=True, help="Profile checkpoint JSONL")
    parser.add_argument("--report", required=True, help="Run report JSON")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--checkpoint-every", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--previous-output", help="Previous envelope/profile JSONL for refresh changes")
    parser.add_argument("--deadline-seconds", type=float, default=None)
    parser.add_argument("--company-timeout-seconds", type=float, default=None)
    parser.add_argument("--modules", default="registry,accounting_obligation,registry_live,financials,roles,group,locations,website")
    args = parser.parse_args()

    started_at = utc_now()
    started_monotonic = time.monotonic()
    budget = BudgetGovernor.from_environment()
    deadline_seconds = max(0.0, args.deadline_seconds if args.deadline_seconds is not None else _deadline_value("RUN_DEADLINE_SECONDS", 300.0))
    safety_margin = _deadline_value("RUN_DEADLINE_SAFETY_SECONDS", 5.0)
    company_timeout = max(0.1, args.company_timeout_seconds if args.company_timeout_seconds is not None else _deadline_value("COMPANY_TIMEOUT_SECONDS", 45.0))
    stop_scheduling_at = started_monotonic + max(0.0, deadline_seconds - safety_margin)

    organisation_inputs = read_organisation_inputs(args.organisations)
    orgs = [item["organisation_number"] for item in organisation_inputs]
    expected_count = args.expected_count if args.expected_count is not None else len(orgs)
    if len(orgs) != expected_count:
        raise SystemExit(f"Expected {expected_count} organisations, received {len(orgs)}")
    requested_modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    previous_profiles, previous_run_id = _load_previous_profiles(Path(args.previous_output) if args.previous_output else None)
    output_path = Path(args.output)
    profiles_path = Path(args.profiles_output)

    bulk_path = Path(args.bulk)
    snapshot_sha256 = hashlib.sha256(bulk_path.read_bytes()).hexdigest()
    registry_retrieved_at = utc_now()
    wanted = set(orgs)
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    for row in iter_bulk(bulk_path):
        scanned += 1
        org = str(row.get("organisation_number") or "")
        if org in wanted:
            found[org] = profile_from_bulk_record(row, snapshot_sha256=snapshot_sha256, retrieved_at=registry_retrieved_at)
            if len(found) == len(wanted):
                break

    annotations = {item["organisation_number"]: item for item in organisation_inputs}
    prior_profiles = {str(row.get("organisation_number") or ""): row for row in read_jsonl(profiles_path)} if args.resume and profiles_path.exists() else {}
    if prior_profiles and not set(prior_profiles).issubset(set(orgs)):
        raise SystemExit("Resume profile membership is not a subset of this batch")
    resumed_orgs: set[str] = set()
    profiles: dict[str, dict[str, Any]] = {}
    errors_by_org: dict[str, list[dict[str, Any]]] = {}
    for org in orgs:
        if org in found:
            profile = found[org]
            prior = prior_profiles.get(org)
            if prior and profile_complete_for_modules(prior, requested_modules):
                profile = prior
                resumed_orgs.add(org)
            for key in ("evaluation_split", "sample_slice"):
                if key in annotations[org]:
                    profile[key] = annotations[org][key]
            profiles[org] = profile
        else:
            reason = "Organisation number is absent from the supplied registry snapshot."
            profiles[org] = _missing_profile(org, reason)
            errors_by_org[org] = [_error("registry_snapshot_missing", reason, "pass1")]

    output_path = Path(args.output)
    profiles_path = Path(args.profiles_output)
    journal_path = output_path.with_suffix(output_path.suffix + ".progress.jsonl")
    latest: dict[str, dict[str, Any]] = {}
    pass1_count = 0
    for org in orgs:
        profile = profiles[org]
        if org in found:
            envelope = _build_envelope(
                profile,
                run_id=args.run_id,
                started_at=started_at,
                completed_at=utc_now(),
                modules=[module for module in ("registry", "accounting_obligation") if module in requested_modules],
                errors=errors_by_org.get(org, []),
                previous=previous_profiles.get(org),
                previous_run_id=previous_run_id,
            )
        else:
            envelope = _build_envelope(
                profile,
                run_id=args.run_id,
                started_at=started_at,
                completed_at=utc_now(),
                modules=["registry"],
                errors=errors_by_org.get(org, []),
                previous=previous_profiles.get(org),
                previous_run_id=previous_run_id,
                status_override="failed",
            )
        latest[org] = envelope
        pass1_count += 1
    write_jsonl(output_path, [latest[org] for org in orgs])
    write_jsonl(profiles_path, [profiles[org] for org in orgs])
    for org in orgs:
        append_progress(journal_path, latest[org], "pass1")

    fetch_modules = set(requested_modules) - {"registry", "accounting_obligation", "website"}
    completed_pass2 = 0
    skipped_pass2 = 0
    pass2_errors = 0

    def enrich(profile: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        company_started = time.monotonic()
        records, metrics = fetch_official_modules(profile["organisation_number"], fetch_modules)
        profile.setdefault("evidence", {}).update(records)
        website_metrics = {"requests": 0, "bytes": 0, "latencies_ms": []}
        if "website" in requested_modules:
            website_record, website_metrics = fetch_website(profile.get("website"))
            profile.setdefault("evidence", {})["website"] = apply_website_identity_gate(profile, website_record)["website"]
        metric = {
            "requests": len(metrics) + website_metrics["requests"],
            "bytes": sum(item.bytes_received for item in metrics) + website_metrics["bytes"],
            "latencies_ms": [item.elapsed_ms for item in metrics] + website_metrics["latencies_ms"],
            "runtime_ms": round((time.monotonic() - company_started) * 1000, 3),
        }
        profile["run_metrics"] = metric
        return profile, metric

    pending = [profiles[org] for org in orgs if org in found and org not in resumed_orgs]
    pending.sort(key=lambda item: (not bool(item.get("website")), str(item.get("organisation_number") or "")))
    workers = max(1, int(args.workers))
    executor = ThreadPoolExecutor(max_workers=workers)
    active: dict[Any, tuple[str, float]] = {}
    pending_index = 0
    try:
        while pending_index < len(pending) or active:
            while pending_index < len(pending) and len(active) < workers and time.monotonic() < stop_scheduling_at:
                profile = pending[pending_index]
                pending_index += 1
                future = executor.submit(enrich, profile)
                active[future] = (str(profile["organisation_number"]), time.monotonic())
            if not active:
                break
            remaining = max(0.0, stop_scheduling_at - time.monotonic())
            done, _ = wait(tuple(active), timeout=min(0.25, remaining) if remaining else 0, return_when=FIRST_COMPLETED)
            if not done:
                if time.monotonic() >= stop_scheduling_at:
                    break
                continue
            for future in done:
                org, submitted_at = active.pop(future)
                try:
                    profile, _metric = future.result(timeout=max(0.0, company_timeout - (time.monotonic() - submitted_at)))
                    profiles[org] = profile
                    latest[org] = _build_envelope(
                        profile,
                        run_id=args.run_id,
                        started_at=started_at,
                        completed_at=utc_now(),
                        modules=requested_modules,
                        errors=errors_by_org.get(org, []),
                        previous=previous_profiles.get(org),
                        previous_run_id=previous_run_id,
                    )
                    completed_pass2 += 1
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    item = _error("company_enrichment_failed", message, "pass2")
                    errors_by_org.setdefault(org, []).append(item)
                    pass2_errors += 1
                    latest[org] = _build_envelope(
                        profiles[org],
                        run_id=args.run_id,
                        started_at=started_at,
                        completed_at=utc_now(),
                        modules=requested_modules,
                        errors=errors_by_org[org],
                        previous=previous_profiles.get(org),
                        previous_run_id=previous_run_id,
                    )
                write_jsonl(output_path, [latest[item] for item in orgs])
                write_jsonl(profiles_path, [profiles[item] for item in orgs])
                append_progress(journal_path, latest[org], "pass2")
            if pending_index < len(pending) and time.monotonic() >= stop_scheduling_at:
                break
    finally:
        for future in active:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    if pending_index < len(pending) or active:
        for profile in pending[pending_index:]:
            skipped_pass2 += 1
            org = str(profile["organisation_number"])
            errors_by_org.setdefault(org, []).append(_error("deadline_pass2_skipped", "Best-effort enrichment was not scheduled before the safety margin.", "deadline"))
    for future, (org, _submitted) in list(active.items()):
        # The executor is deliberately not awaited after the deadline. Whether
        # the underlying request is still running or was cancelled, the output
        # must explain why the pass-2 replacement was not published.
        skipped_pass2 += 1
        code = "deadline_pass2_cancelled" if future.cancelled() else "deadline_pass2_incomplete"
        errors_by_org.setdefault(org, []).append(_error(code, "Best-effort enrichment was not completed before the deadline.", "deadline"))

    completed_at = utc_now()
    final_envelopes = []
    for org in orgs:
        # Rebuild rows that were skipped or had a late error so the pass-1 row is
        # still a complete, explicit terminal result.
        final_envelopes.append(
            _build_envelope(
                profiles[org],
                run_id=args.run_id,
                started_at=started_at,
                completed_at=completed_at,
                modules=requested_modules,
                errors=errors_by_org.get(org, []),
                previous=previous_profiles.get(org),
                previous_run_id=previous_run_id,
                status_override="failed" if org not in found else None,
            )
        )
    write_jsonl(output_path, final_envelopes)
    write_jsonl(profiles_path, [profiles[org] for org in orgs])

    operations = {"requests": 0, "bytes": 0, "latencies_ms": []}
    company_runtime = []
    for profile in profiles.values():
        metric = profile.get("run_metrics") or {}
        operations["requests"] += int(metric.get("requests") or 0)
        operations["bytes"] += int(metric.get("bytes") or 0)
        operations["latencies_ms"].extend(metric.get("latencies_ms") or [])
        if metric.get("runtime_ms") is not None:
            company_runtime.append(float(metric["runtime_ms"]))
    latencies = sorted(operations.pop("latencies_ms"))
    operations["p50_ms"] = latencies[max(0, len(latencies) // 2)] if latencies else None
    operations["p95_ms"] = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None
    operations["company_runtime_ms"] = {
        "n": len(company_runtime),
        "p50": sorted(company_runtime)[max(0, len(company_runtime) // 2)] if company_runtime else None,
        "p95": sorted(company_runtime)[min(len(company_runtime) - 1, int(len(company_runtime) * 0.95))] if company_runtime else None,
    }
    operations["third_party_cost_usd"] = 0
    validation = validate_envelopes(final_envelopes, expected_count)
    report = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "elapsed_seconds": round(time.monotonic() - started_monotonic, 3),
        "deadline_seconds": deadline_seconds,
        "deadline_safety_margin_seconds": safety_margin,
        "company_timeout_seconds": company_timeout,
        "expected_count": expected_count,
        "emitted_envelopes": len(final_envelopes),
        "pass1_envelopes": pass1_count,
        "resumed_profiles": len(resumed_orgs),
        "pass2_completed": completed_pass2,
        "pass2_skipped": skipped_pass2,
        "pass2_errors": pass2_errors,
        "modules": requested_modules,
        "registry": {
            "registry_snapshot_sha256": snapshot_sha256,
            "registry_rows_scanned": scanned,
            "requested": len(orgs),
            "selected": len(found),
            "missing": len(orgs) - len(found),
        },
        "operations": operations,
        "budget": budget.report(),
        "validation": validation,
        "progress_journal": str(journal_path),
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if validation["passed"] else 1)


if __name__ == "__main__":
    main()
