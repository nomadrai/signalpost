from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.company_signals import extract_company_signals
from norway_company_agent.discovery import website_candidates
from norway_company_agent.evidence import evidence
from norway_company_agent.schema import build_contract_envelope, validate_claim_evidence


ORG = "993578843"


def _page(url="https://example.no/jobs", *, activity=False, expired=False, foreign=False):
    title = "Quarterly update" if activity else "Senior engineer"
    if activity:
        node = {"@type": "NewsArticle", "headline": title, "datePublished": "2026-09-01", "url": url}
    else:
        node = {"@type": "JobPosting", "title": title, "datePosted": "2026-08-01", "url": url,
                "hiringOrganization": {"@type": "Organization", "name": "Example AS"}}
        if expired:
            node["validThrough"] = "2026-08-15"
    if foreign:
        node["url"] = "https://other.example/jobs"
    return {"url": url, "content_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "retrieved_at": "2026-09-15T00:00:00Z", "identity_text_excerpt": "Example AS",
            "body_gzip_base64": "captured", "source_document": {"jsonld": [node], "articles": []}}


def _profile(pages, *, publishable=True):
    website = evidence("website", "available", "company_owned_website", "https://example.no/",
                       value={"final_url": "https://example.no/", "identity_assessment": {"publishable": publishable},
                              "pages": pages}, content_sha256="a" * 64, retrieved_at="2026-09-15T00:00:00Z")
    return {"organisation_number": ORG, "name": "Example AS", "evidence": {"website": website}}


def test_extracts_only_first_party_dated_hiring_and_activity_with_replayable_locators():
    profile = _profile([_page(), _page("https://example.no/news", activity=True)])
    records = extract_company_signals(profile, profile["evidence"]["website"])
    assert records["hiring"]["status"] == "available"
    assert records["activity"]["status"] == "available"
    assert records["hiring"]["value"]["items"][0]["value"]["title"] == "Senior engineer"
    assert records["activity"]["value"]["items"][0]["value"]["date"] == "2026-09-01"
    profile["evidence"].update(records)
    envelope = build_contract_envelope(profile, run_id="signals", started_at="2026-09-15T00:00:00Z",
                                       completed_at="2026-09-15T00:00:01Z", requested_modules=["website", "hiring", "activity"])
    assert envelope["sections"]["hiring"]["state"] == "available"
    assert envelope["sections"]["activity"]["state"] == "available"
    assert any(claim["field"] == "hiring.item" for claim in envelope["claims"])
    assert any(claim["field"] == "activity.item" for claim in envelope["claims"])
    assert not validate_claim_evidence(envelope)
    hiring_claim = next(claim for claim in envelope["claims"] if claim["field"] == "hiring.item")
    snapshot_id = hiring_claim["evidence"][0]["snapshot_id"]
    snapshot = next(item for item in envelope["snapshots"] if item["snapshot_id"] == snapshot_id)
    assert snapshot["final_url"] == "https://example.no/jobs"
    assert hiring_claim["effective_date"] == "2026-08-01"


def test_signal_extraction_uses_replay_document_without_retaining_compressed_body():
    page = _page()
    page.pop("body_gzip_base64")
    profile = _profile([page])
    records = extract_company_signals(profile, profile["evidence"]["website"])
    assert records["hiring"]["status"] == "available"
    assert records["hiring"]["value"]["items"][0]["value"]["title"] == "Senior engineer"


@pytest.mark.parametrize("page", [_page(expired=True), _page(foreign=True)])
def test_rejects_expired_or_off_host_job_facts(page):
    profile = _profile([page])
    record = extract_company_signals(profile, profile["evidence"]["website"])["hiring"]
    assert record["status"] == "not_found"
    assert record["value"]["items"] == []
    assert record["value"]["rejected"]


def test_ambiguous_site_never_turns_into_hiring_or_activity_claims():
    profile = _profile([_page()], publishable=False)
    records = extract_company_signals(profile, profile["evidence"]["website"])
    assert records["hiring"]["status"] == "not_found"
    assert records["hiring"]["availability_state"] == "ambiguous"
    assert records["activity"]["availability_state"] == "ambiguous"


def test_derived_website_candidates_are_conservative_and_exclude_directories():
    profile = {"organisation_number": ORG, "name": "Example AS", "legal_form": "AS", "website": "https://proff.no/example"}
    candidates = website_candidates(profile, derived=True)
    assert {candidate["url"] for candidate in candidates} == {"https://example.no/", "https://example.com/"}
    assert all("proff.no" not in candidate["url"] for candidate in candidates)
    assert any(candidate["source"] == "legal_name_domain" for candidate in candidates)


def test_derived_candidates_keep_both_registry_sources_and_bounded_domain_variants():
    profile = {
        "organisation_number": ORG,
        "name": "Royal Subsea AS",
        "legal_form": "AS",
        "website": "https://stale.example/",
        "evidence": {"registry_live": {"value": {"name": "Royal Subsea AS", "website": "https://current.example/"}}},
    }
    candidates = website_candidates(profile, derived=True)
    urls = {candidate["url"] for candidate in candidates}
    assert "https://stale.example/" in urls
    assert "https://current.example/" in urls
    assert "https://royalsubsea.no/" in urls
    assert "https://royal-subsea.no/" in urls
    assert "https://rs.no/" in urls
    assert "https://royalsubsea.com/" in urls
    assert len(candidates) <= 8


def test_registry_live_website_is_a_deterministic_candidate_even_without_snapshot_url():
    profile = {
        "organisation_number": ORG,
        "name": "Example AS",
        "evidence": {"registry_live": {"value": {"website": "https://current.example/"}}},
    }
    assert website_candidates(profile, derived=False) == [{"url": "https://current.example/", "source": "registry_live"}]
