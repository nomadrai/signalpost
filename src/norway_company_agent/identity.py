from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any


LEGAL_AND_GENERIC = {
    "as", "asa", "ans", "da", "enk", "iks", "sa", "sam", "sti", "stiftelsen",
    "nuf", "ab", "b", "v", "limited", "ltd", "inc", "plc", "the", "og", "and",
}

BLOCKED_WEBSITE_HOSTS = {
    "proff.no", "purehelp.no", "1881.no", "gulesider.no", "firmalisten.no", "companywall.no",
    "firmadatabasen.no", "sokfirma.no", "yra.no", "northdata.com", "nor47business.com",
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com",
    "brreg.no", "finn.no", "indeed.com", "nav.no",
}


def company_host_allowed(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").casefold().rstrip(".").removeprefix("www.")
    return bool(host) and not any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_WEBSITE_HOSTS)


def organisation_numbers(text: str) -> set[str]:
    """Match complete checksum-valid numbers, never concatenate arbitrary digits."""
    numbers = set()
    for match in re.finditer(r"(?<!\d)([89]\d{2}[ .\u00a0-]?\d{3}[ .\u00a0-]?\d{3})(?!\d)", text):
        value = re.sub(r"\D", "", match.group())
        check = 11 - sum(int(digit) * weight for digit, weight in zip(value[:8], (3, 2, 7, 6, 5, 4, 3, 2))) % 11
        if check == 11:
            check = 0
        if check != 10 and check == int(value[-1]):
            numbers.add(value)
    return numbers


def _owner_numbers(organisations: list) -> set[str]:
    numbers = set()
    for owner in organisations:
        for key in ("vatID", "taxID", "identifier"):
            if key in owner:
                numbers.update(organisation_numbers(str(owner[key])))
    return numbers


def _name_matches(name: str, text: str) -> bool:
    core = _tokens(name)
    normalized = " " + " ".join(_tokens(text)) + " "
    return bool(core) and " " + " ".join(core) + " " in normalized


def _corroboration(profile: dict, text: str) -> list[str]:
    records = profile.get("evidence", {})
    live = records.get("registry_live", {}).get("value") or {}
    address = profile.get("business_address") or live.get("business_address") or {}
    proofs = []
    streets = address.get("adresse") or []
    if isinstance(streets, str):
        streets = [streets]
    normalized = " ".join(_tokens(text))
    street_match = any(" ".join(_tokens(street)) in normalized for street in streets if _tokens(street))
    postcode = str(address.get("postnummer") or "")
    city = str(address.get("poststed") or "")
    if street_match and ((postcode and re.search(r"(?<!\d)" + re.escape(postcode) + r"(?!\d)", text)) or (city and _name_matches(city, text))):
        proofs.append("registered_street_and_postcode_or_city")
    for role in (records.get("roles", {}).get("value") or {}).get("roles", []):
        if not role.get("inactive") and len(_tokens(role.get("name"))) >= 2 and _name_matches(role["name"], text):
            proofs.append("registered_role_holder")
            break
    return proofs


def _tokens(value: Any) -> list[str]:
    text = str(value or "").translate(str.maketrans({"ø": "o", "Ø": "O", "å": "a", "Å": "A", "æ": "ae", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [token for token in re.findall(r"[a-z0-9]+", text) if token not in LEGAL_AND_GENERIC and len(token) > 1]


def _structured_names(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"name", "legalName", "alternateName"} and isinstance(child, str):
                names.append(child)
            else:
                names.extend(_structured_names(child))
    elif isinstance(value, list):
        for child in value:
            names.extend(_structured_names(child))
    return names


def assess_website_identity(profile: dict[str, Any]) -> dict[str, Any]:
    website = profile.get("evidence", {}).get("website", {})
    value = website.get("value") or {}
    core = _tokens(profile.get("name"))
    hostname = urllib.parse.urlparse(value.get("final_url") or website.get("source_url") or "").hostname or ""
    structured_names = _structured_names(value.get("structured_organisations") or [])
    rendered = value.get("js_fallback") or {}
    homepage_identity_parts = [
        value.get("title"), value.get("description"), value.get("identity_text_excerpt"), hostname, *structured_names,
        rendered.get("title"),
    ]
    candidate_parts = [
        *homepage_identity_parts, value.get("main_text_excerpt"),
        *[page.get("title") for page in value.get("pages", [])],
        *[page.get("main_text_excerpt") for page in value.get("pages", [])],
        *[page.get("identity_text_excerpt") for page in value.get("pages", [])],
    ]
    candidate_parts.append(rendered.get("main_text_excerpt"))
    candidate_text = " ".join(str(part or "") for part in candidate_parts)
    homepage_candidate_text = " ".join(str(part or "") for part in [*homepage_identity_parts, value.get("main_text_excerpt"), rendered.get("main_text_excerpt")])
    normalized_candidate_text = " ".join(_tokens(candidate_text))
    candidate_tokens = set(_tokens(candidate_text))
    org_digits = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    homepage_numbers = organisation_numbers(homepage_candidate_text)
    owner_numbers = organisation_numbers(str(value.get("identity_text_excerpt") or "")) | _owner_numbers(value.get("structured_organisations") or [])
    labelled_numbers = organisation_numbers(" ".join(re.findall(r"(?:org(?:anisasjonsnummer|anization number|\.?\s*(?:nr|number))?|vat)[^\n]{0,45}", homepage_candidate_text, re.I)))
    owner_numbers |= labelled_numbers
    overlap = sorted(set(core) & candidate_tokens)
    ratio = len(overlap) / len(set(core)) if core else 0.0
    reasons = []
    parked_markers = (
        "domain is for sale", "domain for sale", "hugedomains", "parked at", "miss hosting",
        "her flytter snart en ny gjest", "has been informing visitors",
        "find the best information and most relevant links on all topics related to",
    )
    normalized_raw = unicodedata.normalize("NFKD", candidate_text).encode("ascii", "ignore").decode().casefold()
    exact_homepage_name = any(_name_matches(str(profile.get("name") or ""), str(part)) for part in [value.get("title"), value.get("description"), value.get("identity_text_excerpt"), *structured_names] if part)
    substantive_homepage = len(str(value.get("main_text_excerpt") or "").strip()) >= 100
    is_business_sports_club = bool(re.search(r"(?:^|\s)B\.?\s*I\.?\s*L\.?(?:\s|$)", str(profile.get("name") or ""), re.I))
    conflicts = sorted(owner_numbers - {org_digits})
    proofs = []
    proof_url = value.get("final_url") or website.get("source_url")
    search_candidate = value.get("candidate_source") == "transient_firecrawl_search"
    host_tokens = set(_tokens(hostname))
    name_in_host = bool(core and set(core).issubset(host_tokens))
    if proof_url and not company_host_allowed(proof_url):
        score = 0.0
        reasons.append("directory, registry, marketplace or social host is not a company-owned website")
    elif any(marker in normalized_raw for marker in parked_markers):
        score = 0.1
        reasons.append("captured page is a parked, for-sale, or generic hosting placeholder")
    elif is_business_sports_club and "bedriftsidrett" not in normalized_candidate_text and "b i l" not in normalized_candidate_text:
        score = 0.3
        reasons.append("business sports-club entity points to the operating company's site without club evidence")
    elif conflicts:
        score = 0.3
        reasons.append("ownership evidence identifies a different or multiple organisation numbers")
    elif org_digits in owner_numbers or (org_digits in homepage_numbers and exact_homepage_name):
        if search_candidate and not name_in_host and not _corroboration(profile, candidate_text):
            score = 0.85
            reasons.append("search candidate has exact organisation evidence but lacks hostname or registered-identity corroboration")
        else:
            score = 1.0
            reasons.append("exact organisation number appears in homepage identity evidence")
            proofs.append("exact_homepage_organisation_number")
    elif not re.search(r"\b(konsern|group|portfolio)\b", str(value.get("title") or ""), re.I) and any(
        org_digits in organisation_numbers(str(page.get("identity_text_excerpt") or ""))
        and not (organisation_numbers(str(page.get("identity_text_excerpt") or "")) - {org_digits})
        and _name_matches(str(profile.get("name") or ""), str(page.get("identity_text_excerpt") or ""))
        for page in value.get("pages") or []):
        page = next(page for page in value["pages"] if org_digits in organisation_numbers(str(page.get("identity_text_excerpt") or "")))
        score = 1.0
        proof_url = page.get("url") or proof_url
        proofs.append("exact_contact_footer_organisation_number_and_legal_name")
        reasons.append("same-site ownership footer gives the exact legal name and organisation number")
    elif exact_homepage_name and _corroboration(profile, candidate_text):
        score = 0.95
        proofs = ["exact_legal_name", *_corroboration(profile, candidate_text)]
        reasons.append("exact legal name is independently corroborated by registered identity data")
    elif exact_homepage_name:
        score = 0.8
        reasons.append("legal name alone is insufficient; independent ownership proof is missing")
    elif ratio >= 0.75 and len(overlap) >= 2:
        score = 0.85
        reasons.append("most legal-name tokens appear, but exact identity is incomplete")
    elif ratio >= 0.5 and len(overlap) >= 2:
        score = 0.65
        reasons.append("partial legal-name overlap only")
    else:
        score = 0.3
        reasons.append("registry-linked URL lacks strong exact-entity identity evidence")
    status = "exact" if score >= 0.9 else "review" if score >= 0.8 else "related_or_uncertain"
    return {
        "status": status,
        "score": score,
        "publishable": status == "exact",
        "legal_name_tokens": core,
        "matched_tokens": overlap,
        "proofs": proofs,
        "proof_url": proof_url,
        "conflicting_organisation_numbers": conflicts,
        "reasons": reasons,
        "method": "deterministic_name_org_evidence_v3",
    }


def assess_social_identity(profile: dict[str, Any], link: dict[str, str]) -> dict[str, Any]:
    core = _tokens(profile.get("name"))
    parsed = urllib.parse.urlparse(link.get("url") or "")
    handle_text = urllib.parse.unquote(parsed.path)
    handle_compact = "".join(_tokens(handle_text))
    matched = [token for token in core if token in handle_compact]
    core_compact = "".join(core)
    ratio = len(set(matched)) / len(set(core)) if core else 0.0
    if core_compact and core_compact in handle_compact:
        score = 0.98
        reason = "normalized legal-name sequence appears in the social handle"
    elif len(core) == 1 and matched:
        score = 0.95
        reason = "single distinctive legal-name token appears in the social handle"
    elif ratio >= 0.75 and len(set(matched)) >= 2:
        score = 0.9
        reason = "most legal-name tokens appear in the social handle"
    else:
        score = 0.3
        reason = "social handle lacks strong exact-entity name evidence"
    return {
        **link,
        "identity_score": score,
        "publishable": score >= 0.9,
        "matched_tokens": matched,
        "reason": reason,
        "method": "deterministic_social_handle_identity_v1",
    }


def apply_website_identity_gate(profile: dict[str, Any], website: dict[str, Any]) -> dict[str, Any]:
    if website.get("status") != "available":
        return {"website": website, "assessment": None, "quarantined_social_links": 0}
    temporary_profile = {**profile, "evidence": {**profile.get("evidence", {}), "website": website}}
    value = website.get("value") or {}
    assessment = assess_website_identity(temporary_profile)
    value["identity_assessment"] = assessment
    original = list(value.get("discovered_social_links") or value.get("social_links") or [])
    value["discovered_social_links"] = original
    social_assessments = [assess_social_identity(profile, link) for link in original]
    value["social_link_assessments"] = social_assessments
    value["social_links"] = [
        {"platform": item["platform"], "url": item["url"]}
        for item in social_assessments
        if assessment["publishable"] and item["publishable"]
    ]
    website["value"] = value
    return {
        "website": website,
        "assessment": assessment,
        "quarantined_social_links": len(original) - len(value["social_links"]),
    }
