"""
The pipeline: raw script in, three vocabulary profiles out.

  1. take the script as-is
  2. separate noise from language -- junk is never corrected and never scored
  3. correct twice: once CAUTIOUS, once LENIENT
  4. match every word in all three versions against the GSE list
  5. build the four views for each version
  6. record what every correction did to the profile, so a human can check it

Three versions rather than two, because on real exam scripts there is no single
right level of leniency. The original is the floor, cautious is what we can
defend, lenient is what the student plausibly meant. The spread between them is
the honest answer to "how much of this score is spelling?".
"""

from .gse import COARSE_ORDER
from .junk import script_verdict
from .scoring import score as score_profile
from .spelling import CAUTIOUS, LENIENT, slot_requirements
from .views import tokenize, build_profile, highest_band, level_measures

_BAND_POS = {b: i for i, b in enumerate(COARSE_ORDER) if b != "N/A"}

VERSIONS = ("original", "cautious", "lenient")


def analyse(text, bank, corrector, name="script", meta=None):
    tokens = tokenize(text)

    # --- step 2: classify every distinct surface form --------------------
    kinds = {}
    for t in tokens:
        w = t["lower"]
        if w not in kinds:
            kinds[w] = corrector.classify(w)
    junk_forms = {w for w, k in kinds.items() if k == "junk"}
    junk_tokens = sum(1 for t in tokens if t["lower"] in junk_forms)

    # --- step 3: correct twice ------------------------------------------
    # The slot each form sits in is worked out first, from the untouched token
    # stream, and handed to the corrector. Without it the corrector compares
    # letters with the sentence removed, and a reading that cannot fill the slot
    # ties with the one that can -- so the word the student attempted is dropped.
    slots = slot_requirements(tokens)
    decisions = {}
    for mode in (CAUTIOUS, LENIENT):
        d = {}
        for w, kind in kinds.items():
            if kind != "known":
                d[w] = corrector.correct(w, mode, require=slots.get(w))
        decisions[mode.name] = d

    streams = {"original": _mark_junk(tokens, junk_forms)}
    for mode_name, d in decisions.items():
        streams[mode_name] = _apply(tokens, d, junk_forms)

    # --- steps 4 and 5: profile every version ---------------------------
    result = {"name": name, "text": text, "meta": meta or {}}
    for v in VERSIONS:
        prof = build_profile(streams[v], bank)
        for rec, tok in zip(prof["full"], streams[v]):
            rec["junk"] = tok.get("junk", False)
        prof["distinct"] = [r for r in prof["distinct"] if not r.get("junk")]
        prof["summary"] = _resummarise(prof["distinct"])
        prof["highest"] = highest_band(prof["distinct"])
        prof["levels"] = level_measures(prof["distinct"])
        prof["score"] = score_profile(prof["distinct"])
        result[v] = prof

    # --- step 6: the audit ----------------------------------------------
    result["audit"] = {m: _audit(decisions[m], tokens, bank) for m in decisions}
    result["junk"] = sorted(
        ({"token": w, "why": corrector.junk.explain(w),
          "occurrences": sum(1 for t in tokens if t["lower"] == w)}
         for w in junk_forms),
        key=lambda r: -r["occurrences"])
    result["junk_tokens"] = junk_tokens

    valid, headline, notes = script_verdict(result["original"]["full"], junk_tokens, text)
    result["valid"] = valid
    result["verdict"] = headline
    # A band, but explicitly a floor rather than a measurement.
    result["minimum_evidence"] = headline == "minimum evidence"
    # A band needs at least one CREDIBLE word, not merely one distinct form.
    # Without this an NVS script -- "(1) FAMLEE" -- passed the short-and-real
    # branch on a single unscoreable token and came back valid with no band,
    # which loosens the non-language exclusion rather than the length one.
    if result["minimum_evidence"] and not result["lenient"]["score"]["assigned"]:
        result["valid"] = False
        result["minimum_evidence"] = False
        result["verdict"] = headline = "too short to profile"
        notes = notes + ["no credible word to place a band on"]
        result["verdict_notes"] = notes
    result["verdict_notes"] = notes
    result["totals"] = _totals(result)
    return result


def _mark_junk(tokens, junk_forms):
    out = []
    for t in tokens:
        n = dict(t)
        n["junk"] = t["lower"] in junk_forms
        out.append(n)
    return out


def _apply(tokens, decisions, junk_forms):
    """Rebuild the token stream with corrections applied. A split becomes
    several tokens; everything else stays one for one."""
    out = []
    for t in tokens:
        d = decisions.get(t["lower"])
        if d and d.get("split"):
            for part in d["split"]:
                out.append({"raw": part, "lower": part, "start": t["start"],
                            "end": t["end"], "junk": False, "was_corrected": True,
                            "original_lower": t["lower"],
                            "confidence": d.get("confidence", 0.0)})
            continue
        n = dict(t)
        n["junk"] = t["lower"] in junk_forms
        if d and d.get("corrected"):
            n["lower"] = d["corrected"]
            n["raw"] = d["corrected"]
            n["was_corrected"] = True
            n["original_lower"] = t["lower"]
            n["confidence"] = d.get("confidence", 0.0)
        else:
            n["was_corrected"] = False
            n["confidence"] = 1.0
        out.append(n)
    return out


def _resummarise(distinct):
    from collections import Counter
    counts = Counter(r["coarse"] if r["matched"] else "unmatched" for r in distinct)
    rows = [{"band": b, "count": counts[b]}
            for b in COARSE_ORDER + ["unmatched"] if counts.get(b)]
    total = sum(r["count"] for r in rows) or 1
    for r in rows:
        r["pct"] = round(100.0 * r["count"] / total, 1)
    return rows


def _audit(decisions, tokens, bank):
    rows = []
    for surface, d in sorted(decisions.items()):
        before = bank.describe(surface)
        row = dict(d)
        row["occurrences"] = sum(1 for t in tokens if t["lower"] == surface)
        row["band_before"] = before["coarse"] if before["matched"] else None
        row["gse_before"] = before["gse"] if before["matched"] else None
        if d.get("corrected"):
            parts = d.get("split") or [d["corrected"]]
            afters = [bank.describe(p) for p in parts]
            best = None
            for a in afters:
                if a["matched"] and (best is None
                                     or _BAND_POS.get(a["coarse"], -1) > _BAND_POS.get(best, -1)):
                    best = a["coarse"]
            row["band_after"] = best
            row["gse_after"] = max((a["gse"] for a in afters if a["gse"] is not None),
                                   default=None)
            row["effect"], row["band_shift"] = _effect(row["band_before"], row["band_after"])
        else:
            row["band_after"] = None
            row["gse_after"] = None
            row["effect"] = "junk — excluded" if d["decision"] == "junk" else "left as-is"
            row["band_shift"] = 0
        row["review_flags"] = _flags(row)
        rows.append(row)
    rows.sort(key=lambda r: (r["decision"] == "junk", -abs(r["band_shift"]),
                             -r["confidence"], r["original"]))
    return rows


def _effect(before, after):
    if before is None and after is None:
        return "still unmatched", 0
    if before is None and after is not None:
        return "created a match (was unmatched)", 0
    if before is not None and after is None:
        return "lost a match", 0
    shift = _BAND_POS.get(after, -1) - _BAND_POS.get(before, -1)
    if shift > 0:
        return "moved up %d band(s)" % shift, shift
    if shift < 0:
        return "moved down %d band(s)" % -shift, shift
    return "same band", 0


def _flags(row):
    """Things a human should look at first. Not errors -- prompts."""
    flags = []
    if row["decision"] in ("corrected", "split"):
        if row["confidence"] < 0.70:
            flags.append("low confidence")
        if abs(row.get("band_shift", 0)) >= 3:
            flags.append("large band jump")
        if row.get("edit_distance", 0) >= 3:
            flags.append("distant edit")
        if row.get("runner_up") and row.get("margin", 1.0) < 0.25:
            flags.append("close call vs '%s'" % row["runner_up"])
    return flags


def _totals(result):
    out = {}
    for v in VERSIONS:
        p = result[v]
        out[v] = {
            "distinct": len(p["distinct"]),
            "unmatched": sum(1 for r in p["distinct"] if not r["matched"]),
            "highest": p["highest"]["band"],
            "tokens": p["counts"]["tokens"],
        }
        out[v].update(p["levels"])
        sc = p["score"]
        out[v].update({
            "credible": sc["credible_count"],
            "sample_label": sc["sample_label"],
            "assigned": sc["assigned"],
            "confident_band": sc["confident"]["band"] if sc["assigned"] else None,
            "confident_score": sc["confident"]["score"] if sc["assigned"] else None,
            "upper_band": sc["upper"]["band"] if sc["assigned"] else None,
            "upper_score": sc["upper"]["score"] if sc["assigned"] else None,
            "top_band": sc["highest"]["band"] if sc["assigned"] else None,
            "top_score": sc["highest"]["score"] if sc["assigned"] else None,
            "top_word": sc["highest"]["word"] if sc["assigned"] else None,
            "composite_confidence": sc["confidence"]["composite"],
        })
    for m in ("cautious", "lenient"):
        rows = result["audit"][m]
        fixed = [r for r in rows if r["decision"] in ("corrected", "split")]
        out[m].update({
            "non_words": sum(1 for r in rows if r["decision"] != "junk"),
            "corrections": len(fixed),
            "splits": sum(1 for r in fixed if r["decision"] == "split"),
            "abstained": sum(1 for r in rows if r["decision"] == "abstained"),
            "created_match": sum(1 for r in fixed if r["effect"].startswith("created")),
            "flagged": sum(1 for r in fixed if r["review_flags"]),
        })
    out["junk_forms"] = len(result["junk"])
    out["junk_tokens"] = result["junk_tokens"]
    return out
