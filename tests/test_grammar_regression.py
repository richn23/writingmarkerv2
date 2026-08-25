"""
Regression fixtures for the Fix 6 grammar-leveling gate fix (docs/23, 24 Aug
2026) and the Fix 7 'd-contraction disambiguation fix (Task 3c, 25 Aug 2026)
-- the specific triggering sentences the original 92-example fixture set
(docs/21) did not include, which is why it passed 92/92 while both bugs
shipped undetected.

Dependency-free, matching api/score.py's own convention: run directly with
`python3 tests/test_grammar_regression.py`, no pytest/requirements.txt.
Exits non-zero on any failure so it can gate a deploy the same way
tests/test_regression.py does for the scoring engine (see memory notes --
that file lives in a different project; this is this project's equivalent
for the grammar module specifically).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.detect import detect_grammar_structures         # noqa: E402
from _grammar.sentences import split_sentences                # noqa: E402
from _grammar.pos import make_pos_lookup                      # noqa: E402
from _engine.gse import GseBank                                # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)


def detect(text):
    sents = split_sentences(text)
    return detect_grammar_structures(sents, pos_of=_pos_of)["detected"]


def find(detected, explorer_id, family_id=None):
    for d in detected:
        if d["explorer_id"] == explorer_id and (family_id is None or d["family_id"] == family_id):
            return d
    return None


# Each case: (description, text, explorer_id, family_id, expected_level).
# expected_level of None means "this explorer_id/family_id must NOT appear at
# all" -- used for the can/shall cases, where EGP genuinely has no dedicated
# past-modal row (Task 1's brief flagged this as a possible gap; confirmed:
# it is a real data gap, not a resolver bug -- see docs/23's report).
CASES = [
    ("wish + regret, EGP's own example sentence",
     "I wish that you were here, cycling with us.",
     "wish", "past_simple", "b1"),

    ("if only + affirmative, EGP's own example sentence",
     "If only I had listened to my father!",
     "wish", "past_perfect_simple", "b2"),

    ("if only + negative, EGP's own example sentence",
     "If only she had not changed her mind.",
     "wish", "past_perfect_simple", "c2"),

    ("second/third conditional must not resolve to a2 zero-conditional",
     "If I had studied, I would have passed the exam.",
     "conditionals-unreal", "conditional", "b1"),

    ("wish-token family selection follows the complement's own tense",
     "She wished she had brought her notes.",
     "wish", "past_perfect_simple", "b2"),

    ("modals-past: might have -- LENS's flagged, now-confirmed case",
     "She might have missed the train.",
     "modals-past", "might", "b1"),

    ("modals-past: may have -- LENS's flagged, now-confirmed case",
     "She may have thought about it.",
     "modals-past", "may", "b2"),

    # Fix 7 (Task 3c, 25 Aug 2026): 'd + past participle means "had", not
    # "would" -- confirmed identical bug in live LENS via a direct tsx run.
    ("'d + past participle disambiguates to had, not would",
     "They'd already mentioned it before the meeting started.",
     "past-perfect", "past_perfect_simple", "b1"),
    ("'d + past participle disambiguates to had, not would (2)",
     "She'd finished her homework by the time I arrived.",
     "past-perfect", "past_perfect_simple", "b1"),
    ("'d been + -ing disambiguates to had (past perfect continuous)",
     "They'd been waiting for hours when the bus finally came.",
     "past-perfect-continuous", "past_perfect_continuous", "b1"),
    ("'d + bare verb still correctly means would (regression guard)",
     "They'd love to come to the party.",
     "modals-ability", "would", "a2"),
    ("'d rather is a fixed idiom, still correctly would (regression guard)",
     "I'd rather stay home tonight.",
     "modals-ability", "would", "a2"),
]

# can/shall: LENS flagged these as possibly affected too. Confirmed: EGP has
# no dedicated past-modal row for either, so the resolver correctly falls
# back to the best generic (non-past) row -- a1/a2 respectively. This is a
# reference-data gap, not a bug this fix can close.
DATA_GAP_CASES = [
    ("modals-past: can have -- no dedicated EGP row exists, generic fallback",
     "You can have finished by now.", "modals-past", "can", "a1"),
    ("modals-past: shall have -- no dedicated EGP row exists, generic fallback",
     "They shall have arrived by then.", "modals-past", "shall", "a2"),
]


def run():
    failures = []
    for desc, text, explorer_id, family_id, expected in CASES + DATA_GAP_CASES:
        detected = detect(text)
        hit = find(detected, explorer_id, family_id)
        got = hit["level"] if hit else None
        status = "PASS" if got == expected else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    %r -> expected %s, got %s" % (text, expected, got))
        if got != expected:
            failures.append((desc, text, expected, got))

    print()
    print("%d/%d passed" % (len(CASES) + len(DATA_GAP_CASES) - len(failures),
                             len(CASES) + len(DATA_GAP_CASES)))
    if failures:
        print("FAILURES:")
        for desc, text, expected, got in failures:
            print("  - %s: %r expected %s, got %s" % (desc, text, expected, got))
        sys.exit(1)


if __name__ == "__main__":
    run()
