# Grammar Accuracy v1 — Task 0 + Task 1 report

Per docs/29's approved scope (Task 0 + Task 1 only). Not committed yet —
report first, per instruction. Task 2 and beyond not started.

## Task 0 — promoted the closures, verified zero behavior change

`is_third_s`, `is_past_form`, `is_bare_verb`, `is_singular_noun`,
`is_proper_noun_subject` moved from closures nested inside
`detect_grammar_structures()` to module-level functions in `detect.py`,
parameterized explicitly (`pos_of`, and `orig`/`w`/`i` for the proper-noun
check) instead of captured from the enclosing scope. Pure extraction, same
bodies verbatim.

**Verified**: full 92-example fixture set still 92/92, 0 unexplained
(byte-identical to before the extraction). `assert_detector_families`
passes. Module imports clean, no `SyntaxWarning`s. `_engine`/`_intent`
untouched.

## Task 1 — subject-verb agreement, in a new `api/_grammar/accuracy.py`

Not wired into `score.py` yet (Task 11, out of this increment's scope).

### What it does

Detects wrong-form subject-verb agreement errors (a verb IS present but
carries the wrong marking — "he go", "they is", "he have a car") against
raw/written text, per doc 27's input-model correction. Word identity is
never independently re-decided: `written_to_intended` (built from the
Spelling audit trail) supplies the intended reading for any already-
corrected token; a token absent from that map is judged on its own written
form directly.

Scope, deliberately narrow, matching docs/29: wrong-form only. A
completely missing verb/auxiliary ("she happy", "they going" with "are"
omitted) is not detected — distinguishing "no verb attempted" from "not
verb-shaped for some other, possibly intentional, reason" is a harder,
more false-positive-prone problem, left out rather than guessed at.

### Two real design problems found only by testing, not by plan

Docs/29 proposed reusing `is_third_s`/`is_bare_verb` directly for the
agreement verdict itself. Both turned out unsafe once tested against real
sentences — not because the plan was careless, but because these
functions were calibrated for a different job:

1. **"He is going to school" was flagged as an error.** `is_third_s`/
   `is_bare_verb` exclude short auxiliaries (`AUX_S`, length < 4) — correct
   for Range's own purpose (regular "-s" as *evidence* of present-simple
   tense; "is" isn't that kind of evidence), but "is" not passing that
   filter isn't the same as "is" being *wrong* here. Fixed with a small,
   explicit `be`/`have`/`do` irregular-agreement table, checked before
   falling through to the regular path.
2. **"My sister works in London" was flagged as an error — a false
   positive on a completely correct sentence.** `is_third_s`'s strict mode
   requires the word to be `verb_dominant` (more verb senses than noun
   senses) — correct for Range, where requiring high confidence before
   claiming a detection is the right conservative default: a miss there
   just means nothing was detected, which is safe. For Accuracy, the
   identical miss inverts into a false accusation: "works" genuinely has
   noun senses (*public works*) outweighing its verb sense in the GSE data,
   so `verb_dominant` is `False` even though "works" is exactly the correct
   verb here. Fixed by writing this module's own, deliberately more
   permissive, symmetric check (`_agrees_third`/`_agrees_bare`: ends in
   "-s" and is recognised as a verb in *any* sense — not required to be the
   dominant one) rather than reusing Range's detection-confidence
   threshold as a correctness threshold.

Both were caught only by running hand-constructed fixtures against real
sentences, not by reasoning about the plan in advance — the same lesson
the gate fix's own verification history already taught: hand-tracing a
scoring/matching function's behavior is unreliable enough that empirical
testing has to be the actual bar, not a formality after the fact.

### Verification

21 hand-constructed fixtures in `tests/test_accuracy_subject_verb.py`
(21/21 passing), each with a stated reason for its expected answer.
Deliberately includes negative cases (must NOT flag) alongside positive
ones — plural subjects, past tense, present continuous, a correctly-used
noun-dominant verb, a spelling slip with no grammar error underneath — not
just a list of errors to catch, since false positives matter as much here,
arguably more, per this project's own stated bias.

Confirms the design assumptions from docs/29 directly:
- **Spelling/Grammar boundary holds**: "He recieve the letter" (with
  `recieve`→`receive` already resolved by Spelling) still correctly flags
  the missing "-s" on the *corrected* word — Grammar Accuracy judges the
  form Spelling already resolved, never re-litigates the spelling itself.
- **Task 1/Task 2 boundary holds**: "He goed to the shop" is correctly
  *not* flagged by this check — `goed` isn't recognised as a verb at all,
  so it falls through the "unrecognised token" guard rather than being
  misjudged as an agreement error. Confirms this stays Task 2's
  (over-regularization) territory, not Task 1's, without needing to special-
  case it.

Existing suites unaffected: `tests/test_grammar_regression.py` 14/14, full
92-example fixture set 92/92 (0 unexplained), `assert_detector_families`
passes, module imports clean, `_engine`/`_intent` untouched.

## Status

Not committed. Ready for review. Task 2 (verb-form over-regularization) and
everything beyond it not started, per instruction.
