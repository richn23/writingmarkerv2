"""
Spelling normalisation for learner writing.

DESIGN RULE, stated up front because it is the whole point of this module:
WORD FREQUENCY IS NEVER USED TO RANK A CORRECTION. Generic spellcheckers rank
candidates by how common they are, which systematically drags a misspelt
advanced word toward an unrelated common one -- exactly the failure that would
make a vocabulary-range score wrong in the deflating direction. Nothing in this
file reads a frequency count.

Ranking evidence, in the order it carries weight:
  1. edit distance, with the budget SCALED TO WORD LENGTH (long, rare, advanced
     words are where learners make multi-character errors)
  2. phonetic key match (a Metaphone-style key: learners spell by sound)
  3. consonant-skeleton match (vowels dropped, doubled letters collapsed --
     catches minets/minutes, clossed/closed, finaly/finally)
  4. doubled-letter-only difference (beautifull/beautiful, finaly/finally) --
     the single commonest learner slip
  5. shared lemma -- the candidate and the misspelling reduce to the same base
     form ("storys"/"stories" both reduce to "story"), which is the signature of
     a regularised inflection rather than a different word
  6. shared prefix, then shared suffix
  7. as a TIE-BREAK ONLY, whether the candidate is a word in the GSE reference
     list at all. This is not frequency: the GSE list spans <A1 to C2, so it
     carries advanced vocabulary as readily as common vocabulary. It exists to
     stop an obscure dictionary word ("peale", "wether", "nyx") tying with the
     obvious intended word. Its weight (0.06) is set just above the separation
     margin, so it can break a tie and can never drive a correction on its own.

Hard filters applied before any scoring:
  - first letter must match
  - length difference must be within 2 + 20% of the word's length
  - edit distance must be inside the length-scaled budget

If nothing clears the confidence bar, or the top two candidates are too close to
separate, THE WORD IS LEFT UNCORRECTED and the reason is logged. Under-correcting
is safe; inventing vocabulary the student never wrote is not.
"""

import re

from .lemmas import lemma_candidates, british_variants, CONTRACTIONS, US_TO_UK
from .junk import JunkDetector, MIN_CORRECTABLE

# ---------------------------------------------------------------------------
# Phonetic key (Metaphone-style, deliberately compact and deterministic)
# ---------------------------------------------------------------------------

_SOUND_GROUPS = [
    ("tion", "xn"), ("sion", "xn"), ("cion", "xn"), ("cian", "xn"),
    ("tial", "xl"), ("cial", "xl"), ("tious", "xs"), ("cious", "xs"),
    ("ough", "of"), ("augh", "af"),
    ("sch", "sk"), ("tch", "x"), ("ph", "f"), ("ck", "k"),
    ("sh", "x"), ("ch", "x"), ("th", "0"), ("wh", "w"),
]


def phonetic_key(w):
    """Rough sound-shape of a word. Two words with the same key sound alike."""
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return ""
    # silent openings
    for pre, rep in (("kn", "n"), ("gn", "n"), ("pn", "n"), ("wr", "r"), ("ps", "s")):
        if w.startswith(pre):
            w = rep + w[2:]
            break
    for a, b in _SOUND_GROUPS:
        w = w.replace(a, b)
    out = []
    for i, ch in enumerate(w):
        if ch == "c":
            out.append("s" if i + 1 < len(w) and w[i + 1] in "eiy" else "k")
        elif ch == "q":
            out.append("k")
        elif ch == "x":
            out.append("ks")
        elif ch == "z":
            out.append("s")
        elif ch == "g":
            out.append("j" if i + 1 < len(w) and w[i + 1] in "eiy" else "g")
        elif ch == "v":
            out.append("f")
        else:
            out.append(ch)
    key = "".join(out)
    first = key[0]
    body = re.sub(r"[aeiouyh]", "", key[1:])
    key = (first if first in "aeiou" else first) + body
    return re.sub(r"(.)\1+", r"\1", key)


def skeleton(w):
    """Consonant skeleton: vowels dropped, runs of a letter collapsed."""
    return re.sub(r"(.)\1+", r"\1", re.sub(r"[aeiouy]", "", w.lower()))


# ---------------------------------------------------------------------------
# Damerau-Levenshtein with an early exit
# ---------------------------------------------------------------------------

def edit_distance(a, b, limit):
    """Optimal string alignment distance. Returns limit+1 once it exceeds limit."""
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        row_min = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, prev2[j - 2] + 1)          # transposition
            cur[j] = v
            if v < row_min:
                row_min = v
        if row_min > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[lb]


def max_edits(word):
    """
    Edit budget scaled to word length -- never a flat 1 or 2. Long words are
    where learners make multi-character errors, and a long word is usually the
    advanced one, so a flat budget silently protects short common words and
    abandons the vocabulary we most want to recover.
    """
    return max(1, min(4, len(word) // 2))


def split_word(w, known, in_gse=None, min_part=3):
    """
    Split a run-together string into real words: "iplay" -> "i play",
    "igo" -> "i go", "infront" -> "in front", "heisgotis" -> "he is got is".

    Very common in these scripts and, left alone, every part counts as
    unmatched -- so the profile loses vocabulary the student demonstrably has.

    Parts must be real words. Short parts are only allowed from a closed list of
    genuine short words, otherwise any string can be diced into fragments.
    """
    n = len(w)
    if n < 3:
        return None
    # best[i] = best split of w[:i] as a list of words, or None
    best = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(0, i):
            if best[j] is None:
                continue
            part = w[j:i]
            ok = part in known and (len(part) >= min_part or part in _SHORT_WORDS)
            # Every part must be vocabulary in its own right. Without this,
            # "afternon" becomes "after non" instead of "afternoon".
            if ok and in_gse is not None:
                ok = in_gse(part)
            if not ok:
                continue
            cand = best[j] + [part]
            if best[i] is None or len(cand) < len(best[i]):
                best[i] = cand
    parts = best[n]
    if not parts or len(parts) < 2 or len(parts) > 4:
        return None
    if not any(len(p) >= min_part for p in parts):
        return None
    return parts


# Run-together errors so common they are worth naming outright.
RUN_TOGETHER = {
    "alot": "a lot", "infront": "in front", "aswell": "as well",
    "atleast": "at least", "infact": "in fact", "incase": "in case",
    "aslong": "as long", "eachother": "each other", "alongtime": "a long time",
    "everyday": "every day", "somemore": "some more", "abit": "a bit",
    "inorder": "in order", "ofcourse": "of course", "thankyou": "thank you",
    "goodmorning": "good morning", "somethimes": "sometimes",
}

# Short words allowed as a split part. Anything outside this list must be 3+
# letters, or "somthing" would happily become "so m thing".
_SHORT_WORDS = {
    "i", "a", "am", "an", "as", "at", "be", "by", "do", "go", "he", "if",
    "in", "is", "it", "me", "my", "no", "of", "on", "or", "so", "to", "up",
    "us", "we", "he", "id", "ok",
}


def doubling_only(a, b):
    """True when the two words differ only in which letters are doubled."""
    collapse = lambda w: re.sub(r"(.)\1+", r"\1", w)
    return a != b and collapse(a) == collapse(b)


# ---------------------------------------------------------------------------
# Morphological repairs -- targeted fixes for the two error patterns that
# dominate learner writing and that general candidate ranking handles badly.
#
#   1. a regularised plural: "storys"/"countrys"/"familys" for -ies
#   2. a letter doubled where it should not be, or not doubled where it should:
#      "beautifull", "carefull", "finaly", "diferent"
#
# These are not guesses. Each produces a small, closed set of targets, and the
# repair is only used when EXACTLY ONE of them is both a real word and a word in
# the GSE reference list. Anything ambiguous falls through to normal ranking.
# ---------------------------------------------------------------------------

_CONSONANTS = "bcdfghjklmnpqrstvwxz"


def morphological_repairs(word):
    """Candidate repairs for regularised inflections and doubling slips."""
    out = set()
    w = word.lower()
    # regularised plural: consonant + "ys" -> "ies"
    if len(w) > 3 and w.endswith("ys") and w[-3] not in "aeiou":
        out.add(w[:-2] + "ies")
    # regularised past: consonant + "yed" -> "ied"
    if len(w) > 4 and w.endswith("yed") and w[-4] not in "aeiou":
        out.add(w[:-3] + "ied")
    # dropped stem "y" before -ing  (studing -> studying). Included so that a
    # word like "studing" has TWO valid repairs (studying, studding) and is
    # therefore treated as ambiguous rather than confidently mis-repaired.
    if len(w) > 4 and w.endswith("ing"):
        out.add(w[:-3] + "ying")
    # collapse every doubled letter  (beautifull -> beautiful)
    collapsed = re.sub(r"(.)\1+", r"\1", w)
    if collapsed != w:
        out.add(collapsed)
    # double one single consonant  (finaly -> finally, diferent -> different)
    for i, ch in enumerate(w):
        if ch in _CONSONANTS and w[i - 1:i] != ch and w[i + 1:i + 2] != ch:
            out.add(w[:i + 1] + ch + w[i + 1:])
    return out - {w}


# ---------------------------------------------------------------------------
# The corrector
# ---------------------------------------------------------------------------

# Every real one- and two-letter English word. Anything else that short is a
# stray keystroke, not vocabulary.
_REAL_SHORT = set("""
a i am an as at ax be by do go ha he hi id if in is it la me my no of oh ok on
or ox pi so to up us we ye yo im tv uk ad ah aw ay bi bo de ed eh el em en er
ex fa ho jo ka ki lo ma mi mm mu na ne nu od oe oi om op os ow oy pa pe qi re
se sh si ta ti uh um un ur ut wo xi xu za
""".split())

# Contractions and very short forms we never treat as misspellings.
_NEVER_CORRECT = {
    "i", "a", "im", "id", "ive", "ill", "dont", "cant", "wont", "didnt", "doesnt",
    "isnt", "arent", "wasnt", "werent", "havent", "hasnt", "hadnt", "couldnt",
    "wouldnt", "shouldnt", "thats", "its", "hes", "shes", "theyre", "youre",
    "were", "weve", "theyve", "youve", "lets", "ok", "okay", "tv", "uk", "usa",
}

# ---------------------------------------------------------------------------
# Two settings, run side by side rather than chosen between.
#
# CAUTIOUS answers "what can we correct and still be sure?" -- on the labelled
# test set it makes no wrong corrections at all. LENIENT answers "what could
# this student plausibly have meant?" -- it recovers far more, and some of it
# will be wrong. Reporting both shows the range the real vocabulary profile sits
# in, which is the actual question, rather than pretending one number is right.
#
# Real exam scripts need the lenient end. Spellings like KLOZ (close), NEAM
# (name) and SKOOI (school) are three and four edits from the target and no
# cautious setting will ever reach them.
# ---------------------------------------------------------------------------

class Mode(object):
    def __init__(self, name, accept, margin, budget, evidence_required=True,
                 min_length=MIN_CORRECTABLE):
        self.name = name
        self.accept = accept
        self.margin = margin
        self.budget = budget
        self.evidence_required = evidence_required
        # Shortest non-word this mode will try to correct. Cautious stays at 4;
        # three-letter noise is where "ggh"->"gogh" and "hji"->"haji" came from.
        # Lenient drops to 3 because the reference-list filter and the junk
        # detector now block those targets, and real three-letter attempts
        # ("nex" for "next") are common in these scripts.
        self.min_length = min_length


CAUTIOUS = Mode("cautious", accept=0.55, margin=0.16,
                budget=lambda n: max(1, min(4, n // 2)))
LENIENT = Mode("lenient", accept=0.42, margin=0.04,
               budget=lambda n: max(2, min(5, (n + 1) // 2)), min_length=3)
MODES = {"cautious": CAUTIOUS, "lenient": LENIENT}

# Kept for the threshold-search script, which sweeps these directly.
ACCEPT_SCORE = CAUTIOUS.accept
MIN_MARGIN = CAUTIOUS.margin


class Corrector:
    def __init__(self, gse_bank, wordlist_path, extra_words=()):
        self.gse = gse_bank

        # KNOWN-WORD SET (detection only). A word here is "real" and is never
        # corrected. This is a general English list UNION the GSE list -- the
        # general list is essential, otherwise every legitimate English word that
        # happens to be outside the GSE bank would be treated as a misspelling
        # and forced toward a GSE word.
        self.known = set()
        with open(wordlist_path, encoding="utf-8") as fh:
            for line in fh:
                w = line.strip().lower()
                if w:
                    self.known.add(w)
        self.wordlist_size = len(self.known)
        self.known |= gse_bank.all_single_words()
        self.known |= set(extra_words)
        # British spellings, added to the KNOWN set as well as the pool: a
        # correct British form must never be detected as a misspelling.
        for w in list(self.known):
            self.known.update(british_variants(w))
        # Apostrophe-less contractions count as real words, and are also valid
        # correction targets ("wouldent" -> "wouldnt" -> the GSE entry "would").
        self.known.update(CONTRACTIONS.keys())

        # CANDIDATE POOL = ATTESTED WORDS ONLY.
        # An earlier version widened the pool with machine-generated inflections
        # of every GSE lemma. That produced ~94,000 non-words ("eraly" from
        # "era", "desperatelys", "(sic)ed") and one of them promptly out-scored
        # the right answer: "erly" corrected to "eraly" instead of "early".
        # A correction target must be a word someone has actually written.
        # British spellings are folded into the known set above rather than
        # generated here, so they count as correct rather than as targets.
        pool = set(self.known)
        self.pool_size = len(pool)

        # Bucketed by (first letter, length) so a lookup compares against a small
        # window rather than the whole pool.
        self.buckets = {}
        for w in pool:
            if not w or not w.isalpha():
                continue
            self.buckets.setdefault((w[0], len(w)), []).append(w)

        # Noise detector, built from the same word list so "does this look like
        # English" is answered from data. Junk is never corrected.
        self.junk = JunkDetector(sorted(w for w in self.known if w.isalpha()))

        self._phon = {}
        self._skel = {}

    def _pk(self, w):
        v = self._phon.get(w)
        if v is None:
            v = phonetic_key(w)
            self._phon[w] = v
        return v

    def _sk(self, w):
        v = self._skel.get(w)
        if v is None:
            v = skeleton(w)
            self._skel[w] = v
        return v

    # -- detection ---------------------------------------------------------

    def is_non_word(self, token):
        """True when the token is not a real English word in any inflected form."""
        t = token.lower()
        if t in _NEVER_CORRECT or len(t) < 3 or not t.isalpha():
            return False
        if t in self.known:
            return False
        # Try inflection candidates -- "studies" may not be listed but "study" is.
        from .lemmas import lemma_candidates
        for c in lemma_candidates(t):
            if c in self.known:
                return False
        return True

    # -- correction --------------------------------------------------------

    def classify(self, token):
        """
        'known' | 'junk' | 'too short' | 'non-word'.
        Only 'non-word' is ever sent for correction.
        """
        t = token.lower()
        # Stray single letters and letter pairs. A script that reads
        # "g g rgrg r rgr gr grg rr r" is not vocabulary, but the fragments are
        # too short to reach the non-word path, so they have to be named here.
        if t.isalpha() and len(t) <= 2 and t not in _REAL_SHORT:
            return "junk"
        if not self.is_non_word(t):
            return "known"
        if self.junk.is_junk(t):
            return "junk"
        if len(t) < MIN_CORRECTABLE:
            return "too short"
        return "non-word"

    def candidates(self, word, mode=None, require=None):
        mode = mode or CAUTIOUS
        w = word.lower()
        budget = mode.budget(len(w))
        span = int(2 + 0.2 * len(w))
        wp, ws = self._pk(w), self._sk(w)
        w_lemmas = set(lemma_candidates(w))
        scored = []
        for length in range(max(1, len(w) - span), len(w) + span + 1):
            for cand in self.buckets.get((w[0], length), ()):    # first-letter filter
                if cand == w:
                    continue
                ed = edit_distance(w, cand, budget)
                if ed > budget:
                    continue
                phon = self._pk(cand) == wp
                skel = self._sk(cand) == ws
                # structural evidence is required -- a distant match with no
                # sound or skeleton agreement is a guess, not a correction
                # Structural evidence: a distant match with no agreement in
                # sound or consonant shape is a guess, not a correction. The
                # lenient mode relaxes this to "or a long shared prefix",
                # which is what reaches heavily phonetic spellings.
                if ed > 1 and not (phon or skel):
                    if mode.evidence_required and not (
                            _common_prefix(w, cand) >= max(3, len(w) // 2)):
                        continue
                closeness = 1.0 - (ed - 1) / float(max(1, budget))
                pre = _common_prefix(w, cand) / float(len(w))
                suf = _common_suffix(w, cand) / float(len(w))
                dbl = doubling_only(w, cand)
                same_lemma = bool(w_lemmas & set(lemma_candidates(cand)))
                in_gse = self.gse.knows(cand)
                # Core evidence carries the score; the rest are bonuses on top.
                # Clamped to 1.0 so "confidence" reads as a 0-1 number.
                # Ranking uses the RAW total. It is clamped only when reported,
                # so that two strong candidates stay separable -- an earlier
                # version clamped before comparing, which made every strong pair
                # tie at 1.00 and abstain ("beautifull", "carefull", "finaly").
                score = (0.45 * closeness + 0.20 * phon + 0.15 * skel
                         + 0.06 * dbl + 0.06 * same_lemma + 0.08 * pre
                         + 0.04 * suf + 0.06 * in_gse)
                scored.append({
                    "word": cand, "edit_distance": ed, "max_edits": budget,
                    "phonetic_match": phon, "skeleton_match": skel,
                    "prefix_shared": _common_prefix(w, cand),
                    "suffix_shared": _common_suffix(w, cand),
                    "doubling_only": dbl,
                    "same_lemma": same_lemma,
                    "score": round(score, 4),
                    "in_gse": in_gse,
                })
        # HARD PREFERENCE for words that are in the GSE list.
        #
        # This is not a frequency preference -- the GSE list runs from <A1 to C2
        # and carries 13,620 C1 entries, so advanced vocabulary is as reachable
        # as common vocabulary. It is a relevance filter, and on real scripts it
        # is what stops obscure dictionary entries winning:
        #
        #   frands -> fronds  becomes  frands -> friends
        #   neam   -> nam     becomes  neam   -> name
        #   rihur  -> ruhr    becomes  (abstain)
        #
        # A correction to a word outside the reference list adds nothing to the
        # profile anyway, so it is only used when there is no alternative.
        # This is a FILTER, not a preference. A correction to a word outside the
        # reference list contributes nothing to the profile, so proposing one
        # only adds risk: on the first real batch it gave "rihur"->"ruhr" and
        # "neam"->"nam". If nothing in the list is reachable, we abstain.
        scored = [c for c in scored if c["in_gse"]]

        # The reference list is British. When both spellings of the same word
        # are in reach, the British one is the right target ("travelin" ->
        # "travelling", not "traveling").
        present = {c["word"] for c in scored}
        scored = [c for c in scored
                  if not (c["word"] in US_TO_UK and US_TO_UK[c["word"]] in present)]
        scored.sort(key=lambda c: (-c["score"], c["edit_distance"], c["word"]))
        return scored

    def repair(self, word):
        """A morphological repair, but only when exactly one target is valid."""
        hits = [r for r in morphological_repairs(word)
                if r in self.known and self.gse.knows(r)]
        return hits[0] if len(hits) == 1 else None

    def _fits_slot(self, word, require):
        """Could any sense of this word fill the slot? Unknown never rules out."""
        cats = self.gse.categories(word)
        return (not cats) or bool(cats & require)

    def correct(self, word, mode=None, require=None):
        """
        Returns a decision dict. `corrected` is None when we abstain.
        Every field is written for a human to audit.

        Order matters: junk is refused outright, then morphological repair, then
        ranked correction, then -- only if all of that came up empty -- a
        run-together split. Splitting last stops "afternon" becoming
        "after non" when "afternoon" was available.
        """
        mode = mode or CAUTIOUS
        kind = self.classify(word)
        if kind == "too short" and len(word) >= mode.min_length:
            kind = "non-word"        # this mode is willing to try
        if kind == "junk":
            return dict(_blank(word), decision="junk", reason=self.junk.explain(word))
        pre_split = split_word(word.lower(), self.known, self.gse.knows)
        if word.lower() in RUN_TOGETHER:
            parts = RUN_TOGETHER[word.lower()].split()
            return dict(_blank(word), corrected=" ".join(parts), decision="split",
                        confidence=0.95, split=parts,
                        reason="run-together words: %s" % " + ".join(parts))
        if pre_split and kind == "too short":
            return dict(_blank(word), corrected=" ".join(pre_split), decision="split",
                        confidence=0.85, split=pre_split,
                        reason="run-together words: %s" % " + ".join(pre_split))
        if kind == "too short":
            return dict(_blank(word), decision="abstained",
                        reason="only %d letters -- too little to tell a "
                               "misspelling from a keystroke" % len(word))

        fix = self.repair(word)
        if fix:
            return {
                "original": word, "corrected": fix, "decision": "corrected",
                "reason": "morphological repair: the only valid inflection or "
                          "doubled-letter form of this word",
                "confidence": 0.95, "runner_up": None,
                "candidates_considered": 1, "margin": 1.0,
                "edit_distance": abs(len(fix) - len(word)) or 1,
                "max_edits": max_edits(word), "phonetic_match": True,
                "skeleton_match": True, "doubling_only": doubling_only(word, fix),
                "same_lemma": True, "prefix_shared": _common_prefix(word, fix),
                "suffix_shared": _common_suffix(word, fix), "in_gse": True,
            }
        cands = self.candidates(word, mode)
        base = {
            "original": word,
            "corrected": None,
            "decision": "abstained",
            "reason": "",
            "confidence": 0.0,
            "runner_up": None,
            "candidates_considered": len(cands),
            "margin": 0.0,
        }
        split = split_word(word.lower(), self.known, self.gse.knows)

        if not cands:
            if split:
                base.update(corrected=" ".join(split), decision="split",
                            confidence=0.80, split=split,
                            reason="run-together words: %s" % " + ".join(split))
                return base
            base["reason"] = "no candidate within the length-scaled edit budget"
            return base

        best = cands[0]
        second = cands[1] if len(cands) > 1 else None
        base["runner_up"] = second["word"] if second else None
        base["margin"] = round(best["score"] - second["score"], 4) if second else 1.0
        base["confidence"] = round(min(1.0, best["score"]), 4)
        base.update({k: best[k] for k in
                     ("edit_distance", "max_edits", "phonetic_match",
                      "skeleton_match", "doubling_only", "same_lemma",
                      "prefix_shared", "suffix_shared", "in_gse")})

        # A run-together split beats a fuzzy single-word guess unless that guess
        # is one edit away AND starts the same way. "iplay" is "i play", not
        # "inlay"; "alot" is "a lot", not "alto". But "afternon" is "afternoon",
        # which shares seven opening letters, so the single word wins there.
        if split and not (best["edit_distance"] == 1
                          and best["prefix_shared"] >= 3
                          and best["score"] >= mode.accept):
            base.update(corrected=" ".join(split), decision="split",
                        confidence=0.80, split=split,
                        reason="run-together words: %s" % " + ".join(split))
            return base

        if best["score"] < mode.accept:
            if split:
                base.update(corrected=" ".join(split), decision="split",
                            confidence=0.80, split=split,
                            reason="run-together words: %s" % " + ".join(split))
                return base
            base["reason"] = (
                "best candidate '%s' scored %.2f, below the %.2f confidence bar"
                % (best["word"], best["score"], mode.accept)
            )
            return base

        # A strictly closer candidate dominates. When the best match is one edit
        # away and the runner-up is further, the two are not really competing --
        # applying the separation margin there would abstain on obvious cases
        # ("electricty" -> "electricity", runner-up "electrocute" at 3 edits).
        dominates = second is not None and best["edit_distance"] < second["edit_distance"]

        tied = second is not None and not dominates             and (best["score"] - second["score"]) < mode.margin

        # THE SLOT SPEAKS ONLY AT A TIE.
        #
        # An earlier version filtered the whole candidate pool by slot. That was
        # wrong: where the slot is misread it removes the RIGHT answer, and on
        # the real batch it turned "somthing" -> "something" into "smoothing"
        # and lost "wisely", "happiest" and "begging" outright. Every one of
        # those was a case the corrector was already confident about.
        #
        # So grammar is consulted only when letters and sound have genuinely
        # failed to separate two readings -- never to overrule a decision that
        # was already clear. It can convert an abstention into a correction and
        # can do nothing else. "liek" tied leek/like and "pley" ranked plea
        # ABOVE play; a noun cannot be the verb after "I" or after "to", so the
        # tie was never real and the word the student attempted was being thrown
        # away for a reading that could not have been meant.
        settled = None
        if tied and require:
            kept = [c for c in cands if self._fits_slot(c["word"], require)]
            if kept:
                nb = kept[0]
                ns = kept[1] if len(kept) > 1 else None
                clear = ns is None or nb["edit_distance"] < ns["edit_distance"]                     or (nb["score"] - ns["score"]) >= mode.margin
                if clear and nb["score"] >= mode.accept:
                    settled = (nb, ns)

        if settled:
            best, second = settled
            base["runner_up"] = second["word"] if second else None
            base["margin"] = round(best["score"] - second["score"], 4) if second else 1.0
            base["confidence"] = round(min(1.0, best["score"]), 4)
            base.update({k: best[k] for k in
                         ("edit_distance", "max_edits", "phonetic_match",
                          "skeleton_match", "doubling_only", "same_lemma",
                          "prefix_shared", "suffix_shared", "in_gse")})
            base["slot_settled"] = True
        elif tied:
            if split:
                base.update(corrected=" ".join(split), decision="split",
                            confidence=0.80, split=split,
                            reason="run-together words: %s" % " + ".join(split))
                return base
            base["reason"] = (
                "ambiguous: '%s' (%.2f) and '%s' (%.2f) are too close to separate"
                % (best["word"], best["score"], second["word"], second["score"])
            )
            return base

        why = []
        if base.get("slot_settled"):
            why.append("grammar settled a tie letters could not: only a verb or "
                       "noun that fits this slot survived")
        why.append("edit distance %d of %d allowed" % (best["edit_distance"], best["max_edits"]))
        if best["phonetic_match"]:
            why.append("same phonetic key")
        if best["skeleton_match"]:
            why.append("same consonant skeleton")
        if best["doubling_only"]:
            why.append("differs only in doubled letters")
        if best["same_lemma"]:
            why.append("same base form")
        if best["prefix_shared"] >= 3:
            why.append("shares first %d letters" % best["prefix_shared"])
        base["corrected"] = best["word"]
        base["decision"] = "corrected"
        base["reason"] = "; ".join(why)
        return base


def _common_prefix(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def _common_suffix(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def _blank(word):
    """An empty decision record, so every path returns the same shape."""
    return {
        "original": word, "corrected": None, "decision": "abstained",
        "reason": "", "confidence": 0.0, "runner_up": None, "margin": 0.0,
        "candidates_considered": 0, "edit_distance": 0, "max_edits": 0,
        "phonetic_match": False, "skeleton_match": False, "doubling_only": False,
        "same_lemma": False, "prefix_shared": 0, "suffix_shared": 0,
        "in_gse": False, "split": None,
    }


# ---------------------------------------------------------------------------
# Suspicious real words -- the candidate rule for the intent layer
#
# The corrector only ever looks at tokens that are NOT real English, so a
# misspelling that lands on another real word is invisible to it. Two shapes
# matter, and they need different triggers because they fail differently:
#
#   hared -> hard   the written word IS in the GSE list, at 77 (C1), while the
#                   rest of the script sits around A2. A single C1 item in an
#                   otherwise elementary script is the signature.
#   bast  -> best   the written word is a real word (plant fibre) but is NOT in
#                   the GSE list at all, so it contributes nothing to the
#                   profile and no "sits above the script" test can see it.
#
# Both are only suspicious when a MUCH LOWER-LEVEL word sits within one edit and
# shares the sound or the consonant shape -- the same evidence the corrector
# uses. That neighbour test is what leaves "perfume", "camping", "airline",
# "lily", "gala", "invention", "considering", "grand", "aim" and "living" alone
# despite their high GSE: nothing plausible sits one edit below them.
#
# This rule only NOMINATES tokens to ask about. It never changes a score, and
# nothing here feeds the deterministic readings. False positives are expected
# and harmless -- the model is asked, and answers "not_a_misspelling".
# ---------------------------------------------------------------------------

SUSPICIOUS_MAX_EDITS = 1     # a real-word slip is one keystroke, not a rewrite
SUSPICIOUS_MIN_DROP = 20     # GSE points the alternative must sit below
SUSPICIOUS_MIN_ABOVE = 15    # how far above the script's own level to stand out


def lower_neighbour(word, gse, bank, corrector,
                    max_edits=SUSPICIOUS_MAX_EDITS,
                    min_drop=SUSPICIOUS_MIN_DROP):
    """
    The lowest-GSE word within `max_edits` of `word` that shares its phonetic
    key or consonant skeleton. Returns None when nothing qualifies.

    When `gse` is None (the written word is not in the reference list) there is
    no level to drop from, so any reference word one edit away qualifies.
    """
    w = (word or "").lower()
    if not w.isalpha() or len(w) < 3:
        return None
    wp, ws = phonetic_key(w), skeleton(w)
    ceiling = None if gse is None else gse - min_drop
    best = None
    for length in range(max(3, len(w) - max_edits), len(w) + max_edits + 1):
        for cand in corrector.buckets.get((w[0], length), ()):
            # Two-letter neighbours are function words ("aim" -> "am"), which is
            # a grammatical slip, not a misspelt vocabulary item. Contractions
            # are excluded for the same reason.
            if cand == w or len(cand) < 3 or cand in _NEVER_CORRECT:
                continue
            if edit_distance(w, cand, max_edits) > max_edits:
                continue
            if phonetic_key(cand) != wp and skeleton(cand) != ws:
                continue
            d = bank.describe(cand)
            g = d.get("gse")
            if not d.get("matched") or g is None:
                continue
            if ceiling is not None and g > ceiling:
                continue
            if best is None or g < best["gse"]:
                best = {"word": cand, "gse": g, "band": d.get("coarse")}
    return best


def _median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def suspicious_real_words(tokens, distinct, bank, corrector,
                          min_above=SUSPICIOUS_MIN_ABOVE,
                          max_edits=SUSPICIOUS_MAX_EDITS,
                          min_drop=SUSPICIOUS_MIN_DROP):
    """
    Real words in this script worth asking the model about.

    `tokens` is the token stream (for occurrence counts), `distinct` the
    distinct content records from build_profile. Returns one record per
    suspicious token, each carrying the lower-level neighbour that made it
    suspicious so the decision can be audited.
    """
    occurrences = {}
    for t in tokens:
        occurrences[t["lower"]] = occurrences.get(t["lower"], 0) + 1

    levels = [r["gse"] for r in distinct
              if r.get("matched") and r.get("gse") is not None]

    out = []
    for r in distinct:
        token = (r.get("token") or "").lower()
        if not token or occurrences.get(token, 0) != 1:
            continue                       # a word used twice is not a slip
        if corrector.classify(token) != "known":
            continue                       # non-words go down the other path
        gse = r.get("gse") if r.get("matched") else None

        if gse is not None:
            rest = [g for g in levels if g != gse] or [g for g in levels]
            typical = _median(rest)
            if typical is None or gse - typical < min_above:
                continue                   # not standing above its own script
            why = "GSE %d sits %d above the script's typical %g" % (
                gse, gse - typical, typical)
        else:
            why = "a real word, but absent from the reference list"

        alt = lower_neighbour(token, gse, bank, corrector, max_edits, min_drop)
        if not alt:
            continue
        out.append({
            "token": token,
            "gse": gse,
            "band": r.get("coarse") if r.get("matched") else None,
            "alternative": alt["word"],
            "alternative_gse": alt["gse"],
            "alternative_band": alt["band"],
            "reason": "%s; '%s' (GSE %d) is one edit away and sounds the same"
                      % (why, alt["word"], alt["gse"]),
        })
    return out


# ---------------------------------------------------------------------------
# Syntactic slot -- what the word in this position must be able to be
#
# Closed-class triggers only. This is not a parser and does not pretend to be:
# it has an opinion about the position after a pronoun, a modal, "to", or a
# determiner, and no opinion anywhere else. Where it has no opinion nothing is
# eliminated and correction behaves exactly as it did before, so the rule can
# only ever remove readings that were already impossible.
#
# It exists because abstaining on a fake tie throws away the vocabulary the
# student was reaching for. "I liek football" cannot mean the vegetable, and
# "to pley" cannot mean a courtroom plea.
# ---------------------------------------------------------------------------

# Object pronouns are included deliberately. Using one as a subject -- "me liek
# to pley" -- is a hallmark error in this population, and the slot after it still
# demands a verb. Excluding them would abandon exactly the scripts that need
# help most.
_SUBJECT_PRONOUNS = {"i", "you", "he", "she", "it", "we", "they", "who",
                     "me", "him", "her", "us", "them"}
_MODALS = {"can", "could", "will", "would", "shall", "should", "may", "might",
           "must", "do", "does", "did", "dont", "doesnt", "didnt", "cant",
           "wont", "to", "lets", "please"}
_DETERMINERS = {"a", "an", "the", "my", "your", "his", "her", "its", "our",
                "their", "this", "that", "these", "those", "some", "any",
                "every", "each", "no", "another", "much", "many"}

VERB_SLOT = {"verb", "phrasal verb"}
NOMINAL_SLOT = {"noun", "adjective"}


def slot_after(previous):
    """What the word following `previous` must be able to be. None = no view."""
    if not previous:
        return None
    p = previous.lower()
    if p in _SUBJECT_PRONOUNS or p in _MODALS:
        return VERB_SLOT
    if p in _DETERMINERS:
        return NOMINAL_SLOT
    return None


def slot_requirements(tokens):
    """
    Requirement per surface form, keyed the way the corrector is called.

    The corrector resolves each distinct form once, so a form appearing in
    several positions collects every requirement it was seen under and a
    candidate need satisfy only one of them. That keeps the rule from
    eliminating a reading that is right somewhere in the script.
    """
    out = {}
    forms = [t["lower"] for t in tokens]
    for i, w in enumerate(forms):
        req = slot_after(forms[i - 1] if i else None)
        if req:
            out.setdefault(w, set()).update(req)
    return out


# ---------------------------------------------------------------------------
# Joinable pairs -- the error that lives BETWEEN two tokens
#
# The corrector splits run-together words ("iplay" -> "i play") but has never
# joined split ones, and nothing else could see the error either: in
# "I see a play grand" both halves are perfectly good GSE words, so no token is
# suspicious and no gate fires. The damage is real -- "grand" is GSE 56 (B1+),
# so a Pre-A1 script gets credited with a B1+ item the student never meant.
#
# Two tiers, because they carry different amounts of evidence:
#
#   A. the concatenation is itself a reference word -- "play ground" ->
#      "playground", "some times" -> "sometimes". Strong signal, cheap to test.
#   B. the concatenation needs a correction to become one -- "play grand" ->
#      "playgrand" -> "playground". Only considered when one half stands well
#      above the script's own level, which is both the symptom of the error and
#      what keeps this from scanning every adjacent pair in every script.
# ---------------------------------------------------------------------------

JOIN_MIN_PART = 3          # "a lot" is handled by RUN_TOGETHER, not here
JOIN_MAX_LEN = 16
JOIN_MIN_ABOVE = 15        # GSE points above the script's typical level


def joinable_pairs(tokens, distinct, bank, corrector, mode=None):
    """
    Adjacent token pairs that may be one word. Nominates only -- never changes
    anything, and the pair still has to survive the form test on its
    concatenation before it can affect a score.
    """
    mode = mode or LENIENT
    levels = sorted(r["gse"] for r in distinct
                    if r.get("matched") and r.get("gse") is not None)
    typical = _median(levels)

    out, seen = [], set()
    for i in range(len(tokens) - 1):
        a, b = tokens[i]["lower"], tokens[i + 1]["lower"]
        if not (a.isalpha() and b.isalpha()):
            continue
        if len(a) < JOIN_MIN_PART or len(b) < JOIN_MIN_PART:
            continue
        if a not in corrector.known or b not in corrector.known:
            continue          # a non-word half is the corrector's own business
        joined = a + b
        if len(joined) > JOIN_MAX_LEN or joined in seen:
            continue

        target, why = None, None
        if bank.knows(joined):
            target = joined
            why = "'%s %s' run together is '%s', a word in its own right" % (
                a, b, joined)
        elif typical is not None:
            # Tier B: only where one half stands out as too advanced for the
            # script it sits in -- the symptom of a mis-split compound.
            highs = [w for w in (a, b)
                     if (bank.describe(w).get("gse") or 0) - typical >= JOIN_MIN_ABOVE]
            if highs:
                cands = corrector.candidates(joined, mode)
                if cands and cands[0]["score"] >= mode.accept:
                    target = cands[0]["word"]
                    why = ("'%s' (GSE %s) sits well above this script; '%s %s' "
                           "joined is one edit-budget away from '%s'"
                           % (highs[0], bank.describe(highs[0]).get("gse"),
                              a, b, target))
        if not target:
            continue
        seen.add(joined)
        out.append({
            "first": a, "second": b, "written": "%s %s" % (a, b),
            "joined": joined, "target": target, "reason": why,
            "start": tokens[i]["start"], "end": tokens[i + 1]["end"],
        })
    return out


# ---------------------------------------------------------------------------
# Proper-noun candidates
#
# The corrector happily turns a name into a reference word -- `Bodrum` ->
# `bedroom`, `Afnan` -> `avian`, `Humaid` -> `humid`, `Zaina` -> `zany` -- and
# because the result IS a GSE word it is then counted as vocabulary the student
# demonstrated. The contamination is not random: it scales with how many names a
# student happened to mention.
#
# Capitalisation is the signal, but only in a script that uses case
# meaningfully. Many of these scripts are written entirely in capitals, where
# `SLEYP` -> `SLEEP` is a perfectly good correction and case says nothing at
# all. So the test is Title-case, mid-sentence, in a script that is not
# predominantly upper-case.
# ---------------------------------------------------------------------------

_SENTENCE_END = ".!?\n"


def mostly_upper(tokens, threshold=0.6):
    """True when the script is written in capitals and case carries no signal."""
    words = [t["raw"] for t in tokens if t["raw"].isalpha() and len(t["raw"]) > 1]
    if len(words) < 4:
        return False
    caps = sum(1 for w in words if w.isupper())
    return caps / float(len(words)) >= threshold


def proper_noun_candidates(text, tokens):
    """
    Surface forms that look like names rather than misspellings.

    Returns {lower_form: reason}. Nominates only -- the interpretation decides,
    and until it does the corrector's answer is withheld rather than applied.
    """
    if mostly_upper(tokens):
        return {}
    out = {}
    for i, t in enumerate(tokens):
        raw = t["raw"]
        if not raw[:1].isupper() or raw.isupper() or not raw.isalpha():
            continue
        # Sentence-initial capitals are just orthography, not a name.
        before = text[:t["start"]].rstrip()
        if not before or before[-1] in _SENTENCE_END:
            continue
        out.setdefault(t["lower"], "capitalised mid-sentence in a script that "
                                   "otherwise uses lower case -- likely a name")
    return out
