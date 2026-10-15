from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


# THESIS: Signalpost turns public company evidence into a calm, navigable record.
# OWN-WORLD: warm paper, forest ink, marigold wayfinding, outline symbols, and source-first data panels.
# STORY: find a company, understand its verified sections, inspect freshness, then ask a bounded question.
# FIRST VIEWPORT: a compact research header, searchable directory, and evidence status visible before the first scroll.
# FORM: evidence desk, an editorial operations surface inspired by the supplied reference project.
# FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md


CSS = """
:root {
  color-scheme: light;
  --paper: #fbf7f0;
  --paper-2: #f4ecdd;
  --paper-3: #ebe0cc;
  --ink: #191610;
  --ink-soft: #4b453a;
  --muted: #6f6759;
  --forest: #254e2b;
  --forest-dark: #152d1a;
  --forest-soft: #dbe9d7;
  --gold: #eda42e;
  --red: #a44735;
  --line: #d8cdbb;
  --white: #fffdf8;
  --shadow: 0 18px 50px rgba(37, 78, 43, .08);
  --radius: 18px;
  --radius-sm: 10px;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Instrument Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: .16;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.18'/%3E%3C/svg%3E");
  mix-blend-mode: multiply;
  z-index: -1;
}
a { color: var(--forest); text-underline-offset: 3px; }
a:hover { color: var(--forest-dark); }
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }
::selection { background: var(--gold); color: var(--ink); }
:focus-visible { outline: 3px solid var(--gold); outline-offset: 3px; border-radius: 6px; }

.skip-link { position: absolute; left: -9999px; top: 12px; z-index: 10; padding: 10px 14px; background: var(--forest-dark); color: var(--paper); border-radius: 8px; }
.skip-link:focus { left: 14px; }
.site-header { position: sticky; top: 0; z-index: 5; background: rgba(251, 247, 240, .94); border-bottom: 1px solid var(--line); backdrop-filter: blur(14px); }
.header-inner { max-width: 1320px; margin: auto; padding: 14px 28px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.brand { display: inline-flex; align-items: center; gap: 11px; color: var(--ink); font-weight: 800; letter-spacing: -.02em; text-decoration: none; }
.brand-mark { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--forest); color: var(--gold); box-shadow: 0 0 0 5px var(--forest-soft); }
.brand-mark .icon { width: 18px; height: 18px; }
.nav { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.nav a { display: inline-flex; align-items: center; gap: 7px; padding: 8px 11px; border-radius: 8px; color: var(--muted); font-size: .85rem; font-weight: 700; text-decoration: none; }
.nav a:hover, .nav a.active { background: var(--paper-2); color: var(--forest-dark); }
.nav a.active { box-shadow: inset 0 -2px var(--gold); }
.icon { width: 1em; height: 1em; display: inline-block; flex: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; fill: none; }

.page { max-width: 1380px; margin: 0 auto; padding: 52px 28px 84px; }
.page-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 32px; }
.page-head h1 { max-width: 780px; }
.kicker { display: inline-flex; align-items: center; gap: 9px; color: var(--forest); font-size: .72rem; font-weight: 800; letter-spacing: .18em; text-transform: uppercase; }
.kicker::before { content: ""; width: 28px; height: 1px; background: currentColor; opacity: .65; }
h1, h2, h3 { font-family: "Fraunces", Georgia, "Times New Roman", serif; letter-spacing: -.025em; text-wrap: balance; }
h1 { font-size: clamp(2.2rem, 5vw, 4.5rem); line-height: 1.02; margin: 10px 0 12px; }
h2 { font-size: clamp(1.55rem, 2.8vw, 2.25rem); line-height: 1.1; margin: 0 0 9px; }
h3 { font-size: 1.26rem; line-height: 1.2; margin: 0 0 8px; }
.lead { max-width: 67ch; font-size: 1.08rem; color: var(--ink-soft); }
.muted { color: var(--muted); }
.surface { background: var(--white); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); }
.surface.pad { padding: 22px; }
.surface.dark { background: var(--forest-dark); color: var(--paper); border-color: var(--forest-dark); }
.surface.gold { background: var(--gold); border-color: var(--gold); color: var(--ink); }

.toolbar { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; padding: 14px 16px; background: var(--paper-2); border: 1px solid var(--line); border-radius: var(--radius-sm); margin: 22px 0; }
.control { display: grid; gap: 5px; min-width: 230px; }
.control label, .field-label { color: var(--muted); font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.input-wrap { position: relative; flex: 1; }
.input-wrap .icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); width: 17px; height: 17px; color: var(--forest); }
.input, .select { width: 100%; min-height: 44px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--white); color: var(--ink); }
.input-wrap .input { padding-left: 38px; }
.input:hover, .select:hover { border-color: var(--forest); }
.button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 42px; padding: 9px 14px; border: 1px solid var(--forest); border-radius: 8px; background: var(--forest); color: var(--paper); font-weight: 800; text-decoration: none; }
.button:hover { background: var(--forest-dark); color: var(--paper); }
.button.secondary { background: transparent; color: var(--forest); }
.button.secondary:hover { background: var(--forest-soft); }
.button.small { min-height: 34px; padding: 6px 10px; font-size: .82rem; }
.button.gold { background: var(--gold); border-color: var(--gold); color: var(--ink); }
.button.gold:hover { background: #dd8a17; border-color: #dd8a17; }
.count-line { display: flex; justify-content: space-between; gap: 12px; margin: 16px 0 12px; font-size: .9rem; }

.company-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(275px, 1fr)); gap: 16px; }
.company-card { display: flex; flex-direction: column; min-height: 174px; padding: 19px; color: var(--ink); text-decoration: none; transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
.company-card:hover, .company-card:focus { transform: translateY(-3px); border-color: var(--forest); box-shadow: 0 22px 46px rgba(37, 78, 43, .13); }
.company-card[hidden] { display: none; }
.company-card .card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.company-card h2 { font-size: 1.35rem; margin-top: 24px; }
.company-card .org { margin-top: auto; color: var(--muted); font-size: .86rem; font-variant-numeric: tabular-nums; }
.badge { display: inline-flex; align-items: center; gap: 6px; border: 1px solid currentColor; border-radius: 999px; padding: 4px 9px; font-size: .72rem; font-weight: 800; line-height: 1; white-space: nowrap; }
.badge.available { color: var(--forest); }
.badge.not_available, .badge.not_applicable { color: var(--muted); }
.badge.ambiguous, .badge.blocked { color: #8a5d0b; }
.badge.failed { color: var(--red); }
.empty { padding: 28px; border: 1px dashed var(--line); border-radius: var(--radius-sm); color: var(--muted); text-align: center; background: var(--paper-2); }
.coverage-panel { display: grid; grid-template-columns: minmax(220px, .7fr) minmax(0, 1.3fr); gap: 20px; align-items: end; margin: 28px 0; padding: 22px; background: var(--forest-dark); color: var(--paper); border-radius: var(--radius); }
.coverage-panel .kicker { color: var(--gold); }
.coverage-panel h2 { margin-top: 9px; color: var(--paper); }
.coverage-panel p { margin: 0; color: var(--paper-3); }
.coverage-controls { display: grid; gap: 9px; }
.coverage-controls label { color: var(--paper-3); font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.coverage-select { width: 100%; min-height: 44px; padding: 10px 12px; border: 1px solid rgba(255,255,255,.24); border-radius: 8px; background: var(--paper); color: var(--ink); }
.coverage-detail { display: grid; gap: 8px; min-height: 100%; padding: 15px; border: 1px solid rgba(255,255,255,.18); border-radius: 10px; background: rgba(255,255,255,.06); }
.coverage-detail strong { color: var(--gold); }
.coverage-command { display: block; padding: 9px 10px; overflow-wrap: anywhere; background: rgba(0,0,0,.22); border-radius: 7px; color: var(--paper-3); font: .76rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
.coverage-actions { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.coverage-actions .button.secondary { border-color: var(--gold); color: var(--gold); }
.coverage-actions .button.secondary:hover { background: rgba(237,164,46,.12); }

.hero { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 24px; align-items: stretch; margin-bottom: 22px; }
.hero-main { padding: 30px; }
.hero-main h1 { max-width: 800px; }
.hero-meta, .hero-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.hero-meta { margin: 18px 0; }
.hero-actions { margin-top: 22px; }
.meta-chip { display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 999px; color: var(--ink-soft); font-size: .82rem; background: var(--paper); }
.hero-side { padding: 22px; background: var(--forest-dark); color: var(--paper); border: 1px solid var(--forest-dark); border-radius: var(--radius); }
.hero-side .kicker { color: var(--gold); }
.hero-side h2 { font-size: 1.55rem; margin-top: 18px; }
.proof-list, .unknown-list { list-style: none; padding: 0; margin: 0; }
.proof-list li, .unknown-list li { display: flex; align-items: flex-start; gap: 10px; padding: 11px 0; border-top: 1px solid var(--line); }
.surface.dark .proof-list li { border-color: rgba(255, 255, 255, .17); }
.proof-list li:first-child, .unknown-list li:first-child { border-top: 0; }
.proof-list .icon { margin-top: 3px; color: var(--gold); }
.proof-note { display: block; margin-top: 2px; color: var(--paper-3); font-size: .72rem; font-weight: 400; }
.unknown-list .icon { margin-top: 3px; color: #a87012; }
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0; }
.metric { padding: 17px; background: var(--paper-2); border: 1px solid var(--line); border-radius: var(--radius-sm); }
.metric-value { display: block; margin-top: 8px; font-size: 1.28rem; font-weight: 800; letter-spacing: -.025em; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.metric-note { display: block; margin-top: 4px; color: var(--muted); font-size: .76rem; }
.two-col { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr); gap: 24px; align-items: start; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 34px 0 14px; }
.section-heading h2 { margin: 0; }
.company-overview { margin: 26px 0 30px; background: var(--paper-2); box-shadow: none; }
.company-overview .section-heading { margin-top: 0; }
.overview-copy { max-width: 72ch; margin: 0; font-size: 1.08rem; color: var(--ink-soft); }
.overview-proof { margin-top: 14px; color: var(--muted); font-size: .82rem; }
.overview-proof a { font-weight: 800; }
.availability { display: grid; gap: 7px; }
.availability-row { display: grid; grid-template-columns: 26px minmax(0, 1fr) minmax(132px, auto); align-items: center; gap: 10px; padding: 11px 0; border-top: 1px solid var(--line); }
.availability-row:first-child { border-top: 0; }
.availability-row > .icon { color: var(--forest); }
.availability-state { display: grid; justify-items: end; gap: 4px; }
.state-note { color: var(--muted); font-size: .72rem; text-align: right; }
.freshness { display: inline-flex; align-items: center; gap: 5px; color: var(--muted); font-size: .76rem; }
.claim-list { display: grid; gap: 0; }
.claim { padding: 18px 0; border-top: 1px solid var(--line); }
.claim:first-child { border-top: 0; }
.claim-head { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
.claim-label { color: var(--ink-soft); font-size: .83rem; font-weight: 800; }
.claim-value { margin-top: 8px; font-size: 1rem; white-space: pre-wrap; overflow-wrap: anywhere; }
.claim-value.json { max-height: 180px; overflow: auto; padding: 11px; background: var(--paper-2); border-radius: 8px; font: .86rem/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
.source-row { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-top: 10px; color: var(--muted); font-size: .78rem; }
.source-row a { display: inline-flex; align-items: center; gap: 5px; font-weight: 700; }
.claim-details { margin-top: 10px; }
.claim-details summary { cursor: pointer; color: var(--forest); font-size: .78rem; font-weight: 800; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 9px; color: var(--muted); font-size: .76rem; }
.synthesis-sentence { margin: 0; padding: 12px 0; border-top: 1px solid var(--line); }
.synthesis-sentence:first-child { border-top: 0; }
.proof-link { display: inline-flex; align-items: center; gap: 4px; margin-left: 5px; font-size: .75rem; font-weight: 800; }
.research { margin-top: 24px; }
.research-form { display: flex; gap: 9px; align-items: stretch; }
.research-form textarea { flex: 1; min-height: 48px; resize: vertical; padding: 11px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--white); color: var(--ink); }
.research-output { margin-top: 15px; }
.research-fact { padding: 12px 0; border-top: 1px solid var(--line); }
.research-fact:first-child { border-top: 0; }
.research-status { color: var(--muted); font-size: .86rem; }
.compare-shell { padding: 22px; }
.compare-table-wrap, .changes-table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 12px; }
.compare-table, .changes-table { width: 100%; min-width: 720px; border-collapse: collapse; }
.compare-table th, .compare-table td, .changes-table th, .changes-table td { padding: 13px 14px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
.compare-table th { background: var(--forest-dark); color: var(--paper); font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; }
.compare-table th:first-child { min-width: 190px; }
.compare-table td:first-child { color: var(--ink-soft); font-weight: 800; }
.compare-table tr:last-child td, .changes-table tr:last-child td { border-bottom: 0; }
.compare-cell { min-width: 170px; }
.compare-value { display: block; max-width: 260px; overflow-wrap: anywhere; }
.compare-link { display: inline-flex; align-items: center; gap: 4px; margin-top: 7px; font-size: .74rem; font-weight: 800; }
.changes-table-wrap { background: var(--white); border-radius: var(--radius); }
.changes-table th { background: var(--paper-2); color: var(--muted); font-size: .76rem; letter-spacing: .06em; text-transform: uppercase; }
.changes-table td { font-size: .88rem; }
.change-value { max-width: 230px; white-space: pre-wrap; overflow-wrap: anywhere; }
.footer { max-width: 1380px; margin: auto; padding: 24px 28px 42px; color: var(--muted); font-size: .78rem; display: flex; justify-content: space-between; gap: 20px; border-top: 1px solid var(--line); }
@media (max-width: 900px) { .hero, .two-col { grid-template-columns: 1fr; } .metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px) {
  .header-inner { padding-left: 16px; padding-right: 16px; align-items: flex-start; }
  .nav { justify-content: flex-end; }
  .nav a { padding: 7px 6px; font-size: .76rem; }
  .page { padding: 34px 16px 60px; }
  .coverage-panel { grid-template-columns: 1fr; align-items: stretch; }
  .page-head { display: block; }
  .hero-main { padding: 22px; }
  .metric-grid { gap: 8px; }
  .metric { padding: 13px; }
  .metric-value { font-size: 1.05rem; }
  .availability-row { grid-template-columns: 22px minmax(0, 1fr); }
  .availability-state { grid-column: 2; justify-items: start; }
  .state-note { text-align: left; }
  .research-form { display: grid; }
  .evidence-grid { grid-template-columns: 1fr; }
  .footer { display: block; padding-left: 16px; padding-right: 16px; }
  .footer span { display: block; margin-top: 8px; }
}
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important; transition-duration: .001ms !important; } }
"""


ICON_NAMES = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    "arrow-right": '<path d="M4 12h15"/><path d="m13 6 6 6-6 6"/>',
    "arrow-up-right": '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M3 10h18"/><path d="M8 2.5v4M16 2.5v4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18-2.5-3-2.5-15 0-18Z"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "building": '<path d="M4 21V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v16M2 21h20M8 7h2M8 11h2M8 15h2M13 7h2M13 11h2M13 15h2M11 21v-3h3v3"/>',
    "chart": '<path d="M4 19V5M4 19h17"/><path d="m7 15 3-4 3 2 5-7"/>',
    "check": '<path d="m4 12 5 5L20 6"/>',
    "alert": '<path d="M10.3 3.8 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    "external": '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.7-4L3 10M3 5v5h5M4 13a8 8 0 0 0 14.7 4L21 14m0 5v-5h-5"/>',
    "file": '<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5M9 12h6M9 16h6"/>',
    "spark": '<path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8Z"/>',
}


def _icon(name: str, *, label: str | None = None, class_name: str = "icon") -> str:
    aria = f' role="img" aria-label="{html.escape(label, quote=True)}"' if label else ' aria-hidden="true"'
    return f'<svg class="{class_name}" viewBox="0 0 24 24"{aria} focusable="false">{ICON_NAMES.get(name, ICON_NAMES["file"])}</svg>'


def _sprite() -> str:
    return "<svg aria-hidden=\"true\" width=\"0\" height=\"0\" style=\"position:absolute\"><defs>" + "".join(
        f'<symbol id="icon-{name}" viewBox="0 0 24 24">{paths}</symbol>' for name, paths in ICON_NAMES.items()
    ) + "</defs></svg>"


COVERAGE_PROFILES = [
    {"id": "default", "label": "Default balanced profile", "focus": "Completes official categories before optional discovery.", "note": "Use this for the normal Builderr run."},
    {"id": "accounts-diagnostic", "label": "Annual accounts priority", "focus": "Moves annual accounts ahead of optional website work.", "note": "Useful when financial coverage matters most."},
    {"id": "leadership-diagnostic", "label": "Leadership priority", "focus": "Moves registered roles ahead of optional website work.", "note": "Useful when public role coverage matters most."},
    {"id": "workplaces-diagnostic", "label": "Workplaces priority", "focus": "Moves registered subunits ahead of websites and discovery.", "note": "Useful when workplace coverage matters most."},
    {"id": "website-diagnostic", "label": "Official website priority", "focus": "Moves registry-linked website crawling earlier.", "note": "Useful for exact-company website recall."},
    {"id": "hiring-diagnostic", "label": "Hiring priority", "focus": "Fetches a verified website before local hiring extraction.", "note": "Hiring still requires retained first-party evidence."},
    {"id": "activity-diagnostic", "label": "Activity priority", "focus": "Fetches a verified website before local activity extraction.", "note": "Activity still requires retained dated evidence."},
    {"id": "website-discovery-diagnostic", "label": "Website discovery priority", "focus": "Runs registry website work before opt-in discovery.", "note": "Requires --discover-websites and remains budgeted."},
    {"id": "group-diagnostic", "label": "Group structure priority", "focus": "Moves official group structure work earlier.", "note": "Useful when relationships matter most."},
    {"id": "financial-history-diagnostic", "label": "Account history priority", "focus": "Moves annual-account history work earlier.", "note": "Useful when multi-year context matters most."},
]


def _display_text(value: Any) -> str:
    text = str(value or "")
    # Preserve source data in the batch, but use plain punctuation in the UI.
    return re.sub(r"\s+", " ", text.replace("\u2014", " - ")).strip()


def _safe_text(value: Any) -> str:
    if value is None or value == "":
        return "Not available"
    if isinstance(value, (dict, list)):
        return _display_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return _display_text(value)


def _ui_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _ui_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_ui_value(child) for child in value]
    return _display_text(value) if isinstance(value, str) else value


def _safe_href(value: Any) -> str | None:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return str(value)


def _json_script(value: Any) -> str:
    return json.dumps(_ui_value(value), ensure_ascii=False, separators=(",", ":"), default=str).replace("<", "\\u003c")


def _friendly(value: str) -> str:
    labels = {
        "not_available": "Not available", "not_applicable": "Not applicable", "available": "Available",
        "ambiguous": "Needs review", "blocked": "Blocked", "failed": "Failed", "identity": "Identity",
        "accounts": "Annual accounts", "leadership": "Leadership", "workplaces": "Workplaces",
        "website": "Official website", "profiles": "Company profiles", "hiring": "Hiring", "activity": "Activity",
    }
    return labels.get(value, value.replace("_", " ").title())


def _status_icon(status: str) -> str:
    return "check" if status == "available" else "alert" if status in {"ambiguous", "blocked", "failed"} else "clock"


def _badge(status: str) -> str:
    safe = html.escape(status or "not_available", quote=True)
    return f'<span class="badge {safe}">{_icon(_status_icon(status), class_name="icon")} {_friendly(status or "not_available")}</span>'


def _short_date(value: Any) -> str:
    text = _display_text(value)
    return text[:10] if text else "Date not available"


def _domain(value: Any) -> str:
    url = _safe_href(value)
    if not url:
        return "Source record"
    return (urllib.parse.urlparse(url).hostname or "Source record").removeprefix("www.")


def _claim_html(claim: dict[str, Any], snapshots: dict[str, dict[str, Any]]) -> str:
    claim_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(claim.get("claim_id") or "claim"))
    raw_value = claim.get("value")
    value = html.escape(_safe_text(raw_value))
    value_class = "claim-value json" if isinstance(raw_value, (dict, list)) else "claim-value"
    evidence_parts = []
    details = []
    for ref in claim.get("evidence") or []:
        snapshot = snapshots.get(str(ref.get("snapshot_id"))) or {}
        url = _safe_href(snapshot.get("final_url") or snapshot.get("requested_url"))
        if url:
            evidence_parts.append(f'<a href="{html.escape(url, quote=True)}" rel="noreferrer">{_icon("external")} {_domain(url)}</a>')
        evidence_parts.append(f'{_icon("calendar")} {_short_date(snapshot.get("retrieved_at") or claim.get("retrieved_at"))}')
        if snapshot.get("content_sha256"):
            details.append(f"Content hash: {html.escape(_display_text(snapshot['content_sha256']))}")
    details.extend([
        f"Extraction: {html.escape(_display_text(claim.get('extraction_method') or 'Not recorded'))}",
        f"Identity tier: {html.escape(_display_text(claim.get('identity_tier') or 'Not recorded'))}",
        f"Confidence: {html.escape(str(claim.get('confidence') if claim.get('confidence') is not None else 'Not recorded'))}",
    ])
    source = " ".join(evidence_parts) or f'{_icon("alert")} No source reference'
    details_html = "".join(f"<div>{item}</div>" for item in details)
    state = str(claim.get("state") or "not_available")
    return f'''<article class="claim" id="claim-{html.escape(claim_id, quote=True)}"><div class="claim-head"><div class="claim-label">{html.escape(_friendly(str(claim.get("field") or "Fact")))}</div>{_badge(state)}</div><div class="{value_class}">{value}</div><div class="source-row">{source}</div><details class="claim-details"><summary>View evidence record</summary><div class="evidence-grid">{details_html}</div></details></article>'''


def _section_icon(section: str) -> str:
    return {"identity": "building", "accounts": "chart", "leadership": "users", "workplaces": "globe", "website": "globe", "profiles": "users", "hiring": "file", "activity": "spark"}.get(section, "file")


def _section_freshness(section: str, claims: list[dict[str, Any]]) -> str:
    prefix = section + "."
    dates = [str(item.get("retrieved_at")) for item in claims if str(item.get("field", "")).startswith(prefix) and item.get("retrieved_at")]
    return max(dates)[:10] if dates else "Date not available"


def _section_record(row: dict[str, Any], section: str) -> dict[str, Any]:
    evidence = (row.get("profile") or {}).get("evidence") or {}
    key = "locations" if section == "workplaces" else section
    return evidence.get(key) or {}


def _section_note(row: dict[str, Any], section: str, state: str) -> str:
    record = _section_record(row, section)
    raw_status = str(record.get("status") or "")
    note = str(record.get("note") or "").replace("_", " ")
    if raw_status == "not_fetched":
        return "Not fetched in this run" if note in {"run deadline", "outbound request cap", "resume budget unknown"} else "Not fetched"
    if section == "website" and raw_status == "not_found":
        return "No candidate in identity snapshot" if "No website candidate" in str(record.get("note") or "") else "No verified candidate"
    if state == "ambiguous":
        return "Fetched, identity unresolved"
    if state == "blocked":
        return "Blocked by source policy or robots"
    if state == "failed":
        return "Source request failed"
    if state == "available":
        return "Verified evidence present"
    return "Not available"


def _claim_value(claims: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    return next((claim for claim in claims if claim.get("field") == field), None)


def _metric_html(claims: list[dict[str, Any]], field: str, label: str) -> str:
    claim = _claim_value(claims, field)
    value = claim.get("value") if claim else None
    display = _safe_text(value)
    if isinstance(value, (int, float)):
        display = f"{value:,.0f}".replace(",", " ")
    return f'<div class="metric"><span class="field-label">{html.escape(label)}</span><strong class="metric-value">{html.escape(display)}</strong><span class="metric-note">Derived from latest account record</span></div>' if value is not None else f'<div class="metric"><span class="field-label">{html.escape(label)}</span><strong class="metric-value">Not available</strong><span class="metric-note">No supported value returned</span></div>'


def _proof_links(claim_ids: list[str]) -> str:
    return " ".join(
        f'<a class="proof-link" href="#claim-{html.escape(str(claim_id), quote=True)}">{_icon("arrow-up-right")} proof</a>'
        for claim_id in claim_ids
    )


def _company_overview_html(claims: list[dict[str, Any]]) -> str:
    description = _claim_value(claims, "website.description")
    industry = _claim_value(claims, "identity.industry_label")
    claim_ids: list[str] = []
    if description and description.get("value") not in (None, ""):
        overview = f"The verified company website describes the business as: {_safe_text(description['value'])}."
        source_note = "Based on a verified first-party company description."
        claim_ids = [str(description["claim_id"])]
    elif industry and industry.get("value") not in (None, ""):
        overview = (
            f"The registry classifies this company in the {_safe_text(industry['value'])} industry. "
            "No more specific first-party description was verified in this snapshot."
        )
        source_note = "Registry-based overview; company description not verified."
        claim_ids = [str(industry["claim_id"])]
    else:
        overview = "No supported description of what this company does was verified in the supplied sources."
        source_note = "The overview is intentionally withheld rather than inferred."
    proof = _proof_links(claim_ids)
    proof_html = f'<p class="overview-proof">{html.escape(source_note)} {proof}</p>'
    return (
        '<section class="surface pad company-overview" aria-labelledby="company-overview-title">'
        '<div class="section-heading"><div><span class="kicker">Company overview</span>'
        '<h2 id="company-overview-title">What this company does</h2></div>'
        '<span class="freshness">Source-backed</span></div>'
        f'<p class="overview-copy">{html.escape(overview)}</p>{proof_html}</section>'
    )


def _profile_body(row: dict[str, Any], *, snapshots: dict[str, dict[str, Any]]) -> str:
    identity = row.get("identity") or {}
    org = str(row.get("organisation_number") or "")
    name = _safe_text(identity.get("name") or row.get("profile", {}).get("name") or org)
    claims = row.get("claims") or []
    sections = row.get("sections") or {}
    synthesis = row.get("synthesis") or {}
    sentences = synthesis.get("sentences") or []
    sentence_html = []
    for sentence in sentences:
        proof_links = _proof_links(sentence.get("claim_ids") or [])
        sentence_html.append(f'<p class="synthesis-sentence">{html.escape(_display_text(sentence.get("text")))}{proof_links}</p>')
    if not sentence_html and synthesis.get("text"):
        sentence_html.append(f'<p class="synthesis-sentence">{html.escape(_display_text(synthesis.get("text")))}</p>')
    unknowns = synthesis.get("unknowns") or []
    unknown_html = "".join(f'<li><span>{_icon("alert")}</span><span>{html.escape(_display_text(item))}</span></li>' for item in unknowns) or '<li><span>' + _icon("check") + '</span><span>No unknown section states were recorded.</span></li>'
    availability = []
    for section, detail in sections.items():
        state = str((detail or {}).get("state") or "not_available")
        note = _section_note(row, section, state)
        availability.append(f'<div class="availability-row"><span>{_icon(_section_icon(section))}</span><strong>{html.escape(_friendly(section))}</strong><span class="availability-state">{_badge(state)}<small class="state-note">{html.escape(note)}</small><small class="freshness">{_icon("calendar")} {_short_date(_section_freshness(section, claims))}</small></span></div>')
    claim_html = "".join(_claim_html(claim, snapshots) for claim in claims)
    municipality = identity.get("municipality") or row.get("profile", {}).get("municipality")
    latest_period = _claim_value(claims, "accounts.0.period")
    period_text = _safe_text(latest_period.get("value")) if latest_period else "Latest period not available"
    glance = "".join(f'<li>{_icon("check")} <span>{html.escape(_friendly(section))} <strong>{html.escape(_friendly(str((detail or {}).get("state") or "not_available")))}</strong><small class="proof-note">{html.escape(_section_note(row, section, str((detail or {}).get("state") or "not_available")))}</small></span></li>' for section, detail in list(sections.items())[:5])
    return f'''<div class="page"><p><a class="button secondary small" href="index.html">{_icon("arrow-right")} All companies</a></p><div class="hero"><section class="surface hero-main"><div class="kicker">Company record</div><div class="hero-meta">{_badge(str(row.get("status") or "not_available"))}<span class="meta-chip">{_icon("shield")} Evidence-first</span></div><h1>{html.escape(name)}</h1><p class="lead">Organisation number <strong>{html.escape(org)}</strong>{f' · {html.escape(_display_text(municipality))}' if municipality else ''}</p><div class="hero-actions"><a class="button" href="#research">{_icon("spark")} Ask this profile</a><a class="button secondary" href="#facts">{_icon("file")} Browse evidence</a></div></section><aside class="hero-side"><div class="kicker">At a glance</div><h2>What is verified now</h2><ul class="proof-list">{glance}</ul></aside></div><div class="metric-grid">{_metric_html(claims, "accounts.0.revenue", "Revenue")}{_metric_html(claims, "accounts.0.operating_result", "Operating result")}{_metric_html(claims, "accounts.0.assets", "Assets")}{_metric_html(claims, "accounts.0.equity", "Equity")}</div><div class="two-col"><div><section class="surface pad"><div class="section-heading"><div><span class="kicker">Summary</span><h2>Read the record</h2></div><span class="freshness">{_icon("calendar")} Account period: {html.escape(period_text)}</span></div><div>{''.join(sentence_html) or '<p class="muted">No source-linked synthesis is available.</p>'}</div></section><section id="facts"><div class="section-heading"><div><span class="kicker">Evidence</span><h2>Source-linked facts</h2></div><span class="freshness">{_icon("shield")} Each value has a trace</span></div><div class="surface pad claim-list">{claim_html or '<p class="empty">No supported facts were published.</p>'}</div></section></div><aside><section class="surface pad"><div class="section-heading"><div><span class="kicker">Coverage</span><h2>Availability</h2></div></div><div class="availability">{''.join(availability) or '<p class="muted">No section states recorded.</p>'}</div></section><section class="surface pad" style="margin-top:24px"><div class="section-heading"><div><span class="kicker">Open questions</span><h2>Unknowns</h2></div></div><ul class="unknown-list">{unknown_html}</ul></section></aside></div><section id="research" class="surface dark pad research"><div class="section-heading"><div><span class="kicker">Bounded research</span><h2>Ask about this company</h2><p class="muted" style="color:var(--paper-3)">Answers are limited to retained profile evidence. No unsupported fact is filled in.</p></div></div><form id="research-form" class="research-form" data-org="{html.escape(org, quote=True)}"><textarea name="question" rows="1" placeholder="Ask about accounts, roles, locations, or the website" aria-label="Research question"></textarea><button class="button gold" type="submit">{_icon("arrow-right")} Ask</button></form><div id="research-output" class="research-output" aria-live="polite"><p class="research-status">Ready for a source-linked question.</p></div></section></div>'''


def _layout(title: str, body: str, *, active: str = "", data: Any | None = None, script: str = "") -> str:
    nav = "".join(f'<a class="{"active" if active == key else ""}" href="{href}">{_icon(icon)} {label}</a>' for key, href, label, icon in (("companies", "index.html", "Companies", "building"), ("compare", "compare.html", "Compare", "chart"), ("changes", "changes.html", "Changes", "refresh")))
    embedded = f'<script id="signalpost-data" type="application/json">{_json_script(data)}</script>' if data is not None else ""
    inline_script = f"<script>{script}</script>" if script else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{html.escape(title)}</title><style>{CSS}</style></head><body><!-- THESIS: Signalpost turns public company evidence into a calm, navigable record. OWN-WORLD: warm paper, forest ink, marigold wayfinding, outline symbols, and source-first data panels. STORY: find a company, understand its verified sections, inspect freshness, then ask a bounded question. FIRST VIEWPORT: the task starts with searchable records and evidence status. FORM: evidence desk. FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->{_sprite()}<a class="skip-link" href="#main">Skip to content</a><header class="site-header"><div class="header-inner"><a class="brand" href="index.html"><span class="brand-mark">{_icon("spark")}</span><span>Signalpost</span></a><nav class="nav" aria-label="Primary">{nav}</nav></div></header><main id="main">{body}</main><footer class="footer"><strong>Signalpost</strong><span>Public evidence, clear provenance, bounded research.</span></footer>{embedded}{inline_script}</body></html>'''


def _index_body(rows: list[dict[str, Any]]) -> tuple[str, str]:
    cards = []
    for row in rows:
        org = str(row.get("organisation_number") or "")
        name = _safe_text((row.get("identity") or {}).get("name") or (row.get("profile") or {}).get("name") or org)
        status = str(row.get("status") or "not_available")
        cards.append(f'<a class="surface company-card" data-search="{html.escape((org + " " + name).casefold(), quote=True)}" data-status="{html.escape(status, quote=True)}" href="company-{html.escape(org, quote=True)}.html"><span class="card-top">{_badge(status)}{_icon("arrow-up-right")}</span><h2>{html.escape(name)}</h2><span class="org">{html.escape(org)}</span></a>')
    options = "".join(f'<option value="{html.escape(item["id"], quote=True)}">{html.escape(item["label"])}</option>' for item in COVERAGE_PROFILES)
    coverage_data = _json_script(COVERAGE_PROFILES)
    body = f'''<div class="page"><div class="page-head"><div><div class="kicker">Evidence desk</div><h1>Company profiles,<br><em>without the guesswork.</em></h1><p class="lead">Search public Norwegian company records, compare supported values, and follow every fact back to its source.</p></div><div class="surface dark pad"><span class="kicker">Snapshot</span><h2 style="color:var(--paper);margin-top:10px">{len(rows)}<br><span style="font-family:inherit;font-size:1rem;letter-spacing:0">records ready to inspect</span></h2></div></div><section class="coverage-panel" aria-labelledby="coverage-title"><div><div class="kicker">Explicit coverage</div><h2 id="coverage-title">Prioritize what matters now.</h2><p>The default profile stays unchanged. Choose a diagnostic profile when one category deserves the next request allocation.</p></div><div class="coverage-controls"><label for="coverage-profile">Coverage profile</label><select class="coverage-select" id="coverage-profile">{options}</select><div class="coverage-detail" id="coverage-detail" aria-live="polite"></div></div></section><div class="toolbar"><div class="control" style="flex:1"><label for="search">Find a company</label><div class="input-wrap">{_icon("search")}<input class="input" id="search" type="search" placeholder="Name or organisation number" autocomplete="off"></div></div><div class="control"><label for="status">Availability</label><select class="select" id="status"><option value="">All states</option><option value="available">Available</option><option value="not_available">Not available</option><option value="ambiguous">Needs review</option><option value="blocked">Blocked</option><option value="failed">Failed</option></select></div><button class="button secondary" id="clear" type="button">{_icon("refresh")} Reset</button></div><div class="count-line"><strong id="count">{len(rows)} companies</strong><span class="muted">Identity is anchored in the supplied registry snapshot.</span></div><div id="company-list" class="company-grid">{"".join(cards) or '<div class="empty">No profiles found.</div>'}</div></div>'''
    script = f"""
const search=document.querySelector('#search'), status=document.querySelector('#status'), count=document.querySelector('#count'), clear=document.querySelector('#clear');
function filter(){{const query=(search.value||'').toLowerCase().trim(), state=status.value;let visible=0;document.querySelectorAll('.company-card').forEach(card=>{{const show=(!query||card.dataset.search.includes(query))&&(!state||card.dataset.status===state);card.hidden=!show;if(show)visible+=1;}});count.textContent=visible+' compan'+(visible===1?'y':'ies');}}
search.addEventListener('input',filter);status.addEventListener('change',filter);clear.addEventListener('click',()=>{{search.value='';status.value='';filter();search.focus();}});
const coverageProfiles={coverage_data}, coverageSelect=document.querySelector('#coverage-profile'), coverageDetail=document.querySelector('#coverage-detail');
function renderCoverage(){{const profile=coverageProfiles.find(item=>item.id===coverageSelect.value)||coverageProfiles[0];const discovery=profile.id==='website-discovery-diagnostic'?' --discover-websites':'';const command='python scripts/run_batch.py --input <organisations.jsonl> --bulk <registry.csv-or-universe.jsonl> --profiles-output <run>/profiles.jsonl --output <run>/envelopes.jsonl --report <run>/report.json --run-id <run-id> --expected-count <count> --coverage-profile '+profile.id+discovery;coverageDetail.innerHTML='<strong>'+escapeCoverage(profile.label)+'</strong><p>'+escapeCoverage(profile.focus)+' '+escapeCoverage(profile.note)+'</p><code class="coverage-command">'+escapeCoverage(command)+'</code><div class="coverage-actions"><button type="button" class="button secondary small" id="copy-coverage">Copy command</button><span class="muted" id="coverage-copy-status">The viewer is a snapshot. Run the command to create a new allocation.</span></div>';document.querySelector('#copy-coverage').addEventListener('click',async()=>{{try{{await navigator.clipboard.writeText(command);document.querySelector('#coverage-copy-status').textContent='Command copied.';}}catch(_){{document.querySelector('#coverage-copy-status').textContent='Copy unavailable. Select the command above.';}}}});}}
function escapeCoverage(value){{return String(value??'').replace(/[&<>"']/g,char=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));}}
renderCoverage();
"""
    return body, script


def _research_script() -> str:
    return """
const form=document.querySelector('#research-form'), output=document.querySelector('#research-output');
if(form){form.addEventListener('submit',async(event)=>{event.preventDefault();const question=form.querySelector('textarea').value.trim();if(!question){output.innerHTML='<p class="research-status">Write a question first.</p>';return;}output.innerHTML='<p class="research-status">Checking retained evidence...</p>';try{const response=await fetch('/api/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({organisation_number:form.dataset.org,question})});const result=await response.json();if(!response.ok)throw new Error(result.error||'Research request failed');const facts=(result.facts||[]).map(fact=>`<article class="research-fact"><strong>${escapeHtml(fact.claim)}</strong><div>${escapeHtml(formatValue(fact.value))}</div><span class="freshness">${escapeHtml(fact.source_class||'Source record')} · ${escapeHtml((fact.retrieved_at||'Date not available').slice(0,10))}</span></article>`).join('');const unknown=(result.unsupported_or_uncertain||[]).map(item=>`<p class="research-status">${escapeHtml(item)}</p>`).join('');output.innerHTML=(facts||'<p class="research-status">No supported facts matched that question.</p>')+unknown;}catch(error){output.innerHTML='<p class="research-status">The research service is offline. Start it with <code>scripts/serve_viewer.py</code> to enable bounded questions.</p>';}})}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}
function formatValue(value){return typeof value==='object'&&value!==null?JSON.stringify(value):String(value??'Not available');}
"""


def _compare_page(rows: list[dict[str, Any]]) -> tuple[str, str]:
    options = "".join(f'<option value="{html.escape(str(row.get("organisation_number") or ""), quote=True)}">{html.escape(_safe_text((row.get("identity") or {}).get("name") or row.get("organisation_number")))}</option>' for row in rows)
    payload = [{"org": row.get("organisation_number"), "name": (row.get("identity") or {}).get("name") or (row.get("profile") or {}).get("name") or row.get("organisation_number"), "status": row.get("status"), "claims": row.get("claims") or []} for row in rows]
    body = f'''<div class="page"><div class="page-head"><div><div class="kicker">Comparison table</div><h1>Put three records<br><em>side by side.</em></h1><p class="lead">Compare equivalent fields without losing the source trail. Empty values stay visible as unknown.</p></div><div class="surface gold pad"><span class="kicker">View</span><p style="max-width:22ch;margin-bottom:0">A focused table, inspired by the practical clarity of Proff.no.</p></div></div><div class="surface compare-shell"><div class="toolbar" style="margin-top:0"><div class="control"><label for="company-1">Company one</label><select id="company-1" class="select company-select"><option value="">Choose a company</option>{options}</select></div><div class="control"><label for="company-2">Company two</label><select id="company-2" class="select company-select"><option value="">Choose a company</option>{options}</select></div><div class="control"><label for="company-3">Company three</label><select id="company-3" class="select company-select"><option value="">Choose a company</option>{options}</select></div></div><div id="comparison" class="compare-table-wrap" aria-live="polite"></div></div></div>'''
    script = f"""
const rows={_json_script(payload)};const selects=[...document.querySelectorAll('.company-select')];const params=new URLSearchParams(location.search);const requested=(params.get('org')||'').split(',').filter(Boolean);selects.forEach((select,index)=>{{if(requested[index])select.value=requested[index];select.addEventListener('change',render);}});
function esc(value){{return String(value??'').replace(/[&<>\"']/g,char=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[char]));}}
function valueOf(value){{return typeof value==='object'&&value!==null?JSON.stringify(value):String(value??'Not available');}}
function render(){{const chosen=selects.map(select=>rows.find(row=>String(row.org)===select.value)).filter(Boolean);const target=document.querySelector('#comparison');if(!chosen.length){{target.innerHTML='<div class="empty">Choose at least one company to begin.</div>';return;}}const byField=new Map();chosen.forEach(row=>(row.claims||[]).forEach(claim=>{{if(!byField.has(claim.field))byField.set(claim.field,[]);byField.get(claim.field).push({{org:row.org,claim}});}}));const preferred=['identity.name','identity.municipality','identity.legal_form','accounts.0.revenue','accounts.0.operating_result','accounts.0.annual_result','accounts.0.assets','accounts.0.equity','leadership.0.name','website.url'];const fields=[...preferred.filter(field=>byField.has(field)),...([...byField.keys()].filter(field=>!preferred.includes(field)).sort())];const heads=chosen.map(row=>`<th><a href="company-${{esc(row.org)}}.html">${{esc(row.name||row.org)}}</a><br><small>${{esc(row.status||'not_available')}}</small></th>`).join('');const rowsHtml=fields.map(field=>`<tr><td>${{esc(field.replaceAll('_',' ').replaceAll('.',' / '))}}</td>${{chosen.map(row=>{{const claim=(row.claims||[]).find(item=>item.field===field);return `<td class="compare-cell"><span class="compare-value">${{esc(valueOf(claim?.value))}}</span>${{claim?`<a class="compare-link" href="company-${{esc(row.org)}}.html#${{esc('claim-'+claim.claim_id)}}">${{esc('View evidence')}} ${{''}}</a>`:''}}</td>`}}).join('')}}</tr>`).join('');target.innerHTML=`<table class="compare-table"><thead><tr><th>Field</th>${{heads}}</tr></thead><tbody>${{rowsHtml}}</tbody></table>`;}}
render();
"""
    return body, script


def _changes_body(rows: list[dict[str, Any]]) -> str:
    changes = []
    for row in rows:
        for change in (row.get("refresh") or {}).get("changes") or []:
            org = str(row.get("organisation_number") or "")
            changes.append(f'<tr><td><a href="company-{html.escape(org, quote=True)}.html">{html.escape(org)}</a></td><td>{html.escape(_safe_text(change.get("claim_key")))}</td><td class="change-value">{html.escape(_safe_text(change.get("old")))}</td><td class="change-value">{html.escape(_safe_text(change.get("new")))}</td><td>{html.escape(_safe_text(change.get("materiality")))}</td></tr>')
    body = f'''<div class="page"><div class="page-head"><div><div class="kicker">Refresh trail</div><h1>What changed<br><em>since last time?</em></h1><p class="lead">Material differences stay attached to the company record so a refresh is easy to audit.</p></div><div class="surface dark pad"><span class="kicker">History</span><h2 style="color:var(--paper);margin-top:10px">{len(changes)}<br><span style="font-family:inherit;font-size:1rem;letter-spacing:0">material updates</span></h2></div></div><div class="changes-table-wrap"><table class="changes-table"><thead><tr><th>Organisation</th><th>Field</th><th>Previous</th><th>Current</th><th>Materiality</th></tr></thead><tbody>{''.join(changes) or '<tr><td colspan="5" class="empty">No material changes recorded for this snapshot.</td></tr>'}</tbody></table></div></div>'''
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
    ui_rows = _ui_value(rows)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    index_body, index_script = _index_body(ui_rows)
    (out / "index.html").write_text(_layout("Signalpost company profiles", index_body, active="companies", script=index_script), encoding="utf-8")
    for row in ui_rows:
        org = str(row.get("organisation_number") or "unknown")
        row_snapshots = {str(snapshot.get("snapshot_id")): snapshot for snapshot in row.get("snapshots") or []}
        profile_body = _profile_body(row, snapshots=row_snapshots).replace(
            "Answers are limited to retained profile evidence. No unsupported fact is filled in.",
            "Local natural-language topic matching only. No model, paid API, live crawl, or unsupported fact.",
        ).replace(
            '<div class="metric-grid">',
            _company_overview_html(row.get("claims") or []) + '<div class="metric-grid">',
            1,
        )
        (out / f"company-{re.sub(r'[^0-9A-Za-z_-]', '_', org)}.html").write_text(_layout(_safe_text((row.get("identity") or {}).get("name") or org), profile_body, active="companies", script=_research_script()), encoding="utf-8")
    compare_body, compare_script = _compare_page(ui_rows)
    (out / "compare.html").write_text(_layout("Compare company profiles", compare_body, active="compare", script=compare_script), encoding="utf-8")
    (out / "changes.html").write_text(_layout("Signalpost change history", _changes_body(ui_rows), active="changes"), encoding="utf-8")
    (out / "data.json").write_text(json.dumps(ui_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"profiles": len(ui_rows), "output": str(out), "files": len(list(out.iterdir()))}
