# Claude Code prompt — build and deploy the GSE vocabulary profiler

Copy everything below the line into Claude Code, running in
`C:\Users\richa\Desktop\gse-vercel-app`.

---

I have a Next.js + Python app at `C:\Users\richa\Desktop\gse-vercel-app` that
needs building, verifying and deploying to Vercel. The code is already written
and tested — your job is to get it onto Vercel and prove it works, not to
redesign it.

## What this is

A vocabulary scoring tool for student exam writing. A Next.js frontend calls a
**Python** serverless function that scores writing against the Pearson GSE
vocabulary list. Two input modes: paste one sample, or upload a batch CSV.

## Step 1 — check the files are in place

The folder should contain exactly this:

```
C:\Users\richa\Desktop\gse-vercel-app\
  app\layout.tsx
  app\page.tsx
  api\score.py
  api\_engine\__init__.py
  api\_engine\gse.py
  api\_engine\lemmas.py
  api\_engine\junk.py
  api\_engine\spelling.py
  api\_engine\views.py
  api\_engine\scoring.py
  api\_engine\analyse.py
  api\_data\gse_vocabulary.json      (about 5.1 MB)
  api\_data\english_words.txt        (about 1.2 MB)
  vercel.json
  requirements.txt                   (empty on purpose — stdlib only)
  package.json
  tsconfig.json
  next.config.js
  next-env.d.ts
  .gitignore
  README.md
```

All of these should already be present. If any are missing, there is a
`gse-vercel-app.zip` in the same folder holding a complete copy — unzip it over
the top. (You can delete that zip once everything checks out.)

## Step 2 — delete the dead TypeScript engine

An earlier version of this app had a TypeScript scoring engine. It has been
replaced by the Python one and **must go**, because two implementations of the
same spec quietly disagree. Delete if present:

```
lib\                      (the whole folder — gse.ts, lemmatize.ts, spellcorrect.ts,
                           profile.ts, scoring.ts, tokenize.ts, data\gse-raw.json)
scripts\                  (build-gse-index.ts, test-profile.ts)
app\api\analyze\          (the old TypeScript route)
```

Check `package.json` has no `build:data` script — `build` should be plain
`next build`. Check nothing imports from `@/lib/...` any more.

**Do not delete `api\_engine\` or `api\_data\`.** Those are the live engine.

## Step 3 — build

```
npm install
npx next build
```

Must compile with no type errors. `next.config.js` has
`typescript: { ignoreBuildErrors: false }` — leave it that way.

## Step 4 — test locally with `vercel dev`

**`npm run dev` will not work for testing.** Plain `next dev` does not serve
Python functions, so `/api/score` will 404. Use:

```
npx vercel dev
```

Then verify, in order:

**a) Health check.** `GET http://localhost:3000/api/score` should return JSON
containing:

```json
{"ok": true, "reference": {"entries": 34795, "single_word_forms": 18445, "multi_word_excluded": 6109, ...}}
```

If those three numbers do not match exactly, the data file is wrong or truncated.

**b) Single sample.** POST to `http://localhost:3000/api/score`:

```json
{"mode": "single", "text": "Last summer I go to my cusin house in the vilage. Is very beautifull place with many tree and a big river. Evry morning we wake up erly and we go to the river for swiming. My cusin he have a small bote so we can go to the other side. The wather was very cold but we dont care becaus we was so happy."}
```

Expect HTTP 200 and `result.score_lines[0]` starting
`Confident lexical level:`. Check `result.corrected_text` shows `cusin` fixed to
`cousin`, `vilage` to `village`, `beautifull` to `beautiful`, `becaus` to
`because`. `bote` and `wather` should be left alone — that is correct, they are
genuinely ambiguous and the engine abstains rather than guessing.

**c) Batch.** POST:

```json
{"mode": "batch", "rows": [{"id": "a", "text": "I like my school. My teachers are kind."}, {"id": "b", "text": "asdfgh qwerty zzzz"}]}
```

Expect 200, two results. Row `a` valid, row `b` with `"valid": false` and a
verdict of `not language` — that is the junk detector working.

**d) The browser.** Open `http://localhost:3000`, paste a sample, click
**Correct spelling and score**. You should see three stages: input, spelling
(corrected text plus a correction table), and the score with its working. Then
switch to **Upload a batch**, upload a CSV, and confirm clicking a row opens that
sample's full breakdown.

Report anything that does not match before deploying.

## Step 5 — deploy

```
npx vercel --prod
```

No environment variables, no database, no settings to configure. Then on the
live URL:

- open `/api/score` — same health JSON as step 4a
- run one sample and one batch through the UI

**If `/api/score` returns 404 on Vercel but worked locally**, Next.js is
capturing the route. Confirm no `app/api/score/` directory exists. The Python
function lives at `api/score.py` (root-level `api/`, not inside `app/`).

## Constraints — do not change these without asking me

- `vercel.json` sets `maxDuration: 300` and `memory: 2048`. A batch of 100 takes
  about 31 seconds. Do not lower `maxDuration`.
- `requirements.txt` is intentionally empty. The engine is pure standard
  library. **Do not add dependencies** — no numpy, no spaCy, no NLTK.
- Vercel caps a response at **4.5 MB**. Batch mode returns summaries only for
  this reason, and the frontend chunks at 100 rows. Do not make batch return full
  detail.
- **Do not modify anything in `api/_engine/`.** It is copied verbatim from a
  separately calibrated tool (LENS). If the spelling correction looks like it is
  "missing" corrections — for example `nex` not becoming `next` — that is
  measured, deliberate abstention, not a bug. Changing the thresholds silently
  changes every score.

## Expected performance

| | |
|---|---|
| Cold start | ~1.2 s |
| One sample | ~2.3 s |
| Batch of 100 | ~31 s |
| Batch response | ~47 KB |
| Detail response | ~90 KB |

## When you are done

Tell me the live URL, and confirm which of the step-4 checks passed. If any
failed, say which and what the actual output was — do not work around a failure
by changing the engine.
