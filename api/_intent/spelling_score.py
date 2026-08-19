"""
The spelling score, 0-100. Orthographic control, independent of vocabulary range.

100 means every word attempted was spelled correctly. The score falls as errors
accumulate, weighted by how serious the error is, how easy the word should have
been, and whether the student makes it consistently.

WHY THE DENOMINATOR IS THE DIFFICULTY SUM AND NOT A WORD COUNT. It normalises
the penalty against the difficulty of the words THIS student attempted. With a
plain count, a stronger-vocabulary student is automatically penalised less per
error and the spelling score decays into a restatement of the vocabulary score.
Two writers with the same error rate at opposite ends of the range must land on
the same number, and they do:

    Pre-A1 writer, 10 Pre-A1 words (1.00), 2 minor slips
      cost 2 x 0.4 x 1.00 = 0.80   /  denominator 10.0  ->  92
    C1 writer, 10 C1 words (0.50), 2 minor slips
      cost 2 x 0.4 x 0.50 = 0.40   /  denominator  5.0  ->  92

Scored over ALL word tokens, not just content words -- orthographic control
covers "becuase" and "teh" as much as "enviroment". That is a deliberate
difference from the vocabulary score.
"""

# --- a. severity: what kind of error it is ---------------------------------
SEVERITY = {
    "correct": 0.0,
    "minor_slip": 0.4,        # one edit, same sound: beautifull
    "boundary": 0.5,          # run together or split: alot, Iplay
    "phonetic": 0.7,          # spelled as it sounds, 2+ edits: skooi, kloz
    "wrong_word": 0.8,        # produced a different real word: bast, hared
    "unrecoverable": 1.0,     # no confident reading
    "proper_noun": None,      # excluded entirely -- a name is not an error
}

# --- b. difficulty: how easy the word should have been to spell ------------
# Read from the GSE band of the INTENDED word. Misspelling "school" says more
# about orthographic control than misspelling "catastrophic" does.
DIFFICULTY = {
    "Pre-A1": 1.00,
    "A1": 0.90, "A1+": 0.90,
    "A2": 0.80, "A2+": 0.80,
    "B1": 0.70, "B1+": 0.70,
    "B2": 0.60, "B2+": 0.60,
    "C1": 0.50, "C2": 0.50,
}
UNLISTED_DIFFICULTY = 0.60        # a real word the reference list does not carry
_LADDER = [1.00, 0.90, 0.80, 0.70, 0.60, 0.50]

# KNOWN-HARD EXEMPTION. GSE level says when a learner MEETS a word, not how hard
# it is to spell, and the classic traps are all low-level. These drop one
# difficulty step. Keep the list short and visible; add only from observed data.
KNOWN_HARD = {
    "because", "friend", "beautiful", "people", "said", "they", "their",
    "there", "where", "women", "business", "receive", "believe", "achieve",
    "necessary", "different", "enough", "through", "though", "thought",
    "bought", "brought", "which", "whose", "tomorrow", "restaurant",
    "favourite", "weather", "whether",
}

MIN_ATTEMPTED = 8       # below this a number is not a measurement


def _step_down(weight):
    """One step easier on the difficulty ladder."""
    for i, w in enumerate(_LADDER):
        if abs(w - weight) < 1e-9:
            return _LADDER[min(i + 1, len(_LADDER) - 1)]
    return weight


def difficulty_for(intended, band):
    """Difficulty weight for the word the student was reaching for."""
    w = DIFFICULTY.get(band, UNLISTED_DIFFICULTY)
    if intended and intended.lower() in KNOWN_HARD:
        w = _step_down(w)
    return w


def persistence_for(attempt, by_intended):
    """
    Slip or belief. A wrong form produced once is a slip; the same wrong form
    produced every time is a belief and costs more. Several different wrong
    forms for one word are slips again -- the student is guessing, not certain.
    """
    if attempt["occurrences"] < 2 or attempt["category"] == "correct":
        return 1.0
    forms = by_intended.get(attempt["intended"] or attempt["written"], set())
    return 1.3 if len(forms) == 1 else 1.0


def score(attempts):
    """
    `attempts` is one record per DISTINCT written form actually attempted:

        {written, intended, category, band, occurrences}

    Proper nouns, junk and anything non-alphabetic must already be excluded by
    the caller. Returns the score plus every input, so the arithmetic on screen
    can be checked by hand.
    """
    counted = [a for a in attempts if SEVERITY.get(a["category"]) is not None]
    if len(counted) < MIN_ATTEMPTED:
        return {
            "score": None,
            "reason": "insufficient_sample",
            "attempted": len(counted),
            "minimum": MIN_ATTEMPTED,
            "categories": _split(counted),
            "errors": sum(1 for a in counted if a["category"] != "correct"),
        }

    # Wrong forms per intended word, for the slip-or-belief test.
    by_intended = {}
    for a in counted:
        key = a["intended"] or a["written"]
        if a["category"] != "correct":
            by_intended.setdefault(key, set()).add(a["written"])

    # `unrecoverable` has no intended word, so its difficulty cannot be read.
    # Use the student's own mean across everything else they attempted.
    known = [difficulty_for(a["intended"], a["band"]) for a in counted
             if a["category"] != "unrecoverable"]
    fallback = round(sum(known) / len(known), 4) if known else UNLISTED_DIFFICULTY

    rows, total_cost, total_diff = [], 0.0, 0.0
    for a in counted:
        d = (fallback if a["category"] == "unrecoverable"
             else difficulty_for(a["intended"], a["band"]))
        sev = SEVERITY[a["category"]]
        per = persistence_for(a, by_intended)
        cost = sev * d * per
        total_cost += cost
        total_diff += d
        if a["category"] != "correct":
            rows.append({
                "written": a["written"], "read_as": a["intended"],
                "category": a["category"], "band": a["band"],
                "severity": sev, "difficulty": round(d, 3),
                "persistence": per, "cost": round(cost, 4),
                "occurrences": a["occurrences"],
            })

    index = 1.0 - (total_cost / total_diff) if total_diff else 0.0
    errors = sum(1 for a in counted if a["category"] != "correct")
    return {
        "score": int(round(max(0.0, index) * 100)),
        "reason": None,
        "attempted": len(counted),
        "errors": errors,
        "error_rate": round(100.0 * errors / len(counted), 1),
        "categories": _split(counted),
        # The arithmetic, so the number can be checked rather than trusted.
        "total_cost": round(total_cost, 4),
        "total_difficulty": round(total_diff, 4),
        "index": round(max(0.0, index), 4),
        "mean_difficulty": fallback,
        "detail": sorted(rows, key=lambda r: -r["cost"]),
    }


def _split(counted):
    out = {}
    for a in counted:
        out[a["category"]] = out.get(a["category"], 0) + 1
    return out
