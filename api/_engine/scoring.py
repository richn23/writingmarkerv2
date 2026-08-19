"""
Confidence-weighted vocabulary level, and a 0-100 score.

Replaces the old "highest band" summary, which was set by a single token and
saturated: on the first real batch every script from B1 upwards reported C1.

The idea here is that a word should count toward the level in proportion to how
sure we are it is the word the student actually wrote. A word spelled correctly
counts fully; a word we corrected counts as much as the correction was worth; a
word we were not confident about does not count toward the level at all, though
it stays visible in the profile.

Everything below is deterministic and inspectable — every number on screen can
be traced back to a word and a weight.
"""

# --- 6. GSE to output band -------------------------------------------------
# Note these are the assessment bands for this project, not Pearson's own
# published cut-points: A1 is 22-27 and A1+ is 28-29 here.
GSE_BANDS = [
    ("Pre-A1", 10, 21),
    ("A1", 22, 27),
    ("A1+", 28, 29),
    ("A2", 30, 35),
    ("A2+", 36, 42),
    ("B1", 43, 50),
    ("B1+", 51, 58),
    ("B2", 59, 66),
    ("B2+", 67, 75),
    ("C1", 76, 84),
    ("C2", 85, 90),
]

# --- 7. Target 0-100 scale, one row per band -------------------------------
SCORE_BANDS = {
    "Pre-A1": (0, 9), "A1": (10, 18), "A1+": (19, 28), "A2": (29, 35),
    "A2+": (36, 40), "B1": (41, 50), "B1+": (51, 57), "B2": (58, 66),
    "B2+": (67, 73), "C1": (74, 85), "C2": (86, 100),
}

BAND_NAMES = [b[0] for b in GSE_BANDS]

# --- thresholds ------------------------------------------------------------
CREDIBLE_MIN = 0.70        # a word below this does not count toward the level
RELIABLE_MIN = 0.90        # "reliably matched", for the composite confidence
SUPPORT_WINDOW = 5         # GSE points either side, for the small-sample backstop
SUPPORT_NEEDED = 3         # distinct credible words needed inside that window
FLOOR = 15                 # below this the evidence is thin -- see EVIDENCE_CAP

# --- evidence cap ----------------------------------------------------------
# A short answer cannot demonstrate a wide vocabulary, however advanced the two
# or three words in it happen to be. Rather than refusing to score short
# scripts, we score them and cap how high the level can go.
#
# The caps are read off the first real batch of 100 rather than invented: for
# each band of credible-word count, the 90th percentile of the official MOE band
# actually awarded. Observed, valid scripts only:
#
#   credible words    MOE bands awarded            90th pct
#     3-4             Pre-A1 .. A2+                  A2
#     5-6             A1 .. A2                       A1+
#     7-9             A1 .. B1                       A2+
#     10-14           A1 .. A2+                      A2+
#     20-29           A1+ .. B2+                     B1+
#     30-49           A2+ .. C1                      B2
#     50+             B1 .. C1                       C1
#
# The caps below sit at or just above those, so they clip the over-reads without
# clipping any script the markers actually placed higher.
# (upper limit of credible-word count, floor band, cap band)
EVIDENCE_RANGE = [
    (4, "A1", "A2"),
    (9, "A1+", "A2+"),
    (14, "A2", "A2+"),
    (19, "A2", "B1"),
    (29, None, "B1+"),      # enough words for the percentile to stand on its own
    (49, None, "B2+"),
]                           # 50+ -> no floor, no cap
FALLBACK_RANGE = (None, None)

# WHY THE FLOOR STOPS AT 19 WORDS.
# The floor exists to repair one specific artefact: with few credible words the
# step-down backstop has nothing to land on and walks the level to Pre-A1. That
# only happens when words are scarce, so the repair only belongs there.
#
# Extending floors to 30+ and 50+ scored BETTER on the first batch (79% vs 74%
# within one band) because in that batch the long scripts happened to be the
# strong ones. It is fitting the sample, not the construct -- and it produced a
# visibly wrong answer: the smoke sample, a long piece of plainly A2 writing,
# came out B1 purely because it was long. A rule that credits length as
# vocabulary is not defensible in an assessment tool, so the five points go.


def evidence_range(n):
    """Band floor and cap that this much evidence can support."""
    for limit, floor, cap in EVIDENCE_RANGE:
        if n <= limit:
            return floor, cap
    return FALLBACK_RANGE


def cap_for(n):
    return evidence_range(n)[1]


def apply_range(band, n, stepped_down=0):
    """
    Clamp a band into the range the evidence supports.

    THE CAP is unconditional: three advanced-looking words cannot demonstrate
    B2, however advanced they are.

    THE FLOOR ONLY APPLIES WHEN THE STEP-DOWN BACKSTOP FIRED. That is the one
    thing it was ever meant to repair -- the backstop walking a level down to
    Pre-A1 because it could not find three supporting words to land on. It is
    not a prior about short answers, and it must never override the words
    themselves.

    An earlier version applied the floor unconditionally, and it produced a
    plainly wrong answer: a script whose only words were "school" (GSE 15),
    "big" (18) and "love" (19) -- every one of them below A1 -- was reported as
    A1, purely because the floor for four-or-fewer words said A1. The evidence
    was unambiguous and the floor overrode it. If the words are Pre-A1, the
    level is Pre-A1.

    Returns (band, "capped" | "raised" | None).
    """
    floor, cap = evidence_range(n)
    if band is None:
        return band, None
    i = BAND_NAMES.index(band)
    if cap is not None and i > BAND_NAMES.index(cap):
        return cap, "capped"
    if stepped_down and floor is not None and i < BAND_NAMES.index(floor):
        return floor, "raised"
    return band, None

DEFAULT_CONFIDENT_PCT = 0.80
DEFAULT_UPPER_PCT = 0.90


def band_for_gse(gse):
    if gse is None:
        return None
    for name, lo, hi in GSE_BANDS:
        if gse <= hi:
            return name
    return "C2"


def score_for_gse(gse):
    """
    Position within the band, carried across to the same position in the target
    row. GSE 46 is 43% of the way through B1 (43-50), so it lands 43% of the way
    through the B1 score row (41-50) = 45.
    """
    if gse is None:
        return None
    for name, lo, hi in GSE_BANDS:
        if gse <= hi:
            gse = max(gse, lo)
            pos = 0.0 if hi == lo else (gse - lo) / float(hi - lo)
            slo, shi = SCORE_BANDS[name]
            return int(round(slo + pos * (shi - slo)))
    return 100


# ---------------------------------------------------------------------------
# 1. The credible word list
# ---------------------------------------------------------------------------

def credible_words(distinct_records):
    """
    Every distinct content word that matched the GSE list, with the confidence
    that it is the word the student meant.

      exact match, nothing changed  -> 1.0
      corrected or split            -> the correction's own confidence
      below CREDIBLE_MIN            -> excluded from the level, still shown

    Records must already carry a `confidence` (set when the corrected token
    stream is built) and a `gse`.
    """
    out = []
    for r in distinct_records:
        if r.get("junk") or not r.get("matched") or r.get("gse") is None:
            continue
        conf = r.get("confidence")
        if conf is None:
            conf = 1.0
        out.append({
            "word": r.get("matched_form") or r.get("token"),
            "token": r.get("token"),
            "gse": r["gse"],
            "band": band_for_gse(r["gse"]),
            "confidence": round(float(conf), 4),
            "credible": float(conf) >= CREDIBLE_MIN,
        })
    out.sort(key=lambda w: (w["gse"], w["word"]))
    return out


# ---------------------------------------------------------------------------
# 2. Confidence-weighted percentile
# ---------------------------------------------------------------------------

def weighted_percentile(words, pct):
    """
    Walk up the credible words in GSE order, accumulating each word's confidence
    as its weight rather than a flat 1. Return the GSE value at which the
    running weight first crosses `pct` of the total.
    """
    if not words:
        return None
    total = sum(w["confidence"] for w in words)
    if total <= 0:
        return None
    target = pct * total
    running = 0.0
    for w in words:
        running += w["confidence"]
        if running >= target:
            return w["gse"]
    return words[-1]["gse"]


def support(words, gse):
    """Distinct credible words within SUPPORT_WINDOW GSE points of a value."""
    if gse is None:
        return []
    return [w for w in words if abs(w["gse"] - gse) <= SUPPORT_WINDOW]


# ---------------------------------------------------------------------------
# 3. Small-sample backstop
# ---------------------------------------------------------------------------

def _step_down(words, gse):
    """
    A percentile value is only accepted when at least SUPPORT_NEEDED distinct
    credible words sit within SUPPORT_WINDOW points of it. Otherwise the value
    is a spike rather than a level, and we step down to the top of the next
    lower band and test again, repeating to the floor.

    Returns (gse_value, steps_taken, support_count).
    """
    if gse is None:
        return None, 0, 0
    # Do not start a walk that cannot succeed.
    #
    # The backstop steps down until SUPPORT_NEEDED words sit within
    # SUPPORT_WINDOW of the value. If NO value anywhere in this word list can
    # satisfy that -- because there are too few words, or because they are
    # spread too thinly -- the walk is futile and simply runs to the bottom of
    # the scale. "Consequently the regulations proved catastrophic" has four
    # credible words, every one of them B2 or above, and the walk delivered
    # Pre-A1. The evidence cap is the right instrument for that case: four words
    # cannot demonstrate more than A2, whatever they are.
    if not words or max(len(support(words, w["gse"])) for w in words) < SUPPORT_NEEDED:
        return gse, 0, len(support(words, gse))
    steps = 0
    while True:
        n = len(support(words, gse))
        if n >= SUPPORT_NEEDED:
            return gse, steps, n
        band = band_for_gse(gse)
        i = BAND_NAMES.index(band)
        if i == 0:
            return gse, steps, n         # nothing lower to step to
        # top of the next band down
        gse = GSE_BANDS[i - 1][2]
        steps += 1


# ---------------------------------------------------------------------------
# 4 & 5. Gating and the composite confidence
# ---------------------------------------------------------------------------

def sample_label(n):
    if n < 5:
        return "very low confidence"
    if n < FLOOR:
        return "thin evidence"
    if n < 30:
        return "low confidence"
    if n < 50:
        return "moderate confidence"
    return "high confidence"


def composite_confidence(words, confident_gse):
    n = len(words)
    # Below the 15-word mark the sample term is scaled down rather than zeroed,
    # so a 12-word script and a 3-word script do not carry the same confidence.
    sample = min(n / 50.0, 1.0) * (1.0 if n >= FLOOR else n / float(FLOOR))
    reliable = (sum(1 for w in words if w["confidence"] >= RELIABLE_MIN) / float(n)) if n else 0.0
    k = len(support(words, confident_gse))
    stability = {0: 0.0, 1: 0.33, 2: 0.67}.get(k, 1.0)
    return {
        "sample_size_score": round(sample, 4),
        "match_reliability_score": round(reliable, 4),
        "distribution_stability_score": stability,
        "composite": round(0.4 * sample + 0.3 * reliable + 0.3 * stability, 4),
        "support_at_confident": k,
    }


# ---------------------------------------------------------------------------
# 5b. Ceiling evidence -- folds `upper` and `highest` into the reported score
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. The confident point already places a learner correctly
# within their band (score_for_gse is a straight interpolation), but on its
# own it is a single value and ignores whether the learner also has credible
# evidence reaching further -- the "Learner A vs Learner B" case: two
# learners can both land on the same confident GSE value while one has
# nothing above it and the other has a real, supported spread reaching
# toward the next band. Both stay in the same band -- ceiling evidence must
# never promote a band on its own, `_step_down` already owns that decision --
# but they should not report the same position within it.
#
# HOW IT WORKS. Two independent factors, multiplied so both have to be true
# for a full nudge:
#   strength  how far the upper point reaches past the confident value,
#             scaled against the width of the confident band itself (raw GSE
#             points). 0 = no reach. 1 = reaches a full band-width beyond.
#   trust     how well supported the upper point is (reuses the same
#             support-count buckets as the confidence composite, so a
#             one-word spike counts for little).
# The nudge moves the confident score up by strength * trust * headroom,
# where headroom is the distance from the confident score to the TOP of its
# own band -- so this can never cross into the next band's score value. If
# the confident point has already been capped (evidence too thin to say
# more), headroom is 0 and nothing moves, which is the correct behaviour.
#
# ⚠️ FIRST-PASS, UNCALIBRATED. Unlike the evidence caps above (read off a
# real batch), this formula has not been tested against marked scripts yet.
# It exists so the shape of the effect can be inspected and calibrated once
# a real batch is available -- treat every number in `ceiling` on the result
# as provisional, not as a settled weighting.

CEILING_TRUST = {0: 0.0, 1: 0.33, 2: 0.67}   # by support count, else 1.0


def _ceiling_strength(conf_gse, up_gse, band):
    if conf_gse is None or up_gse is None or up_gse <= conf_gse:
        return 0.0
    lo, hi = next((b[1], b[2]) for b in GSE_BANDS if b[0] == band)
    width = max(1, hi - lo)
    return min(1.0, (up_gse - conf_gse) / float(width))


def _ceiling_trust(support_count):
    return CEILING_TRUST.get(support_count, 1.0)


def ceiling_adjusted(conf_pt, up_pt):
    """
    Returns (reported_point, working). `reported_point` is a copy of
    `conf_pt` with `score` nudged toward the top of its band by ceiling
    evidence. `working` carries strength/trust/nudge/headroom so the
    adjustment can be checked by hand, same as everything else here.
    """
    band = conf_pt.get("band")
    if band is None:
        return dict(conf_pt), {"strength": 0.0, "trust": 0.0, "nudge": 0, "headroom": 0}
    slo, shi = SCORE_BANDS[band]
    headroom = shi - conf_pt["score"]
    strength = _ceiling_strength(conf_pt["gse"], up_pt["gse"], band)
    trust = _ceiling_trust(up_pt.get("support", 0))
    nudge = int(round(strength * trust * headroom))
    out = dict(conf_pt)
    out["score"] = conf_pt["score"] + nudge
    return out, {
        "strength": round(strength, 4), "trust": round(trust, 4),
        "nudge": nudge, "headroom": headroom,
    }


# ---------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------

def score(distinct_records, confident_pct=DEFAULT_CONFIDENT_PCT,
          upper_pct=DEFAULT_UPPER_PCT):
    words = credible_words(distinct_records)
    cred = [w for w in words if w["credible"]]
    excluded = [w for w in words if not w["credible"]]

    result = {
        "credible_count": len(cred),
        "excluded_low_confidence": excluded,
        "words": cred,
        "sample_label": sample_label(len(cred)),
        "assigned": False,
        "confident": None, "upper": None, "highest": None,
        "confident_pct": confident_pct, "upper_pct": upper_pct,
    }

    # Nothing at all to go on. Everything else gets a level, capped by evidence.
    if not cred:
        result["note"] = "no credible words — nothing to score"
        result["confidence"] = composite_confidence(cred, None)
        return result

    raw_conf = weighted_percentile(cred, confident_pct)
    raw_up = weighted_percentile(cred, upper_pct)
    conf_gse, conf_steps, conf_support = _step_down(cred, raw_conf)
    up_gse, up_steps, up_support = _step_down(cred, raw_up)

    # The highest credible item is reported on its own and is never allowed to
    # become the level -- that is the whole point of moving off "highest band".
    top = max(cred, key=lambda w: w["gse"])

    # Upper evidence should never sit below the confident level.
    if up_gse is not None and conf_gse is not None and up_gse < conf_gse:
        up_gse = conf_gse

    n = len(cred)
    conf_pt = _point(conf_gse, raw_conf, conf_steps, conf_support)
    up_pt = _point(up_gse, raw_up, up_steps, up_support)
    conf_pt["band"], conf_pt["clamped"] = apply_range(conf_pt["band"], n, conf_steps)
    up_pt["band"], up_pt["clamped"] = apply_range(up_pt["band"], n, up_steps)
    for pt in (conf_pt, up_pt):
        if pt["clamped"] == "capped":
            pt["score"] = SCORE_BANDS[pt["band"]][1]     # top of the capped band
        elif pt["clamped"] == "raised":
            pt["score"] = SCORE_BANDS[pt["band"]][0]     # bottom of the floor band
    reported_pt, ceiling_work = ceiling_adjusted(conf_pt, up_pt)
    result.update({
        "assigned": True,
        "evidence_floor": evidence_range(n)[0],
        "evidence_cap": evidence_range(n)[1],
        "confident": conf_pt,
        "reported": reported_pt,
        "ceiling": ceiling_work,
        "upper": up_pt,
        "highest": {
            "gse": top["gse"], "band": band_for_gse(top["gse"]),
            "score": score_for_gse(top["gse"]), "word": top["word"],
            "confidence": top["confidence"],
        },
        "confidence": composite_confidence(cred, conf_gse),
    })
    return result


def _point(gse, raw_gse, steps, support_count):
    return {
        "clamped": None,
        "gse": gse,
        "band": band_for_gse(gse),
        "score": score_for_gse(gse),
        "raw_gse": raw_gse,
        "stepped_down": steps,
        "support": support_count,
    }


def format_lines(s):
    """The three-line summary, exactly as specified."""
    if not s["assigned"]:
        return ["Confident lexical level: not assigned — %s" % s.get("note", "")]
    cap = ""
    if s["confident"].get("clamped") == "capped":
        cap = " [capped — %d credible words cannot show more]" % s["credible_count"]
    elif s["confident"].get("clamped") == "raised":
        cap = " [floored — too few words to read the level any lower]"
    return [
        "Confident lexical level: %s — %s (score: %d)%s"
        % (s["confident"]["band"], s["sample_label"], s["confident"]["score"], cap),
        "Reported score (ceiling-adjusted): %s (score: %d)%s"
        % (s["reported"]["band"], s["reported"]["score"], cap),
        "Upper evidence: %s (score: %d)" % (s["upper"]["band"], s["upper"]["score"]),
        'Highest credible item: %s (score: %d) — "%s"'
        % (s["highest"]["band"], s["highest"]["score"], s["highest"]["word"]),
    ]
