#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


# Keep the implementation's own deadline inclusive of module import time when
# it is invoked directly (the public wrapper supplies an even earlier process
# start timestamp through _SIGNALPOST_STARTED_MONOTONIC).
_MODULE_STARTED_MONOTONIC = time.monotonic()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import (  # noqa: E402
    profile_complete_for_modules,
    profile_from_bulk_record,
    read_organisation_inputs,
    terminal_envelope,
    validate_envelopes,
)
from norway_company_agent.budget import BudgetGovernor, RunBudget  # noqa: E402
from norway_company_agent.evidence import evidence, utc_now  # noqa: E402
from norway_company_agent.enrichment import enrich_module  # noqa: E402
from norway_company_agent.official import official_endpoints  # noqa: E402
from norway_company_agent.sampling import iter_bulk, snapshot_sha256 as hash_snapshot  # noqa: E402
from norway_company_agent.workers import BoundedWorkers  # noqa: E402
from norway_company_agent.llm import ModelConfig  # noqa: E402
from norway_company_agent.discovery import website_candidates  # noqa: E402


DEFAULT_PRIORITY = [
    "registry_live", "planner", "website", "financials", "roles", "hiring", "activity",
    "locations", "group", "financial_history", "website_discovery", "model_signals",
]
WORKPLACE_DIAGNOSTIC_PRIORITY = [
    "registry_live", "locations", "planner", "website", "financials", "roles", "hiring", "activity",
    "website_discovery", "model_signals", "group", "financial_history",
]
CATEGORY_PROFILE_TARGETS = {
    "accounts-diagnostic": "financials",
    "leadership-diagnostic": "roles",
    "workplaces-diagnostic": "locations",
    "website-diagnostic": "website",
    "hiring-diagnostic": "hiring",
    "activity-diagnostic": "activity",
    "website-discovery-diagnostic": "website_discovery",
    "group-diagnostic": "group",
    "financial-history-diagnostic": "financial_history",
}
COVERAGE_PROFILE_CHOICES = ("default", "workplace-diagnostic", *CATEGORY_PROFILE_TARGETS)


def priority_for_profile(profile: str) -> list[str]:
    """Return an explicit field-family order with optional diagnostic overrides."""
    if profile == "workplace-diagnostic":
        return list(WORKPLACE_DIAGNOSTIC_PRIORITY)
    target = CATEGORY_PROFILE_TARGETS.get(profile)
    if not target:
        return list(DEFAULT_PRIORITY)
    prerequisites = {"hiring": ["website"], "activity": ["website"], "website_discovery": ["website"]}.get(target, [])
    selected = ["registry_live", *prerequisites, target]
    return selected + [module for module in DEFAULT_PRIORITY if module not in selected]


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
    for line in path.read_text(encoding="utf-8").split("\n"):
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
    parser.add_argument("--bulk", required=True, help="Frozen registry CSV or normalized universe JSONL, optionally gzip")
    parser.add_argument("--output", required=True, help="Final terminal envelope JSONL")
    parser.add_argument("--profiles-output", required=True, help="Profile checkpoint JSONL")
    parser.add_argument("--report", required=True, help="Run report JSON")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--previous-output", help="Previous envelope/profile JSONL for refresh changes")
    parser.add_argument("--deadline-seconds", type=float, default=None)
    parser.add_argument("--company-timeout-seconds", type=float, default=None)
    parser.add_argument("--max-requests", type=int, default=int(os.environ.get("MAX_OUTBOUND_REQUESTS") or "2000"))
    parser.add_argument("--response-snapshot", help="Saved official responses: JSON object with a responses URL map")
    parser.add_argument("--modules", default="registry,accounting_obligation,registry_live,financials,roles,group,locations,website,hiring,activity")
    parser.add_argument("--discover-websites", action="store_true", help="Try conservative legal-name domain candidates after the registry website")
    parser.add_argument("--model-assist", action="store_true", help="Use an optional OpenAI-compatible model only on retained exact-company page captures")
    parser.add_argument("--planner-assist", action="store_true", help="Use an optional bounded model planner for website candidate selection")
    parser.add_argument("--coverage-profile", choices=COVERAGE_PROFILE_CHOICES, default="default",
                        help="Keep default scoring order or opt into a category-priority diagnostic allocation")
    args = parser.parse_args()

    started_at = utc_now()
    started_monotonic = float(os.environ.get("_SIGNALPOST_STARTED_MONOTONIC", _MODULE_STARTED_MONOTONIC))
    governor = BudgetGovernor.from_environment()
    deadline_seconds = args.deadline_seconds if args.deadline_seconds is not None else _deadline_value("RUN_DEADLINE_SECONDS", 2700.0)
    if not math.isfinite(deadline_seconds) or not 0 <= deadline_seconds <= 2700:
        parser.error("--deadline-seconds must be finite and between 0 and 2700")
    if not 0 <= args.max_requests <= 2000:
        parser.error("--max-requests must be between 0 and 2000")
    if not math.isfinite(governor.max_cost_usd) or not 0 <= governor.max_cost_usd <= 10:
        parser.error("MAX_COST_USD must be finite and between 0 and 10")
    if (not math.isfinite(governor.daily_cost_cap_usd) or
            not 0 <= governor.daily_cost_cap_usd <= 10):
        parser.error("SIGNALPOST_DAILY_COST_CAP_USD must be finite and between 0 and 10")
    if (governor.daily_cost_cap_usd or governor.model_requests_per_key_per_day) and not governor.daily_cost_ledger_path:
        parser.error("SIGNALPOST_DAILY_COST_LEDGER is required when a daily cap or per-key limit is enabled")
    safety_margin = _deadline_value("RUN_DEADLINE_SAFETY_SECONDS", 5.0)
    company_timeout = max(0.1, args.company_timeout_seconds if args.company_timeout_seconds is not None else _deadline_value("COMPANY_TIMEOUT_SECONDS", 45.0))
    if not math.isfinite(safety_margin) or not math.isfinite(company_timeout):
        parser.error("Safety margin and company timeout must be finite")
    stop_scheduling_at = started_monotonic + max(0.0, deadline_seconds - safety_margin)

    organisation_inputs = read_organisation_inputs(args.organisations)
    orgs = [item["organisation_number"] for item in organisation_inputs]
    expected_count = args.expected_count if args.expected_count is not None else len(orgs)
    if len(orgs) != expected_count:
        raise SystemExit(f"Expected {expected_count} organisations, received {len(orgs)}")
    requested_modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    if args.discover_websites and "website_discovery" not in requested_modules:
        requested_modules.append("website_discovery")
    if args.coverage_profile == "website-discovery-diagnostic" and not args.discover_websites:
        parser.error("--coverage-profile website-discovery-diagnostic requires --discover-websites")
    if args.model_assist and "model_signals" not in requested_modules:
        requested_modules.append("model_signals")
    if args.planner_assist and "planner" not in requested_modules:
        requested_modules.append("planner")
    if "planner" in requested_modules and not args.planner_assist:
        parser.error("planner requires explicit --planner-assist")
    if args.planner_assist and "website" not in requested_modules:
        requested_modules.append("website")
    allowed_modules = {"registry", "accounting_obligation", "website", "website_discovery", "hiring", "activity", *official_endpoints("000000000")}
    allowed_modules.add("model_signals")
    allowed_modules.add("planner")
    if set(requested_modules) - allowed_modules:
        parser.error(f"Unknown modules: {sorted(set(requested_modules) - allowed_modules)}")
    previous_profiles, previous_run_id = _load_previous_profiles(Path(args.previous_output) if args.previous_output else None)
    model_config = ModelConfig.from_environment()
    output_path = Path(args.output)
    profiles_path = Path(args.profiles_output)

    bulk_path = Path(args.bulk)
    snapshot_sha256 = hash_snapshot(bulk_path)
    registry_retrieved_at = utc_now()
    wanted = set(orgs)
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    for row in iter_bulk(bulk_path):
        scanned += 1
        org = str(row.get("organisation_number") or "")
        if org in wanted:
            found[org] = profile_from_bulk_record(row, snapshot_sha256=snapshot_sha256, retrieved_at=registry_retrieved_at, snapshot_uri=bulk_path.resolve().as_uri())
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
            if prior and (prior.get("evidence", {}).get("registry", {}).get("content_sha256") == snapshot_sha256):
                profile = prior
                if profile_complete_for_modules(prior, requested_modules):
                    resumed_orgs.add(org)
            profile["run_metrics"] = {"requests": 0, "bytes": 0, "latencies_ms": [], "runtime_ms": 0, "snapshot_reads": 0}
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

    # The POSIX supervisor already provides process-tree isolation. Forking on
    # POSIX also avoids paying a full application-import cost before a short
    # deadline can even start the first enrichment task; retain spawn for
    # platforms where fork is unavailable.
    context = multiprocessing.get_context("fork" if os.name == "posix" else "spawn")
    budget = RunBudget(max_requests=args.max_requests, deadline=stop_scheduling_at,
                       companies=len(orgs), governor=governor, context=context,
                       ledger_path=str(output_path.with_suffix(output_path.suffix + ".budget.jsonl")), run_id=args.run_id,
                       modules=tuple(requested_modules), model_keys=model_config.credentials,
                       model_requests_per_key=model_config.requests_per_key_per_day)
    resume_budget_unknown = False
    if args.resume and prior_profiles:
        report_path = Path(args.report)
        prior_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        if prior_report.get("run_id") == args.run_id and "budget" in prior_report:
            previous_budget = prior_report["budget"]
            budget.requests.value = int(previous_budget.get("outbound_requests", args.max_requests))
            budget.cost.value = budget._cost_units(float(previous_budget.get("cost_usd", 0)))
            budget.llm_calls.value = int(previous_budget.get("llm_calls", 0))
            budget.llm_tokens.value = int(previous_budget.get("llm_tokens", 0))
            budget.search_calls.value = int(previous_budget.get("search_calls", 0))
            elapsed_before_resume = float(prior_report.get("elapsed_seconds", 0))
            started_monotonic -= elapsed_before_resume
            stop_scheduling_at -= elapsed_before_resume
            budget.deadline = stop_scheduling_at
        else:
            # An interrupted run can have sent requests absent from its last
            # checkpoint. Fail closed instead of resetting the daily allowance.
            budget.requests.value = args.max_requests
            resume_budget_unknown = True
    initial_requests = budget.requests.value
    Path(budget.ledger_path).write_text(json.dumps({"run_id": args.run_id, **budget.report()}) + "\n", encoding="utf-8")
    saved_responses = json.loads(Path(args.response_snapshot).read_text(encoding="utf-8")) if args.response_snapshot else {}
    if saved_responses and not isinstance(saved_responses.get("responses"), dict):
        parser.error("--response-snapshot must contain a responses URL map")
    completed_orgs = set()
    skipped_orgs = set()
    pass2_errors = 0
    completed_tasks = 0
    skipped_tasks = 0
    coverage_profile = args.coverage_profile
    priority = priority_for_profile(coverage_profile)
    module_operations = {
        module: {"planned_tasks": 0, "started_tasks": 0, "completed_tasks": 0,
                 "failed_tasks": 0, "skipped_tasks": 0, "skip_reasons": Counter(),
                 "local_tasks": 0, "snapshot_reads": 0, "bytes": 0, "runtime_ms": 0.0}
        for module in priority if module in requested_modules
    }
    tasks = []
    for module in priority:
        if module not in requested_modules:
            continue
        for index, org in enumerate(orgs):
            if org not in found or profile_complete_for_modules(profiles[org], [module]):
                continue
            saved = module not in {"website", "website_discovery", "hiring", "activity", "model_signals", "planner"} and official_endpoints(org)[module][0] in saved_responses.get("responses", {})
            tasks.append({"module": module, "organisation_number": org, "company_index": index, "saved": saved})
            module_operations[module]["planned_tasks"] += 1
    # Supplied responses require no live requests and precede all network work.
    tasks.sort(key=lambda task: not task["saved"])
    workers = max(1, int(args.workers))
    pool = BoundedWorkers(enrich_module, (budget, saved_responses), workers, context=context)
    pending_index = 0
    dirty = set()
    active_module = None

    def skip(task, reason):
        nonlocal skipped_tasks
        org, module = task["organisation_number"], task["module"]
        if module in {"website", "website_discovery", "hiring", "activity"}:
            url, source_type = profiles[org].get("website") or "https://data.brreg.no/enhetsregisteret/api/enheter", "registry_linked_company_website"
        elif module in {"model_signals", "planner"}:
            url, source_type = "", "model_assisted_extraction"
        else:
            url, source_type = official_endpoints(org)[module]
        profiles[org].setdefault("evidence", {})[module] = evidence(module, "not_fetched", source_type, url, note=reason)
        skipped_orgs.add(org)
        skipped_tasks += 1
        module_operations[module]["skipped_tasks"] += 1
        module_operations[module]["skip_reasons"][reason] += 1
        code = (
            "deadline_pass2_skipped" if reason == "run_deadline"
            else "model_assist_skipped" if reason.startswith("model_")
            else "request_budget_exhausted"
        )
        if not any(item["code"] == code for item in errors_by_org.get(org, [])):
            errors_by_org.setdefault(org, []).append(_error(code, reason, "pass2"))

    try:
        while pending_index < len(tasks) or pool.active:
            if time.monotonic() >= stop_scheduling_at:
                break
            while pending_index < len(tasks) and pool.active < workers and time.monotonic() < stop_scheduling_at:
                task = dict(tasks[pending_index])
                # Finish and merge a field family before dependent tasks read
                # its evidence. This matters for small batches with spare slots.
                if pool.active and task["module"] != active_module:
                    break
                pending_index += 1
                org = task["organisation_number"]
                module = task["module"]
                if module in {"model_signals", "planner"}:
                    website = profiles[org].get("evidence", {}).get("website") or {}
                    if not model_config.configured:
                        skip(task, "model_not_configured")
                        continue
                    if module == "model_signals" and (
                            website.get("status") != "available" or
                            not (website.get("value") or {}).get("identity_assessment", {}).get("publishable")):
                        skip(task, "model_no_verified_website")
                        continue
                planner_action = ((profiles[org].get("evidence", {}).get("planner") or {}).get("value") or {}).get("action") or {}
                planner_has_candidate = planner_action.get("status") == "accepted" and bool(
                    planner_action.get("candidate_url") or planner_action.get("url")
                )
                if task["module"] == "website" and not website_candidates(profiles[org], derived=False) and not planner_has_candidate:
                    profiles[org].setdefault("evidence", {})["website"] = evidence("website", "not_found", "registry_linked_company_website", "https://data.brreg.no/enhetsregisteret/api/enheter", note="No website candidate in the supplied identity snapshot")
                    completed_orgs.add(org)
                    completed_tasks += 1
                    module_operations[module]["local_tasks"] += 1
                    module_operations[module]["completed_tasks"] += 1
                    dirty.add(org)
                    continue
                local_extraction = module in {"hiring", "activity"}
                if not task["saved"] and not local_extraction and (budget.requests.value >= budget.max_requests or resume_budget_unknown):
                    skip(task, "resume_budget_unknown" if resume_budget_unknown else "outbound_request_cap")
                    continue
                task["profile"] = profiles[org]
                task["deadline"] = min(stop_scheduling_at, time.monotonic() + company_timeout)
                task["request_limit"] = 0 if local_extraction else 4 if module in {"website", "website_discovery"} else 2
                if module == "model_signals":
                    task["request_limit"] = min(2, len(model_config.credentials))
                if module == "planner":
                    task["request_limit"] = min(2, len(model_config.credentials)) + 1
                    task["derived_candidates"] = args.discover_websites
                    task["allow_search"] = governor.max_search_calls > 0
                if module in {"model_signals", "planner"}:
                    task["model_config"] = {
                        "api_key": model_config.api_key,
                        "endpoint": model_config.endpoint,
                        "model": model_config.model,
                        "timeout_seconds": model_config.timeout_seconds,
                        "max_input_chars": model_config.max_input_chars,
                        "max_output_tokens": model_config.max_output_tokens,
                        "cost_per_call_usd": model_config.cost_per_call_usd,
                        "api_keys": model_config.api_keys,
                        "requests_per_key_per_day": model_config.requests_per_key_per_day,
                        "provider_min_interval_seconds": model_config.provider_min_interval_seconds,
                    }
                pool.submit(task, company_timeout)
                active_module = module
                module_operations[module]["started_tasks"] += 1
                if local_extraction:
                    module_operations[module]["local_tasks"] += 1
            if not pool.active:
                break
            for task, ok, result in pool.poll(min(0.1, max(0, stop_scheduling_at - time.monotonic()))):
                org, module = task["organisation_number"], task["module"]
                module_metric = module_operations[module]
                if ok:
                    profiles[org].setdefault("evidence", {}).update(result["records"])
                    metric = profiles[org]["run_metrics"]
                    for key in ("bytes", "runtime_ms", "snapshot_reads"):
                        metric[key] += result["metric"].get(key, 0)
                        module_metric[key] += result["metric"].get(key, 0)
                    metric["latencies_ms"].extend(result["metric"].get("latencies_ms", []))
                    completed_orgs.add(org)
                    completed_tasks += 1
                    module_metric["completed_tasks"] += 1
                else:
                    if module in {"website", "website_discovery", "hiring", "activity"}:
                        url, source_type = profiles[org].get("website") or "", "registry_linked_company_website"
                    elif module in {"model_signals", "planner"}:
                        url, source_type = "", "model_assisted_extraction"
                    else:
                        url, source_type = official_endpoints(org)[module]
                    transient = str(result) in {"company_timeout", "worker_exit"} or "BudgetExceeded" in str(result)
                    profiles[org].setdefault("evidence", {})[module] = evidence(module, "not_fetched" if transient else "source_error", source_type, url, note=str(result))
                    errors_by_org.setdefault(org, []).append(_error("company_enrichment_failed", f"{module}: {result}", "pass2"))
                    pass2_errors += 1
                    module_metric["failed_tasks"] += 1
                profiles[org]["run_metrics"]["requests"] = budget.company_requests[task["company_index"]]
                dirty.add(org)
            if len(dirty) >= max(1, args.checkpoint_every):
                for org in dirty:
                    latest[org] = _build_envelope(profiles[org], run_id=args.run_id, started_at=started_at,
                        completed_at=utc_now(), modules=requested_modules, errors=errors_by_org.get(org, []),
                        previous=previous_profiles.get(org), previous_run_id=previous_run_id)
                    append_progress(journal_path, latest[org], "pass2")
                write_jsonl(output_path, [latest[item] for item in orgs])
                write_jsonl(profiles_path, [profiles[item] for item in orgs])
                dirty.clear()
    finally:
        incomplete = pool.close()
    for task in incomplete + tasks[pending_index:]:
        skip(task, "run_deadline")
    for index, org in enumerate(orgs):
        profiles[org].setdefault("run_metrics", {})["requests"] = budget.company_requests[index]

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
    operations["requests"] = budget.requests.value - initial_requests
    operations["snapshot_reads"] = sum(profile.get("run_metrics", {}).get("snapshot_reads", 0) for profile in profiles.values())
    operations["third_party_cost_usd"] = budget.report()["cost_usd"]
    for module, metric in module_operations.items():
        metric["requests"] = budget.module_requests[budget.module_indices[module]]
        metric["runtime_ms"] = round(metric["runtime_ms"], 3)
    attributed_requests = sum(metric["requests"] for metric in module_operations.values())
    request_attribution = {
        "scope": "current_invocation",
        "attributed_requests": attributed_requests,
        "unattributed_requests": budget.unattributed_requests.value,
        "reconciled": attributed_requests + budget.unattributed_requests.value == operations["requests"],
    }
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
        "status_counts": dict(Counter(envelope["status"] for envelope in final_envelopes)),
        "section_state_counts": {section: dict(Counter(envelope["sections"][section]["state"] for envelope in final_envelopes))
                                 for section in final_envelopes[0]["sections"]} if final_envelopes else {},
        "pass1_envelopes": pass1_count,
        "resumed_profiles": len(resumed_orgs),
        "pass2_completed": len(completed_orgs),
        "pass2_skipped": len(skipped_orgs),
        "pass2_tasks_completed": completed_tasks,
        "pass2_tasks_skipped": skipped_tasks,
        "pass2_errors": pass2_errors,
        "modules": requested_modules,
        "coverage_profile": coverage_profile,
        "registry": {
            "registry_snapshot_sha256": snapshot_sha256,
            "registry_rows_scanned": scanned,
            "requested": len(orgs),
            "selected": len(found),
            "missing": len(orgs) - len(found),
            "source_type": next(iter(found.values()), {}).get("evidence", {}).get("registry", {}).get("source_type"),
            "local_snapshot_uri": bulk_path.resolve().as_uri(),
        },
        "operations": operations,
        "module_operations": module_operations,
        "request_attribution": request_attribution,
        "budget": budget.report(),
        "request_ledger": budget.ledger_path,
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
