"""
What the model is asked, and what its answers have to survive.

THE QUESTION IS DELIBERATELY NARROW: "what word was this a misspelling of?",
one token at a time, with the sentence it sits in for context. Not "what did the
student intend" -- that invites rewriting the sentence, and a vocabulary score
built on a rewritten sentence is not a score of what the student wrote.

THE VALIDATION IS THE CONSTRAINT. A proposal is accepted only if it is a single
real word that is orthographically close to what was written, judged by the
engine's own edit budget, phonetic key and consonant skeleton -- imported, never
re-implemented, so the two can never drift. `enormus` -> `enormous` passes and is
correctly credited at B1+. `good` -> `excellent` cannot pass at any confidence:
it is a vocabulary upgrade, not a repair. Rejections are logged, and a rejection
count of zero means the test is not running.
"""

import re

from _engine.spelling import (edit_distance, max_edits, phonetic_key,   # noqa
                              skeleton)

ANSWERS = ("replacement", "not_a_misspelling", "proper_noun", "unrecoverable")

# Structured outputs constrain the reply to exactly this shape, so there is no
# prose to parse. Numeric bounds are not expressible here -- confidence is
# clamped on arrival instead.
SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "token": {"type": "string"},
                    "answer": {"type": "string", "enum": list(ANSWERS)},
                    "replacement": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["token", "answer", "replacement",
                             "confidence", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

SYSTEM = """\
You are producing a SPELLING-CORRECTED version of a piece of second-language \
exam writing, so that its vocabulary can be assessed afterwards.

You are given the whole sample, then a list of the words in it that could not be \
resolved mechanically. For each of those words, answer one question and only \
that question:

    what word was this a misspelling of?

Read the whole sample before answering. Context is your main evidence: the \
grammatical slot the word sits in, the words it pairs with, and the rest of the \
sample. A word that cannot fill the slot is not the answer, however similar it \
looks -- 'leek' is a vegetable and cannot be the verb after 'me', and 'plea' is \
a noun and cannot follow 'to'. If the same misspelling appears twice, resolve it \
the same way both times.

Some entries are TWO WORDS with a space, offered because the student may have \
meant one word: 'play grand' for 'playground', 'some times' for 'sometimes'. \
Answer those the same way -- give the single word if that is what was meant, or \
`not_a_misspelling` if the two words are correct as they stand ('every day' and \
'a lot' usually are).

FIX SPELLING ONLY. Do not correct grammar, do not add missing words, and do not \
improve the student's vocabulary. 'me' stays 'me'. This is a vocabulary \
assessment: a word you supply would be credited to the student, and a word you \
upgrade would inflate their level.

Answer each token with exactly one of:

  replacement        the student misspelt a word; give that word in
                     `replacement`, lowercase, as ONE word
  not_a_misspelling  the word written is the word meant, even if it is an odd
                     choice or an advanced word in a simple script
  proper_noun        a name, place, or brand -- not vocabulary
  unrecoverable      you cannot read it with confidence

`not_a_misspelling` is an ordinary, expected answer. Most tokens you are shown \
are flagged by a cheap mechanical rule, not by evidence of an error: an unusual \
word in a simple script is usually just an unusual word. Answering \
`not_a_misspelling` is never a failure, and inventing a correction for a word \
that was already right is worse than leaving it.

A replacement must be a real English word that is a plausible MISSPELLING of \
what was written -- close in letters and in sound. It must not be a better or \
more advanced word for the same idea: `enormus` -> `enormous` is a repair, \
`good` -> `excellent` is not, whatever the sentence suggests. Proposals that are \
not orthographically close are discarded automatically, so they cost accuracy \
and gain nothing.

`confidence` is your own 0-1 estimate. `reason` is one short line.
Return a verdict for every token you are given, using the token exactly as \
written."""

_SENTENCE = re.compile(r"[^.!?\n]*[.!?\n]|[^.!?\n]+")


def sentence_for(text, start, end, limit=300):
    """The sentence a token sits in, trimmed so context stays cheap."""
    for m in _SENTENCE.finditer(text):
        if m.start() <= start < m.end():
            s = m.group(0).strip()
            if len(s) <= limit:
                return s
            head = max(0, start - m.start() - limit // 2)
            return s[head:head + limit].strip()
    return text[max(0, start - 60):end + 60].strip()


def build_question(text, items):
    """
    One user turn: the whole sample first, then the words to resolve.

    The sample leads so the model reads it before it reaches the word list --
    slot, collocation and sample-internal consistency all come from there.
    """
    lines = []
    for i, it in enumerate(items, 1):
        lines.append("%d. %s\n   in: %s\n   why unresolved: %s"
                     % (i, it["token"], it["sentence"], it["why"]))
    return ("THE WHOLE SAMPLE, exactly as the student wrote it:\n\n"
            "%s\n\n"
            "----\n\n"
            "These words could not be resolved mechanically. Read them in the "
            "sample above and answer the question for each.\n\n%s"
            % (text.strip(), "\n\n".join(lines)))


# ---------------------------------------------------------------------------
# Validation -- the whole safety mechanism
# ---------------------------------------------------------------------------

def form_test(written, proposed):
    """
    Is `proposed` orthographically close enough to `written` to be a repair?

    THE EDIT BUDGET IS THE GATE. Sound and consonant shape are recorded as
    evidence but no longer veto, because a context-aware reading must not lose
    to a shape technicality -- that is what "defer to the interpretation" means.

    This was measured, not assumed. Requiring sound-or-skeleton agreement threw
    out 14 correct repairs per 100 scripts -- `intead`->`instead`,
    `shoud`->`should`, `famiy`->`family`, `wite`->`write` -- because dropping or
    inserting one consonant changes the skeleton. On the 25 cases collected from
    live batches, the budget alone accepts 18 of 18 genuine repairs and admits
    0 of 7 upgrades: `good`->`excellent`, `nice`->`wonderful`,
    `big`->`enormous` and `happy`->`delighted` all fail on distance, which is
    the only thing that was ever holding them back.

    Returns (ok, detail).
    """
    budget = max_edits(written)
    ed = edit_distance(written, proposed, budget)
    if ed > budget:
        return False, ("edit distance exceeds the budget of %d -- a repair is "
                       "close to what was written; this is a different word"
                       % budget)
    phon = phonetic_key(written) == phonetic_key(proposed)
    skel = skeleton(written) == skeleton(proposed)
    note = ("same phonetic key" if phon else
            "same consonant skeleton" if skel else
            "different sound shape, accepted on the reading of the sentence")
    return True, "edit distance %d of %d allowed; %s" % (ed, budget, note)


def validate_join(pair, verdict, corrector):
    """
    A pair of adjacent words the student may have meant as one.

    The form test runs against the CONCATENATION, which is the only comparison
    that makes a join legal: `grand` -> `playground` is nonsense on its own, but
    `playgrand` -> `playground` is two edits inside a budget of four. The
    single-token rule still applies to the PROPOSAL, so this cannot become a
    route for replacing two words with a phrase.
    """
    rec = validate(pair["joined"], verdict, corrector)
    rec.update({
        "join": True,
        "original": pair["written"],       # "play grand", as written
        "joined": pair["joined"],          # "playgrand", what was tested
        "first": pair["first"], "second": pair["second"],
        "start": pair["start"], "end": pair["end"],
    })
    if rec["accepted"] and rec["corrected"]:
        rec["effect"] = "two words read as one"
    return rec


def validate(written, verdict, corrector):
    """
    Turn one raw verdict into a decision record. Never raises.

    A record always carries `accepted`; when False, `rejected_because` says
    which check failed. Both are surfaced in the audit.
    """
    answer = verdict.get("answer")
    raw = (verdict.get("replacement") or "").strip().lower()
    try:
        conf = float(verdict.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    rec = {
        "original": written,
        "answer": answer if answer in ANSWERS else "unrecoverable",
        "proposed": raw or None,
        "corrected": None,
        "confidence": round(conf, 3),
        "model_reason": (verdict.get("reason") or "").strip()[:200],
        "accepted": False,
        "rejected_because": None,
    }

    if rec["answer"] != "replacement":
        rec["accepted"] = True          # nothing is being changed
        rec["proposed"] = None
        return rec

    if not raw:
        rec["rejected_because"] = "answered 'replacement' with no word"
        return rec
    if not raw.isalpha():
        rec["rejected_because"] = "not a single alphabetic token"
        return rec
    if raw == written:
        rec["rejected_because"] = "proposed the word that was already written"
        return rec
    if raw not in corrector.known:
        rec["rejected_because"] = "'%s' is not a known English word" % raw
        return rec

    ok, detail = form_test(written, raw)
    if not ok:
        rec["rejected_because"] = "failed the form test: %s" % detail
        return rec

    rec["accepted"] = True
    rec["corrected"] = raw
    rec["form"] = detail
    return rec


# ---------------------------------------------------------------------------
# Error categorisation -- descriptive only, never touches a score
# ---------------------------------------------------------------------------

CATEGORIES = ("correct", "minor_slip", "phonetic", "wrong_word", "boundary",
              "proper_noun", "unrecoverable")

CATEGORY_LABEL = {
    "correct": "no error",
    "minor_slip": "one edit, same sound",
    "phonetic": "spelled as it sounds",
    "wrong_word": "a different real word",
    "boundary": "run together or split",
    "proper_noun": "a name",
    "unrecoverable": "not resolvable",
}


def categorise(written, corrected, answer, was_real_word, split=False):
    """
    Which kind of error this token was. Descriptive: nothing downstream reads
    it, and CEFR treats orthographic control as a trait of its own.
    """
    if split:
        return "boundary"
    if answer == "proper_noun":
        return "proper_noun"
    if not corrected:
        return "correct" if answer == "not_a_misspelling" else "unrecoverable"
    if was_real_word:
        return "wrong_word"
    ed = edit_distance(written, corrected, 4)
    same_sound = phonetic_key(written) == phonetic_key(corrected)
    if ed <= 1 and same_sound:
        return "minor_slip"
    if same_sound or skeleton(written) == skeleton(corrected):
        return "phonetic"
    return "minor_slip" if ed <= 1 else "phonetic"
