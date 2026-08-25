"""
Fixtures for Grammar Accuracy v1's Number check (Task 3, family 1, docs/33)
-- missing/wrong plural after an explicit quantity marker. Hand-constructed
and hand-judged, not diffed against an external reference -- see
tests/test_accuracy_subject_verb.py's module docstring for why. Every
fixture states why the expected answer is what it is; includes both
positive (must flag) and negative (must NOT flag) cases.

Dependency-free: run directly with `python3 tests/test_accuracy_number.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_number     # noqa: E402
from _grammar.pos import make_pos_lookup       # noqa: E402
from _engine.gse import GseBank                 # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("missing plural after a number, regular noun",
     "I saw three dog in the park.", {}, True),
    ("correct regular plural, must not flag",
     "I saw three dogs in the park.", {}, False),
    ("missing plural after a number, -es-requiring noun",
     "There are five box on the table.", {}, True),
    ("correct -es plural, must not flag",
     "There are five boxes on the table.", {}, False),
    ("irregular singular written where the irregular plural was needed",
     "There were several child in the room.", {}, True),
    ("correct irregular plural, must not flag",
     "There were several children in the room.", {}, False),
    ("irregular singular after a number",
     "I have two person to meet.", {}, True),
    ("correct irregular plural, must not flag",
     "I have two people to meet.", {}, False),
    ("common phrase 'many people', must not flag",
     "Many people came to the party.", {}, False),
    ("missing plural after 'many'",
     "Many student attended the class.", {}, True),
    ("correct, must not flag",
     "Many students attended the class.", {}, False),
    ("uncountable noun after 'many' -- a countability error, not this"
     " check's construct (deferred, per docs/33) -- must not flag",
     "She gave me many advice.", {}, False),
    ("uncountable noun after 'few' -- same reasoning, must not flag",
     "I need few information.", {}, False),
    ("'one' takes a singular noun, must not flag",
     "One dog is enough.", {}, False),
    ("intervening adjective between marker and noun -- deliberately out of"
     " this check's narrow scope (stated limitation, not a silent gap) --"
     " must not flag",
     "I saw three big dog.", {}, False),
    ("irregular plural via 'both'",
     "Both wolf howled at the moon.", {}, True),
    ("correct irregular plural, must not flag",
     "Both wolves howled at the moon.", {}, False),
    ("spelling-corrected noun still missing its plural marker -- flags on"
     " the CORRECTED word, not the misspelling (docs/24 Overlap Rule 1)",
     "I met three frend at the park.", {"frend": "friend"}, True),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_number(text, w2i, _pos_of)
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
