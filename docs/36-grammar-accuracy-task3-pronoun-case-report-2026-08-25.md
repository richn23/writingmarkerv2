# Grammar Accuracy v1 — Task 3, family 3: Pronoun case report

Per docs/33's approved build order. Not committed yet — report first, per
instruction. Narrow Tense not started.

## What it does

`check_pronoun_case()` covers three patterns: a pronoun in simple subject
position ("him goes"), a pronoun after a preposition ("to I"), and a
compound subject ("me and him went"). The case table itself is small (5
pairs: I/me, he/him, she/her, we/us, they/them) — "you"/"it" carry no case
distinction and are excluded; "who"/"whom" excluded too, since their
relative/interrogative uses are genuinely more complex and out of scope
for a first pass.

## One deliberate exclusion decided *before* writing detection code, and confirmed by testing

**Direct-object-after-verb ("she saw he") is not attempted at all**, and
this was decided at design time, not discovered as a bug afterward: a
plain lexical verb is extremely often followed by an embedded clause with
its own subject — "I know **he** is here," "she said **they** were late" —
and nothing distinguishes a genuine direct object from an embedded
clause's subject without real syntactic parsing, which this module
doesn't have. A naive "verb then pronoun = object position" rule would
false-positive on this constantly. Stated as an honest, deliberate
exclusion in the module docstring before the code was written, then
confirmed correct by testing "I know he is here." — must not flag, and
doesn't.

## One risk found by testing, guarded before it could false-positive

Simple subject-position detection ("object-form pronoun immediately
followed by a verb") has the same false-positive shape Task 1's "my
sister works" bug taught: **causative constructions** — "let him go,"
"make her stay," "have them wait" — are all correct English, an
object-case pronoun correctly followed by a bare verb, not a misplaced
subject. Guarded with a small, bounded exclusion list (`let`/`make`/
`have`/`help`, same spirit as `ADJ_PARTICIPLE`/Number's uncountable-noun
list) checked *before* writing the pattern's test fixtures, not patched
in afterward — confirmed correct: "Let him go." and "Make her stay." both
correctly don't flag.

## No reusable preposition list existed — built one, small and bounded

Checked directly: Range's own `prepositions` family is deliberately
deferred ("always present — uninformative as a detection"), so no
existing word list to reuse. Built a small, purpose-specific list (`to`,
`for`, `with`, `at`, `on`, `in`, `from`, `of`, `about`, `between`, `among`,
`near`, `against`, `like`, `without`, `into`, `onto`, `over`, `under`,
`through`, `during`, `before`, `after`) for the one narrow purpose this
check needs. Considered and deliberately excluded `"than"` — it introduces
an elliptical clause ("taller **than I** [am]") rather than functioning as
a true preposition, and including it would have flagged the more formally
correct reading as an error.

## Verified

15 hand-constructed fixtures in `tests/test_accuracy_pronoun_case.py`
(15/15 passing on first run). Confirms all three patterns catch real
errors, both stated exclusions (causative verbs, embedded clauses) hold,
questions are correctly out of scope, and a compound-subject sentence with
two wrong pronouns correctly produces two entries (one per pattern entry
point) rather than silently dropping the second.

Existing suites unaffected: `tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_accuracy_verb_form.py` 19/19, `tests/test_accuracy_number.py`
18/18, `tests/test_accuracy_word_order.py` 13/13,
`tests/test_grammar_regression.py` 14/14, full 92-example fixture set
92/92 (0 unexplained), module imports clean, `_engine`/`_intent`
untouched.

## Status

Not committed. Ready for review. Narrow Tense (time-marker contradiction)
not started, per instruction — the last of the four approved families.
