# Grammar Accuracy v1 — Task 3, family 4: narrow Tense report

Per docs/33's approved build order. This is the fourth and last of the
approved Task 3 families. Not committed yet — report first, per
instruction. Task 9 (cascading-error merge logic) not started.

## What it does

`check_tense_time_marker()` detects a sentence containing an explicit
past-time marker (`yesterday`, `ago`, `last night`/`week`/`month`/`year`/…)
whose main verb isn't marked past. Scoped exactly as docs/33 proposed:
marker-contradiction only, not whole-narrative tense-consistency tracking
(docs/24's cascading Scenario B), which stays out of scope as a materially
bigger, more novel build.

## A helper-reuse issue found again, same shape as Task 1's

Checked directly before writing detection code: `is_past_form("was",
pos_of)` is `False`. Range's `is_past_form()` deliberately excludes
`AUX_PAST` (`was`/`were`/`had`/`did`/`been`/`being`) — correct for Range's
own purpose (those auxiliaries are handled by separate, dedicated branches
elsewhere in its detector), wrong for this module's broader "does this
verb show past marking at all" question. `_verb_shows_past()` treats
`AUX_PAST` membership as past evidence too, avoided before it could ever
produce a false positive on "Last night she was tired."

## A real bug found by testing, not by design review

An earlier version scanned the *whole* sentence for subject-shaped
candidates and required exactly one, skipping anything ambiguous. That
broke on "Tom visit London last year" — a genuine tense error — because
"London" (capitalised, unrecognised) matched the same proper-noun-subject
heuristic Task 1 already relies on, even though it's the *object* of
"visit," not a second clause's subject. The same issue would affect any
sentence with an object noun phrase — common nouns too ("I visit the
museum last year" hit the identical false skip before the fix).

Fixed by taking only the *first* subject-shaped candidate found, then
checking for a genuine compound subject via an "and" between that
candidate and its own verb — a later object noun phrase never enters the
check at all, so it can't suppress a real catch. Confirmed with four new
regression-guard fixtures (two proper-noun, two common-noun) that this
specific failure mode can't silently return.

## Two deliberate exclusions, stated plainly

**Non-past auxiliaries/modals are excluded from checking** — "Yesterday
she is happy" (should be "was") is not caught. `am`/`is`/`are` have clear
correct-past counterparts and could plausibly be added later, but modals
(`would`/`could`/`might`, etc.) are genuinely ambiguous for this narrow
check, and rather than build a special case for the be-verb subset alone
in this pass, the whole non-past-aux/modal group is excluded uniformly —
narrower than it could be, but consistent and honestly stated rather than
partially covered without saying so.

**Only the first clause's subject+verb is ever examined** — an embedded
clause's own verb ("I don't know what happened yesterday") is not
independently checked, the same limitation Number and Pronoun case both
state for their own narrower scopes.

## Verified

16 hand-constructed fixtures in `tests/test_accuracy_tense.py` (16/16
passing, after the fix above — the bug was caught by the test battery
itself, not found separately). Includes the two deliberate-exclusion cases
(non-past copula, embedded clause) and four regression-guard fixtures for
the object-noun-phrase bug specifically.

Existing suites unaffected: `tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_accuracy_verb_form.py` 19/19, `tests/test_accuracy_number.py`
18/18, `tests/test_accuracy_word_order.py` 13/13,
`tests/test_accuracy_pronoun_case.py` 15/15,
`tests/test_grammar_regression.py` 14/14, full 92-example fixture set
92/92 (0 unexplained), module imports clean, `_engine`/`_intent`
untouched.

## Status

Not committed. Ready for review. This closes out all four of docs/33's
approved Task 3 families (Number, Word order, Pronoun case, narrow Tense).
Task 9 (cascading-error merge logic, docs/29) not started.
