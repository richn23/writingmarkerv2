# AZE six-dimension construct model (working summary)

> Consolidated from the six uploaded dimension construct files
> (`dimension1taskachievement.md` … `dimension6contentquality.md`) plus
> Richard's "Evidence Metrics — Spec v1" note, both shared 18 Aug 2026.

## The six dimensions, as officially defined

1. **Task Achievement** — Word Count (no CEFR, level-locked, soft floor —
   explicitly not a proficiency claim) + Task Requirements (CEFR can-do per task
   type per level, not level-locked — can earn above the task's assigned level).
2. **Language Accuracy** — Grammatical Accuracy (EGP-level breakdown, by error
   type: missing/wrong-form/added/wrong-order, by severity: meaning survives or
   breaks) + Spelling (GSE-level breakdown, error type: sound/structural/
   boundary, severity: recognisable/unclear/unrecoverable) + Punctuation
   (adjacent only — no CEFR ladder possible, complexity tiers not A1–C2 labels).
3. **Language Range** — Vocabulary Range (GSE breadth spanned, replaces TTR/
   MTLD on purpose) + Sentence Complexity, redefined as **Grammar Range** (EGP
   structures attempted, correct or not — breadth, not accuracy).
4. **Organisation** — Paragraph Structure (task-type structural expectation,
   e.g. an email needs greeting/body/sign-off) + Transition Words (Range:
   possible if an EGP/GSE-style connector-to-level resource exists, else
   adjacent-only; Accuracy: judged directly, no level mapping needed) +
   Coherence (logical flow, adjacent only, inherently a judgment call).
5. **Style and Register** — Register (single match/mismatch vs the task's
   expected tone, B2+ floor — CEFR names register-matching as a skill only from
   B2 up).
6. **Content Quality** — Content and Ideas (depth/development of ideas, B1+
   floor, softer/qualitative CEFR alignment, not a clean data list like GSE/EGP).

Every metric doc states its CEFR-sourcing rigor (Yes / Possible / No-adjacent-
only) and a "not to be confused with" section pointing at neighbouring metrics.

## Key structural insight

Grammar Range (Dimension 3 — structures attempted, correct or not) and Grammar
Accuracy (Dimension 2 — were the attempted structures correct) are two
different dimensions but **both depend on the same missing engine piece**: a
detector that finds attempted EGP structures whether or not they're well-
formed. LENS's current detector only finds correctly-formed ones. Building
that one detector unblocks both dimensions at once.

Other notes:

- Spelling (Dimension 2) is already very close to what gse-vercel-app built —
  its error types (sound-based / structural / boundary) map closely to the
  live categories in `spelling_score.py` (phonetic / minor_slip / boundary),
  though the spec doesn't separately name `wrong_word` or the full severity
  scale already built. Worth a side-by-side reconciliation, not a rebuild.
- Punctuation is officially "adjacent only, no CEFR ladder possible" — that's
  cover for the known weakness (only 4 advanced constructs currently checked).
  The fix is broader complexity-tier coverage, not a CEFR ladder.
- Possible unconfirmed lead: Transition Words Range asks whether an EGP/GSE-
  style connector-to-level mapping resource exists. LENS's detection layer
  (`mapping/functions.json`, 51 marker-signalled relations) might already be
  this, or close to it — worth checking before assuming nothing exists.
- Dimensions 1, 4's Paragraph Structure, 5, and 6 stay properly out of scope
  for the deterministic engine — task-specific or inherently qualitative/
  AI-judged, consistent with LENS's task-agnostic principle.

## "Evidence Metrics — Spec v1" — review

Proposal: cheap, deterministic, code-only text stats (sentence count, avg
sentence length, length spread, avg word length, TTR-style diversity ratio,
paragraph count, connector keyword count, duplicate/near-duplicate sentence %,
sentence-starter repetition) in a separate `evidence` block — not scored, not
CEFR-labelled, not blended into the composite. Same treatment as Word Count.

**Endorsed as architecture.** The evidence-vs-verdict split is exactly the
pattern already proven out in LENS and gse-vercel-app. The duplicate-sentence
and sentence-starter-repetition metrics are genuinely novel — nothing already
built catches within-a-valid-response repetition.

**Two caveats before this ships:**

1. TTR-style vocabulary diversity is actively backwards as a signal. Measured
   on 201 real verified learner scripts: TTR ran from 0.91 at Pre-A1 down to
   0.59 at B2, because longer texts naturally repeat function words. Recommend
   dropping it, or shipping with that specific caveat inline.
2. Average word length carries the same length-confound risk GSE Profiler
   already hit with raw word count (r=+0.65 with MOE band, but that's
   productivity, not quality). Fine as raw evidence, flag the confound
   explicitly.

**One correction, not just a caveat:** the spec frames sentence count/length as
"exactly the raw signal Sentence Complexity would need once un-stubbed." But
the six-dimension docs redefine Sentence Complexity as Grammar Range — EGP
structures attempted, not sentence length. Length-based signal isn't an input
to the real fix under the new definition; EGP structure detection is. Sentence
length is still a fine, independent QA signal on its own merits.

**Independence note:** this whole spec needs zero GSE/EGP framework work and no
rubric decisions — plain tokenization and counting. It could ship well ahead of
the grammar-detection work everything else is blocked on.
