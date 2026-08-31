"""
Fixtures for Grammar Accuracy v1's subject-verb agreement check (Task 1,
docs/29). Hand-constructed and hand-judged, not diffed against an external
reference -- Accuracy has no LENS-equivalent to verify against (docs/29's
own stated limitation). Every fixture states, in its description, WHY the
expected answer is what it is, so it can be checked by a human reader, not
just trusted because the code that wrote it says so.

Includes both positive (must flag) and negative (must NOT flag) cases --
false positives matter as much as false negatives here, arguably more,
given this project's stated bias toward false negatives over false
positives throughout.

Dependency-free, matching api/score.py's and
tests/test_grammar_regression.py's own convention: run directly with
`python3 tests/test_accuracy_subject_verb.py`, no pytest.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_subject_verb_agreement    # noqa: E402
from _grammar.pos import make_pos_lookup                      # noqa: E402
from _engine.gse import GseBank                                # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("regular -s missing, pronoun subject",
     "He go to school every day.", {}, True),
    ("regular -s missing, pronoun subject (2)",
     "She like coffee.", {}, True),
    ("regular -s missing, determiner+noun subject",
     "The dog run fast.", {}, True),
    ("correctly third-s marked, must not flag",
     "He goes to school every day.", {}, False),
    ("correct bare form for a plural-class pronoun, must not flag",
     "They go to school every day.", {}, False),
    ("past tense needs no agreement in English, must not flag",
     "He went to school yesterday.", {}, False),
    ("present continuous -- missing-aux case, deliberately out of scope",
     "He is going to school.", {}, False),
    ("no verb at the candidate position -- missing-verb case, out of scope",
     "She happy today.", {}, False),
    ("correct bare form for I, must not flag",
     "I go to school.", {}, False),
    ("irregular 'have': he have -> should be has",
     "He have a car.", {}, True),
    ("irregular 'have': correct, must not flag",
     "He has a car.", {}, False),
    ("irregular 'be': am correctly paired with I, must not flag",
     "I am happy.", {}, False),
    ("irregular 'be': he am -> should be is",
     "He am happy.", {}, True),
    ("irregular 'be': they is -> should be are",
     "They is here.", {}, True),
    ("irregular 'do': he do -> should be does",
     "He do not like it.", {}, True),
    ("irregular 'do': correct, must not flag",
     "He does not like it.", {}, False),
    ("plural subject needs the bare form -- must not flag",
     "The dogs run fast.", {}, False),
    ("spelling-corrected verb still missing -s -- flags on the CORRECTED form,"
     " not the misspelling (that's Spelling's, per docs/24 Overlap Rule 1)",
     "He recieve the letter.", {"recieve": "receive"}, True),
    ("morphological over-regularization ('goed') is unrecognised, correctly"
     " out of this check's scope -- Task 2's territory, not Task 1's",
     "He goed to the shop.", {}, False),
    ("noun-dominant verb sense ('works' also means noun-works) must not"
     " false-positive -- the bug this file exists to guard against",
     "My sister works in London.", {}, False),
    ("proper-noun subject, wrong-form",
     "Tom live in Paris.", {}, True),

    # REGRESSION GUARDS for docs/39 Bug A: every modal and invariant past
    # auxiliary was flagged after a third-singular subject, because the
    # regular "-s" fallback read the missing marker as a missing agreement.
    # "He can swim." -- ordinary English -- was a confident false accusation.
    # These fixtures exist so that specific failure mode cannot return.
    ("REGRESSION GUARD (Bug A): modals take no agreement marking -- must"
     " not flag",
     "He can swim.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'will'", "He will leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'would'", "He would leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'could'", "She could swim.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'must'", "He must leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'should'", "He should leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'may'", "He may leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'might'", "He might leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal 'shall'", "He shall leave.", {}, False),
    ("REGRESSION GUARD (Bug A): modal after a proper-noun subject",
     "Tom will leave.", {}, False),
    ("REGRESSION GUARD (Bug A): 'had' is a past form of have and does NOT"
     " inflect for person -- it was being held to 'has'",
     "He had left.", {}, False),
    ("REGRESSION GUARD (Bug A): 'did' is a past form of do and does NOT"
     " inflect for person -- it was being held to 'does'",
     "He did leave.", {}, False),

    # The other half of Bug A's fix: was/were were deliberately NOT added to
    # the invariant set, because unlike modals they DO agree. These two
    # fixtures prove the fix didn't silently switch off a real check.
    ("was/were DO agree, unlike modals -- 'he were' is a real error and"
     " must still flag after Bug A's fix",
     "He were leaving.", {}, True),
    ("correct past agreement, must not flag", "He was leaving.", {}, False),
    ("correct plural past agreement, must not flag",
     "They were leaving.", {}, False),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_subject_verb_agreement(text, w2i, _pos_of)
        got_flag = len(errors) > 0
        status = "PASS" if got_flag == expect_flag else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    %r -> expected flag=%s, got %s" % (text, expect_flag, errors or "[]"))
        if got_flag != expect_flag:
            failures.append((desc, text, expect_flag, errors))

    print()
    print("%d/%d passed" % (len(CASES) - len(failures), len(CASES)))
    if failures:
        print("FAILURES:")
        for desc, text, expect_flag, errors in failures:
            print("  - %s: %r expected flag=%s, got %s" % (desc, text, expect_flag, errors))
        sys.exit(1)


if __name__ == "__main__":
    run()
