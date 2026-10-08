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
            "jsonld": structured, "articles": articles}


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
