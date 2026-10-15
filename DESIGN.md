# Signalpost viewer design

## Direction

Signalpost is an evidence desk for Norwegian company records. The interface
should feel like a careful public-interest publication rather than a generic
dashboard: warm paper for the reading surface, deep forest for verified states,
and marigold for wayfinding and attention.

## Visual system

- **Palette:** paper `#fbf7f0`, secondary paper `#f4ecdd`, ink `#191610`, forest
  `#254e2b`, deep forest `#152d1a`, marigold `#eda42e`, and restrained semantic
  red for failures.
- **Type:** Instrument Sans or a system sans for controls and metadata; Fraunces
  or a strong serif fallback for company and page headings.
- **Symbols:** inline outline SVGs with one consistent stroke vocabulary for
  evidence, calendar, source, accounts, roles, website, activity, and state.
- **Surfaces:** warm paper, thin warm borders, modest rounded corners, and soft
  depth. No gradients, glass decoration, or decorative metric rings.
- **Composition:** searchable company directory, source-aware profile hero,
  finance headline, availability rail, claim-level evidence records, aligned
  comparison table, refresh history, and bounded profile research.

## Interaction rules

- Every displayed fact has a state, retrieval date where available, and a path
  to source evidence.
- Unknown is visible and never presented as zero.
- Comparison aligns fields across companies and links back to each claim.
- Profile questions use the bounded local endpoint and retained evidence only.
- Static builds remain usable without the research endpoint.
- Keyboard focus, reduced motion, narrow screens, and empty states are first
  class states.

## Reference influence

The palette and editorial warmth follow the supplied Jatin college project.
The information model takes the practical comparison discipline of Proff.no,
the financial headline and derived-value labeling pattern of
bedriftssok.webagent.no, the per-section freshness pattern of 21st.ai, and the
source/retrieval proximity associated with OpenCorporates and Companies House.
The viewer copies the principles, not their visual density or unverified data.
