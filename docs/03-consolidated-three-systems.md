# The three systems, tied together (working summary, 18 Aug 2026)

Three systems exist, not one:

1. **LENS** (`language-awareness-pipeline`, TypeScript, Next.js) — the
   reference platform, evidence-only by design, never scores. The only place
   EGP grammar/structure detection exists anywhere across all three systems —
   but only for *correctly-formed* structures; malformed attempts are
   undetected everywhere, still.
2. **GSE_PROFILER** (Python, local CLI) — the origin. Vocabulary + spelling
   only, no grammar. Deterministic, no AI/LLM. This is where the confidence-
   weighted 0–100 scoring (`scoring.py`) and the severity-aware corrector
   (`spelling.py`) were first built and calibrated against real MOE scripts.
3. **gse-vercel-app** (Python serverless + Next.js frontend, deployed) — the
   most advanced of the three. Its `api/_engine/` is GSE_PROFILER's engine
   copied in verbatim, but it goes well beyond GSE_PROFILER with a new
   `api/_intent/` AI layer:
   - Full corrected-script reassembly (`_corrected_text()` in `score.py`).
   - A richer spelling severity engine (`spelling_score.py`): categories
     `correct`, `minor_slip` (0.4), `boundary` (0.5), `phonetic` (0.7),
     `wrong_word` (0.8), `unrecoverable` (1.0), `proper_noun` (excluded).
     Difficulty read from the GSE band of the intended word, with a
     `KNOWN_HARD` exemption list. Persistence multiplier: 1.3x for a repeated
     wrong form (a "belief"), 1.0x for a one-off (a "slip").
   - Two selectable vocabulary 0–100 models (`vocab_fit.py`): `legacy`
     (default, calibrated) and `fitted` (statistical refit, higher r but
     unreliable at the top of the scale — flagged explicitly in code).
   - No grammar anywhere — explicit by design: *"Grammar is deliberately left
     as written: this is a vocabulary profiler."*

## Naming collision (fixed in the new project's copy)

gse-vercel-app's README and DEPLOY_PROMPT.md both said the engine in
`api/_engine/` was "the LENS profiler copied verbatim." It is not — it's
`GSE_PROFILER`, a separate Python workstream. Left uncorrected, a reader would
wrongly assume gse-vercel-app inherited LENS's EGP grammar detection along
with the vocabulary engine. It didn't. **Fixed in the copy at
`Writing Marking V2 - GSE Based/README.md`** — now reads "GSE_PROFILER's
engine, copied verbatim." The original `gse-vercel-app` project's README still
has the old wording if that also needs fixing.

## What's genuinely still open

Confirmed across all three systems, no exceptions: **grammar**. Nobody has
built malformed-structure detection, a grammar accuracy score, a grammar range
score, or corrected-sentence generation, anywhere. LENS detects correct
structures only; GSE_PROFILER and gse-vercel-app don't touch grammar at all.
This is the one clean remaining gap. The AI-layer pattern gse-vercel-app
already proved out for spelling (deterministic drives the score, AI only
guesses intent / produces presentational text) is the template to reuse for
grammar — it's a validated pattern, not an open design question.

## Why gse-vercel-app was chosen as the seed for the new project

It is the most advanced, most current, most calibrated of the three systems
for the vocabulary + spelling scope this phase covers. Vocabulary and spelling
are, in effect, already through most of the document → build → map → test →
sign-off cycle (documented, built, mapped to the GSE reference, tested against
a real 100-script MOE batch). Starting fresh from LENS or GSE_PROFILER alone
would mean rebuilding work that already exists and is calibrated.
