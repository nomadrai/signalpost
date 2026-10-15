from __future__ import annotations

import base64
import gzip
import hashlib
import json
from typing import Any

from bs4 import BeautifulSoup

from .evidence import utc_now


def source_document(body: bytes, url: str) -> dict[str, Any]:
    """Deterministic, replayable source representation, including footer text."""
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "lxml")
    structured = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            structured.append(json.loads(node.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
    articles = []
    for node in soup.select("article")[:100]:
        heading = node.select_one("h1, h2, h3")
        stamp = node.select_one("time[datetime]")
        link = heading.select_one("a[href]") if heading else None
        link = link or node.select_one("a[href]")
        if heading and stamp and link:
            articles.append({"title": heading.get_text(" ", strip=True),
                             "date": stamp.get("datetime"), "url": link.get("href")})
    microdata = []
    for node in soup.select("[itemscope][itemtype]")[:100]:
        itemtype = " ".join(str(node.get("itemtype") or "").split())
        lowered = itemtype.casefold()
        if not any(kind in lowered for kind in ("jobposting", "newsarticle", "article", "blogposting")):
            continue

        def prop(*names: str) -> str | None:
            for name in names:
                child = node.select_one(f'[itemprop="{name}"]')
                if child is None:
                    continue
                raw = child.get("content") or child.get("datetime") or child.get("href") or child.get_text(" ", strip=True)
                if raw:
                    return " ".join(str(raw).split())[:1000]
            return None

        owner = node.select_one('[itemprop="hiringOrganization"], [itemprop="publisher"]')
        owner_name = None
        owner_identifier = None
        if owner is not None:
            owner_name_node = owner.select_one('[itemprop="name"]') or owner
            owner_name = (owner_name_node.get("content") or owner_name_node.get_text(" ", strip=True))[:500] or None
            identifier = owner.select_one('[itemprop="identifier"]')
            owner_identifier = ((identifier.get("content") or identifier.get_text(" ", strip=True))[:200] if identifier else None)
        is_hiring = "jobposting" in lowered
        microdata.append({
            "kind": "hiring" if is_hiring else "activity",
            "itemtype": itemtype,
            "title": prop("title", "headline", "name"),
            "date": prop("datePosted", "datePublished", "dateCreated"),
            "valid_through": prop("validThrough") if is_hiring else None,
            "url": prop("url") or url,
            "owner_name": owner_name,
            "owner_identifier": owner_identifier,
        })
    description = soup.select_one('meta[name="description"], meta[property="og:description"]')
    identity = " ".join(node.get_text(" ", strip=True) for node in soup.select(
        'footer, address, [itemprop="legalName"], [itemprop="address"], [itemprop="telephone"]'))
    # Scripts/styles do not become visible ownership or body-text evidence.
    for node in soup.select("script, style, template, noscript"):
        node.decompose()
    return {"url": url, "title": soup.title.get_text(" ", strip=True) if soup.title else "",
            "description": str(description.get("content") or "") if description else "",
            "identity_text": " ".join(identity.split())[:10000],
            "visible_text": " ".join(soup.get_text(" ", strip=True).split())[:12000],
            "jsonld": structured, "articles": articles, "microdata": microdata}


def capture_page(body: bytes, *, requested_url: str, final_url: str,
                 redirect_chain: list | None = None) -> dict[str, Any]:
    document = source_document(body, final_url)
    return {"url": final_url, "requested_url": requested_url,
            "title": document["title"][:500], "description": document["description"][:2000],
            "identity_text_excerpt": document["identity_text"],
            "main_text_excerpt": document["visible_text"][:5000],
            "retrieved_at": utc_now(), "content_sha256": hashlib.sha256(body).hexdigest(),
            "redirect_chain": list(redirect_chain or []), "source_document": document,
            "body_gzip_base64": base64.b64encode(gzip.compress(body, mtime=0)).decode("ascii")}


def replay_document(snapshot: dict) -> dict:
    compressed = base64.b64decode(snapshot["body_gzip_base64"], validate=True)
    with gzip.GzipFile(fileobj=__import__("io").BytesIO(compressed)) as handle:
        body = handle.read(2_000_001)
    if len(body) > 2_000_000 or hashlib.sha256(body).hexdigest() != snapshot["content_sha256"]:
        raise ValueError("Captured page bytes do not match their content hash or byte limit")
    return source_document(body, snapshot["final_url"])


def read_path(document: Any, path: list) -> Any:
    for key in path:
        document = document[key]
    return document
