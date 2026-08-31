"""
Fixtures for Grammar Accuracy v1's Task 10 global aggregation (docs/29):
errors/100 words and grammatically error-free sentence %. Hand-constructed
and hand-judged -- see tests/test_accuracy_subject_verb.py's module
docstring for why.

Two layers, the same split that worked for Task 9's merge logic:

1. aggregate_accuracy() tested directly against hand-built merged-error
   lists. This is the primary layer: aggregation is pure arithmetic over
   (text, errors), so testing it against fixed inputs pins the arithmetic
   down independently of what the six checks currently detect. That
   independence is not theoretical -- two genuine false positives in the
   already-committed checks were found while building this task (docs/39),
   and this layer stays valid and meaningful regardless of them.

2. accuracy_report() end-to-end on real sentences, deliberately chosen to
   avoid the two known false positives above so these fixtures assert
   aggregation behaviour rather than re-asserting the checks' behaviour.

Dependency-free: run directly with
`python3 tests/test_accuracy_aggregate.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _grammar.accuracy import aggregate_accuracy, accuracy_report  # noqa: E402
from _grammar.pos import make_pos_lookup                            # noqa: E402
from _engine.gse import GseBank                                      # noqa: E402

_bank = GseBank(os.path.join(ROOT, "api", "_data", "gse_vocabulary.json"))
_pos_of = make_pos_lookup(_bank)


def _err(sentence_index, token_index=0):
    return {"sentence_index": sentence_index, "token_index": token_index,
            "family": "number", "also_flagged_by": []}


# ---------------------------------------------------------------------------
# Layer 1: aggregate_accuracy() against hand-built merged-error lists.
# (description, text, merged_errors, check_fn)
# ---------------------------------------------------------------------------

DIRECT_CASES = [
    ("no errors -- 100% grammatically error-free, rate 0.0 (not None:"
     " zero errors over real words is a genuine 0, not an absent value)",
     "He goes to school. She left early.", [],
     lambda r: (r["sentence_count"] == 2 and r["error_count"] == 0
                and r["errors_per_100_words"] == 0.0
                and r["grammatically_error_free_sentences"] == 2
                and r["grammatically_error_free_sentence_pct"] == 100.0)),

    ("one error in one of two sentences -- the OTHER sentence is still"
     " grammatically error-free, so the metric is 50%, not 0%",
     "He goes to school. She left early.", [_err(0)],
     lambda r: (r["grammatically_error_free_sentences"] == 1
                and r["grammatically_error_free_sentence_pct"] == 50.0)),

    ("TWO errors in the SAME sentence -- error_count is 2 but only ONE"
     " sentence is disqualified; the two metrics must not be conflated",
     "He goes to school. She left early.", [_err(0, 1), _err(0, 3)],
     lambda r: (r["error_count"] == 2
                and r["grammatically_error_free_sentences"] == 1
                and r["grammatically_error_free_sentence_pct"] == 50.0)),

    ("errors in every sentence -- 0% grammatically error-free",
     "He goes to school. She left early.", [_err(0), _err(1)],
     lambda r: r["grammatically_error_free_sentence_pct"] == 0.0),

    ("errors/100 words arithmetic on a known count: 8 written words, 2"
     " errors -> 25.0 per 100",
     "He goes to school. She left early quickly.", [_err(0), _err(1)],
     lambda r: r["word_count"] == 8 and r["errors_per_100_words"] == 25.0),

    ("CONTRACTIONS count as one written word each, NOT as the expanded"
     " tokens the checks index into -- \"I don't know\" is 3 words to a"
     " teacher, and 4 tokens internally; the denominator must be 3",
     "I don't know.", [],
     lambda r: r["word_count"] == 3),

    ("apostrophe-s likewise counts as one word -- the internal token"
     " stream splits \"he's\" into an artifact pair, the word count"
     " must not",
     "He's late.", [],
     lambda r: r["word_count"] == 2),

    ("empty text -- both rates are None rather than 0 or a crash, since"
     " there is genuinely nothing to take a rate over",
     "", [],
     lambda r: (r["sentence_count"] == 0 and r["word_count"] == 0
                and r["errors_per_100_words"] is None
                and r["grammatically_error_free_sentence_pct"] is None)),

    ("out-of-range sentence_index from a mismatched caller must NOT"
     " silently reduce the error-free count below the real sentences",
     "He goes to school.", [_err(0), _err(7)],
     lambda r: (r["sentence_count"] == 1
                and r["grammatically_error_free_sentences"] == 0
                and r["grammatically_error_free_sentence_pct"] == 0.0)),

    ("an error with no sentence_index at all must not crash the"
     " aggregation or corrupt the error-free count",
     "He goes to school.", [{"family": "number", "token_index": 1}],
     lambda r: (r["error_count"] == 1
                and r["grammatically_error_free_sentences"] == 1)),

    ("the grammatically-error-free DEFINITION ships in the payload, and"
     " says GRAMMAR errors specifically -- docs/24 and docs/28 both"
     " require it be stated in the metric itself, not only in the UI",
     "He goes to school.", [],
     lambda r: ("GRAMMAR" in r["grammatically_error_free_definition"]
                and "not a general correctness score"
                in r["grammatically_error_free_definition"])),

    ("no field is labelled bare 'error_free' -- every surfaced name must"
     " carry 'grammatically', so a UI cannot pick up a bare label",
     "He goes to school.", [],
     lambda r: all(("error_free" not in k) or k.startswith("grammatically_")
                   for k in r)),

    ("coverage is reported as PARTIAL with both unbuilt families named --"
     " absence of evidence, not evidence of absence (docs/29)",
     "He goes to school.", [],
     lambda r: (r["coverage"]["partial"] is True
                and r["coverage"]["families_checked"] == 6
                and r["coverage"]["families_total"] == 8
                and {f["family"] for f in r["coverage"]["families"]
                     if not f["checked"]} == {"article/determiner", "preposition"})),

    ("every checked family also carries its own scope note, so a checked"
     " family is never read as fully covered",
     "He goes to school.", [],
     lambda r: all(f["scope"] for f in r["coverage"]["families"])),
]


# ---------------------------------------------------------------------------
# Layer 2: accuracy_report() end-to-end.
# Sentences deliberately avoid the two known committed-check false positives
# (possessive "her", and modals/invariant auxiliaries after a 3rd-singular
# subject) so these assert AGGREGATION, not detection.
# (description, text, check_fn)
# ---------------------------------------------------------------------------

END_TO_END_CASES = [
    ("clean text -- no errors, 100% grammatically error-free",
     "He goes to school. She visited the museum yesterday.",
     lambda r: (r["error_count"] == 0
                and r["grammatically_error_free_sentence_pct"] == 100.0)),

    ("one real error in the first of two sentences",
     "He go to school. She visited the museum yesterday.",
     lambda r: (r["error_count"] == 1
                and r["grammatically_error_free_sentences"] == 1
                and r["grammatically_error_free_sentence_pct"] == 50.0)),

    ("THE LOAD-BEARING CASE for the definition: misspellings with zero"
     " grammar errors must count as grammatically error-free -- this is"
     " the claim docs/24 and docs/28 require, tested behaviourally rather"
     " than asserted in prose",
     "I recieved the letter. She visted the musem.",
     lambda r: (r["error_count"] == 0
                and r["grammatically_error_free_sentence_pct"] == 100.0)),

    ("a merged overlap counts as ONE error, not two -- Task 9's merge"
     " feeding Task 10's count is the whole reason aggregation takes"
     " merged errors rather than the six checks' raw output",
     "Yesterday he go to school.",
     lambda r: (r["error_count"] == 1
                and r["grammatically_error_free_sentence_pct"] == 0.0)),

    ("the report carries the merged error list alongside the aggregate,"
     " so a caller never has to re-run the checks to see what was counted",
     "He go to school.",
     lambda r: (len(r["errors"]) == r["error_count"] == 1
                and r["errors"][0]["family"] == "subject-verb-agreement")),
]


def run():
    failures = []

    print("=== Layer 1: aggregate_accuracy() direct tests ===")
    for desc, text, errors, check_fn in DIRECT_CASES:
        result = aggregate_accuracy(text, errors)
        ok = check_fn(result)
        status = "PASS" if ok else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    %r + %d error(s) -> words=%s sents=%s per100=%s errfree=%s%%"
              % (text, len(errors), result["word_count"], result["sentence_count"],
                 result["errors_per_100_words"],
                 result["grammatically_error_free_sentence_pct"]))
        if not ok:
            failures.append(("direct", desc, result))

    print()
    print("=== Layer 2: accuracy_report() end-to-end ===")
    for desc, text, check_fn in END_TO_END_CASES:
        result = accuracy_report(text, {}, _pos_of)
        ok = check_fn(result)
        status = "PASS" if ok else "FAIL"
        print("[%s] %s" % (status, desc))
        print("    %r -> errors=%s per100=%s errfree=%s%%"
              % (text, result["error_count"], result["errors_per_100_words"],
                 result["grammatically_error_free_sentence_pct"]))
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
