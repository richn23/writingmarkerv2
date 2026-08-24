# Grammar detected (Range) — port verification, 24 Aug 2026

Verification report for Task 1 of the "Build brief for Claude Code — Grammar
detected (Range), 24 Aug 2026": porting LENS's `src/lib/grammarDetect.ts`
into `api/_grammar/`. Task 1 is done. Tasks 2 (`score.py` wiring) and 3
(UI tab) have not started, per the brief's explicit ordering instruction.

## What was ported

- `api/_grammar/_data/grammar_profile.json`, `structures.json` — byte-for-byte
  copies of LENS's reference files, confirmed via `diff -q` against the
  source repo.
- `api/_grammar/families.py` — port of `egpFamilies.ts`: family→EGP-row
  resolution, the half-band CEFR level scale (a1=1 … c2=6, kept local and
  never mixed with `_engine`'s GSE-point `GSE_BANDS`), and
  `assert_detector_families()`, the build-time consistency check that fails
  import if the family table drifts from `structures.json`'s declared
  coverage.
- `api/_grammar/pos.py` — the `posOf` equivalent, reusing `_engine.lemmas`
  and this project's own `gse_vocabulary.json` (confirmed to be the same
  Pearson dataset LENS uses, so no second vocabulary index was ported).
- `api/_grammar/sentences.py` — `split_sentences`, reimplemented rather than
  directly ported: Python's `re` has no variable-width lookbehind, which the
  original JS split regex relies on.
- `api/_grammar/detect.py` — the detector itself. All 30 declared families,
  the 16-entry DEFERRED list with reasons, the 2 PARTIAL entries with their
  detects/misses text, and the FORM/USE guideword-gating + row-verification
  logic from `resolveStructure()` (`grammarDetect.ts:207-264`).

## Verification method

Captured live ground truth by running the real LENS TS detector (`npx tsx`
against `detectGrammarStructures()`, not a re-read of the source) over every
worked example in `structures.json` — 92 sentences across all 45 structure
headings. Diffed the Python port's output against that captured ground
truth on `(explorer_id, family_id, matched, level)` for every example.

## Result: 92/92 match

All 92 examples agree on family, matched span, and level, with one
deliberate exception detailed below. All temporary scripts used for this
(fixture capture, row dumps, debug instrumentation) were created inside the
LENS repo's own `scripts/` folder and deleted after use; `git status
--porcelain` on that repo returns 0 lines, confirming it was left exactly as
found.

## Divergence found, and how it was resolved

Three examples — all `modals-past`, all "modal + have + past participle"
constructions — initially disagreed on **level only** (family, span, and
detection all agreed):

| Sentence | Live LENS | Python port (as written) |
|---|---|---|
| "You should have called me." | a2 | b1 |
| "She might have missed the train." | a2 | b1 |
| "If I had known, I would have helped." | a2 | b1 |

Root cause, confirmed against the git-committed blob
(`git show HEAD:src/lib/grammarDetect.ts` in the LENS repo, not just the
working tree — so this is not a local edit artifact): line 223 of
`grammarDetect.ts`, part of commit `ffddc694` (2026-08-10), reads

```ts
hasPast = /\x08PAST\x08/.test(T)
```

`\x08` is a literal backspace control character, not the word-boundary
escape (`\b`) it was almost certainly meant to be. Guideword text never
contains backspace bytes, so this condition can never be true — the
past/perfect scoring bonus in `resolveStructure()`'s row-selection loop is
silently dead in production, for every family that has both a base-level and
a PAST-level row, not only "should"/"might"/"would". With that bonus never
firing, the base-level and PAST-level rows tie on score, and LENS's own
tie-break rule (`lowerReading`: on a tie, keep the first-seen, lower-level
row — `pool` is level-ascending) resolves to the lower level. That is why
live LENS reports a2 here even though "should/might/would + have + past
participle" is a real past-modal construction.

This was flagged rather than silently resolved, per the brief's explicit
instruction. Asked the user directly: replicate LENS's live behavior (a2,
matching production byte-for-byte including the bug) or keep the Python
port's already-correct regex (b1, the level a working detector reports).

**Decision: keep the port's correct behavior (b1).** The three fixture
mismatches are therefore expected, not porting defects, and are recorded as
a known-divergence allowlist in the verification script
(`verify_grammar_port.py`) rather than silently dropped. With that
allowlist applied: 92/92 examples match, 0 unexplained.

## Other fix made during verification

`api/_grammar/sentences.py`'s module docstring triggered a `SyntaxWarning`
for an invalid `\]` escape sequence (a leftover from quoting the original JS
split regex in prose). Made the docstring a raw string (`r"""…"""`) so nothing
inside it is escape-processed. Confirmed clean via
`python3 -W error::SyntaxWarning`. No behavior change — the regex the module
actually uses (`_SENT_BOUNDARY`) was already a separate, correctly-raw
string; only the docstring was affected.

## Headline counts (all confirmed matching the brief)

- 30 detector families (`DETECTOR_FAMILIES`)
- 16 deferred families, each with its stated reason (`DEFERRED`)
- 2 partial families, each with detects/misses text kept as-is
  (`PARTIAL`) — not silently upgraded to full coverage
- `assert_detector_families()` passes at import time

## Open question carried over from the brief

The brief recommended treating `api/_grammar/` as protected (like
`_engine`/`_intent`) once ported and verified, but left this "not yet
decided" and invited a flag-back if it should stay unprotected. Flagging
back now that Task 1 is verified: no objection to protecting it — the
module is now a completed, verified port with a known and deliberately
resolved divergence documented above, the same state `_engine`/`_intent`
were in when they were protected. Recommend proceeding with protection
unless told otherwise.

**Confirmed protected.** Recorded in docs/22, a new living reference doc —
the rule previously lived only inline in dated reports (docs/06, docs/19,
docs/20), with no single place a future session could check it without
already knowing which report to search.

## Next

Task 2: wire `grammar_detected` into `score.py` against the approved
interpretation text (freshest of first-pass/marker-adjusted, same selection
logic as Vocab/Spelling), no correction logic, three-way
detected/partial/deferred response shape. Not started yet.
