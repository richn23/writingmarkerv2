# Investigation — apostrophe stripping and the awaiting-review count mismatch, 21 Aug 2026

Read-only. **Nothing changed.** Both issues traced with live code, not inferred
from the screenshot description. Both live inside `_coverage()` in
`api/_intent/layer.py` — same protected function, two independent bugs.

## Issue 1 — apostrophes and case stripped in "still awaiting review"

### Where the list is built

`_coverage()`, `api/_intent/layer.py:820-861`. The returned `unresolved` value
— the one `app/page.tsx:575` renders verbatim as `Still awaiting review:
{d.coverage_detail.unresolved.join(", ")}` — is built from two token sets:

```python
unresolved = {d["original"] for d in decisions.values()
              if d["answer"] in ("unrecoverable",) or
              (d["answer"] == "replacement" and not d["accepted"])}
...
unresolved |= {(r.get("token") or "") for r in written
               if not r.get("matched") and (r.get("token") or "") not in corrected}
```

`d["original"]` and `r.get("token")` are both the **normalised** identifier:
lowercase, apostrophe stripped. That normalisation starts at
`_engine/views.py:39`, `_TOKEN.finditer` feeding
`"lower": raw.lower().replace("'", "")` — and it propagates through
`_engine/analyse.py`'s `kinds`/`decisions` dicts, into
`_intent/review.validate()`'s `"original": written`, into
`_coverage()`'s sets. `score.py:431` forwards the dict unmodified
(`"coverage_detail": result.get("coverage")`); `app/page.tsx:575` renders it
unmodified. Neither layer touches the value.

**Confirmed live**, using `I didn't go to London to see Sarah. Tom's
flibbertigibbet cousin annoyed everyone.`:

```
coverage.unresolved: ['didnt', 'flibbertigibbet', 'london', 'sarah', 'toms']
```

— exactly the shape reported: lowercase, no apostrophe.

### Is the normalisation intentional?

Yes, and it has to be — it is the same field the entire pipeline uses as a
word's identity for indexing and deduplication: `kinds`/`decisions` dicts in
`analyse.py` are keyed on it, `GseBank.resolve()` is called with it, the
`intent_decisions` dict (the review table's source) is keyed on it. Changing
what `_coverage()` matches *against* would risk breaking that identity.

### Is the display a bug?

Yes, and it is fixable without touching the matching logic. The **raw** form
(case and apostrophe intact) already exists on the same records `_coverage()`
is iterating: `build_profile()` sets `rec["raw"] = t["raw"]`
(`_engine/views.py:61`), and `score.py`'s `_words()` already uses exactly that
field for the word-chip grid — `"word": r.get("raw") or r["token"]`
(`score.py:203`). That is why the chip grid shows `Tom's` and `didn't`
correctly: it reads a field `_coverage()` has available and simply doesn't use.

**Confirmed live** — every one of the five test words carries its raw form on
the matching `written` record:

```
token=didnt            raw="didn't"
token=london            raw='London'
token=sarah             raw='Sarah'
token=toms              raw="Tom's"
token=flibbertigibbet   raw='flibbertigibbet'
```

### Where the fix belongs

Inside `_coverage()`, in `unresolved`'s construction — nowhere else, since
`score.py` and `page.tsx` never see the raw forms for these tokens at all; they
only receive whatever `_coverage()` returns. The filtering logic (which
`written` records get *added* to `unresolved`, based on the normalised
`token`/`d["original"]` keys) is correct and should not change. Only the value
stored for display needs to become the record's `raw` form instead of its
`token` form. This is protected code, so the fix needs the same explicit
approval the Coverage and possessive fixes got.

---

## Issue 2 — 35 / 38 / 5, and why three of the five never appear as review rows

This is **two independent bugs**, confirmed separately, not one explanation.
Doc 08's join-pair divergence is **not** the mechanism here — the repro below
has no join pairs, and both bugs reproduce without one.

### The three lists, and what each one actually is

| List | Source | What it counts |
|---|---|---|
| Credible words | `credible_words()`, `_engine/scoring.py:172` | Distinct content words that **matched** the GSE list, confidence ≥ 0.70 |
| Repetition stripped (chip count) | `views["distinct"]` | Distinct content words in the **intent reading**, matched or not |
| Vocabulary review table | `intent_audit` = `intent_decisions.values()`, `score.py:418` | Only tokens `flag()` decided to **ask the model about** |
| "Still awaiting review" | `coverage_detail.unresolved`, `_coverage()` | Union of two different rules — see below |

The review table and the awaiting-review note are **not** the same list and
were never meant to be — but the note's own wording ("awaiting review") claims
a relationship to the table that the code doesn't deliver.

### Bug A — the awaiting-review list includes words that were never asked about

`flag()` (`_intent/layer.py:135`) only builds candidates from
`result["audit"]["lenient"]` rows — i.e. words the deterministic corrector
actually produced a decision for. A word never reaches that stage if
`corrector.classify()` already calls it `"known"`: `analyse.py:50`,
`if kind != "known": d[w] = corrector.correct(...)` — skipped entirely,
never corrected, never abstained, never asked about.

**Confirmed live**: `didnt` and `flibbertigibbet` both classify as `"known"` —
they're real, correctly-spelled entries in the corrector's general word list
(`english_words.txt`, much larger than the GSE list) — so `flag()`'s candidate
set for the test sentence was exactly `['london', 'sarah', 'toms']`; `didnt`
and `flibbertigibbet` were never in it, and never entered `intent_decisions`.

But `_coverage()`'s second clause doesn't check whether a word was ever asked
about — it scans **every** distinct content word in the original text:

```python
unresolved |= {(r.get("token") or "") for r in written
               if not r.get("matched") and (r.get("token") or "") not in corrected}
```

`didnt` and `flibbertigibbet` are unmatched (no GSE band) and were never
corrected, so this clause adds them regardless of `flag()` ever having seen
them. That is why they appear in "awaiting review" with no row in the table:
there was never a review to have.

This part is arguably not a bug so much as an unlabelled definitional gap —
"awaiting review" implies "review pending", but some of these words were never
eligible for review at all; they are words the reference list simply doesn't
contain.

### Bug B — proper nouns are excluded from the fraction but not from the list

This one is a real inconsistency inside the same function. `_coverage()`
builds `names` (tokens the model or a marker confirmed are proper nouns) and
correctly excludes them from **both** the numerator and denominator of the
coverage fraction:

```python
eligible = [r for r in written
            if (r.get("token") or "") not in unresolved
            and (r.get("token") or "") not in names]
denom = [r for r in written if (r.get("token") or "") not in names]
```

But `unresolved`'s clause (b) — the one that adds `didnt` and
`flibbertigibbet` above — has no `names` check at all. A token confirmed as a
proper noun is unmatched by definition (GSE doesn't index names) and was never
"corrected" (a `proper_noun` answer never sets `corrected`), so it satisfies
clause (b) and lands in `unresolved` regardless of being a settled, accepted
proper noun.

**Confirmed live**, feeding realistic model verdicts (`london`, `sarah`,
`toms` all answered `proper_noun`) rather than empty ones:

```
intent_decisions: london=proper_noun accepted=True
                   sarah =proper_noun accepted=True
                   toms  =proper_noun accepted=True

coverage: resolved=4  written=6   (9 distinct content words - 3 names = 6, correct)
          unresolved (5): ['didnt', 'flibbertigibbet', 'london', 'sarah', 'toms']
```

`written` correctly dropped from 9 to 6 — the names exclusion works for the
fraction. `unresolved` still lists all three names anyway, because the clause
that builds it never consults `names`. This is exactly the shape in the
original report: a coverage fraction that is internally consistent (its own
arithmetic checks out) sitting next to a longer "unresolved" list built by a
rule that partially ignores the same exclusion the fraction applies two lines
later.

### Answering the third question directly: is "accepted" a real terminal state?

Yes — and that is precisely why it doesn't resolve the contradiction.
`review.validate()` (`_intent/review.py:200`) initialises every decision with
`"accepted": False`, then for any answer other than `"replacement"`:

```python
if rec["answer"] != "replacement":
    rec["accepted"] = True          # nothing is being changed
```

`accepted: True` means **"no proposed replacement was rejected"** — it says
nothing about whether the word has a GSE match. A `proper_noun` or
`unrecoverable` answer is always `accepted`, by this rule, whether or not the
word ever scores. So "accepted" in the review table and "unresolved" in
coverage are two different, independently-true facts about the same token —
not a staleness bug, and not evidence that coverage is reading old data. The
mismatch is that the coverage note's wording implies review status, when the
field it's built from was never designed to track that.

## Issue 3 — three "content word" counts, three different readings and shapes

**Not one bug — three fields with near-identical labels, drawing from two
different readings and two different levels of deduplication, none of it
stated on screen.**

### Where each number comes from

| On screen | Field | Built at | What it counts |
|---|---|---|---|
| "N distinct content words" (Words tile subtext) | `d.distinct` | `score.py:341`, inside `summarise()` | `len(result["lenient"]["distinct"])` |
| "Repetition stripped (N)" (toggle) | `d.views.distinct.length` | `score.py:399`, inside `detail()` | `len(_words(prof["distinct"]))`, `prof` = the **assessed** reading |
| "Content words only (N)" (toggle) | `d.views.content.length` | `score.py:398` | `len(_words(prof["content_only"]))`, same `prof`, **not deduplicated** |

`prof` comes from `_assessed()` (`score.py:345-358`): the intent reading if
`result["intent"]["score"]["assigned"]`, otherwise lenient. `summarise()` is a
separate function, called before `_assessed()` even runs, and its `distinct`
field is hardcoded to `result["lenient"]` — **unconditionally**, regardless of
which reading the rest of the screen ends up showing.

### Are the headline and "Repetition stripped" meant to be the same number?

They are describing the same *concept* — distinct content-word identities —
but from two different token streams, and nothing on screen says so. The
headline is always the lenient reading (deterministic correction only, no
model). The toggle is the assessed reading (intent, when assigned) — which can
differ from lenient in two ways:

1. **A correction only the model made.** Lenient's deterministic corrector
   abstains on some words the model resolves in context (e.g. `bote` staying
   `bote` in lenient, resolving to `boat` in intent) — a straight one-for-one
   swap, so it doesn't change the *count*, only which words appear in it.
2. **Multi-word phrase merging**, added 21 Aug. `_merge_phrases()` runs only on
   the intent stream, inside `_apply()` — never on lenient. A matched phrase
   collapses two or more lenient-distinct entries into one intent-distinct
   entry.

**Confirmed live** — a sample containing `a lot` (twice) and `task force`
once:

```
lenient distinct (14): [... 'force', ... 'lot', ... 'task', ...]
intent  distinct (13): [... 'a lot', ... 'task force', ...]
```

`task force` alone collapses two lenient entries (`task`, `force`) into one
(`task force`) — a genuine, reproducible −1. `a lot`'s two occurrences were
already deduplicated to one entry on both sides, so it contributed no further
shift here, but a script where `lot` and `a lot` compete with an *otherwise
separate* existing `lot`-only usage could shift the count by more. The gap is
real, reproducible, and grows with how much the intent reading's corrections
and phrase merges diverge from lenient's — it is not a fixed offset and won't
always be the same number session to session.

### Is "Content words only (47)" a token count including repeats?

Yes, confirmed directly from `_engine/views.py:68`:

```python
content = [r for r in records if not r["is_function_word"]]
```

`records` is the full per-token stream (`build_profile()`'s first loop, one
record per token, `views.py:58-66`) — no deduplication happens here. Dedup
only happens afterward, building `distinct` (`views.py:73-82`), which is a
*different* list. So `content_only` counts every occurrence of every content
word, repeats included; `distinct` counts each identity once. That is
mechanically why "Content words only" is always ≥ "Repetition stripped" for
the same reading — it's the same words, pre- and post-dedup, not two
different definitions of "content word."

### The root inconsistency

Not that any one number is wrong — each is internally correct for what it
literally computes. The inconsistency is that **`summarise()`'s `distinct`
field never adopts the reading `_assessed()`/`detail()` chose**, so the Words
tile can show a lenient-reading count sitting directly above a card whose
every other figure — score, band, word chips — comes from the intent reading.
The two are only guaranteed to agree when intent scoring wasn't assigned at
all (lenient is used everywhere, by fallback), which is exactly the condition
under which nobody would notice a divergence to begin with.

## Summary — what needs deciding, not what needs building

Four separate, narrowly-scoped things, none built yet:

1. **Issue 1** — `unresolved`'s display value should be each token's `raw` form,
   not its normalised `token`/`d["original"]` form. Filtering logic unchanged.
2. **Issue 2, Bug A** — decide whether "awaiting review" should keep including
   words that were never sent to the model (reference-list misses like
   `flibbertigibbet`), or whether that deserves separate wording / a separate
   list from genuinely-pending review items.
3. **Issue 2, Bug B** — `unresolved`'s clause (b) should apply the same `names`
   exclusion the fraction already applies, so a confirmed proper noun stops
   appearing in "awaiting review" once it's been confirmed.
4. **Issue 3** — decide whether `summarise()`'s `distinct` field should switch
   to the assessed reading (matching what the rest of the card shows), and
   separately, whether the three toggle/tile labels should say which reading
   and which level of deduplication each one is — "Repetition stripped" and
   "Content words only" read as differing only by dedup, when they can also
   differ from the headline by *which correction pass* produced the count.

Issues 1, 2A and 2B are inside `_coverage()`, protected code, same function as
the Coverage/possessive fixes already approved on 20 Aug. Issue 3's fix, if
`summarise()` should switch readings, is in `api/score.py` — the unprotected
integration layer — since `summarise()` and `_assessed()` both live there; no
protected file needs to change for it. None of the four are built here per the
brief's instruction to report first.
