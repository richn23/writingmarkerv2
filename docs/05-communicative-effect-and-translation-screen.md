# The Communicative Effect and Translation Screen — Specification

## Purpose

This is screen 3 in the build order (after the landing screen, after the
Question + sample input screen, before any dimension score). It does two
related jobs:

1. **Translation** — surfaces what the model believes the student actually
   meant, across vocabulary, grammar, and overall message, before any of that
   belief is allowed to feed a score.
2. **Communicative Effect** — produces one holistic, CEFR-anchored read of
   how easy the script was to understand as written.

Both exist for the same reason: every dimension score downstream depends on
some reading of the text, and the one place a model — not a rule — makes a
judgment about that reading has to be visible and overridable before it's
trusted with anything. This screen is that checkpoint.

## Position in the flow

```
1. Landing / instruction screen        (built)
2. Question + sample input screen      (built, task type/CEFR fields pending)
3. Communicative Effect & Translation  (this document)
4. Dimension-scoring sections           (read FROM this screen's output,
                                          not from raw input)
5. Evidence screen + weighting
6. Final score
```

Every later dimension section consumes the ONE approved interpretation
rather than independently re-asking a model what the learner meant. That
prevents Vocabulary silently interpreting a passage one way while Grammar
interprets the same passage another way.

**Important correction (Richard, 19 Aug 2026): this is not "dimensions read
from this screen instead of raw input."** Some constructs need the raw
as-written text as well as the approved interpretation, not instead of it.
Concretely, there are three access patterns, not one:

1. **Raw only.** Communicative Effect (below) must NOT see the approved
   interpretation — the whole point is measuring reader burden on the
   unedited text, and reading the corrected version would launder away the
   exact friction it exists to capture.
2. **Raw + approved interpretation.** Spelling, Grammar Accuracy, Grammar
   Range, Punctuation. These need the *pair* — what was written and what was
   intended — to compute a deviation, an error type, a severity. This is
   already how the one built construct works: `spelling_score.py`'s
   `score()` takes records carrying both `written` and `intended` fields and
   scores the gap between them, not `intended` alone. Grammar's eventual
   version should copy this same shape.
3. **Approved interpretation only.** Constructs concerned with what was
   communicated rather than the error surface — Content Quality plausibly
   sits here, reading the intended message rather than the literal text.

So the rule is: **the interpretation layer prevents re-interpretation, it
does not replace the source text.** Each construct receives whichever of
raw / approved-interpretation / both its own construct actually needs — never
a silent default of "everything reads from here now."

## What gets translated: three hypothesis types

The model produces three kinds of "here's what we think you meant"
hypotheses from the same script. They are not interchangeable — two are
narrow and checkable, one is open-ended — and the screen should keep that
distinction visible, not flatten it into one undifferentiated list.

### 1. Intended vocabulary

*Quant-adjacent, constrained.* Given a spelling the deterministic corrector
couldn't resolve on its own, the model proposes which GSE-list word it was
reaching for. The candidate set is bounded (the GSE reference list), so the
guess is checkable against that structure the same way a dictionary lookup
is checkable.

Status: **built.** `api/_intent/client.py` + `spelling_score.py` already do
this. Every proposal — accepted and rejected — is already surfaced
(`intent_audit` in the current code), which is the right pattern to carry
onto this screen unchanged.

### 2. Intended grammar

*Quant-adjacent, constrained.* Given a malformed clause, the model
hypothesises which EGP structure it was attempting (e.g. "this looks like an
attempt at third-person present simple, missing the -s"). The candidate set
is bounded — the known EGP structure inventory — the same shape of
constraint as vocabulary's GSE list.

Status: **not built anywhere.** This is the real shape of the still-missing
Grammar detector: not a standalone classifier, but an intent-inference step
structurally parallel to the spelling corrector. Only once this hypothesis
exists can deterministic code score accuracy (was the realisation correct,
what error type, what severity) and range (breadth of structures attempted).

### 3. Intended communicative message

*Qual, open-ended.* What the writer was actually trying to say, at the level
of the whole script or a passage — not a specific word or structure. There is
no bounded reference set to check this against, unlike the two hypotheses
above. This is a genuinely different kind of claim, and the screen should
present it that way: not "accept/reject this specific proposal" but "here is
a holistic read, judge it as a whole."

## The Communicative Effect metric

The vital human-marker question this answers: **do we understand the
message, and is it clear?** CEFR's own level descriptors are substantially
built around this at the main bands — B1 "can produce simple connected
text," C2 "clear, smoothly-flowing text" — arguably closer to what a CEFR
band is actually trying to capture than granular per-error counts are.

**Specification:**

- **Tag:** qual, but CEFR-anchored — a second axis from the CEFR-rigor tag
  already used elsewhere in the construct model. Being a judgment call
  doesn't mean it's ungrounded; it means it isn't computed from a fixed
  reference inventory the way vocabulary or grammar matching is.
- **Not a seventh dimension.** Anchored as supporting evidence for
  **Coherence** (the existing dimension already marked "inherently
  judgment-based, no CEFR ladder possible"), secondarily for Content Quality
  and Register. Feeding it in as a free-floating eighth score would risk the
  same double-counting problem that made the old Sentence Complexity stub
  unusable.
- **Evidence source: the as-written text, specifically, and ONLY the
  as-written text.** Not the corrected version, not the intent-resolved
  version, not even the approved interpretation from this same screen. The
  entire point is measuring reader burden — how much effort the actual,
  unedited script demanded — and letting this judgment see any corrected
  reading would hide exactly the friction it exists to capture.
- **Reporting form: descriptor-anchored, NOT a CEFR band or classification.**
  Corrected 19 Aug 2026 (Richard) — "Communicative Effect: B1" reads as an
  independent proficiency classification sitting next to Coherence, which
  the construct model explicitly says has no clean CEFR ladder. That's a
  construct-validity problem, not just an imprecision. The fix: anchor the
  judgment to descriptor language instead of a band label. For example:

  > **Communicative Effect: consistent with B1 expectations.**
  > The main message is clear and connected. Errors occasionally interrupt
  > the flow but generally do not prevent understanding.

  rather than a bare "Communicative Effect: B1." The former says the reader
  experience *resembles the expectations represented in the B1 descriptors*.
  The latter sounds like a second, independent CEFR measurement — which this
  is explicitly not meant to be.
- **Built, but not yet score-driving.** Corrected 19 Aug 2026 (Richard): this
  is real, working functionality — a live OpenAI call via `api/_intent/client.py`
  — not a mockup, and the screen should not label it "Experimental." It is
  still excluded from the score until validated, but that's a scoring-pipeline
  fact, not a build-status one — say "AI-generated, not yet score-driving,"
  not "Experimental." The sign-off condition is specific and falsifiable: test
  whether it predicts real human markers' actual Coherence judgments on the
  same scripts. If it correlates well, there's an empirical basis to fold it
  in as real supporting evidence. If it doesn't, that's a genuine finding —
  learned without contaminating the scoring model in the meantime. This
  matches the document → build → map → test → sign-off cycle already
  governing every other section of this build.

## Screen behaviour

**Communicative Effect always renders.** Every script has some reader
experience to describe, even a flawless one, so this isn't contingent on
errors being present.

**The vocabulary and grammar translation reviews are conditional.** If
nothing in the script needed a judgment call — no ambiguous spelling, no
malformed structure — there's nothing to review, and the screen should skip
straight through rather than show an empty checklist. An empty "review"
step reads as process theater and trains people to stop looking.

**Different interaction models for different hypothesis types.** Vocabulary
and grammar hypotheses are individually accept/reject/override-able, the
same pattern already proven for spelling (`intent_audit`, including
rejections, visible). The communicative-effect judgment isn't a list of
discrete proposals to accept or reject one at a time — it's a holistic read
a marker either agrees with or flags as off, at the level of the whole
script.

## What exists vs. what's new

| Piece | Status |
|---|---|
| Vocabulary translation (intent layer) | Built, in `api/_intent/` |
| Grammar translation (intent-inference for EGP structures) | Not built anywhere — the real scope of the "missing Grammar detector" |
| Communicative message / Communicative level / Effect on reader | Built 19 Aug 2026 — `communicative_effect()` in `api/score.py`, a live OpenAI call reusing `api/_intent/client.py`'s proven `call()` helper. Degrades honestly: shows a labelled worked example when no sample has been scored, an explicit "Not available — {reason}" when a sample was scored but no key is configured, and real generated content otherwise. |
| Shared screen surfacing all four together | Built (this document's screen) |
| The "written + intended" pair pattern for downstream scoring | Proven in production for Spelling (`spelling_score.py`) — the template to copy for Grammar, not a new idea to design |

## Grammar worked example (illustrates the corrected architecture)

Learner writes: *"She go school every day."*

The interpretation layer proposes: intended structure — third-person present
simple; EGP candidate — [mapped structure]; `go` intended as `goes`. A marker
(or the model, where confident enough) accepts the proposal — this becomes
part of the approved interpretation.

The deterministic grammar engine then receives BOTH the raw clause and the
approved interpretation, and produces:

- Range evidence: attempted structure at [level] — the attempt counts toward
  breadth regardless of correctness.
- Accuracy evidence: incorrect realisation, error type = missing inflection,
  severity = meaning preserved.

At no point does the model say "grammar = 44." It says "this appears to be
an attempt at structure X." The scoring machinery — deterministic, reading
both the raw form and the approved interpretation — does the rest. Same
principle already governing Vocabulary and Spelling, applied to the one
construct that doesn't have it yet.

## The corrected pipeline, stated once

```
Original text
      ↓
Shared Interpretation Layer  →  intended vocabulary
                              →  intended grammar
                              →  intended message
      ↓
Approved interpretation / evidence object
      ↓
Each construct receives: raw text, and/or approved interpretation,
                          whichever it actually needs (see the three
                          access patterns above)
      ↓
Evidence  →  Construct judgement  →  CEFR band  →  Within-band position
                                                  →  Reporting score
```

This screen handles **interpretation**, not **scoring**. That boundary is
the most important thing this document exists to protect.

## Screen 3 layout — finalized hierarchy (Richard, 19 Aug 2026)

Top to bottom, agreed order, and the order the built screen follows:

1. **Actual text / intended text, side by side**, with a disclaimer that the
   intended reading is AI-generated. This is the readable headline view of
   the underlying interpretation — it must sit ON TOP OF the granular,
   per-correction audit structure already proven for spelling (each change
   individually inspectable: what it was, what it's read as, why, confidence,
   accept/reject state), not replace it with an untraceable before/after
   diff. Losing that granularity would be a step backward from what's
   already built.
2. **Basic script statistics — word count, sentence count, sentence length,
   paragraph count.** Pure quant, code-based, zero AI involvement — computed
   directly from the raw text. Placed here, near the top, specifically
   because it's the most trustworthy, zero-ambiguity content on the screen:
   no AI disclaimer, no accept/reject control, no "experimental" label — it
   should visually read as a different KIND of thing from everything below
   it (fact, not judgment), not a lesser version of the same thing. Reuses
   the same metric set already reviewed in the Evidence Metrics proposal
   (18 Aug 2026) — sentence count, avg sentence length, paragraph count were
   three of that spec's nine; word count already has its own home as a
   Task Achievement metric. This screen's word count is the same raw fact
   Task Achievement later judges against the task's expected range — computed
   once, reused, not recomputed twice. ⚠️ Caveat carried over from that
   review: sentence length shares the same length-confound risk vocabulary's
   fitted model hit (longer isn't better) — fine as raw evidence, don't let
   it imply quality on its own.
3. **Summary of the learner's message, as bullet points.** The natural
   display form for the "intended communicative message" hypothesis — the
   most open-ended, least constrained of the three, so it carries the
   clearest hedge on the screen. Must be marker-correctable, not just
   informational: if this feeds Content Quality downstream (which reads the
   approved interpretation, not raw text, per the access-pattern rule
   above), a marker's "no, that's not what they meant" has to actually
   propagate, the same way a word-level correction does.
4. **Communicative level** — the framework-anchored read, for assessors who
   read CEFR fluently. This is the field with the construct-validity risk
   already fixed above: it must render as a descriptor sentence
   ("consistent with B1 expectations...") and never as a bare "Level: B1"
   badge, or it silently becomes a second, independent proficiency
   classification sitting next to Coherence, which the construct model
   explicitly says isn't measurable that cleanly. Grounded in the Writing row
   of the official CEFR Self-Assessment Grid (uploaded 19 Aug 2026).
5. **Effect on reader** — a plain-language companion read, for anyone who
   doesn't read CEFR (a class teacher, a parent, an admin) — e.g. "readable
   with occasional re-reading needed" rather than a band reference. Doesn't
   carry the same construct-validity risk as #4, since it never claims CEFR
   grounding, but still needs the same AI-generated/not-yet-score-driving
   label (never "Experimental" — see the correction above).
6. **Vocabulary review** — renamed from "evidence" 19 Aug 2026, deliberately.
   "Evidence" is reserved for the deterministic, scored output (GSE bands,
   percentiles) that only exists once the Vocabulary dimension section does
   its own work. This is the individually accept/reject/override-able list
   of intended-vocabulary hypotheses — a review of proposals, not a score.
7. **Grammar review** — same naming logic as #6, for intended-grammar
   hypotheses. Not built anywhere yet (see the grammar worked example
   above).
8. **Other reviews** — placeholder, not yet defined.

**The AI-disclaimer is a screen-level requirement for everything EXCEPT the
basic script statistics (#2), which need no disclaimer at all — they're not
model output.** Components 3-5 (summary, communicative level, effect on
reader) need the disclaimer as much as the side-by-side text does — arguably
more, since they're less constrained.

**Not yet resolved by this layout:** where the accept/reject interaction
actually lives for each hypothesis type. The layout above describes what's
displayed; it doesn't yet specify the click targets, override UI, or how an
override on the summary bullets or the communicative-level read gets
recorded and propagated. Needs a pass before this is fully build-complete —
the current build shows all data read-only (accepted/rejected state is
displayed, not yet editable from this screen).

## Highlighting requirements (Richard, 19 Aug 2026)

Two additions, both extensions of visual language already proven in the
existing app rather than new invention.

**Highlight changes, differentiated by kind.** The current app already does
this for spelling — strikethrough on the original, colour on the correction,
in both the word chips and the audit table. Carry that same language onto
the actual/intended side-by-side view, and make vocabulary corrections and
grammar corrections visually distinct from each other, not one undifferentiated
"this was touched" colour — reinforces the three-hypothesis-type distinction
instead of flattening it. Built: vocabulary corrections render in orange
(the app's existing "corrected" colour), a reserved violet is defined for
grammar corrections once that layer exists, and unresolved words render in
a third, amber-brown colour, distinct from both.

**Highlight sentences that can't be interpreted.** This is a construct-honesty
requirement, not just a display nicety. The system already has a word-level
version: `unrecoverable` in the spelling severity table ("no confident
reading"). This extends the same idea one level up — a sentence where the
interpretation layer can't produce a confident guess at all needs its own
visibly distinct THIRD state: not "unchanged," not "successfully interpreted,"
but "attempted and failed." Built at word level, using the engine's real
`abstained` decision (the deterministic corrector's own "won't guess"
signal) — e.g. "bote" in a real test sample. Sentence-level escalation is
not built (see below).

**Downstream consequence:** any construct reading the approved interpretation
for that span must EXCLUDE it from evidence, not guess anyway — same
discipline already used elsewhere (Spelling's `MIN_ATTEMPTED` floor refusing
to score below a minimum sample; the vocabulary evidence caps refusing to let
a handful of words support a level they can't carry). A confident-looking
guess dressed up as an interpretation would be worse than visibly no
interpretation, since it would be indistinguishable from a real one at a
glance.

**⚠️ Not yet decided:** the threshold for when a sentence escalates from
"one word inside it failed" to "flag the whole sentence." A single
unresolvable word in an otherwise clear sentence is a different case from a
sentence whose structure itself has collapsed. Needs a defined rule before
this is build-ready — not specified here. The current build only flags at
word level, deliberately, rather than guessing at a sentence-level rule.

## Open questions, not yet decided

- Whether Communicative Effect needs more than one model pass for
  reliability (a single holistic judgment vs. an ensemble), before real-batch
  testing can say whether one pass is stable enough to trust.
- Exact visual treatment that keeps the constrained hypotheses (vocabulary,
  grammar) visually distinct from the open-ended one (message/communicative
  effect) on the same screen — flagged as a requirement here, not yet
  designed.
- How a marker's disagreement with the communicative-effect read gets
  recorded and whether it feeds back into calibration over time.
- Where the accept/reject interaction lives for each hypothesis type (see
  above) — currently read-only in the built screen.
- The sentence-level "can't be interpreted" escalation threshold (see above)
  — currently word-level only in the built screen.

## Note on scope

Originally written as advisory-only. Superseded 19 Aug 2026: this screen is
now built, following the finalized hierarchy above. Real data is used
wherever it exists (the as-written/intended text pair, the spelling audit,
vocabulary intent proposals, the basic script statistics, and — as of the
second 19 Aug 2026 update — the communicative message summary, communicative
level, and effect on reader, all genuinely generated by a live OpenAI call).

**Corrected 19 Aug 2026 (Richard):** the earlier draft of this note said the
three communicative-effect reads were placeholders. They are not — they're
built, working functionality, wired end-to-end through `api/score.py`. Two
honest, non-placeholder states remain, and both are surfaced explicitly
rather than silently substituted: a worked example (clearly prefixed
"Example:") when no sample has been scored yet, and "Not available —
{reason}" when a sample was scored but the OpenAI call didn't run or failed
(most commonly: no `OPENAI_API_KEY` configured in the environment). Neither
state should be described or labelled as "Experimental" — that word implies
the feature itself is unfinished, when what's actually true is narrower and
more specific: the output isn't yet folded into any score, and its
reliability against real markers hasn't been validated.

**Only Grammar review (component #7) remains an actual placeholder** — there
is no grammar structure-detection layer anywhere in the codebase to call, so
that section still reads "Not built yet, anywhere," which is accurate rather
than optimistic.
