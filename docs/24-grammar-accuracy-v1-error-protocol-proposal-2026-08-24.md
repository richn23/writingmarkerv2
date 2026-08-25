# Grammar Accuracy v1: error-counting protocol — investigation + proposal

**Revision 2** (25 Aug 2026). Investigation and proposal only — still no
code written. Revises the original version below at the requester's
instruction, to: state an explicit "error-free" definition, reconcile the
feature-family taxonomy against the edit-type taxonomy, and restate the
overlap/cascading rules as settled rather than open. Responds to a prompt
referencing `claude_21-grammar-full-spec`, `claude_22-grammar-spec-
amendment`, and `claude_23-grammar-error-protocol-sequence` (all 24 Aug
2026), plus a follow-up asserting doc 23 "wasn't in the repo yet [but] now
that it is."

## Doc 23 (and 19, 20c, 22) still do not exist in this project

Checked again immediately before this revision, fresh: no `claude_19`/
`claude_20`/`claude_21`/`claude_22`/`claude_23` file, and no
`grammar-metrics`/`tier`/`calibration` file, anywhere in the repo, under any
name or numbering. This project's own `docs/19` and `docs/20` are unrelated
pre-existing files (a coverage-display investigation and a spelling-error-
rate investigation, both from before this brief existed) — not the "Tier 1
proxy metrics" or "calibration protocol" documents referenced. This is the
same pattern as the earlier "LENS fact-finding response," "Doc 16," and the
original claude_21/22/23 references: the advisory session's own document
numbering does not correspond to anything saved into this repo, and the
belief that doc 23 has since "landed" here does not hold up against a
direct check.

**What this revision is actually built from**, since doc 23's real text is
still not available to me: the specific content pasted directly into the
follow-up instruction — the category list ("subject-verb agreement, verb
form, tense, article/determiner, number, pronoun, preposition, word
order"), the "error-free" requirement, and the reconciliation direction
("feature-family as the primary category with edit-type as a
sub-classification") — plus everything Revision 1 already verified against
the actual code. Where this revision states something as a firm rule below,
that firmness is this document adopting the instruction's own direction,
not independent confirmation against doc 23's text, which I still have not
seen. If doc 23 exists somewhere outside this repo, pasting its actual text
would let this be checked properly rather than reconstructed from category
names and paraphrase.

## Investigation 1: how Spelling's taxonomy actually draws its lines

Read `api/_intent/spelling_score.py` (as instructed, read-only) plus its
upstream category source, `api/_intent/review.categorise()`, and where
`real_word` gets set in `api/_intent/layer.py` — the scoring file alone
doesn't show *how* a token lands in a category, only what happens once it
has.

**Categories, as actually built** (not as docs/02 originally named them —
see the drift note below): `minor_slip` (one edit, same sound —
"beautifull"), `boundary` (run together/split — "alot"), `phonetic`
(2+ edits, same sound — "skooi"), `wrong_word` (a *different real word* —
"bast" for "based"), `unrecoverable` (no confident reading), `proper_noun`
(excluded from scoring entirely).

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
unrecoverable." The as-built code has six categories under different names,
and critically, `wrong_word` — a real-word-for-real-word confusion — isn't
clearly anticipated by that three-way sound/structural/boundary framing at
all. If Grammar's error taxonomy gets designed against docs/02's original
prose description rather than the actual shipped categories, it will very
likely re-claim `wrong_word` cases as grammar errors without realizing
Spelling already fully scores them — a live double-counting risk, not a
hypothetical one.

## Investigation 2: is raw (pre-correction) text available, separate from the interpretation?

**Yes, confirmed directly in `api/score.py`'s `detail()`:**

- `out["text"] = result["text"]` — the raw, as-written learner text.
  Nothing applied to it at all.
- `out["corrected_sample"] = result.get("corrected_sample")` — the
  "approved interpretation": spelling-only corrected (per
  `_intent/layer.py`'s own docstring: "Nothing is inserted, no grammar is
  touched, and no word is upgraded"). This is what Grammar Detected/Range
  already reads (`_grammar_source_text()` in score.py, falling back to
  `_corrected_text()` when the intent layer didn't run).
- `out["corrected_text"]` — a third, always-present field: the
  deterministic-only correction, used as `corrected_sample`'s own fallback.

Both raw and interpretation text are already siblings on the same response
object, with no new plumbing required for Accuracy to read both. Confirmed
by reading the field assignments directly, not inferred.

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

This means Accuracy cannot be built as "judge what Range already finds" —
it needs its own, separate attempt-recognition logic that can recognize a
malformed attempt as an attempt, which is a materially different and
harder problem than Range's correctly-shaped pattern matching. This is
almost certainly *why* Accuracy was scoped out of the original grammar
brief as "not built yet," and it directly shapes the "unit of error"
question below — worth surfacing explicitly before any protocol gets
signed off on, since it changes what "v1" can realistically mean.

## "Error-free" — explicit definition

**"Error-free" means zero grammar errors specifically**, per the taxonomy
below. A sentence carrying a spelling slip or a punctuation issue but no
grammar error is error-free. This is not a looser reading of "clean
writing" — it is a statement about which dimension a given metric is
measuring, and it must hold both in the metric's own definition and in
whatever UI label surfaces it (never "error-free" unqualified, always
"grammatically error-free" or equivalent, wherever it's shown to a marker).

This falls directly out of Overlap Rule 1 below, not as an extra check
layered on top: if a token has already been claimed by Spelling, Grammar
Accuracy never independently evaluates it, so a spelling slip can never be
double-counted as a grammar error and can never cost a sentence its
error-free status under this definition. The definition is only as reliable
as that rule being airtight in the actual implementation — a gap there
would silently make "error-free" mean something narrower or broader than
stated here.

## Category boundaries — reconciled: feature-family primary, edit-type sub-classification

Two taxonomies were sitting side by side unmerged: doc 23's eight
feature-family categories (subject-verb agreement, verb form, tense,
article/determiner, number, pronoun, preposition, word order) and doc 02's
four edit-type categories (missing / wrong-form / added / wrong-order).
Combined as instructed: **feature-family is the primary category a marker
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

Two things worth stating plainly rather than smoothing over:

- **Word order is structurally exclusive**: by definition, a word-order
  error IS a misordering, so "wrong-order" is effectively the only
  applicable edit-type for that feature-family. The other three edit-types
  don't meaningfully apply there.
- **Comparatives/superlatives ("more better") and several other EGP
  families Range already detects (passive voice, relative clauses,
  reported speech, conditionals, modals) do not map cleanly onto doc 23's
  eight features.** This is either an intentional scope decision — doc 23's
  eight categories are the classic "core" morphosyntactic error set from
  error-analysis research, and structure-specific errors (passive
  formation, relative clause formation) may be deliberately out of v1's
  scope — or a gap in what's been pasted here versus doc 23's full list.
  I can't tell which from what's available; flagging rather than guessing.
  If it's the former, this needs to be stated as an explicit exclusion (see
  below); if the latter, the missing feature categories need to be shared.

Severity stays as Revision 1 proposed: binary-ish, "meaning survives or
breaks" (doc 02), distinct from Spelling's continuous weighted scale, since
the two measure genuinely different things (orthographic cost vs.
communicative damage) and forcing Grammar onto Spelling's numeric model
would blur that.

## Overlap rules with Spelling — stated as rules, not recommendations

1. **Any token Spelling has already claimed as an error, under any of its
   six categories, is out of scope for Grammar Accuracy on that token.**
   Accuracy reads from the already-resolved interpretation and never
   independently re-evaluates a token Spelling has scored. This is the rule
   the "error-free" definition above depends on.
2. **Homophone/confusable real-word pairs (Spelling's `wrong_word`
   category) stay entirely Spelling's**, even where the confusion lands on
   a grammatical category by coincidence (possessive vs. contraction:
   "its"/"it's"). Grammar Accuracy treats the interpretation layer's
   resolved word identity as given and only judges whether that word is
   used correctly — it never re-litigates which word was intended.
3. **Morphological over-regularization ("goed," "runned," "comed") is
   Grammar's domain, not Spelling's.** Spelling's form-test-gated corrector
   structurally can't reach these (edit distance/phonetic similarity to the
   correct irregular form is normally too large to pass `form_test`), so
   they fall through as `unrecoverable` or unresolved in Spelling rather
   than being claimed by it — there is no overlap to adjudicate, only a gap
   Spelling leaves that Grammar fills. This is exactly why raw-text access
   (confirmed available in Investigation 2 above) matters for Accuracy: it
   needs to examine what the learner actually wrote, not only the
   spelling-corrected reading, to catch this class at all.
4. **Punctuation stays its own dimension** (doc 02) — counted in neither
   Spelling's nor Grammar Accuracy's error tallies.

## Cascading-error treatment — stated as a rule

**Count by root cause, not by surface symptom.** One underlying mistake
that could be described under more than one feature-family or edit-type
(a missing 3rd-person "-s" is describable as both a Verb form error and a
Subject-verb agreement error) counts once, attributed to the single most
specific applicable feature-family, not once per possible description.

Mechanically: two candidate errors merge into one when they share a token
span and describe the same grammatical relationship (the verb and its
subject, in the example above) — implemented as a span-overlap check at
merge time, not as a rule requiring the detector itself to only ever
propose one description per token. This is stated as the rule to build
against; it has not been validated against real error data, since no
Accuracy code exists yet to validate it with.

## Exclusions — stated as rules

- The 16 EGP families Range already defers stay deferred for Accuracy too.
  If a structure isn't reliably detectable at all, judging attempts at it
  is premature. The 2 partial families keep their existing honest
  detects/misses framing for Accuracy as well.
- Proper nouns, already excluded from Spelling's scoring, are excluded from
  Grammar's scanning too — no agreement judgments on names.
- Register-driven, plausibly-intentional non-standard forms (informal
  contractions, deliberate fragments) default to not-flagged when genuinely
  ambiguous, rather than building intent-detection for this in v1.
- Structure-specific EGP families that don't map onto doc 23's eight
  feature categories (see the table note above) are excluded from v1
  pending clarification of whether that's doc 23's intent.

## What's now settled vs. still open

**Settled by this revision** (per the explicit instruction to firm these
up): the error-free definition; the reconciled feature-family/edit-type
taxonomy; both overlap rules with Spelling, including the
over-regularization boundary (now stated as Grammar's domain, not left
open); the cascading-error merge rule; the four exclusions.

**Still open, unresolved by anything provided so far**:

1. **Unit of error** — (a) attempted-structure level, extending Range's own
   family model (larger build, needs new per-family attempt-recognition
   logic), or (b) word/local-agreement level (smaller v1, doesn't map onto
   Range's families the same way). Revision 1's recommendation of (b)
   stands; nothing in this revision's inputs addressed it.
2. **The structure-specific-family gap** above (comparatives, passives,
   relative clauses, etc. not mapping onto the eight listed features) —
   intentional v1 scope limit, or missing categories from doc 23's actual
   list?
3. **Whether this document, even now, matches doc 23's real content.**
   Revision 2 is built from what was pasted into the follow-up instruction
   plus Revision 1's own investigation — not from doc 23's text, which
   remains unseen. If doc 23 exists outside this repo, sharing its actual
   content would let this be checked directly rather than reconstructed.

No build authorization sought or assumed.
