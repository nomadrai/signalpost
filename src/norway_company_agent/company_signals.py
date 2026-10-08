from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime
from typing import Any

from .evidence import evidence
from .identity import _name_matches, organisation_numbers
from .page_capture import read_path


def iso_date(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.+)?", value):
        raise ValueError("A complete ISO source date is required")
    if len(value) > 10:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    return date.fromisoformat(value[:10]).isoformat()


def normalize_supported_value(raw: Any, transform: str, base_url: str) -> Any:
    if transform == "iso_date":
        return iso_date(raw)
    if transform == "text":
        if not isinstance(raw, str):
            raise ValueError("Source text must be a string")
        return " ".join(raw.split())[:500]
    if transform == "url":
        if not isinstance(raw, str):
            raise ValueError("Source URL must be a string")
        url = urllib.parse.urljoin(base_url, raw)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("Invalid source URL")
        return url
    raise ValueError("Unsupported extraction transform")


def _nodes(value: Any, path: list):
    if isinstance(value, dict):
        kind = value.get("@type", [])
        kinds = kind if isinstance(kind, list) else [kind]
        if any(item in {"JobPosting", "NewsArticle", "Article", "BlogPosting"} for item in kinds if isinstance(item, str)):
            yield value, path, kinds
        for key, child in value.items():
            if isinstance(child, (list, dict)):
                yield from _nodes(child, [*path, key])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _nodes(child, [*path, index])


def _owner_matches(owner: Any, profile: dict) -> bool:
    if not owner:
        return True  # inherit ownership only from an already verified first-party page
    if isinstance(owner, list):
        return all(_owner_matches(item, profile) for item in owner)
    if not isinstance(owner, dict):
        return isinstance(owner, str) and _name_matches(str(profile.get("name") or ""), owner)
    numbers = set()
    for key in ("identifier", "vatID", "taxID"):
        numbers.update(organisation_numbers(str(owner.get(key) or "")))
    if numbers:
        return numbers == {profile["organisation_number"]}
    name = owner.get("legalName") or owner.get("name")
    return bool(name and _name_matches(str(profile.get("name") or ""), str(name)))


def extract_company_signals(profile: dict, website: dict) -> dict[str, dict]:
    value = website.get("value") or {}
    assessment = value.get("identity_assessment") or {}
    outputs = {}
    if website.get("status") != "available" or not assessment.get("publishable"):
        status = website.get("status") if website.get("status") in {"blocked", "source_error", "not_fetched"} else "not_found"
        for family in ("hiring", "activity"):
            record = evidence(family, status, "company_owned_page", website.get("source_url") or "",
                              note="website_identity_ambiguous" if website.get("status") == "available" else "verified_website_unavailable")
            if website.get("status") == "available":
                record["availability_state"] = "ambiguous"
            outputs[family] = record
        return outputs
    home_host = (urllib.parse.urlparse(value.get("final_url") or website["source_url"]).hostname or "").casefold().removeprefix("www.")
    items = {"hiring": [], "activity": []}
    rejected = {"hiring": [], "activity": []}
    seen = set()
    for page in value.get("pages") or []:
        document = page.get("source_document") or {}
        if not document or not page.get("body_gzip_base64"):
            continue
        page_host = (urllib.parse.urlparse(page.get("url") or "").hostname or "").casefold().removeprefix("www.")
        if page_host != home_host:
            continue
        owner_numbers = organisation_numbers(str(page.get("identity_text_excerpt") or ""))
        if owner_numbers - {profile["organisation_number"]}:
            continue
        retrieved = iso_date(str(page.get("retrieved_at") or website["retrieved_at"]))
        candidates = []
        for node, path, kinds in _nodes(document.get("jsonld") or [], ["jsonld"]):
            family = "hiring" if "JobPosting" in kinds else "activity"
            title_key = "title" if family == "hiring" else "headline" if node.get("headline") else "name"
            date_key = "datePosted" if family == "hiring" else "datePublished"
            fields = {"title": {"path": [*path, title_key], "transform": "text"},
                      "date_posted" if family == "hiring" else "date": {"path": [*path, date_key], "transform": "iso_date"},
                      "url": {"path": [*path, "url"] if isinstance(node.get("url"), str) else ["url"], "transform": "url"}}
            if family == "hiring" and node.get("validThrough"):
                fields["valid_through"] = {"path": [*path, "validThrough"], "transform": "iso_date"}
            candidates.append((family, fields, node.get("hiringOrganization") if family == "hiring" else node.get("publisher"), "jsonld_job_posting" if family == "hiring" else "jsonld_dated_article"))
        for index, article in enumerate(document.get("articles") or []):
            path = ["articles", index]
            candidates.append(("activity", {key: {"path": [*path, key], "transform": "iso_date" if key == "date" else "url" if key == "url" else "text"}
                                            for key in ("title", "date", "url")}, None, "html_article_time"))
        for family, support, owner, method in candidates:
            try:
                if not _owner_matches(owner, profile):
                    raise ValueError("posting employer or publisher does not match the verified company")
                fact = {key: normalize_supported_value(read_path(document, proof["path"]), proof["transform"], page["url"])
                        for key, proof in support.items()}
                if not fact["title"]:
                    raise ValueError("missing title")
                fact_date = fact.get("date_posted") or fact["date"]
                if fact_date > retrieved or fact_date < "1950-01-01":
                    raise ValueError("publication date is outside the supported source period")
                fact_host = (urllib.parse.urlparse(fact["url"]).hostname or "").casefold().removeprefix("www.")
                if fact_host != home_host:
                    raise ValueError("linked item is outside the verified company host")
                if family == "hiring":
                    if fact.get("valid_through") and (fact["valid_through"] < retrieved or fact["valid_through"] < fact_date):
                        raise ValueError("posting is expired")
                    if not fact.get("valid_through") and (date.fromisoformat(retrieved) - date.fromisoformat(fact_date)).days > 90:
                        raise ValueError("undated availability on an old posting")
                key = (family, fact["url"], fact["title"], fact_date)
                if key in seen:
                    continue
                seen.add(key)
                items[family].append({"value": fact, "page_url": page["url"], "page_sha256": page.get("content_sha256"),
                                      "support": support, "method": method})
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                rejected[family].append({"page_url": page["url"], "reason": str(exc)[:200], "method": method})
    for family in ("hiring", "activity"):
        outputs[family] = evidence(family, "available" if items[family] else "not_found", "company_owned_page", website["source_url"],
                                   value={"items": items[family], "rejected": rejected[family]}, retrieved_at=website["retrieved_at"],
                                   content_sha256=website.get("content_sha256"),
                                   note="Source-backed items observed on fetched first-party pages" if items[family] else "No supported dated item observed in fetched pages; coverage is incomplete, not zero")
    return outputs
