"""
The GSE reference layer: load the vocabulary file, index it, and look words up.

Two rules matter here.

1. LOWEST SENSE WINS. A word with several senses is scored at its lowest GSE
   sense that carries a real number. "make" spans GSE 11-70 across ~12 senses;
   taking the highest would make almost every text score near 70. Senses tagged
   "N/A" (no GSE number) can never win the minimum -- without that guard, "i"
   profiles as N/A despite having a GSE 11 sense.

2. MULTI-WORD ENTRIES ARE EXCLUDED FROM MATCHING in v1, and the count is
   reported so the exclusion is visible rather than silent. Matching phrases in
   running text is a separate problem (inflection inside the phrase, gaps,
   literal-vs-idiomatic) and mixing it in here would muddy the spelling result.
"""

import json
import os

from .lemmas import lemma_candidates
from .scoring import band_for_gse

# Ordered CEFR bands. The GSE file writes them as "B2+ (67-75)" etc.; we keep the
# short band label for reporting and preserve the raw string for audit.
BAND_ORDER = ["<A1", "A1", "A2", "A2+", "B1", "B1+", "B2", "B2+", "C1", "C2", "N/A"]
BAND_RANK = {b: i for i, b in enumerate(BAND_ORDER)}

# ONE BAND VOCABULARY ON SCREEN.
#
# Two band systems were in play and they collided in a way that made the output
# read as self-contradictory. Pearson's own per-entry label calls GSE 10-21
# "<A1" and lumps 22-29 together as "A1". This project's assessment bands
# (scoring.GSE_BANDS) call 10-21 "Pre-A1" and split 22-29 into A1 (22-27) and
# A1+ (28-29) -- which is the vocabulary the ministry's own marks use.
#
# So a word could be labelled "<A1" in the chart while the level line called the
# identical range "Pre-A1", and a word labelled "A1" in the chart could sit in
# either A1 or A1+ on the level line. The chart is meant to be the evidence for
# the level; it has to speak the same language.
#
# Every band shown to a user now comes from scoring.band_for_gse. Pearson's raw
# string is still parsed and kept on `band` for audit, but it does not reach the
# screen.
COARSE_ORDER = ["Pre-A1", "A1", "A1+", "A2", "A2+", "B1", "B1+",
                "B2", "B2+", "C1", "C2", "N/A"]

# Kept only so the raw Pearson sub-band on `band` can still be folded if needed.
COARSE = {b: b for b in COARSE_ORDER}
COARSE["<A1"] = "Pre-A1"


# ---------------------------------------------------------------------------
# Homograph collision: the inflected form carries a level its base never earns
#
# `going` is in the reference list only as a noun ("the going was tough") at GSE
# 78, so "I like going to the beach" was being read as a C1 item. `helping` is
# 80, `moving` 79, `saw` 67 -- the tool, not the past tense. "Lowest sense wins"
# does not help when the inflected form has no low sense of its own.
#
# The count was never wrong -- `distinct` merges on the matched form -- but the
# VALUE flowed into p80_gse, p90_gse, median_gse, the displayed band, and
# `words_at_b2_plus`, which is the one feature carrying real level signal. It was
# contaminated in the direction that flatters the score.
#
# THIS RULE RESOLVES DOWNWARD, ALWAYS, AND THAT IS THE INTENDED TRADE. A student
# who writes "I used a saw" is credited at Pre-A1 rather than B2+. For an
# assessment tool that is correct: one ambiguous token is not evidence of a
# level, and we do not award what we cannot evidence. Every flip is recorded on
# the word record so a marker can see `saw -> see` was applied and disagree.
#
# THE GAP IS THE FINDING; THE EXACT NUMBER IS NOT. Observed on batch 1:
#     flip wanted:  going 63   helping 59   saw 52   moving 45
#     spare these:  training 28   feeling 18   meaning 12
# The clean separation is 28..45, so the threshold sits near the middle rather
# than hugging either edge. Tuning it to the boundary of a dozen cases on one
# batch is how the evidence floor went wrong before.
COLLISION_GAP = 38



def clean_band(raw):
    """'B2+ (67-75)*' -> 'B2+'. The trailing '*' is a Pearson annotation marker."""
    if not raw:
        return "N/A"
    b = raw.split("(")[0].strip().rstrip("*").strip()
    return b if b in BAND_RANK else "N/A"


class GseBank:
    def __init__(self, path):
        self.path = path
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        entries = payload.get("vocabulary", payload) if isinstance(payload, dict) else payload

        self.index = {}            # lowercase single word -> list of sense dicts
        self.multi_word = []       # entries excluded from matching, kept for the audit
        self.total_entries = len(entries)

        for e in entries:
            word = (e.get("word") or "").strip()
            if not word:
                continue
            if " " in word:
                self.multi_word.append(e)
                continue
            self.index.setdefault(word.lower(), []).append(e)

        self.single_word_forms = len(self.index)

    # -- lookup ------------------------------------------------------------

    def resolve(self, token):
        """
        Look a surface form up, trying inflection candidates in contract order.
        Returns (matched_form, sense_dict) or (None, None).
        """
        for cand in lemma_candidates(token):
            senses = self.index.get(cand)
            if senses:
                return cand, self._primary(senses)
        return None, None

    def knows(self, token):
        return self.resolve(token)[0] is not None

    def categories(self, token):
        """
        Every grammatical category this word can be, across ALL its senses.

        The union, not the primary sense's category -- that is what makes it safe
        to eliminate a candidate on grammar. "play" is {noun, verb}, so it
        survives a noun slot and a verb slot alike; "leek" is {noun} only and
        can never be the verb after a subject pronoun. A word is only ever ruled
        out when NONE of its senses could fill the slot.

        Populated on 99.3% of the reference list. An empty set means "unknown",
        and unknown must never eliminate anything.
        """
        form, _ = self.resolve(token)
        if not form:
            return set()
        out = set()
        for s in self.index.get(form) or ():
            raw = (s.get("grammatical_category") or "").strip().lower()
            if not raw:
                continue
            # "adverb; preposition" and "phrasal verb" both appear in the data.
            for part in raw.split(";"):
                part = part.strip()
                if part:
                    out.add(part)
                    if part.endswith("verb"):        # phrasal verb -> verb
                        out.add("verb")
        return out

    @staticmethod
    def _primary(senses):
        """Lowest-GSE sense that has a real number. N/A senses never win the min."""
        scored = [s for s in senses if isinstance(s.get("gse"), (int, float))]
        if scored:
            return min(scored, key=lambda s: s["gse"])
        return senses[0]

    def collision(self, form, gse):
        """
        A base form whose level is far below this inflected form's.

        Returns (base_form, base_sense) or (None, None). Only ever looks
        downward, and only past COLLISION_GAP.
        """
        if not isinstance(gse, (int, float)):
            return None, None
        best = (None, None)
        for cand in lemma_candidates(form):
            if cand == form:
                continue
            senses = self.index.get(cand)
            if not senses:
                continue
            s = self._primary(senses)
            g = s.get("gse") if s else None
            if not isinstance(g, (int, float)) or g >= gse - COLLISION_GAP:
                continue
            if best[1] is None or g < best[1].get("gse"):
                best = (cand, s)
        return best

    def describe(self, token):
        """Full match record for one surface token."""
        form, sense = self.resolve(token)
        collided_from = None
        if sense is not None:
            base, base_sense = self.collision(form, sense.get("gse"))
            if base_sense is not None:
                collided_from = {"form": form, "gse": sense.get("gse"),
                                 "band": band_for_gse(sense.get("gse"))}
                form, sense = base, base_sense
        if sense is None:
            return {
                "token": token, "matched": False, "matched_form": None,
                "gse": None, "band": None, "coarse": None,
                "pos": None, "definition": None, "senses": 0,
            }
        band = clean_band(sense.get("cefr"))
        return {
            "token": token,
            "matched": True,
            "matched_form": form,
            "inflected": form != token,
            "gse": sense.get("gse") if isinstance(sense.get("gse"), (int, float)) else None,
            "band": band,                       # Pearson's own sub-band, for audit
            # What the user sees, and what the level line speaks: the project's
            # assessment bands, derived from the GSE number itself.
            "coarse": band_for_gse(sense.get("gse"))
            if isinstance(sense.get("gse"), (int, float)) else "N/A",
            "pos": (sense.get("grammatical_category") or "").strip() or None,
            "definition": sense.get("definition") or None,
            "senses": len(self.index.get(form, [])),
            # Visible in the audit so a marker can see the flip and disagree.
            "collision": collided_from,
        }

    def all_single_words(self):
        return set(self.index.keys())


def default_gse_path(tool_dir):
    """
    Look for the vocabulary file next to the tool, then in a sibling VALIDATOR
    folder. Override with --gse.
    """
    candidates = [
        os.path.join(tool_dir, "data", "pearson_gse_vocabulary.json"),
        os.path.join(tool_dir, "pearson_gse_vocabulary.json"),
        os.path.join(os.path.dirname(tool_dir), "VALIDATOR", "pearson_gse_vocabulary.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]
