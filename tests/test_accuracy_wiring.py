"""
Fixtures for Grammar Accuracy v1's Task 11 wiring (docs/29): accuracy_report()
surfaced as score.detail()'s `grammar_accuracy` field.

Unlike the other test_accuracy_* files, these run the REAL pipeline
(GseBank + Corrector + analyse + detail), because the things worth testing
here are exactly the things a unit test with hand-built inputs cannot see:
that the raw text reaches the checks rather than the interpretation, that
the written_to_intended map is really built from the audit trail, and that
the defensive pattern actually isolates failures. Slower than the other
suites by design.

Dependency-free: run directly with `python3 tests/test_accuracy_wiring.py`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))

from _engine.gse import GseBank            # noqa: E402
from _engine.analyse import analyse         # noqa: E402
from _engine.spelling import Corrector      # noqa: E402
import score                                # noqa: E402

_DATA = os.path.join(ROOT, "api", "_data")
_bank = GseBank(os.path.join(_DATA, "gse_vocabulary.json"))
_corrector = Corrector(_bank, os.path.join(_DATA, "english_words.txt"))


def _run(text):
    result = analyse(text, _bank, _corrector)
    return result, score.detail(result)


CHECKS = []


def check(desc):
    def deco(fn):
        CHECKS.append((desc, fn))
        return fn
    return deco


@check("the field is present, populated, and carries no error on a normal run")
def _():
    _, d = _run("Yesterday he go to the shop. He can swim well.")
    ga = d["grammar_accuracy"]
    return (d["grammar_accuracy_error"] is None and ga is not None
            and ga["error_count"] == 1
            and ga["errors"][0]["family"] == "subject-verb-agreement")


@check("READS THE RAW TEXT, not the interpretation -- a misspelling that is"
       " corrected must still leave the raw text as what got checked; routing"
       " through _grammar_source_text() would grade the corrected text and"
       " report near-zero errors")
def _():
    r, d = _run("He recieve the letter.")
    err = d["grammar_accuracy"]["errors"][0]
    # written is the RAW form, intended is the interpretation's form.
    return (err["written"] == "recieve" and err["intended"] == "receive"
            and r["text"] == "He recieve the letter.")


@check("OVERLAP RULE 1 live: the agreement verdict is reached on the"
       " CORRECTED form, so a spelling slip is never re-litigated as a"
       " grammar error, and never double-counted")
def _():
    _, d = _run("He recieve the letter.")
    ga = d["grammar_accuracy"]
    return (ga["error_count"] == 1
            and ga["errors"][0]["family"] == "subject-verb-agreement")


@check("written_to_intended is really built from the audit trail, keyed by"
       " the lowercased written form")
def _():
    r, _d = _run("She recieved her freind letter.")
    m = score._accuracy_written_to_intended(r)
    return m == {"recieved": "received", "freind": "friend"}


@check("misspellings with no grammar error do NOT cost a sentence its"
       " grammatically-error-free status -- docs/24's definition, live")
def _():
    _, d = _run("She recieved the freind letter.")
    ga = d["grammar_accuracy"]
    return (ga["error_count"] == 0
            and ga["grammatically_error_free_sentence_pct"] == 100.0)


@check("SPLIT DIVERGENCE: a spelling split ('alot' -> 'a lot') makes the raw"
       " word count and the interpretation word count genuinely differ, so"
       " grammar_accuracy.word_count and grammar_metrics.word_count are two"
       " different true numbers -- the thing Task 12 must not conflate")
def _():
    _, d = _run("I have alot of freinds.")
    return (d["grammar_accuracy"]["word_count"]
            != d["grammar_metrics"]["word_count"])


@check("a multi-word map value ('a lot') must not crash the checks or"
       " produce a false flag -- it fails every set/POS test and degrades to"
       " no-flag, the conservative direction")
def _():
    _, d = _run("I have alot of freinds.")
    return (d["grammar_accuracy_error"] is None
            and d["grammar_accuracy"]["error_count"] == 0)


@check("DEFENSIVE PATTERN: an Accuracy failure sets the paired _error field,"
       " returns None, and never fails the score")
def _():
    orig = score.accuracy_report
    try:
        def boom(*a, **k):
            raise RuntimeError("simulated failure")
        score.accuracy_report = boom
        r, d = _run("He go to school.")
        return (d["grammar_accuracy"] is None
                and "simulated failure" in d["grammar_accuracy_error"]
                and r["valid"] is True
                and d["grammar_detected"] is not None)
    finally:
        score.accuracy_report = orig


@check("INDEPENDENCE: a total Range failure must NOT suppress Accuracy."
       " grammar_metrics genuinely depends on gd and is correctly suppressed"
       " with it, but Accuracy shares nothing with Range beyond the pos"
       " lookup -- nesting its try block would have reported 'no errors'"
       " instead of 'an error occurred', the one failure mode this panel"
       " must never have")
def _():
    orig = score._grammar_detected
    try:
        def boom(*a, **k):
            raise RuntimeError("range exploded")
        score._grammar_detected = boom
        _, d = _run("He go to school.")
        return (d["grammar_detected"] is None
                and d["grammar_metrics"] is None
                and d["grammar_accuracy"] is not None
                and d["grammar_accuracy"]["error_count"] == 1
                and d["grammar_accuracy_error"] is None)
    finally:
        score._grammar_detected = orig


@check("the payload carries its own error-free definition and partial"
       " coverage block through the wiring, not just in the module")
def _():
    _, d = _run("He goes to school.")
    ga = d["grammar_accuracy"]
    return ("GRAMMAR" in ga["grammatically_error_free_definition"]
            and ga["coverage"]["partial"] is True
            and ga["coverage"]["families_checked"] == 6)


@check("empty-ish input does not raise and does not fabricate a rate")
def _():
    _, d = _run("")
    ga = d["grammar_accuracy"]
    return (d["grammar_accuracy_error"] is None
            and ga["errors_per_100_words"] is None
            and ga["grammatically_error_free_sentence_pct"] is None)


def run():
    failures = []
    for desc, fn in CHECKS:
        try:
            ok = fn()
        except Exception as exc:
            ok = False
            desc = "%s  [raised %s: %s]" % (desc, type(exc).__name__, exc)
        print("[%s] %s" % ("PASS" if ok else "FAIL", desc))
        if not ok:
            failures.append(desc)

    print()
    print("%d/%d passed" % (len(CHECKS) - len(failures), len(CHECKS)))
    if failures:
        print("FAILURES:")
        for desc in failures:
            print("  - %s" % desc)
        sys.exit(1)


if __name__ == "__main__":
    run()
