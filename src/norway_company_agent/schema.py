from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence import utc_now

SCHEMA_VERSION = "1.0"
AVAILABILITY_STATES = {
    "available",
    "not_available",
    "blocked",
    "not_applicable",
    "ambiguous",
    "failed",
}


class EvidenceLocator(BaseModel):
    model_config = ConfigDict(extra="allow")

    snapshot_id: str
    locator: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_id: str
    field: str
    value: Any = None
    state: str = "available"
    evidence: list[EvidenceLocator] = Field(default_factory=list)
    retrieved_at: str
    reporting_period: Any | None = None
    effective_date: str | None = None
    extraction_method: str
    identity_tier: str = "A"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    snapshot_id: str
    requested_url: str
    final_url: str
    http_status: int
    redirect_chain: list[str] = Field(default_factory=list)
    retrieved_at: str
    content_sha256: str
    parser_version: str
    source_class: str
    access_policy: str


class SynthesisSentence(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    claim_ids: list[str] = Field(default_factory=list)


class Synthesis(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    sentences: list[SynthesisSentence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    organisation_number: str
    status: Literal[
        "available",
        "not_available",
        "blocked",
        "not_applicable",
        "ambiguous",
        "failed",
    ]
    identity: dict[str, Any] = Field(default_factory=dict)
    sections: dict[str, Any] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)
    snapshots: list[Snapshot] = Field(default_factory=list)
    synthesis: Synthesis
    refresh: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    run: dict[str, Any] = Field(default_factory=dict)
    operations: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    modules: dict[str, Any] = Field(default_factory=dict)
    state: str = "complete"


def _json_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(value)


def _normalised_value(value: Any) -> str:
    return " ".join(_json_value(value).casefold().split())


def stable_claim_id(organisation_number: str, field: str, value: Any, source_key: str) -> str:
    material = "|".join((organisation_number, field, _normalised_value(value), source_key))
    return "clm-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def stable_snapshot_id(record: dict[str, Any], field: str) -> str:
    # One immutable source capture can support many fields. The field remains
    # in the claim ID and locator, not in the snapshot identity.
    material = "|".join(
        (
            str(record.get("source_url") or "unknown"),
            str(record.get("content_sha256") or "unknown"),
            str(record.get("source_row_key") or ""),
        )
    )
    return "snp-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _record_state(record: dict[str, Any] | None) -> str:
    state = str((record or {}).get("status") or "not_fetched")
    return {
        "available": "available",
        "blocked": "blocked",
        "not_applicable": "not_applicable",
        "not_found": "not_available",
        "not_fetched": "not_available",
        "source_error": "failed",
    }.get(state, "failed")


def _legacy_module_state(record: dict[str, Any] | None) -> str:
    state = str((record or {}).get("status") or "not_fetched")
    return {
        "available": "complete",
        "not_applicable": "not_applicable",
        "not_found": "not_found",
        "blocked": "blocked_policy",
        "source_error": "source_error",
    }.get(state, "submission_error")


def _record_for_field(profile: dict[str, Any], field: str) -> dict[str, Any]:
    evidence = profile.get("evidence") or {}
    if field.startswith("identity.") or field.startswith("registry."):
        return evidence.get("registry") or evidence.get("registry_live") or {}
    if field.startswith("accounts."):
        return evidence.get("financials") or {}
    if field.startswith("leadership."):
        return evidence.get("roles") or {}
    if field.startswith("workplaces."):
        return evidence.get("locations") or {}
    if field.startswith("website.") or field.startswith("profiles."):
        return evidence.get("website") or {}
    return {}


def _snapshot(record: dict[str, Any], field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot_id = stable_snapshot_id(record, field)
    value = record.get("value")
    final_url = value.get("final_url") if isinstance(value, dict) else None
    final_url = str(final_url or record.get("source_url") or "")
    status = str(record.get("status") or "")
    http_status = 200 if status == "available" else 404 if status == "not_found" else 0
    content_hash = str(record.get("content_sha256") or "")
    if len(content_hash) != 64:
        content_hash = hashlib.sha256(_json_value(value).encode("utf-8")).hexdigest()
    retrieved_at = str(record.get("retrieved_at") or utc_now())
    snapshot = {
        "snapshot_id": snapshot_id,
        "requested_url": str(record.get("source_url") or final_url),
        "final_url": final_url,
        "http_status": 0 if record.get("local_snapshot_uri") else http_status,
        "redirect_chain": [],
        "retrieved_at": retrieved_at,
        "content_sha256": content_hash,
        "parser_version": "signalpost-contract-v1",
        "source_class": str(record.get("source_class") or record.get("source_type") or "unknown"),
        "access_policy": "local-snapshot" if record.get("local_snapshot_uri") else "bounded-public-source",
    }
    if record.get("local_snapshot_uri"):
        snapshot["local_snapshot_uri"] = record["local_snapshot_uri"]
    locator = {
        "type": "json_path",
        "path": field,
        "source_row_key": record.get("source_row_key"),
    }
    return snapshot, {"snapshot_id": snapshot_id, "locator": locator}


def _claim(
    profile: dict[str, Any],
    field: str,
    value: Any,
    record: dict[str, Any],
    *,
    extraction_method: str,
    identity_tier: str = "A",
    confidence: float = 1.0,
    reporting_period: Any | None = None,
    effective_date: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot, reference = _snapshot(record, field)
    source_key = "|".join((str(record.get("source_url") or ""), str(record.get("content_sha256") or "")))
    claim = {
        "claim_id": stable_claim_id(str(profile.get("organisation_number") or ""), field, value, source_key),
        "field": field,
        "value": value,
        "state": "available",
        "evidence": [reference],
        "retrieved_at": str(record.get("retrieved_at") or utc_now()),
        "reporting_period": reporting_period,
        "effective_date": effective_date or record.get("effective_at") or record.get("as_of"),
        "extraction_method": extraction_method,
        "identity_tier": identity_tier,
        "confidence": confidence,
    }
    return claim, snapshot


def _append_claim(
    profile: dict[str, Any], claims: list[dict[str, Any]], snapshots: dict[str, dict[str, Any]], field: str, value: Any, record: dict[str, Any], **kwargs: Any
) -> None:
    if value is None or value == "":
        return
    claim, snapshot = _claim(profile, field, value, record, **kwargs)
    if any(item.get("claim_id") == claim["claim_id"] for item in claims):
        return
    claims.append(claim)
    snapshots[snapshot["snapshot_id"]] = snapshot


def _module_claim_ids(claims: Iterable[dict[str, Any]], prefix: str) -> list[str]:
    return [item["claim_id"] for item in claims if item.get("field", "").startswith(prefix)]


def _section_state(record: dict[str, Any] | None, claims: list[dict[str, Any]], prefix: str) -> str:
    record_state = _record_state(record)
    if claims:
        return "available"
    return record_state


def _unknowns(sections: dict[str, Any]) -> list[str]:
    labels = {
        "accounts": "Annual accounts",
        "leadership": "Leadership",
        "workplaces": "Registered workplaces",
        "website": "Official website",
        "profiles": "Company-owned profiles",
        "hiring": "Hiring",
        "activity": "Dated public activity",
    }
    return [f"{labels[key]}: {value.get('state', 'not_available')}" for key, value in sections.items() if value.get("state") != "available" and key in labels]


def _synthesis(profile: dict[str, Any], claims: list[dict[str, Any]], sections: dict[str, Any]) -> dict[str, Any]:
    by_field = {item["field"]: item for item in claims}
    sentences: list[dict[str, Any]] = []
    name = by_field.get("identity.name")
    legal_form = by_field.get("identity.legal_form")
    if name:
        text = str(name["value"])
        ids = [name["claim_id"]]
        if legal_form:
            text += f" is registered as {legal_form['value']}."
            ids.append(legal_form["claim_id"])
        else:
            text += " appears in the supplied identity snapshot."
        sentences.append({"text": text, "claim_ids": ids})
    employees = by_field.get("identity.employees")
    if employees:
        sentences.append({"text": f"The supplied identity snapshot reports {employees['value']} employees.", "claim_ids": [employees["claim_id"]]})
    industry = by_field.get("identity.industry_label")
    if industry:
        sentences.append({"text": f"The registered industry is {industry['value']}.", "claim_ids": [industry["claim_id"]]})
    account_fields = [item for item in claims if item["field"].startswith("accounts.")]
    if account_fields:
        first = account_fields[0]
        period = first.get("reporting_period")
        period_text = f" for {period}" if period else ""
        sentences.append({"text": f"The latest available account record includes {first['field'].split('.', 1)[1]}{period_text}: {first['value']}.", "claim_ids": [first["claim_id"]]})
    role = next((item for item in claims if item["field"] == "leadership.role"), None)
    if role:
        value = role["value"]
        label = value.get("role") if isinstance(value, dict) else value
        person = value.get("name") if isinstance(value, dict) else None
        sentences.append({"text": f"A registered role is {label}: {person}.", "claim_ids": [role["claim_id"]]})
    website = by_field.get("website.title") or by_field.get("website.description")
    if website:
        sentences.append({"text": f"The verified company website reports: {website['value']}.", "claim_ids": [website["claim_id"]]})
    text = " ".join(sentence["text"] for sentence in sentences)
    return {"text": text, "sentences": sentences, "unknowns": _unknowns(sections)}


def _refresh_changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    if not previous:
        return []
    from .refresh import diff_profile

    try:
        raw = diff_profile(previous, current)
    except (KeyError, ValueError, TypeError):
        return []
    return [
        {
            "type": "changed_value",
            "claim_key": item.get("field"),
            "old": item.get("old_value"),
            "new": item.get("new_value"),
            "materiality": "material",
            "evidence_old": {"content_sha256": item.get("old_content_sha256")},
            "evidence_new": {
                "source_url": item.get("source_url"),
                "content_sha256": item.get("new_content_sha256"),
                "retrieved_at": item.get("retrieved_at"),
            },
        }
        for item in raw
    ]


def validate_claim_evidence(envelope: dict[str, Any]) -> list[str]:
    """Validate structural evidence completeness for every published claim."""
    snapshots = {str(item.get("snapshot_id")): item for item in envelope.get("snapshots") or []}
    errors: list[str] = []
    for claim in envelope.get("claims") or []:
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id:
            errors.append("claim without claim_id")
        refs = claim.get("evidence") or []
        if not refs:
            errors.append(f"{claim_id}: claim has no evidence reference")
        for ref in refs:
            snapshot_id = str(ref.get("snapshot_id") or "")
            snapshot = snapshots.get(snapshot_id)
            if not snapshot:
                errors.append(f"{claim_id}: missing snapshot {snapshot_id}")
                continue
            if len(str(snapshot.get("content_sha256") or "")) != 64:
                errors.append(f"{claim_id}: snapshot hash is incomplete")
            if not snapshot.get("retrieved_at"):
                errors.append(f"{claim_id}: snapshot retrieval time is missing")
            if not ref.get("locator"):
                errors.append(f"{claim_id}: evidence locator is missing")
    return errors


def build_contract_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    requested_modules: Iterable[str] = (),
    errors: list[dict[str, Any]] | None = None,
    previous: dict[str, Any] | None = None,
    previous_run_id: str | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    errors = list(errors or [])
    org = str(profile.get("organisation_number") or "")
    evidence = profile.get("evidence") or {}
    claims: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    registry = evidence.get("registry") or evidence.get("registry_live") or {}

    identity_fields = (
        ("name", profile.get("name")),
        ("legal_form", profile.get("legal_form")),
        ("employees", profile.get("employees")),
        ("municipality", profile.get("municipality")),
        ("industry_code", profile.get("industry_code")),
        ("industry_label", profile.get("industry_label")),
        ("business_address", profile.get("business_address")),
        ("postal_address", profile.get("postal_address")),
        ("website_candidate", profile.get("website")),
        ("latest_submitted_accounts", profile.get("latest_submitted_accounts")),
    )
    for field, value in identity_fields:
        _append_claim(profile, claims, snapshots, f"identity.{field}", value, registry, extraction_method="normalized_universe_snapshot" if registry.get("source_type") == "local_company_universe" else "registry_snapshot")

    financial_record = evidence.get("financials") or {}
    for index, record in enumerate(((financial_record.get("value") or {}).get("records") or [])[:3]):
        period = record.get("period")
        for field in ("currency", "revenue", "operating_result", "profit_before_tax", "annual_result", "assets", "equity", "debt"):
            _append_claim(
                profile,
                claims,
                snapshots,
                f"accounts.{index}.{field}",
                record.get(field),
                financial_record,
                extraction_method="official_structured_accounts",
                reporting_period=period,
            )

    roles_record = evidence.get("roles") or {}
    for role in ((roles_record.get("value") or {}).get("roles") or []):
        if role.get("inactive") or not role.get("name") and not role.get("organisation_number"):
            continue
        _append_claim(profile, claims, snapshots, "leadership.role", role, roles_record, extraction_method="official_role_record", effective_date=role.get("last_changed"))

    locations_record = evidence.get("locations") or {}
    for location in ((locations_record.get("value") or {}).get("locations") or []):
        _append_claim(profile, claims, snapshots, "workplaces.location", location, locations_record, extraction_method="official_subunit_record")

    website_record = evidence.get("website") or {}
    website_value = website_record.get("value") or {}
    website_identity = website_value.get("identity_assessment") or {}
    website_publishable = website_record.get("status") == "available" and website_identity.get("publishable", True)
    if website_publishable:
        for field in ("title", "description"):
            _append_claim(profile, claims, snapshots, f"website.{field}", website_value.get(field), website_record, extraction_method="company_site_structured_and_text", identity_tier="A" if website_identity.get("score", 0) >= 0.9 else "B", confidence=float(website_identity.get("score", 0.9) or 0.9))
        for link in website_value.get("social_links") or []:
            _append_claim(profile, claims, snapshots, "profiles.company_owned", link, website_record, extraction_method="company_site_declared_link", identity_tier="A")

    module_names = list(requested_modules) or ["registry", "financials", "roles", "locations", "website"]
    legacy_modules: dict[str, Any] = {}
    for module in module_names:
        record = evidence.get(module)
        if module == "registry":
            record = evidence.get("registry") or evidence.get("registry_live") or registry
        if module == "accounting_obligation":
            record = evidence.get("accounting_obligation") or {}
        legacy_modules[module] = {
            "state": _legacy_module_state(record),
            "retry_count": int((record or {}).get("retry_count") or 0),
            "final_timestamp": (record or {}).get("retrieved_at") or completed_at,
        }

    sections = {
        "identity": {"state": _section_state(registry, _module_claim_ids(claims, "identity."), "identity."), "claim_ids": _module_claim_ids(claims, "identity.")},
        "accounts": {"state": _section_state(financial_record, _module_claim_ids(claims, "accounts."), "accounts."), "claim_ids": _module_claim_ids(claims, "accounts.")},
        "leadership": {"state": _section_state(roles_record, _module_claim_ids(claims, "leadership."), "leadership."), "claim_ids": _module_claim_ids(claims, "leadership.")},
        "workplaces": {"state": _section_state(locations_record, _module_claim_ids(claims, "workplaces."), "workplaces."), "claim_ids": _module_claim_ids(claims, "workplaces.")},
        "website": {"state": "available" if website_publishable else "ambiguous" if website_record.get("status") == "available" else _record_state(website_record), "claim_ids": _module_claim_ids(claims, "website.")},
        "profiles": {"state": "available" if _module_claim_ids(claims, "profiles.") else "not_available", "claim_ids": _module_claim_ids(claims, "profiles.")},
        "hiring": {"state": "not_available", "claim_ids": []},
        "activity": {"state": "not_available", "claim_ids": []},
    }
    for section, record in (("accounts", financial_record), ("leadership", roles_record),
                            ("workplaces", locations_record), ("website", website_record)):
        if record.get("note"):
            sections[section]["reason"] = record["note"]
    identity_state = sections["identity"]["state"]
    status = status_override or ("available" if identity_state == "available" else "failed" if not org else identity_state)
    if status not in AVAILABILITY_STATES:
        status = "failed"
    synthesis = _synthesis(profile, claims, sections)
    refresh = {
        "previous_run_id": previous_run_id,
        "changes": _refresh_changes(previous, profile),
    }
    operations = dict(profile.get("run_metrics") or {})
    operations.setdefault("third_party_cost_usd", 0)
    operations.setdefault("requests", 0)
    operations.setdefault("bytes", 0)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "organisation_number": org,
        "status": status,
        "identity": {"organisation_number": org, "name": profile.get("name"), "claim_ids": sections["identity"]["claim_ids"]},
        "sections": sections,
        "claims": claims,
        "snapshots": list(snapshots.values()),
        "synthesis": synthesis,
        "refresh": refresh,
        "errors": errors,
        "run": {"run_id": run_id, "started_at": started_at, "completed_at": completed_at, "terminal_status": "completed" if status != "failed" else "failed"},
        "operations": operations,
        "evidence": [{"id": item["snapshot_id"], **item} for item in snapshots.values()],
        "profile": profile,
        "modules": legacy_modules,
        "state": "complete" if status == "available" else "submission_error" if status == "failed" else status,
    }
    return Envelope.model_validate(envelope).model_dump(mode="json", exclude_none=False)
