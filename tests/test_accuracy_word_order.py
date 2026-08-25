"""
Fixtures for Grammar Accuracy v1's Word order check (Task 3, family 2,
docs/33) -- frequency-adverb placement. Hand-constructed and hand-judged,
not diffed against an external reference -- see
tests/test_accuracy_subject_verb.py's module docstring for why. Every
fixture states why the expected answer is what it is; includes both
positive (must flag) and negative (must NOT flag) cases.

Deliberately includes fixtures for the cases this check does NOT attempt
(sentence-initial "sometimes"/"usually", inverted "never", non-inverted
"never") -- confirming the stated limitations hold, not just the happy
path, same discipline as Number's own fixture file.

Dependency-free: run directly with
`python3 tests/test_accuracy_word_order.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_word_order_frequency_adverbs  # noqa: E402
from _grammar.pos import make_pos_lookup                          # noqa: E402
from _engine.gse import GseBank                                    # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("sentence-initial 'always' before a pronoun subject -- the one"
     " unambiguous fronting case this check flags",
     "Always I go to school.", {}, True),
    ("adverb placed after the main verb instead of before it",
     "I go always to school.", {}, True),
    ("adverb after a verb whose noun sense outweighs its verb sense in the"
     " GSE data (the same word Task 1's 'my sister works' fixture guards)",
     "She works always at home.", {}, True),
    ("correct position, must not flag",
     "I always go to school.", {}, False),
    ("'sometimes' is completely normal sentence-initial in English -- must"
     " not flag (this is the nuance that scoped Pattern A to 'always' only)",
     "Sometimes I go to the park.", {}, False),
    ("'usually' is likewise fine sentence-initial -- must not flag",
     "Usually she wakes up early.", {}, False),
    ("'never' correctly fronted WITH subject-aux inversion -- must not flag",
     "Never have I seen such a thing.", {}, False),
    ("'never' fronted WITHOUT inversion -- genuinely wrong, but inversion"
     " detection is deliberately deferred (module docstring) -- must not"
     " flag, an honest miss rather than a guess",
     "Never I have seen such a thing.", {}, False),
    ("correct position after an auxiliary, must not flag",
     "She has always liked cats.", {}, False),
    ("correct position after 'be', must not flag",
     "I am always happy.", {}, False),
    ("correct position, determiner+singular-noun subject",
     "The dog always barks.", {}, False),
    ("adverb misplaced after the verb, determiner+singular-noun subject",
     "The dog barks always at home.", {}, True),
    ("questions are out of this check's scope entirely -- must not flag",
     "Is she always late?", {}, False),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_word_order_frequency_adverbs(text, w2i, _pos_of)
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
