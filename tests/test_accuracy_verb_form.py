"""
Fixtures for Grammar Accuracy v1's verb-form over-regularization check
(Task 2, docs/29) -- the canonical Grammar/Spelling seam (docs/24, doc 28's
own "goed" example). Hand-constructed and hand-judged, not diffed against
an external reference -- see tests/test_accuracy_subject_verb.py's module
docstring for why. Every fixture states why the expected answer is what it
is; includes both positive (must flag) and negative (must NOT flag) cases.

Dependency-free: run directly with `python3 tests/test_accuracy_verb_form.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_verb_form_overregularization  # noqa: E402
from _grammar.pos import make_pos_lookup                          # noqa: E402
from _engine.gse import GseBank                                    # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("over-regularized 'go' -> 'goed', the canonical example",
     "Yesterday I goed to the shop.", {}, True),
    ("over-regularized 'eat' -> 'eated'",
     "She eated her breakfast quickly.", {}, True),
    ("over-regularized 'run' -> 'runned' (doubled-consonant spelling attempt)",
     "He runned to the bus stop.", {}, True),
    ("over-regularized 'run' -> 'runed' (undoubled spelling variant)",
     "He runed to the bus stop.", {}, True),
    ("over-regularized 'buy' -> 'buyed'",
     "They buyed a new car.", {}, True),
    ("over-regularized 'come' -> 'comed' (silent-e base)",
     "We comed home late.", {}, True),
    ("correct irregular 'went', must not flag",
     "Yesterday I went to the shop.", {}, False),
    ("correct irregular 'ate', must not flag",
     "She ate her breakfast quickly.", {}, False),
    ("correct REGULAR verb 'played', must not flag -- not every -ed word is an error",
     "He played football yesterday.", {}, False),
    ("correct regular 'walked', must not flag",
     "She walked to school.", {}, False),
    ("correct regular 'used', must not flag",
     "He used the tool carefully.", {}, False),
    ("'shed' -- coincidental -ed shape (not a regularized irregular), must not flag",
     "The shed needed repairs.", {}, False),
    ("over-regularized 'steal' -> 'stealed' -- added after fixing the"
     " IRREG_PAST gap this file's own cross-verification found (docs/32)",
     "He stealed the money.", {}, True),
    ("correct irregular 'stole', must not flag",
     "He stole the money.", {}, False),
    ("over-regularized 'forget' -> 'forgetted'",
     "She forgetted her keys.", {}, True),
    ("correct irregular 'forgot', must not flag",
     "She forgot her keys.", {}, False),
    ("over-regularized 'wake' -> 'waked'",
     "He waked up early.", {}, True),
    ("correct irregular 'woke', must not flag",
     "He woke up early.", {}, False),
    ("word identity already resolved by Spelling to the correct form --"
     " nothing left for this check to flag (docs/24 Overlap Rule 1)",
     "He goed to the shop.", {"goed": "went"}, False),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_verb_form_overregularization(text, w2i, _pos_of)
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
