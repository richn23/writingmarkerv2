# AZE Language Profiler — Proposal & How (working summary)

> Note: this is my consolidated, code-verified summary of the two documents Richard
> shared on 18 Aug 2026 ("AZE Language Profiler — Proposal" and "— How"), not a
> verbatim copy. The originals were pasted into chat; if the exact original wording
> is needed, Richard has the source.

## The problem, as documented from real AZE scored samples

- Vocabulary Diversity rewards short answers and is non-monotonic across CEFR.
- Spelling Accuracy is bare "% valid dictionary words" — misses real-word errors
  (`non`/`one`), has no severity, no word-difficulty sense, and an artificially
  high floor because most words are short function words.
- Grammar Accuracy has no ambition adjustment (a safe short sentence scores the
  same as a sophisticated long one) plus a lookup bug that drops the CEFR band
  entirely on a perfect score.
- Sentence Complexity is a hardcoded stub — same value every time — and
  double-counts what Punctuation/Coherence already score.
- Punctuation only checks 4 advanced constructions, so simple writing coasts to
  near-perfect by never attempting them.
- A shared word-count gate blanks Grammar/Spelling/Punctuation under ~30 words,
  rolled up as a flat 0.0 rather than "no data" — 39% of a sampled batch scored
  zero for reasons unrelated to writing quality.

Root cause: bespoke per-metric logic, no shared reference framework, no evidence
trail behind any number.

## Architecture decided

AZE Language Profiler = a separate codebase, the same relationship GSE Profiler
already has to LENS (portable, no LENS runtime dependency), API-first, mirroring
`POST /api/analysis`. LENS stays permanently evidence-only by design — not a
blocker, a feature to preserve.

**Scope, this phase:** vocabulary + spelling + grammar (accuracy & range) only.
Register/Organisation deferred (blocked on Richard's own EAQUALS authoring, not
engineering). Content Quality/Task Achievement out of scope — matches LENS's
task-agnostic principle.

## Two decisions the proposal settles

1. **Scoring rubric** — resolve evidence to a CEFR level, map through a shared
   anchor table:

   `Pre-A1:0, A1:10, A2:29, A2+:36, B1:41, B1+:51, B2:58, B2+:67, C1:74, C2:86`

   Vocab / Grammar-range = highest level with enough evidence. Spelling =
   accuracy discounted by severity, weighted against the student's own
   demonstrated vocab level (so a miss below their level costs more than a miss
   on a reach-word).

2. **Deterministic vs AI** — keep whatever *drives a score* deterministic
   (structure classification, matching); reserve AI/LLM inference for guessing
   intent (spelling correction) and for corrected-sentence text generation
   (presentational, not score-driving).

## Code-verified corrections to the "How" doc's gap list (checked 18 Aug 2026)

The gap list undercounts what already exists — it exists in `GSE_PROFILER`'s
Python codebase, not in LENS's TypeScript engine.

- **Vocabulary #5 (score /100)** — not new. `gseprofiler/scoring.py` already
  implements `score_for_gse()` + `SCORE_BANDS`, byte-identical to the proposal's
  own anchor table on every shared band. Port `score_for_gse`/`band_for_gse`
  directly, don't rebuild.
- **Vocabulary #3 (confidence of demonstrated level)** — closer to "have it."
  `scoring.py`'s `composite_confidence()` already computes this: sample-size +
  match-reliability + distribution-stability, calibrated on 77 real scripts
  (32% exact / 79% within-1-band).
- **Spelling #3 (severity scaled to length)** — already computed. `spelling.py`'s
  `correct()` already returns `edit_distance` and `max_edits` on every
  correction.
- **Spelling #4 (CEFR level per flagged word)** — one function call. `gse.py`'s
  `GseBank.describe(word)` already returns a `coarse` CEFR band.
- **Vocabulary #2 (full corrected script reassembly)** — genuinely was an open
  question at proposal time, but is now confirmed **built**, in gse-vercel-app's
  `_corrected_text()` (see the three-systems summary doc).

## The practical build risk

The "Reused as-is" list reads as one shared engine. In reality it's two
separate, independently-built codebases in two different languages:
`GSE_PROFILER` (Python) holds the confidence-weighted scoring/anchor-table/
severity machinery; LENS's Production Analyser (`production.ts`) holds the
word/structure classification and the EGP structure detector. They share the
same underlying GSE JSON data, not code. Whoever builds AZE Language Profiler
has to either port one into the other's stack or write real bridging logic.

**Resolved 18 Aug 2026:** built as a new project, seeded from `gse-vercel-app`'s
current Python engine (already the most advanced of the three systems), hosted
at `Writing Marking V2 - GSE Based`. See `03-consolidated-three-systems.md` for
why gse-vercel-app was chosen as the seed rather than LENS or GSE_PROFILER
directly.
