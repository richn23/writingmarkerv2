# GSE vocabulary profiler — web app

Paste one sample or upload a batch CSV. Get a confidence-weighted vocabulary
level, a 0–100 score, and the full working behind both.

Next.js frontend, **Python scoring engine**. The engine in `api/_engine/` is the
GSE_PROFILER's engine, copied verbatim — not a re-implementation — so the deployed app and
the local batch tool cannot drift apart.

---

## Deploy

```
vercel
```

That is the whole thing. No environment variables, no database, no build step
beyond `next build`. `vercel.json` sets `maxDuration: 300` and `memory: 2048`
for the Python function.

**The one thing to check on the first deploy:** open `/api/score` in a browser.
It should return JSON with the reference-list counts (34,795 entries). If it
404s, Next.js is swallowing the route — see *Routing* below.

### Local

```
npm install
npm run dev        # frontend on :3000
vercel dev         # frontend AND the Python function
```

Plain `next dev` will not serve `/api/score` — that is a Vercel function, not a
Next.js route. Use `vercel dev` when you need both.

---

## How it works

**Three modes, one endpoint** (`POST /api/score`):

| body | returns |
|---|---|
| `{ mode: "single", text }` | full result for one sample |
| `{ mode: "batch", rows: [{ id, text }] }` | one summary per row |
| `{ mode: "detail", id, text }` | full result for one row |

Batch deliberately returns summaries only. Full detail for 100 samples is
**~16 MB** of JSON and Vercel caps a response at **4.5 MB**. Summaries for 100
come to ~47 KB; detail for a single sample is ~90 KB and is fetched when a row is
opened. The frontend sends batches in chunks of 100 for the same reason.

**Measured on a real batch of 100 messy exam scripts:**

| | |
|---|---|
| Cold start | 1.2 s |
| One sample | 2.3 s |
| Batch of 100 | 31 s (limit 300 s) |
| Batch response | 47 KB (limit 4,500 KB) |
| Detail response | 89 KB |

### The staged flow

1. **Input** — paste, or drop a CSV. The answer column is found automatically
   (`answer_1`, `text`, `script`, `response`…), and `MOE score`, `Human score`,
   `task_type`, `cefr_level` are carried through if present.
2. **Spelling** — the corrected version is shown in full, with every correction
   listed: what it was, what it was read as, why, the confidence, and what it did
   to the band. Words judged not-language are listed separately and never scored.
3. **Score** — the three-line level with its working underneath, the band chart
   written-vs-corrected, the same level under all three readings, and the four
   word views.

---

## What was replaced, and why

The TypeScript engine (`lib/lemmatize.ts`, `lib/spellcorrect.ts`, `lib/gse.ts`,
`lib/profile.ts`, `lib/scoring.ts`, `lib/tokenize.ts`, `scripts/`) is gone.
Keeping two implementations of the same spec is how they quietly disagree — and
the Python one carries work the TypeScript port predates:

- a hand-built irregular table, comparative/superlative handling, British
  spellings and apostrophe-less contractions
- **junk detection** — keyboard mashing, held keys, keyboard rows, repeated
  phrases, platform text. Without it a spellchecker turns noise into vocabulary:
  on the first real batch `ggh → gogh`, `rihur → ruhr`, and two scripts the
  ministry marked NVS came out at C1.
- **run-together splitting** (`Iplay` → `i play`, `HEISGOTIS` → `he is got is`)
- **the evidence range** — every valid script is scored, with the level clamped
  into the band range that much evidence can support
- correction targets restricted to words in the GSE list, which is what turns
  `frands → fronds` into `frands → friends`

`app/page.tsx` keeps the paste/upload interface and adds the staged view and the
per-sample breakdown. `app/layout.tsx` is unchanged.

---

## Routing

Vercel's Python runtime and the Next.js App Router do not share a routing tree.
The Python function lives at `api/score.py` and is served at `/api/score`; Next.js
routes live under `app/api/`. There is no `app/api/score/` directory, so nothing
competes for the path.

The old `app/api/analyze/route.ts` has been removed. If you ever add a Next.js
route at the same path as a Python function, Next.js wins and the Python function
becomes unreachable.

---

## Layout

```
app/
  layout.tsx           unchanged
  page.tsx             staged UI + per-sample breakdown
api/
  score.py             the Vercel function — single / batch / detail
  _engine/             the LENS engine, verbatim
    gse.py             load and index the list; lowest-sense lookup
    lemmas.py          inflection, contractions, British spellings
    junk.py            telling language from noise
    spelling.py        non-word detection and correction
    views.py           tokenising and the four views
    scoring.py         confidence-weighted level and the 0–100 score
    analyse.py         the pipeline
  _data/
    gse_vocabulary.json    34,795 entries (5.1 MB — trimmed to the fields the
                           engine reads, from 14.5 MB)
    english_words.txt      128k known words, for non-word DETECTION only
vercel.json
requirements.txt       empty on purpose — standard library only
```

Directories under `api/` beginning with `_` are not routes, so the engine and the
data are bundled but never served.

---

## Known limits

- **Multi-word GSE entries are excluded** — 6,109 of 34,795 (17.6%). Matching
  phrases in running text is a separate problem.
- **Real-word errors are not detected** (`their`/`there`, `ant`/`aunt`). Only
  non-words are corrected, which is what keeps false corrections at zero.
- **GSE levels are receptive**, applied here to productive writing. A deliberate
  simplification, not an oversight.
- **The top end is compressed.** Scripts marked B2/B2+/C1 by a human tend to come
  out B1+ on the confident level. Most words in any English text are common ones,
  so the 80th percentile does not move much with proficiency. Fixing it means
  fitting the percentile→band mapping to marked data.
- **500 rows per request**, and the frontend chunks at 100.
