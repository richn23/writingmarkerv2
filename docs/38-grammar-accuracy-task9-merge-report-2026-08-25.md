# Grammar Accuracy v1 — Task 9: cascading-error merge logic report

Per docs/29. Not committed yet — report first, per instruction. This closes
Scenario A (span-overlap merging across the six checks). Scenario B
(whole-narrative pattern propagation, docs/24) is explicitly out of scope
here and not attempted.

## What it does

Unlike Tasks 1–3, this isn't a new standalone check — it's a merge step
over the *already-computed* output of the six checks that now exist
(subject-verb-agreement, verb-form, number, word-order, pronoun, tense).

Every one of those six checks' error dicts now carries a `token_index`
field (the flagged token's integer position within its sentence), added in
this task specifically so overlap can be detected precisely. Two errors
are considered the *same span* only if they share both `sentence_index`
and `token_index` — not by string-matching `matched`/`written`, which
would be fragile against repeated words in a sentence (e.g. two "go"s in
the same sentence, only one of which is actually wrong).

`merge_accuracy_errors(errors_by_family)` takes a dict of
`{family_name: [error, ...]}` (the six checks' raw output, uncalled by
this function itself), groups by `(sentence_index, token_index)`, and for
any group with more than one entry, picks a single **primary** error and
attaches the others' family names to it as `also_flagged_by`. Groups of
one pass through unchanged except for an added `also_flagged_by: []`.

Errors with no `token_index` (defensive — none of the six checks currently
omit it, but nothing enforces that at the type level) fall into an
`_unkeyed` bucket keyed by their position in the input list, so two
such errors can never accidentally collide and get merged with each
other.

`check_all(raw_text, written_to_intended, pos_of)` is a convenience
wrapper: runs all six checks, passes their output straight into
`merge_accuracy_errors()`, returns the merged list. This is the first
function in `accuracy.py` that represents the module's actual output
shape as a whole — it is still not wired into `score.py` (Task 11).

## Choosing which error becomes primary

A `_FAMILY_SPECIFICITY` ranking decides which family "owns" a merged
entry when more than one fires on the same token. Right now it's a
two-tier ranking, not six-way: `tense` is ranked 1 (most general — it
only knows "this verb doesn't show past marking"), and the other five are
all ranked 0 (equally specific relative to each other, since no genuine
overlap has been found among any pair of them). The lower rank wins and
becomes primary; ties keep the dict's iteration order (Python's
`sorted()` is stable), which in practice means whichever family happened
to be listed first in `check_all()`'s `by_family` dict for a same-rank
tie — an edge case not yet observed in real sentences, and stated as such
rather than given a false sense of precision it doesn't have yet.

This ranking exists because I found one genuine, reproducible overlap
case — see below — and reasoned from it, not from a guess at all
possible pairings the six checks could ever produce.

## The one confirmed real overlap, and why it happens

`"Yesterday he go to school."` fires **both** subject-verb-agreement
("he go" should be "he goes") and tense ("go" doesn't show past marking,
contradicting "Yesterday") — same token, "go", same sentence. This isn't
a coincidence: a bare-form verb after a 3rd-singular subject is
*simultaneously* a subject-verb-agreement violation (wrong form for this
subject) and, whenever a past-time marker is also present, a tense
violation (wrong form for this time reference) — the same underlying
written word fails two independent, correctly-scoped checks for two
independent, correctly-stated reasons. Confirmed this isn't a one-off
fluke of that specific sentence by reproducing it with a different
subject shape ("Yesterday Tom go to school.", proper-noun subject rather
than pronoun) — see `test_accuracy_merge.py`'s end-to-end cases.

Tense loses the primary slot here because it's the more general
diagnosis of the two — "wrong form for the time reference" is true but
less specific than "wrong form for this subject," which is the more
directly actionable description of the actual error. No other pairing
among the six checks has produced an observed overlap; the four Task 3
families were each designed against materially different signal (a
plural marker, a sentence-initial adverb, a subject/object pronoun slot,
a time-marker/verb pairing) precisely to avoid firing on the same word
for the same underlying mistake, and none of the test fixtures across all
six suites has produced an unexpected merge.

## Verified

Testing here is split into two deliberately separate layers, per the
instruction to be concrete about the merge mechanism itself and not just
"each check still passes alone":

**Layer 1 — `merge_accuracy_errors()` tested directly against hand-built
error dicts**, bypassing the six real checks entirely. This isolates the
merge logic from whatever the checks currently produce, so a future
change to any one check's detection behavior can never silently mask a
merge-logic bug (or vice versa). Nine cases: a genuine two-family merge
with correct specificity ordering; same `token_index` but different
`sentence_index` (must NOT merge — confirms the key is the pair, not
either field alone); a three-way merge at equal specificity; two errors
that both lack `token_index` (must NOT spuriously merge via the
`_unkeyed` fallback); two errors at different `token_index` values in the
same sentence (must stay separate); empty input; no families at all;
a single unmatched error (confirms `also_flagged_by` is always present,
never omitted); and two errors from the *same* family colliding on one
token (shouldn't happen from the real checks today, but the merge logic
handles it without special-casing rather than assuming it can't occur).

**Layer 2 — `check_all()` tested end-to-end against real sentences.**
Five cases: the confirmed overlap sentence (merges correctly, primary is
subject-verb-agreement, `also_flagged_by: ["tense"]`); the same
underlying agreement error with no time marker present, so only one
check fires and no merge is possible (single entry, empty
`also_flagged_by`); a sentence with a genuinely separate, non-overlapping
number error (confirms an unrelated error from a different family isn't
merged into anything or suppressed just for co-occurring in the same
`check_all()` call); a fully correct sentence (all six checks return
empty, merge step correctly returns `[]` rather than erroring on
all-empty input); and the second overlap sentence with a proper-noun
subject, confirming the overlap shape reproduces beyond the one sentence
first found.

All 14 cases pass on first run in `tests/test_accuracy_merge.py`.

**Regression, confirmed unaffected by the `token_index` additions and the
new merge code:**
`tests/test_accuracy_subject_verb.py` 21/21,
`tests/test_accuracy_verb_form.py` 19/19,
`tests/test_accuracy_number.py` 18/18,
`tests/test_accuracy_word_order.py` 13/13,
`tests/test_accuracy_pronoun_case.py` 15/15,
`tests/test_accuracy_tense.py` 16/16,
`tests/test_grammar_regression.py` 14/14,
full 92-example fixture set 92/92 (0 unexplained — `detect.py` untouched
by this task), module imports clean under
`-W error::SyntaxWarning`, `_engine`/`_intent` untouched
(`git status --short` empty).

## What's deliberately not covered

**Scenario B (whole-narrative pattern propagation)** — an established
incorrect pattern earlier in a piece of writing making later, individually
correct-looking forms read as consistent with the error rather than as a
separate mistake. This is a materially different, harder problem
(requires tracking state across sentences, not just within one) and was
named as out of scope for Task 9 from the start, not discovered as a gap
partway through.

**Six-way specificity ranking** — only a two-tier ranking exists (tense
vs. everything else) because that's what the one confirmed overlap case
actually requires. Extending `_FAMILY_SPECIFICITY` to rank the other five
checks against each other would be guessing at pairings that haven't been
observed; if a real overlap among them ever surfaces, it should be added
then, with its own test case, the same way this one was.

## Status

Not committed. Ready for review. This closes out Task 9. Remaining
docs/29 items (Task 10 aggregation, Task 11 `score.py` wiring, Task 12 UI)
not started, unscheduled beyond this point.
