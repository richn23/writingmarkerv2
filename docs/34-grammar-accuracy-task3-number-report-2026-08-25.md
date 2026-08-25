# Grammar Accuracy v1 — Task 3, family 1: Number report

Per docs/33's approved build order (Number → Word order → Pronoun case →
narrow Tense). Not committed yet — report first, per instruction. Word
order and the remaining families not started.

## What it does

`check_number()` in `api/_grammar/accuracy.py` detects a missing or wrong
plural after an explicit quantity marker: a number 2–12 ("three dog"), or
an unambiguous plural quantifier — "many"/"several"/"few"/"both"/
"various"/"numerous" ("many student"). Reuses `_engine.lemmas.IRREGULAR`'s
existing, trusted irregular-plural pairs (confirmed present in docs/33
before building anything around them) rather than new data — the same
reuse pattern Task 2 used for `IRREG_PAST`.

Word identity deferred the same way as Tasks 1–2 (docs/24 Overlap Rule 1):
a token Spelling already corrected is judged on its resolved form, not the
misspelling.

## Scope, deliberately narrow — two stated limitations, not silent gaps

**Only the word immediately after the marker is examined.** "three big
dog" (an intervening adjective) isn't detected — the same kind of honest,
stated limitation Task 1's missing-verb exclusion already uses, not
something to guess at by trying to skip an unknown number of adjectives.

**Ambiguous quantifiers are deliberately excluded from the marker set.**
"some"/"a lot of"/"most"/"all" correctly pair with *either* a plural
countable noun ("some books") or an uncountable one ("some information"),
and this module has no countability data (docs/33's finding, still true).
Including them would risk confidently asserting a wrong answer rather than
conservatively not flagging. A small, visible, "add from observed data"
uncountable-noun exclusion list (`advice`, `information`, `furniture`,
etc. — 17 entries, same spirit as `detect.py`'s `ADJ_PARTICIPLE`) guards
the *unambiguous* markers ("many"/"several"/etc.) against the same risk,
since those, unlike "some," genuinely do require a countable noun in
correct English but a learner could still misuse them with an uncountable
one by mistake.

## Verified

18 hand-constructed fixtures in `tests/test_accuracy_number.py` (18/18
passing on first run — no false positives or false negatives needed
fixing this time, unlike Task 1's two design corrections), each with a
stated reason. Covers: regular missing plurals, `-es`-requiring nouns,
irregular-singular-written-for-irregular-plural, the common phrase "many
people" (must not flag), uncountable nouns after both "many" and "few"
(must not flag — the countability-error case this check deliberately
doesn't claim), "one" taking a singular (must not flag), the intervening-
adjective limitation (must not flag, honestly), and the spelling+grammar
interaction case (flags on the corrected word, matching Tasks 1–2's
established pattern).

Existing suites unaffected: `tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_accuracy_verb_form.py` 19/19, `tests/test_grammar_regression.py`
14/14, full 92-example fixture set 92/92 (0 unexplained), module imports
clean, `_engine`/`_intent` untouched.

## Status

Not committed. Ready for review. Word order (frequency-adverb placement)
and the remaining approved families not started, per instruction.
