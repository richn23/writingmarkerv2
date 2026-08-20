"""
GSE vocabulary scoring — Vercel Python function.

One endpoint, three modes. The engine underneath is the LENS profiler verbatim
(api/_engine), not a re-implementation, so the deployed app and the local batch
tool cannot drift apart.

  POST /api/score
    { "mode": "single", "text": "..." }                    -> full result
    { "mode": "batch",  "rows": [{ "id": "...", "text": "..." }] }
                                                           -> one summary per row
    { "mode": "detail", "id": "...", "text": "..." }        -> full result for one row
    { "mode": "override", "text": "...", "baseline": [...],
      "overrides": { "<written token>": {"answer": "...", "proposed": "..."} } }
                                                           -> full result,
      re-interpreted with a marker's corrections and re-scored. No model call.

Why batch returns summaries only: full detail for 100 samples is ~16 MB of JSON
and Vercel caps a response at 4.5 MB. Summaries for 100 come to ~30 KB, and the
client asks for detail one sample at a time (~400 KB) when a row is opened.

Deliberately dependency-free — no requirements.txt, nothing to install, nothing
to break on a runtime upgrade.
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# api/_intent/client.py (not modified — see that file's own rules) reads the
# key strictly from an env var named OPENAI_API_KEY. If the Vercel project
# has it saved under a different name (e.g. a typo like OPEN_AI_KEY made
# when the variable couldn't be renamed in place, only deleted/recreated),
# this bridges it across at cold start without touching the protected
# _intent/ code at all. Safe no-op once the real OPENAI_API_KEY exists.
if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPEN_AI_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["OPEN_AI_KEY"]

from _engine.analyse import analyse                      # noqa: E402
from _engine.gse import GseBank                          # noqa: E402
from _engine.scoring import format_lines                 # noqa: E402
from _engine.spelling import Corrector, CAUTIOUS, LENIENT  # noqa: E402
from _intent import client as intent_client              # noqa: E402
from _intent import layer as intent_layer                # noqa: E402
from _intent.review import ANSWERS as INTENT_ANSWERS     # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_data")
MAX_ROWS = 500
MAX_CHARS = 40000        # per sample; longer inputs are truncated, not rejected

_bank = None
_corrector = None

# ---------------------------------------------------------------------------
# Communicative Effect & Translation (docs/05) -- a new caller of the
# existing api/_intent/client.py helper. This does not modify _intent/ or
# _engine/ at all; it only adds a second use of the same proven call()
# function, with its own prompt and schema. Reads the as-written text only,
# per docs/05's evidence-source rule -- never the corrected reading, so the
# judgment can't launder away the friction it exists to measure. Omitted
# entirely (not faked) when OPENAI_API_KEY isn't configured, same as the
# vocabulary intent layer.
# ---------------------------------------------------------------------------

COMMUNICATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_bullets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 5,
        },
        "communicative_level_band": {
            "type": "string",
            "enum": ["Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "B2+", "C1", "C2"],
        },
        "communicative_level_descriptor": {"type": "string"},
        # The band on its own is an assertion. These two make it arguable: what
        # the writing does that the band below does not, and what it fails to do
        # that the band above would. A marker who disagrees can now see the
        # reasoning rather than only the verdict.
        "why_not_below": {"type": "string"},
        "why_not_above": {"type": "string"},
        # The model names the bands it is arguing against, rather than the UI
        # computing them and hoping the two agree. They did not agree: given the
        # six-level grid, a B1 verdict argued against B2 while the screen
        # captioned it "why not B1+".
        "band_below": {"type": "string"},
        "band_above": {"type": "string"},
        "effect_on_reader": {"type": "string"},
    },
    "required": ["summary_bullets", "communicative_level_band",
                 "communicative_level_descriptor",
                 "why_not_below", "why_not_above",
                 "band_below", "band_above", "effect_on_reader"],
    "additionalProperties": False,
}

# Standard CEFR Self-Assessment Grid, Writing row. Swap for Richard's uploaded
# version if it differs from the published grid.
_CEFR_WRITING_GRID = """
A1: Can write a short, simple postcard, for example sending holiday greetings. Can fill in forms with personal details.
A2: Can write short, simple notes and messages. Can write a very simple personal letter.
B1: Can write simple connected text on topics which are familiar or of personal interest. Can write personal letters describing experiences and impressions.
B2: Can write clear, detailed text on a wide range of subjects related to my interests. Can write an essay or report, passing on information or giving reasons in support of or against a particular point of view. Can write letters highlighting the personal significance of events and experiences.
C1: Can express myself in clear, well-structured text, expressing points of view at some length. Can write about complex subjects in a letter, an essay or a report, underlining the points I consider important. Can select a style appropriate to the reader in mind.
C2: Can write clear, smoothly-flowing text in an appropriate style. Can write complex letters, reports or articles which present a case with an effective logical structure. Can write summaries and reviews of professional or literary works.
""".strip()

_COMMUNICATIVE_SYSTEM = """
You are reading one piece of student writing exactly as the student wrote it —
spelling and grammar mistakes included. Do not correct it and do not imagine a
corrected version — judge the raw, as-written text only, the same way a reader
who only ever sees the original would experience it.

Produce four things:

1. summary_bullets: 2-5 short bullet points describing what the student was
   trying to communicate — the content and meaning, not the vocabulary or
   grammar used. Write these as if paraphrasing the student's intended message
   for someone who has not read the script.

2. communicative_level_band + communicative_level_descriptor: your read of how
   well the writing communicates, anchored to the CEFR Writing scale below.
   communicative_level_descriptor MUST start with "Consistent with {band}
   expectations." followed by 1-2 sentences describing the reading experience —
   never state the band on its own with no descriptor.

CEFR Writing scale (Self-Assessment Grid):
""" + _CEFR_WRITING_GRID + """

THE BAND SCALE YOU MUST USE has eleven steps, finer than the six-level grid
above:

    Pre-A1  A1  A1+  A2  A2+  B1  B1+  B2  B2+  C1  C2

The grid above describes A1, A2, B1, B2, C1 and C2. The plus bands sit
immediately above their base band: A1+ is between A1 and A2, B1+ between B1 and
B2, and so on. "Immediately above" and "immediately below" always mean one step
on THIS eleven-step scale, never one level on the six-level grid.

3. why_not_below + why_not_above: the case against the two neighbouring bands,
   one short sentence each, written for a marker who wants to check the
   judgment rather than take it.

   why_not_below: what this writing does that the band immediately BELOW your
   chosen band would not do. Name the specific thing in this script that rules
   the lower band out.

   why_not_above: what this writing does not do, that the band immediately
   ABOVE yours would require. Again, name the specific shortfall in this script.

   Both must point at something actually in the text. Do not restate the band
   definitions at each other, and do not hedge: if you cannot name a concrete
   reason, your chosen band is probably wrong, so change it.

   band_below and band_above: the two bands you are arguing against, named
   exactly as they appear on the eleven-step scale. If your chosen band is B1
   these are "A2+" and "B1+", not "A2" and "B2". Your reasoning must be about
   the bands you name here and no others.

   If your chosen band is Pre-A1 there is no band below: set band_below to ""
   and write "Pre-A1 is the lowest band on the scale." If it is C2 there is no
   band above: set band_above to "" and write "C2 is the highest band on the
   scale."

4. effect_on_reader: one plain-language sentence, for someone who does not
   know CEFR (a class teacher, a parent) — for example "readable with
   occasional re-reading needed". Never reference a CEFR band here.

This is a judgment about how easy the ORIGINAL text is to understand, not a
count of errors and not a vocabulary or grammar assessment — those are scored
elsewhere, from the corrected reading. Base every judgment only on the text
given below, nothing else.
"""


def communicative_effect(text, cfg, deadline_at):
    """One call producing every Communicative Effect / Translation read."""
    return intent_client.call(_COMMUNICATIVE_SYSTEM, text, COMMUNICATIVE_SCHEMA, cfg, deadline_at)


def engine():
    """Built once per warm instance. Cold start is about 1.4 seconds."""
    global _bank, _corrector
    if _corrector is None:
        _bank = GseBank(os.path.join(_DATA, "gse_vocabulary.json"))
        _corrector = Corrector(_bank, os.path.join(_DATA, "english_words.txt"))
    return _bank, _corrector


# ---------------------------------------------------------------------------
# Shaping the engine's output for the browser
# ---------------------------------------------------------------------------

def _words(records):
    return [{
        "word": r.get("raw") or r["token"],
        "matched": bool(r["matched"]),
        "band": r["coarse"] if r["matched"] else None,
        "gse": r.get("gse"),
        "definition": r.get("definition"),
        "junk": bool(r.get("junk")),
        "confidence": round(float(r.get("confidence", 1.0)), 3),
        # A homograph resolved downward. Surfaced so a marker can see that
        # `saw -> see` was applied and overrule it -- making the flip visible was
        # a condition of the rule, not a follow-up to it.
        "collision": r.get("collision"),
    } for r in records]


def _audit(rows):
    return [{
        "original": r["original"],
        "corrected": r.get("corrected"),
        "decision": r["decision"],
        "reason": r["reason"],
        "confidence": round(float(r.get("confidence") or 0), 3),
        "occurrences": r.get("occurrences", 1),
        "band_before": r.get("band_before"),
        "band_after": r.get("band_after"),
        "effect": r.get("effect"),
        "flags": r.get("review_flags", []),
    } for r in rows]


def _corrected_text(text, audit_rows):
    """
    The script rewritten with the accepted corrections applied, so the user can
    read the version the score was actually calculated from.
    """
    import re
    fixes = {r["original"]: r["corrected"] for r in audit_rows if r.get("corrected")}
    if not fixes:
        return text

    def sub(m):
        w = m.group(0)
        rep = fixes.get(w.lower())
        if not rep:
            return w
        return rep.upper() if w.isupper() else (rep.capitalize() if w[0].isupper() else rep)

    return re.sub(r"[A-Za-z']+", sub, text)


def _intent_summary(result):
    """The fourth reading, flattened for the batch table. Absent is normal."""
    prof = result.get("intent")
    if not prof or not prof["score"]["assigned"]:
        return {"intent_band": None, "intent_score": None,
                "intent_note": result.get("intent_note")}
    sc = prof["score"]
    return {
        "intent_band": sc["confident"]["band"],
        "intent_score": sc["confident"]["score"],
        "intent_credible": sc["credible_count"],
        "intent_note": result.get("intent_note"),
    }


def summarise(result):
    t = result["totals"]
    lv = t["lenient"] if result["valid"] else {}
    spell = result.get("spelling") or {}
    cov = result.get("coverage") or {}
    # The row reports the level of the good-spelling version, the same reading
    # the drill-down reports. A table that disagrees with the panel it opens is
    # worse than either number on its own. The deterministic figures stay
    # alongside, under lenient_*, so the calibrated comparison is not lost.
    av = dict(lv)
    prof = result.get("intent")
    if result["valid"] and prof and prof["score"]["assigned"]:
        sc = prof["score"]
        av.update({
            "credible": sc["credible_count"],
            "sample_label": sc["sample_label"],
            "confident_band": sc["confident"]["band"],
            "confident_score": sc["confident"]["score"],
            "upper_band": sc["upper"]["band"],
            "upper_score": sc["upper"]["score"],
            "top_band": sc["highest"]["band"],
            "top_word": sc["highest"]["word"],
            "composite_confidence": sc["confidence"]["composite"],
        })
    sp = result.get("spelling_score") or {}
    vf = result.get("vocabulary_score") or {}
    return {
        # The two scores, both 0-100, both from the intent reading, deliberately
        # independent of each other. Scalars here; the arithmetic is in detail().
        #
        # Gated on `valid` for the same reason the band column is: a script the
        # verdict rejected as too short or not-language must not show a score
        # next to a blank level. One row saying both "—" and "16" is a row
        # nobody can act on.
        # Suppressed on a minimum-evidence script too: the band is a floor we
        # can defend on two words, a 0-100 is not.
        "vocabulary_score": (vf.get("score") if result["valid"]
                             and not result.get("minimum_evidence") else None),
        "spelling_score": (sp.get("score") if result["valid"]
                           and not result.get("minimum_evidence") else None),
        "minimum_evidence": bool(result.get("minimum_evidence")),
        "spelling_reason": ("minimum_evidence" if result.get("minimum_evidence")
                            else sp.get("reason")),
        "spelling_error_rate_scored": sp.get("error_rate"),
        "reading": vf.get("reading"),
        "lenient_band": lv.get("confident_band"),
        "lenient_score": lv.get("confident_score"),
        "spelling_error_rate": spell.get("error_rate"),
        "spelling_profile": spell.get("profile"),
        # How much of the sample the level actually rests on.
        "coverage": cov.get("coverage"),
        "indicative_only": cov.get("indicative_only"),
        **_intent_summary(result),
        "id": result["name"],
        "valid": result["valid"],
        "verdict": result["verdict"],
        "verdict_notes": result["verdict_notes"],
        "words": t["original"]["tokens"],
        "junk_tokens": t["junk_tokens"],
        "credible_words": av.get("credible"),
        "sample_label": av.get("sample_label"),
        "confident_band": av.get("confident_band"),
        "confident_score": av.get("confident_score"),
        "upper_band": av.get("upper_band"),
        "upper_score": av.get("upper_score"),
        "top_band": av.get("top_band"),
        "top_word": av.get("top_word"),
        "composite_confidence": av.get("composite_confidence"),
        "unmatched_written": t["original"]["unmatched"],
        "unmatched_corrected": t["lenient"]["unmatched"],
        "corrections": t["lenient"]["corrections"],
        "distinct": t["lenient"]["distinct"],
    }


def _assessed(result):
    """
    The reading the reported level is OF.

    The process is: fix the spelling, then assess the vocabulary. So when a
    good-spelling version exists, the headline is its level -- reporting the
    lenient figure next to a corrected sample it was not computed from is how
    you get a screen that contradicts itself. The other readings stay in the
    comparison table, as does the as-written column.
    """
    prof = result.get("intent")
    if prof and prof["score"]["assigned"]:
        return "intent", prof
    return "lenient", result["lenient"]


def detail(result):
    out = summarise(result)
    reading, prof = _assessed(result)
    out["assessed_reading"] = reading
    sc = prof["score"]
    audit = _audit(result["audit"]["lenient"])
    out.update({
        "text": result["text"],
        "corrected_text": _corrected_text(result["text"], result["audit"]["lenient"]),
        "score_lines": format_lines(sc),
        "score": {
            "assigned": sc["assigned"],
            "note": sc.get("note"),
            "credible_count": sc["credible_count"],
            "sample_label": sc["sample_label"],
            "confidence": sc["confidence"],
            "confident": sc.get("confident"),
            # The ceiling-adjusted point and the arithmetic behind it. Both are
            # produced by scoring.py's score() and were simply never forwarded
            # here, which is why the UI had nothing to render them from.
            # `ceiling` is flagged first-pass/uncalibrated in scoring.py; the
            # screen says so too rather than presenting it like the rest.
            "reported": sc.get("reported"),
            "ceiling": sc.get("ceiling"),
            "upper": sc.get("upper"),
            "highest": sc.get("highest"),
            "evidence_floor": sc.get("evidence_floor"),
            "evidence_cap": sc.get("evidence_cap"),
            "excluded": sc.get("excluded_low_confidence", []),
        },
        "bands": {v: result[v]["summary"]
                  for v in ("original", "cautious", "lenient", "intent")
                  if result.get(v)},
        # The word chips are the evidence for the headline, so they come from
        # the same reading it does. "written" stays as-written throughout.
        "views": {
            "full": _words(prof["full"]),
            "content": _words(prof["content_only"]),
            "distinct": _words(prof["distinct"]),
            "written": _words(result["original"]["distinct"]),
        },
        "audit": audit,
        "junk": result["junk"],
        "readings": [{
            "reading": v,
            "credible": result[v]["score"]["credible_count"],
            "confident_band": (result[v]["score"]["confident"]["band"]
                               if result[v]["score"]["assigned"] else None),
            "confident_score": (result[v]["score"]["confident"]["score"]
                                if result[v]["score"]["assigned"] else None),
            "upper_band": (result[v]["score"]["upper"]["band"]
                           if result[v]["score"]["assigned"] else None),
            "confidence": result[v]["score"]["confidence"]["composite"],
        } for v in ("original", "cautious", "lenient", "intent")
            if result.get(v)],
        # Every proposal the model made, accepted and rejected alike. The
        # rejections are the evidence that the form test is doing its job.
        "intent_audit": sorted(
            (result.get("intent_decisions") or {}).values(),
            key=lambda d: (d["accepted"], -d["confidence"], d["original"])),
        "intent_note": result.get("intent_note"),
        "spelling": result.get("spelling"),
        # Stage 2's output: the good-spelling version the level was computed
        # from. Spelling only -- no inserted words, no grammar changes.
        "corrected_sample": result.get("corrected_sample"),
        # NOT `corrections` -- summarise() already returns that as a count, and
        # overwriting it with a list put an object where the UI renders a number.
        "spelling_changes": result.get("corrections"),
        # Likewise: `coverage` is the scalar in summarise(). The breakdown gets
        # its own key so one name never carries two shapes.
        "coverage_detail": result.get("coverage"),
        # Every downward homograph resolution in this script, deduplicated.
        "collisions": sorted(
            {(r["token"], r["collision"]["gse"], r["collision"]["band"],
              r.get("gse"), r.get("coarse"))
             for r in prof["distinct"] if r.get("collision")},
            key=lambda x: -(x[1] - (x[3] or 0))),
        # Full arithmetic for both scores, so either number can be checked by
        # hand rather than trusted.
        "spelling_score_detail": result.get("spelling_score"),
        "vocabulary_features": result.get("vocabulary_score"),
    })
    return out


# ---------------------------------------------------------------------------
# Marker overrides -- re-scoring against the approved interpretation
# ---------------------------------------------------------------------------
#
# A marker reviews the vocabulary proposals on the Translate screen and can
# disagree with any of them. Their answers have to re-enter the pipeline as
# first-class verdicts, not as a patch applied afterwards -- a marker typo has
# to fail the form test the same way a model proposal does, or the corrected
# sample quietly breaks.
#
# The way in without touching _intent/ at all: rebuild the SAME candidate list
# the first pass asked about (flag() is deterministic given the same text), put
# a synthetic verdict set in place of the model's reply, and hand both to
# _apply(). No network call happens on this path -- `raw` is manufactured here,
# so nothing is asked and nothing is billed. Every acceptance check the model's
# answers went through, the marker's answers go through too.
#
# Underscore-prefixed is a naming convention inside _intent/, not an access
# restriction; calling _apply() is a call INTO the protected code, not an edit
# OF it, which is the whole point of routing overrides through here.

def _verdict_from_override(token, ov):
    """One marker answer, shaped exactly like a model verdict."""
    answer = ov.get("answer")
    if answer not in INTENT_ANSWERS:
        # An answer the schema does not know is not a silent pass-through: the
        # safe reading of "I do not recognise this instruction" is that nothing
        # was resolved, which is what the model's own fallback says too.
        answer = "unrecoverable"
    proposed = (ov.get("proposed") or "").strip().lower() if answer == "replacement" else ""
    return {
        "token": token,
        "answer": answer,
        "replacement": proposed,
        # 1.0 is the marker's certainty, not a claim about the word. It matters
        # because CREDIBLE_MIN gates what counts toward the level, and a human
        # decision should not be filtered out as low-confidence machine output.
        "confidence": 1.0,
        "reason": "marker override",
    }


def _verdict_from_baseline(token, row):
    """The model's original answer, round-tripped back from the client."""
    return {
        "token": token,
        "answer": row.get("answer"),
        # validate() blanks `proposed` on every answer but `replacement`, so
        # this reproduces the first pass rather than reviving a discarded word.
        "replacement": row.get("proposed") or "",
        "confidence": row.get("confidence") or 0.0,
        "reason": row.get("model_reason") or "",
    }


def rescore_with_overrides(payload):
    """
    Re-run the interpretation with a marker's corrections folded in.

    Deterministic and offline: analyse() and flag() are local, and the verdicts
    are built here rather than asked for. Tokens the marker left alone keep the
    model's original answer, carried in `baseline`; tokens they changed use
    theirs.
    """
    bank, corrector = engine()
    text = (payload.get("text") or "")[:MAX_CHARS]
    if not text.strip():
        return 400, {"error": "no text provided"}
    name = str(payload.get("id") or "sample")
    meta = {k: payload.get(k) for k in
            ("moe", "human", "task", "cefr", "word_count_min", "word_count_max",
             "word_count_mid", "prompt")
            if payload.get(k)}

    overrides = payload.get("overrides") or {}
    if not isinstance(overrides, dict):
        return 400, {"error": "overrides must be an object keyed by written token"}
    overrides = {str(k).strip().lower(): v for k, v in overrides.items()
                 if isinstance(v, dict)}
    baseline = {str(r.get("original") or "").strip().lower(): r
                for r in (payload.get("baseline") or [])
                if isinstance(r, dict) and r.get("original")}

    # A FRESH result. _apply() mutates the dict it is given in place, so it must
    # never be handed one another stage has already written into.
    result = analyse(text, bank, corrector, name=name, meta=meta)
    items = intent_layer.flag(text, result, bank, corrector)

    verdicts, applied = [], []
    asked = set(i["token"] for i in items)
    for it in items:
        tok = it["token"]
        if tok in overrides:
            verdicts.append(_verdict_from_override(tok, overrides[tok]))
            applied.append(tok)
        elif tok in baseline:
            verdicts.append(_verdict_from_baseline(tok, baseline[tok]))
        # Neither: _index() supplies the same "no verdict returned" default the
        # model path uses, so an unanswered token is unresolved, not invented.

    # An override for a token this sample never flagged cannot be applied --
    # reported rather than dropped, because silently ignoring a marker's
    # correction is the one failure mode this whole path exists to prevent.
    unknown = sorted(t for t in overrides if t not in asked)

    intent_layer._apply(result, items, {"verdicts": verdicts},
                        bank, corrector, None)
    intent_layer.assert_complete(result, intent_expected=True)

    out = detail(result)
    out["meta"] = meta
    # Which reading this is. Dimensions reads this rather than guessing, so a
    # marker-adjusted score can never be shown as if it were the first pass.
    out["interpretation_source"] = "marker" if applied else "first_pass"
    out["overrides_applied"] = applied
    out["overrides_unknown"] = unknown
    # Deliberately not re-asked. Communicative Effect reads the as-written text
    # only, which an override cannot change, so re-running it would spend a
    # call to get the same answer. The client carries its first-pass reading
    # forward.
    out["communicative"] = None
    out["communicative_error"] = None
    out["communicative_carried_forward"] = True
    return 200, {"mode": "override", "result": out, "reference": _reference(bank)}


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

def run(payload):
    bank, corrector = engine()
    mode = payload.get("mode") or ("batch" if payload.get("rows") else "single")

    if mode == "override":
        return rescore_with_overrides(payload)

    if mode == "batch":
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            return 400, {"error": "rows must be a list of { id, text }"}
        if len(rows) > MAX_ROWS:
            return 400, {"error": "batch limited to %d rows per request" % MAX_ROWS}
        # Every script is profiled deterministically first, then the whole
        # batch gets ONE concurrent intent pass. Per-script requests issued
        # inside the loop would serialise and blow the duration budget.
        analysed, metas = [], []
        for i, row in enumerate(rows, 1):
            text = (row.get("text") or "")[:MAX_CHARS]
            name = str(row.get("id") or "row_%d" % i)
            meta = {k: row.get(k) for k in
                    ("moe", "human", "task", "cefr", "word_count_min", "word_count_max", "word_count_mid", "prompt")
                    if row.get(k)}
            analysed.append((text, analyse(text, bank, corrector,
                                           name=name, meta=meta)))
            metas.append(meta)
        stats = intent_layer.enrich(analysed, bank, corrector)
        results = []
        for (_, res), meta in zip(analysed, metas):
            s = summarise(res)
            s["meta"] = meta
            results.append(s)
        return 200, {"mode": "batch", "count": len(results), "results": results,
                     "intent": stats, "reference": _reference(bank)}

    text = (payload.get("text") or "")[:MAX_CHARS]
    if not text.strip():
        return 400, {"error": "no text provided"}
    name = str(payload.get("id") or "sample")
    meta = {k: payload.get(k) for k in
            ("moe", "human", "task", "cefr", "word_count_min", "word_count_max", "word_count_mid", "prompt")
            if payload.get(k)}
    res = analyse(text, bank, corrector, name=name, meta=meta)
    stats = intent_layer.enrich([(text, res)], bank, corrector)
    out = detail(res)
    out["meta"] = meta

    out["communicative"] = None
    out["communicative_error"] = None
    if intent_client.available():
        try:
            comm_cfg = intent_client.config()
            out["communicative"] = communicative_effect(
                text, comm_cfg, time.time() + comm_cfg["timeout"])
        except intent_client.IntentUnavailable as exc:
            out["communicative_error"] = str(exc)
        except Exception as exc:                          # never fail the score over this
            out["communicative_error"] = "%s: %s" % (type(exc).__name__, exc)
    else:
        out["communicative_error"] = "no OPENAI_API_KEY configured"

    return 200, {"mode": mode, "result": out, "intent": stats,
                 "reference": _reference(bank)}


def _reference(bank):
    cfg = intent_client.config()
    return {
        "entries": bank.total_entries,
        "single_word_forms": bank.single_word_forms,
        "multi_word_excluded": len(bank.multi_word),
        "cautious": {"accept": CAUTIOUS.accept, "margin": CAUTIOUS.margin},
        "lenient": {"accept": LENIENT.accept, "margin": LENIENT.margin},
        # Which model produced a score has to be reportable, so it is stated
        # even when the layer is switched off.
        "intent": {
            "available": intent_client.available(),
            "model": cfg["model"],
            "effort": cfg["effort"],
        },
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status, obj):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Health check — also warms the instance so the first real call is fast."""
        bank, _ = engine()
        self._send(200, {"ok": True, "reference": _reference(bank)})

    def do_POST(self):
        try:
            length = int(self.headers.get("content-length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:
            self._send(400, {"error": "could not read the request body: %s" % exc})
            return
        try:
            status, out = run(payload)
        except Exception as exc:
            import traceback
            self._send(500, {"error": str(exc), "trace": traceback.format_exc()[-1500:]})
            return
        self._send(status, out)

    def log_message(self, *args):
        pass
