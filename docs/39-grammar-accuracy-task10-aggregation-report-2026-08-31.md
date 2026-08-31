# Grammar Accuracy v1 — Task 10: global aggregation report

Per docs/29. Not committed yet — report first, per instruction. Task 11
(`score.py` wiring) not started.

**Read the second half first.** Task 10 itself is small and works. The more
important outcome is that building it surfaced **two genuine false positives
in already-committed, already-signed-off checks** — both hitting very common
English. Neither is in Task 10's own code.

## What Task 10 does

`aggregate_accuracy(raw_text, merged_errors)` — pure arithmetic over a text
and an error list, calling none of the checks. Returns sentence count, word
count, error count, errors/100 words, grammatically error-free sentence
count and %, the error-free definition itself, and a coverage block.
`accuracy_report()` wraps `check_all()` + the aggregation into the shape
Task 11 will wire in.

It takes **merged** errors (Task 9's output) rather than the six checks' raw
output: under docs/24's Scenario A one span is one error however many
families describe it, so aggregating pre-merge output would double-count
precisely the overlaps Task 9 exists to collapse. Confirmed behaviourally —
"Yesterday he go to school." counts as 1 error, not 2.

## "Grammatically error-free" — carried in the payload, not left to the UI

Per docs/24 and docs/28's explicit requirement, the label is never bare
"error-free". Every field name carries it
(`grammatically_error_free_sentences`,
`grammatically_error_free_sentence_pct`), and the definition ships *in the
metric's own payload* rather than only in a UI string:

> A sentence with zero GRAMMAR errors, full stop — not "no errors of any
> kind". A sentence carrying a spelling mistake or a punctuation slip but no
> grammar error still counts as grammatically error-free. This is not a
> general correctness score.

Two fixtures enforce this mechanically rather than by prose: one asserts no
field name contains a bare `error_free`, so a UI can't pick up an
unqualified label; one asserts the definition text is present and says
GRAMMAR specifically. The definition's load-bearing claim is also tested
*behaviourally* — "I recieved the letter. She visted the musem." (two
misspellings, zero grammar errors) returns 100% grammatically error-free.

## Two denominator decisions, both deliberate

**Which text.** Both denominators come from the **raw as-written text** —
the text the errors were found in. This is the same self-consistency
principle `score.py`'s `_grammar_metrics()` states for itself, but it
resolves to the *opposite* text, because Accuracy's primary input is raw
(docs/27) while Metrics' is the interpretation.

These two word counts genuinely differ, not just in principle: Spelling's
corrector has a `split` decision (six call sites in `_engine/spelling.py`)
that turns one written token into several — "alot" → "a lot" — so the
interpretation can carry more words than the raw text.
`grammar_metrics["word_count"]` and `grammar_accuracy["word_count"]` are
two different true numbers about two different texts. **Flagging for Task
12: they must never be surfaced as the same count.** A `word_count_basis`
field is carried in the payload to make the distinction visible at the point
of use.

**Which tokenization.** The word count deliberately does *not* use the
contraction-expanded `_WORD` stream the checks index `token_index` into.
That stream is an internal index space, not a word count — `_expand()`
rewrites "don't" as "do not", and `_WORD` (`[a-z]+`) splits an unexpanded
"he's" into `["he", "s"]`, emitting an artifact token. Measured on
contraction-heavy learner text, the expanded stream runs **27–29% longer**
than the written word count. Using it would systematically flatter writers
who use contractions — denominator inflates, error count doesn't. So the
denominator is written words (`[A-Za-z']+`, counting "don't" as the one word
a teacher counts), matching the convention `score.py` already uses. The
numerator's index space and the denominator's unit are intentionally
different things; that's correct for a rate reported to a human, and the
reason it's written down in the module.

## Coverage is reported as partial, per family

Per docs/29's "absence isn't evidence of absence" requirement, the payload
carries all eight docs/24 families with a per-family scope note, not just a
6-of-8 count — because every *checked* family is itself a slice (verb form
is over-regularisation only; tense is time-marker contradiction only; word
order is frequency-adverb placement only; pronoun excludes direct-object
position). Both unbuilt families carry the reason: no countable/uncountable
noun data and no preposition-selection data exist in the codebase.

---

# The two false positives this task exposed

Both are in committed code (Task 1 and Task 3). Neither was caught by those
tasks' own fixture suites, because both suites test each pattern in
isolation; these only appear on ordinary connected prose, which is what
Task 10's aggregation put through the checks for the first time.

## Bug A — every modal and invariant auxiliary is flagged after a 3rd-singular subject

`check_subject_verb_agreement()`. **`"He can swim."` is flagged as a
subject-verb-agreement error.** So are:

| Flagged (all correct English) | | |
|---|---|---|
| He can swim. | He could swim. | He may leave. |
| He might leave. | He must leave. | He shall leave. |
| He should leave. | He will leave. | He would leave. |
| He had left. | He did leave. | Tom will leave. |

**Root cause:** the check has a correct irregular-agreement table for
be/have/do (`is`/`has`/`was` correctly pass, `have`/`do`/`are`/`were`
correctly flag), but **modals were never given "no agreement required"
treatment**, and `had`/`did` are being held to their present-tense
counterparts' agreement (`has`/`does`) despite being past forms that don't
inflect for person.

**Severity: high.** Modals after a third-person subject are about as common
as English gets — most learner texts will contain several, each producing a
confident, wrong accusation. This is the single most damaging thing
currently in the Accuracy module.

Correct behaviour is preserved on the true positives — "He have left.",
"He do leave.", "He are leaving.", "He were leaving." all still flag
correctly, so the fix is an exclusion, not a redesign.

## Bug B — possessive "her" read as a misplaced subject pronoun

`check_pronoun_case()`. **`"He took her book."` is flagged**, claiming "her"
should be "she". Also flagged: her friend, her hand, her face, her name,
her place, her work, her love, her help, her call, her watch, her plant,
her water — 13 of 13 sampled.

**Root cause:** `"her"` is the one member of `_OBJECT_FORMS` that is *also*
a possessive determiner. The subject-position pattern fires on "object-form
pronoun + verb-capable word", and a large share of common nouns
("book", "hand", "work", "name") also carry a verb sense, so
"her&nbsp;+&nbsp;noun" matches. "her dog"/"her car"/"her keys" don't flag
only because those nouns happen to have no verb sense — which is why the
existing 15 fixtures missed it.

**Severity: high**, same reason — possessive "her" is extremely common.

This is the third instance of the recurring pattern already documented in
docs/30 and docs/37: a word's *dominant* reading isn't checked, only whether
some reading is possible. Same shape as "my sister works" and the "London"
object-noun bug.

## Recommendation

Fix both before Task 11. Task 11 is what makes this output visible in the
product, and shipping a metric whose most common flags are wrong would
discredit the whole Accuracy panel — including the parts that are correct.
Neither fix looks like a redesign: Bug A is an invariant-form exclusion list
(modals + `had`/`did`), Bug B is a possessive-determiner guard on "her".

Both touch signed-off code, so I'd propose the same rigor as the
IRREG_PAST fix: root-cause first, narrow fix, new regression-guard fixtures
locking each specific failure mode, full suite green before commit.

## Verified (Task 10 itself)

19 fixtures in `tests/test_accuracy_aggregate.py` (19/19), split the same
two ways Task 9's merge testing was:

**Layer 1 — `aggregate_accuracy()` against hand-built error lists** (14
cases), so the arithmetic is pinned independently of what the checks
currently detect. That independence proved to be worth having rather than
theoretical, given the two bugs above. Covers: zero errors (rate is `0.0`,
not `None`); one error of two sentences; **two errors in the same sentence**
(error_count 2 but only one sentence disqualified — the two metrics must not
be conflated); all sentences flagged; exact per-100 arithmetic on a known
word count; contractions and apostrophe-s counting as one written word;
empty text (rates `None`, not `0`, not a crash); out-of-range
`sentence_index` not silently reducing the clean count; an error missing
`sentence_index` entirely; and the two label-discipline assertions.

**Layer 2 — `accuracy_report()` end-to-end** (5 cases), on sentences
deliberately chosen to avoid the two known false positives so they assert
aggregation rather than re-asserting detection: clean text, one real error
of two sentences, the misspelling/error-free load-bearing case, merged
overlap counted once, and the merged error list travelling with the
aggregate.

**Regression, all unchanged:** merge 14/14, subject-verb 21/21, verb-form
19/19, number 18/18, word-order 13/13, pronoun-case 15/15, tense 16/16,
grammar regression 14/14, full 92-example fixture set 92/92 (0 unexplained —
`detect.py` untouched). Module imports clean under
`-W error::SyntaxWarning`; `_engine`/`_intent` untouched.

## Status

Not committed. Ready for review. Two decisions needed: sign-off on Task 10,
and whether to fix Bugs A and B before Task 11 (recommended) or proceed to
wiring first.
