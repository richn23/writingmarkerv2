# Build plan and UI flow (working summary, 18 Aug 2026)

## The plan, as Richard laid it out (refined across four passes)

1. **Question screen** — single/bulk input, structured task type + target
   CEFR level.
2. **Evidence screen** — per-metric traceability + adjustable weighting. Built
   alongside the Question screen, as the other bookend.
3. Each dimension is its own **construct**, cross-linked to others but built
   and verified independently, through a fixed cycle: **document → build →
   map → test → sign off** — then move to the next. Vocabulary profile first,
   Grammar next, others later. Each section is deliberately siloed —
   self-contained data, detection, and scoring, so work on one section can't
   silently corrupt an already-signed-off one.
4. Richard is sourcing a fresh group of real samples specifically to test each
   section against as it goes through this cycle.
5. Final composite/weighting stays deferred until enough sections are signed
   off to compare.

## Task-type-by-level maps

These come bundled with their own sections as they're built — not a separate
blocker to clear first.

## What this means for Vocabulary specifically

Vocabulary has, in effect, already been through most of this cycle once, via
gse-vercel-app / GSE_PROFILER: documented (the construct docs + README),
built (`scoring.py`, `spelling_score.py`, `vocab_fit.py`), mapped (GSE
reference layer), and tested against a real batch (100 MOE scripts, r=+0.85
distinct-words-matched, 32%/79%/92% exact/within-1/within-2 band agreement).
`vocab_fit.py` even references a "batch 2" already in its code comments
("compare both mappings on batch 2 before trusting the top end") — worth
checking whether that's the same sample group Richard is sourcing now, or a
separate one, before assuming Vocabulary's sign-off needs to start from zero.
It may just need a confirmation pass on fresh samples, not a full re-run of
the cycle.

**Grammar starts the cycle from further back.** The construct-level "document"
step exists already (Dimension 2's Grammatical Accuracy, Dimension 3's Grammar
Range), but "map" (connecting the construct to LENS's EGP detection layer) and
"build" (the malformed-structure detector itself) haven't happened. Expect
Grammar's full cycle to take meaningfully longer than Vocabulary's
re-confirmation.

## Next actions

- Before starting Vocabulary's "test" step, check whether the new sample
  group is the same "batch 2" `vocab_fit.py` already references.
- Treat each section's sign-off as final and protected once done.
- Build inside this project (`Writing Marking V2 - GSE Based`), not inside the
  old `gse-vercel-app` project — that one stays frozen as the origin/reference
  copy.
