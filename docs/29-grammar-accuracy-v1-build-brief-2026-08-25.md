# Grammar Accuracy v1 — build brief

Plan only — no scoring logic written yet, per instruction. Grounded in
docs/24 Revision 3 (signed off) and the checks below against the actual
code Accuracy would build on.

## What's already settled (docs/24 Rev 3) and not reopened here

Input model (raw text primary, interpretation as paired reference), word
identity never re-decided by Accuracy, homophone pairs stay Spelling's,
over-regularization is Grammar's, the eight feature-family categories with
edit-type sub-classification, both cascading-error rules, error-free
definition, exclusions, unit of error (sentence-level global counts +
feature-level breakdown, T-unit and EGP-structure mapping deferred). This
brief is about *how to build toward that protocol*, not re-litigating it.

## Architecture

**New module: `api/_grammar/accuracy.py`**, not additions to `detect.py`.
Reasons:

- Accuracy's data contract is genuinely different — it needs *both* raw and
  interpretation text simultaneously (doc 27), where Range/Metrics take one
  text field. Bolting a second contract onto `detect_grammar_structures()`
  would blur what that function's single-text-in, evidence-out contract
  means.
- `detect_grammar_structures()` is already a large, calibrated, protected
  function (92/92 fixtures riding on its exact current shape). Keeping
  Accuracy separate means a mistake in new, unproven detection logic can't
  silently perturb Range's verified behavior, and Accuracy's own
  regression suite doesn't need to re-verify Range's 92 fixtures every run.

**Reuse, not reinvent — one small extraction needed first.** Doc 26
correctly identifies `is_third_s`/`is_bare_verb` (plus, checked directly,
`is_singular_noun`/`is_proper_noun_subject`) as already doing most of the
anchoring work subject-verb agreement needs. All four currently exist only
as closures nested inside `detect_grammar_structures()`
(`api/_grammar/detect.py:846-880`), capturing `pos_of`/`orig`/`w` from that
function's own scope — not callable from outside it.

**Task 0, before any detection logic**: promote these four to module-level
functions in `detect.py`, parameterized explicitly (`pos_of`, and `orig`/`w`
or equivalent passed as arguments rather than captured) instead of
reimplementing them a second time in `accuracy.py`. Pure extraction, zero
behavior change — verified by re-running the full 92-example fixture set
(must stay 92/92, byte-identical) before this task is considered done. This
keeps one source of truth for "what counts as a bare verb" shared between
Range's baseline-tense detection and Accuracy's agreement checking, rather
than two copies that can quietly drift apart. Flagging this as a distinct,
narrow, verifiable first step rather than folding it invisibly into Task 1,
since it touches already-protected, already-calibrated code and deserves
its own checkpoint.

**Data contract**: `check_accuracy(raw_text, interpretation_text, pos_of)`
— mirrors `spelling_score.py`'s `written`/`intended` pairing at the level
Accuracy actually operates on (spans, not single tokens, since agreement
errors involve two words). Sentence-aligned via the same `split_sentences()`
both raw and interpretation text already use elsewhere, so a raw-text
sentence and its interpreted counterpart can be paired positionally.

## Task sequence — vertical slice first, not eight parallel designs

Doc 28 lists eight feature-families as if scoping them together, but
committing to detailed designs for all eight before any of them has been
built and checked against real sentences risks the same kind of
hand-traced-and-wrong mistake the gate fix ran into twice. Proposing
instead: build **one feature-family completely** — detection through UI —
establish and verify the pattern, then extend to the rest with a proven
architecture rather than a paper one.

**Task 1 — Subject-verb agreement** (first, per doc 26's own
recommendation: existing anchoring logic, high tractability, no new
linguistic data needed beyond what Task 0 exposes).

- Detect: for each sentence, find subject-verb pairs using the promoted
  helpers; a written-form verb that doesn't agree with its subject given
  the interpreted/intended reading is a candidate error ("he go" — subject
  `he` is 3rd singular, `go` is a bare form where `goes` was needed).
- Edit-type sub-classification per the docs/24 table: wrong-form (most
  agreement errors) or missing (verb/auxiliary omitted entirely).
- Output shape: mirrors `grammar_detected`'s instance shape where
  reasonable (`family`, `matched` span, level/severity per docs/02's
  binary "meaning survives or breaks", `written` vs `intended` pair shown)
  — reusing an established shape rather than inventing a new one, but
  *not* claiming EGP-row/CEFR-level attachment, since that's explicitly
  out of v1's scope (docs/24's exclusions).

**Task 2 — Verb form (morphological over-regularization)**, second: the
canonical Grammar/Spelling seam doc 28 named explicitly, so proving this
one works is closer to "proving the protocol" than any of the others.
Needs a new, small irregular-verb reference (base → correct past/participle
forms) — this project's `IRREG_PAST`/`IRREG_PP` sets in `detect.py` already
list the correct forms; what's needed additionally is the *base* form each
maps from ("go" → "went"), so a written "goed" can be recognized as an
over-regularized attempt at a known irregular, not a random non-word. Given
`IRREG_PAST` is a flat set (not a base→form mapping), this is new data to
build, not reuse — flagging the size of that list (~90 irregular verbs) as
a real but bounded task.

**Tasks 3–8 — the remaining six feature-families**, scoped only at a
one-line level here, detailed only once Tasks 1–2 have proven the
architecture against real sentences:

- Tense (beyond agreement — e.g. inconsistent tense choice)
- Article/determiner (missing/wrong-form/added)
- Number (plural marking)
- Pronoun (case/reference)
- Preposition (choice/omission)
- Word order

Each will need its own tractability assessment before being scheduled —
some may turn out to need the same "new reference data" treatment Task 2
does, others may be closer to Task 1's reuse of existing anchoring logic.
Not pre-committing to a schedule for these six until 1–2 are built and
checked.

**Task 9 — Cascading-error merge logic.** Cross-cutting, needed once more
than one family-check can fire on overlapping material. Implements both
docs/24 rules: Scenario A (span-overlap merge across categories) and
Scenario B (pattern-level propagation counting). Natural to build once at
least two family-checks exist (Tasks 1–2) to merge against, not before.

**Task 10 — Global aggregation** (errors/100 words, error-free sentence %).
Computed *from* whatever family-checks exist at any point, not gated on all
eight being done. Must be labelled honestly as partial coverage while
Tasks 3–8 remain unbuilt — same "absence isn't evidence of absence"
discipline as Range's deferred-families list, not a number presented as if
it already reflects every grammar error the checked category can catch.

**Task 11 — `score.py` wiring.** New `grammar_accuracy` field in
`detail()`, following the exact defensive pattern `grammar_detected`/
`grammar_metrics` already use (try/except, never fail the whole score, a
paired `grammar_accuracy_error` field).

**Task 12 — UI.** Replaces the current "not built yet" placeholder inside
the existing "Grammar accuracy" collapsible in `app/page.tsx` — the
collapsible itself already exists (24 Aug brief), only its contents change.
Follows `GrammarDetectedSection`'s established pattern (per-family
breakdown, honest about what's covered vs. not, written/intended pair shown
per docs/24's overlap rules so a marker can see exactly what was compared).

## Verification — a real difference from Range's, worth stating plainly

Range's gate fix and the `'d`-contraction fix were both verified against a
genuine external ground truth: the live LENS TS detector, diffed directly.
**Accuracy has no equivalent reference to diff against** — doc 26
confirms LENS's own `production.ts` is one narrow, unrelated deterministic
case, not a general accuracy detector. There is nothing to run Accuracy's
output against and confirm agreement the way `npx tsx` against
`grammarDetect.ts` provided for Range.

This means Accuracy's fixtures will be **hand-constructed and hand-judged**
— written by reasoning about what a specific sentence's correct/incorrect
grammar actually is, not verified by an independent second implementation.
Proposing to compensate by:

- Sourcing example sentences from EGP's own reference data where possible
  (`grammar_profile.json`'s worked examples already used for Range's
  fixtures include some malformed-attempt-adjacent cases worth checking),
  rather than inventing sentences from scratch.
- Multiple independently-reasoned fixtures per family-check (not one
  "happy path" example), covering both a genuine error and a
  correctly-formed sentence that must *not* be flagged — false positives
  matter as much as false negatives here, arguably more, given the
  project's own stated bias toward false negatives over false positives.
- Stating explicitly, per fixture, *why* the expected answer is what it is
  — the same discipline `tests/test_grammar_regression.py`'s docstrings
  already apply, so a fixture can be checked by a human reader, not just
  trusted because the code that wrote it says so.

This is a genuinely lower-confidence verification posture than Range had,
not a gap to paper over — flagging it now so it's an informed trade-off,
not a silent one.

## What this brief is asking for

Confirmation to proceed with **Task 0 (the extraction) and Task 1 (subject-
verb agreement) only**, as a first, checkable increment — not the full
twelve-task list at once. Task 2 and beyond return for their own review
once Task 1's pattern is proven against real sentences. Report/plan before
implementation continues at every subsequent step, same discipline as
throughout.
