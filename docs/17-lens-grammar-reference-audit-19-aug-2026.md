# LENS grammar-detection reference audit — 19 Aug 2026

Findings from a direct read of four files from a partial upload of the LENS
repo (`language-awareness-pipeline`): `src/lib/grammarDetect.ts`,
`src/lib/production.ts`, `src/lib/analysis.ts`,
`src/app/analysis/production/page.tsx`. Not inferred from the earlier
consolidated docs (`03-consolidated-three-systems.md`,
`02-six-dimension-construct-model.md`) — this supersedes those at the file
level for anything grammar-related, since those were written from
higher-level project summaries, not the LENS source itself.

A full extraction prompt based on these findings was sent 19 Aug 2026 to a
separate session with LENS repo access, asking it to pull the actual
contents of the files listed below as "confirmed to exist" and flag any
drift from this description.

## Confirmed to exist in LENS

1. **`src/lib/egpFamilies.ts`** — not read directly (not in the partial
   upload), but `grammarDetect.ts` imports `rowsForFamily`,
   `ALL_DECLARED_FAMILIES`, `assertDetectorFamilies`, `SHORT_DESCRIPTION`,
   and the `EgpStructure` type from it. This is where the actual EGP
   reference rows get loaded and shaped — the loader-equivalent of what
   handles `gse_vocabulary.json` for vocabulary.
2. **The EGP reference data**: `explorers/structures.json` (45 EGP-keyed
   "Structure Explorer" entries) reported against `grammar_profile.json`
   ("the Cambridge EGP reference," per `grammarDetect.ts`'s own header
   comment) for identity, level, and can-do statements. Real paths not yet
   confirmed — flagged for the extraction session to verify.
3. **`src/lib/taxonomy.ts`** — not read directly, but `grammarDetect.ts`
   imports `levelNum` from it; comments describe it as the single owner of
   CEFR level ordering (a1-c2), plus `PROFILER_AUDIENCE` (General Learning
   vs. Young Learners, affecting which levels words/structures get credited
   at).
4. **`src/lib/grammarDetect.ts`** (787 lines, read in full). The structure
   detector itself: hand-written token-pattern rules per structure family
   (aux+participle chains, modal lookups, subordinator word lists,
   comparative/superlative suffix checks), not a POS parser or ML model.
   Optionally takes a `posOf` callback for noun/verb disambiguation. ~29
   structure families detected; 16 explicitly marked DEFERRED with reasons
   (imperatives, gerunds/infinitives, phrasal verbs, inversion, etc.) —
   stated principle: a smaller accurate profile beats a larger wrong one.
   Each rule is hand-tuned to fire only when a form is mechanically
   unambiguous, specifically to avoid false positives. This is the file any
   new "detect attempted-but-malformed" work extends — but the existing
   rules likely need a parallel rule set rather than an in-place edit,
   since bolting "detect even when malformed" onto rules built to dodge
   ambiguity risks reintroducing exactly that ambiguity.
5. **`src/lib/production.ts`** (271 lines, read in full). Not a grammar
   file — the per-word classifier for vocabulary (not-engaged / landed /
   not-landed [form, boundary, grammatical-form, suspected-form] /
   can't-tell). Useful only as a pattern reference for the "attempted vs.
   landed" distinction Grammar Accuracy will need, applied to structures
   instead of words. Already solves the same shape of problem (slip vs.
   consistent error via a count threshold, confidence flags that are never
   silent) for a different construct.

## Confirmed NOT to exist in LENS

Checked directly against the four files above, not inferred:

- Any detector for malformed/incorrect grammar structures.
  `production.ts`'s own returned data states this outright: "Form-correct
  patterns only — a structure listed here was attempted AND landed.
  Structures reached for but malformed need the AI inference step... their
  absence here is not evidence of absence." LENS already knows this is the
  gap.
- Any grammar accuracy or grammar range score.
- Any error-type taxonomy for grammar (missing/wrong-form/added/wrong-order).
- Any corrected-sentence generation for grammar.
- **`mapping/functions.json`** ("51 marker-signalled relations") —
  previously flagged in `02-six-dimension-construct-model.md` as a possible
  lead for Transition Words Range. Checked directly: not referenced
  anywhere in `analysis.ts` or `production.ts`. `analysis.ts`'s own header
  states "Deterministic only — no AI, no teaching advice, no function
  mapping." Downgraded from "worth checking" to "probably a dead end, worth
  one grep to confirm, don't expect it wired to anything."

## Net read

LENS gets the eventual Grammar build two things: the EGP reference data
(the structure-to-CEFR-level inventory) and a partial, correctly-formed-only
detector covering ~29 of the known structure families. The "attempted but
malformed" layer and the error-type classification are new work, following
the same AI-guesses-intent pattern already proven for spelling in this
project — not portable from LENS as-is.
