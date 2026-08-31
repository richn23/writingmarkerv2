"""
Fixtures for Grammar Accuracy v1's Pronoun case check (Task 3, family 3,
docs/33). Hand-constructed and hand-judged, not diffed against an external
reference -- see tests/test_accuracy_subject_verb.py's module docstring for
why. Every fixture states why the expected answer is what it is; includes
both positive (must flag) and negative (must NOT flag) cases.

Deliberately includes fixtures for the causative-verb exception ("let him
go") and the embedded-clause case direct-object-after-verb deliberately
doesn't attempt ("I know he is here") -- confirming the stated limitations
hold, not just the happy path, same discipline as every prior fixture file
in this series.

Dependency-free: run directly with
`python3 tests/test_accuracy_pronoun_case.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_pronoun_case  # noqa: E402
from _grammar.pos import make_pos_lookup          # noqa: E402
from _engine.gse import GseBank                    # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)

# (description, text, written_to_intended, expect_flag)
CASES = [
    ("object-form pronoun in simple subject position",
     "Him goes to school.", {}, True),
    ("correct subject-form, must not flag",
     "He goes to school.", {}, False),
    ("compound subject with object-form pronouns -- both wrong pronouns"
     " flagged, one via each pattern entry point",
     "Me and him went to the store.", {}, True),
    ("correct compound subject, must not flag",
     "He and I went to the store.", {}, False),
    ("subject-form pronoun after a preposition",
     "Give it to I.", {}, True),
    ("correct object-form after a preposition, must not flag",
     "Give it to him.", {}, False),
    ("subject-form pronoun after a different preposition",
     "This gift is for I.", {}, True),
    ("correct, must not flag",
     "This gift is for her.", {}, False),
    ("causative construction -- object pronoun correctly followed by a"
     " bare verb, must not flag (the false-positive shape this file"
     " exists to guard against, same lesson as Task 1's 'my sister works')",
     "Let him go.", {}, False),
    ("causative construction with a different verb, must not flag",
     "Make her stay.", {}, False),
    ("embedded clause with its own subject -- direct-object-after-verb is"
     " DELIBERATELY not attempted (module docstring): nothing distinguishes"
     " this from a genuine direct-object error without real parsing, so"
     " both are left unflagged rather than guessed at -- must not flag",
     "I know he is here.", {}, False),
    ("'you' carries no case distinction, must not flag",
     "This is between you and me.", {}, False),
    ("correct compound subject with two different pronouns, must not flag",
     "They and we are friends.", {}, False),
    ("questions are out of this check's scope entirely, must not flag",
     "Are you and him coming?", {}, False),
    ("subject-form pronoun after 'to' with a full sentence around it",
     "I gave the book to she.", {}, True),

    # REGRESSION GUARDS for docs/39 Bug B: "her" is the one object-form
    # pronoun that is also a possessive determiner, and most common nouns
    # carry a verb sense too, so ordinary possessive noun phrases matched
    # Pattern 1's "object pronoun + verb-capable word" test. "He took her
    # book." was flagged as a misplaced subject. These lock that shut.
    ("REGRESSION GUARD (Bug B): possessive 'her' before a noun that also"
     " has a verb sense must not flag",
     "He took her book.", {}, False),
    ("REGRESSION GUARD (Bug B): possessive 'her' + 'friend'",
     "She visited her friend.", {}, False),
    ("REGRESSION GUARD (Bug B): possessive 'her' + 'work'",
     "He praised her work.", {}, False),
    ("REGRESSION GUARD (Bug B): possessive 'her' + 'hand'",
     "He held her hand.", {}, False),
    ("REGRESSION GUARD (Bug B): possessive 'her' + 'name'",
     "I forgot her name.", {}, False),

    # The other half of Bug B's fix: the guard is scoped to a following
    # NOUN-capable word, so a genuinely misplaced subject still catches --
    # "goes"/"runs" are noun=False in the GSE data.
    ("Bug B's guard must NOT mask a genuine subject-position error: 'goes'"
     " is not noun-capable, so 'Her goes' still flags",
     "Her goes to school.", {}, True),
    ("same, with 'runs'", "Her runs every day.", {}, True),
    ("Bug B's guard is scoped to 'her' alone -- 'them' is never a"
     " possessive determiner, so this must still flag even though 'work'"
     " is noun-capable",
     "Them work hard.", {}, True),
]


def run():
    failures = []
    for desc, text, w2i, expect_flag in CASES:
        errors = check_pronoun_case(text, w2i, _pos_of)
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
