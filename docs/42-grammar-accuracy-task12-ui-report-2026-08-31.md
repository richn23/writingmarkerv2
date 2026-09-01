# Grammar Accuracy v1 — Task 12: UI report

Per docs/29. Not committed yet — report first, per instruction. **This is the
last task in docs/29's plan.**

The "Grammar accuracy — not built yet" placeholder in the Grammar profile tab
is replaced with the real section, reading `grammar_accuracy` from the
payload Task 11 wired in.

## What it shows

**Headline:** the error count plus its own coverage caveat inline —
*"4 grammar errors in 6 of 8 families"* — so the number is never seen without
the qualifier, even collapsed.

**Five metric tiles**, matching `GrammarMetricsSection`'s existing
`MetricTile` grid: grammar errors, errors per 100 words, grammatically
error-free %, sentences, and words as written.

**The errors table:** family, edit-type, the written form with its
correction, the matching context, and the sentence number. Where Spelling
resolved a token to something else, a *"read as …"* line appears underneath,
so it's visible that the verdict was reached on the intended word rather than
the misspelling (Overlap Rule 1, made legible instead of merely true).
Task 9's merges surface here too, as *"also Tense"* under the primary family.

**The coverage table:** all eight families, filled/hollow marker for
checked/unchecked, each with its scope note. Both unbuilt families carry
their reason. A clean result can't be read as more than it is.

## The two things carried forward

**Word counts are never adjacent.** `grammar_metrics` doesn't render a word
count at all, so there was no adjacency to remove — but the tile is still
labelled **"Words as written"** and carries `word_count_basis` from the
payload as its subtitle, so the number is self-describing wherever it ends
up. The type declaration in `page.tsx` also carries a comment explaining why
the two counts differ, since that's where a future edit would most likely
reintroduce the confusion.

**"Grammatically error-free", never bare.** The tile label reads
*"Grammatically error-free"*, and the definition below it is
`grammatically_error_free_definition` **rendered straight from the payload** —
not re-written as UI copy. My first draft did write a lead-in sentence of my
own above the coverage note; testing showed it duplicated what the payload
already said ("Partial coverage — absence of evidence… Partial coverage.
Counts reflect only…"), so I deleted mine and kept the payload's. Same
principle: one source of wording, no drift.

## Three issues found by rendering it, not by reading it

**1. The UI told the teacher the correct form was "i".** The checks work in
lowercase throughout, so `_OBJ_TO_SUBJ` maps `"me"` → `"i"`, and the table
rendered *"me → i"* — printing the wrong form as the right answer. Fixed
with a display-only re-capitalisation (`accuracyForm()`). Deliberately at the
display layer: lowercasing is correct for the matching the checks do, and
only the reader-facing string needs the case back. Now renders *"me → I"*.

**2. Duplicated coverage wording** — described above.

**3. Errors came out in check-execution order**, not reading order —
sentences 1, 5, 4, 4. Now sorted by `sentence_index` then `token_index`, so
the table reads in the order a marker reads the script: 1, 4, 4, 5.

None of these were visible in the payload or in a typecheck. They needed the
thing on screen.

## One stale comment fixed

`EVIDENCE_TABS` carried a comment saying *"Grammar accuracy is still an
honest placeholder within it (docs/21)"*. No longer true; updated rather than
left to mislead the next reader.

The Translate screen's *"grammar correction (not built yet)"* legend is
**deliberately left alone** — that refers to the grammar *correction/
translation* layer (rewriting the text), which still doesn't exist. Accuracy
detects errors; it doesn't rewrite. Checked before assuming they were the
same thing.

## Verified

Typecheck clean (`tsc --noEmit`, exit 0). Verified **live in the browser**
against the real `api/score.py` handler — `serve_real.py` + `cors_proxy.py`
with a temporary `next.config.js` rewrite, since `vercel dev` is still broken
on this machine. The rewrite has been reverted; `next.config.js` is
byte-identical to the committed version (`git status` clean for it), and all
three servers are stopped.

Sample: *"Yesterday he go to the shop. She recieved her freind letter. He can
swim well. Me and him went to town. I saw three dog in the park."*

Rendered:

```
GRAMMAR ACCURACY   4 grammar errors in 6 of 8 families

GRAMMAR ERRORS 4 | ERRORS PER 100 WORDS 14.3 | GRAMMATICALLY ERROR-FREE 40%
SENTENCES 5      | WORDS AS WRITTEN 28 (raw as-written text, written words)

Subject–verb agreement  wrong-form · also Tense   go        he go             1
Pronoun                 wrong-form                me → I    me and him went   4
Pronoun                 wrong-form                him → he  him went          4
Number                  missing                   dog       three dog         5
```

Everything docs/40 fixed holds on screen: *"He can swim well."* is clean,
*"her freind letter"* doesn't flag as a pronoun error, and the two
misspellings don't cost their sentence its grammatically-error-free status.
The subject–verb/tense merge shows as one row with *"also Tense"*, not two.

Python suites unaffected and re-run green: 183 fixtures across ten suites.
Only `app/page.tsx` is modified.

## Status

Not committed. Ready for review. **This completes docs/29's twelve-task
plan.** Grammar Accuracy v1 is built, wired, and visible.

Known remaining scope, all previously stated rather than newly discovered:
Scenario B (whole-narrative pattern propagation, docs/24) deferred;
article/determiner and preposition families blocked on data that doesn't
exist in the codebase; every built family is a deliberate slice with its
scope stated on the face of the UI. Accuracy v2 (errors/T-unit, error-free
T-unit %) stays gated on Tier 2 parsing being calibrated first, per docs/28's
sequence.
