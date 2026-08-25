# Grammar construct — full spec, start to finish, 24 Aug 2026
Consolidates everything decided across docs 09, 11, 15, the two LENS
fact-finding responses, docs 19/20/20b/20c, and the external CAF (
Complexity/Accuracy/Fluency) advice into one reference spec. This is the
authoritative shape of Grammar as a construct — supersedes nothing, just
brings it together in one place. Where something is still open or
provisional, it's marked as such rather than presented as settled.
---
## 1. Framing: three constructs, not one
Grammar splits into three independently-scoped pieces, matching the
established CAF framework from second-language-acquisition research
(Complexity, Accuracy, Fluency — Fluency isn't applicable to written
assessment here, so effectively C+A, plus a third axis this project adds
explicitly):
| Our section | CAF-equivalent | Question it answers |
|---|---|---|
| **Grammar detected** | Repertoire (a refinement beyond bare CAF) | What structures did the learner successfully demonstrate, and at what CEFR level? |
| **Grammar Metrics** | Complexity | How structurally elaborate is the language they produced? |
| **Grammar accuracy** | Accuracy | How correctly did they use the grammar they attempted? |
External validation (24 Aug advice): repertoire/demonstrated-structures is
independently flagged as "potentially more valuable... than adding
another five parser statistics" — i.e. Grammar detected is likely the
single most pedagogically load-bearing of the three, not just the first
one that happened to get built.
This mirrors the same interpretation/scoring separation already
established for Vocabulary and Spelling: all three Grammar sections read
from the same **approved interpretation text** (freshest of first-pass or
marker-adjusted), never raw as-written text. No Grammar-specific
correction logic exists or is planned — if underlying text doesn't parse
because of an uncorrected error, the affected structure simply isn't
detected, same "absence isn't evidence of absence" honesty used
throughout this project.
---
## 2. Grammar detected (Repertoire) — built
### Source
Ported from LENS (`language-awareness-pipeline`), specifically
`grammarDetect.ts`, `egpFamilies.ts`, `taxonomy.ts`, and the EGP reference
data (`grammar_profile.json`, 1,222 rows, full A1–C2 coverage).
### Coverage
45 total structure families. **30 detectable** (2 explicitly partial —
coverage gaps stated, not silently claimed as full), **16 deferred**
(each with LENS's own stated reason — imperatives, gerunds/infinitives,
phrasal verbs, inversion, etc. — false positives judged worse than false
negatives, so these are declared out of scope rather than guessed at).
### Architecture — two-pass, per docs 19/LENS response
- **Pass 1 (evidence/matching):** token-pattern matching against the
  text, producing `{explorer_id, family, matched span, context}` tuples.
  No level or EGP row attached at this stage.
- **Pass 2 (leveling):** resolves each Pass 1 tuple against the EGP
  reference to attach a level and specific row. This is where the
  now-fixed FORM-only gate bug lived (see below).
### The gate fix (built, per doc 19 Task 1)
**Bug, confirmed by LENS via direct code trace:** the leveling gate
discarded every `USE:`/`FORM/USE:`-guideworded EGP row whenever a shared
family had any plain `FORM:` row — silently breaking `wish`/`if only`
(mislevelled A1 instead of B1/B2), `conditionals-unreal` (worse — didn't
even land on a conditional-shaped row), and likely 4 of 8 `modals-past`
sub-families. **Fix:** guideword-aware selection replacing the blanket
per-family exclusion, applied once at the resolver level — fixes all
affected families under one change, not per-family patches. Also fixed:
the wish-token match-time bug (never checked complement tense).
### Confidence signal
`condition_unverified` (set when the resolver had to fall back to a
non-form-only row) is surfaced explicitly per detected structure in Pass
2's output, not just used to silently suppress can-do text — shown in the
UI as a visible flag (e.g. "can-do unverified"), consistently across
every row where it's true.
### Framework decision
EGP confirmed as the right base (LENS's own check against
`eaquals_inventory.json`: EAQUALS is coarser, not finer, and couldn't
represent compound-case distinctions even in principle; both frameworks
independently agree on the corrected levels). No framework swap needed —
this was a resolver bug, not a data/framework gap.
### UI
Two states per detected family: **Detected** (family, EGP level, matched
example span, confidence flag if `condition_unverified`) and **Deferred**
(explicitly listed as out-of-scope, never presented as a false absence).
Labelled clearly as Range/Repertoire, not accuracy or complexity — a
structure absent from "detected" says nothing about whether the writer
can produce it, only that it wasn't found in this sample.
### Known still-open item, separate from the above
The `'d`-contraction ambiguity bug ("they'd mentioned" resolving to
"would" instead of "had," producing "would mentioned") — flagged doc 16,
**not yet investigated or fixed**, deliberately not folded into the gate
fix since it's a different bug (match-time ambiguity, not the leveling
gate). Status: open, no owner assigned yet.
---
## 3. Grammar Metrics (Complexity) — partially built, partially spec'd, not yet built
### Two tiers, by what's needed to compute them
**Tier 1 — available now, no new parsing infrastructure (doc 19):**
built from Pass 1's structure profile plus existing sentence/word
tokenization already in the app:
- Mean sentence length, sentence count
- Subordination density (proxy: subordinating/concessive/relative family
  hits ÷ sentences)
- Coordination density (proxy: coordination hits ÷ sentences)
- Structure diversity (distinct families detected out of 30)
- Passive voice frequency, modal density
Labelled explicitly as descriptive counts/ratios, not a CEFR-validated
complexity score.
**Tier 2 — needs a real clause-boundary parser (docs 20/20b/20c),
scoped but not yet built:**
- Clauses per sentence, mean clause length, mean T-unit length, dependent
  clauses per clause, complex T-unit ratio
**Tier 3 — new addition per the CAF advice, not yet scoped in detail:**
phrasal/nominal complexity — complex nominals per clause, noun-phrase
elaboration, coordinate phrases per clause. The advice is explicit that
this is what actually distinguishes B2–C2 writing, not additional
subordination — "higher proficiency increasingly involves dense,
efficient phrasal structures," not simply more subordinate clauses.
Current Tier 1/2 metric sets have **no phrasal-complexity measure at
all** — this is a real gap, not a nice-to-have. Likely computable from
the same dependency parse Tier 2 already requires (complex nominals are
a tree-shape question, same infrastructure), so probably a targeted
addition to the Tier 2 build rather than a separate new capability —
needs confirming, not assumed.
### Why Tier 2/3 need a trigger, not a blanket rollout — two independent reasons
1. **Technical (doc 20):** dependency parsers are trained on well-formed
   text; our input is learner writing, often containing exactly the
   errors that make parsing least reliable. A parser can silently
   misjudge structure on the sentences where it's least certain.
2. **Validity (24 Aug advice, newly added):** even a perfectly accurate
   parser wouldn't make Tier 2/3 metrics meaningful at every level.
   Below B1, syntactic/phrasal complexity isn't the informative signal at
   all — accuracy and basic structural control are. The advice's own
   per-level relevance table:
   | Level | What's actually informative |
   |---|---|
   | A1–A2 | Errors/100 words, error-free sentence %, error type distribution, successful use of basic structures |
   | B1 | Clauses/T-unit, dependent clauses/clause, error-free T-units, mean T-unit length |
   | B2–C2 | Complex nominals/clause, noun-phrase elaboration, coordinate phrases, mean clause length |
   Both reasons should be stated in the below-threshold UI message (doc
   20 Task 4), not just the technical one — they point the same
   direction but they're different claims, and citing only reliability
   understates the case for gating.
### Trigger mechanism (spec'd, doc 20/20b/20c, not yet built)
- Reuses Vocabulary's existing confident lexical level as the trigger
  signal — no new gating infrastructure invented.
- Ships with a provisional threshold (B1, explicitly labelled
  provisional) — the real threshold is set by calibration testing, not
  guessed in advance.
- Below threshold: explicit stated-reason message (both technical and
  validity reasons), never a silent hide — matches the three-state
  honesty pattern already used on Translate.
### Calibration protocol (spec'd, doc 20b/20c, not yet run)
- Data collected from every scored sample during the testing period, not
  a curated set.
- Two independent checks per sample: automatic internal-plausibility
  bounds (Check 1), and manual clause-boundary agreement on a spot-check
  subset weighted toward uncertain levels (Check 2). A level only counts
  as trustworthy "data" if both checks pass; disagreement between checks
  defaults to "noise" rather than averaging to borderline.
- Required output table: CEFR level × samples × clause-count agreement ×
  boundary agreement × major parse failures — clause-count and boundary
  agreement kept as separate columns, since a parser can get the count
  right while attaching a clause to the wrong parent.
- Metric-level error required in addition to segmentation agreement — the
  same segmentation mistake can barely move a metric or badly distort it
  depending on context, so segmentation agreement alone doesn't answer
  "can we trust the displayed number."
- Threshold is **proposed by Claude Code from the observed error
  distribution**, with stated reasoning — not asserted by eye ("B1 looks
  okay" is explicitly disallowed as a conclusion).
- Operational definitions (clause, dependent clause, T-unit — exact
  tree-based rules covering coordination, subordination, relatives,
  complements, infinitivals, fragments, run-ons) must be documented as
  part of the module itself, written before implementation, not inferred
  from library defaults after the fact.
---
## 4. Grammar accuracy — not built, design exists but unapproved
### What exists today
One narrow deterministic case, on the LENS side only, not wired into
this project: pluralised uncountables ("a lot of breads") —
`production.ts`. Not accuracy detection for grammar structures generally.
### What's designed but not built
LENS's `STUDENT_PRODUCTION_ANALYSER_DESIGN.md` (v2.1, dated 4 Aug 2026,
"awaiting Richard's approval") already defines the general category
("grammatical form error" — structure reached for, form incomplete) and
a four-state classification shape (not engaged / attempted-and-landed /
attempted-not-landed / can't tell) generic enough to extend beyond
vocabulary to grammar structures. Not reviewed or approved on our side
yet.
### Why this is architecturally harder than Grammar detected or Metrics
The correct-structure detector's rules are deliberately conservative
(false positives judged worse than false negatives). Detecting
"attempted but wrong" needs tolerating exactly the ambiguity those rules
were built to avoid — LENS's own recommendation is a **separate module**
reusing the reference layer, not extending the detector in place.
Deterministic checks look tractable for some families (subject-verb
agreement is the standout candidate — the detector's own
`isThirdS`/`isBareVerb` functions already do most of the anchoring work
needed to check for a mismatch instead of a match). Other families have
no existing "correct" detector to anchor against at all (the 16 deferred
families) — for those, this is a materially harder, open-ended problem.
### External validation of priority (24 Aug advice, new)
Errors/100 words, error-free T-unit %, and error-type distribution are
flagged as "very established" and most meaningful **specifically at
A1–A2** — the levels where this section currently has nothing. This is a
signal, not yet a decision: Grammar accuracy may deserve earlier priority
than "not built yet, unscheduled" currently implies, once Grammar
detected + Metrics ship. Not decided — flagging for your call.
### Current placeholder behaviour (built)
Honest "not built yet," matching the pattern used elsewhere on this
project for not-built constructs — no reference to LENS's one narrow
built case, since that's not wired to anything here and referencing it
would imply more than exists.
---
## 5. Data flow, end to end
1. Sample submitted → routes to Translate (interpretation), not
   Dimensions, same as Vocabulary/Spelling.
2. Vocabulary/Spelling's correction pipeline produces the approved
   interpretation text (first-pass or marker-adjusted, whichever is
   freshest).
3. Grammar detected's Pass 1 runs token-pattern matching against that
   approved text (not raw as-written).
4. Pass 2 resolves each match against the EGP reference (gate-fixed),
   attaching level + confidence flag.
5. Grammar Metrics Tier 1 aggregates directly from Pass 1's output plus
   existing sentence stats — no additional parsing.
6. If/when Tier 2/3 ship: the same approved text is parsed by the
   dependency parser, gated by the calibrated trigger (Vocabulary's
   confident level signal), displayed only where classified as "data,"
   otherwise shown with an explicit two-reason not-shown message.
7. Grammar accuracy: not built. No data flow exists yet.
8. Export JSON already generalizes to whatever's in the response object —
   confirmed no separate work needed each time a new field is added.
---
## 6. Protected/architecture status
- `api/_grammar/` (the ported detector + gate-fixed resolver): treated as
  protected, same tier as `_engine`/`_intent` — calibrated, verified
  logic (92/92 fixtures, further targeted fixtures per doc 19 Task 3b).
  Recommendation confirmed, not just proposed.
- Any new dependency-parser module (Tier 2/3): explicitly **not**
  proposed for the same protection tier — general-purpose parsing
  infrastructure, not project-specific calibrated logic. Open question
  for Claude Code to confirm during build, not settled here.
- `app/page.tsx`: UI layer, freely editable throughout, per existing
  rules.
---
## 7. Status summary — what's actually done vs. spec'd vs. open
| Piece | Status |
|---|---|
| Grammar detected — port, gate fix, two-pass split | Built and verified |
| Grammar detected — `'d` contraction bug | Open, not investigated |
| Grammar Metrics Tier 1 (proxy metrics) | Spec'd (doc 19), build pending your confirmation of metric set |
| Grammar Metrics Tier 2 (clause parser) | Fully spec'd (docs 20/20b/20c), not built |
| Grammar Metrics Tier 3 (phrasal/nominal) | Identified as a gap today, not yet scoped in detail |
| Grammar Metrics calibration/trigger | Fully spec'd, not run |
| Grammar accuracy | Design exists (LENS side, unapproved), nothing built, priority signal newly surfaced |
