# Grammar Accuracy v1 — Task 2 report (verb-form over-regularization)

Not committed yet — report first, per instruction. Task 3 and beyond not
started.

## What it does

`check_verb_form_overregularization()` in `api/_grammar/accuracy.py`
detects a written "-ed" form that over-regularizes a known irregular verb
("goed" for "went", "runned"/"runed" for "ran"). Reuses
`_engine.lemmas.lemma_candidates()` (already-existing, already-trusted
morphology reference — the same suffix-stripping/de-doubling rules that
correctly lemmatize "stopped"→"stop") to recover the base verb from the
written form, rather than writing new spelling-rule logic. Confirmed this
reuse works correctly across every common over-regularization pattern
before writing any detection code around it (doubled-consonant, undoubled,
silent-e-base, plain-suffix cases all recovered the right base).

Word identity deferred the same way as Task 1 (docs/24 Overlap Rule 1):
`written_to_intended` supplies the already-resolved reading for a token
Spelling already corrected, so this module never re-litigates a word
Spelling has already claimed.

## Scope, narrowed deliberately, twice

**Starter set of 31 irregular verbs, not the full ~90-verb list** — docs/29
flagged this size as "a real but bounded task," and building it
incrementally (same vertical-slice discipline Task 1 used) rather than
attempting all ~90 in one pass kept the risk of a transcription error
contained and checkable.

**Past-simple only, not past-participle, for this increment.** Two
reasons: it's the far more common real-world pattern (over-regularized
narrative past tense — "I goed to the shop" — versus rarer over-
regularized perfect-tense participles), and participle coverage runs into
`is_pp()` not even recognising some correct participles as valid at all
(confirmed: "run" isn't in `IRREG_PP` and doesn't end in "-ed", so
`is_pp("run")` is `False`) — a separate verification problem, deferred
rather than guessed at alongside this one.

## Every mapping entry cross-verified against Range's own trusted data — and it caught real gaps

Rather than typing 31 base→past-form pairs from memory and trusting them,
every value was asserted against `detect.py`'s own `IRREG_PAST` set (the
same set Range's `is_past_form()` already relies on) before this code ever
ran against a sentence. That check is still live at import time
(`assert all(v in IRREG_PAST for v in IRREGULAR_PAST_BY_BASE.values())`),
not just a one-off check thrown away after building the list.

**It found three real problems, none of them typos in this new file:**

- `"steal"` → `"stole"` and `"forget"` → `"forgot"` are **not present in
  `IRREG_PAST` at all** — a genuine gap in Range's own existing reference
  data. `is_past_form("stole", pos_of)` would currently return `False`,
  meaning Range's baseline-tense detector doesn't recognise "he stole the
  money" as valid past tense either. Not something to silently patch here
  — that's protected, calibrated code, out of this task's scope — so both
  verbs are simply left out of this starter set rather than built on
  unverified ground. Flagging for a decision on whether this is worth a
  separate, small fix to `IRREG_PAST` itself.
- `"wake"` → `"woke"`/`"woken"` is also absent — only `"awake"` →
  `"awoke"`/`"awoken"` is present in the trusted sets. Possibly deliberate
  (LENS's reference data may simply not have included plain "wake"), left
  out for the same reason as above.
- `"run"`'s past participle (`"run"`, unchanged from the base) isn't in
  `IRREG_PP` either, as noted above — kept for past-simple checking only.

## Verification

13 hand-constructed fixtures in `tests/test_accuracy_verb_form.py`
(13/13 passing), each with a stated reason. Deliberately includes negative
cases: correct irregulars ("went", "ate"), correct *regular* verbs
("played", "walked", "used" — confirming not every "-ed" word is treated
as suspect), and "shed" specifically (a coincidental "-ed"-shaped word that
isn't a regularized irregular at all, included because Task 1's fixtures
already surfaced how easily a real-word coincidence produces a false
positive if not tested for directly).

Confirms the Task 1/Task 2 boundary from the other direction too: `"He
goed to the shop."` with `written_to_intended={"goed": "went"}` (simulating
Spelling having somehow already resolved it) correctly produces zero
errors — once word identity is settled, there's nothing left for this
check to flag.

Existing suites unaffected: `tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_grammar_regression.py` 14/14, full 92-example fixture set
92/92 (0 unexplained), module imports clean including the new
cross-verification assertion, `_engine`/`_intent` untouched.

## Status

Not committed. Ready for review. Task 3 and everything beyond it not
started, per instruction.
