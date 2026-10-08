from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


CSS = """
:root{color-scheme:light dark;--bg:#f4f1ea;--card:#fffdf8;--ink:#1d2523;--muted:#5d6964;--line:#d5d0c5;--accent:#176b5b;--good:#176b5b;--warn:#9a6400;--bad:#a52c2c}
@media(prefers-color-scheme:dark){:root{--bg:#17201e;--card:#202b28;--ink:#f2f0e9;--muted:#b6c0ba;--line:#40504a;--accent:#80d1b9;--good:#80d1b9;--warn:#f2bd63;--bad:#ff9494}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}a{color:var(--accent)}header,main{max-width:1220px;margin:auto;padding:20px}header{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line)}nav{display:flex;gap:12px;flex-wrap:wrap}.brand{font-weight:800;letter-spacing:.04em;text-decoration:none;color:var(--ink)}h1{font-size:clamp(1.8rem,4vw,3.3rem);line-height:1.05;margin:28px 0 10px}h2{margin-top:28px}h3{margin:0 0 8px}.muted{color:var(--muted)}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.toolbar input,.toolbar select{font:inherit;padding:11px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:6px;min-width:220px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:16px;min-width:0}.company-card{display:block;text-decoration:none;color:var(--ink);transition:border-color .15s,transform .15s}.company-card:hover,.company-card:focus{border-color:var(--accent);transform:translateY(-1px)}.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 9px;font-size:.78rem;font-weight:700}.badge.available{color:var(--good)}.badge.ambiguous,.badge.blocked{color:var(--warn)}.badge.failed{color:var(--bad)}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}.fact{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:13px;min-width:0}.fact-label{display:block;color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.08em}.fact-value{display:block;margin-top:5px;overflow-wrap:anywhere}.claim{border-top:1px solid var(--line);padding:13px 0}.claim:first-child{border-top:0}.claim-value{white-space:pre-wrap;overflow-wrap:anywhere}.source{font-size:.82rem;color:var(--muted);margin-top:6px;overflow-wrap:anywhere}.source a{word-break:break-all}.unknown{border-left:3px solid var(--warn);padding:8px 12px;margin:7px 0;background:color-mix(in srgb,var(--warn) 10%,transparent)}table{width:100%;border-collapse:collapse;background:var(--card)}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}th{color:var(--muted)}.compare-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.empty{padding:24px;text-align:center;color:var(--muted)}button{font:inherit;padding:10px 13px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}@media(max-width:700px){header{align-items:flex-start;flex-direction:column;padding:16px}main{padding:16px}.compare-grid{grid-template-columns:1fr}table{font-size:.9rem}.toolbar input,.toolbar select{min-width:0;width:100%}}
"""


def _safe_text(value: Any) -> str:
    if value is None or value == "":
        return "Not available"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return str(value)


def _safe_href(value: Any) -> str | None:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return str(value)


def _json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).replace("<", "\\u003c")


def _layout(title: str, body: str, *, data: Any | None = None, script: str = "") -> str:
    embedded = f'<script id="signalpost-data" type="application/json">{_json_script(data)}</script>' if data is not None else ""
    inline_script = f"<script>{script}</script>" if script else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><title>{html.escape(title)}</title><style>{CSS}</style></head><body><header><a class="brand" href="index.html">Signalpost</a><nav aria-label="Primary"><a href="index.html">Companies</a><a href="compare.html">Compare</a><a href="changes.html">Changes</a></nav></header><main>{body}</main>{embedded}{inline_script}</body></html>'''


def _badge(status: str) -> str:
    safe = html.escape(status or "not_available", quote=True)
    return f'<span class="badge {safe}">{safe.replace("_", " ")}</span>'


def _claim_html(claim: dict[str, Any], snapshots: dict[str, dict[str, Any]]) -> str:
    value = html.escape(_safe_text(claim.get("value")))
    state = html.escape(str(claim.get("state") or "not_available"), quote=True)
    evidence_parts = []
    for ref in claim.get("evidence") or []:
        snapshot = snapshots.get(str(ref.get("snapshot_id"))) or {}
        url = _safe_href(snapshot.get("final_url") or snapshot.get("requested_url"))
        if url:
            evidence_parts.append(f'<a href="{html.escape(url, quote=True)}" rel="noreferrer">Source</a>')
        date = snapshot.get("retrieved_at") or claim.get("retrieved_at") or "date not available"
        evidence_parts.append(f"retrieved {html.escape(str(date))}")
        if claim.get("reporting_period") is not None:
            evidence_parts.append(f"period {html.escape(_safe_text(claim['reporting_period']))}")
    source = " · ".join(evidence_parts) or "No source reference"
    return f'<article class="claim"><strong>{html.escape(str(claim.get("field") or "Fact"))}</strong><div class="claim-value">{value}</div><div class="source">{source} · state {state}</div></article>'


def _profile_body(row: dict[str, Any], *, snapshots: dict[str, dict[str, Any]]) -> str:
    identity = row.get("identity") or {}
    org = str(row.get("organisation_number") or "")
    name = _safe_text(identity.get("name") or row.get("profile", {}).get("name") or org)
    claims = row.get("claims") or []
    claim_html = "".join(_claim_html(claim, snapshots) for claim in claims)
    sections = row.get("sections") or {}
    section_rows = []
    for section, detail in sections.items():
        state = str((detail or {}).get("state") or "not_available")
        section_rows.append(f'<li><strong>{html.escape(section.title())}</strong>: {_badge(state)}</li>')
    unknowns = row.get("synthesis", {}).get("unknowns") or []
    unknown_html = "".join(f'<li class="unknown">{html.escape(str(item))}</li>' for item in unknowns) or '<li class="muted">No unknown section states were recorded.</li>'
    synthesis = row.get("synthesis", {}).get("text") or "No source-linked synthesis is available."
    changes = row.get("refresh", {}).get("changes") or []
    change_html = "".join(f'<li>{html.escape(_safe_text(item.get("claim_key")))}: {html.escape(_safe_text(item.get("old")))} → {html.escape(_safe_text(item.get("new")))}</li>' for item in changes) or '<li class="muted">No material changes recorded.</li>'
    return f'''<p><a href="index.html">← all companies</a></p><div class="card"><div>{_badge(str(row.get("status") or "not_available"))}</div><h1>{html.escape(name)}</h1><p class="muted">Organisation number: {html.escape(org)}</p><p>{html.escape(str(synthesis))}</p></div><section><h2>Availability</h2><ul>{"".join(section_rows)}</ul></section><section><h2>Source-linked facts</h2><div class="card">{claim_html or '<p class="empty">No supported facts were published.</p>'}</div></section><section><h2>Unknowns</h2><ul>{unknown_html}</ul></section><section><h2>Change history</h2><ul>{change_html}</ul></section>'''


def _index_body(rows: list[dict[str, Any]]) -> str:
    cards = []
    for row in rows:
        org = str(row.get("organisation_number") or "")
        name = _safe_text((row.get("identity") or {}).get("name") or (row.get("profile") or {}).get("name") or org)
        status = str(row.get("status") or "not_available")
        cards.append(f'<a class="card company-card" data-search="{html.escape((org + " " + name).casefold(), quote=True)}" data-status="{html.escape(status, quote=True)}" href="company-{html.escape(org, quote=True)}.html"><span>{_badge(status)}</span><h2>{html.escape(name)}</h2><p class="muted">{html.escape(org)}</p></a>')
    body = f'''<h1>Company profiles</h1><p class="muted">Find source-linked facts by organisation number, name, or availability state.</p><div class="toolbar"><label for="search">Search <input id="search" type="search" placeholder="Name or organisation number"></label><label for="status">State <select id="status"><option value="">All states</option><option>available</option><option>not_available</option><option>ambiguous</option><option>blocked</option><option>failed</option></select></label></div><p id="count" class="muted">{len(cards)} profiles</p><div id="company-list" class="grid">{"".join(cards) or '<div class="empty">No profiles.</div>'}</div>'''
    script = """
const search=document.querySelector('#search'), status=document.querySelector('#status'), count=document.querySelector('#count');
function filter(){const q=(search.value||'').toLowerCase().trim(), s=status.value; let n=0; document.querySelectorAll('.company-card').forEach(card=>{const show=(!q||card.dataset.search.includes(q))&&(!s||card.dataset.status===s);card.hidden=!show;if(show)n++;});count.textContent=n+' profiles';}
search.addEventListener('input',filter);status.addEventListener('change',filter);
"""
    return body, script


def _compare_page(rows: list[dict[str, Any]]) -> tuple[str, str]:
    options = "".join(f'<option value="{html.escape(str(row.get("organisation_number") or ""), quote=True)}">{html.escape(_safe_text((row.get("identity") or {}).get("name") or row.get("organisation_number")))}</option>' for row in rows)
    payload = [{"org": row.get("organisation_number"), "name": (row.get("identity") or {}).get("name") or (row.get("profile") or {}).get("name") or row.get("organisation_number"), "status": row.get("status"), "claims": row.get("claims") or []} for row in rows]
    body = f'''<h1>Compare profiles</h1><p class="muted">Choose up to three companies. Each displayed value remains tied to its claim in the individual profile.</p><div class="toolbar"><label>Company 1 <select class="company-select"><option value="">Choose</option>{options}</select></label><label>Company 2 <select class="company-select"><option value="">Choose</option>{options}</select></label><label>Company 3 <select class="company-select"><option value="">Choose</option>{options}</select></label></div><div id="comparison" class="compare-grid"></div>'''
    script = f"""
const rows={_json_script(payload)}; const selects=[...document.querySelectorAll('.company-select')]; const params=new URLSearchParams(location.search); const requested=(params.get('org')||'').split(',').filter(Boolean); selects.forEach((select,i)=>{{if(requested[i])select.value=requested[i];select.addEventListener('change',render);}});
function render(){{const chosen=selects.map(x=>rows.find(row=>String(row.org)===x.value)).filter(Boolean);document.querySelector('#comparison').innerHTML='';if(!chosen.length){{document.querySelector('#comparison').textContent='Choose at least one company.';return;}}chosen.forEach(row=>{{const card=document.createElement('article');card.className='card';const title=document.createElement('h2');title.textContent=row.name||row.org;card.append(title);const status=document.createElement('p');status.textContent='State: '+(row.status||'not_available');card.append(status);(row.claims||[]).slice(0,12).forEach(claim=>{{const p=document.createElement('p');p.className='claim';p.textContent=claim.field+': '+JSON.stringify(claim.value);card.append(p);}});document.querySelector('#comparison').append(card);}})}}
render();
"""
    return body, script


def _changes_body(rows: list[dict[str, Any]]) -> str:
    changes = []
    for row in rows:
        for change in (row.get("refresh") or {}).get("changes") or []:
            org = str(row.get("organisation_number") or "")
            changes.append(f'<tr><td><a href="company-{html.escape(org, quote=True)}.html">{html.escape(org)}</a></td><td>{html.escape(_safe_text(change.get("claim_key")))}</td><td>{html.escape(_safe_text(change.get("old")))}</td><td>{html.escape(_safe_text(change.get("new")))}</td><td>{html.escape(_safe_text(change.get("materiality")))}</td></tr>')
    body = '<h1>Change history</h1><p class="muted">Material differences between the current profile and its supplied previous profile.</p><table><thead><tr><th>Organisation</th><th>Field</th><th>Previous</th><th>Current</th><th>Materiality</th></tr></thead><tbody>' + ("".join(changes) or '<tr><td colspan="5" class="empty">No material changes recorded.</td></tr>') + '</tbody></table>'
    return body


def read_envelopes(source: str | Path) -> list[dict[str, Any]]:
    path = Path(source)
    if path.is_dir():
        candidates = [path / "envelopes.jsonl", path / "output.jsonl"] + sorted(path.glob("*.jsonl"))
        path = next((candidate for candidate in candidates if candidate.exists()), path)
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else [value]
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def build_viewer(source: str | Path, output: str | Path) -> dict[str, Any]:
    rows = read_envelopes(source)
    rows.sort(key=lambda row: str(row.get("organisation_number") or ""))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    snapshots = {str(snapshot.get("snapshot_id")): snapshot for row in rows for snapshot in row.get("snapshots") or []}
    index_body, index_script = _index_body(rows)
    (out / "index.html").write_text(_layout("Signalpost profiles", index_body, script=index_script), encoding="utf-8")
    for row in rows:
        org = str(row.get("organisation_number") or "unknown")
        row_snapshots = {str(snapshot.get("snapshot_id")): snapshot for snapshot in row.get("snapshots") or []}
        (out / f"company-{re.sub(r'[^0-9A-Za-z_-]', '_', org)}.html").write_text(_layout(_safe_text((row.get("identity") or {}).get("name") or org), _profile_body(row, snapshots=row_snapshots)), encoding="utf-8")
    compare_body, compare_script = _compare_page(rows)
    (out / "compare.html").write_text(_layout("Compare profiles", compare_body, script=compare_script), encoding="utf-8")
    (out / "changes.html").write_text(_layout("Change history", _changes_body(rows)), encoding="utf-8")
    (out / "data.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"profiles": len(rows), "output": str(out), "files": len(list(out.iterdir()))}
