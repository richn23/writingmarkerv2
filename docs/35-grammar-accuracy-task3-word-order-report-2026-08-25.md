# Grammar Accuracy v1 — Task 3, family 2: Word order report

Per docs/33's approved build order. Not committed yet — report first, per
instruction. Pronoun case and narrow Tense not started.

## What it does

`check_word_order_frequency_adverbs()` detects a frequency adverb in one
of two unambiguous wrong positions. Reuses Range's own `FREQ_ADV` directly
— no new reference data at all, the smallest-cost candidate in docs/33's
assessment. Range's own `adverbs-of-frequency` family is explicitly
"detected by presence only — position analysis deferred"; this check is
that deferred position analysis, built as its own construct.

**Pattern A (sentence-initial)** — scoped to `"always"` alone, not the
full `FREQ_ADV` set. English frequency adverbs don't behave uniformly
sentence-initially, checked directly rather than assumed:
`"sometimes"`/`"usually"`/`"often"`/`"frequently"`/`"occasionally"` are
completely normal there ("Sometimes I go to the park" is ordinary,
correct English), while `"never"`/`"rarely"`/`"seldom"` require
subject-aux inversion when fronted ("Never have I seen" — correct; "Never
I have seen" — wrong) — a case Range's own detector already has separate,
nested fencing logic for (`INVERSION_OPENERS`/`FRONTED_NEGATIVE`) that
isn't safely reusable here without replicating its full nuance. Rather
than guess, this increment flags only `"always"` — the one member with no
competing correct sentence-initial reading — and explicitly, statedly
defers the inversion-requiring group rather than handling it wrong.

**Pattern B (adverb after the main verb)** applies to the full `FREQ_ADV`
set — no comparable nuance exists; every member of this set belongs
before the main lexical verb, never after. Only fires immediately after a
*confirmed* subject+verb pair, reusing Task 1's own subject-detection
patterns, rather than treating any verb-shaped word anywhere in the
sentence as a candidate — the same false-positive lesson Task 1's "my
sister works" bug taught (a bare "is this word a verb" check isn't
enough). Confirmed this still correctly excludes a *correctly*-placed
adverb: for "the dog always barks," the token immediately after the
subject is the adverb itself, which fails the "is this the verb" check
and the sentence is correctly left unflagged — verified empirically, not
assumed from the code's shape.

## Verified

13 hand-constructed fixtures in `tests/test_accuracy_word_order.py`
(13/13 passing on first run). Deliberately includes fixtures for what this
check does *not* attempt, not just the happy path: "sometimes"/"usually"
sentence-initial (must not flag — confirms the nuance that scoped Pattern
A down to "always" alone), correctly-inverted "never" (must not flag),
non-inverted "never" (must not flag — an honest, stated miss, not a
silent wrong answer), and questions (out of scope entirely, must not
flag). Also confirms correct placement after an auxiliary and after "be"
don't false-positive, and that both subject types (pronoun,
determiner+singular-noun) catch the actual after-verb error correctly.

Existing suites unaffected: `tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_accuracy_verb_form.py` 19/19, `tests/test_accuracy_number.py`
18/18, `tests/test_grammar_regression.py` 14/14, full 92-example fixture
set 92/92 (0 unexplained), module imports clean, `_engine`/`_intent`
untouched.

## Status

Not committed. Ready for review. Pronoun case and narrow Tense not
started, per instruction.
