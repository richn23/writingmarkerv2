# IRREG_PAST/IRREG_PP gap fix — "stole", "forgot", "woke"/"woken"

Fixes the three gaps Task 2's cross-verification found (docs/31) in
`api/_grammar/detect.py`'s trusted reference data. Protected, calibrated
code — verified with the same rigor as the gate fix before being treated
as done.

## The fix

`IRREG_PAST` was missing `"stole"` and `"forgot"` entirely (their
participles, `"stolen"`/`"forgotten"`, were already present in `IRREG_PP` —
only the past-simple forms were absent). `"wake"` was missing both forms;
only `"awake"`'s (`"awoke"`/`"awoken"`) were present. Added `"stole"`,
`"forgot"`, `"woke"` to `IRREG_PAST` and `"woken"` to `IRREG_PP`, so
`wake`/`awake` now have the same parity `IRREG_PP` already gave `awake`
alone.

## Verified

- **Full 92-example fixture set: still 92/92, 0 unexplained** — the fix
  adds recognition, it doesn't touch any existing detection path.
- **`is_past_form()` now correctly recognizes all three** for Range
  directly: `is_past_form("stole", pos_of)`, `("forgot", ...)`,
  `("woke", ...)` all now `True` (previously `False`).
- **Live effect on real sentences, confirmed positive**: "He stole the
  money.", "She forgot her keys.", "He woke up early." now all correctly
  detect as `past-simple`/`a1` — previously these produced no detection at
  all (a silent miss, not a wrong answer, but a real gap in what Range
  could recognize).
- **Accuracy's Task 2 starter set extended cleanly**: `"steal"`,
  `"forget"`, `"wake"` added to `IRREGULAR_PAST_BY_BASE` (34 entries now),
  the module's own cross-verification assertion against `IRREG_PAST`
  passes with the extended set, and 6 new fixtures confirm both directions
  — over-regularized forms ("stealed", "forgetted", "waked") correctly
  flag, correct irregulars ("stole", "forgot", "woke") correctly don't.
  `tests/test_accuracy_verb_form.py` now 19/19.
- **Nothing else regressed**: `tests/test_accuracy_subject_verb.py` 21/21,
  `tests/test_grammar_regression.py` 14/14, module imports clean including
  both live assertions (`assert_detector_families` and Accuracy's
  irregular-mapping check), `_engine`/`_intent` untouched.

## Status

Not committed. Ready for review. Task 3 not started.
