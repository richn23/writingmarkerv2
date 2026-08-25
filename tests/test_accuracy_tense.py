"""
Fixtures for Grammar Accuracy v1's narrow Tense check (Task 3, family 4,
docs/33) -- past-time-marker contradiction. Hand-constructed and
hand-judged, not diffed against an external reference -- see
tests/test_accuracy_subject_verb.py's module docstring for why. Every
fixture states why the expected answer is what it is; includes both
positive (must flag) and negative (must NOT flag) cases.

Includes a regression pair (object noun phrase must not suppress a real
catch) that a first version of the checker got wrong -- caught by testing,
fixed, and locked in here so it can't silently regress.

Dependency-free: run directly with `python3 tests/test_accuracy_tense.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_tense_time_marker  # noqa: E402
from _grammar.pos import make_pos_lookup                # noqa: E402
from _engine.gse import GseBank                          # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("present-tense verb contradicts an explicit 'yesterday' marker",
     "Yesterday I go to the shop.", {}, True),
    ("correct past, must not flag",
     "Yesterday I went to the shop.", {}, False),
    ("present-tense verb contradicts an 'ago' marker",
     "Two days ago I go to the shop.", {}, True),
    ("correct past, must not flag",
     "Two days ago I went to the shop.", {}, False),
    ("bare verb contradicts a 'last week' marker",
     "Last week she visit her grandmother.", {}, True),
    ("correct past, must not flag",
     "Last week she visited her grandmother.", {}, False),
    ("no time marker at all, must not flag",
     "I go to the shop every day.", {}, False),
    ("'was' is past via AUX_PAST, not is_past_form directly -- must not"
     " flag (the same 'helper calibrated for a different job' lesson"
     " Task 1's is_third_s/is_bare_verb taught)",
     "Last night she was tired.", {}, False),
    ("genuine compound subject -- ambiguous which half governs the verb"
     " without real parsing, deliberately skipped -- must not flag",
     "Yesterday, my brother and his friend went to the shop.", {}, False),
    ("embedded clause's own verb is not independently checked -- only the"
     " first clause's subject+verb is ever examined -- must not flag",
     "I don't know what happened yesterday.", {}, False),
    ("be-verb copula tense contradiction ('is' should be 'was') is"
     " deliberately not covered -- non-past aux/modal excluded as too"
     " ambiguous for this narrow check -- must not flag",
     "Yesterday she is happy.", {}, False),
    ("questions are out of this check's scope entirely, must not flag",
     "Did you go there yesterday?", {}, False),
    ("REGRESSION GUARD: an object noun phrase ('London') must not be"
     " counted as a second, competing subject candidate -- a first version"
     " of this check missed this case because it did exactly that",
     "Tom visit London last year.", {}, True),
    ("correct past, must not flag",
     "Tom visited London last year.", {}, False),
    ("REGRESSION GUARD: correct sentence with an object noun phrase must"
     " not false-positive either",
     "I visited the museum last year.", {}, False),
    ("REGRESSION GUARD: the object-noun-phrase fix must still catch a"
     " genuine error when the object is a common noun, not just a proper one",
     "I visit the museum last year.", {}, True),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_tense_time_marker(text, w2i, _pos_of)
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
