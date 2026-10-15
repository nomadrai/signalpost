from __future__ import annotations

import re
from typing import Any


def _claim(label: str, value: Any, record: dict[str, Any], classification: str) -> dict[str, Any]:
    return {
        "claim": label,
        "value": value,
        "classification": classification,
        "source_url": record.get("source_url"),
        "retrieved_at": record.get("retrieved_at"),
        "source_class": record.get("source_class") or record.get("source_type"),
        "content_sha256": record.get("content_sha256"),
    }


RESEARCH_TOPIC_PATTERNS = {
    "identity": (
        r"\b(?:who is|what is the company(?:\s|$)|company name|legal name|organisation number|organization number|org(?:anisation|anization)?\s*(?:no|number)|legal form|municipality|registered as)\b",
        r"\b(?:hvem er|organisasjonsnummer|org(?:anisasjons)?nr|organisasjonsform|kommune)\b",
    ),
    "financials": (
        r"\b(?:financial|finance|finances|account|accounts|revenue|turnover|income|profit|result|debt|asset|balance sheet|income statement|annual report|made|make|earned|generated|regnskap|omsetning|driftsresultat|årsresultat|eiendeler|gjeld)\b",
        r"\bhow much did (?:the company|it)\s+(?:make|earn|generate|bring in)\b",
    ),
    "roles": (
        r"\b(?:lead|leads|leader|leadership|role|roles|director|ceo|board|manager|manages|runs|who runs|who manages|styre|styret|daglig leder|leder|roller)\b",
    ),
    "locations": (
        r"\b(?:location|locations|where|workplace|workplaces|office|offices|branch|branches|address|addresses|based|physical presence|registered subunit|registered units|adresse|arbeidssted|avdeling|sted)\b",
    ),
    "website": (
        r"\b(?:website|web site|homepage|home page|online|company site|official site|nettside|hjemmeside)\b",
    ),
    "social": (
        r"\b(?:social|social media|linkedin|facebook|instagram|youtube|tiktok|profile|profiles)\b",
    ),
    "employee": (
        r"\b(?:employee|employees|staff|workforce|workers|headcount|people work|work there|ansatte|arbeidere)\b",
    ),
    "sentiment": (
        r"\b(?:sentiment|reputation|reviews|review|rating|ratings|opinion|buzz|glassdoor|satisfaction)\b",
    ),
}
GENERAL_QUESTION_PATTERNS = (
    r"\b(?:what do we know|tell me about|give me an overview|summari[sz]e|overview|general information|all available information)\b",
    r"\b(?:hva vet vi|fortell meg om|oversikt|oppsummer)\b",
)
SUPPORTED_RESEARCH_TOPICS = ("identity", "financials", "roles", "locations", "website", "social", "employee")


def parse_question_intent(question: str) -> dict[str, Any]:
    """Map flexible local phrasing to a closed evidence topic set.

    This is intentionally a local regex/topic normalizer, not an LLM call. It
    never creates a fact and abstains when the question is outside the supported
    evidence families.
    """
    normalized = " ".join(str(question or "").casefold().split())
    topics = sorted({
        topic
        for topic, patterns in RESEARCH_TOPIC_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    })
    if not topics and any(re.search(pattern, normalized) for pattern in GENERAL_QUESTION_PATTERNS):
        return {"mode": "overview", "topics": list(SUPPORTED_RESEARCH_TOPICS), "normalized_question": normalized, "local_only": True}
    if topics:
        return {"mode": "topic", "topics": topics, "normalized_question": normalized, "local_only": True}
    return {"mode": "abstain", "topics": [], "normalized_question": normalized, "local_only": True}


def answer_profile(row: dict[str, Any], question: str) -> dict[str, Any]:
    """Local bounded retrieval layer; it never invents a missing field or calls a model."""
    intent = parse_question_intent(question)
    q = intent["normalized_question"]
    topics = set(intent["topics"])
    all_topics = intent["mode"] == "overview"
    evidence = row.get("evidence", {})
    facts: list[dict[str, Any]] = []
    unsupported: list[str] = []

    if intent["mode"] == "abstain":
        unsupported.append("This local bounded answer supports identity, financials, roles, locations, websites, social profiles, and employees only; no external request was made.")

    registry = evidence.get("registry", {})
    if all_topics or "identity" in topics or "employee" in topics:
        for label, value in (
            ("Registered name", row.get("name")),
            ("Organisation number", row.get("organisation_number")),
            ("Legal form", row.get("legal_form")),
            ("Municipality", row.get("municipality")),
            ("Registry employee count", row.get("employees")),
        ):
            if value not in (None, ""):
                facts.append(_claim(label, value, registry, "official_registry_fact"))

    financial = evidence.get("financials", {})
    if all_topics or "financials" in topics:
        records = (financial.get("value") or {}).get("records") or []
        if records:
            latest = records[0]
            for label, key in (
                ("Reporting period", "period"),
                ("Revenue", "revenue"),
                ("Operating result", "operating_result"),
                ("Annual result", "annual_result"),
                ("Assets", "assets"),
                ("Debt", "debt"),
            ):
                if latest.get(key) is not None:
                    facts.append(_claim(label, latest[key], financial, "official_annual_account"))
        else:
            unsupported.append("No normalized annual-account record was returned; missing values are not interpreted as zero.")

    roles = evidence.get("roles", {})
    if all_topics or "roles" in topics:
        people = [item for item in (roles.get("value") or {}).get("roles", []) if not item.get("inactive")]
        for person in people[:12]:
            facts.append(_claim(person.get("role") or person.get("group") or "Registered role", person.get("name") or person.get("organisation_number"), roles, "official_role_record"))
        if not people:
            unsupported.append("No active public role holder was returned.")

    locations = evidence.get("locations", {})
    if all_topics or "locations" in topics:
        items = (locations.get("value") or {}).get("locations", [])
        for item in items[:12]:
            facts.append(_claim("Registered subunit", {"name": item.get("name"), "address": item.get("address")}, locations, "official_subunit_record"))
        if not items:
            unsupported.append("No registered subunit was returned; this does not prove the company has no physical presence.")

    website = evidence.get("website", {})
    if all_topics or "website" in topics or "social" in topics:
        value = website.get("value") or {}
        website_publishable = (value.get("identity_assessment") or {}).get("publishable", True)
        if value.get("description") and website_publishable:
            facts.append(_claim("Website description", value["description"], website, "company_reported_claim"))
        for item in (value.get("social_links") or []) if website_publishable and (all_topics or "social" in topics) else []:
            facts.append(_claim(f"Declared {item['platform']} profile", item["url"], website, "company_linked_social_profile"))
        if website.get("status") == "available" and not website_publishable:
            unsupported.append("A registry-linked website was fetched, but exact legal-entity identity was not established; its claims and social links are quarantined.")
        if website.get("status") != "available":
            unsupported.append("The registry-linked company website was not available to this run.")

    if "sentiment" in topics:
        unsupported.append("Sentiment is not scored: no labelled Norwegian news/social evaluation corpus has been run, and company-owned pages are structurally promotional.")

    return {
        "organisation_number": row.get("organisation_number"),
        "company_name": row.get("name"),
        "question": question,
        "facts": facts,
        "unsupported_or_uncertain": unsupported,
        "intent": intent,
        "answer_policy": "Local natural-language topic matching routes only to retained evidence; no model, paid API, or live crawl is used.",
    }


UNSUPPORTED_SCREEN_TERMS = {
    "sentiment": "sentiment is not qualified",
    "glassdoor": "Glassdoor data is not available through a permitted connector",
    "linkedin": "LinkedIn-derived employee data is not available through a permitted connector",
    "traffic": "website traffic is not available through a qualified provider",
    "reviews": "review data is not available through a qualified provider",
    "buzz": "social buzz is not available through a qualified provider",
    "without a website": "missing or unverified website evidence does not prove that a company has no website",
}


def _latest_financial(row: dict[str, Any]) -> dict[str, Any]:
    records = ((row.get("evidence", {}).get("financials", {}).get("value") or {}).get("records") or [])
    return records[0] if records else {}


def _numeric_operator(phrase: str) -> str:
    return {
        "more than": ">", "over": ">", "above": ">", "at least": ">=",
        "fewer than": "<", "less than": "<", "under": "<", "at most": "<=",
    }.get(phrase.casefold(), phrase)


def parse_screen_query(query: str) -> dict[str, Any]:
    """Parse a deliberately closed company-screen grammar into an inspectable plan."""
    text = " ".join(query.strip().split())
    lower = text.casefold()
    filters: list[dict[str, Any]] = []
    unsupported = [message for term, message in UNSUPPORTED_SCREEN_TERMS.items() if term in lower]

    municipality = re.search(r"\b(?:in|municipality(?:\s+is|\s*=)?)\s+([a-zæøåéü .'-]+?)(?=\s+(?:with|and|having|that|where)\b|$)", lower)
    if municipality:
        filters.append({"field": "municipality", "operator": "eq", "value": municipality.group(1).strip().upper(), "evidence_module": "registry"})

    legal_form = re.search(r"\b(?:legal\s+form|organisation\s+form)\s*(?:is|=)?\s*(asa|as|enk|nuf|ans|da|sa|sti|brl)\b", lower)
    if legal_form:
        filters.append({"field": "legal_form", "operator": "eq", "value": legal_form.group(1).upper(), "evidence_module": "registry"})

    employees = re.search(r"\b(more than|over|above|at least|fewer than|less than|under|at most)\s+(\d+)\s+(?:registered\s+)?employees?\b", lower)
    if not employees:
        employees = re.search(r"\bemployees?\s*(>=|<=|>|<|=)\s*(\d+)\b", lower)
    if employees:
        filters.append({"field": "employees", "operator": _numeric_operator(employees.group(1)), "value": int(employees.group(2)), "evidence_module": "registry"})

    revenue = re.search(r"\brevenue\s*(>=|<=|>|<|=|more than|over|above|at least|fewer than|less than|under|at most)\s*(?:nok\s*)?([\d.,]+)\s*(billion|million|bn|m)?\b", lower)
    if not revenue:
        revenue = re.search(r"\b(more than|over|above|at least|fewer than|less than|under|at most)\s*(?:nok\s*)?([\d.,]+)\s*(billion|million|bn|m)?\s+revenue\b", lower)
    if revenue:
        amount = float(revenue.group(2).replace(",", "."))
        unit = revenue.group(3)
        amount *= 1_000_000_000 if unit in {"billion", "bn"} else 1_000_000 if unit in {"million", "m"} else 1
        filters.append({"field": "revenue", "operator": _numeric_operator(revenue.group(1)), "value": amount, "evidence_module": "financials"})

    if re.search(r"\bunprofitable|loss[- ]making|negative annual result\b", lower):
        filters.append({"field": "annual_result", "operator": "<", "value": 0, "evidence_module": "financials"})
    elif re.search(r"\bprofitable|positive annual result\b", lower):
        filters.append({"field": "annual_result", "operator": ">", "value": 0, "evidence_module": "financials"})

    if re.search(r"\b(?:with|has|have)\s+(?:an?\s+)?(?:official\s+)?website\b", lower):
        filters.append({"field": "website", "operator": "present", "value": True, "evidence_module": "website"})
    if re.search(r"\b(?:with|has|have)\s+(?:annual\s+)?accounts\b", lower):
        filters.append({"field": "financials", "operator": "available", "value": True, "evidence_module": "financials"})

    industry = re.search(r"\bindustry(?:\s+contains|\s+is|\s*=)?\s+[\"']([^\"']+)[\"']", text, flags=re.IGNORECASE)
    if industry:
        filters.append({"field": "industry", "operator": "contains", "value": industry.group(1).casefold(), "evidence_module": "registry"})

    sort = None
    top = re.search(r"\btop\s+(\d+)\s+by\s+(revenue|employees)\b", lower)
    if top:
        sort = {"field": top.group(2), "direction": "desc", "limit": min(int(top.group(1)), 100)}
    return {
        "version": "closed_company_screen_v1",
        "query": text,
        "filters": filters,
        "sort": sort,
        "unsupported": unsupported,
        "executable": bool(filters or sort) and not unsupported,
    }


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return str(actual or "").casefold() == str(expected or "").casefold()
    if operator == "present":
        return bool(actual) is bool(expected)
    if operator == "available":
        return bool(actual) is bool(expected)
    if operator == "contains":
        return str(expected).casefold() in str(actual or "").casefold()
    if actual is None:
        return False
    return {">": actual > expected, ">=": actual >= expected, "<": actual < expected, "<=": actual <= expected, "=": actual == expected}[operator]


def _screen_value(row: dict[str, Any], field: str) -> Any:
    if field in {"municipality", "legal_form", "employees"}:
        return row.get(field)
    if field in {"revenue", "annual_result"}:
        return _latest_financial(row).get(field)
    if field == "website":
        record = row.get("evidence", {}).get("website", {})
        return record.get("status") == "available" and bool((record.get("value") or {}).get("identity_assessment", {}).get("publishable", True))
    if field == "financials":
        return row.get("evidence", {}).get("financials", {}).get("status") == "available"
    if field == "industry":
        return " ".join(filter(None, [str(row.get("industry_code") or ""), str(row.get("industry_label") or "")]))
    return None


def screen_profiles(rows: list[dict[str, Any]], query: str) -> dict[str, Any]:
    plan = parse_screen_query(query)
    if not plan["executable"]:
        return {"query": query, "plan": plan, "results": [], "result_count": 0, "abstained": True, "reason": "; ".join(plan["unsupported"]) or "No supported criterion was recognized."}
    results = []
    for row in rows:
        if not all(_compare(_screen_value(row, item["field"]), item["operator"], item["value"]) for item in plan["filters"]):
            continue
        citations = []
        evidence_modules = {item["evidence_module"] for item in plan["filters"]}
        if plan.get("sort"):
            evidence_modules.add("financials" if plan["sort"]["field"] == "revenue" else "registry")
        for module in sorted(evidence_modules):
            record = row.get("evidence", {}).get(module, {})
            citations.append({
                "module": module,
                "source_url": record.get("source_url"),
                "retrieved_at": record.get("retrieved_at"),
                "content_sha256": record.get("content_sha256"),
            })
        results.append({
            "organisation_number": row.get("organisation_number"),
            "name": row.get("name"),
            "municipality": row.get("municipality"),
            "employees": row.get("employees"),
            "revenue": _latest_financial(row).get("revenue"),
            "annual_result": _latest_financial(row).get("annual_result"),
            "citations": citations,
        })
    sort = plan.get("sort")
    if sort:
        results.sort(key=lambda item: (item.get(sort["field"]) is None, -(item.get(sort["field"]) or 0), item.get("organisation_number") or ""))
        results = results[: sort["limit"]]
    else:
        results.sort(key=lambda item: item.get("organisation_number") or "")
    return {"query": query, "plan": plan, "results": results, "result_count": len(results), "abstained": False}
