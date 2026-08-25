# Grammar leveling gate fix, two-pass split, Grammar Metrics — 24 Aug 2026

Report for the "Build brief for Claude Code — grammar leveling gate fix,
two-pass split, Grammar Metrics section, 24 Aug 2026." Tasks 1–3 (including
3b) are done and verified. Task 3c is flagged, not started. Task 4 is
blocked on confirming the metric set, per the brief's own explicit gate.

## A note on the brief's own references

The brief cites "the LENS fact-finding response (24 Aug 2026, `docs/22` or
wherever it lands in your numbering)" and "Doc 16 (24 Aug)" for the `'d`
contraction investigation. Neither exists in this project's `docs/` — the
numbering here runs 01–22 with no gap at 16, and 22 is
`protected-code-areas.md`, unrelated. The advisory session that wrote this
brief was evidently working from a different context than this repo's
actual state. Given that, and given how the earlier `hasPast` investigation
went (docs/21), I independently re-derived and verified every factual claim
in Task 1 against the actual code and the live LENS detector before acting
on it, rather than trusting the diagnosis at face value. It held up — see
below — but it's worth flagging that the brief's own citations weren't
reliable.

## Task 1: root cause, independently confirmed

Reproduced the bug directly before touching anything. Counted the excluded
rows per family:

| Family | Total rows | Form-only (eligible) | Excluded |
|---|---|---|---|
| `past_simple` (wish) | 24 | 14 | 10 |
| `past_perfect_simple` (wish/if-only) | 20 | 8 | 12 |
| `conditional` | 27 | 4 | 23 |

All three match the brief's figures exactly. `resolveStructure()`'s
FORM-only gate (`_is_form_only_row`, `api/_grammar/detect.py`) excluded
every `USE:`/`FORM/USE:` row from a family's candidate pool whenever the
family had any pure `FORM:` row — discarding the wish/regret row, both
if-only rows, and every second/third-conditional row outright. A genuine
second conditional ("If I had studied, I would have passed the exam.") was
resolving to a2 `FORM: 'IF' + PRESENT SIMPLE` because nothing more specific
was left to compete.

### A finding beyond the brief's diagnosis: the "if only" branch was dead code

The brief states "if only" already routes correctly to `wish`/
`past_perfect_simple`, and only the `wish`/`wishes`/`wished` branch has the
match-time family-selection bug. Testing found otherwise: **the `wish`
family never fired at all for "if only ..." sentences**, in either the
Python port or, confirmed by running the actual live LENS TS detector
against the same sentences, LENS itself.

Root cause: `"only"` is in LENS's own `SKIP` set (word list a matcher
looks past when scanning for "the next token"), so `nextIdx()` always skips
over it — meaning the branch's guard, `t == "if" and n == "only"`, could
never be true, since `n` is computed via that same SKIP-filtering. Both
"If only I had listened to my father!" and "If only she had not changed her
mind." were landing purely on the generic "had + past participle" detector
(`explorer_id: "past-perfect"`), never on `wish` at all — confirmed
identical in a fresh `npx tsx` run against the real, unmodified
`grammarDetect.ts`. This is upstream, not a porting artifact.

This mattered directly: without fixing it, `wish` could never fire for
either of Task 3b's two "if only" fixtures regardless of how well the
FORM-only gate itself got fixed, since those sentences would never reach
the resolver under that family at all.

## The fix

Three separate changes, all in `api/_grammar/detect.py`:

**1. Match-time fixes** — `wish`/`wishes`/`wished` now checks the
complement's own tense (via the same `after_subject`/`is_pp` idiom used
elsewhere in the file) to choose `past_simple` vs `past_perfect_simple`,
instead of always picking `past_simple`. The `if` + `only` branch checks the
literal next token directly, bypassing `nextIdx`'s SKIP filtering (since
"if only" is a fixed collocation, not a case where an intervening adverb
should be skipped past), and computes its own negation look-ahead (fire()'s
default 3-token window never reaches a `not` sitting after the subject and
auxiliary). Both branches canonicalize `marker="wish"`/`marker="if"` and set
`past=True`, since the EGP can-do prose always quotes the dictionary form
and these constructions are inherently past-oriented.

**2. The resolver gate ("Fix 6")** — Scoped, not universal. A small,
explicit set (`_UNGATE_FAMILIES`: `past_simple`, `past_perfect_simple`,
`conditional`, and all 8 modal names) drops the blanket form-only pool
restriction; every other family keeps its exact prior gating. Within the
ungated families, the existing guideword-only generic scoring
(AFFIRMATIVE/NEGATIVE/QUESTION/PAST, marker, variant, quoted-word) now
applies uniformly to every row rather than only form-only ones — unchanged
formula, wider pool. This alone was sufficient for the `may`/`might`
modals-past sub-families, whose `FORM/USE: PAST AFFIRMATIVE`-style rows
already declare PAST/AFFIRMATIVE in their own guideword.

For rows that name their construction only in can-do prose, never in the
guideword (`USE: REGRET`; the shared "AFTER 'IF ONLY' AND 'WISH'" row), an
additional, opt-in mechanism searches can-do prose for the one already-known
trigger word from match time — never a generic vocabulary scan, exactly one
specific word the detector already chose. Where a can-do sentence covers
more than one construction/polarity in one breath (the shared row covers
both "if only" and "wish"), a polarity check is scoped to the clause that
actually names the marker, not the whole sentence, so "if only" and "wish"
can't bleed into each other's affirmative/negative claims.

**3. Scoping this opt-in mechanism** — Two collateral-damage findings
during verification forced the mechanism to be *narrower* than a first
implementation:

- Applying the prose-marker search to *every* `ctx.marker` (not just
  wish/if-only's) reintroduced the exact historical bug guideword-only
  scoring was built to prevent: common auxiliaries like `"are"`/`"is"`/
  `"could"` matched unrelated USE-row prose as ordinary grammatical glue
  (`"They are meeting tomorrow."` spuriously resolved through `"USE:
  TEMPORARY REPEATED ACTIONS"` via `marker="are"` appearing incidentally in
  its can-do text). Fixed by making the mechanism opt-in per call site — a
  new `FireCtx.thematic_marker` flag, set only by the wish/if-only
  branches — rather than firing for any marker.
- Applying the pool-ungating to *every* family (not just the four named
  above) surfaced an unrelated, pre-existing scoring quirk in
  `question-tags`: those rows are penalized whenever `ctx.question` is
  false and their own guideword happens to contain the word "QUESTION" —
  which is *every* tag row, since the family names itself "Question Tags."
  That penalty was previously masked only because the form-only gate
  excluded the specific row it hurt most. This is a real, separate bug —
  not this brief's to fix. Flagged here rather than silently patched
  alongside Fix 6; scoping `_UNGATE_FAMILIES` down to exactly the brief's
  diagnosed families avoided touching it at all.

Both were caught only by re-running the full 92-example fixture set after
each change, not by hand-tracing — the scoring formula has enough
interacting terms that hand-derived predictions were wrong twice before
landing on the scoped, empirically-verified design above.

## Task 3b: fixture results, individually

All from `tests/test_grammar_regression.py` (new — see below), run against
the live port:

| Case | Expected | Got | Result |
|---|---|---|---|
| "I wish that you were here, cycling with us." → `wish`/`past_simple` | B1 | B1 | **PASS** |
| "If only I had listened to my father!" → `wish`/`past_perfect_simple` | B2 | B2 | **PASS** |
| "If only she had not changed her mind." → `wish`/`past_perfect_simple` | C2 | C2 | **PASS** |
| "If I had studied, I would have passed the exam." → `conditionals-unreal`, not A2 | B1 (not A2) | B1 | **PASS** |
| "She might have missed the train." → `modals-past`/`might` | B1 | B1 | **PASS** |
| "She may have thought about it." → `modals-past`/`may` | B2 | B2 | **PASS** |

**`can`/`shall` (LENS's flagged-but-unconfirmed suspicion), resolved:**
`might` and `may` were genuinely affected by the gate bug and are now fixed.
`can` and `shall` are **not** — EGP has no dedicated past-modal row for
either at all (confirmed by listing every row in both families' reference
data). "You can have finished by now." and "They shall have arrived by
then." both fall back to the best generic row available (a1/a2
respectively) both before and after this fix. This is a genuine gap in the
underlying Cambridge EGP reference data, not a resolver bug — nothing in
this fix (or a further one scoped the same way) can close it, since there's
no correct row to select. Recorded as passing "data-gap" cases in the
regression file rather than silently omitted.

## Full regression: 92/92, 0 unexplained

Re-ran the original 92-example fixture set (docs/21) against the fixed
port. Six examples now deliberately diverge from live LENS — three are the
already-decided `hasPast` bug (docs/21), three are new, from this fix, all
individually confirmed as the *intended* result of fixing the FORM-only
gate rather than an unintended side effect:

- "I wish I had more time." — a1 → b1 (now resolves via the wish/regret row)
- "If only I had studied harder." — `wish` now fires at all (b2); LENS
  never fires it, per the dead-code finding above
- "If I had more time, I would travel." — a2 → b1 (conditional fix)

(A fourth, "If I had known, I would have helped.", carries both the
pre-existing `hasPast` divergence and this fix's conditional divergence at
once, still one example.) Every other one of the 92 is byte-identical to
its docs/21 result — confirming the scoped `_UNGATE_FAMILIES` design didn't
touch anything outside its intended four families.

## New durable regression fixtures

`tests/test_grammar_regression.py` — this project had no `tests/` folder;
created one. Dependency-free (`python3 tests/test_grammar_regression.py`,
no pytest), matching `api/score.py`'s own no-requirements-file convention.
Covers all six Task 3b cases plus the two `can`/`shall` data-gap cases,
9/9 passing. Exists specifically because the original 92-example set
(docs/21) didn't include the triggering sentences for this bug and so
passed 92/92 while it shipped undetected — these fixtures close that gap
going forward.

## Task 2: two-pass split

`detect_grammar_structures()` now genuinely separates evidence from
levelling:

- **Pass 1** (`add()`, inside `detect_grammar_structures`): token-matching
  only. Collects `{explorer_id, family, matched, matched_spans, count}` per
  hit, carrying the `FireCtx` the resolver will need under a private `_ctx`
  key. No EGP row or level attached at this stage.
- **Pass 2** (new module-level `_level_evidence(raw_hits)`): maps Pass 1's
  raw hits through the (now gate-fixed) resolver independently per hit,
  attaching `level`/`egp_structure_id`/`guideword`/`can_do`/
  `selection_basis`/`condition_unverified`. Genuinely a separate function,
  not just a second loop inline — callable and testable on its own, one
  family's resolve failing or changing doesn't touch another's.

`detect_grammar_structures()` stays the single external entry point (calls
Pass 1 then Pass 2 then sorts/returns), so `api/score.py`'s existing call
site needed no changes at all.

## Task 3: `condition_unverified` surfaced explicitly

Already correct in the existing UI (built for the earlier 24 Aug brief) —
checked, not assumed. `app/page.tsx`'s `GrammarDetectedSection` renders the
`"can-do unverified"` tag inside the `.map()` over every `f.instances`
entry, unconditionally on `inst.condition_unverified` — already applied
consistently to every row where the flag is true, not a subset. No UI
change was needed for this task. The flag itself now reads `true` more
often post-Fix-6 (any winning row that isn't a pure `FORM:` row, or whose
can-do states an unverifiable condition), which is the intended,
correctly-surfaced consequence of widening the pool to admit real
USE/FORM-USE rows as winners — the tag is doing more real work than before,
not more false-positive work.

Verified end-to-end through the real `score.py` `detail()` pipeline (not
just the raw detector) against a multi-construction sample — all four
Fix-6-affected families showed correct levels and `condition_unverified`
flags together, no errors.

## `_engine`/`_intent` confirmed untouched

`git status --short api/_engine api/_intent` — empty, before and after this
work.

## Task 3c: the `'d` contraction bug — flagged, not started

Per the brief's explicit instruction, not folded into Tasks 1–3. This is a
genuinely different bug (a match-time ambiguity — `"they'd mentioned"`
apparently resolving `'d` to "would" instead of "had," producing an
ungrammatical `modals-ability` reading) from everything Fix 6 addresses.
The brief references "Doc 16" as already investigating this, but as noted
above, no such doc exists in this project — so there is no existing
write-up to build on. **Flagging back for direction**, per the brief's own
request: investigate now as a follow-on, or leave for a separate pass?

## Task 4: blocked on metric-set confirmation

Not started. The brief's own instruction is explicit: "Confirm before
building: does this metric set look right... This brief treats the list
above as a recommendation requiring a nod, not a green light on its own."
No UI work has begun pending that confirmation.
