# Task 3c: 'd contraction disambiguation fix — 25 Aug 2026

Root-caused, implemented, and verified. **Not yet committed** — verification
results below, per instruction, before any commit.

## Root cause, confirmed

`api/_grammar/detect.py`'s `_expand()` mapped `'d` unconditionally to
`" would"`. Checked the real LENS source directly: `grammarDetect.ts:443`
has the identical unconditional mapping — upstream, not a porting
artifact. No "Doc 16" exists anywhere in the repo (confirmed again, fresh),
so this genuinely started from scratch rather than extending prior work.

`'d` is lexically ambiguous in English: `'d + bare verb` means "would"
("they'd love to come" = "they would love to come"), but `'d + past
participle` means "had" ("they'd already mentioned it" = "they had already
mentioned it"). The blanket mapping is right for the first case and wrong
for the second — reproduced directly:

| Sentence | 'd means | Before fix |
|---|---|---|
| "They'd already mentioned it before the meeting started." | had | `modals-ability`/`would`, "would already" — wrong; the real past-perfect went undetected |
| "She'd finished her homework by the time I arrived." | had | `modals-ability`/`would`, "would finished" — wrong |
| "They'd been waiting for hours when the bus finally came." | had | `modals-ability`/`would`, "would been" — wrong |
| "They'd love to come to the party." | would | `modals-ability`/`would`, "would love" — correct |
| "I'd rather stay home tonight." | would | `modals-ability`/`would`, "would rather" — correct |

## Fix

Disambiguated by inspecting the word immediately following `'d` (skipping
any `SKIP`-listed adverb, same as every other branch in this file already
does when it needs to look past an adverb to a verb) and checking whether
that word is a past participle via the existing `is_pp()`/`IRREG_PP` — no
new data, reusing exactly what the `had`/`have` branches already use for
the identical judgment call. `'d have`/`'d rather` are correctly left as
"would" (past participle check fails for "have"/"rather"); `'d been` is
correctly reclassified to "had" ("been" is already in `IRREG_PP`).

## Verification

**Reproduced against 6 cases**, including 2 not in the table above (`'d
have` and `'d been`, to check the fix doesn't overcorrect):

- All 3 "had" cases now correctly resolve to `past-perfect`/
  `past-perfect-continuous`, at the right level, with the spurious
  `modals-ability`/`would` hit gone.
- All 3 "would" cases (`'d love`, `'d rather`, `'d have`) are unchanged —
  confirming the fix doesn't overcorrect the common case.

**Live LENS comparison**, via a direct `npx tsx` run against the real,
unmodified `grammarDetect.ts` (temporary script, deleted after use — LENS
repo confirmed clean, `git status --porcelain` returns 0 lines): live LENS
reproduces the exact same "would already" / "would finished" / "would
been" bug on the same three sentences. Confirms this is a genuine, still-
live upstream bug, not something already fixed in LENS that the port had
drifted from.

**Full 92-example fixture set** (docs/21): still 92/92, 0 unexplained. Only
one of the original 92 examples contains a `'d` contraction at all
("I'd like a coffee, please.") — "like" isn't a past participle, so it
resolves identically before and after this fix. No new known-divergence
entry needed; this fix doesn't change any of the 92's expected outputs.

**New regression fixtures**: added 5 cases to
`tests/test_grammar_regression.py` (3 for the fix, 2 as regression guards
confirming the common "would" case stays correct) — suite now 14/14.

**Build-time consistency check** (`assert_detector_families`): passes.
**Module import**: clean, no `SyntaxWarning`s.
**`_engine`/`_intent`**: confirmed untouched (`git status --short` empty).
**End-to-end through the real `score.py` pipeline**: verified — a
multi-clause sample with both an "already mentioned" and a "finished"
`'d`-contraction correctly resolves both as past-perfect, no errors.

## Status

Ready to commit once reviewed. Only `api/_grammar/detect.py` and
`tests/test_grammar_regression.py` changed.
