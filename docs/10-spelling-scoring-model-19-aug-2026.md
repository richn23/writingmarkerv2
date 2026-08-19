# Spelling scoring model — what's already built, 19 Aug 2026

Reference note, not a build task. Captures what `api/_intent/spelling_score.py`
(protected — read-only reference here) already does, since it's more capable
than "percent correct" and that wasn't written down anywhere else in the
project docs. Verified 19 Aug 2026 by reading the actual current file on
Richard's Desktop, line by line — every figure below matches the code.

## Three dimensions scored at once, not just right/wrong

**Severity** — six categories, not a binary:

| category | meaning | cost |
|---|---|---|
| correct | — | 0.0 |
| minor_slip | one edit, same sound (`beautifull`) | 0.4 |
| boundary | run together or split (`alot`) | 0.5 |
| phonetic | spelled by sound, 2+ edits (`skool`) | 0.7 |
| wrong_word | a different real word (`bast` for `best`) | 0.8 |
| unrecoverable | no confident reading at all | 1.0 |

`proper_noun` is excluded entirely — a name isn't an error.

**Difficulty** — the cost of an error is weighted by the GSE/CEFR band of the
*intended* word, not a flat penalty. Misspelling "school" (GSE 15, Pre-A1,
weight 1.00) costs more than misspelling something genuinely advanced (C1/C2,
weight 0.50), because getting an easy word wrong says more about
orthographic control. A short, explicit exemption list (`KNOWN_HARD` —
"because," "friend," "beautiful," "people," "receive," "believe," and
similar classic traps) steps the difficulty down one level for words that
are low-GSE but genuinely hard to spell, so those don't get unfairly
punished. A word missing from the reference list gets a fallback weight of
0.60; an `unrecoverable` word (no intended reading to look up) uses the
student's own mean difficulty across everything else they attempted.

**Persistence** — a wrong form produced once is a slip (normal cost); the
exact same wrong form produced every time that word is attempted is treated
as a belief, not a slip, and costs 1.3× more. Several different wrong forms
for the same word are still slips (the student is guessing, not settled on
a wrong rule).

## The formula

`index = 1 − (total cost ÷ total difficulty)`, over every word token
attempted (not just content words — orthographic control covers "becuase"
and "teh" as much as "enviroment," which is a deliberate difference from how
the vocabulary score is scoped). The reported 0–100 figure is that index
floored at zero and scaled: `score = round(max(0, index) × 100)`.

The denominator being total *difficulty*, not a word count, is what makes
this fair across ability levels: a Pre-A1 writer and a C1 writer with the
same *kind* of error rate land on the same number, because the penalty is
normalised against how hard the words *this* student actually attempted
were — a stronger-vocabulary student isn't automatically scored more
leniently per error just because their words are harder.

**No score below 8 attempts.** `MIN_ATTEMPTED = 8`; under that the function
returns `score: None` with `reason: "insufficient_sample"` rather than a
number, on the grounds that below it a figure isn't a measurement. This is
why a meaningful minority of scripts in a real batch legitimately show no
spelling score at all, and why the batch table prints a reason in that cell
instead of leaving it blank.

Every **error's** severity, difficulty, persistence, and resulting cost is
returned itemised (`detail`, sorted by cost) — nothing here is a black box;
the arithmetic behind the headline number can be checked row by row.
Correctly-spelled attempts are deliberately *not* in `detail`: they carry no
cost, but they do contribute their difficulty to the denominator, so
`total_difficulty` is larger than the sum of the difficulties visible in
`detail`. `categories` carries the per-severity counts across all counted
attempts, correct ones included, so the two together account for everything.

## The one honest gap, not yet built

Every error row already carries its CEFR/GSE `band`, but nothing currently
aggregates across rows into a level-based profile — e.g. "most of this
student's errors happen at B1-level words." `categories` (counts per
severity type) is already rolled up; a `band`-based rollup isn't.

**If this gets built**, it doesn't need `_intent/spelling_score.py` touched
at all — the `band` field already exists on every row in
`spelling_score_detail.detail`, so the aggregation (group errors by band,
maybe by severity-within-band) can be done entirely in `api/score.py` (the
unprotected glue layer) or even client-side in `app/page.tsx` from data
that's already in the response. Small addition on top of what exists, not
new engineering — flagged here for whenever Richard wants it, not scheduled.

**One caveat for whoever builds it.** A count of errors per band is
available from `detail` alone, but a *rate* per band — "how many of the
B1-level words this student attempted were misspelled" — is not: the
denominator would need the correctly-spelled attempts, and those never reach
`detail`. Getting rates rather than raw counts therefore does need a change
inside `spelling_score.py` (emitting a per-band attempted count alongside
`categories`), which puts it in protected territory and makes it a bigger
decision than the counts-only version. Worth settling which of the two is
actually wanted before starting.
