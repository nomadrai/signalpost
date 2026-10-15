from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any

from .website import normalize_homepage
from .identity import BLOCKED_WEBSITE_HOSTS, company_host_allowed


BLOCKED_DISCOVERY_HOSTS = BLOCKED_WEBSITE_HOSTS
GENERIC_NAME_TOKENS = {"as", "asa", "ans", "da", "enk", "sa", "nuf", "company", "norge", "norway", "gruppen", "group"}
DERIVED_CANDIDATE_LIMIT = 8


def website_candidates(profile: dict[str, Any], *, derived: bool = False) -> list[dict[str, str]]:
    """A bounded plan, never a publication decision or a financial-data source."""
    candidates = []
    live = profile.get("evidence", {}).get("registry_live", {}).get("value") or {}
    for value, source in ((profile.get("website"), "registry_snapshot"), (live.get("website"), "registry_live")):
        normalized = normalize_homepage(value)
        if normalized and company_host_allowed(normalized):
            candidates.append({"url": normalized, "source": source})
    if derived:
        names = [profile.get("name"), live.get("name")]
        unsuitable = {"holding", "invest", "investering", "eiendom", "borettslaget", "borettslag", "sameie", "enk"}
        for name in names:
            tokens = [token for token in _tokens(name) if token not in GENERIC_NAME_TOKENS]
            if not (1 <= len(tokens) <= 3 and 4 <= len("".join(tokens)) <= 40 and
                    not set(tokens) & unsuitable and not any(token.isdigit() for token in tokens) and
                    profile.get("legal_form") != "ENK"):
                continue
            labels = ["".join(tokens)]
            if len(tokens) >= 2:
                labels.append("-".join(tokens))
                labels.append("".join(token[0] for token in tokens))
            for suffix in ("no", "com"):
                for label in labels:
                    candidates.append({"url": f"https://{label}.{suffix}/", "source": "legal_name_domain"})
    unique = {item["url"]: item for item in reversed(candidates)}
    return list(reversed(list(unique.values())))[:DERIVED_CANDIDATE_LIMIT]


def build_company_search_query(profile: dict[str, Any]) -> str:
    name = " ".join(str(profile.get("name") or "").split())
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    municipality = " ".join(str(profile.get("municipality") or "").split())
    if not name or not org:
        raise ValueError("Company discovery requires a legal name and organisation number")
    location = f" {municipality}" if municipality else ""
    return f'"{name}" {org}{location}'


def parse_brave_web_results(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    results = (payload.get("web") or {}).get("results") or []
    parsed = []
    for rank, result in enumerate(results, start=1):
        if not isinstance(result, dict) or not result.get("url"):
            continue
        parsed.append({
            "url": result.get("url"),
            "title": result.get("title") or "",
            "snippet": result.get("description") or "",
            "rank": rank,
            "provider": "brave_search_api",
            "query": query,
        })
    return parsed


def _tokens(value: Any) -> list[str]:
    text = str(value or "").translate(str.maketrans({"ø": "o", "å": "a", "æ": "ae", "Ø": "O", "Å": "A", "Æ": "AE"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return [token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 1]


def score_search_candidate(profile: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_homepage(result.get("url"))
    if not normalized:
        return {"status": "rejected", "score": 0.0, "publishable_candidate": False, "reasons": ["invalid HTTP(S) candidate URL"]}
    host = (urllib.parse.urlparse(normalized).hostname or "").casefold().removeprefix("www.")
    if any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DISCOVERY_HOSTS):
        return {"status": "rejected", "score": 0.0, "publishable_candidate": False, "url": normalized, "host": host, "reasons": ["directory, aggregator, or social host is not a company website candidate"]}

    name_tokens = [token for token in _tokens(profile.get("name")) if token not in GENERIC_NAME_TOKENS]
    title_tokens = _tokens(result.get("title"))
    snippet_tokens = _tokens(result.get("snippet"))
    evidence_tokens = set(title_tokens + snippet_tokens + _tokens(host))
    host_compact = "".join(_tokens(host))
    name_compact = "".join(name_tokens)
    org = re.sub(r"\D", "", str(profile.get("organisation_number") or ""))
    evidence_digits = re.sub(r"\D", "", f"{result.get('title', '')} {result.get('snippet', '')}")
    municipality_tokens = set(_tokens(profile.get("municipality")))

    org_match = bool(org and org in evidence_digits)
    all_name_tokens = bool(name_tokens and set(name_tokens).issubset(evidence_tokens))
    all_name_tokens_in_title = bool(name_tokens and set(name_tokens).issubset(set(title_tokens)))
    name_in_host = bool(name_compact and name_compact in host_compact)
    municipality_match = bool(municipality_tokens and municipality_tokens <= set(snippet_tokens))
    review_markers = {"directory", "catalog", "portfolio", "group", "listing", "profile", "marketplace"}
    review_marker_match = bool(review_markers & set(title_tokens + snippet_tokens))
    score = 0.0
    reasons = []
    if org_match:
        score += 0.75
        reasons.append("exact organisation number appears in result evidence")
    if all_name_tokens_in_title:
        score += 0.45
        reasons.append("all distinctive legal-name tokens appear in the result title")
    elif all_name_tokens:
        score += 0.25
        reasons.append("all distinctive legal-name tokens appear across result evidence")
    if name_in_host:
        score += 0.3
        reasons.append("normalized legal name appears in candidate hostname")
    if municipality_match:
        score += 0.1
        reasons.append("registry municipality appears in result snippet")
    score = min(score, 1.0)
    # Registry/directory pages routinely reproduce both the legal name and org
    # number. The hostname rule remains the strict path. A second, crawl-only
    # path admits a branded domain when the search result itself contains the
    # exact organisation number and full legal name in the title. The fetched
    # page still has to pass the independent ownership gate before publication.
    publishable_candidate = score >= 0.75 and name_in_host and (org_match or all_name_tokens_in_title)
    branded_crawl_candidate = (
        score >= 0.75 and org_match and all_name_tokens_in_title and not review_marker_match
    )
    crawl_eligible = publishable_candidate or branded_crawl_candidate
    return {
        "status": "accepted_for_crawl" if crawl_eligible else "review" if score >= 0.6 else "rejected",
        "score": score,
        "publishable_candidate": publishable_candidate,
        "crawl_eligible": crawl_eligible,
        "url": normalized,
        "host": host,
        "rank": result.get("rank"),
        "provider": result.get("provider"),
        "query": result.get("query"),
        "reasons": reasons or ["insufficient exact-entity evidence"],
        "method": "deterministic_search_candidate_identity_v1",
    }


def choose_search_candidate(profile: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    assessed = [score_search_candidate(profile, result) for result in results]
    assessed.sort(key=lambda item: (-item.get("score", 0.0), item.get("rank") or 10_000, item.get("url") or ""))
    accepted = [item for item in assessed if item.get("crawl_eligible")]
    return {
        "selected": accepted[0] if accepted else None,
        "selected_candidates": accepted[:3],
        "candidates": assessed,
        "abstained": not accepted,
        "policy": "A search result is only a crawl candidate. Publication still requires fetched-page exact-entity verification.",
    }
