# Follow-up for Claude Code — coverage/unresolved wording, 19 Aug 2026

Small, scoped fix. Not a re-open of Task 2-4 from the build brief — those are
verified done. This is the one loose end from that report: "Dimensions
reports Coverage 100%... still unresolved: will always."

## Root cause (confirmed by reading the current code)

`app/page.tsx` (~line 543-551) renders one sentence built from
`d.coverage_detail`:

```tsx
Coverage {Math.round(d.coverage_detail.coverage * 100)}% — the level rests on{" "}
{d.coverage_detail.resolved} of {d.coverage_detail.written} content words written
...
{d.coverage_detail.unresolved && d.coverage_detail.unresolved.length
  ? ` Still unresolved: ${d.coverage_detail.unresolved.join(", ")}.`
  : ""}
```

`d.coverage_detail` comes from `_intent/layer.py`'s `_coverage()` —
protected, do not edit. Its `written`/`resolved`/`coverage` figures are
counted over individual word tokens; join-pair candidates like "will
always" (two words flagged together as possibly one misspelling) aren't
folded into that denominator at all. So `coverage` can genuinely be 100%
(every individual word resolved) while `unresolved` still names a join-pair
token that's a separate, still-open question. Both numbers are individually
correct — the sentence just presents them as if they were one fact.

## Fix (page.tsx only, no `_intent/` change)

Don't touch `_coverage()`'s math or denominator — that's calibrated,
protected code, and the two figures being separate is arguably correct: word
coverage and open review items are genuinely different questions.

Instead, split the rendering into two independent statements, matching the
pattern already used for Task 4's two Dimensions banners (interpretation
source vs. unapplied corrections — same idea: two true things, shown as two
things, not merged into one that reads as self-contradictory). Suggested
wording, adjust to fit the existing tone:

- Coverage line, unchanged in substance: "Coverage 100% — every individual
  word used in scoring is resolved."
- Separate line/note, only when `unresolved.length`: "Still awaiting review:
  will always (see Vocabulary review)." — and ideally this should link or
  point at section 6 the way other cross-references on Translate already do,
  since that's literally where the marker resolves it.

Verify after: a script with zero unresolved items shows only the coverage
line (no empty second line), and a script with a join-pair still pending
shows both lines without either implying the other is wrong.
