"use client";

import { useMemo, useRef, useState } from "react";
import Papa from "papaparse";

/* ------------------------------------------------------------------ types */

type Summary = {
  id: string;
  valid: boolean;
  verdict: string;
  verdict_notes: string[];
  words: number;
  junk_tokens: number;
  credible_words: number | null;
  sample_label: string | null;
  confident_band: string | null;
  confident_score: number | null;
  upper_band: string | null;
  upper_score: number | null;
  top_band: string | null;
  top_word: string | null;
  composite_confidence: number | null;
  unmatched_written: number;
  unmatched_corrected: number;
  corrections: number;
  distinct: number;
  // The two headline scores, 0-100. Scalars on the row; the arithmetic behind
  // each one lives on the detail shape, under a different key so the two can
  // never be confused for one another.
  vocabulary_score?: number | null;
  spelling_score?: number | null;
  spelling_reason?: string | null;
  coverage?: number | null;
  indicative_only?: boolean | null;
  meta?: Record<string, string>;
};

type Word = {
  word: string;
  matched: boolean;
  band: string | null;
  gse: number | null;
  definition: string | null;
  junk: boolean;
  confidence: number;
};

type AuditRow = {
  original: string;
  corrected: string | null;
  decision: string;
  reason: string;
  confidence: number;
  occurrences: number;
  band_before: string | null;
  band_after: string | null;
  effect: string;
  flags: string[];
};

type Detail = Summary & {
  text: string;
  corrected_text: string;
  score_lines: string[];
  score: any;
  bands: Record<string, Array<{ band: string; count: number }>>;
  views: { full: Word[]; content: Word[]; distinct: Word[]; written: Word[] };
  audit: AuditRow[];
  junk: Array<{ token: string; why: string; occurrences: number }>;
  readings: Array<any>;
  intent_audit?: IntentRow[];
  intent_note?: string | null;
  assessed_reading?: string;
  vocabulary_features?: {
    reading: string; assigned: boolean; score: number | null; band: string | null;
    credible_words: number; distinct_gse_matched: number; words_at_b2_plus: number;
    total_words: number; content_words: number;
    p80_gse: number | null; p90_gse: number | null; median_gse: number | null;
    coverage: number | null; composite_confidence: number;
  } | null;
  spelling_score_detail?: {
    score: number | null; reason: string | null; attempted: number;
    errors?: number; error_rate?: number; minimum?: number;
    categories: Record<string, number>;
    total_cost?: number; total_difficulty?: number; index?: number;
    detail?: Array<{
      written: string; read_as: string; category: string; band: string | null;
      severity: number; difficulty: number; persistence: number; cost: number;
      occurrences: number;
    }>;
  } | null;
  corrected_sample?: string | null;
  spelling_changes?: Array<{ written: string; read_as: string; confidence: number; source: string }>;
  collisions?: Array<[string, number, string, number | null, string | null]>;
  coverage_detail?: {
    coverage: number | null;
    resolved: number;
    written: number;
    unresolved?: string[];
    indicative_only: boolean;
  } | null;
  spelling?: {
    examined: number;
    error_rate: number;
    profile: Array<{ category: string; label: string; count: number; pct: number }>;
    errors: Array<{ word: string; category: string; source: string }>;
  } | null;
  communicative?: {
    summary_bullets: string[];
    communicative_level_band: string;
    communicative_level_descriptor: string;
    // The case against each neighbouring band. Optional because a result
    // scored before these fields existed will not carry them.
    why_not_below?: string;
    why_not_above?: string;
    band_below?: string;
    band_above?: string;
    effect_on_reader: string;
  } | null;
  communicative_error?: string | null;
  // Set only on a result that came back from the override path. `first_pass`
  // means the marker re-scored but changed nothing; the field's absence means
  // the result predates any review at all.
  interpretation_source?: "marker" | "first_pass";
  overrides_applied?: string[];
  overrides_unknown?: string[];
  communicative_carried_forward?: boolean;
};

// A marker's disagreement with one vocabulary proposal, keyed by the token as
// the student wrote it. Only tokens they actually changed get an entry —
// everything absent keeps the model's original answer, which is what makes
// clearing an override a real revert rather than a second edit.
type Override = {
  answer: "replacement" | "not_a_misspelling" | "proper_noun" | "unrecoverable";
  proposed?: string;               // only meaningful when answer === "replacement"
};
type Overrides = Record<string, Override>;

// Deliberately the same four answers `_intent/review.py` accepts from the
// model. A marker's correction goes through the identical acceptance checks —
// so a mistyped replacement fails the form test the same way a bad model
// proposal does, rather than silently corrupting the corrected sample.
const OVERRIDE_ANSWERS: Array<{ value: Override["answer"]; label: string }> = [
  { value: "replacement", label: "A different word…" },
  { value: "not_a_misspelling", label: "Not a misspelling" },
  { value: "proper_noun", label: "It's a name" },
  { value: "unrecoverable", label: "Can't tell" },
];

type IntentRow = {
  original: string;
  proposed: string | null;
  corrected: string | null;
  answer: string;
  confidence: number;
  model_reason: string;
  accepted: boolean;
  rejected_because: string | null;
  form?: string;
};

// One band vocabulary across the whole screen. The chart is the evidence for
// the level, so it has to speak the same language as the level line: the
// project's assessment bands, not Pearson's coarser per-entry labels. Pearson
// calls GSE 10-21 "<A1" and lumps 22-29 into "A1"; here that same range is
// Pre-A1, and 22-29 splits into A1 and A1+ — which is what the ministry's own
// marks use.
const BANDS = ["Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "B2+", "C1", "C2", "unmatched"];

// The four task types the question screen offers. Extend here if more are needed.
const TASK_TYPES = ["Descriptive writing", "Instructions", "Essay", "Email"];

// The top-level screens, in build order. Free navigation between them is
// deliberate — while this is being built, every screen needs to be viewable
// on its own, not gated behind finishing the one before it.
const SCREENS = [
  { key: "landing", label: "1. Landing" },
  { key: "question", label: "2. Question" },
  { key: "translate", label: "3. Translate" },
  { key: "evidence_collection", label: "4. Evidence Collection" },
  { key: "dimension_scoring", label: "5. Dimension scoring" },
  { key: "final", label: "6. Final score" },
] as const;
type ScreenKey = typeof SCREENS[number]["key"];

// Screen 4's own tabs, one level in from SCREENS above. Each tab gathers
// evidence for one construct, built module by module. Screen 5 is where that
// evidence gets turned into dimension scores; this screen does not score
// dimensions and must not start to.
//
// NO TAB-TO-DIMENSION MAPPING LIVES HERE, or anywhere else in this file. Which
// dimensions each module eventually informs is still being decided and will
// change as modules land, so a guess encoded now would be wrong in a way that
// is hard to find later. The tabs name what is measured, never what it feeds.
//
// The Vocabulary tab covers spelling too — `DetailView` already reports both as
// two independent headline scores — so the label does not enumerate them.
//
// To add one: an entry here, plus a branch in the content dispatch inside
// EvidenceCollectionScreen. `built: false` needs only the entry, because the
// placeholder is written from the label alone.
const EVIDENCE_TABS = [
  { key: "vocab_spelling", label: "Vocabulary profile", built: true },
  { key: "grammar", label: "Grammar profile", built: false },
  { key: "task_analysis", label: "Task Analysis", built: false },
  { key: "additional_metrics", label: "Additional Metrics", built: false },
] as const;
type EvidenceKey = typeof EVIDENCE_TABS[number]["key"];

/* ----------------------------------------------------------------- styles */

const C = {
  ink: "#0b0b0b",
  ink2: "#52514e",
  ink3: "#77766f",
  rule: "#dedcd6",
  surface: "#fcfcfb",
  surface2: "#eeeeeb",
  page: "#f6f6f4",
  written: "#2a78d6",
  corrected: "#eb6834",
  ok: "#1baf7a",
  bad: "#c0392b",
  flag: "#b45309",
  // Reserved for grammar corrections once the grammar translation layer
  // exists — kept visually distinct from vocabulary's orange on purpose.
  grammar: "#7c5cbf",
  experimental: "#8a6d3b",
};

const S = {
  page: { maxWidth: 1180, margin: "0 auto", padding: "30px 24px 90px", color: C.ink, background: C.page, minHeight: "100vh" } as const,
  h1: { fontSize: 23, margin: "0 0 4px", letterSpacing: "-0.01em" } as const,
  sub: { color: C.ink2, marginBottom: 24, fontSize: 14 } as const,
  card: { background: C.surface, border: `1px solid ${C.rule}`, borderRadius: 10, padding: 18, marginBottom: 14 } as const,
  h2: { fontSize: 16, margin: "30px 0 10px", letterSpacing: "-0.005em" } as const,
  h3: { fontSize: 12, margin: "18px 0 8px", color: C.ink2, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 } as const,
  tabRow: { display: "flex", gap: 8, marginBottom: 18 } as const,
  tab: (a: boolean) => ({ padding: "8px 16px", borderRadius: 8, border: `1px solid ${a ? C.ink : C.rule}`, background: a ? C.ink : "#fff", color: a ? "#fff" : C.ink, cursor: "pointer", fontSize: 14 }) as const,
  ta: { width: "100%", minHeight: 190, padding: 12, borderRadius: 8, border: `1px solid ${C.rule}`, fontSize: 14, fontFamily: "inherit", boxSizing: "border-box" } as const,
  field: { width: "100%", padding: "9px 10px", borderRadius: 8, border: `1px solid ${C.rule}`, fontSize: 14, fontFamily: "inherit", boxSizing: "border-box", background: "#fff" } as const,
  label: { fontSize: 11, color: C.ink2, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, marginBottom: 5, display: "block" } as const,
  btn: { padding: "10px 18px", borderRadius: 8, border: "none", background: C.ink, color: "#fff", fontSize: 14, cursor: "pointer" } as const,
  btn2: { padding: "9px 16px", borderRadius: 8, border: `1px solid ${C.rule}`, background: "#fff", color: C.ink, fontSize: 14, cursor: "pointer" } as const,
  table: { width: "100%", borderCollapse: "collapse", fontSize: 13 } as const,
  th: { textAlign: "left", padding: "7px 9px", borderBottom: `1px solid ${C.rule}`, color: C.ink2, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 } as const,
  td: { padding: "7px 9px", borderBottom: `1px solid ${C.surface2}`, verticalAlign: "top" } as const,
  num: { textAlign: "right", fontVariantNumeric: "tabular-nums" } as const,
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 } as const,
  tile: { background: C.surface, border: `1px solid ${C.rule}`, borderRadius: 10, padding: "13px 15px" } as const,
  tileK: { fontSize: 11, color: C.ink2, textTransform: "uppercase", letterSpacing: "0.05em" } as const,
  tileV: { fontSize: 21, fontWeight: 600, marginTop: 3, letterSpacing: "-0.02em" } as const,
  tileN: { fontSize: 11, color: C.ink3, marginTop: 2 } as const,
  mono: { fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace", fontSize: 12.5 } as const,
  note: { fontSize: 13, color: C.ink2, background: C.surface2, borderLeft: `3px solid ${C.rule}`, padding: "10px 13px", borderRadius: "0 6px 6px 0", margin: "10px 0" } as const,
  step: (state: "done" | "active" | "todo") => ({
    display: "flex", alignItems: "center", gap: 8, padding: "7px 13px", borderRadius: 20, fontSize: 13,
    border: `1px solid ${state === "todo" ? C.rule : C.ink}`,
    background: state === "active" ? C.ink : "#fff",
    color: state === "active" ? "#fff" : state === "todo" ? C.ink3 : C.ink,
  }) as const,
};

/* -------------------------------------------------------------- fragments */

function Tile({ k, v, n }: { k: string; v: any; n?: string }) {
  return (
    <div style={S.tile}>
      <div style={S.tileK}>{k}</div>
      <div style={S.tileV}>{v ?? "—"}</div>
      {n ? <div style={S.tileN}>{n}</div> : null}
    </div>
  );
}

// Two stages, because that is what this screen has. The old middle stage,
// "Spelling", was a separate screen before the six-screen restructure; that
// content is on Translate now and nothing on the Question screen corresponds
// to it.
function Steps({ at }: { at: 1 | 2 }) {
  const labels = ["1. Input", "2. Score"];
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
      {labels.map((l, i) => (
        <div key={l} style={S.step(at === i + 1 ? "active" : at > i + 1 ? "done" : "todo")}>{l}</div>
      ))}
    </div>
  );
}

function WordChips({ words }: { words: Word[] }) {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.95 }}>
      {words.map((w, i) => (
        <span
          key={i}
          title={w.definition ?? (w.junk ? "not language" : "not in the GSE list")}
          style={{
            display: "inline-block", padding: "1px 7px", margin: "0 3px 3px 0", borderRadius: 5,
            background: C.surface2,
            border: `1px ${w.junk ? "dotted" : w.matched ? "solid" : "dashed"} ${w.junk ? C.bad : C.rule}`,
            color: w.junk ? C.bad : w.matched ? C.ink : C.ink3,
            textDecoration: w.junk ? "line-through" : "none",
          }}
        >
          {w.word}
          <b style={{ fontWeight: 600, fontSize: 10.5, color: C.ink3, marginLeft: 5 }}>
            {w.matched ? `${w.band}${w.gse != null ? " " + w.gse : ""}` : "—"}
          </b>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------- the detail panel */

// `part` lets the Evidence Collection tab draw these blocks in the order the
// 20 Aug brief specifies — two scripts, then the confident level, then the
// profile — without any of them being rewritten or duplicated. "all" is the
// default and renders everything in the original order, which is what the batch
// drill-down still uses.
type DetailPart = "all" | "vocab_level" | "vocab_profile" | "spelling";

function DetailView({ d, onBack, part = "all" }: {
  d: Detail; onBack?: () => void; part?: DetailPart;
}) {
  const [view, setView] = useState<"distinct" | "content" | "full">("distinct");
  const sc = d.score;
  const show = (k: DetailPart) => part === "all" || part === k;

  return (
    <div>
      {onBack ? (
        <button style={{ ...S.btn2, marginBottom: 14 }} onClick={onBack}>← back to the batch</button>
      ) : null}

      {show('all') ? (
        <>
      <h2 style={{ ...S.h2, marginTop: 0 }}>{d.id}</h2>
      {d.meta && Object.keys(d.meta).length ? (
        <p style={S.sub}>
          {Object.entries(d.meta).map(([k, v]) => (
            <span key={k} style={{ marginRight: 16 }}>{k}: <b>{v}</b></span>
          ))}
        </p>
      ) : null}

      {!d.valid ? (
        <div style={{ ...S.card, borderColor: C.bad }}>
          <b style={{ color: C.bad }}>Not a usable script — no level reported.</b>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {d.verdict_notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      ) : null}
        </>
      ) : null}

      {show('all') ? (
        <>
      {/* TWO SCORES, both 0-100, both from the same reading, deliberately
          independent. Across the batch of 100 they correlate at r = 0.20, so a
          student can be A2 vocabulary with poor spelling or Pre-A1 spelled
          accurately and these two numbers will say so. */}
      {d.vocabulary_features || d.spelling_score_detail ? (
        <div style={{ ...S.card, display: "flex", gap: 28, flexWrap: "wrap" }}>
          {[
            {
              label: "Vocabulary",
              value: d.vocabulary_features?.score ?? null,
              colour: C.written,
              note: d.vocabulary_features?.assigned
                ? `${d.vocabulary_features.band} · ${d.vocabulary_features.credible_words} credible words · coverage ${
                    d.vocabulary_features.coverage != null
                      ? Math.round(d.vocabulary_features.coverage * 100) + "%"
                      : "—"}`
                : "not assigned — too little to profile",
            },
            {
              label: "Spelling",
              value: d.spelling_score_detail?.score ?? null,
              colour: "#5c9e69",
              note: d.spelling_score_detail?.score != null
                ? `${d.spelling_score_detail.attempted} words attempted · ${d.spelling_score_detail.errors} carried an error (${d.spelling_score_detail.error_rate}%)`
                : `no score — ${d.spelling_score_detail?.attempted ?? 0} attempted words, ${d.spelling_score_detail?.minimum ?? 8} needed`,
            },
          ].map((s) => (
            <div key={s.label} style={{ minWidth: 240, flex: "1 1 240px" }}>
              <div style={{ fontSize: 12.5, letterSpacing: "0.06em", textTransform: "uppercase", color: C.ink3 }}>
                {s.label}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6, margin: "2px 0 4px" }}>
                <span style={{ fontSize: 40, fontWeight: 700, letterSpacing: "-0.02em",
                               color: s.value == null ? C.ink3 : s.colour }}>
                  {s.value ?? "—"}
                </span>
                <span style={{ fontSize: 15, color: C.ink3 }}>/ 100</span>
              </div>
              <div style={{ fontSize: 13, color: C.ink2 }}>{s.note}</div>
            </div>
          ))}
          <div style={{ ...S.note, flexBasis: "100%", marginTop: 4 }}>
            Two separate traits. Vocabulary range and orthographic control are
            scored independently — one is not evidence for the other, and
            spelling has no CEFR band because CEFR treats it under
            Orthographic control, not vocabulary.
          </div>
        </div>
      ) : null}
        </>
      ) : null}

      {show('vocab_level') ? (
        <>
      {/* ---- stage 3: the score ---- */}
      <div style={S.card}>
        {sc.assigned ? (
          <>
            {/* Every line format_lines() produces, in its order. Hardcoding
                three indices meant the 4th line — "Highest credible item" —
                silently fell off the end the moment the ceiling-adjusted line
                was added ahead of it. */}
            {d.score_lines.map((line, i) => (
              <div
                key={i}
                style={i === 0
                  ? { fontSize: 20, fontWeight: 600, letterSpacing: "-0.01em", marginBottom: 4 }
                  : { fontSize: 15, color: C.ink2 }}
              >
                {line}
              </div>
            ))}
            <table style={{ ...S.table, marginTop: 14 }}>
              <tbody>
                <tr>
                  <td style={S.td}><b>Credible words</b></td>
                  <td style={{ ...S.td, ...S.num, ...S.mono }}>{sc.credible_count}</td>
                  <td style={S.td}>distinct content words matched with confidence ≥ 0.70</td>
                </tr>
                <tr style={{ background: C.surface2 }}>
                  <td style={S.td}><b>Composite confidence</b></td>
                  <td style={{ ...S.td, ...S.num, ...S.mono }}>{sc.confidence.composite.toFixed(2)}</td>
                  <td style={S.td}>
                    0.4 × sample {sc.confidence.sample_size_score.toFixed(2)} + 0.3 × reliability{" "}
                    {sc.confidence.match_reliability_score.toFixed(2)} + 0.3 × stability{" "}
                    {sc.confidence.distribution_stability_score.toFixed(2)}
                  </td>
                </tr>
                <tr>
                  <td style={S.td}><b>Confident level</b></td>
                  <td style={{ ...S.td, ...S.num, ...S.mono }}>GSE {sc.confident.gse}</td>
                  <td style={S.td}>
                    80% of weight below it · {sc.confident.support} word(s) within ±5 GSE
                    {sc.confident.clamped ? ` · ${sc.confident.clamped} by the evidence range` : ""}
                  </td>
                </tr>
                {/* The reported score: the confident score nudged up by how
                    far the upper evidence reaches past it. Sits between the two
                    numbers it is built from, so the arithmetic reads in order.
                    Flagged as uncalibrated because scoring.py flags it that way
                    — the caption under the table says so in full. */}
                {sc.reported && sc.ceiling ? (
                  <tr style={{ background: C.surface2 }}>
                    <td style={S.td}>
                      <b>Reported score</b>
                      <div style={{ fontSize: 11, color: C.experimental, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", marginTop: 2 }}>
                        uncalibrated
                      </div>
                    </td>
                    <td style={{ ...S.td, ...S.num, ...S.mono }}>{sc.reported.band} {sc.reported.score}</td>
                    <td style={S.td}>
                      confident {sc.confident.score} + nudge {sc.ceiling.nudge} = round(strength{" "}
                      {sc.ceiling.strength.toFixed(2)} × trust {sc.ceiling.trust.toFixed(2)} × headroom{" "}
                      {sc.ceiling.headroom})
                      {sc.ceiling.headroom === 0
                        ? " · no headroom left in the band, so nothing moves"
                        : ""}
                    </td>
                  </tr>
                ) : null}
                <tr>
                  <td style={S.td}><b>Upper evidence</b></td>
                  <td style={{ ...S.td, ...S.num, ...S.mono }}>GSE {sc.upper.gse}</td>
                  <td style={S.td}>90% of weight below it · {sc.upper.support} word(s) within ±5 GSE</td>
                </tr>
                <tr style={{ background: C.surface2 }}>
                  <td style={S.td}><b>Highest credible item</b></td>
                  <td style={{ ...S.td, ...S.num, ...S.mono }}>GSE {sc.highest.gse}</td>
                  <td style={S.td}>“{sc.highest.word}” — reported only, never the level</td>
                </tr>
              </tbody>
            </table>
            {sc.reported && sc.ceiling ? (
              <p style={{ fontSize: 12, color: C.experimental, marginTop: 10, marginBottom: sc.excluded?.length ? 10 : 0 }}>
                <b>The reported score is first-pass and uncalibrated.</b> The confident, upper and
                highest figures come from evidence caps read off a real marked batch; the ceiling
                nudge does not — its weighting has not been tested against marked scripts yet, and
                every number in that row should be read as provisional.
              </p>
            ) : null}
            {sc.excluded?.length ? (
              <p style={{ fontSize: 13, color: C.ink2, marginBottom: 0 }}>
                <b>{sc.excluded.length} word(s) excluded</b> from the level for confidence below 0.70:{" "}
                {sc.excluded.map((w: any) => `${w.word} (${w.confidence.toFixed(2)})`).join(", ")}
              </p>
            ) : null}
          </>
        ) : (
          <div style={{ fontSize: 16 }}>
            <b>No level assigned</b>
            <div style={{ color: C.ink2, fontSize: 14, marginTop: 4 }}>{sc.note}</div>
          </div>
        )}
      </div>
        </>
      ) : null}

      {show('vocab_level') ? (
        <>
      <div style={S.grid}>
        <Tile k="Words" v={d.words} n={`${d.distinct} distinct content words`} />
        <Tile k="Unmatched" v={`${d.unmatched_written} → ${d.unmatched_corrected}`} n="written → corrected" />
        <Tile k="Corrections" v={d.corrections} n="see the Translate screen" />
        <Tile k="Not language" v={d.junk_tokens} n={`${d.junk.length} distinct forms`} />
      </div>
        </>
      ) : null}

      {show('vocab_level') ? (
        <>
      {d.junk.length ? (
        <div style={S.card}>
          <h3 style={{ ...S.h3, marginTop: 0 }}>Excluded as not language</h3>
          <table style={S.table}>
            <tbody>
              {d.junk.map((j, i) => (
                <tr key={i} style={i % 2 ? { background: C.surface2 } : undefined}>
                  <td style={{ ...S.td, ...S.mono }}>{j.token}</td>
                  <td style={{ ...S.td, ...S.num }}>{j.occurrences}</td>
                  <td style={S.td}>{j.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
        </>
      ) : null}
      {show('vocab_level') ? (
        <>
      {/* Coverage qualifies the LEVEL, so it stays with the score even though
          the good-spelling version it describes now reads on Translate: a level
          built from part of a sample has to say so next to itself.

          TWO STATEMENTS, NOT ONE. `_coverage()` counts individual word tokens;
          a join-pair candidate like "will always" is two words flagged as
          possibly one, so it never enters that denominator. Both figures are
          right, but welded into a sentence they read as a contradiction —
          "coverage 100% ... still unresolved: will always". Same fix as the two
          Dimensions banners above: two true things, shown as two things. */}
      {d.coverage_detail && d.coverage_detail.coverage != null ? (
        <div style={{ ...S.note, color: d.coverage_detail.indicative_only ? C.corrected : C.ink2 }}>
          Coverage {Math.round(d.coverage_detail.coverage * 100)}% — the level rests on{" "}
          {d.coverage_detail.resolved} of {d.coverage_detail.written} individual content words written
          {d.coverage_detail.indicative_only
            ? ". Indicative only: a level built from part of a sample is built from the part that happened to be spelled well."
            : "."}
        </div>
      ) : null}
      {d.coverage_detail?.unresolved?.length ? (
        <div style={{ ...S.note, borderLeftColor: C.flag, color: C.flag }}>
          Still awaiting review: {d.coverage_detail.unresolved.join(", ")}. Separate from the
          coverage figure — that counts individual words, this counts questions still open, so
          both can be true at once. Resolve these in the Vocabulary review further down this
          tab.
        </div>
      ) : null}

        </>
      ) : null}

      {show('spelling') ? (
        <>

      {/* CEFR treats orthographic control as a trait of its own, separate from
          vocabulary range — so it gets its own profile, and it never feeds a
          score. It answers the question the vocabulary score cannot: is this
          student's difficulty vocabulary, or spelling? */}
      {d.spelling && d.spelling.profile?.length ? (
        <>
          <h2 style={S.h2}>Spelling profile</h2>
          <div style={S.card}>
            <div style={{ ...S.note, marginTop: 0, marginBottom: 12 }}>
              {d.spelling.error_rate}% of the {d.spelling.examined} distinct words
              carried an error. Descriptive only — nothing here changes the level.
            </div>
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th}>Category</th><th style={S.th}>Meaning</th>
                  <th style={{ ...S.th, ...S.num }}>Words</th>
                  <th style={{ ...S.th, ...S.num }}>Share</th>
                </tr>
              </thead>
              <tbody>
                {d.spelling.profile.map((row) => (
                  <tr key={row.category}>
                    <td style={{ ...S.td, fontWeight: 600 }}>{row.category}</td>
                    <td style={{ ...S.td, color: C.ink2 }}>{row.label}</td>
                    <td style={{ ...S.td, ...S.num }}>{row.count}</td>
                    <td style={{ ...S.td, ...S.num }}>{row.pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.spelling.errors.length ? (
              <div style={{ ...S.note, marginTop: 12 }}>
                {d.spelling.errors.map((e) => `${e.word} (${e.category})`).join(" · ")}
              </div>
            ) : null}
          </div>
        </>
      ) : null}
        </>
      ) : null}
      {show('spelling') ? (
        <>

      {/* The spelling score's arithmetic, so it can be checked by hand. The
          denominator is the anti-circularity mechanism: the penalty is
          normalised against the difficulty of the words THIS student attempted,
          so two writers with the same error rate at opposite ends of the
          vocabulary range land on the same number. */}
      {d.spelling_score_detail?.detail?.length ? (
        <>
          <h2 style={S.h2}>How the spelling score was reached</h2>
          <div style={S.card}>
            <div style={{ ...S.note, marginTop: 0, marginBottom: 12 }}>
              index {d.spelling_score_detail.index?.toFixed(4)} = 1 − (
              {d.spelling_score_detail.total_cost?.toFixed(3)} cost ÷{" "}
              {d.spelling_score_detail.total_difficulty?.toFixed(3)} difficulty) →{" "}
              <b>{d.spelling_score_detail.score} / 100</b>. Cost per error is
              severity × how easy the word should have been × whether the student
              makes the error consistently.
            </div>
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th}>As written</th><th style={S.th}>Read as</th>
                  <th style={S.th}>Error type</th><th style={S.th}>Band</th>
                  <th style={{ ...S.th, ...S.num }}>Severity</th>
                  <th style={{ ...S.th, ...S.num }}>Difficulty</th>
                  <th style={{ ...S.th, ...S.num }}>Persistence</th>
                  <th style={{ ...S.th, ...S.num }}>Cost</th>
                </tr>
              </thead>
              <tbody>
                {d.spelling_score_detail.detail.map((r, i) => (
                  <tr key={i} style={i % 2 ? { background: C.surface2 } : undefined}>
                    <td style={{ ...S.td, ...S.mono, textDecoration: "line-through", color: C.ink3 }}>{r.written}</td>
                    <td style={{ ...S.td, ...S.mono }}>{r.read_as ?? "—"}</td>
                    <td style={S.td}>{r.category.replace(/_/g, " ")}</td>
                    <td style={S.td}>{r.band ?? "not in GSE"}</td>
                    <td style={{ ...S.td, ...S.num }}>{r.severity.toFixed(1)}</td>
                    <td style={{ ...S.td, ...S.num }}>{r.difficulty.toFixed(2)}</td>
                    <td style={{ ...S.td, ...S.num }}>
                      {r.persistence.toFixed(1)}
                      {r.persistence > 1 ? <span style={{ color: C.flag }}> ×{r.occurrences}</span> : null}
                    </td>
                    <td style={{ ...S.td, ...S.num, fontWeight: 600 }}>{r.cost.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
        </>
      ) : null}
      {show('vocab_level') ? (
        <>

      {/* The proposals themselves — accepted and rejected alike — are reviewed
          in the Vocabulary review below, which is also where a marker overrides them.
          Only the provenance note stays here, because it says which reading the
          score below was computed from. */}
      {d.intent_note ? (
        <div style={{ ...S.card, ...S.note }}>Intent reading: {d.intent_note}.</div>
      ) : null}
        </>
      ) : null}

      {show('spelling') ? (
        <>
      <div style={S.card}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>
          {new Set(d.readings.map((r: any) => r.confident_band)).size === 1
            ? `The same level under all ${d.readings.length} readings`
            : `How the level moves across ${d.readings.length} readings`}
        </h3>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>Reading</th><th style={{ ...S.th, ...S.num }}>Credible words</th>
              <th style={S.th}>Confident level</th><th style={{ ...S.th, ...S.num }}>Score</th>
              <th style={S.th}>Upper</th><th style={{ ...S.th, ...S.num }}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {d.readings.map((r, i) => {
              // The `intent` label was missing, so the row the reported level
              // actually comes from rendered blank — and when several readings
              // agree there was no way to tell which one was used.
              const label = ({
                original: "As written",
                cautious: "Cautious fix",
                lenient: "Lenient fix",
                intent: "In context",
              } as Record<string, string>)[r.reading as string] ?? r.reading;
              const isAssessed = r.reading === d.assessed_reading;
              return (
                <tr key={r.reading} style={{
                  ...(i % 2 ? { background: C.surface2 } : {}),
                  ...(isAssessed ? { background: "#eef5ef" } : {}),
                }}>
                  <td style={{ ...S.td, fontWeight: isAssessed ? 700 : 400 }}>
                    {label}
                    {isAssessed ? (
                      <span style={{ ...S.note, marginTop: 0, marginLeft: 8, color: "#5c9e69" }}>
                        ← the level reported above
                      </span>
                    ) : null}
                  </td>
                  <td style={{ ...S.td, ...S.num }}>{r.credible}</td>
                  <td style={S.td}>{r.confident_band ?? "—"}</td>
                  <td style={{ ...S.td, ...S.num }}>{r.confident_score ?? "—"}</td>
                  <td style={S.td}>{r.upper_band ?? "—"}</td>
                  <td style={{ ...S.td, ...S.num }}>{r.confidence?.toFixed(2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
        </>
      ) : null}

      {show('vocab_profile') ? (
        <>
      <div style={S.card}>
        <div style={{ ...S.tabRow, marginBottom: 12 }}>
          {(["distinct", "content", "full"] as const).map((v) => (
            <button key={v} style={S.tab(view === v)} onClick={() => setView(v)}>
              {{ distinct: "Repetition stripped", content: "Content words only", full: "Every word" }[v]}{" "}
              ({d.views[v].length})
            </button>
          ))}
        </div>
        <WordChips words={d.views[view]} />
      </div>
        </>
      ) : null}
    </div>
  );
}

/* ------------------------------------------- communicative effect screen */
// Screen 3. Interpretation, not scoring — see docs/05. Vocabulary translation
// (audit / intent_audit) is real data from api/_intent, already built. Grammar
// translation and the communicative-message/effect reads are not built
// anywhere yet, so they render as clearly-labelled placeholders, never as if
// they were live model output.

function AiBadge() {
  return (
    <span style={{
      fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
      color: C.ink3, border: `1px solid ${C.rule}`, borderRadius: 20,
      padding: "2px 8px", whiteSpace: "nowrap",
    }}>
      AI-generated
    </span>
  );
}

/* --------------------------------------------------- CEFR band and colour */
// One ramp across the eleven assessment bands, in scale order. Sequential
// rather than eleven unrelated hues, because level is ordinal: the colour has
// to read as "further along", not "a different category".
//
// Deliberately one hue family and deliberately not red. Red already means
// "spelling-corrected" on this screen, and a level colour that drifted towards
// it would blur the two signals a word chip has to carry at once.
const BAND_COLOUR: Record<string, { bg: string; fg: string }> = {
  // A1 family, slate
  "Pre-A1": { bg: "#edf0f3", fg: "#26333f" },
  "A1":     { bg: "#dbe2e9", fg: "#26333f" },
  "A1+":    { bg: "#c3cedb", fg: "#22303c" },
  // A2 family, green
  "A2":     { bg: "#d7e9d2", fg: "#1f3320" },
  "A2+":    { bg: "#aed5a6", fg: "#1c2e1d" },
  // B1 family, blue
  "B1":     { bg: "#b3cdec", fg: "#16283f" },
  "B1+":    { bg: "#7ea9de", fg: "#ffffff" },
  // B2 family, purple
  "B2":     { bg: "#c8b8e6", fg: "#241a3d" },
  "B2+":    { bg: "#a289d3", fg: "#ffffff" },
  // C1, amber
  "C1":     { bg: "#c08a2e", fg: "#ffffff" },
  // C2, charcoal: top of the scale, and the only one that cannot be mistaken
  // for any other family at a glance.
  "C2":     { bg: "#33383d", fg: "#ffffff" },
  none:     { bg: "#f6f5f2", fg: "#8b8a84" },   // not in the reference list
};

// Which bands share a hue. Used only to space the legend, so the families read
// as families rather than as eleven unrelated swatches.
const BAND_FAMILIES: string[][] = [
  ["Pre-A1", "A1", "A1+"],
  ["A2", "A2+"],
  ["B1", "B1+"],
  ["B2", "B2+"],
  ["C1"],
  ["C2"],
];

const SCALE_BANDS = BANDS.filter((b) => b !== "unmatched");

function bandColour(band: string | null | undefined) {
  return BAND_COLOUR[band && BAND_COLOUR[band] ? band : "none"];
}

function CefrLegend() {
  return (
    <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center",
                  fontSize: 11.5, color: C.ink2, marginBottom: 10 }}>
      {BAND_FAMILIES.map((family) => (
        // Tight inside a family, loose between them: the grouping is the point.
        <span key={family[0]} style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          {family.map((b) => (
            <span key={b} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <i style={{ width: 11, height: 11, borderRadius: 3, background: BAND_COLOUR[b].bg,
                          border: `1px solid ${C.rule}`, display: "inline-block" }} />
              {b}
            </span>
          ))}
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <i style={{ width: 11, height: 11, borderRadius: 3, background: BAND_COLOUR.none.bg,
                    border: `1px solid ${C.rule}`, display: "inline-block" }} />
        not in the list
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <i style={{ width: 11, height: 11, borderRadius: 3, background: "#fff",
                    border: `2px solid ${C.bad}`, display: "inline-block" }} />
        spelling-corrected
      </span>
    </div>
  );
}

/* --------------------------------------------------- the two scripts, side by side */
// As-written and intended, every word carrying its CEFR group as fill.
//
// TWO SIGNALS ON ONE CHIP. Level is the fill; "this word was corrected" is a red
// outline, on the intended text only. Keeping them on different visual channels
// is what stops them fighting — a corrected B2 word is still visibly B2.
function ScriptView({ title, text, infoOf, correctedFrom, note }: {
  title: string;
  text: string;
  // The engine's whole record for the word, not just its band: the GSE number
  // is the classification, and the band is derived from it.
  infoOf: (word: string) => Word | null;
  // read-as form -> what the student actually wrote, so a corrected word can
  // say which misspelling it came from.
  correctedFrom: Map<string, string>;
  note?: string;
}) {
  // Split keeping the separators, so punctuation and spacing survive and the
  // panel reads as the student's script rather than a bag of words.
  const parts = text.split(/([A-Za-z']+)/);
  return (
    <div style={{ flex: "1 1 320px", minWidth: 280 }}>
      <label style={S.label}>{title}</label>
      <div style={{ ...S.field, minHeight: 90, lineHeight: 2.1, whiteSpace: "pre-wrap" }}>
        {parts.map((tok, i) => {
          if (!/^[A-Za-z']+$/.test(tok)) return <span key={i}>{tok}</span>;
          const lower = tok.toLowerCase();
          const info = infoOf(lower);
          const col = bandColour(info?.band);
          const wrote = correctedFrom.get(lower);
          const corrected = wrote !== undefined;
          // Everything the engine knows about this word, on hover. GSE number
          // first because that is the actual classification; the band is a
          // bucket derived from it.
          const tip = [
            tok,
            info && info.gse != null
              ? `GSE ${info.gse} \u00b7 ${info.band}`
              : "not in the GSE reference list",
            info?.definition || null,
            corrected ? `spelling-corrected, written as "${wrote}"` : null,
          ].filter(Boolean).join("\n");
          return (
            <span
              key={i}
              title={tip}
              style={{
                background: col.bg, color: col.fg,
                padding: "1px 5px", borderRadius: 4,
                border: corrected ? `2px solid ${C.bad}` : "2px solid transparent",
                boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone",
              }}
            >
              {tok}
            </span>
          );
        })}
      </div>
      {note ? <p style={{ fontSize: 11.5, color: C.ink3, marginTop: 6, marginBottom: 0 }}>{note}</p> : null}
    </div>
  );
}

/* ------------------------------------------------------- the profile donut */
// Distribution of the scored words across the eleven CEFR bands, in scale
// order, sliced by the band each word's GSE number maps to.
function ProfileDonut({ words }: { words: Word[] }) {
  const scored = words.filter((w) => w.matched && !w.junk);
  const total = scored.length;
  const rows = SCALE_BANDS.map((band) => {
    const inBand = scored.filter((w) => w.band === band);
    const gses = inBand.map((w) => w.gse).filter((g): g is number => g != null);
    return {
      band,
      count: inBand.length,
      pct: total ? Math.round((1000 * inBand.length) / total) / 10 : 0,
      gseRange: gses.length
        ? (Math.min(...gses) === Math.max(...gses)
            ? `GSE ${Math.min(...gses)}`
            : `GSE ${Math.min(...gses)}-${Math.max(...gses)}`)
        : "",
      // Highest GSE first: the examples should be the words that earned the
      // band, not whichever came first in the script.
      samples: [...inBand].sort((a, b) => (b.gse ?? 0) - (a.gse ?? 0)).slice(0, 4).map((w) => w.word),
    };
  }).filter((r) => r.count > 0);

  const R = 62, STROKE = 26, CIRC = 2 * Math.PI * R;
  let offset = 0;

  return (
    <div style={{ display: "flex", gap: 26, flexWrap: "wrap", alignItems: "center" }}>
      <svg width={2 * (R + STROKE / 2) + 4} height={2 * (R + STROKE / 2) + 4} role="img"
           aria-label="Vocabulary distribution across CEFR bands">
        <g transform={`translate(${R + STROKE / 2 + 2}, ${R + STROKE / 2 + 2}) rotate(-90)`}>
          {rows.map((r) => {
            const len = (r.pct / 100) * CIRC;
            const el = (
              <circle
                key={r.band} r={R} fill="none"
                stroke={BAND_COLOUR[r.band].bg} strokeWidth={STROKE}
                strokeDasharray={`${len} ${CIRC - len}`} strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central"
              style={{ fontSize: 22, fontWeight: 700, fill: C.ink }}>{total}</text>
        <text x="50%" y="50%" dy="20" textAnchor="middle" dominantBaseline="central"
              style={{ fontSize: 10.5, fill: C.ink3 }}>words</text>
      </svg>
      <div style={{ flex: "1 1 320px", minWidth: 280 }}>
        <table style={S.table}>
          <tbody>
            {rows.map((r) => (
              <tr key={r.band}>
                <td style={{ ...S.td, width: 18 }}>
                  <i style={{ width: 11, height: 11, borderRadius: 3, background: BAND_COLOUR[r.band].bg,
                              border: `1px solid ${C.rule}`, display: "inline-block" }} />
                </td>
                <td style={{ ...S.td, fontWeight: 600 }}>{r.band}</td>
                <td style={{ ...S.td, ...S.mono, color: C.ink3, fontSize: 11.5 }}>{r.gseRange}</td>
                <td style={{ ...S.td, ...S.num, ...S.mono }}>{r.pct}%</td>
                <td style={{ ...S.td, ...S.num, color: C.ink3 }}>{r.count}</td>
                <td style={{ ...S.td, color: C.ink2, fontSize: 12 }}>{r.samples.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!total ? <p style={{ fontSize: 13, color: C.ink3 }}>No scored words to profile.</p> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ collapsible */
function Collapsible({ title, headline, sub, open, onToggle, children }: {
  title: string; headline: React.ReactNode; sub?: string;
  open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <div style={{ ...S.card, padding: 0, overflow: "hidden" }}>
      <button
        onClick={onToggle}
        aria-expanded={open}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 14,
          padding: "16px 18px", background: "transparent", border: "none",
          cursor: "pointer", textAlign: "left", font: "inherit", color: "inherit",
        }}
      >
        <span style={{ fontSize: 13, color: C.ink3, width: 14 }}>{open ? "▾" : "▸"}</span>
        <span style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: "0.06em",
                       color: C.ink2, fontWeight: 600, minWidth: 110 }}>{title}</span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: 8 }}>
          {headline}
        </span>
      </button>
      {sub && !open ? (
        <div style={{ padding: "0 18px 14px 46px", fontSize: 12.5, color: C.ink3 }}>{sub}</div>
      ) : null}
      {open ? <div style={{ padding: "0 18px 18px" }}>{children}</div> : null}
    </div>
  );
}

/* ------------------------------------------- vocabulary review + base forms */
// Both blocks below were lifted verbatim off the Translate screen (20 Aug
// feedback, item 3). Translate is interpretation-and-communication only now;
// anything vocabulary-specific belongs with the vocabulary evidence.
//
// THE OVERRIDE MECHANISM MOVED HOUSE, IT WAS NOT REBUILT. The same props drive
// it — `overrides` / `setOverrides` populate the map, `onRescore` posts
// `mode: "override"`, `firstPass` supplies the baseline the API round-trips.
// Only the component wrapping them changed, so the re-score path and its
// propagation into the intended reading and the scores are the same code.

function VocabularyReview({
  single, firstPass, overrides, setOverrides, onRescore, rescoring, rescoreError, dirty,
}: {
  single: Detail | null;
  firstPass: Detail | null;
  overrides: Overrides;
  setOverrides: (fn: (prev: Overrides) => Overrides) => void;
  onRescore: () => void;
  rescoring: boolean;
  rescoreError: string | null;
  dirty: boolean;
}) {
  const hasSample = !!single;
  const vocabProposals = firstPass?.intent_audit ?? single?.intent_audit ?? [];
  const collisions = single?.collisions ?? [];
  const overrideCount = Object.keys(overrides).length;
  const blankReplacement = Object.values(overrides).some(
    (o) => o.answer === "replacement" && !(o.proposed ?? "").trim());
  const canRescore = !!firstPass?.intent_audit?.length
    && overrideCount > 0 && !blankReplacement && !rescoring && dirty;
  const appliedFor = (token: string) =>
    (single?.interpretation_source === "marker" && single.overrides_applied?.includes(token)
      ? (single.intent_audit ?? []).find((x) => x.original === token)
      : undefined) ?? null;

  return (
    <div>
      {/* Was section 6 of Translate. */}
      <div style={S.card}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>Vocabulary review</h3>
        <p style={{ fontSize: 12, color: C.ink3, marginTop: 0, marginBottom: 12 }}>
          AI-generated proposals for words the deterministic corrector couldn't resolve on its own —
          a review of hypotheses, not a score. The scored evidence is in the profile above.
        </p>
        {vocabProposals.length ? (
          <>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Written</th><th style={S.th}>Proposed</th>
                <th style={S.th}>Reasoning</th><th style={S.th}>Status</th>
                <th style={S.th}>Your answer</th>
              </tr>
            </thead>
            <tbody>
              {vocabProposals.map((r, i) => {
                const ov = overrides[r.original];
                return (
                <tr key={i} style={i % 2 ? { background: C.surface2 } : undefined}>
                  <td style={{ ...S.td, textDecoration: "line-through", color: C.ink3 }}>{r.original}</td>
                  <td style={{ ...S.td, color: C.corrected, fontWeight: 600 }}>{r.proposed ?? "—"}</td>
                  <td style={{ ...S.td, fontSize: 12.5, color: C.ink2 }}>{r.model_reason}</td>
                  <td style={{ ...S.td, color: r.accepted ? "#5c9e69" : C.bad, fontWeight: 600 }}>
                    {r.accepted ? "accepted" : `rejected — ${r.rejected_because ?? "no reason given"}`}
                  </td>
                  {/* The override controls. An empty selection is not "no
                      opinion" — it is "the model's answer stands", which is why
                      it clears the entry rather than storing one. */}
                  <td style={{ ...S.td, minWidth: 210 }}>
                    <select
                      style={{ ...S.field, padding: "5px 7px", fontSize: 12.5 }}
                      value={ov?.answer ?? ""}
                      onChange={(e) => {
                        const v = e.target.value as Override["answer"] | "";
                        setOverrides((prev) => {
                          const next = { ...prev };
                          if (!v) delete next[r.original];
                          else next[r.original] = v === "replacement"
                            ? { answer: v, proposed: prev[r.original]?.proposed ?? r.corrected ?? r.proposed ?? "" }
                            : { answer: v };
                          return next;
                        });
                      }}
                    >
                      <option value="">Keep the model's answer</option>
                      {OVERRIDE_ANSWERS.map((a) => (
                        <option key={a.value} value={a.value}>{a.label}</option>
                      ))}
                    </select>
                    {ov?.answer === "replacement" ? (
                      <input
                        style={{ ...S.field, padding: "5px 7px", fontSize: 12.5, marginTop: 6 }}
                        placeholder="the word the student meant"
                        value={ov.proposed ?? ""}
                        onChange={(e) => {
                          const w = e.target.value;
                          setOverrides((prev) => ({
                            ...prev, [r.original]: { answer: "replacement", proposed: w },
                          }));
                        }}
                      />
                    ) : null}
                    {ov ? (
                      <div style={{ fontSize: 11, color: C.flag, marginTop: 4 }}>your answer, not the model's</div>
                    ) : null}
                    {/* A marker's replacement goes through the same acceptance
                        checks a model's does, so it can be rejected — and if
                        that is not said here, they will believe a correction
                        landed when it did not. */}
                    {appliedFor(r.original) ? (
                      appliedFor(r.original)!.accepted ? (
                        <div style={{ fontSize: 11, color: "#5c9e69", marginTop: 4 }}>
                          applied{appliedFor(r.original)!.corrected ? ` — read as “${appliedFor(r.original)!.corrected}”` : ""}
                        </div>
                      ) : (
                        <div style={{ fontSize: 11, color: C.bad, marginTop: 4 }}>
                          not applied — {appliedFor(r.original)!.rejected_because}
                        </div>
                      )
                    ) : null}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>

          {/* Batch, not per-row: a marker usually disagrees with two or three
              words at once, and one re-score is cheaper and less jumpy than one
              per keystroke. Nothing about the backend design depends on this
              choice, so it can become per-row later without touching it. */}
          <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button
              style={{ ...S.btn, opacity: canRescore ? 1 : 0.5, cursor: canRescore ? "pointer" : "not-allowed" }}
              onClick={onRescore}
              disabled={!canRescore}
            >
              {rescoring ? "Re-scoring…" : "Re-score with my corrections"}
            </button>
            {overrideCount ? (
              <button
                style={S.btn2}
                onClick={() => setOverrides(() => ({}))}
                disabled={rescoring}
              >
                Clear my corrections
              </button>
            ) : null}
            <span style={{ fontSize: 13, color: C.ink2 }}>
              {!firstPass?.intent_audit?.length
                ? "The interpretation pass didn't run on this sample, so there is nothing to override."
                : blankReplacement
                ? "One of your answers is “a different word” with no word typed in."
                : !overrideCount
                ? "Change an answer above to enable this."
                : dirty
                ? `${overrideCount} correction${overrideCount === 1 ? "" : "s"} ready — the score doesn't move until you re-score.`
                : `${overrideCount} correction${overrideCount === 1 ? "" : "s"} applied. Change one to re-score again.`}
            </span>
          </div>
          {rescoreError ? (
            <div style={{ ...S.note, borderLeftColor: C.bad, color: C.bad, marginTop: 10 }}>{rescoreError}</div>
          ) : null}
          {single?.overrides_unknown?.length ? (
            <div style={{ ...S.note, borderLeftColor: C.bad, color: C.bad, marginTop: 10 }}>
              Not applied — this sample never flagged {single.overrides_unknown.join(", ")}, so there
              was no proposal to override. Nothing was changed for those words.
            </div>
          ) : null}
          {single?.interpretation_source ? (
            <div style={{ ...S.note, marginTop: 10,
                          borderLeftColor: single.interpretation_source === "marker" ? "#5c9e69" : C.rule }}>
              {single.interpretation_source === "marker"
                ? `Re-scored against your corrections (${single.overrides_applied?.join(", ")}). The intended reading above and every score on the Dimensions screen now come from this reading.`
                : "Re-scored with no corrections applied — this is the first-pass reading."}
            </div>
          ) : null}
          </>
        ) : (
          <p style={{ fontSize: 13, color: C.ink3, marginBottom: 0 }}>
            {hasSample
              ? "No ambiguous words needed a vocabulary guess in this script — nothing to review, and nothing to override."
              : "Shown once a sample with an ambiguous spelling has been scored."}
          </p>
        )}
      </div>

      {/* HOMOGRAPH READINGS RESOLVED DOWNWARD. Interpretation, not scoring —
          a real word the engine chose to read at its base sense — so it
          belongs with the intended reading above, not on Dimensions where it
          used to sit. Not marker-overridable through the vocabulary review
          below: this is a deterministic engine decision, not a model
          proposal, and the two must not look alike. */}
      {collisions.length ? (
        <div style={{ marginTop: 18 }}>
          <label style={S.label}>Words read down to their base form</label>
          <p style={{ fontSize: 12, color: C.ink3, marginTop: 0, marginBottom: 10 }}>
            These words appear in the reference list only in an advanced sense — “the going was
            tough”, a <i>saw</i> as a tool — so taken at face value they would credit a level the
            student almost certainly did not produce. The engine reads them at their base form
            instead. It only ever resolves <b>downward</b>; if you disagree with a reading here,
            the level is understating that word, never overstating it.
          </p>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Word</th>
                <th style={S.th}>Taken at face value</th>
                <th style={S.th}>Read as</th>
                <th style={{ ...S.th, ...S.num }}>GSE dropped</th>
              </tr>
            </thead>
            <tbody>
              {collisions.map(([word, fromGse, fromBand, toGse, toBand], i) => (
                <tr key={i} style={i % 2 ? { background: C.surface2 } : undefined}>
                  <td style={{ ...S.td, ...S.mono }}>{word}</td>
                  <td style={{ ...S.td, color: C.corrected }}>{fromBand} ({fromGse})</td>
                  <td style={S.td}>{toBand ?? "—"} ({toGse ?? "—"})</td>
                  <td style={{ ...S.td, ...S.num }}>{fromGse - (toGse ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

// One band up or down the eleven-band scale, or null at either end. Used to
// name the two bands section 4 argues against.
function bandNeighbour(band: string, step: -1 | 1): string | null {
  const scale = BANDS.filter((b) => b !== "unmatched");
  const i = scale.indexOf(band);
  if (i < 0) return null;
  const j = i + step;
  return j >= 0 && j < scale.length ? scale[j] : null;
}

function TranslateScreen({ single }: {
  single: Detail | null;              // the freshest reading — override-adjusted if one exists
}) {
  const hasSample = !!single;

  // A worked example so the layout is checkable before any sample has been
  // scored — the same example used in docs/05's own grammar walkthrough.
  const exampleWritten = "She go school every day. My favrite subjcet is math.";
  const exampleIntended = "She goes to school every day. My favourite subject is math.";

  const written = single?.text ?? exampleWritten;
  // The intended reading is the version that comes OUT of the whole
  // interpretation step, not the mechanical pass alone. `corrected_sample`
  // carries the accepted vocabulary proposals (and, once a marker has
  // re-scored, their overrides); `corrected_text` is the mechanical fallback
  // for a sample the intent reading never ran on. Showing corrected_text alone
  // meant accepting "bote" -> "boat" in section 6 changed nothing here.
  const intended = single
    ? (single.corrected_sample ?? single.corrected_text)
    : exampleIntended;
  const intendedIsMechanicalOnly = !!single && !single.corrected_sample;
  const audit = single?.audit ?? [];
  const meta = single?.meta ?? {};

  // Pure quant, computed from the raw as-written text — no model involved,
  // so this carries none of the AI disclaimers everything else on the
  // screen needs.
  //
  // ONE SOURCE OF TRUTH FOR THE WORD COUNT. This used to split on whitespace
  // here, which gave a second, independently-derived count sitting next to the
  // engine's own on the Dimensions screen. They agreed on the samples tried,
  // but nothing made them agree — the engine's tokenizer and a `\s+` split
  // disagree on hyphenation, apostrophes and stray punctuation. `result.words`
  // is `totals.original.tokens` straight from `analyse()`, the same number
  // `DetailView` renders, so both screens now quote one figure. The whitespace
  // split survives only as the fallback for the worked example, where no
  // sample has been analysed and there is no engine count to read.
  const stats = useMemo(() => {
    const trimmed = written.trim();
    const splitWords = trimmed ? trimmed.split(/\s+/).length : 0;
    const words = single?.words ?? splitWords;
    const sentenceMatches = trimmed.match(/[^.!?]+[.!?]+|[^.!?]+$/g);
    const sentences = trimmed ? (sentenceMatches?.length ?? 1) : 0;
    const paragraphs = trimmed ? (trimmed.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean).length || 1) : 0;
    // Derived from the same `words` above, so the tile and this ratio can
    // never quote different totals.
    const avgSentenceLen = sentences ? Math.round((words / sentences) * 10) / 10 : 0;
    return { words, sentences, paragraphs, avgSentenceLen, fromEngine: single?.words != null };
  }, [written, single?.words]);

  return (
    <div>
      <h1 style={S.h1}>Communicative Effect &amp; Translation</h1>
      <p style={S.sub}>
        Before any dimension is scored, this is where the model's reading of what the student
        meant gets surfaced and checked. This screen interprets; it does not score.
      </p>

      {!hasSample ? (
        <div style={{ ...S.note, marginBottom: 14 }}>
          No sample has been scored yet, so the panels below show a worked example, not real
          output. Run a sample on the <b>Question</b> screen to see this screen populated with it.
        </div>
      ) : null}

      {/* 1. As written / intended reading */}
      <div style={S.card}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>1. As written / intended reading</h3>
        <p style={{ fontSize: 12, color: C.ink3, marginTop: 0, marginBottom: 14 }}>
          The intended reading is AI-generated: a hypothesis about intent, not a fact about the text.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginBottom: 14 }}>
          <div>
            <label style={S.label}>As written</label>
            <div style={{ ...S.field, minHeight: 90, background: C.surface2, whiteSpace: "pre-wrap" }}>{written}</div>
          </div>
          <div>
            <label style={S.label}>Intended reading</label>
            <div style={{ ...S.field, minHeight: 90, background: "#fff", color: C.corrected, whiteSpace: "pre-wrap" }}>{intended}</div>
            {intendedIsMechanicalOnly ? (
              <p style={{ fontSize: 11.5, color: C.ink3, marginTop: 6, marginBottom: 0 }}>
                Mechanical pass only. The in-context reading didn't run on this sample, so words
                needing context are still unresolved here.
              </p>
            ) : null}
          </div>
        </div>

        {audit.length ? (
          <>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8, fontSize: 12, color: C.ink2 }}>
              <span><i style={{ width: 10, height: 10, borderRadius: 3, background: C.corrected, display: "inline-block", marginRight: 5 }} /> vocabulary correction</span>
              <span><i style={{ width: 10, height: 10, borderRadius: 3, background: C.grammar, display: "inline-block", marginRight: 5 }} /> grammar correction (not built yet)</span>
              <span><i style={{ width: 10, height: 10, borderRadius: 3, background: C.experimental, display: "inline-block", marginRight: 5 }} /> couldn't confidently interpret</span>
            </div>
            <table style={S.table}>
              <thead><tr><th style={S.th}>Written</th><th style={S.th}>Read as</th><th style={{ ...S.th, ...S.num }}>Confidence</th></tr></thead>
              <tbody>
                {audit.map((r, i) => (
                  <tr key={i} style={{ ...(i % 2 ? { background: C.surface2 } : {}), ...(r.decision === "abstained" ? { background: "#faf1e2" } : {}) }}>
                    <td style={{ ...S.td, textDecoration: "line-through", color: C.ink3 }}>{r.original}</td>
                    <td style={{ ...S.td, color: r.decision === "abstained" ? C.experimental : C.corrected, fontWeight: 600 }}>
                      {r.decision === "abstained" ? "couldn't confidently interpret" : (r.corrected ?? "left as written")}
                    </td>
                    <td style={{ ...S.td, ...S.num }}>{r.confidence?.toFixed(2) ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : hasSample ? (
          <p style={{ fontSize: 13, color: C.ink3 }}>Nothing in this script needed a spelling judgment call.</p>
        ) : null}

      </div>

      {/* 2. Basic script statistics — fact, not judgment. No AI disclaimer. */}
      <div style={{ ...S.card, borderStyle: "solid" }}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>2. Basic script statistics</h3>
        <p style={{ fontSize: 12, color: C.ink3, marginTop: 0, marginBottom: 14 }}>
          Computed directly from the as-written text, with no model involved and nothing to
          accept or reject. {stats.fromEngine
            ? "The word count is the engine's own token count, the same figure the Dimensions screen reports."
            : "Counts shown for the worked example are computed here; a scored sample uses the engine's own token count."}
        </p>
        <div style={S.grid}>
          <Tile k="Word count" v={stats.words}
                n={meta.word_count_min && meta.word_count_max ? `target ${meta.word_count_min}–${meta.word_count_max}` : undefined} />
          <Tile k="Sentence count" v={stats.sentences} />
          <Tile k="Avg. sentence length" v={stats.avgSentenceLen} n="words per sentence" />
          <Tile k="Paragraph count" v={stats.paragraphs} />
        </div>
        <p style={{ fontSize: 11.5, color: C.ink3, marginTop: 12, marginBottom: 0 }}>
          Raw evidence only; longer isn't better. Sentence length carries the same length-confound
          risk vocabulary's fitted model hit; don't read it as a quality signal on its own.
        </p>
      </div>

      {/* 3. Communicative message summary */}
      <div style={S.card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <h3 style={{ ...S.h3, marginTop: 0 }}>3. Communicative message: summary</h3>
          <AiBadge />
        </div>
        {single?.communicative ? (
          <ul style={{ fontSize: 14, color: C.ink2, lineHeight: 1.7, paddingLeft: 20, marginTop: 4, marginBottom: 8 }}>
            {single.communicative.summary_bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        ) : hasSample ? (
          <p style={{ fontSize: 13, color: C.ink3, marginBottom: 0 }}>
            Not available. {single?.communicative_error ?? "No reading returned"}.
          </p>
        ) : (
          <>
            <ul style={{ fontSize: 14, color: C.ink2, lineHeight: 1.7, paddingLeft: 20, marginTop: 4, marginBottom: 8 }}>
              <li>Example: describes a family visit to a relative's house in a village.</li>
              <li>Example: mentions the setting and a daily routine of swimming in a river.</li>
            </ul>
            <p style={{ fontSize: 11.5, color: C.ink3, marginBottom: 0 }}>
              Worked example. Run a sample on the Question screen to see this generated for real.
            </p>
          </>
        )}
        {single?.communicative ? (
          <p style={{ fontSize: 11.5, color: C.ink3, marginTop: 8, marginBottom: 0 }}>
            Not yet marker-correctable from this screen. See the open question on how an override
            here should propagate downstream.
          </p>
        ) : null}
      </div>

      {/* 4 & 5. Communicative level / effect on reader */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <div style={S.card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <h3 style={{ ...S.h3, marginTop: 0 }}>4. Communicative level</h3>
            <AiBadge />
          </div>
          {single?.communicative ? (
            <>
              {/* The band is the headline of this panel, so it is set like one
                  rather than buried mid-sentence in the descriptor.

                  Underneath it, the case against each neighbouring band. A band
                  on its own is an assertion; these two make it arguable, which
                  was the point of the "why not A2, why not B2" question. The
                  reasoning comes from the model, which is asked to name
                  something actually in this script rather than restate the band
                  definitions at each other. */}
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "2px 0 6px" }}>
                <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em", color: C.ink }}>
                  {single.communicative.communicative_level_band}
                </span>
                <span style={{ fontSize: 12, color: C.ink3 }}>communicative level</span>
              </div>
              <p style={{ fontSize: 13, color: C.ink2, marginBottom: 10 }}>{single.communicative.communicative_level_descriptor}</p>
              {single.communicative.why_not_below || single.communicative.why_not_above ? (
                <table style={S.table}>
                  <tbody>
                    {([
                      ["below",
                       single.communicative.band_below
                         || bandNeighbour(single.communicative.communicative_level_band, -1),
                       single.communicative.why_not_below],
                      ["above",
                       single.communicative.band_above
                         || bandNeighbour(single.communicative.communicative_level_band, 1),
                       single.communicative.why_not_above],
                    ] as Array<[string, string | null, string | undefined]>)
                      .filter(([, , why]) => !!why)
                      .map(([dir, band, why]) => (
                        <tr key={dir}>
                          <td style={{ ...S.td, whiteSpace: "nowrap", fontWeight: 600, width: 1 }}>
                            {band ? `Why not ${band}?` : `Why not one ${dir}?`}
                          </td>
                          <td style={{ ...S.td, color: C.ink2 }}>{why}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ) : null}
            </>
          ) : hasSample ? (
            <p style={{ fontSize: 13, color: C.ink3, marginBottom: 0 }}>
              Not available. {single?.communicative_error ?? "No reading returned"}.
            </p>
          ) : (
            <>
              <p style={{ fontSize: 14, color: C.ink, marginBottom: 6 }}><b>Example: consistent with B1 expectations.</b></p>
              <p style={{ fontSize: 13, color: C.ink2, marginBottom: 0 }}>
                The main message is clear and connected. Errors occasionally interrupt the flow but
                generally do not prevent understanding.
              </p>
            </>
          )}
        </div>
        <div style={S.card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <h3 style={{ ...S.h3, marginTop: 0 }}>5. Effect on reader</h3>
            <AiBadge />
          </div>
          {single?.communicative ? (
            <p style={{ fontSize: 14, color: C.ink, marginBottom: 0 }}>{single.communicative.effect_on_reader}</p>
          ) : hasSample ? (
            <p style={{ fontSize: 13, color: C.ink3, marginBottom: 0 }}>
              Not available. {single?.communicative_error ?? "No reading returned"}.
            </p>
          ) : (
            <p style={{ fontSize: 14, color: C.ink, marginBottom: 0 }}>
              Example: readable with occasional re-reading needed.
            </p>
          )}
        </div>
      </div>
      <p style={{ fontSize: 12, color: C.ink3, margin: "14px 0" }}>
        Both read from the as-written text only, never the intended reading above, so the judgment
        can't hide the friction it exists to measure. Supporting evidence for Coherence, not a
        seventh dimension: sign-off depends on testing whether it predicts real markers' Coherence
        judgments, not on how it looks here.
      </p>


      {/* 6. Other reviews */}
      <div style={S.card}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>6. Other reviews</h3>
        <p style={{ fontSize: 13, color: C.ink3, marginBottom: 0 }}>
          Placeholder. Not yet defined.
        </p>
      </div>
    </div>
  );
}

/* -------------------------------------------- the vocabulary profile tab */
// Two collapsed rows by default, each showing only its metric name and one
// headline figure. Everything that used to arrive at once now sits behind an
// expand — the 20 Aug feedback was that landing on this tab showed both scores,
// the whole scoring table and the full word list simultaneously.
//
// Nothing was dropped in the reorganisation. Every block DetailView rendered is
// still rendered, just distributed across the two sections by `part`.

function VocabularyProfileTab({
  d, firstPass, overrides, setOverrides, onRescore, rescoring, rescoreError, dirty,
}: {
  d: Detail;
  firstPass: Detail | null;
  overrides: Overrides;
  setOverrides: (fn: (prev: Overrides) => Overrides) => void;
  onRescore: () => void;
  rescoring: boolean;
  rescoreError: string | null;
  dirty: boolean;
}) {
  // Independent, so opening one never closes the other.
  const [openVocab, setOpenVocab] = useState(false);
  const [openSpelling, setOpenSpelling] = useState(false);

  const sc = d.score;

  // Band per word, from the engine's own records rather than a second lookup.
  // `written` carries the as-written forms; `full` the intent reading's stream.
  const infoOfIntended = useMemo(() => {
    const m = new Map<string, Word>();
    for (const w of [...d.views.full, ...d.views.distinct]) m.set(w.word.toLowerCase(), w);
    return m;
  }, [d.views.full, d.views.distinct]);

  // `views.written` is the as-written DISTINCT CONTENT words, so function words
  // are not in it. Looking a word up there alone made "the", "my" and "was"
  // render as "not in the reference list" on the left while the same words were
  // banded on the right, which is nonsense: they are in the list.
  //
  // Falling back to the intent reading's map is safe precisely because a word
  // only appears in it under the form the engine ended up reading. An unchanged
  // word has the same form in both texts and resolves correctly; a misspelling
  // does not appear there at all, so `vilage` and `bote` still show as not in
  // the list on the left, which is the truth about the text as written.
  const infoOfWritten = useMemo(() => {
    const m = new Map<string, Word>();
    for (const w of d.views.written) m.set(w.word.toLowerCase(), w);
    return (w: string) => m.get(w) ?? infoOfIntended.get(w) ?? null;
  }, [d.views.written, infoOfIntended]);

  const infoOfIntendedFn = useMemo(
    () => (w: string) => infoOfIntended.get(w) ?? null, [infoOfIntended]);

  // The forms that ARE a correction, i.e. what a misspelling was read as. Marked
  // on the intended text only — the as-written script has no corrections in it
  // by definition.
  const correctedFrom = useMemo(() => {
    const out = new Map<string, string>();
    for (const c of d.spelling_changes ?? []) {
      if (c.read_as) out.set(c.read_as.toLowerCase(), c.written);
    }
    for (const r of d.audit ?? []) {
      if (r.corrected) out.set(r.corrected.toLowerCase(), r.original);
    }
    return out;
  }, [d.spelling_changes, d.audit]);

  const intendedText = d.corrected_sample ?? d.corrected_text;

  return (
    <>
      <Collapsible
        title="Vocabulary"
        open={openVocab}
        onToggle={() => setOpenVocab((v) => !v)}
        sub={sc.assigned ? `${sc.credible_count} credible words · ${sc.sample_label}` : undefined}
        headline={
          <>
            <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em",
                           color: sc.assigned ? C.written : C.ink3 }}>
              {sc.assigned ? sc.confident.band : "—"}
            </span>
            <span style={{ fontSize: 12, color: C.ink3 }}>estimated CEFR level</span>
          </>
        }
      >
        {/* 1. The two scripts. */}
        <h2 style={{ ...S.h2, marginTop: 6 }}>The two scripts</h2>
        <p style={{ fontSize: 12, color: C.ink3, marginTop: 0, marginBottom: 10 }}>
          Every word is classified by its GSE level. One colour per CEFR level, shaded within it,
          so A2 and A2+ read as the same level at different strengths rather than as two unrelated
          bands. Hover a word for its exact GSE number, its level, and the dictionary sense the
          engine matched.
        </p>
        <CefrLegend />
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          <ScriptView title="As written" text={d.text}
                      infoOf={infoOfWritten} correctedFrom={new Map()} />
          <ScriptView title="Intended reading" text={intendedText}
                      infoOf={infoOfIntendedFn} correctedFrom={correctedFrom}
                      note="Hover any word for its GSE number and level. A red outline marks a word the spelling pass read differently from what was written." />
        </div>

        {/* 2. Confident lexical level, then the arithmetic behind it. */}
        <h2 style={S.h2}>Confident lexical level</h2>
        <div style={S.card}>
          {sc.assigned ? (
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 38, fontWeight: 700, letterSpacing: "-0.02em", color: C.written }}>
                {sc.confident.band}
              </span>
              <span style={{ fontSize: 16, color: C.ink2 }}>score {sc.confident.score} / 100</span>
              <span style={{ fontSize: 13, color: C.ink3 }}>
                GSE {sc.confident.gse} · {sc.sample_label} · {sc.credible_count} credible words
              </span>
            </div>
          ) : (
            <div style={{ fontSize: 15 }}>
              <b>No level assigned</b>
              <div style={{ color: C.ink2, fontSize: 13, marginTop: 4 }}>{sc.note}</div>
            </div>
          )}
        </div>
        <DetailView d={d} part="vocab_level" />

        {/* 3. The profile. */}
        <h2 style={S.h2}>The vocabulary profile</h2>
        <div style={S.card}>
          <ProfileDonut words={d.views.distinct} />
        </div>
        <DetailView d={d} part="vocab_profile" />

        <VocabularyReview
          single={d}
          firstPass={firstPass}
          overrides={overrides}
          setOverrides={setOverrides}
          onRescore={onRescore}
          rescoring={rescoring}
          rescoreError={rescoreError}
          dirty={dirty}
        />
      </Collapsible>

      <Collapsible
        title="Spelling"
        open={openSpelling}
        onToggle={() => setOpenSpelling((v) => !v)}
        sub={d.spelling_score_detail?.score != null
          ? `${d.spelling_score_detail.attempted} words attempted · ${d.spelling_score_detail.errors} carried an error`
          : `not scored — ${d.spelling_score_detail?.attempted ?? 0} attempted, ${d.spelling_score_detail?.minimum ?? 8} needed`}
        headline={
          <>
            <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em",
                           color: d.spelling_score_detail?.score != null ? "#5c9e69" : C.ink3 }}>
              {d.spelling_score_detail?.score ?? "—"}
            </span>
            <span style={{ fontSize: 12, color: C.ink3 }}>/ 100</span>
          </>
        }
      >
        <DetailView d={d} part="spelling" />
      </Collapsible>
    </>
  );
}

function EvidenceCollectionScreen({
  single, hasOverrides, firstPass, overrides, setOverrides, onRescore, rescoring, rescoreError, dirty,
}: {
  single: Detail | null;
  hasOverrides: boolean;
  // The vocabulary review moved here from Translate (20 Aug feedback, item 3).
  // These props are the same ones that drove it there, threaded to its new home.
  firstPass: Detail | null;
  overrides: Overrides;
  setOverrides: (fn: (prev: Overrides) => Overrides) => void;
  onRescore: () => void;
  rescoring: boolean;
  rescoreError: string | null;
  dirty: boolean;
}) {
  // Local to this screen on purpose: switching evidence tabs must never touch
  // the outer `screen` state, so the "4. Evidence Collection" pill and the
  // Back/Next flow between screens stay exactly where they were.
  const [tab, setTab] = useState<EvidenceKey>("vocab_spelling");
  const active = EVIDENCE_TABS.find((t) => t.key === tab)!;

  // WHICH READING THIS IS has to be on the screen, not inferred. Showing
  // first-pass numbers with no indication that they predate a marker's
  // corrections is the exact failure the interpretation/scoring split exists
  // to prevent.
  const fromMarker = single?.interpretation_source === "marker";

  // Every evidence module reads the same interpretation, so the banners belong
  // to the screen rather than to the Vocabulary tab — a module built later needs
  // them unchanged, not reimplemented.
  const banners = single ? (
    <>
      <div style={{ ...S.note, borderLeftColor: fromMarker ? "#5c9e69" : C.rule, marginBottom: hasOverrides ? 8 : 16 }}>
        {fromMarker ? (
          <>
            <b>Scored from your approved interpretation.</b> Every number below was recomputed
            after you corrected{" "}
            {single.overrides_applied?.length ? single.overrides_applied.join(", ") : "the reading"}{" "}
            in the Vocabulary review below.
          </>
        ) : (
          <>
            <b>Scored from the first-pass interpretation.</b> No marker corrections have been
            applied — these are the model's own readings, reviewable in the Vocabulary review below.
          </>
        )}
      </div>
      {/* Independent of which reading is shown. A marker who re-scores,
          then changes their mind, is looking at numbers that are stale in
          exactly the same way a first-pass screen is — and the "approved"
          banner above would otherwise reassure them it isn't. */}
      {hasOverrides ? (
        <div style={{ ...S.note, borderLeftColor: C.corrected, color: C.corrected, marginBottom: 16 }}>
          <b>These numbers do not include your latest corrections.</b> There are unapplied
          changes in the Vocabulary review below — re-score there to bring them through.
        </div>
      ) : null}
    </>
  ) : null;

  return (
    <div>
      <h1 style={S.h1}>Evidence Collection</h1>
      <p style={S.sub}>
        Each tab gathers the evidence for one construct, reading from the approved interpretation
        on the Translate screen rather than re-asking a model what the text means. Dimension
        scoring happens on the next screen, from whatever has been built here. Vocabulary is
        built; the rest get a tab as they are.
      </p>

      {/* Second-level navigation. Same pill styling as ScreenNav — one visual
          language for "where am I", at both levels. A greyed pill is a tab with
          nothing behind it yet; it is still clickable, because saying so
          plainly is better than a dead control. */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 18 }}>
        {EVIDENCE_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{ ...S.step(t.key === tab ? "active" : t.built ? "done" : "todo"), cursor: "pointer" }}
          >
            {t.label}
            {!t.built ? (
              <span style={{ fontSize: 11, opacity: 0.75 }}>not built yet</span>
            ) : null}
          </button>
        ))}
      </div>

      {!active.built ? (
        <div style={S.card}>
          <h3 style={{ ...S.h3, marginTop: 0 }}>Not built yet</h3>
          <p style={{ fontSize: 14, color: C.ink2, lineHeight: 1.6, marginBottom: 0 }}>
            There is no <b>{active.label}</b> module in this codebase — nothing detects it, nothing
            measures it, and there is no partial version running behind this tab. It is here so the
            shape of the screen is visible while the rest gets built, and it will stay empty until
            the module behind it exists.
          </p>
        </div>
      ) : !single ? (
        <div style={S.note}>
          No sample has been scored yet. Run one on the <b>Question</b> screen, then come back
          here to see the vocabulary profile.
        </div>
      ) : (
        <>
          {banners}
          {/* Content dispatch. One branch per built tab. */}
          {tab === "vocab_spelling" ? (
            <VocabularyProfileTab
              d={single}
              firstPass={firstPass}
              overrides={overrides}
              setOverrides={setOverrides}
              onRescore={onRescore}
              rescoring={rescoring}
              rescoreError={rescoreError}
              dirty={dirty}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

function ComingSoonScreen({ title, blurb, items }: { title: string; blurb: string; items: string[] }) {
  return (
    <div>
      <h1 style={S.h1}>{title}</h1>
      <p style={S.sub}>{blurb}</p>
      <div style={S.card}>
        <h3 style={{ ...S.h3, marginTop: 0 }}>Not built yet</h3>
        <ul style={{ fontSize: 14, color: C.ink2, lineHeight: 1.8, paddingLeft: 20, marginBottom: 0 }}>
          {items.map((it) => <li key={it}>{it}</li>)}
        </ul>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- landing screen */
// Orientation only, shown before anything else. No scoring logic lives here.

const DIMENSIONS = [
  { name: "Task Achievement", blurb: "Whether the writing does what the task asked, and there's enough of it." },
  { name: "Language Accuracy", blurb: "How correct the grammar, spelling and punctuation are." },
  { name: "Language Range", blurb: "How wide a range of vocabulary and sentence structures the writer uses." },
  { name: "Organisation", blurb: "How clearly the writing is structured — paragraphs, connectors, logical flow." },
  { name: "Style & Register", blurb: "Whether the tone matches what the task calls for." },
  { name: "Content Quality", blurb: "How developed and thoughtful the ideas are." },
];

const SCALE: Array<[string, number]> = [
  ["Pre-A1", 0], ["A1", 10], ["A1+", 19], ["A2", 29], ["A2+", 36], ["B1", 41],
  ["B1+", 51], ["B2", 58], ["B2+", 67], ["C1", 74], ["C2", 86],
];

const PROCESS = [
  { n: 1, t: "Input", d: "Paste one sample, or upload a batch of scripts." },
  { n: 2, t: "Six sections", d: "Each dimension is scored in its own section." },
  { n: 3, t: "Evidence", d: "An evidence screen shows where every number came from." },
  { n: 4, t: "Final score", d: "The six sections combine into one weighted score." },
];

function ScreenNav({ screen, setScreen }: { screen: ScreenKey; setScreen: (s: ScreenKey) => void }) {
  const idx = SCREENS.findIndex((s) => s.key === screen);
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {SCREENS.map((s, i) => (
          <button
            key={s.key}
            onClick={() => setScreen(s.key)}
            style={{ ...S.step(s.key === screen ? "active" : i < idx ? "done" : "todo"), cursor: "pointer" }}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button style={S.btn2} disabled={idx === 0} onClick={() => setScreen(SCREENS[idx - 1].key)}>← Back</button>
        <button style={S.btn2} disabled={idx === SCREENS.length - 1} onClick={() => setScreen(SCREENS[idx + 1].key)}>Next →</button>
      </div>
    </div>
  );
}

function LandingScreen({ onStart, nav }: { onStart: () => void; nav: React.ReactNode }) {
  return (
    <div style={S.page}>
      {nav}
      <h1 style={S.h1}>Writing Marking</h1>
      <p style={{ ...S.sub, maxWidth: 720 }}>
        This tool scores a piece of student writing against the Global Scale of English (GSE),
        mapped onto CEFR levels from Pre-A1 to C2. It looks at six dimensions of the writing,
        shows the evidence behind every number, and combines them into one final score.
      </p>

      <h2 style={S.h2}>What it scores</h2>
      <div style={S.grid}>
        {DIMENSIONS.map((d) => (
          <div key={d.name} style={S.tile}>
            <div style={S.tileK}>{d.name}</div>
            <div style={{ fontSize: 13, color: C.ink2, marginTop: 6, lineHeight: 1.5 }}>{d.blurb}</div>
          </div>
        ))}
      </div>

      <h2 style={S.h2}>The scale</h2>
      <div style={{ ...S.card, paddingLeft: 24, paddingRight: 30 }}>
        <div style={{ position: "relative", height: 58, margin: "4px 0 0" }}>
          {/* the track itself: a plain 0–100 line, shaded light-to-dark to show direction */}
          <div style={{
            position: "absolute", left: 0, right: 0, top: 30, height: 8, borderRadius: 4,
            background: "linear-gradient(90deg, rgba(11,11,11,0.06), rgba(11,11,11,0.75))",
          }} />
          {SCALE.map(([band, score]) => (
            <div key={band} style={{ position: "absolute", left: `${score}%`, top: 0, transform: "translateX(-50%)" }}>
              {/* band name, sitting above its point on the line */}
              <div style={{ fontSize: 11, fontWeight: 600, color: C.ink, whiteSpace: "nowrap", textAlign: "center" }}>{band}</div>
              {/* the tick, dropping down to the track */}
              <div style={{ width: 2, height: 14, background: C.ink3, margin: "3px auto 0", borderRadius: 1 }} />
            </div>
          ))}
          {SCALE.map(([band, score]) => (
            <div key={band + "-n"} style={{
              position: "absolute", left: `${score}%`, top: 42, transform: "translateX(-50%)",
              ...S.mono, fontSize: 10.5, color: C.ink3,
            }}>
              {score}
            </div>
          ))}
          {/* the scale's own ceiling — nothing is named above 86, but the line runs to 100 */}
          <div style={{ position: "absolute", left: "100%", top: 42, transform: "translateX(-50%)", ...S.mono, fontSize: 10.5, color: C.ink3 }}>
            100
          </div>
        </div>
        <p style={{ fontSize: 12.5, color: C.ink3, marginTop: 10, marginBottom: 0 }}>
          Every dimension maps onto this same 0–100 line, so scores are comparable across sections.
          Bands sit at their real position on the scale — the gap between A2+ and B1 is smaller than
          the gap between C1 and C2 because that's where they actually fall.
        </p>
      </div>

      <h2 style={S.h2}>How it works</h2>
      <div style={S.grid}>
        {PROCESS.map((p) => (
          <div key={p.n} style={S.tile}>
            <div style={S.tileK}>Step {p.n}</div>
            <div style={{ fontSize: 15, fontWeight: 600, marginTop: 4 }}>{p.t}</div>
            <div style={{ fontSize: 13, color: C.ink2, marginTop: 4, lineHeight: 1.5 }}>{p.d}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 24 }}>
        <button style={S.btn} onClick={onStart}>Get started</button>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- the page  */

export default function Page() {
  const [screen, setScreen] = useState<ScreenKey>("landing");
  const [mode, setMode] = useState<"single" | "batch">("single");
  // Pre-filled with a worked sample (real spelling errors + one genuine
  // abstain — "bote" — verified against the live engine) purely so the app
  // has something sensible to show on first load. Not fixture data used by
  // any test; just a default a user can clear and overwrite.
  const SAMPLE_TEXT =
    "Last summer I visited my grandmother's vilage in the mountains. " +
    "The houses are small but very colorfull, and every morning we walked " +
    "down to the river to watch the fishermen. One day a strange bote " +
    "appeared and everyone in the vilage came out to see it. My grandmother " +
    "cooked traditional food for us and told storys about her childhood. " +
    "It was a peacefull and unforgetable trip that I will always remember.";
  const SAMPLE_PROMPT =
    "Describe a memorable trip or visit you made. Say where you went, " +
    "what you did, and why it was memorable.";

  const [text, setText] = useState(SAMPLE_TEXT);

  // The question itself — what the student was asked to do, and against
  // what standard. Target level is a floor: the task is set for this level
  // and above, not an exact expected level.
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [targetLevel, setTargetLevel] = useState("A2");
  const [wordCountMin, setWordCountMin] = useState("60");
  const [wordCountMax, setWordCountMax] = useState("100");
  const wordCountMid = useMemo(() => {
    const min = parseInt(wordCountMin, 10);
    const max = parseInt(wordCountMax, 10);
    if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
    return Math.round((min + max) / 2);
  }, [wordCountMin, wordCountMax]);
  const [questionPrompt, setQuestionPrompt] = useState(SAMPLE_PROMPT);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [single, setSingle] = useState<Detail | null>(null);
  // The override-adjusted reading, when a marker has re-scored. Kept separate
  // from `single` so the baseline sent back to the API is always the ORIGINAL
  // model pass — otherwise clearing an override would revert to a previous
  // override rather than to what the model actually said.
  const [approved, setApproved] = useState<Detail | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({});
  // The corrections the result in `approved` was actually computed from, so
  // "ready to apply" and "already applied" can be told apart.
  const [appliedOverrides, setAppliedOverrides] = useState<Overrides>({});
  const [rescoring, setRescoring] = useState(false);
  const [rescoreError, setRescoreError] = useState<string | null>(null);
  // Everything downstream reads the freshest interpretation, not the first one.
  const current = approved ?? single;
  const overridesDirty = JSON.stringify(overrides) !== JSON.stringify(appliedOverrides);

  const [rows, setRows] = useState<Array<{ id: string; text: string; meta?: any }>>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [batch, setBatch] = useState<Summary[] | null>(null);
  const [open, setOpen] = useState<Detail | null>(null);
  // The first thing anyone does with these columns is sort by spelling and look
  // at the bottom. Nulls always sort last, whichever direction — a script with
  // no score is not the weakest script, it is an unmeasured one.
  const [sort, setSort] = useState<{ key: "vocabulary_score" | "spelling_score" | null; dir: 1 | -1 }>(
    { key: null, dir: 1 }
  );
  const sortBy = (key: "vocabulary_score" | "spelling_score") =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  const sorted = (list: Summary[]) => {
    if (!sort.key) return list;
    const k = sort.key;
    return [...list].sort((a, b) => {
      const av = a[k], bv = b[k];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * sort.dir;
    });
  };
  const fileRef = useRef<HTMLInputElement>(null);

  const stage: 1 | 2 = single || batch ? 2 : 1;

  async function post(body: any) {
    const res = await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    let data: any;
    try {
      data = JSON.parse(raw);
    } catch {
      // The API route returned something that isn't JSON — almost always an
      // HTML error page (a 404, or a dev-server error page), not a real
      // response from api/score.py. The most common cause: the Python
      // function only runs under `vercel dev`; plain `next dev` serves the
      // frontend but has nothing behind /api/score, so this request 404s to
      // an HTML page. Surface that plainly instead of the raw JSON.parse error.
      throw new Error(
        res.status === 404
          ? "Couldn't reach the scoring API (got a web page back, not data). If you're running `next dev`, switch to `vercel dev` — the Python scoring function only runs there."
          : `The server sent back something unexpected (status ${res.status}), not the usual result. Try again, and if it keeps happening, check that \`vercel dev\` is running.`
      );
    }
    if (!res.ok) throw new Error(data.error ?? `Request failed (${res.status})`);
    return data;
  }

  async function runSingle() {
    setBusy(true); setError(null); setSingle(null); setProgress("correcting spelling and scoring…");
    // A new sample starts a new review. Carrying a previous sample's overrides
    // forward would apply one script's corrections to another's tokens.
    setApproved(null); setOverrides({}); setAppliedOverrides({}); setRescoreError(null);
    try {
      const data = await post({
        mode: "single", text,
        task: taskType, cefr: targetLevel,
        word_count_min: wordCountMin, word_count_max: wordCountMax,
        word_count_mid: wordCountMid != null ? String(wordCountMid) : "",
        prompt: questionPrompt,
      });
      setSingle(data.result);
      setScreen("translate");
    } catch (e: any) { setError(e.message ?? String(e)); }
    finally { setBusy(false); setProgress(null); }
  }

  // Re-run the interpretation with the marker's answers folded in. No model
  // call happens on this path — the API rebuilds the same candidate list and
  // substitutes a synthetic verdict set — so this is cheap and repeatable.
  async function rescore() {
    if (!single) return;
    setRescoring(true); setRescoreError(null);
    try {
      const data = await post({
        mode: "override",
        id: single.id,
        text: single.text,
        // ALWAYS the first pass. See the comment on `approved`.
        baseline: single.intent_audit ?? [],
        overrides,
        task: taskType, cefr: targetLevel,
        word_count_min: wordCountMin, word_count_max: wordCountMax,
        word_count_mid: wordCountMid != null ? String(wordCountMid) : "",
        prompt: questionPrompt,
      });
      // Communicative Effect reads the as-written text only, so an override
      // cannot change it and the API deliberately doesn't re-ask. Carry the
      // first pass's reading across rather than blanking the panels.
      setApproved({
        ...data.result,
        communicative: single.communicative ?? null,
        communicative_error: single.communicative_error ?? null,
      });
      setAppliedOverrides(overrides);
    } catch (e: any) {
      setRescoreError(e.message ?? String(e));
    } finally {
      setRescoring(false);
    }
  }

  function readFile(file: File) {
    setFileName(file.name); setBatch(null); setOpen(null); setError(null);
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (r) => {
        const data = r.data as Record<string, string>[];
        const cols = r.meta.fields ?? [];
        const pick = (re: RegExp) => cols.find((c) => re.test(c.trim()));
        const textCol = pick(/^(answer_?1?|text|script|response|writing)$/i) ?? cols[0];
        const idCol = pick(/^(id|.*external.?id|sample|candidate)$/i);
        const moeCol = pick(/^moe.?score$/i);
        const humanCol = pick(/^human.?score$/i);
        const taskCol = pick(/^task.?type$/i);
        const cefrCol = pick(/^cefr.?level$/i);
        setRows(data.map((row, i) => ({
          id: (idCol && row[idCol]) || `row_${i + 1}`,
          text: row[textCol] ?? "",
          meta: {
            ...(moeCol && row[moeCol] ? { moe: row[moeCol] } : {}),
            ...(humanCol && row[humanCol] ? { human: row[humanCol] } : {}),
            ...(taskCol && row[taskCol] ? { task: row[taskCol] } : {}),
            ...(cefrCol && row[cefrCol] ? { cefr: row[cefrCol] } : {}),
          },
        })));
      },
    });
  }

  async function runBatch() {
    setBusy(true); setError(null); setBatch(null); setOpen(null);
    try {
      const CHUNK = 100;                       // keeps every request well inside 4.5 MB
      const all: Summary[] = [];
      for (let i = 0; i < rows.length; i += CHUNK) {
        setProgress(`scoring ${Math.min(i + CHUNK, rows.length)} of ${rows.length}…`);
        const slice = rows.slice(i, i + CHUNK).map((r) => ({ id: r.id, text: r.text, ...r.meta }));
        const data = await post({ mode: "batch", rows: slice });
        all.push(...data.results);
      }
      setBatch(all);
    } catch (e: any) { setError(e.message ?? String(e)); }
    finally { setBusy(false); setProgress(null); }
  }

  async function openRow(s: Summary) {
    const row = rows.find((r) => r.id === s.id);
    if (!row) return;
    setBusy(true); setProgress(`loading ${s.id}…`);
    try {
      const data = await post({ mode: "detail", id: row.id, text: row.text, ...row.meta });
      setOpen(data.result);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e: any) { setError(e.message ?? String(e)); }
    finally { setBusy(false); setProgress(null); }
  }

  function reset() {
    setSingle(null); setBatch(null); setOpen(null); setRows([]);
    setFileName(null); setText(""); setError(null);
    setApproved(null); setOverrides({}); setAppliedOverrides({}); setRescoreError(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  const counts = useMemo(() => {
    if (!batch) return null;
    const usable = batch.filter((b) => b.valid);
    const scored = usable.filter((b) => b.confident_band);
    return { total: batch.length, usable: usable.length, scored: scored.length };
  }, [batch]);

  /* -------------------------------------------------------------- render */

  if (screen === "landing") {
    return <LandingScreen onStart={() => setScreen("question")} nav={<ScreenNav screen={screen} setScreen={setScreen} />} />;
  }

  if (open) {
    return (
      <div style={S.page}>
        <ScreenNav screen={screen} setScreen={setScreen} />
        <DetailView d={open} onBack={() => setOpen(null)} />
      </div>
    );
  }

  return (
    <div style={S.page}>
      <ScreenNav screen={screen} setScreen={setScreen} />

      {screen === "question" && (
      <>
      <h1 style={S.h1}>Question</h1>
      <p style={S.sub}>
        Define the task, then paste or upload the writing to be assessed. For now this only
        routes through to the vocabulary dimension — the other five sections plug in here as
        they're built.
      </p>

      <Steps at={stage} />

      <div style={S.tabRow}>
        <button style={S.tab(mode === "single")} onClick={() => { setMode("single"); setOpen(null); }}>Paste one sample</button>
        <button style={S.tab(mode === "batch")} onClick={() => { setMode("batch"); setOpen(null); }}>Upload a batch</button>
        {(single || batch || rows.length) ? <button style={S.btn2} onClick={reset}>Start again</button> : null}
      </div>

      {error ? <div style={{ ...S.card, borderColor: C.bad, color: C.bad }}>{error}</div> : null}

      {mode === "single" ? (
        <>
          <div style={S.card}>
            <h3 style={{ ...S.h3, marginTop: 0 }}>The question</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 14, marginBottom: 14 }}>
              <div>
                <label style={S.label}>Task type</label>
                <select style={S.field} value={taskType} onChange={(e) => setTaskType(e.target.value)}>
                  {TASK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label style={S.label}>Target level</label>
                <select style={S.field} value={targetLevel} onChange={(e) => setTargetLevel(e.target.value)}>
                  {BANDS.filter((b) => b !== "unmatched").map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div>
                <label style={S.label}>Word count (min–max)</label>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    style={S.field} type="number" min={0} inputMode="numeric" placeholder="min"
                    value={wordCountMin} onChange={(e) => setWordCountMin(e.target.value)}
                  />
                  <span style={{ color: C.ink3 }}>–</span>
                  <input
                    style={S.field} type="number" min={0} inputMode="numeric" placeholder="max"
                    value={wordCountMax} onChange={(e) => setWordCountMax(e.target.value)}
                  />
                </div>
              </div>
            </div>
            <p style={{ fontSize: 12, color: C.ink3, margin: "-6px 0 14px" }}>
              Target level is a floor — the task is set for this level <b>and above</b>, not an exact expected level.
              {wordCountMid != null ? <> Middle ground: <b style={{ color: C.ink2 }}>{wordCountMid} words</b>, calculated automatically.</> : null}
            </p>
            <label style={S.label}>Question prompt</label>
            <textarea
              style={{ ...S.field, minHeight: 70, marginBottom: 14 }}
              placeholder="Paste the exact task the student was responding to…"
              value={questionPrompt}
              onChange={(e) => setQuestionPrompt(e.target.value)}
            />
            <label style={S.label}>Student writing</label>
            <textarea
              style={S.ta}
              placeholder="Paste one piece of student writing. Spelling can be as rough as it likes — that is the point."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center" }}>
              <button style={S.btn} onClick={runSingle} disabled={busy || !text.trim()}>
                {busy ? "Working…" : "Process sample"}
              </button>
              {progress ? <span style={{ color: C.ink2, fontSize: 13 }}>{progress}</span> : null}
            </div>
          </div>
          {single ? (
            <div style={{ ...S.note }}>
              Scored. Head to <b>Translate</b> to review the interpretation behind it — and to
              correct it, which re-scores <b>Dimensions</b> against your version rather than the
              model's.
            </div>
          ) : null}
        </>
      ) : (
        <>
          <div style={S.card}>
            <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])} />
            <div style={{ ...S.note, marginTop: 12 }}>
              A CSV with one row per script. The answer column is found automatically
              (<span style={S.mono}>answer_1</span>, <span style={S.mono}>text</span>,{" "}
              <span style={S.mono}>script</span>, <span style={S.mono}>response</span>…), and any{" "}
              <span style={S.mono}>MOE score</span>, <span style={S.mono}>Human score</span>,{" "}
              <span style={S.mono}>task_type</span> or <span style={S.mono}>cefr_level</span>{" "}
              columns are carried through. Sent in batches of 100.
            </div>
            {rows.length ? (
              <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, color: C.ink2 }}>{fileName} — {rows.length} rows</span>
                <button style={S.btn} onClick={runBatch} disabled={busy}>
                  {busy ? "Working…" : "Correct spelling and score all"}
                </button>
                {progress ? <span style={{ color: C.ink2, fontSize: 13 }}>{progress}</span> : null}
              </div>
            ) : null}
          </div>

          {batch && counts ? (
            <>
              <div style={S.grid}>
                <Tile k="Scripts" v={counts.total} n={`${counts.usable} usable`} />
                <Tile k="Levels assigned" v={counts.scored} n="the rest are noise or too short" />
                <Tile
                  k="Unmatched words"
                  v={`${batch.reduce((a, b) => a + b.unmatched_written, 0)} → ${batch.reduce((a, b) => a + b.unmatched_corrected, 0)}`}
                  n="written → corrected"
                />
                <Tile k="Corrections" v={batch.reduce((a, b) => a + b.corrections, 0)} n="across the batch" />
              </div>

              <h2 style={S.h2}>Every script — click a row for the full breakdown</h2>
              <div style={S.card}>
                <table style={S.table}>
                  <thead>
                    <tr>
                      <th style={S.th}>Script</th>
                      {batch.some((b) => b.meta?.moe) ? <th style={S.th}>MOE</th> : null}
                      <th style={{ ...S.th, ...S.num }}>Words</th>
                      <th style={S.th}>Confident level</th>
                      {([
                        ["vocabulary_score", "Vocabulary"],
                        ["spelling_score", "Spelling"],
                      ] as Array<["vocabulary_score" | "spelling_score", string]>).map(([k, lbl]) => (
                        <th key={k} style={{ ...S.th, ...S.num, cursor: "pointer", userSelect: "none" }}
                            onClick={() => sortBy(k)} title="Click to sort">
                          {lbl} /100{sort.key === k ? (sort.dir === 1 ? " ▲" : " ▼") : " ↕"}
                        </th>
                      ))}
                      <th style={{ ...S.th, ...S.num }}>Score</th>
                      <th style={S.th}>Upper</th>
                      <th style={S.th}>Highest item</th>
                      <th style={{ ...S.th, ...S.num }}>Credible</th>
                      <th style={{ ...S.th, ...S.num }}>Conf.</th>
                      <th style={{ ...S.th, ...S.num }}>Fixes</th>
                      <th style={S.th}>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted(batch).map((b, i) => (
                      <tr
                        key={b.id}
                        onClick={() => openRow(b)}
                        style={{ cursor: "pointer", ...(i % 2 ? { background: C.surface2 } : {}) }}
                      >
                        <td style={{ ...S.td, textDecoration: "underline" }}>{b.id}</td>
                        {batch.some((x) => x.meta?.moe) ? <td style={S.td}>{b.meta?.moe ?? "—"}</td> : null}
                        <td style={{ ...S.td, ...S.num }}>{b.words}</td>
                        <td style={{ ...S.td, fontWeight: 600 }}>{b.confident_band ?? "—"}</td>
                        {/* A blank cell reads as a failure; a reason reads as a
                            decision. 9 scripts legitimately have no vocabulary
                            score and 22 no spelling score. */}
                        <td style={{ ...S.td, ...S.num, fontWeight: 600, color: C.written }}>
                          {b.vocabulary_score ?? (
                            <span style={{ fontWeight: 400, fontSize: 12, color: C.ink3 }}>
                              — no level assigned
                            </span>
                          )}
                        </td>
                        <td style={{ ...S.td, ...S.num, fontWeight: 600, color: "#5c9e69" }}>
                          {b.spelling_score ?? (
                            <span style={{ fontWeight: 400, fontSize: 12, color: C.ink3 }}>
                              {b.spelling_reason === "insufficient_sample"
                                ? "— under 8 words"
                                : "— not scored"}
                            </span>
                          )}
                        </td>
                        <td style={{ ...S.td, ...S.num }}>{b.confident_score ?? "—"}</td>
                        <td style={S.td}>{b.upper_band ?? "—"}</td>
                        <td style={S.td}>{b.top_band ?? "—"}</td>
                        <td style={{ ...S.td, ...S.num }}>{b.credible_words ?? "—"}</td>
                        <td style={{ ...S.td, ...S.num }}>{b.composite_confidence?.toFixed(2) ?? "—"}</td>
                        <td style={{ ...S.td, ...S.num }}>{b.corrections}</td>
                        <td style={{ ...S.td, color: C.flag, fontSize: 11.5 }}>
                          {b.valid ? (b.sample_label === "high confidence" ? "" : b.sample_label) : b.verdict}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </>
      )}
      </>
      )}

      {screen === "translate" && <TranslateScreen single={current} />}

      {screen === "evidence_collection" && (
        <EvidenceCollectionScreen
          single={current}
          hasOverrides={overridesDirty}
          firstPass={single}
          overrides={overrides}
          setOverrides={(fn) => setOverrides((prev) => fn(prev))}
          onRescore={rescore}
          rescoring={rescoring}
          rescoreError={rescoreError}
          dirty={overridesDirty}
        />
      )}

      {screen === "dimension_scoring" && (
        <ComingSoonScreen
          title="Dimension scoring"
          blurb="Where the evidence gathered on the Evidence Collection screen is turned into a score for each of the six dimensions. Not built: one evidence module exists so far, so there is nothing to combine yet."
          items={[
            "A score for each of the six dimensions, built from the evidence modules on screen 4",
            "The evidence behind each score, traceable back to the module that produced it",
            "Which evidence informs which dimension — a mapping still being decided as modules are built, and deliberately not guessed at here",
            "Adjustable weighting between dimensions",
          ]}
        />
      )}

      {screen === "final" && (
        <ComingSoonScreen
          title="Final score"
          blurb="The six dimensions combined into one weighted score, once more than one dimension is built and signed off."
          items={[
            "One combined 0–100 score across all six dimensions",
            "The CEFR band that score maps to",
            "A link back to the Dimension scoring screen for how it was reached",
          ]}
        />
      )}
    </div>
  );
}
