"""
Fixtures for Grammar Accuracy v1's Task 9 cascading-error merge logic
(docs/29). Hand-constructed and hand-judged, not diffed against an external
reference -- see tests/test_accuracy_subject_verb.py's module docstring for
why.

Two layers of testing, deliberately kept separate:

1. Direct tests of merge_accuracy_errors() against hand-built error dicts.
   This is the more important layer for this file's purpose: it exercises
   the merge MECHANISM itself (matching, specificity ordering, the
   _unkeyed fallback) in isolation from whatever the six real checks
   happen to produce, so a change in any one check's detection logic can
   never silently mask a merge-logic bug or vice versa.

2. End-to-end tests of check_all() against real sentences, confirming the
   one CONFIRMED genuine overlap in the current check set (subject-verb-
   agreement + tense, both firing on the same bare-present-tense verb after
   a past-time marker and a 3rd-person-singular-shaped subject) merges
   correctly in practice, and that non-overlapping errors from a realistic
   sentence are NOT merged just because they came from the same check_all()
   call.

Scenario B (whole-narrative pattern propagation, docs/24) is explicitly out
of scope for Task 9 and not tested here -- see the comment block at the top
of merge_accuracy_errors() in accuracy.py.

Dependency-free: run directly with `python3 tests/test_accuracy_merge.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import check_all, merge_accuracy_errors  # noqa: E402
from _grammar.pos import make_pos_lookup                         # noqa: E402
from _engine.gse import GseBank                                   # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)


# ---------------------------------------------------------------------------
# Layer 1: direct tests of merge_accuracy_errors() against hand-built input.
# (description, errors_by_family, check_fn) -- check_fn(result) -> bool
# ---------------------------------------------------------------------------

def _one_entry_with_also_flagged_by(result, family_count):
    return len(result) == 1 and len(result[0]["also_flagged_by"]) == family_count - 1


DIRECT_CASES = [
    ("two families, same sentence_index+token_index -> must merge into one"
     " entry; tense (specificity 1, most general) must yield to"
     " subject-verb-agreement (specificity 0) as the primary",
     {
         "subject-verb-agreement": [{"sentence_index": 0, "token_index": 2, "written": "go"}],
         "tense": [{"sentence_index": 0, "token_index": 2, "written": "go"}],
     },
     lambda r: (len(r) == 1
                and r[0]["also_flagged_by"] == ["tense"]
                and "_source_family" not in r[0])),

    ("same token_index but DIFFERENT sentence_index -- must NOT merge,"
     " since the same token position in two different sentences is"
     " unrelated material",
     {
         "subject-verb-agreement": [{"sentence_index": 0, "token_index": 2, "written": "go"}],
         "tense": [{"sentence_index": 1, "token_index": 2, "written": "go"}],
     },
     lambda r: len(r) == 2 and all(e["also_flagged_by"] == [] for e in r)),

    ("three families overlap on the same slot, all specificity 0 (equal"
     " rank) -- must merge into one entry with both others listed in"
     " also_flagged_by",
     {
         "number": [{"sentence_index": 0, "token_index": 5, "written": "x"}],
         "word-order": [{"sentence_index": 0, "token_index": 5, "written": "x"}],
         "pronoun": [{"sentence_index": 0, "token_index": 5, "written": "x"}],
     },
     lambda r: _one_entry_with_also_flagged_by(r, 3)),

    ("errors missing token_index entirely (defensive _unkeyed fallback) --"
     " two DIFFERENT errors that both lack token_index must NOT be"
     " spuriously merged with each other just because they share the"
     " fallback bucket shape",
     {
         "number": [{"sentence_index": 0, "written": "a"}],
         "pronoun": [{"sentence_index": 0, "written": "b"}],
     },
     lambda r: len(r) == 2 and all(e["also_flagged_by"] == [] for e in r)),

    ("non-overlapping token_index values in the same sentence -- must stay"
     " fully separate, not merged just for being in the same sentence",
     {
         "number": [{"sentence_index": 0, "token_index": 3, "written": "dog"}],
         "pronoun": [{"sentence_index": 0, "token_index": 7, "written": "him"}],
     },
     lambda r: len(r) == 2 and all(e["also_flagged_by"] == [] for e in r)),

    ("empty input across all families -- must not crash, must return []",
     {"number": [], "tense": []},
     lambda r: r == []),

    ("no families at all -- must not crash, must return []",
     {},
     lambda r: r == []),

    ("single family, single error, no overlap possible -- also_flagged_by"
     " must still be present and empty (not omitted)",
     {"number": [{"sentence_index": 0, "token_index": 1, "written": "dog"}]},
     lambda r: len(r) == 1 and r[0]["also_flagged_by"] == []),

    ("two errors from the SAME family sharing a token_index (shouldn't"
     " happen in practice, since one check doesn't double-flag its own"
     " token, but the merge logic must not crash or misbehave if it did) --"
     " merges into one entry, the family flags itself in also_flagged_by",
     {"number": [
         {"sentence_index": 0, "token_index": 4, "written": "dog", "variant": "a"},
         {"sentence_index": 0, "token_index": 4, "written": "dog", "variant": "b"},
     ]},
     lambda r: _one_entry_with_also_flagged_by(r, 2)),
]


# ---------------------------------------------------------------------------
# Layer 2: end-to-end tests of check_all() against real sentences.
# (description, text, check_fn)
# ---------------------------------------------------------------------------

END_TO_END_CASES = [
    ("CONFIRMED genuine overlap: a bare-present verb after 'Yesterday' with"
     " a 3rd-singular subject fires both subject-verb-agreement and tense"
     " on the same token -- must merge into one entry, primary family"
     " subject-verb-agreement (specificity 0), tense listed in"
     " also_flagged_by",
     "Yesterday he go to school.",
     lambda r: (len(r) == 1
                and r[0]["family"] == "subject-verb-agreement"
                and r[0]["also_flagged_by"] == ["tense"])),

    ("same underlying agreement error with NO time marker -- only"
     " subject-verb-agreement fires (tense has nothing to contradict),"
     " must be a single entry with an empty also_flagged_by",
     "He go to school.",
     lambda r: (len(r) == 1
                and r[0]["family"] == "subject-verb-agreement"
                and r[0]["also_flagged_by"] == [])),

    ("a sentence with a correct past-tense verb but a number error on the"
     " object -- confirms an unrelated, non-overlapping error from a"
     " different family is left alone (not merged into anything, not"
     " suppressed) when it shares a check_all() call with no genuine"
     " overlap partner",
     "Yesterday I saw three dog.",
     lambda r: (len(r) == 1
                and r[0]["family"] == "number"
                and r[0]["also_flagged_by"] == [])),

    ("fully correct sentence -- no checks fire, merge step receives all"
     " empty lists and returns []",
     "Yesterday he went to school.",
     lambda r: r == []),

    ("a different real overlap shape: 'yesterday' + bare verb + a proper-"
     "noun subject also 3rd-singular-shaped -- confirms the overlap isn't"
     " a one-off fluke of a single sentence",
     "Yesterday Tom go to school.",
     lambda r: (len(r) == 1
                and r[0]["family"] == "subject-verb-agreement"
                and r[0]["also_flagged_by"] == ["tense"])),
]


def run():
    failures = []

    print("=== Layer 1: merge_accuracy_errors() direct tests ===")
    for desc, errors_by_family, check_fn in DIRECT_CASES:
        result = merge_accuracy_errors(errors_by_family)
        ok = check_fn(result)
        status = "PASS" if ok else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    -> %s" % (result,))
        if not ok:
            failures.append(("direct", desc, result))

    print()
    print("=== Layer 2: check_all() end-to-end tests ===")
    for desc, text, check_fn in END_TO_END_CASES:
        result = check_all(text, {}, _pos_of)
        ok = check_fn(result)
        status = "PASS" if ok else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    %r -> %s" % (text, result))
        if not ok:
            failures.append(("end-to-end", desc, result))

    total = len(DIRECT_CASES) + len(END_TO_END_CASES)
    print()
    print("%d/%d passed" % (total - len(failures), total))
    if failures:
        print("FAILURES:")
        for layer, desc, result in failures:
            print("  - [%s] %s: got %s" % (layer, desc, result))
        sys.exit(1)


if __name__ == "__main__":
    run()
