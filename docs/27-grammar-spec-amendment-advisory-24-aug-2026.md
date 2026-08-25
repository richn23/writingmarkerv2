# Amendment to claude_21-grammar-full-spec-24-aug-2026.md, 24 Aug 2026
Based on external CAF-literature review of that spec. Doc 21 stands as
the base document — this amendment corrects one architectural point and
tightens several others. Read together, this amendment takes precedence
wherever it conflicts with doc 21.
## The one material architectural change — Accuracy needs raw text, not approved interpretation
**Doc 21 §1 currently states:** "all three Grammar sections read from the
same approved interpretation text... never raw as-written text." **This
is wrong for Grammar accuracy specifically**, confirmed by the external
review and, on reflection, already contradicted by a principle this
project locked in back in doc 06:
> "The written+intended pair pattern (`spelling_score.py`'s `score()`
> takes both fields) is the template every future construct's scoring
> should copy, not reinvent."
Spelling scoring already works exactly this way — it scores what was
*written* against what was *intended*, because that gap is the entire
object being measured. Grammar accuracy is the same shape of problem: if
it read the approved (corrected) interpretation text, it would be scoring
the correction pipeline's grammar, not the learner's. Concretely, for
"Yesterday I go shopping and buy two shirt" → corrected to "Yesterday I
went shopping and bought two shirts" — Accuracy has to see `go→went`,
`buy→bought`, `shirt→shirts` as the actual errors under measurement;
scoring the corrected sentence would show zero errors and measure
nothing.
**Corrected input model, replacing doc 21 §1's blanket statement:**
| Section | Reads from |
|---|---|
| Grammar detected (Repertoire) | Approved interpretation text |
| Grammar Metrics (Complexity) | Approved interpretation text |
| Grammar accuracy | **Original/raw learner text**, with the approved interpretation available as a reference/aid, same written+intended pairing Spelling already uses |
This also means Grammar accuracy needs its own explicit data contract
(raw text + corrected text as a pair) — not a variant of the same single
text field the other two sections share. Flag this for whenever Grammar
accuracy actually gets built; no code exists yet, so nothing needs
correcting today, but the eventual build brief must not default to reusing
Repertoire/Complexity's approved-text-only input.
## Soften: "below B1, complexity isn't informative" → not yet demonstrated reliable/useful
Doc 21 §3's framing was too absolute. Replace with: at lower proficiency,
complexity measures tend to be **less diagnostically informative than
accuracy/repertoire, and their usefulness depends on task and text
length** — not that the underlying construct has no validity below B1.
The B1 display gate itself is unchanged and still justified — reframe it
as a product-validity decision ("we haven't yet demonstrated these
metrics are sufficiently reliable and useful below this level"), not a
claim that the construct itself is invalid there. This is a stronger,
more defensible claim and costs nothing to adopt.
## Reorganize Tiers 2/3 into one "Parsed Syntactic Complexity" tier
Doc 21 currently has Tier 2 (clause metrics) and Tier 3 (phrasal/nominal,
flagged as a new gap) as separate. Collapse into one tier, matching how
the literature actually structures syntactic complexity — global,
clausal, and phrasal as three dimensions of the same construct, not
separate tiers:
**Tier 1 — parser-independent** (unchanged from doc 21): mean sentence
length, structure diversity, proxy subordination/coordination, passive
frequency, modal density.
**Tier 2 — parsed syntactic complexity** (merges old Tier 2 + Tier 3),
three dimensions from the same parse:
- *Global:* mean T-unit length
- *Clausal:* clauses/T-unit, dependent clauses/clause, complex T-unit
  ratio
- *Phrasal:* mean clause length, complex nominals/clause, complex
  nominals/T-unit, mean noun-phrase length, coordinate phrases/clause
This isn't just relabeling — it confirms what doc 21 already suspected:
phrasal metrics are a same-build addition to the clause parser work
(docs 20/20b/20c), not a separate future task. The calibration protocol
in doc 20c applies to all of Tier 2 together, not to clause metrics
first and phrasal metrics as a later pass.
Later research-backlog candidates, not v1: fine-grained nominal features
(adjective premodification, prepositional postmodification, participial
modification, relative-clause postmodification), and weighted clause
ratio — noted as validated in the literature but not added just because
it exists; goes on the shortlist for whenever real corpus validation
happens.
## Reprioritize: build order vs. display order are different things
**Display order stays as designed:** Repertoire / Complexity / Accuracy,
matching the three collapsibles already built/spec'd.
**Build/implementation priority changes:** Repertoire → **Accuracy** →
Complexity. Reasoning, and it's a real risk, not just a preference: a
learner producing ambitious but unstable syntax could visually look more
grammatically capable than one producing simpler, controlled language, if
a rich Complexity panel ships before any Accuracy signal exists to
contextualize it. Doc 21 §4 already flagged accuracy measures as most
established precisely at the levels (A1–A2) currently uncovered — this
sharpens that into an explicit priority call, not just a signal to note.
**Not yet decided:** whether to act on this reprioritization now (i.e.
pause Metrics/parser work from docs 19–20c and scope Accuracy next) or
finish what's already spec'd first. Flagging for your call, not deciding
here.
## Scope Grammar accuracy smaller than the LENS design's full version
Doc 21 §4 pointed at LENS's `STUDENT_PRODUCTION_ANALYSER_DESIGN.md` as
the eventual shape. Recommendation: don't start there. Build order,
smallest-first:
1. Global measures: errors/100 words, error-free sentence %
2. Once T-unit parsing (Tier 2 above) is trustworthy: errors/T-unit,
   error-free T-unit %
3. Deterministic error-family checks underneath those global numbers:
   subject-verb agreement, verb form, tense, article/determiner, number,
   pronoun, preposition, word order — giving diagnostic distribution
   without solving the harder problem of mapping every malformed attempt
   back onto a specific EGP structure
This explicitly defers, not abandons, the full attempted-vs-landed
EGP-structure mapping LENS's design doc describes — that remains the
eventual goal, just not the v1 scope.
## What's unchanged
The three-construct separation itself (Repertoire/Complexity/Accuracy,
none independently "the grammar level") is confirmed as the strongest
part of the design by the external review — no change there. Everything
in doc 21 §2 (Grammar detected — port, gate fix, two-pass split,
framework decision) is unaffected by this amendment. The `'d`-contraction
bug (doc 16) remains open, unaffected.
## Updated status summary (replaces doc 21 §7's last three rows)
| Piece | Status |
|---|---|
| Grammar Metrics Tier 1 | Spec'd, build pending confirmation |
| Grammar Metrics Tier 2 (parsed — global/clausal/phrasal combined) | Spec'd (docs 20/20b/20c + this amendment's reorganization), not built |
| Grammar accuracy | Scope narrowed (this amendment), input model corrected (raw text, not approved interpretation), build-priority raised above Complexity — pending your decision on whether to act on the reprioritization now |
