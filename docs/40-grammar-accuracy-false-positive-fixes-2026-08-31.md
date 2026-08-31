# Grammar Accuracy v1 — Bugs A and B fix report

Fixes the two false positives docs/39 found while building Task 10. Both
were in committed, signed-off code (Task 1 and Task 3). Not committed yet —
report first, per instruction. Task 11 not started.

Both fixes are exclusions, not redesigns, and both are scoped as narrowly as
the evidence supports.

## Bug A — modals and invariant auxiliaries

**Was:** `"He can swim."` flagged as a subject-verb-agreement error, along
with every modal (can/could/may/might/must/shall/should/will/would) and
`had`/`did` after a third-singular subject.

**Root cause:** `_irregular_required()` returns `None` for these, so they
fell through to the regular `-s` fallback, which read the absent marker as a
missing third-person `-s`.

**Fix:** an `_INVARIANT_AGREEMENT` set, checked before the regular fallback,
holding two genuinely invariant groups — modals (no inflected forms at all)
and `had`/`did` (past forms of have/do, which unlike `has`/`have` and
`does`/`do` don't inflect for person, but were being held to those present
tables).

**The part worth flagging: `was`/`were` were deliberately left out.** Unlike
modals they *do* agree ("he was" / "they were"), and adding them to the same
set — the obvious way to write this fix, since they sit alongside `had`/`did`
in `AUX_PAST` — would have silently switched off a working check. They
currently pass by way of the `-s` heuristic ("was" ends in -s, "were"
doesn't), which happens to give the right answer in all four
person/number combinations. Confirmed by fixture rather than assumed:
"He were leaving." still flags after the fix.

**Verified:** all 12 documented repros clean; true positives preserved
("He have left", "He do leave", "He are leaving", "He were leaving",
"He go to school", "Tom live in Paris", "She want a cat" all still flag);
correct forms still clean ("He is leaving", "He has left", "He was leaving",
"They were leaving", "They have left"). 15 new fixtures in
`tests/test_accuracy_subject_verb.py`, which goes 21 → 36.

## Bug B — possessive "her"

**Was:** `"He took her book."` flagged, claiming "her" should be "she" —
along with her friend/hand/face/name/place/work/love/help/call/watch/plant/
water, 13 of 13 sampled.

**Root cause:** `"her"` is the only member of `_OBJECT_FORMS` that is also a
possessive determiner, and a large share of common nouns carry a verb sense,
so Pattern 1's "object pronoun + verb-capable word" test matched ordinary
possessive noun phrases. "her dog"/"her car" escaped only because those
nouns have no verb sense — which is exactly why the existing 15 fixtures
missed it.

**Fix:** for `"her"` only, a following **noun-capable** word means
possessive, not a misplaced subject. Checked the GSE data before writing the
guard rather than assuming it would separate: every false-positive word
above is `noun=True`, while the words that follow a genuinely misplaced
subject ("goes", "runs", "walks", "swims", "sings", "sleeps", "likes") are
all `noun=False`. The separation is clean, so the guard is precise rather
than a blunt suppression.

**Scoped to "her" deliberately.** Applying it across `_OBJECT_FORMS` would
have weakened real catches for nothing, since him/me/us/them are never
possessive determiners — "Them work hard." must still flag even though
"work" is noun-capable, and it does.

**Known, accepted narrowing:** "Her works hard." (where the verb is itself
noun-capable) is now missed. That's the deliberate trade — possessive "her +
noun" is overwhelmingly more common than a misplaced subject whose verb
happens to be noun-capable, and the module's standing posture is that a miss
is preferable to a confident false accusation.

**Verified:** all 13 repros clean; genuine subject-position errors preserved
("Her goes to school", "Her runs every day", "Her walks to work",
"Him goes to school", "Them work hard", "Me and him went to the store");
the other two patterns untouched ("Give it to I", "This gift is for I",
"I gave the book to she" still flag; "Let him go", "Make her stay",
"I know he is here", "Give it to him" still clean). 8 new fixtures in
`tests/test_accuracy_pronoun_case.py`, which goes 15 → 23.

## Both are the same recurring lesson, third instance

A word's **dominant** reading matters, not merely whether some reading is
possible. Same shape as "my sister works" (docs/30) and the "London"
object-noun bug (docs/37). Bug B is the direct case — a noun sense
outweighing a verb sense. Bug A is the mirror image: a form that has *no*
inflection to check being pushed through a rule that assumes one.

Worth noting for the remaining build: both were invisible to fixture suites
that test each pattern in isolation, and only appeared once ordinary
connected prose ran through the checks. That's an argument for keeping
`accuracy_report()` pointed at realistic multi-sentence text as new families
are added, not only at targeted single-pattern fixtures.

## Verified overall

`tests/test_accuracy_subject_verb.py` 36/36 (was 21),
`tests/test_accuracy_pronoun_case.py` 23/23 (was 15),
`tests/test_accuracy_aggregate.py` 19/19,
`tests/test_accuracy_merge.py` 14/14,
`tests/test_accuracy_number.py` 18/18,
`tests/test_accuracy_tense.py` 16/16,
`tests/test_accuracy_verb_form.py` 19/19,
`tests/test_accuracy_word_order.py` 13/13,
`tests/test_grammar_regression.py` 14/14,
full 92-example fixture set 92/92 (0 unexplained — `detect.py` untouched by
either fix). Module imports clean under `-W error::SyntaxWarning`;
`_engine`/`_intent` untouched.

End-to-end on the prose that originally exposed both bugs:

| Text | Before | After |
|---|---|---|
| "He goes to school. She visited her friend yesterday." | 1 error, 50% error-free | **0 errors, 100%** |
| "I don't know. He can't come." | 1 error, 50% | **0 errors, 100%** |
| "She took her book and he will read it later." | 2 errors | **0 errors, 100%** |
| "Yesterday he go to school and she visited her friend." | 2 errors | **1 error** (the real one) |

The last row is the useful one: the genuine agreement error is still caught,
with the spurious possessive flag gone.

## Status

Not committed. Ready for review. Task 11 (`score.py` wiring) not started.
