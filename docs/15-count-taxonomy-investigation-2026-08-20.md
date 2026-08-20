# Investigation — the 30 / 31 / 32 / 56 counts, 20 Aug 2026

Task 1 of the count-taxonomy brief. **Read-only: nothing was changed.** Traced
against a live scoring call on the standard sample.

## The numbers, and what each one actually counts

| On screen | Value | Universe | Deduplicated? | Function words? | Unmatched words? |
|---|---|---|---|---|---|
| Every word | 71 | intent reading, all tokens | no | **yes** | yes |
| Spelling: words attempted | 56 | as-written, distinct **forms** | yes | **yes** | yes |
| Content words only | 33 | intent reading, tokens | no | no | yes |
| Repetition stripped | 32 | intent reading, distinct | yes | no | **yes (2)** |
| Coverage denominator | 31 | **as-written**, distinct | yes | no | **yes** |
| Credible words | 30 | intent reading, distinct | yes | no | **no** |

Six numbers, five different definitions. None of them is labelled with the
distinction that makes it differ from its neighbour, which is why they read as
inconsistent.

The two easy ones first, because they are not the problem:

- **71 vs 56** is tokens vs distinct forms. 71 word tokens deduplicate to 56
  distinct written forms, which is exactly what the spelling score counts
  (`spelling_score.py` takes "one record per DISTINCT written form actually
  attempted"). Both include function words, which the content-word counts do not.
- **33 vs 32** is tokens vs distinct, within content words.

## 32 vs 30: definitional, and correctly so

The chip list shows the intent reading's distinct content words **including
words that never matched the reference list**. Two did not match:

- `fishermen` — irregular plural; no lemma candidate reaches `fisherman`.
- `grandmother's` — possessive; not stripped before lookup.

`credible_words()` (`_engine/scoring.py:172`) skips any record where
`matched` is false or `gse` is None, then keeps those at confidence ≥ 0.70.
Nothing here was below the bar (`excluded` is empty), so:

**32 chips − 2 unmatched = 30 credible words.** That arithmetic holds exactly.

This is a legitimate definitional difference, not a bug. It needs wording, not a
fix: the toggle says "Repetition stripped (32)" without saying that two of those
32 contributed nothing to the level.

## 31 vs 32: a real inconsistency, not a definitional one

Coverage counts a different universe from the chip list — `result["original"]
["distinct"]`, the **as-written** distinct content words, rather than the intent
reading's. Comparing the two lists directly:

```
views.written  (31): … ("grandmother's", A2+) … ("fishermen", None) …
views.distinct (32): … ("grandmother's", None) … ("grandmother", A2+) … ("fishermen", None) …
```

**`grandmother's` matches in the as-written reading and does not match in the
intent reading.** Same surface token, same reference list, two different answers.

That single inconsistency produces the whole 31 → 32 gap:

- As-written, `grandmother's` resolves to the form `grandmother`. The sample's
  other occurrence, plain `grandmother`, resolves to the same form. `distinct` is
  keyed on the **matched form**, so both collapse into **one** entry → 31.
- In the intent reading, `grandmother's` fails to match, so it keys on its own
  surface token and `grandmother` keys separately → **two** entries → 32.

So the gap is not a counting-rule difference. It is the same word being resolved
in one pass and not the other. The five misspellings behave consistently across
both lists (`vilage`→`village` and so on), so they are not implicated.

## Coverage overstates: `fishermen` is counted as resolved

`_coverage()` (`_intent/layer.py:644`) builds its numerator by removing only:

- tokens the intent layer answered `unrecoverable`, and
- tokens whose `replacement` was rejected, and
- tokens answered `proper_noun` (removed from numerator **and** denominator).

It never asks whether a word matched the reference list. On this sample no token
fell into any of those three categories, so `unresolved` is empty and coverage
reports **31 of 31, 100%**.

But `fishermen` is in that 31 and it matched nothing, scored nothing, and
contributed nothing to the level. Coverage's own docstring says it counts
"score-eligible distinct content words"; an unmatched word is not score-eligible.

**Tracing the two test words through both counts:**

| | Coverage denominator | Coverage numerator | Credible words |
|---|---|---|---|
| `fishermen` | included (1 of the 31) | **included — wrong**, it resolved to nothing | excluded, correctly |
| `grandmother's` | included, and collapsed with `grandmother` into one entry | included | excluded from the intent reading, though it *is* matched in the as-written one |

So the answer to the brief's question is: **one of each.** The 32 vs 30 gap is a
legitimate definitional difference needing clearer wording. The 31 is affected by
two real defects.

## What I have not done, and why

Both defects sit inside protected code:

1. **The possessive inconsistency** is in the intent reading's token stream,
   built by `corrected_sample()` / `_profile()` in `_intent/layer.py`. The
   as-written path (`_engine/views.py` → `GseBank.resolve`) handles `'s`;
   the intent path does not.
2. **Coverage counting unmatched words as resolved** is `_coverage()` in
   `_intent/layer.py`.

The brief is explicit: stop and report rather than edit protected code, and
confirm before changing what any number computes. So nothing was touched, and
Tasks 2, 3 and 4 are not started — a taxonomy written now would either document
two wrong numbers as correct, or describe intended behaviour that the code does
not implement. Both are worse than waiting.

## Decisions needed before Task 2

1. **`fishermen` in Coverage.** Should an unmatched word count as resolved? If
   not, this is a one-line change in `_coverage()` — but inside protected code,
   and it moves a published number (100% → 97%).
2. **`grandmother's`.** Should the possessive be stripped before lookup in the
   intent reading, matching the as-written pass? That would make the two lists
   agree at 31 and remove the gap at source. Also protected code.
3. **If neither is to be fixed now**, the taxonomy can still be written, but it
   must document the numbers as they behave, including that Coverage counts
   unmatched words as resolved. Say which, and Task 2 follows immediately.

An additional note for whichever way this goes: `fishermen` is a genuine
reference-list miss rather than a spelling error, and the brief's Task 4 asks
what to do with unmatched words in a band filter. They are the same population.
Whatever is decided here should hold there too.
