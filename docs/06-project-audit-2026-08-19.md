# Project Audit — 19 Aug 2026

## Status update (19 Aug 2026, evening)

All five priority build tasks from
`07-build-brief-for-claude-code-19-aug-2026.md` are done and independently
verified against the actual Desktop files (not just taken on the builder's
word) — ceiling-adjusted score display, the `DetailView`/Translate split
(including the real gap it surfaced: accepted vocabulary corrections weren't
reaching the "Intended reading" panel — fixed), the marker approve/override
mechanism, Vocab scoring reading the freshest interpretation, and the
Question-screen Steps cleanup. The one follow-up that came out of that work —
Coverage 100% reading as a contradiction next to "still unresolved: will
always" — is also done and verified, as two honestly separate statements
instead of one merged one. `api/_engine/` and `api/_intent/` remain untouched
throughout all of this, confirmed each time by reading the actual diffs, not
just the build reports.

Detail on all of that stays below as the historical record of what was found
and why. Items 6 and 7 in the prioritized list are still genuinely open — see
their entries below, unchanged.

**Not under version control.** This directory has a `.gitignore` but no `.git`
— `git rev-parse` reports "not a git repository". Nothing here has been
committed anywhere, so the only copy of today's work is the working tree, and
the "verified against the actual Desktop files" checks above were reads of that
tree rather than of diffs. Worth resolving before more is built on top of it.

**Operational note, worth keeping:** stopping `next dev` (or `vercel dev`) via a
task-runner's stop/kill control can leave the underlying node process still
holding port 3000, which then keeps serving stale build output and makes the app
look broken until that process is killed directly (e.g. by PID, not just by
stopping the task that launched it). Seen with both `vercel dev` and plain
`next dev`. If the app looks broken after a restart and the code looks right,
check for an orphaned process on port 3000 before assuming a real bug.

## Where this sits

Three source systems exist: LENS (`language-awareness-pipeline`, evidence-only,
has the only EGP grammar detection anywhere, correct-structures-only), GSE
Profiler (Python, vocabulary/spelling origin, calibrated scoring), and
gse-vercel-app (deployed, most advanced, vocab+spelling+AI intent layer). The
new build, `Writing Marking V2 - GSE Based`, was seeded from gse-vercel-app's
engine and is where all of today's work has happened. The old projects stay
frozen as reference.

## What's built, screen by screen

**1. Landing** — done. Six-dimension overview, the 11-band scale rendered as
a proper number line (bands positioned at their real score value, not evenly
spaced — A2+→B1's gap is visibly smaller than C1→C2's, matching `SCORE_BANDS`
exactly), the four-step process summary.

**2. Question** — done. Task type, target CEFR level (floor, not exact),
word count min/max with an auto-computed midpoint, question prompt, and the
single/batch text input. Submitting routes straight to Translate rather than
Dimensions — the right default, since interpretation comes before scoring.
Steps indicator now matches reality (Input → Score).

**3. Translate** — done, all eight sections in the finalized order: as-written/
intended text with highlighting (vocabulary correction, grammar correction —
not built, couldn't-confidently-interpret, three visually distinct states);
basic script statistics (word/sentence/paragraph counts, pure quant, no AI
disclaimer, correctly separated from the qual content around it); communicative
message summary; communicative level (descriptor-anchored, not a bare band —
the construct-validity fix held); effect on reader; vocabulary review (genuinely
separate from section 1's deterministic corrections — uses real `intent_audit`
data, and is now the place a marker actually overrides a proposal, with the
override propagating back into the "Intended reading" panel and into scoring);
grammar review (honest "not built yet" placeholder); other reviews
(placeholder). Three-state handling throughout (real data / not-available-with-
reason / worked example) means nothing here pretends to be live when it isn't.
Collisions table relocated here from Dimensions, labelled as not
marker-overridable (a deterministic engine decision, not a model proposal).

**4. Dimensions** — Vocabulary only, via `DetailView`, now genuinely
scoring-only: two headline scores, the scoring table (credible words, composite
confidence, confident/reported-ceiling-adjusted/upper/highest), coverage note,
excluded-word note. Reads whichever interpretation is freshest (first-pass or
marker-adjusted) and says which, via two independent banners — interpretation
source, and separately, whether there are unapplied corrections — deliberately
not merged into one banner, since a marker who re-scores and then changes their
mind again would otherwise see stale numbers vouched for as current.

**5. Evidence, 6. Final score** — honest "not built yet" placeholders.

## Architecture principles locked in (should hold for every future section)

- Interpretation and scoring are different steps, done by different screens.
  Translate interprets; it does not score. (Richard's stated verdict, still
  the load-bearing rule.)
- Three access patterns for downstream constructs: raw only (Communicative
  Effect), raw + approved interpretation (Spelling, Grammar), approved
  interpretation only (Content Quality, plausibly). Not "everything reads
  from Translate instead of raw text" — that was an error, caught and fixed.
- Qual vs quant is a tag on every metric, orthogonal to CEFR-sourcing-rigor.
  Quant = deterministic, reference-framework-backed. Qual = judgment call,
  AI or human. Communicative Effect is qual but CEFR-anchored; Punctuation is
  quant but weakly CEFR-grounded — the two axes genuinely diverge.
- "Evidence" is a reserved word for scored, deterministic output. Hypothesis
  review screens are "reviews," not "evidence" — this got corrected once
  already (Vocab/Grammar evidence → Vocab/Grammar review) specifically to
  protect this distinction.
- The written+intended pair pattern (`spelling_score.py`'s `score()` takes
  both fields) is the template every future construct's scoring should copy,
  not reinvent.
- The CEFR Self-Assessment Grid (official Council of Europe document,
  uploaded 19 Aug) grounds the qualitative dimensions — Task Achievement,
  Organisation/Coherence, Content Quality, Style & Register, Communicative
  Effect — and explicitly does NOT ground Vocabulary or Grammar, which have
  their own itemized reference frameworks (GSE, EGP).
- **New, from the override mechanism build:** when two true numbers could be
  read as contradicting each other (e.g. Coverage 100% next to "still
  unresolved"), the fix is to state them as two separate, clearly-scoped
  sentences — never to merge them into one, and never to change a
  protected/calibrated figure's definition just to make the prose read smoother.

## Open items, prioritized

Items 1-5 below are the original list at the time of the first audit. All five
are now built and verified — see the status update at the top of this document
for what changed. Left in place, unedited, as the historical record of what was
found and why; items 6-7 remain open exactly as originally stated.

1. **Vocab's data flow doesn't yet reflect the new architecture — see the
   dedicated note below.** This is the live item.
2. **The ceiling-adjustment score (`reported`/`ceiling` in `scoring.py`,
   built earlier today) doesn't appear in the current `DetailView`.** Flagged
   twice now across two build iterations — worth confirming whether the
   patched file is actually the one running, or whether it needs reapplying.

   *Verified 19 Aug 2026 (Claude, against the live Desktop copy):* the engine
   side is real — `_engine/scoring.py`'s `score()` does compute and return
   `reported`/`ceiling`, and `format_lines()` was updated to a 4-line summary
   (Confident, Reported/ceiling-adjusted, Upper, Highest). But `DetailView` in
   `app/page.tsx` only ever rendered `score_lines[0]`, `[1]`, `[2]` — three
   lines, a leftover from the old 3-line format. So right now the
   ceiling-adjusted line DOES show, by accident, in the slot that used to hold
   "Upper evidence" — and the old line 3 ("Highest credible item" as prose)
   silently drops off the bottom of that array slice (harmless only because the
   table below independently re-renders the highest-item numbers from
   `sc.highest`, not from that dropped text line). Net effect: the new field is
   visible, but by coincidence of array indexing, not by design, and it has no
   structured table row of its own — unlike Composite Confidence, which gets a
   full strength/trust/breakdown row. Not yet fixed; needs a deliberate row, not
   a relabeled accident.
3. **No approve/override mechanism exists yet between Translate and
   Dimensions.** Every hypothesis review (vocabulary corrections, the
   eventual grammar ones, the communicative-message summary) is designed to
   be marker-correctable, but there's no UI wiring for it yet, and no
   mechanism for a correction to propagate downstream. Currently everything
   downstream just trusts the API's first-pass output unconditionally.
4. **`DetailView` duplicates content that now belongs to Translate.** It
   still renders the full spelling audit trail, the corrected-version
   display, and the homograph-collision table — all of which either already
   exist on Translate (audit) or arguably should move there rather than
   being shown twice.
5. Minor: the old three-stage `Steps` indicator on the Question screen no
   longer corresponds to the six-screen structure (no separate "Spelling"
   screen anymore). Cleanup, not urgent.
6. **Still open.** Not yet decided: the threshold for escalating a "couldn't
   confidently interpret" flag from one word to a whole sentence (from the
   highlighting requirements discussion). Needs Richard's decision — don't let
   a build session invent a threshold to fill this gap.
7. **Still open, unscheduled.** Grammar's intent-inference detector — the real
   missing engine piece, precisely specified (see
   `docs/05-communicative-effect-and-translation-screen.md`'s worked example)
   but a much bigger effort than anything else here — no EGP structure-detection
   layer exists anywhere in the codebase to build on.

## Vocab scoring: reuse the engine, not the old process

Direct answer to "make sure vocab scoring doesn't completely use the GSE
scorer as-is."

**Keep, unchanged:** the math in `scoring.py` — `score_for_gse`,
`weighted_percentile`, `_step_down`, `apply_range`, `composite_confidence`,
`ceiling_adjusted`. This is calibrated, tested against a real batch, and nothing
about today's architecture work changes any of it. Don't rebuild it; call it.

**Resolved 19 Aug 2026** — the data flow now does this properly. The old
one-shot `mode: "single"` call (bundling spelling correction and vocabulary
scoring into a single non-reviewable response) is still there for the first
pass, but a new `mode: "override"` on `api/score.py` re-runs the deterministic
engine, reproduces the same candidate token list via `intent_layer.flag()`, and
builds a synthetic verdict set from the marker's overridden answers — going
through the exact same acceptance checks (`form_test`, known-word check) a model
proposal would, without ever modifying `_intent/layer.py` or touching the file.
No network call on that path. Vocab's Dimensions section now reads
`reported`/`ceiling`, and shows scoring/evidence only — the
interpretation-review content (spelling audit, corrected text, collisions) moved
to Translate, ending the duplication that used to live in `DetailView`.
