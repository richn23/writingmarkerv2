"""
Grammar Accuracy v1 (docs/24 Revision 3, docs/29) -- Task 1 (subject-verb
agreement) and Task 2 (verb-form over-regularization). Not wired into
score.py yet (Task 11, not this increment).

INPUT MODEL (doc 27's correction, not Repertoire/Metrics' pattern): reads
raw/written text as the primary input -- scoring the approved interpretation
would measure the correction pipeline's grammar, not the learner's. Word
IDENTITY is never independently re-decided here: `written_to_intended` is
the already-resolved written->intended mapping the Spelling/intent pipeline
produced (the audit trail), exactly matching `spelling_score.py`'s own
written/intended pairing (docs/24 Overlap Rule 1). Only the grammatical
MARKING of an already-identified word is this module's own judgment.

Reuses `is_singular_noun`/`is_proper_noun_subject`/`is_past_form` from
`detect.py` (promoted to module level in Task 0) for SUBJECT recognition
and the "skip past-tense verbs" guard -- safe to reuse, since a miss there
just means this check doesn't examine that token, the same "absence, not a
false negative" cost Range already accepts. `is_third_s`/`is_bare_verb`
turned out NOT safely reusable for the actual agreement verdict, despite
docs/29's plan: their strict mode requires `verb_dominant` (more verb
senses than noun senses) as evidence AGAINST a false Range detection --
correct when a miss is free, wrong here, where the identical miss becomes
a false accusation. Confirmed concretely: "my sister works" was flagged as
an error, because "works" has noun senses in the GSE data (public works)
outweighing its verb sense, making it non-`verb_dominant` even though it's
the correct verb here. `_agrees_third`/`_agrees_bare` below are this
module's own, deliberately more permissive, symmetric check instead.

SCOPE, DELIBERATELY NARROW FOR v1: wrong-form only (a verb IS present but
carries the wrong agreement marking, e.g. "he go"). A completely missing
verb/auxiliary ("she happy", "they going" with "are" omitted) is NOT
detected by this check -- distinguishing "no verb attempted" from "not a
verb-shaped constituent for some other, possibly intentional, reason" is
a materially harder and more false-positive-prone problem, deliberately
deferred rather than guessed at. -ing forms and unrecognised tokens are
explicitly excluded from flagging for the same reason.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from .detect import (
    _expand, _WORD, _WORD_CASED, SKIP, SING_DET, SUBJ_PRON_ANY,
    SUBJ_PRON_3SG, SUBJ_PRON_BARE, is_singular_noun, is_past_form,
    is_proper_noun_subject, IRREG_PAST, IRREG_PP,
)
from .sentences import split_sentences
from _engine.lemmas import lemma_candidates  # noqa: E402 -- same reach-outside-the-package pattern pos.py already uses


def _agrees_third(verb, pos_of):
    """Correctly third-person-marked: ends in a real "-s" and is
    recognised as a verb in some sense (any sense -- not required to be
    verb-dominant; that requirement is right for Range's "only claim
    detection when confident" purpose, wrong for judging correctness of an
    already-identified word)."""
    if not verb or not verb.endswith("s") or verb.endswith("ss"):
        return False
    return bool(pos_of and pos_of(verb)["verb"])


def _agrees_bare(verb, pos_of):
    """Correctly bare-form: does NOT carry the "-s" marker, and is
    recognised as a verb in some sense. Callers already exclude -ing/past
    forms before reaching this, so a plain "-s" check is the only
    remaining distinction needed."""
    if not verb or (verb.endswith("s") and not verb.endswith("ss")):
        return False
    return bool(pos_of and pos_of(verb)["verb"])


def _next_idx(w, i):
    j = i + 1
    while j < len(w) and w[j] in SKIP:
        j += 1
    return j


# is_third_s/is_bare_verb deliberately exclude short auxiliaries (AUX_S,
# len<4) -- correct for Range's own purpose (regular "-s" as EVIDENCE of
# present-simple tense), wrong for validating be/have/do's own irregular
# agreement, which needed its own table rather than routing through them.
_BE_FORMS = {"am", "is", "are"}
_HAVE_FORMS = {"has", "have"}
_DO_FORMS = {"does", "do"}


def _irregular_required(verb, subj_text, third):
    """The correctly-agreeing form for be/have/do, given what the subject
    requires. None if `verb` isn't one of these irregulars at all -- caller
    falls through to the regular _agrees_third/_agrees_bare check."""
    if verb in _BE_FORMS:
        if subj_text == "i":
            return "am"
        return "is" if third else "are"
    if verb in _HAVE_FORMS:
        return "has" if third else "have"
    if verb in _DO_FORMS:
        return "does" if third else "do"
    return None


def check_subject_verb_agreement(raw_text, written_to_intended=None, pos_of=None):
    """
    `written_to_intended`: {lowercased written token: intended/corrected
    form}. A token absent from this map is unchanged -- its own written
    form IS its intended form (the common case: nothing to correct).

    Returns a list of error dicts, one per candidate wrong-form agreement
    error: {family, edit_type, subject, written, intended, matched,
    sentence_index}.
    """
    written_to_intended = written_to_intended or {}
    sentences = split_sentences(raw_text)
    errors = []

    def intended_of(tok):
        return written_to_intended.get(tok, tok)

    for sent_idx, sentence in enumerate(sentences):
        low = _expand(sentence.lower())
        w = _WORD.findall(low)
        orig = _WORD_CASED.findall(_expand(sentence))

        for i in range(len(w)):
            third = bare = strict = False
            v = None
            subj_text = None

            if w[i] in SUBJ_PRON_ANY:
                v = _next_idx(w, i)
                third = w[i] in SUBJ_PRON_3SG
                bare = w[i] in SUBJ_PRON_BARE
                subj_text = w[i]
            elif (w[i] in SING_DET and i + 1 < len(w)
                  and is_singular_noun(intended_of(w[i + 1]), pos_of)):
                v = i + 2
                third = True
                strict = True
                subj_text = " ".join(w[i:i + 2])
            elif is_proper_noun_subject(orig, w, i, pos_of):
                v = _next_idx(w, i)
                third = True
                subj_text = orig[i] if i < len(orig) else w[i]

            if not (third or bare) or v is None or v >= len(w):
                continue
            if strict and v - 1 >= 0 and w[v - 1] in SUBJ_PRON_ANY:
                continue

            written_verb = w[v]
            verb = intended_of(written_verb)

            required = _irregular_required(verb, subj_text, third)
            if required is not None:
                if verb != required:
                    errors.append({
                        "family": "subject-verb-agreement", "edit_type": "wrong-form",
                        "subject": subj_text, "written": written_verb, "intended": verb,
                        "matched": "%s %s" % (subj_text, written_verb),
                        "sentence_index": sent_idx,
                    })
                continue

            # Past tense needs no person/number agreement in English --
            # never an error here regardless of subject.
            if is_past_form(verb, pos_of):
                continue
            # -ing / not-a-recognised-verb: a missing-auxiliary or
            # missing-verb case, out of this check's deliberately narrow
            # scope (see module docstring).
            if verb.endswith("ing") or not (pos_of and pos_of(verb)["verb"]):
                continue

            if third and not _agrees_third(verb, pos_of):
                errors.append({
                    "family": "subject-verb-agreement", "edit_type": "wrong-form",
                    "subject": subj_text, "written": written_verb, "intended": verb,
                    "matched": "%s %s" % (subj_text, written_verb),
                    "sentence_index": sent_idx,
                })
            elif bare and not _agrees_bare(verb, pos_of):
                errors.append({
                    "family": "subject-verb-agreement", "edit_type": "wrong-form",
                    "subject": subj_text, "written": written_verb, "intended": verb,
                    "matched": "%s %s" % (subj_text, written_verb),
                    "sentence_index": sent_idx,
                })

    return errors


# ---------------------------------------------------------------------------
# Task 2 -- verb-form over-regularization ("goed" for "went")
# ---------------------------------------------------------------------------
#
# The canonical Grammar/Spelling seam (docs/24, docs/28's own example):
# Spelling's form-test-gated corrector can't reach these ("goed" is too far
# from "went" by edit distance/phonetic similarity to pass), so they fall
# through unresolved rather than being claimed by Spelling -- there is no
# overlap to adjudicate here, only a gap Spelling leaves that this fills.
#
# STARTER SET, not the full ~90-verb IRREG_PAST/IRREG_PP list (docs/29 flagged
# this size as "a real but bounded task" -- built incrementally rather than
# all at once, same vertical-slice discipline as Task 1). Every entry is
# cross-verified programmatically against the EXISTING, TRUSTED IRREG_PAST
# set (used by Range's own is_past_form) -- not just typed from memory.
# That check caught real mistakes before this ever ran against a sentence:
# "steal"->"stole" and "forget"->"forgot" are NOT in IRREG_PAST at all, a
# genuine gap in Range's own reference data (not something to silently patch
# here -- that's protected, calibrated code, out of this task's scope, and
# flagged in the accompanying report instead). "wake"->"woke"/"woken" is
# absent too (only "awake"->"awoke"/"awoken" is present). All three are
# left out of this starter set rather than built on unverified ground.
#
# PAST-SIMPLE ONLY for this increment, not past-participle -- the far more
# common real-world pattern (over-regularized narrative past tense: "I
# goed to the shop") and avoids a second class of problem entirely:
# `is_pp()` doesn't even recognise "run" as a valid participle (it's absent
# from IRREG_PP and doesn't end in "-ed"), so participle coverage would
# need its own, separate verification pass -- deferred, not guessed at.
IRREGULAR_PAST_BY_BASE = {
    "go": "went", "eat": "ate", "run": "ran", "swim": "swam",
    "buy": "bought", "bring": "brought", "think": "thought",
    "catch": "caught", "teach": "taught", "take": "took",
    "give": "gave", "know": "knew", "write": "wrote",
    "speak": "spoke", "break": "broke", "choose": "chose",
    "begin": "began", "drink": "drank", "drive": "drove",
    "ride": "rode", "fall": "fell", "grow": "grew",
    "throw": "threw", "draw": "drew", "fly": "flew",
    "wear": "wore", "sing": "sang", "come": "came",
    "sit": "sat", "stand": "stood", "understand": "understood",
}
assert all(v in IRREG_PAST for v in IRREGULAR_PAST_BY_BASE.values()), (
    "IRREGULAR_PAST_BY_BASE has a form not present in detect.py's own "
    "trusted IRREG_PAST -- fix the mapping, don't silently trust it"
)


def check_verb_form_overregularization(raw_text, written_to_intended=None, pos_of=None):
    """
    Detects a written "-ed" form that regularizes a known irregular verb
    (e.g. "goed" for "went"). Word identity deferred the same way as Task 1:
    `written_to_intended` supplies the already-resolved reading for any
    corrected token before this module judges its form.

    Returns a list of error dicts: {family, edit_type, written, intended,
    base, correct, matched, sentence_index}.
    """
    written_to_intended = written_to_intended or {}
    sentences = split_sentences(raw_text)
    errors = []

    for sent_idx, sentence in enumerate(sentences):
        low = _expand(sentence.lower())
        w = _WORD.findall(low)

        for written in w:
            token = written_to_intended.get(written, written)
            if len(token) <= 3 or not token.endswith("ed"):
                continue
            if token in IRREG_PAST or token in IRREG_PP:
                continue  # already a recognised correct irregular form

            for cand in lemma_candidates(token):
                correct = IRREGULAR_PAST_BY_BASE.get(cand)
                if correct is None:
                    continue
                if token == correct:
                    break  # correctly formed after all, not an error
                errors.append({
                    "family": "verb-form", "edit_type": "wrong-form",
                    "written": written, "intended": token,
                    "base": cand, "correct": correct,
                    "matched": written, "sentence_index": sent_idx,
                })
                break

    return errors
