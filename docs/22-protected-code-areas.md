# Protected code areas

A living list, not a dated report — add to it when a folder earns protected
status; don't let it go stale the way a point-in-time doc would. Until now
this rule only lived inline in dated reports (docs/06, docs/19, docs/20) and
in session memory, which meant it had no single place a future session could
check without already knowing which report to search.

**Protected** means: edits require explicit approval before being made, the
same forcing-function weight as a human code reviewer on a sensitive path.
Not a technical lock — nothing stops an edit — a discipline to apply anyway.

## What's protected, and why

- **`api/_engine/`** — the scoring engine itself. Calibrated against a fixed
  regression baseline (`tests/test_regression.py`, canonical hash over
  `Batch_1_Tuning_100.csv`); an uncontrolled edit here can silently shift
  every score the app has ever produced.
- **`api/_intent/`** — the LLM intent/interpretation layer. Two hard
  constraints (only flagged tokens are ever sent; every proposal must pass
  the form test) are easy to violate by a well-meaning "helpful" widening,
  and a violation there doesn't fail loudly — it just quietly launders a
  vocabulary upgrade through as a spelling fix.
- **`api/_grammar/`** — added 24 Aug 2026. A verified port of LENS's grammar
  structure detector (docs/21): 30 detector families resolved against 1,222
  EGP reference rows, checked against 92 live-captured fixture examples with
  0 unexplained mismatches. It has already diverged deliberately from its
  own upstream source once (a confirmed regex bug in LENS's shipped code,
  docs/21) — exactly the kind of calibrated, already-reconciled logic where
  a casual later edit could reintroduce drift that shows up only as a wrong
  level on someone's script, not as an error.

## What isn't

`api/score.py` and `app/page.tsx` are the two files everything else routes
through, and are expected to change often as new modules get wired in and
new screens get built. Freely editable — that's the point of keeping the
calibrated logic elsewhere.

## Adding an entry

When a new module reaches the same bar — calibrated against real reference
data, verified, and not merely "written" — add it here with the same three
things this doc gives `_engine`/`_intent`/`_grammar`: what it is, what it's
calibrated against, and the concrete failure mode an uncontrolled edit risks.
