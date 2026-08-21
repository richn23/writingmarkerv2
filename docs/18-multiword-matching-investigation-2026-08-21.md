# Investigation — why multi-word entries are excluded, 21 Aug 2026

Task B of doc 16, report-before-building. **Read-only: no code changed.**

## Why they were excluded

Not unfinished work, and not a double-counting guard. It is a **deliberate
deferral, with the reason written down** — `api/_engine/gse.py:12-15`, in the
module docstring:

> 2. MULTI-WORD ENTRIES ARE EXCLUDED FROM MATCHING **in v1**, and the count is
> reported so the exclusion is visible rather than silent. Matching phrases in
> running text is a separate problem (inflection inside the phrase, gaps,
> literal-vs-idiomatic) and mixing it in here would muddy the spelling result.

So of the three possibilities in the brief, it is the first: **matching
complexity was deferred, not rejected.** "in v1" is explicit, the count is
surfaced in the health check on purpose, and the three hard sub-problems are
named.

One clause does change the plan, though: *"mixing it in here would muddy the
spelling result."* That is a specific constraint, not throat-clearing. The
spelling corrector calls `bank.knows()` and `bank.resolve()` per token; if
`GseBank` started matching phrases, every one of those per-token calls would
change behaviour. **The fix must not go inside `GseBank`'s lookup path.**

## What the data actually looks like

Measured against the live file, not assumed:

| | Count | Share |
|---|---|---|
| Multi-word entries | 6,109 | 100% |
| Plain word-sequences (directly matchable) | **4,979** | 81.5% |
| Carry `( )`, `...`, `!`, `?`, `/`, `,` or `'` | **1,091** | 17.9% |

That 17.9% is the first thing the brief's framing misses. Entries like
`if it's any comfort (to you)`, `I abhor...` and `get off!` are not plain
phrases: they carry optional-part parentheses, elision placeholders and
punctuation. They cannot be string-matched as stored, and roughly one in five
of the 6,109 is in that state. A first pass should take the 4,979 and report
the rest as out of scope rather than silently failing on them.

Of the 4,979 plain entries there are **4,413 distinct phrase strings**, of which
**403 carry more than one sense**, sometimes across an enormous range:

| Phrase | GSE range | Spread |
|---|---|---|
| `go out` | 19–65 | 46 |
| `take off` | 22–67 | 45 |
| `come in` | 26–67 | 41 |
| `stand up` | 30–70 | 40 |

`GseBank._primary()`'s existing rule — lowest sense wins — resolves this the
same way it does for single words, and conservatively. For the priority case
that is exactly right: **`a lot` has three senses (26, 34, 43) and would credit
at GSE 26, A1**, which is the outcome the brief asks for.

## The false-positive risk, quantified

**149 plain phrases are composed entirely of common function words** — `a lot`,
`go out`, `take off`, `get up`, `no one`, `at least`, `up and down`, `some more`.
These are the frequent ones, so they carry both the most benefit and all of the
risk.

Two distinct failure modes:

1. **Substring capture.** `the sick` (B2+ 70, "people who are ill as a group")
   would match inside *"the sick man went home"*, crediting B2+ for an ordinary
   A2 construction. This is worse than the current under-crediting, because it
   inflates rather than deflates.
2. **Literal-vs-idiomatic.** `take off` at GSE 22 means an aircraft leaving the
   ground; at 34, removing clothing; at 62 and 67, two further senses. Lowest-
   sense-wins keeps it conservative, but the phrase still gets credited when the
   student may have written a literal verb-plus-preposition that is not the
   listed unit at all.

Neither is a reason not to build it. Both are reasons the first version should
probably be restricted — e.g. to phrases of three words or more, or to phrases
containing at least one content word — with the frequent function-word phrases
handled as a deliberate second step. `a lot` would need to be an explicit
exception to that restriction, since it is the priority case and is two function
words.

## The design questions, answered from the code

### Overlap: there is already a convention, and it is span-supersedes-tokens

`corrected_sample()` in `_intent/layer.py` already collapses a two-token span
into one. The join mechanism (`play grand` → `playground`) sets `skip = idx + 1`
at line 396, and the loop's first statement (`if idx == skip: continue`, line
385) swallows the second token entirely. One stream entry is emitted for the
pair; `_coverage()` and `credible_words()` never see the constituents.

So the answer is **the multi-word match supersedes its individual tokens**, and
that is not an invention — it is the existing behaviour for joins. Nothing
double-counts because the constituents never reach the scorer.

`_coverage()` itself has no span concept at all; it counts distinct content word
*types* from `result["original"]["distinct"]`. It inherits span ownership from
the stream rather than implementing it, which is why following the join
precedent is enough.

### Which text: the corrected stream, confirmed

Single-word credit runs on the intent reading, not the raw text:
`_apply()` → `corrected_sample()` builds `stream` → `_profile(stream, bank)` →
`build_profile()` → `bank.describe(t["lower"])`. Multi-word matching should run
on the same stream, for the same reason.

### Strictness: entries are exact lowercase strings, no lemma forms

`multi_word` stores the raw entry dicts. The `word` field is a literal phrase
(`decide on`, `task force`); there is no lemma or pattern field. So inflection
inside the phrase (`paid up` for `pay up`) is not supported by the data and
would need to be generated — `lemma_candidates` applied per-word inside the
phrase would be the obvious route, but that multiplies the false-positive
surface and should not be in a first version.

## The thing that changes the plan

The brief assumes this can be built entirely in the unprotected integration
layer. **It cannot, quite** — not if it is to follow the join precedent.

Span collapsing happens inside `corrected_sample()`, and profiling happens
inside `_apply()`, both in protected `_intent/layer.py`. There is no hook
between them for `score.py` to intervene on the normal path.

Two ways forward, both real:

**A. Wrapper bank, no protected edit.** `build_profile(stream, bank)` calls
`bank.describe(...)`, so a `MultiWordBank` defined in `score.py` that delegates
to `GseBank` and adds phrase lookups would be picked up without touching
`_engine/` or `_intent/`. `score.py` would drive `corrected_sample()` →
collapse spans → `_profile()` itself, exactly as `rescore_with_overrides()`
already drives `flag()` → `_apply()`. Keeps the protected boundary intact;
costs a second code path that has to stay in step with `_apply()`.

**B. Edit `_intent/layer.py`.** Collapse multi-word spans in `corrected_sample()`
next to the join logic, where the convention already lives. Smaller and more
honest structurally — it puts the behaviour where the identical existing
behaviour is — but it is protected code and needs the same explicit approval the
Coverage and possessive fixes got.

I have not chosen between them. A is the default given the brief's stated
constraint; B is what I would pick if the protected boundary were open, because
duplicating `_apply()`'s sequence in `score.py` is how the two drift apart.

## Recommended first version, if this proceeds

1. Plain entries only (4,979); report the 1,091 punctuated ones as out of scope.
2. Exact contiguous match on the corrected stream, no inflection.
3. Lowest-sense-wins, reusing `_primary()`'s existing rule.
4. Span supersedes its tokens, following the join precedent.
5. Longest match first, so `a whole lot` wins over `a lot`.
6. Restrict to phrases with at least one content word, plus an explicit
   allowlist for the frequent function-word phrases we actually want — starting
   with `a lot`.

Point 6 is the one worth arguing about, and it is a judgement call rather than
something the code can settle. Without it, `the sick` and `go out` start firing
on ordinary text.
