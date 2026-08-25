# Second amendment to claude_21-grammar-full-spec-24-aug-2026.md
(on top of claude_22-grammar-spec-amendment-24-aug-2026.md), 24 Aug 2026
Adds one prerequisite to Grammar accuracy v1, and adopts a revised implementation sequence. Read alongside doc 21 and the first amendment (doc 22) — this doesn't replace either, it adds to doc 22's "scope smaller" section.
## New prerequisite: Grammar error counting protocol, before any Accuracy v1 code
Same discipline already required for Tier 2's clause/T-unit definitions (doc 20c) — define the unit before counting it, don't let an implicit library/model default decide what "error" means. Must be written and confirmed before Accuracy v1 implementation starts, covering:

* Unit of error — what counts as one countable error (a single wrong token? a single wrong dependency relation? a whole malformed phrase as one unit?).
* Category boundaries — the error-family list from doc 22 (subject-verb agreement, verb form, tense, article/determiner, number, pronoun, preposition, word order) needs each category's edges defined precisely enough that two different errors don't get double-counted across categories, and an ambiguous case has a stated home rather than an implicit one.
* Grammar/Spelling boundary — specific to this project, not generic. This system already has a working Spelling taxonomy (doc 10: correct/minor_slip/boundary/phonetic/wrong_word/unrecoverable/proper_noun). A form like "goed" for "went" sits on the seam between the two — wrong tense formation expressed as nonstandard spelling. The protocol must state explicitly which construct owns cases like this, so the same error isn't silently double-counted across Grammar and Spelling, or silently uncounted in both. This needs its own explicit rule, not an assumption that the two taxonomies will naturally sort themselves out.
* Overlap rules more generally — beyond the Spelling boundary, whether a single malformed span can trigger more than one Grammar error category at once (e.g. a wrong-tense wrong-agreement verb), and if so whether that counts as one error or two.
* Cascading-error treatment — if an early error (e.g. a wrong tense established mid-sentence) makes later, internally-consistent forms look "wrong" relative to standard English even though they're consistent with the writer's own (incorrect) pattern, does that count as one root error or multiple surface errors? State the rule; don't let it fall out of however the counting code happens to iterate.
* Exclusions — what's explicitly out of scope for error counting (e.g. stylistic register choices that aren't actually ungrammatical, deferred structure families where no reliable "correct" baseline exists to compare against).

## Explicit definition required: "error-free" for error-free sentence %
Must state precisely, before implementation: error-free means no grammar errors, full stop — not "no errors of any kind." A sentence with a spelling mistake or a punctuation slip but zero grammar errors still counts as error-free for this metric. This needs to be stated plainly in the metric's own definition and in whatever UI label surfaces it, so it isn't read as a general correctness score.

## Revised implementation sequence (supersedes doc 22's priority section)

1. Repertoire — already built.
2. Accuracy v1 — error counting protocol (this doc) written and confirmed first, then: error taxonomy, errors/100 words, error-free sentence %, deterministic error families (subject-verb agreement, verb form, tense, article/determiner, number, pronoun, preposition, word order).
3. Complexity Tier 1 — parser-independent proxy metrics (doc 19).
4. Parsed Syntactic Complexity + calibration — Tier 2, global/clausal/phrasal combined (doc 22's reorganization), full calibration protocol (doc 20c) before any threshold ships.
5. Accuracy v2 — errors/T-unit, error-free T-unit % (needs Tier 2's T-unit parsing to be calibrated and trustworthy first, hence sequenced after step 4).
6. Eventually — attempted-vs-landed EGP-structure mapping, the full scope from LENS's original design doc. Not scheduled.

This sequence's logic: meaningful grammar evidence gets surfaced across the proficiency range earlier (Accuracy v1 doesn't wait on parser calibration), while the harder parsing work stays properly validated rather than being rushed just because Complexity was next in the UI's visual order. Display order in the UI remains Repertoire / Complexity / Accuracy throughout, unaffected by this build sequence, per doc 22.

## Status
This amendment is treated as the current authoritative build sequence, superseding doc 22's priority section specifically (doc 22's other content — the raw-text input correction, the tier reorganization, the softened below-B1 claim — is unaffected and still stands). Not yet acted on — still your call whether to begin step 2 now or continue whatever's currently in flight from docs 19-20c first.
