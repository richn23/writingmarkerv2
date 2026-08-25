# Grammar Accuracy v1: error-counting protocol — investigation + proposal

**Revision 3** (25 Aug 2026). Investigation and proposal only — still no
Accuracy code written. Checked properly this time: `docs/26`
(`claude_21-grammar-full-spec`), `docs/27` (`claude_22`, the first
amendment), and `docs/28` (`claude_23`, the error-protocol-sequence second
amendment) now exist in this repo and have been read in full. Revisions 1
and 2 were built from paraphrase and pasted fragments because those three
documents didn't exist here yet; this revision replaces every place that
mattered with what they actually say, not just the two items flagged for
update.

One correction found beyond the two flagged items, material enough to
restructure a section: **doc 27 corrects the input model for Accuracy
specifically** — it reads raw/written text, not the approved interpretation
Repertoire and Metrics read. Revisions 1–2 had Accuracy reading the
interpretation (matching Repertoire/Metrics' pattern); that was wrong for
Accuracy, and everything downstream of it (Overlap Rule 1 especially) is
rewritten below to match doc 27's actual correction rather than patched.

## Investigation 1: how Spelling's taxonomy actually draws its lines

Read `api/_intent/spelling_score.py` (as instructed, read-only) plus its
upstream category source, `api/_intent/review.categorise()`, and where
`real_word` gets set in `api/_intent/layer.py` — the scoring file alone
doesn't show *how* a token lands in a category, only what happens once it
has.

**Categories, as actually built** (doc 26/28 cite doc 10's naming —
`correct`/`minor_slip`/`boundary`/`phonetic`/`wrong_word`/`unrecoverable`/
`proper_noun` — which matches the code exactly; docs/02's older
"sound/structural/boundary" framing does not, see the drift note below):
`minor_slip` (one edit, same sound — "beautifull"), `boundary` (run
together/split — "alot"), `phonetic` (2+ edits, same sound — "skooi"),
`wrong_word` (a *different real word* — "bast" for "based"),
`unrecoverable` (no confident reading), `proper_noun` (excluded from
scoring entirely).

**`categorise()`'s actual decision tree** (`api/_intent/review.py:273`):

```
split?                          -> boundary
answer == "proper_noun"?        -> proper_noun
no correction at all?           -> correct (if "not_a_misspelling") else unrecoverable
was_real_word?                  -> wrong_word
edit_distance<=1 and same_sound -> minor_slip
same_sound or same skeleton     -> phonetic
edit_distance<=1                -> minor_slip
else                             -> phonetic
```

**The critical line for the Grammar boundary is `was_real_word`.** Traced
to `layer.py`: it's `True` only for tokens flagged by
`suspicious_real_words()` (`_engine/spelling.py`) — a token that **is**
found in the vocabulary reference, but which is orthographically/
phonetically close enough to a *different* real word that it's flagged to
the intent layer as a possible confusion (homophone- or near-miss pairs:
"then"/"than", "loose"/"lose", "your"/"you're", "their"/"there"/"they're").
Every other path (junk, weak corrections, joinable pairs) is `real_word:
False`.

**What this means concretely: Spelling already fully owns homophone/
confusable-real-word substitution**, at severity 0.8 (`wrong_word`) — the
second-highest severity in its scale. This is resolved entirely by
orthographic/phonetic similarity between two real words, not by any
grammatical reasoning about which one the sentence needs.

### A real drift worth flagging: docs/02's spec vs. what's actually built

docs/02 (18 Aug 2026, the original six-dimension model) describes Spelling
as "error type: sound/structural/boundary, severity: recognisable/unclear/
unrecoverable." The as-built code has six categories under different names
(doc 26/28 correctly cite doc 10's naming instead, confirmed matching the
code), and critically, `wrong_word` — a real-word-for-real-word confusion —
isn't clearly anticipated by docs/02's three-way framing at all. If
Grammar's error taxonomy gets designed against docs/02's original prose
description rather than the actual shipped categories, it will very likely
re-claim `wrong_word` cases as grammar errors without realizing Spelling
already fully scores them — a live double-counting risk, not a
hypothetical one. (Doc 28 independently arrives at the same seam via its
own example — see the Grammar/Spelling boundary rule below.)

## Investigation 2: is raw (pre-correction) text available, separate from the interpretation?

**Yes, confirmed directly in `api/score.py`'s `detail()`:**

- `out["text"] = result["text"]` — the raw, as-written learner text.
  Nothing applied to it at all.
- `out["corrected_sample"] = result.get("corrected_sample")` — the
  "approved interpretation": spelling-only corrected (per
  `_intent/layer.py`'s own docstring: "Nothing is inserted, no grammar is
  touched, and no word is upgraded"). This is what Grammar Detected/Range
  and Grammar Metrics both read (`_grammar_source_text()` in score.py).
- `out["corrected_text"]` — a third, always-present field: the
  deterministic-only correction, used as `corrected_sample`'s own fallback.

Both raw and interpretation text are already siblings on the same response
object, with no new plumbing required. Confirmed by reading the field
assignments directly, not inferred. **This is now load-bearing, not just
available**: doc 27 requires Accuracy to read the raw field as its primary
input — see the input model correction below.

## A structural problem this investigation surfaced, not asked for but load-bearing

Grammar Detected (Range)'s entire detection mechanism is pattern-matching
against **correctly-formed** constructions — e.g. the present-perfect
detector fires on `have/has + past participle`, which requires the
auxiliary to already agree with its subject to match at all. **A malformed
attempt at a structure typically won't match any detector pattern, so it
doesn't fail loudly — it just doesn't fire, becoming invisible rather than
flagged.** "She have finished" would very likely not register as an
attempted present perfect at all under the current detector, let alone as
one done wrong.

Doc 26 §4 independently confirms this is why full attempted-vs-landed
EGP-structure mapping (LENS's original design) is architecturally harder
than Repertoire or Metrics, and doc 28's revised sequence schedules it as
"eventually... not scheduled" — step 6, after even Accuracy v2. Consistent
with, not contradicted by, what this investigation found independently.

## The input model — corrected per doc 27, not what Revisions 1–2 had

**Doc 27's correction, verbatim reasoning:** Repertoire and Metrics both
read the approved interpretation text. Accuracy must not — doing so would
score the correction pipeline's grammar, not the learner's. "Yesterday I go
shopping and buy two shirt" corrected to "Yesterday I went shopping and
bought two shirts" would show *zero* errors if Accuracy read the corrected
version, because the errors under measurement (`go→went`, `buy→bought`,
`shirt→shirts`) are exactly what correction removes. Doc 27 also grounds
this in an existing project principle from doc 06: the written+intended
pair `spelling_score.py`'s `score()` already takes is "the template every
future construct's scoring should copy, not reinvent."

**Corrected model:**

| Section | Reads from |
|---|---|
| Grammar detected (Repertoire) | Approved interpretation text |
| Grammar Metrics (Complexity) | Approved interpretation text |
| Grammar Accuracy | **Raw/written learner text**, with the approved interpretation available as the paired "intended" reference — same written+intended shape `spelling_score.py`'s `attempts` list already uses |

**What this changes about the protocol below**: Accuracy doesn't ask "is
this interpreted word used correctly" — it asks "does the written form
match what the writer needed, given what they were interpreted to mean."
Word *identity* still defers entirely to the interpretation (Overlap Rule
1, rewritten below) — Accuracy never re-decides which word was intended.
What it independently examines is the *written form's own grammatical
marking* against that already-settled identity, which is a genuinely
different question from what Repertoire/Metrics ask of the same text.

This also sharpens the morphological over-regularization case (Overlap
Rule 3): because Accuracy sees the raw text directly, it can recognize
"goed" as an attempted irregular past tense even in the likely case that
neither Spelling nor the interpretation ever resolves it to "went" at all
(the form-test gate structurally can't bridge that far) — "written" and
"intended" may be identical for that token, and Accuracy's judgment there
has to come from its own irregular-verb knowledge, not from a
written-vs-intended discrepancy the earlier pipeline stages already
surfaced.

**Not resolved here, flagged for the eventual build brief** (doc 27's own
words): this is a new data contract for Accuracy specifically (raw +
interpretation as a pair, not the single text field the other two
sections share) and shouldn't default to reusing Repertoire/Metrics'
single-field pattern when that build starts.

## "Error-free" — explicit definition

**"Error-free" means zero grammar errors, full stop — not "no errors of
any kind."** A sentence carrying a spelling mistake or a punctuation slip
but zero grammar errors still counts as error-free for this metric. Stated
plainly per doc 28's own requirement, both here and in whatever UI label
surfaces it — never presented as a general correctness score.

This falls directly out of Overlap Rule 1 below, not as an extra check
layered on top: Grammar Accuracy never independently re-decides word
identity for a token Spelling has already resolved, so a spelling slip can
never be double-counted as a grammar error and can never cost a sentence
its error-free status under this definition. The definition is only as
reliable as that rule being airtight in the actual implementation.

## Category boundaries — reconciled: feature-family primary, edit-type sub-classification

Doc 28's eight feature-family categories (subject-verb agreement, verb
form, tense, article/determiner, number, pronoun, preposition, word order)
and doc 02's four edit-type categories (missing / wrong-form / added /
wrong-order) combine as: **feature-family is the primary category a marker
sees; edit-type is a sub-classification within it**, describing *how* that
feature went wrong rather than *which* feature it was.

| Feature-family (primary) | Typical edit-types (sub) | Example |
|---|---|---|
| Subject-verb agreement | wrong-form; missing | "he go" (wrong-form); "she \_\_ happy" for "is" (missing) |
| Verb form | wrong-form; missing; added | "goed" (wrong-form, irregular over-regularized); "she working" (missing aux); "did went" (added, redundant aux) |
| Tense | wrong-form | "yesterday I go" (wrong-form) |
| Article/determiner | missing; wrong-form; added | "I went to store" (missing); "a university" → "an university" (wrong-form); "the homework" → "the a homework" (added) |
| Number | wrong-form; missing | "three dog" (missing plural marker, arguably wrong-form depending on how the marker is modeled) |
| Pronoun | wrong-form | "me and him went" (wrong-form, case) |
| Preposition | wrong-form; missing | "arrived the station" (missing "at"); "married with her" (wrong-form) |
| Word order | wrong-order (only) | "always I go" |

Word order is structurally exclusive: by definition a word-order error IS
a misordering, so "wrong-order" is effectively the only applicable
edit-type for that feature-family.

**These eight are v1's diagnostic layer, not the whole of v1** — doc 28's
build order (§ below) puts two *global* metrics (errors/100 words,
error-free sentence %) ahead of this feature breakdown. The eight
categories give distribution *underneath* the global counts, not the
counts themselves.

Severity: binary-ish, "meaning survives or breaks" (doc 02) — distinct
from Spelling's continuous weighted scale, since the two measure genuinely
different things (orthographic cost vs. communicative damage). Not
addressed in docs 26–28 specifically; carried forward from doc 02 as
unchanged and uncontradicted.

## Overlap rules with Spelling — rewritten for the corrected input model

1. **Word identity is never re-decided by Grammar Accuracy.** For any
   token, the "intended" word is whatever the interpretation already
   settled on (Spelling's correction, the intent layer's resolution, or
   the written form itself if nothing changed it) — Accuracy takes that as
   given and only examines whether the written form's own grammatical
   marking is correct for that identity. This is the rule the "error-free"
   definition depends on, and it's the mechanism that makes "reads raw
   text" (above) not mean "re-litigates spelling."
2. **Homophone/confusable real-word pairs (Spelling's `wrong_word`
   category) stay entirely Spelling's**, even where the confusion lands on
   a grammatical category by coincidence (possessive vs. contraction:
   "its"/"it's"). Falls directly out of Rule 1: word identity there is
   already settled by Spelling: Accuracy only asks whether *that* word,
   once identified, is grammatically correct.
3. **Morphological over-regularization ("goed," "runned," "comed") is
   Grammar's domain, not Spelling's.** Doc 28 names this exact case as the
   canonical Grammar/Spelling seam requiring "its own explicit rule, not an
   assumption that the two taxonomies will naturally sort themselves out."
   Spelling's form-test-gated corrector structurally can't reach these
   (edit distance/phonetic similarity to the correct irregular form is
   normally too large to pass `form_test`), so they fall through as
   `unrecoverable` or stay unresolved in Spelling rather than being claimed
   by it. Per the input model above, Accuracy sees the raw "goed" directly
   and judges it as a verb-form error using its own irregular-verb
   knowledge — not by comparing against an interpretation that may never
   have resolved it either.
4. **Punctuation stays its own dimension** (doc 02) — counted in neither
   Spelling's nor Grammar Accuracy's error tallies.

## Cascading-error treatment — two distinct scenarios, both need a stated rule

Revision 2 only addressed the first of these. Doc 28 names a second,
materially different one that needs its own rule, not a reuse of the
first.

**Scenario A — one span, multiple possible descriptions.** A missing
3rd-person "-s" is describable as both a Verb form error and a
Subject-verb agreement error. **Rule: count once, attributed to the single
most specific applicable feature-family** — mechanically, two candidate
errors merge when they share a token span and describe the same
grammatical relationship (the verb and its subject), implemented as a
span-overlap check at merge time.

**Scenario B — one root error propagating as many later "errors."** Doc
28's example: an early tense error establishes a pattern (present tense
used for past narration), and every subsequent verb that's internally
consistent with the writer's own established (incorrect) pattern would
otherwise get flagged as a separate, fresh tense error relative to standard
English. **Rule: once a specific error type is identified as a sustained
pattern across a stretch of text (not a single slip), count it once as a
pattern-level error, scoped to where it holds** — not once per instance,
and not silently reduced to only the first occurrence either, since that
would understate how pervasive it is. The count reflects the pattern's
span (e.g. "present-for-past used consistently across N clauses"), not N
separate identical tense errors.

Both rules are stated to build against; neither has been validated against
real error data, since no Accuracy code exists yet to validate them with.

## Exclusions — stated as rules

- The 16 EGP families Range already defers stay deferred for Accuracy too.
  The 2 partial families keep their existing honest detects/misses framing
  for Accuracy as well.
- **Structure-specific EGP families that don't map onto the eight feature
  categories (comparatives/superlatives, passive voice, relative clauses,
  reported speech, conditionals, modals) are excluded from v1 — confirmed
  intentional scope limit, not a gap.** Doc 28's build order schedules the
  full attempted-vs-landed EGP-structure mapping as step 6, "eventually...
  not scheduled" — v1 is deliberately the eight-feature deterministic
  layer plus the two global metrics, nothing structure-specific.
- Proper nouns, already excluded from Spelling's scoring, are excluded from
  Grammar's scanning too — no agreement judgments on names.
- Register-driven, plausibly-intentional non-standard forms (informal
  contractions, deliberate fragments) default to not-flagged when genuinely
  ambiguous, rather than building intent-detection for this in v1.

## Unit of error — settled

**Word/local-agreement level — confirmed, not attempted-structure level.**
Refined by doc 28's actual build order, which is more specific than a
binary choice:

1. **Global, sentence-level**: errors/100 words, error-free sentence % —
   raw counts, no feature categorization needed at this layer.
2. **Feature-level, underneath the global counts**: the eight
   deterministic checks above, giving diagnostic distribution.
3. **Deferred to Accuracy v2** (doc 28 step 5, after Tier 2's T-unit
   parsing is calibrated): errors/T-unit, error-free T-unit % — sentence
   is v1's unit, T-unit is v2's, and v2 is explicitly gated on Tier 2
   being trustworthy first.
4. **Deferred indefinitely** (doc 28 step 6, "not scheduled"):
   attempted-vs-landed EGP-structure mapping — the harder, per-family
   attempt-recognition problem the structural finding above describes.

## What's settled vs. still open

**Settled**: error-free definition; the input model (raw text, paired
interpretation, per doc 27); the reconciled taxonomy; both cascading-error
rules; all four overlap rules; the structure-specific-family exclusion;
unit of error, with doc 28's actual phasing.

**Still open**:

1. Whether to act on doc 27's build-priority reprioritization
   (Repertoire → Accuracy → Complexity) now, or finish Tier 1/2 Metrics
   work already in flight first — doc 27 explicitly leaves this as your
   call, not a decision either advisory document makes. (Doc 28's revised
   sequence assumes Accuracy is next, but doc 28 also says explicitly:
   "Not yet acted on — still your call.")
2. Whether Revision 3 now fully matches docs 26–28 — checked directly this
   time, not reconstructed from paraphrase, but worth a final read-through
   on your side before treating it as signed off, since these are dense
   documents and a subtler point could still have been missed.

No build authorization sought or assumed.
