# Signalpost competition optimization loop

The objective is a reproducible, evidence-complete official run and then higher
coverage without weakening exact-company precision. Builderr scores 50 points
for recall/coverage, 30 for precision/evidence, 12 for synthesis and 8 for UX;
an official run qualifies at 65/100. The supplied company set is selected at
evaluation time and may grow, so local strategy measurements are development
evidence rather than a substitute for the hidden score.

The independent judge score is authoritative. A deterministic local scorer is only the fast feedback
signal between independent reviews. It must never replace the hidden evaluation.

## Loop

1. Measure terminal completion, exact-company precision, evidence validity, coverage, runtime, requests and cost on frozen development/validation artifacts.
2. Identify the largest score loss that can be changed without lowering exact-entity precision.
3. Make one bounded change and add the regression that would catch its most dangerous failure.
4. Rerun the same corpus. Keep the change only when it closes a hard gate or adds supported coverage without a precision/evidence regression.
5. Rerun a held-out validation corpus. A gain that disappears there is overfitting and is dropped.
6. Submit only a frozen exact revision; Builderr performs the official run and score.

## Controller behavior

- Reinforce: qualification gate closes or same-corpus score rises by at least two without regressions.
- Hold: improvement is under two points but supplies necessary infrastructure for the next measured gate.
- Drop: two iterations produce under one point total, coverage rises by lowering precision, or the extension
  corpus regresses materially.
- Roll back immediately: wrong-company publication, fabricated financial claim, silent entity drop,
  missing material evidence hash, prohibited request, or broken regression gate.

The first experiments should remain credential-free where possible: verified
company websites, same-host hiring/activity pages, and deterministic candidate
generation. Search APIs, licensed connectors and hosted models are optional
experiments and must be declared, permitted, budgeted and integrated with the
bounded runner before promotion.
