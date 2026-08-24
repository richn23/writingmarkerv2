# Investigation — "carried an error" counts proper nouns as errors, 24 Aug 2026

Read-only. **Nothing changed.** Both issues traced live, root cause confirmed
with a real repro, not inferred from the screenshot.

## Issue 1 — is `proper_noun` excluded, or just labelled separately?

**Confirmed: excluded from the scored index, not excluded from the descriptive
profile that produces the headline sentence.** Two different protected
functions compute two different "spelling error" figures, and only one of
them implements doc 10's rule.

### Where the headline sentence is computed

Not `_intent/spelling_score.py` — that file computes `d.spelling_score_detail`
(a different figure, see below). The sentence `"N% of the M distinct words
carried an error"` (`app/page.tsx:597-598`) reads `d.spelling`, which is built
by `spelling_profile()`, `api/_intent/layer.py:704-759` — a separate,
purely descriptive categorisation pass, also protected, that has never been
covered by doc 10 (doc 10 is about `spelling_score.py` specifically).

```python
counts = {c: 0 for c in review.CATEGORIES}     # includes "proper_noun"
...
for rec in result["original"]["distinct"]:
    ...
    counts[cat] += 1                            # proper_noun counted here too
    ...
total = sum(counts.values()) or 1               # proper_noun IS in the total
profile = [{
    "category": c, "label": review.CATEGORY_LABEL[c],
    "count": counts[c],
    "pct": round(100.0 * counts[c] / total, 1),  # same `total` for every row
} for c in review.CATEGORIES if counts[c]]

return {
    "examined": total,
    "profile": profile,
    "errors": sorted(rows, ...),
    "error_rate": round(100.0 * (total - counts["correct"]) / total, 1),
}
```

`error_rate`'s numerator is `total - counts["correct"]` — everything that
isn't literally `"correct"`. `proper_noun` is not `"correct"` (it's its own
category, labelled `"a name"` by `review.CATEGORY_LABEL`), so it lands in the
numerator. It is also part of `total`, the denominator. Both the headline
sentence and the category table's "Share" column read from this same `total`
— confirmed directly, not inferred: the `pct` field in the loop above uses the
identical `total` variable the headline's `error_rate` divides by.

### Confirmed live

Built a sample with two names (London, Sarah) and no genuine spelling errors
anywhere else, ran it through the real pipeline with `proper_noun` verdicts
for both:

```
d.spelling (spelling_profile(), drives the headline sentence):
   examined  : 36
   error_rate: 2.8
   profile   : [{'category': 'correct', 'count': 35, 'pct': 97.2},
                {'category': 'proper_noun', 'label': 'a name', 'count': 1, 'pct': 2.8}]
   -> renders as: "2.8% of the 36 distinct words carried an error."
```

(Only one of the two names was flagged for review in this repro — the other
resolved as a known dictionary word before `flag()` ever ran, same mechanism
as `flibbertigibbet` in docs/19. Doesn't change the finding: the one name that
*was* confirmed `proper_noun` still counts as an "error" here.)

### The scored index (`d.spelling_score_detail`) is NOT affected — checked, not assumed

The figure doc 10 actually documents is `spelling_score.score()`, fed by
`attempts()` (`_intent/layer.py:647-701`), a *different* function. Its
docstring states the rule explicitly and the code enforces it:

```python
# Excluded entirely -- proper nouns (a name is not an orthography failure),
# junk, and anything non-alphabetic.
...
names = {d["original"] for d in decisions.values()
         if d["answer"] == "proper_noun"}
...
for w, n in occ.items():
    if (w in junk_forms and w not in recovered) or w in names:
        continue          # <-- proper nouns never enter `out` at all
```

**Confirmed live, same sample:**

```
d.spelling_score_detail (attempts() -> spelling_score.score()):
   attempted : 45
   errors    : 0
   error_rate: 0.0
   score     : 100
```

`spelling_score.py` does exactly what doc 10 says. The bug is isolated to
`spelling_profile()` — a second, separately-maintained categorisation of the
same words that reuses `review.categorise()` but never learned the same
exclusion rule `attempts()` already has.

### What the headline should read

For the report's exact scenario (2 proper nouns, 40 distinct words, zero real
spelling mistakes): **once `spelling_profile()` excludes proper nouns the way
`attempts()` already does — not counted, and not part of `total` either — the
correct figure is "0% of 38 distinct words carried an error."** Not "0% of 40"
— doc 10's language is "excluded entirely," not "counted as correct," and
`attempts()`'s implementation of that rule removes the word from the
population being described, not just from the numerator. `spelling_profile()`
should match.

## Issue 2 — wording, and whether it's independent of the arithmetic

**Not independent — they're the same fix.** The sentence template ("N% of the
M distinct words carried an error") is fine English and needs no new wording
once the number it reports is correct. The "40 vs 38" question in the brief
is really asking whether the denominator itself should change, and the answer
is yes: `total` in `spelling_profile()` should exclude confirmed proper nouns
the same way `attempts()`'s `occ` loop already skips them, which is exactly
Issue 1's fix. Once that's done, "N% of the M distinct words" is already
correct wording for the correct M — no separate wording-only change is
needed on top of it.

One genuine wording question that *is* independent, worth flagging for
whoever picks up the fix: the category table still has a purpose for showing
`proper_noun` rows even after this fix (a marker may want to see which words
were treated as names), so removing proper nouns from `total`/`error_rate`
should not mean removing the `proper_noun` row from the table entirely — only
from the two percentage calculations that currently misuse it as an error
category.

## Task — JSON export on the Spelling tab

**No new code needed.** Checked the current architecture rather than
assuming a separate "Spelling tab" exists: `EVIDENCE_TABS` has one entry
covering both constructs (`vocab_spelling`, `"Vocabulary profile"`) —
Vocabulary and Spelling are two `<Collapsible>` sections inside the single
`VocabularyProfileTab` component, not two separate tabs.

The "Export JSON" button added for the 24 Aug brief already sits above both
sections (`app/page.tsx:1641-1646`, before the `Vocabulary` `Collapsible` at
1647 and the `Spelling` `Collapsible` at 1721) and downloads `d` — the full
`Detail` object — unfiltered. `d` already carries every spelling-related
field the Spelling section reads from: `spelling`, `spelling_score_detail`,
`spelling_changes`. Confirmed by reading what the Spelling `Collapsible`
itself renders from (`DetailView d={d} part="spelling"`, same `d`) — there is
no separate spelling-only response object to export; it was never split out
from the vocabulary one.

Per the brief's own stated condition — "reuse the existing export mechanism
if it already generalizes to other tabs; only build a second copy if it
doesn't" — it does generalize, so nothing was built. A live check
(intercepting the download, as done for the original Vocabulary export)
would confirm the exported file already contains `spelling_score_detail` and
`spelling` alongside everything else; not re-run here since the mechanism is
unchanged from its verified 24 Aug state.

One placement note, not a functional gap: the button sits at the top of the
tab, above the Vocabulary section, so a marker who expands only "Spelling"
and scrolls past it may not immediately see it. Worth a UX decision (duplicate
the button, or move it) if it turns out to matter in practice — not fixed
here, since the mechanism itself needed no change.

## Summary

Two things confirmed, nothing built:

1. **`spelling_profile()`** (`_intent/layer.py:704-759`, protected) should
   exclude confirmed proper nouns from `total`/`counts` entirely, mirroring
   `attempts()`'s existing `or w in names: continue` — not just leave them
   uncounted as errors, but removed from the population being described. This
   makes `examined` drop from 40 to 38 in the reported scenario and
   `error_rate` read the true 0%, without any wording change beyond the
   number itself.
2. **JSON export** requires no work — the existing button already covers
   Spelling's data, confirmed by reading the component tree, not assumed.
