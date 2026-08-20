> **SUPERSEDED, 20 Aug 2026.** The two-tab split described below was built,
> then replaced by the structure in the 20 Aug brief: screen 4 became
> Evidence Collection (four tabs, evidence gathering only) and dimension
> scoring moved to screen 5. The tab-row pattern this doc established —
> nested pills, `S.step()` styling, screen-local `useState`, one-line
> additions to the tab list — was carried over unchanged. Kept as the
> record of why that pattern exists.

# Follow-up for Claude Code — split screen 4 into per-construct tabs

Richard's direction, from a screenshot of the current Dimensions screen: it
should read **"Vocabulary and Spelling profile"** (they're related
constructs, shown together), then hand off to a separate **"Grammar
profile"** tab once that's built, and so on for whichever constructs come
after — "it kinda goes piece by piece." So screen 4 needs its own internal
tab row, not one flat page that tries to hold every construct at once.

## What exists now (confirmed by reading the current code)

`DimensionsScreen` (`app/page.tsx`, ~line 1199) is a single flat page: an
`<h1>Dimension scoring</h1>`, a subtitle that says "Only Vocabulary is built
so far," the two source/override banners, then `<DetailView d={single} />`
directly. There's no sub-navigation at all.

Two things worth noting before touching this:
- `DetailView` (as of today's build) already shows **both** Vocabulary and
  Spelling as two independent headline scores side by side — so the content
  for the "Vocabulary and Spelling profile" tab already exists and needs no
  new work, just a new label and a home inside a tab.
- The current subtitle ("Only Vocabulary is built so far") is already stale
  for the same reason — Spelling is in there too. Fix this as part of the
  same change.

## The change

Add a small, second-level tab row inside `DimensionsScreen`, separate from
the top-level `ScreenNav` (screen 4 stays "4. Dimensions" in that outer
nav — don't rename or split it there; the new tabs are nested one level
in). Reuse the existing `S.step()` pill styling — the same function
`ScreenNav` already uses for "active"/"done"/"todo" pills — so the new tabs
look like a natural extension of the app's existing visual language rather
than a new pattern.

Suggested shape:

```tsx
const CONSTRUCT_TABS = [
  { key: "vocab_spelling", label: "Vocabulary and Spelling profile", built: true },
  { key: "grammar", label: "Grammar profile", built: false },
  // more appended here as later constructs are built — do not pre-name or
  // guess the rest of the list now, see "Not decided yet" below
] as const;
```

- `vocab_spelling` tab: today's `<DetailView d={single} />` plus the two
  source/override banners, exactly as they render today — just relabelled
  and moved under this tab instead of being the screen's only content.
- `grammar` tab: an honest placeholder, matching the pattern already used
  elsewhere for not-built content (e.g. `ComingSoonScreen`, or Translate's
  "Grammar review" section) — say plainly that it's not built yet, don't
  imply partial functionality.
- Local `useState` for which construct tab is active, scoped to
  `DimensionsScreen` — independent of the top-level `screen` state, so
  switching construct tabs never touches the outer "4. Dimensions" pill or
  the Back/Next flow between screens.

## Not decided yet — do not guess

How many more tabs to stub now, what they're called, and how the six
dimensions from the Landing screen (Task Achievement, Language Accuracy,
Language Range, Organisation, Style & Register, Content Quality) map onto
construct tabs (Vocabulary, Spelling, and Grammar aren't the same list as
those six — they're the underlying constructs some of those dimensions are
built from) is Richard's call, not something to infer from this brief.
Build the two-tab version now (`vocab_spelling` built, `grammar` stubbed),
structured so adding a third tab later is a one-line addition to
`CONSTRUCT_TABS`, and stop there.
