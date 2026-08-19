# Build brief for Claude Code — 19 Aug 2026

Written by the advisory Claude session, for the Claude Code session doing the
actual building in `C:\Users\richa\Desktop\Writing Marking V2 - GSE Based`.
Based on the audit at `docs/06-project-audit-19-aug-2026.md` (also saved to
the project) — read that first for full context on what exists and why.

## Constraints that do not change, no matter what task you're on

- **Never modify `api/_engine/` or `api/_intent/`.** This is calibrated,
  tested code. Every task below that touches interpretation or scoring
  works by calling functions in those folders, never editing them. Where a
  task seems to require an edit there, the design section explains the
  workaround — read it before concluding an exception is needed.
- **`api/score.py` is the integration layer and is NOT protected.** It's
  been edited repeatedly already and that's expected. New backend logic
  belongs here, gluing together calls into `_engine`/`_intent`.
- Interpretation (Translate, screen 3) and scoring (Dimensions, screen 4) are
  different steps. Translate must not compute a score; Dimensions must not
  re-interpret raw text.
- "Evidence" means scored, deterministic output. A list of hypotheses a
  marker can accept/reject is a "review," never "evidence."

## Recommended build order and why

1. Fix the ceiling-adjusted display (small, isolated, zero risk — do this
   first so it's off the list).
2. Split `DetailView` — move interpretation-only content out, leave only
   scoring/evidence. Do this **before** task 3, because task 3 adds new UI
   to the review tables, and you don't want to wire it into content that's
   about to move.
3. Build the approve/override mechanism. This is the actual blocker behind
   everything else in the audit.
4. Rewire Vocab's scoring call to run against the approved interpretation,
   now that task 3 gives it something to run against.
5. Steps-indicator cleanup on the Question screen — bundle in whenever
   convenient, no dependency on anything else.

Two items from the audit are explicitly **not** build tasks yet — see the
bottom of this document.

---

## Task 1 — Ceiling-adjusted score: fix the display

**Verified root cause** (checked directly against the current
`api/_engine/scoring.py` and `app/page.tsx`): `scoring.py`'s `score()`
already returns `reported` and `ceiling` fields, and `format_lines()`
already builds a 4-line summary (`Confident`, `Reported (ceiling-adjusted)`,
`Upper evidence`, `Highest credible item`). But `DetailView` in
`app/page.tsx` (~line 388-390) still hardcodes:

```tsx
<div>{d.score_lines[0]}</div>
<div>{d.score_lines[1]}</div>
<div>{d.score_lines[2]}</div>
```

— three lines, a leftover from before `format_lines()` grew a 4th line. The
ceiling-adjusted line currently shows *by accident* in the slot that used to
say "Upper evidence," and the real "Highest credible item" text silently
falls off the end (harmless only because the table below re-derives that
number separately from `sc.highest`).

**Fix:**
- Change that block to map over the full `d.score_lines` array rather than
  hardcoding 3 indices, so all 4 lines render, in order, deliberately.
- Add a dedicated table row for the reported/ceiling-adjusted score,
  parallel to how "Composite confidence" already gets its own row with a
  formula breakdown (~line 398-406). Use `sc.reported.score`,
  `sc.reported.band`, and the breakdown in `sc.ceiling` (`strength`,
  `trust`, `nudge`, `headroom`) the same way. Note the comment in
  `scoring.py` above `ceiling_adjusted()`: this formula is flagged
  "first-pass, uncalibrated" — the UI should probably say so too (a small
  caption, matching how other not-yet-validated content on Translate is
  labelled), rather than presenting it with the same confidence as the
  calibrated confident/upper numbers next to it.

---

## Task 2 — Split `DetailView`: move interpretation content to Translate

**Verified current duplication** (checked directly):

- The spelling audit table is genuinely rendered twice: `DetailView` builds
  it from `d.audit` (~line 462-473), and Translate's section 1 builds the
  same table from `single?.audit` (~line 831 onward) independently. This is
  true duplication — remove it from `DetailView`.
- `d.corrected_text` and `d.corrected_sample` are both shown in `DetailView`
  (~line 456-460 and ~529-538), with a note when they differ. Translate's
  section 1 only shows `single?.corrected_text` — **not**
  `corrected_sample`. This is a real gap, not just duplication: if a marker
  accepts a vocabulary proposal in section 6 (e.g. "bote" → "boat"),
  Translate's "Intended reading" panel in section 1 currently does **not**
  reflect that acceptance, because it never reads `corrected_sample` at
  all. Fix this as part of the split: section 1's "Intended reading" should
  show `corrected_sample` (falling back to `corrected_text` if
  `corrected_sample` isn't present), not `corrected_text` alone.
- The homograph-collision table (`d.collisions`, ~line 561-583) is **not**
  currently duplicated — it only exists in `DetailView`, not on Translate at
  all. This one is a relocation, not a dedup: it's interpretation content
  (a case where the corrector picked a lower-frequency reading of a real
  word) and belongs on Translate, most naturally folded into section 1 or
  hung off section 6 (Vocabulary review) since it's the same kind of
  "here's a reading, confirm it" object as the other rows there.

**After the split, `DetailView` should show only:** the two headline scores
(Vocabulary, Spelling), the scoring table (credible words, composite
confidence, confident/reported/upper/highest), and the excluded-word note.
Nothing about spelling audit, corrected text, or collisions belongs there
once this is done.

---

## Task 3 — The approve/override mechanism (the foundational piece)

This is a real design, not just a UI addition, so read the whole section
before starting.

### The state shape

Client-side, per scored sample, keep a map of marker overrides keyed by the
token each review row is about:

```ts
type Override = {
  answer: "replacement" | "not_a_misspelling" | "proper_noun" | "unrecoverable";
  proposed?: string;   // only set when answer === "replacement"
};
type Overrides = Record<string, Override>;   // keyed by the written token
```

Only tokens the marker actually changed need an entry — everything else
implicitly keeps the model's original decision. This mirrors the shape
`_intent/review.py`'s `validate()` already produces
(`answer`/`proposed`/`accepted`/`rejected_because`/`corrected`), so nothing
new needs inventing on the data-model side, only a UI to populate it and a
backend path to apply it.

### The UI

Each row in Vocabulary review (section 6) — and eventually Grammar review
once that exists — needs controls to: accept the model's answer as-is,
supply a different word (`replacement`), or say "not a misspelling" /
"it's a name" (`proper_noun`) / "genuinely can't tell" (`unrecoverable`).
Store the marker's choice in the `Overrides` map on change; a "re-score with
my corrections" action sends it back to the API.

### How overrides re-enter scoring without touching `_intent/`

This is the part that needs care. The pipeline that turns model verdicts
into a corrected sample and two scores (`_intent/layer.py`'s `_apply()`,
called from `enrich()`) is internal to the protected file — but it's built
out of composable pieces, and `score.py` can drive those pieces directly
with a **synthetic verdict set** built from the marker's overrides, instead
of a real model response. Concretely, in `score.py`:

1. Re-run `_engine.analyse.analyse()` on the same text to get the
   deterministic `result` (cheap, local, no network call).
2. Call `intent_layer.flag(text, result, bank, corrector)` to reproduce the
   same candidate token list (`items`) the first pass used — this is
   deterministic given the same text, so it doesn't need to be persisted
   between requests.
3. Build a synthetic `raw = {"verdicts": [...]}`, one entry per item in
   `items`: for tokens with no override, carry forward the model's original
   answer (the frontend already has this in `intent_audit` — round-trip it
   back in the request, or re-fetch the original decisions server-side);
   for tokens with an override, use the marker's `answer`/`proposed`
   directly, with `confidence: 1.0` and `reason: "marker override"`.
4. Call `intent_layer._apply(result, items, raw, bank, corrector, note)` —
   yes, the underscore-prefixed function; it's still importable, it's just
   naming convention, not a real access restriction — to regenerate
   `corrected_sample`, `spelling_score`, `vocabulary_score`, and
   `intent_decisions` from the marker-adjusted verdicts. No OpenAI call
   happens on this path at all, since `raw` is synthetic.
5. `_apply()` mutates the `result` dict it's given in place, so pass it a
   fresh `result` from step 1, not one that's been used elsewhere.

This keeps every line of `_intent/layer.py` untouched while still reusing
its exact validation and scoring logic for the override path — the marker's
correction goes through the identical acceptance checks (`form_test`,
known-word check, etc.) a model proposal would, which is the right
behaviour: a marker typo shouldn't silently break the corrected sample
either.

**Before building this, sanity-check the design above against the actual
current code** — it's based on a direct read of `_intent/layer.py` and
`_intent/review.py` as of 19 Aug 2026, but re-verify signatures haven't
shifted since.

### Open UI question, not resolved here

Whether "re-score with my corrections" is a per-row action (immediate) or a
batch action at the bottom of the review section (apply several overrides
at once, then re-score) is a UX call, not an architecture one — pick
whichever is simpler to build first; it can change later without touching
the backend design above.

---

## Task 4 — Vocab scoring: run against the approved interpretation

Once task 3 exists, change `runSingle()`'s contract: the *first* POST (on
"Process sample") still runs the full first-pass pipeline as it does today,
routes to Translate. A *second*, separate action — "re-score with my
corrections," from task 3 — is what should call into Dimensions with the
override-adjusted result. Dimensions should read from whichever result is
freshest (override-adjusted if the marker has re-scored, first-pass
otherwise), and the screen should say plainly which one it's showing.

Do **not** make Dimensions silently show first-pass data with no
indication that it predates any marker correction — that's exactly the
"everything downstream just trusts the API's first-pass output
unconditionally" problem the audit flags.

---

## Task 5 — Steps indicator cleanup (low priority, bundle in whenever)

The three-stage `Steps` component on the Question screen (Input / Spelling /
Score) predates the six-screen restructure and no longer matches it — there's
no separate "Spelling" screen anymore, that content moved to Translate.
Either remove it or relabel it to match what Question screen actually still
does (Input → Score, two stages, since spelling correction is no longer a
distinct visible stage here).

---

## Not build-ready yet — do not start these without a decision first

- **Sentence-level "couldn't confidently interpret" escalation threshold.**
  The audit flags this as genuinely undecided — what makes a whole sentence,
  not just one word, get flagged as uninterpretable. Don't invent a
  threshold to fill the gap; ask Richard, or leave the current word-level-only
  behaviour as is until he specifies one.
- **Grammar's intent-inference detector.** Real, scoped, documented (see
  `docs/05-communicative-effect-and-translation-screen.md`'s worked
  example), but a much bigger effort than anything else here — no EGP
  structure-detection layer exists anywhere in the codebase to build on. Not
  scheduled. Don't attempt a partial version; a fake grammar detector is
  worse than the current honest "not built yet" placeholder.
