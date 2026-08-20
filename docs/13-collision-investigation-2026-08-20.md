# Investigation — "decided" reading as C1 (76), 20 Aug 2026

Read-only. Nothing in `api/_engine/`, `api/_intent/` or the reference data was
changed. Answers item 1 of the 20 Aug feedback-triage brief.

## Verdict

**Working as intended, and the number is real — but the label on screen invites
exactly the misreading it produced.** This is not a data error and not a
sense-disambiguation bug. It is the conservative homograph rule doing its job,
described in words that make the raw value look like a claim about the student.

## What the reference list actually holds

`decided` appears in `gse_vocabulary.json` **once**, and not as the past tense of
`decide`:

| Form | GSE | Band | POS | Definition |
|---|---|---|---|---|
| `decided` | 76 | C1 | **adjective** | "definite and easily noticed" |

That is the `decided` of "a decided advantage", "a decided improvement". It is a
genuine C1 word and a correct Pearson entry.

The verb lives under its own headword:

| Form | GSE | Band | POS | Definition |
|---|---|---|---|---|
| `decide` | 34 | A2 | verb | "to make a choice to do something…" |
| `decide` | 52 | B1+ | verb | "to be the reason for someone making a particular choice" |
| `decide` | 57 | B1+ | verb | "to be the reason why something has a particular result" |

## Why the face-value lookup lands on C1

`GseBank.resolve()` (`api/_engine/gse.py:114`) walks `lemma_candidates(token)`
in order and returns **the first candidate that has any senses at all**. For
`decided` the candidate order is `['decided', 'decide', 'decid']`, and
`decided` itself matches — so the adjective is returned and `decide` is never
consulted.

Nothing at that point knows the token is a past-tense verb. There is no
part-of-speech tagging in this path; `GseBank.categories()` exists and is used
by the spelling corrector's grammar tie-break, but `resolve()`/`describe()` do
not use it. The face-value reading is therefore a pure surface-form lookup, and
for `decided` the only surface-form entry is the C1 adjective.

`describe()` (`gse.py:190`) then calls `collision(form, gse)` (`gse.py:166`),
which looks *downward only* at the other lemma candidates, takes the
lowest-GSE sense of each, and flips if the gap exceeds `COLLISION_GAP = 38`.

## The three flagged words, measured

Reproduced directly against the live bank:

| Token | Face value | Scored as | Gap | Margin over the 38 threshold |
|---|---|---|---|---|
| `decided` | 76 (C1) adjective | `decide` 34 (A2) | 42 | **+4** |
| `selling` | 72 (B2+) noun, "the job and skill of persuading people to buy" | `sell` 22 (A1) | 50 | **+12** |
| `relaxing` | 60 (B2) adjective, "making you feel calm" | `relax` 21 (Pre-A1) | 39 | **+1** |

All three flip, so all three are scored at the low value. The C1 never reaches
the vocabulary score — it appears on screen only as the "before" column of the
flip.

## Which of the three answers applies

- **Data problem?** No. All three high entries are legitimate senses correctly
  levelled by Pearson.
- **Sense-disambiguation problem?** Only in the weak sense that there is no
  disambiguation at all at this point — `resolve()` prefers the surface form and
  has no POS signal. That is deliberate; the collision rule is the safety net
  built for precisely this, and it caught all three.
- **Working as intended?** Yes. `gse.py:66-70` states the trade explicitly:
  the rule resolves downward always, because "one ambiguous token is not
  evidence of a level, and we do not award what we cannot evidence."

## Two things worth Richard's attention anyway

### 1. The column label is doing the damage

The table says **"Taken at face value: C1 (76)"** next to the word `decided`.
Read plainly that says *this student used a C1 word*, which is what looked
wrong. What it actually means is *the only reference entry spelled this way is a
C1 adjective, which we are not going to credit.* The value is right; the phrase
"taken at face value" reads as an assessment rather than as a discarded lookup.

Nothing needs recomputing to fix this — it is wording on one column header.

### 2. `relaxing` clears the threshold by one point

`relaxing` flips on a gap of 39 against a threshold of 38. Had `COLLISION_GAP`
been 40, it would not flip and would score B2 (60) instead of Pre-A1 (21) — a
seven-band swing decided by a single GSE point.

That is worth knowing because `relaxing` is the case where the read-down is most
likely to be *wrong about the student*. In "it was a relaxing trip", the B2
adjective is the natural reading and the rule credits Pre-A1 `relax` instead.
The same applies to `selling` used as a gerund. The rule is behaving as
designed — the design under-credits by choice — but these are the cases where
that choice costs the most, and the margin on `relaxing` is one point.

`gse.py:72-77` already flags the threshold as calibrated on a dozen cases from
one batch and warns against tuning it to the boundary. Nothing here suggests
changing it; it does suggest that the next real batch should look at
near-threshold flips specifically.

## Not the cause

The brief guessed at `_intent/layer.py` and `_coverage()`. Neither is involved:
`grep -n collision api/_intent/layer.py` returns nothing, and `_coverage()`
counts resolved vs unresolved tokens, unrelated to homograph resolution. The
whole path is `GseBank.describe()` → `_engine/views.py:60` → `api/score.py:381`,
which deduplicates the flips for display.
