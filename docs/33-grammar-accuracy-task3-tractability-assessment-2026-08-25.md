# Grammar Accuracy v1 — Task 3: tractability assessment

Per docs/29's plan: assess each remaining feature-family before scheduling
implementation in detail. Investigation only — no detection code written
for these six yet. Grounded in what actually exists in the codebase
(checked directly, not assumed), the same discipline Tasks 1–2 used.

## Tense (beyond agreement)

Task 1 already covers subject-verb mismatch. What's left is *wrong tense
choice for context* — "Yesterday I go to the store" (past time marker,
non-past verb).

**Tractable narrow version**: detect an explicit past-time marker
("yesterday", "last week", "ago", …) in a clause and check the verb isn't
also marked past (reusing `is_past_form`, already module-level from Task
0). Bounded, reuses existing infrastructure, similar shape to Tasks 1–2.

**Not tractable for v1**: whole-narrative tense-*consistency* tracking (an
established pattern later deviated from) — this is docs/24's cascading
Scenario B, and building the pattern-detection machinery for it is a
materially bigger, more novel task than anything built so far, not a
small extension.

**Assessment: MEDIUM.** Recommend the narrow time-marker-contradiction
version only, if scheduled.

## Article/determiner

"I went to store" (missing), "an university" (wrong-form), "the a
homework" (added).

**Checked**: no countable/uncountable noun classification exists anywhere
in this codebase (`api/_data/gse_vocabulary.json`, `_engine/lemmas.py`,
nothing). Article correctness in English depends heavily on exactly that
distinction, and it isn't even a fixed per-word property — "chicken" is
uncountable as food ("I like chicken") and countable as an animal ("I saw
a chicken"), the same surface form needing different answers depending on
sense. Building or sourcing this data is a materially larger and fuzzier
task than Task 2's 34-verb list — likely thousands of nouns, with genuine
sense-dependent exceptions baked in, not a bounded list to cross-verify
against an existing trusted set the way `IRREG_PAST` was.

**Assessment: LOW for v1.** Recommend deferring, the same honest-exclusion
pattern Range already uses for structures it can't reliably detect, not a
silent gap.

## Number

"three dog" (missing plural), "many informations" (uncountable
incorrectly pluralized).

**Checked directly**: `_engine.lemmas.IRREGULAR` already has a trusted
irregular-plural table (`men`→`man`, `women`→`woman`, `children`→`child`,
`people`→`person`, `teeth`→`tooth`, `feet`→`foot`, `mice`→`mouse`,
`geese`→`goose`, `lives`→`life`, `wives`→`wife`, `knives`→`knife`,
`leaves`→`leaf`, `wolves`→`wolf`, `shelves`→`shelf`, `halves`→`half`,
`thieves`→`thief`) — the exact same shape of reusable reference data
`IRREG_PAST` was for Task 2, already built and already trusted, not
something to construct from scratch.

**Tractable sub-case**: a number/plural-quantifier ("three", "many",
"several") followed by a noun that's neither correctly `-s`-marked nor a
known irregular plural. Doesn't need full countability judgment — just
"is this specific noun pluralized correctly given an explicit quantity
marker," which is a narrower, better-defined question than Article's.

**Not tractable alongside it**: the *opposite* direction (uncountable
nouns wrongly pluralized, "informations") needs the same countability data
Article/determiner needs, so it inherits that gap.

**Assessment: MEDIUM-HIGH** for the "missing/wrong plural after an
explicit quantity marker" sub-case specifically. Good next-build candidate
— same reuse pattern and rough size as Task 2.

## Pronoun (case)

"Me and him went to the store" (subject case), "Give it to I" (object
case).

The case table itself is a small, closed class (`I`/`me`, `he`/`him`,
`she`/`her`, `we`/`us`, `they`/`them`, `who`/`whom` — 6-7 pairs, not a
large data-building task at all). The harder part is determining
*syntactic position* (subject vs. object) reliably enough to know which
form is required — compound subjects ("him and me went") and
post-preposition objects need the same kind of position-detection Task 1
already built for subject recognition, extended rather than reinvented.

**Assessment: MEDIUM.** Small reference data, moderate new detection
logic reusing Task 1's subject-position patterns. Good next-build
candidate.

## Preposition (choice/omission)

"arrived the station" (missing "at"), "married with her" (wrong choice).

Preposition choice is collocational, not rule-governed — it depends on the
specific verb or noun it pairs with ("depend ON", "arrive AT/IN", "married
TO"), and many verbs correctly take *different* prepositions for different
meanings ("agree WITH someone" / "agree ON something" / "agree TO a
proposal"). A verb→correct-preposition lookup big enough to be useful
would be a substantially larger and more ambiguity-prone data-curation
task than Task 2's list, with real risk of confidently asserting a "wrong"
answer that's actually one of several correct ones.

**Assessment: LOW for v1.** Recommend deferring, same reasoning as
Article/determiner.

## Word order

"always I go to school" (adverb misplaced), embedded-question word order
("what is he doing" inside a subordinate clause).

**Checked**: Range already has `FREQ_ADV` (`always usually often sometimes
rarely never seldom frequently occasionally`) and its own
`adverbs-of-frequency` family. **Tractable sub-case**: detect a frequency
adverb in an invalid position relative to the verb (e.g. sentence-initial
before the subject in a declarative, or misplaced after the main verb)
using data Range already has — no new reference data needed at all, the
smallest-effort candidate of the six.

**Not tractable alongside it**: the fully general word-order category
(embedded question word order, and others) needs dedicated pattern work
per sub-case, no shared infrastructure the way frequency-adverb placement
has.

**Assessment: MEDIUM** for the frequency-adverb-placement sub-case
specifically (smallest new-data cost of any candidate here); **LOW** for
the general category.

## Recommended build order, if approved

Ranked by tractability and how closely they match Task 1/2's proven
pattern (small, verifiable reference data or none at all; a bounded,
false-positive-conscious detection scope):

1. **Number** (missing/wrong plural after an explicit quantity) — reuses
   `_engine.lemmas.IRREGULAR`'s existing irregular-plural table directly.
2. **Word order** (frequency-adverb placement only) — reuses `FREQ_ADV`
   directly, no new reference data at all.
3. **Pronoun case** — small new reference table (6-7 pairs), moderate new
   position-detection logic extending Task 1's pattern.

**Recommend deferring for v1** (matching Range's own honest-exclusion
pattern, not silently building something less reliable): Article/
determiner and Preposition (both need substantial new, ambiguity-prone
reference data this codebase doesn't have); full tense-consistency
tracking (a materially bigger, more novel build than anything so far). A
narrow time-marker-contradiction version of Tense could be considered
alongside Number/Word order/Pronoun if there's appetite for a fourth, but
isn't in the top three by tractability.

## What this brief is asking for

Confirmation of this assessment and the proposed order before any
detection code is written for these three (or any of the deferred ones).
Same discipline as Tasks 1–2: one family built and verified at a time,
report before continuing to the next.
