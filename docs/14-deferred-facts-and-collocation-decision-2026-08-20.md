# Deferred facts and the collocation decision — 20 Aug 2026

Appendix to the 20 Aug feedback-triage brief, filed separately so it isn't lost
in a brief whose main items are already built. **Nothing here is scheduled.**
Items 1–4 of that brief are done (commits `5414717`, `7a99dec`); everything
below was explicitly marked out of scope for it.

Each item below is a fact the current data already supports, or nearly
supports. They are recorded to be scoped into their own brief once the
Evidence Collection restructure has been tested in use.

## Vocabulary profile

- **Out-of-reference-list word count** — words carrying no GSE band at all.
  Distinct from an unrecoverable spelling: the word was read fine, it simply
  isn't in the reference list. Already visible per-word (`matched: false` on
  every word record); never counted as a figure.
- **Reaching-beyond-safe-zone attempts** — high-band words attempted and
  landed wrong. Needs spelling severity cross-referenced against the word-level
  CEFR band. Both halves exist (`spelling_score_detail.detail` carries `band`
  and `severity` per error); nothing joins them today.
- **Ceiling vs floor spread** — highest CEFR-tagged word used against the
  lowest, as one span. Different from the donut, which shows distribution shape
  rather than range.
- **Collocation / multi-word unit use** — has a decision attached rather than
  just a deferral. See the section below.

## Spelling profile

- **Consistency per word (belief vs slip)** — already computed inside the cost
  formula (`persistence_for()`, doc 10), where a repeated identical wrong form
  costs 1.3×. Never surfaced as a readable fact.
- **Correction confidence distribution** — the per-correction confidences
  (0.95 / 0.77 / 0.68 …) are already returned per row. Their spread is not shown
  as a fact of its own.
- **Band-based error rollup** — doc 10's documented "one honest gap". Worth
  keeping its true size when scoped: `band` already exists on every error row,
  so a *count* per band is an aggregation in `score.py` or client-side, not new
  engineering. A *rate* per band is a bigger job — the denominator needs the
  correctly-spelled attempts, which never reach `detail`, so that version does
  require a change inside the protected `spelling_score.py`. Decide which of the
  two is wanted before starting.

## New "Supporting data" section

- **Lexical diversity / repetition rate** — the gap between "Every word" and
  "Repetition stripped" counts. Both already computed; never stated as a ratio.
- **Content-word ratio** — content words against total. Same situation.

## Collocation review — decision recorded, not built

**The decision, as taken:** the eventual version is evidence, derived from GSE's
own collocation reference data. The interim version is an LLM-judged pass,
built and labelled as a **review**, never as evidence — the standing rule from
doc 06 is that "evidence" is reserved for scored, deterministic output, and
anything a marker accepts or rejects is a review. Interim scope: take the
intended/corrected sample, ask the model to identify collocations and flag which
read as natural or unnatural; surface it as its own review section with the same
AI-generated labelling used on Communicative Level; report only, no score, and
nothing downstream may depend on it. When real GSE collocation data exists, the
interim version is **replaced, not extended** — the same pattern as Grammar's
placeholder.

That decision stands. One factual correction to the premise underneath it:

### The reference data is not simply absent

The appendix states GSE's collocation reference data "doesn't exist in the
codebase yet (confirmed: no collocation or multi-word-unit detection anywhere)".
Checked directly, that is half right, and the half that is wrong changes what
the eventual build costs.

**What is absent:** any detection or matching logic. `grep -rni colloc` over
`api/` and `app/` returns one passing mention in a prompt comment
(`_intent/review.py:126`) and nothing else. No multi-word unit is ever matched
against a script.

**What is present:** `gse_vocabulary.json` already carries **6,109 multi-word
entries**, each with its own GSE number and CEFR band. They are loaded at
startup into `GseBank.multi_word` (`api/_engine/gse.py:105-107`) and then
deliberately excluded from matching. The count is already reported in the health
check as `multi_word_excluded: 6109`.

By length: 3,661 two-word, 1,122 three-word, 732 four-word, and 594 longer. By
kind they are phrasal verbs, fixed phrases and multi-word nouns — a sample:

| GSE | Band | Category | Entry |
|---|---|---|---|
| 50 | B1 | phrasal verb | `decide on` |
| 51 | B1+ | phrase | `by hand` |
| 54 | B1+ | phrase | `at least` |
| 60 | B2 | phrasal verb | `get around` |
| 64 | B2 | phrasal verb | `pay up` |
| 73 | B2+ | noun | `task force` |
| 79 | C1 | phrasal verb | `knock back` |

**Why this matters for scoping.** These are levelled multi-word *lexical items*,
not collocation pairings — they will not tell you whether "make a decision"
reads naturally, which is the judgement the LLM interim step is for. So the
interim decision above is unaffected.

But it does mean **multi-word unit use is buildable deterministically today**,
from data already in the file, and that would be *evidence* rather than review:
match these 6,109 entries against the corrected sample and report which the
student produced, at what level. That is a different and much cheaper task than
waiting for collocation data that genuinely isn't there — and today the engine
silently drops every one of these, so a student writing "task force" or "knock
back" gets no credit for it at all.

Worth splitting into two items when this is picked up, rather than one:

1. **Multi-word unit detection** — deterministic, evidence, data already
   present, no new reference material needed.
2. **Collocation naturalness review** — LLM-judged interim as decided above,
   replaced when real GSE collocation data exists.

Conflating them would either delay (1) behind data it doesn't need, or let (2)
inherit an "evidence" framing it must not have.
