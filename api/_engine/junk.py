"""
Telling language from noise.

Real exam scripts contain a lot that is not an attempt at English: keyboard
mashing ("FDTENYC TEGTF DVFRTG"), held-down keys ("uuuuuuuuuuuuuuu"), keyboard
rows ("qwertyuiop"), the same phrase pasted forty times, and occasionally the
test platform's own interface text.

This has to be separated out BEFORE any spelling correction, because a
spellchecker will happily turn noise into vocabulary. On the first run of a real
batch, uncorrected junk produced these:

    ggh   -> gogh      rihur -> ruhr      chfg -> chug      hji -> haji

Every one of those is a rare or proper noun sitting at C1, and two scripts the
ministry had marked "NVS" came out with a highest band of C1 as a result.

Nothing here is applied to a word that is already a real English word. These
tests only ever run on tokens that failed the known-word lookup, so ordinary
vocabulary ("rhythm", "strengths") can never be caught by them.
"""

import re
from collections import Counter

_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890")

# Text that belongs to the test platform, not to the student.
BOILERPLATE = (
    "it may take a moment or two to load your test",
    "please be patient",
    "click next to continue",
    "your answer has been saved",
)

_VOWELS = "aeiouy"


def _has_keyboard_run(w, n=4):
    for row in _KEYBOARD_ROWS:
        rev = row[::-1]
        for i in range(len(w) - n + 1):
            chunk = w[i:i + n]
            if chunk in row or chunk in rev:
                return True
    return False


def _longest_run(w):
    best = run = 1
    for i in range(1, len(w)):
        run = run + 1 if w[i] == w[i - 1] else 1
        best = max(best, run)
    return best


def _longest_consonant_run(w):
    best = 0
    for m in re.finditer(r"[^%s]+" % _VOWELS, w):
        best = max(best, len(m.group(0)))
    return best


# Shortest non-word we will try to correct. Below this, an edit-1 neighbour is
# almost always an accident: on the first real batch, three-letter noise gave
# "ggh"->"gogh", "hji"->"haji", "rji"->"rsi", "uho"->"uh". There is not enough
# signal in three letters to tell a misspelling from a keystroke.
MIN_CORRECTABLE = 4


class JunkDetector:
    """
    Character-bigram plausibility plus a handful of shape rules.

    The bigram table is built from the same English word list used for
    detection, so "is this string shaped like an English word" is answered from
    data rather than from a hand-written rule. Measured separation on the first
    real batch:

        real attempts   frands 1.00 · becaus 1.00 · jewllry 0.88 · wthoa 0.83
        noise           yhgfv 0.17 · uuv 0.25 · rji 0.50 · dvfrtg 0.57 · yuiy 0.60
    """

    def __init__(self, words, min_count=200):
        self.bigrams = Counter()
        for w in words:
            s = "^" + w + "$"
            for i in range(len(s) - 1):
                self.bigrams[s[i:i + 2]] += 1
        self.min_count = min_count

    def plausibility(self, w):
        """Share of this string's letter pairs that occur in ordinary English."""
        s = "^" + w.lower() + "$"
        grams = [s[i:i + 2] for i in range(len(s) - 1)]
        if not grams:
            return 0.0
        return sum(1 for g in grams if self.bigrams[g] >= self.min_count) / float(len(grams))

    def reasons(self, token, has_candidates=True):
        """Strong and weak signals that this token is noise, not a misspelling."""
        w = token.lower()
        strong, weak = [], []

        if len(w) >= 4 and not any(c in _VOWELS for c in w):
            strong.append("no vowel")
        run = _longest_run(w)
        if run >= 3:
            strong.append("same letter %dx in a row" % run)
        if len(w) >= 4 and _has_keyboard_run(w):
            strong.append("keyboard row")
        plaus = self.plausibility(w)
        if plaus < 0.80:
            strong.append("letter pairs are not English (%.0f%%)" % (plaus * 100))
        elif plaus < 0.90:
            weak.append("unusual letter pairs (%.0f%%)" % (plaus * 100))

        if len(w) >= 5:
            vratio = sum(1 for c in w if c in _VOWELS) / float(len(w))
            if vratio < 0.25:
                weak.append("almost no vowels")
        crun = _longest_consonant_run(w)
        if crun >= 5:
            weak.append("%d consonants in a row" % crun)
        if len(w) >= 4 and len(set(w)) <= max(2, len(w) // 3):
            weak.append("only %d different letters" % len(set(w)))
        if not has_candidates and len(w) >= 5:
            weak.append("no real word within reach")

        return strong, weak

    def is_junk(self, token, has_candidates=True):
        """One strong signal, or two weak ones."""
        strong, weak = self.reasons(token, has_candidates)
        return len(strong) >= 1 or len(weak) >= 2

    def explain(self, token, has_candidates=True):
        strong, weak = self.reasons(token, has_candidates)
        return "; ".join(strong + weak)


# ---------------------------------------------------------------------------
# Script-level verdicts
# ---------------------------------------------------------------------------

JUNK_SHARE_LIMIT = 0.35      # above this, the script is mostly noise
MIN_CONTENT_WORDS = 3        # below this there is nothing to profile
REPEAT_SHARE_LIMIT = 0.50    # one repeated phrase covering this much of the text


def repeated_phrase(tokens, n=5):
    """
    The most repeated n-word phrase and how much of the script it covers.
    Catches both "MY NEAM HAMAD AWAD ALDHAHERI" forty times over and the
    platform's own loading message pasted into the answer box.
    """
    if len(tokens) < n * 2:
        return None, 0.0
    grams = Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))
    phrase, count = grams.most_common(1)[0]
    if count < 2:
        return None, 0.0
    return " ".join(phrase), min(1.0, (count * n) / float(len(tokens)))


def script_verdict(records, junk_count, text):
    """
    Whether this script can carry a vocabulary profile at all.
    Returns (valid, headline, notes). `valid` False means the report shows no
    band -- a script made of noise must not produce a CEFR level.
    """
    notes = []
    total = len(records)
    if total == 0:
        return False, "empty", ["no words at all"]

    lowered = text.lower()
    for phrase in BOILERPLATE:
        if phrase in lowered:
            notes.append("contains test-platform text, not the student's writing")
            break

    tokens = [r["token"] for r in records]
    phrase, share = repeated_phrase(tokens)
    if share >= REPEAT_SHARE_LIMIT:
        notes.append('one phrase repeated over %d%% of the script: "%s..."'
                     % (round(share * 100), phrase[:40]))

    junk_share = junk_count / float(total)
    if junk_share >= JUNK_SHARE_LIMIT:
        notes.append("%d%% of words are not language" % round(junk_share * 100))

    content = [r for r in records if not r["is_function_word"] and not r.get("junk")]
    distinct = len({r["matched_form"] or r["token"] for r in content})
    if distinct < MIN_CONTENT_WORDS:
        notes.append("only %d distinct content word(s) -- too little to profile" % distinct)

    # The reason matters as much as the verdict. "Too short to profile" is a
    # finding about the answer; "not language" is a finding about the input.
    # Collapsing them would hide exactly the distinction this tool exists to
    # make -- a very short real answer is not keyboard mashing, even though
    # neither can carry a vocabulary profile.
    if any("platform" in n for n in notes):
        return False, "platform text", notes
    if junk_share >= JUNK_SHARE_LIMIT:
        return False, "not language", notes
    if share >= REPEAT_SHARE_LIMIT:
        return False, "repeated text", notes
    if distinct < MIN_CONTENT_WORDS:
        # SHORT AND REAL IS NOT UNPROFILABLE.
        #
        # `I dont no` is an honest short attempt. The marker banded it Pre-A1,
        # and the engine was calling it unprofilable -- disagreeing with a
        # decision already taken here: short scripts should produce Pre-A1,
        # because we have no evidence to award higher and the vocabulary tagging
        # is evidence collection. Returning nothing threw away six students'
        # results and deleted the bottom of the scale from every correlation we
        # then reasoned from.
        #
        # A band on two words is a defensible floor statement. A 0-100 on two
        # words is manufactured precision, so the numeric scores stay absent --
        # `score.py` suppresses them on this headline, the way the 8-word
        # spelling gate already does.
        #
        # Nothing here loosens the non-language exclusions above: platform text,
        # junk and repeated text have already returned by this point.
        if distinct >= 1:
            return True, "minimum evidence", notes
        return False, "too short to profile", notes
    return True, "usable", notes
