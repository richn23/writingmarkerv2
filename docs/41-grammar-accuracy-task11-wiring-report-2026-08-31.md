# Grammar Accuracy v1 — Task 11: `score.py` wiring report

Per docs/29. Not committed yet — report first, per instruction. Task 12 (UI)
not started.

Accuracy is now live in the API response. This is the first task in the
series whose output a caller can actually see.

## What was added

Three things in `api/score.py`:

- `_accuracy_written_to_intended(result)` — builds the
  `{lowercased written token: intended form}` map from the Spelling audit
  trail.
- `_grammar_accuracy(result)` — calls `accuracy_report()` with the **raw**
  text and that map.
- A `grammar_accuracy` / `grammar_accuracy_error` pair in `detail()`,
  following the defensive shape `grammar_detected`/`grammar_metrics` already
  use.

## The one thing this task had to get right

`_grammar_source_text()` returns the **interpretation**, and says so in its
own docstring: *"Never the raw as-written text: grammar structures are read
off what the student meant to write."* That is correct for Range and Metrics
and wrong for Accuracy, whose primary input is the raw text (docs/27's
correction to the input model).

Reusing it would have been the obvious move — it's the established helper,
every other grammar reader calls it, and nothing would have crashed. It
would simply have graded the *corrected* text and reported near-zero errors
for everyone, silently. So `_grammar_accuracy()` reads `result["text"]`
directly, with a docstring saying why, and there's a fixture asserting the
raw form is what reaches the checks (`written` is `"recieve"`, `intended` is
`"receive"`) rather than trusting the comment to survive future edits.

## Overlap Rule 1 is now mechanism, not intention

The `written_to_intended` map is what makes docs/24's Overlap Rule 1 real:
Accuracy never re-decides word identity, it looks up what Spelling already
decided. Built from the same audit rows `_corrected_text()` rewrites the
displayed script from, so Accuracy and the text the user reads can never
disagree about what a word was taken to be.

Verified live rather than by construction: `"He recieve the letter."`
produces exactly one error — subject-verb agreement, reached on the
corrected form `"receive"` — and the misspelling is not re-litigated as a
grammar error or double-counted. `"She recieved the freind letter."`
(misspellings, no grammar error) comes back 100% grammatically error-free.

**Stated limit:** the map captures Spelling's resolutions. Where the intent
layer changed something beyond spelling, that isn't in the map — recovering
it would mean aligning `corrected_sample` back to the raw text
token-by-token, which the corrector's own `split` decision makes a genuine
alignment problem rather than a `zip()`. Out of scope for v1. The
documented fallback (a token absent from the map is judged on its own
written form) means the cost is a missed correction, never a false
accusation.

## The split divergence is now confirmed live

docs/39 predicted that `grammar_accuracy["word_count"]` and
`grammar_metrics["word_count"]` would genuinely differ. Confirmed in the
real pipeline: `"I have alot of freinds."` → Accuracy counts **5** words
(raw), Metrics counts **6** (interpretation, where "alot" became "a lot").

Both numbers are correct about their own text. **This is the thing Task 12
must not conflate** — a UI showing an errors/100-words rate next to the
wrong word count would be quietly wrong in a way nothing would catch. There
is a fixture pinning the divergence so it stays visible.

Also confirmed: a multi-word map value (`"a lot"`) doesn't crash the checks
or produce a false flag — it fails every set and POS test and degrades to
no-flag, the conservative direction.

## One deliberate departure from the existing pattern

`grammar_metrics` is nested *inside* `grammar_detected`'s `try` block, which
is correct — it takes `gd` as an argument and genuinely cannot run without
it.

Accuracy is given its **own** `try` block instead. It shares nothing with
Range beyond the pos lookup, and nesting it would mean a Range failure
silently suppressed Accuracy too — reporting *"no errors"* rather than
*"an error occurred"*. That's the one failure mode this panel must never
have: a grammar-accuracy figure that reads as a clean bill of health when
the check never ran.

Tested rather than reasoned about: with `_grammar_detected` forced to
raise, `grammar_detected` and `grammar_metrics` are both correctly `None`
with the error recorded, and `grammar_accuracy` is still present, correct,
and error-free.

## Verified

11 fixtures in `tests/test_accuracy_wiring.py` (11/11). Unlike the other
`test_accuracy_*` files these drive the **real** pipeline (GseBank +
Corrector + `analyse` + `detail`), because the claims worth testing here are
exactly the ones hand-built inputs cannot see: that raw text reaches the
checks, that the map really comes from the audit trail, and that the
defensive isolation holds. Covers the field being populated; raw-vs-
interpretation; Overlap Rule 1 live; the map's exact contents; misspellings
not costing error-free status; the split divergence; multi-word map values;
a forced Accuracy failure setting the paired `_error` field without failing
the score; a forced Range failure not suppressing Accuracy; the definition
and coverage block surviving the wiring; and empty input not fabricating a
rate.

**Full regression, all green:** aggregate 19/19, merge 14/14, number 18/18,
pronoun-case 23/23, subject-verb 36/36, tense 16/16, verb-form 19/19,
wiring 11/11, word-order 13/13, grammar regression 14/14 — 183 fixtures
total. Full 92-example fixture set 92/92 (0 unexplained). `score.py` imports
clean under `-W error::SyntaxWarning`; `_engine`/`_intent` untouched.

## Sample live output

`"Yesterday he go to the shop. She recieved her freind letter. He can swim well."`

```
sentences=3  words=15 (raw as-written text, written words)
errors=1     errors/100 words=6.7
grammatically error-free: 2/3 = 66.7%
coverage: 6/8 families, partial=True
  ERROR: subject-verb-agreement 'go' (sentence 0)
```

Both docs/40 fixes hold in the live pipeline: "He can swim well." is clean,
and possessive "her freind" doesn't flag.

## Status

Not committed. Ready for review. Task 12 (UI) not started — it replaces the
current "not built yet" placeholder, and inherits two things from this task
that need care: the word-count divergence above, and the requirement that
the error-free metric is labelled **grammatically** error-free wherever it
surfaces (docs/24, docs/28). The definition string ships in the payload
precisely so the UI doesn't have to reinvent it.
