"""
Port of LENS's `src/lib/grammarDetect.ts` (787 lines, verified against the
same fixture set structures.json ships -- see docs/21 for the verification
report). Ported, not reimplemented: control flow, regexes and comments below
mirror the TypeScript line for line wherever Python syntax allows, so a
divergence is visible as a diff rather than hidden inside a rewrite.

SCOPE IS DELIBERATELY PARTIAL AND SAYS SO -- same as the original. Only
structures whose form is mechanically unambiguous are detected. The fuzzy
ones are DEFERRED and listed in `coverage`. False positives are the worse
failure: a teacher can spot a missing structure, but a confidently-wrong one
gets believed.

This module does not correct anything. A structure that doesn't parse simply
isn't detected -- Accuracy (attempted-but-malformed) is explicitly out of
scope, per the 24 Aug brief.
"""

import re

from .families import (
    rows_for_family, ALL_DECLARED_FAMILIES, assert_detector_families,
    SHORT_DESCRIPTION, level_num,
)

# ---------------------------------------------------------------------------
# EGP resolution (reference)
# ---------------------------------------------------------------------------

MODAL_FAMILY = {
    "can": "can", "could": "could", "may": "may", "might": "might",
    "must": "must", "should": "should", "shall": "shall", "would": "would",
}

# Every family a detector can fire. This is DETECTION logic -- which family a
# given token belongs to is not derivable from the reference -- but it is NOT
# a coverage claim. assert_detector_families() (called below, at import time)
# fails the import if any pair here is missing from structures.json.
DETECTOR_FAMILIES = {
    "present-simple": ["present_simple"],
    "past-simple": ["past_simple"],
    "present-continuous": ["present_continuous"],
    "past-continuous": ["past_continuous"],
    "present-perfect": ["present_perfect_simple"],
    "present-perfect-continuous": ["present_perfect_continuous"],
    "past-perfect": ["past_perfect_simple"],
    "past-perfect-continuous": ["past_perfect_continuous"],
    "future-will-going-to": ["future_simple_with_will_and_shall", "future_with_be_going_to"],
    "future-continuous": ["future_continuous"],
    "future-perfect": ["future_perfect_simple"],
    "passive": ["passives_form"],
    "there-is-are": ["there_isare"],
    "used-to": ["used_to"],
    "wish": ["past_simple", "past_perfect_simple"],
    "would-like": ["would"],
    "modals-ability": ["can", "could", "shall", "would"],
    "modals-obligation": ["must", "should", "ought", "have_got_to"],
    "modals-deduction": ["may", "might"],
    "modals-past": list(MODAL_FAMILY.values()),
    "adverbs-of-frequency": ["adverbs_and_adverb_phrases_types_and_meanings"],
    "subordination": ["subordinating"],
    "concessive-clauses": ["subordinating"],
    "relative-clauses": ["relative"],
    "reported-speech": ["reported_speech"],
    "question-tags": ["tags"],
    "conditionals-real": ["conditional"],
    "conditionals-unreal": ["conditional"],
    "comparatives-superlatives": ["comparatives", "superlatives"],
    "coordinating-conjunctions": ["coordinating", "coordinated"],
}

assert_detector_families(DETECTOR_FAMILIES)

# Rows resolve from the single source for every declared family, not a
# private list: a family keyed on the Explorer becomes reachable here the
# moment it is keyed.
_FAMILY_ROWS = {}
for _fid in ALL_DECLARED_FAMILIES:
    _rows = rows_for_family(_fid)
    if _rows:
        _FAMILY_ROWS[_fid] = _rows


# FIX 2 -- CAN-DO ROWS CARRY CONDITIONS THAT NOTHING CHECKS.
#
# An EGP row's guideword declares what kind of claim it is:
#   "FORM: ..."      the row is about the form alone      -> selectable from a form match
#   "USE: ..."       the row adds a semantic/pragmatic condition (politeness,
#   "FORM/USE: ..."  hedging, temporary situations, a required verb class)
#
# Only a FORM row can be chosen by a form match. Choosing a USE row from form
# alone is how "they are laughing" resolved to present continuous C2
# POLITENESS in the original bug: that row's can-do prose happens to contain
# "are" and "statements", which a naive scorer reads as a marker hit and an
# affirmative hit. So: gate the conditioned rows out of form-driven
# selection, and score against the GUIDEWORD only.
def _is_form_only_row(r):
    return bool(re.match(r"^\s*FORM\s*:", r.get("guideword") or "", re.I))


# F5 -- CONDITIONS STATED IN PROSE, NOT DECLARED IN THE TYPE.
#
# The Fix 2 gate reads the guideword PREFIX. But many FORM rows go on to
# state a condition in the can-do TEXT, and nothing checks it there either --
# so a passive matching "is planned" (present) was described as "past simple
# passive". Where the claim cannot be verified against what actually fired,
# the can-do is suppressed and the family/level/span still print. A missing
# description is a gap; a wrong one is a falsehood.

_QUOTED_WORD = re.compile(r"['\"‘’“”]([a-z][a-z' -]{0,24})['\"‘’“”]", re.I)
_PAREN_LIST = re.compile(r"\(([^)]*)\)")
_PAREN_ITEM = re.compile(r"^[a-z][a-z' -]{0,24}$")


def _claimed_words(can_do):
    """Words the can-do explicitly requires, taken from quotes and
    parenthesised lists."""
    out = []
    for m in _QUOTED_WORD.finditer(can_do):
        out.append(m.group(1).lower().strip())
    for m in _PAREN_LIST.finditer(can_do):
        if "," not in m.group(1):
            continue  # a list, not an aside
        for part in m.group(1).split(","):
            t = re.sub(r"['\"‘’“”]", "", part).strip().lower()
            if _PAREN_ITEM.match(t):
                out.append(t)
    seen, uniq = set(), []
    for w in out:
        if w and w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


_TENSE_CLAIMS = [
    (re.compile(r"\bpast simple\b", re.I), "past simple"),
    (re.compile(r"\bpresent simple\b", re.I), "present simple"),
    (re.compile(r"\bpast continuous\b", re.I), "past continuous"),
    (re.compile(r"\bpresent continuous\b", re.I), "present continuous"),
    (re.compile(r"\bpast perfect\b", re.I), "past perfect"),
    (re.compile(r"\bpresent perfect\b", re.I), "present perfect"),
    (re.compile(r"\bfuture\b", re.I), "future"),
    (re.compile(r"\bimperative\b", re.I), "imperative"),
]


def _prose_condition_holds(can_do, matched, window, fam):
    """Does the fired evidence support every claim the prose makes?"""
    if not can_do:
        return True
    hay = ("%s %s" % (matched, window)).lower()

    words = _claimed_words(can_do)
    if words and not any(
        re.search(r"(^|\s)%s(\s|$)" % re.escape(v), hay) for v in words
    ):
        return False

    for pat, name in _TENSE_CLAIMS:
        if not pat.search(can_do):
            continue
        f = fam.replace("_", " ")
        if name == "imperative":
            # an imperative main clause has no subject before its verb -- not checkable here
            return False
        if name == "future":
            continue  # "future" is a use, not a form claim
        if f.split(" ")[0] if False else name.split(" ")[0] not in f:
            return False
        if "perfect" in name and "perfect" not in f:
            return False
        if "continuous" in name and "continuous" not in f:
            return False
        if "simple" in name and "perfect" in f:
            return False
    return True


class FireCtx:
    __slots__ = ("question", "negative", "past", "marker", "variant", "window", "thematic_marker")

    def __init__(self, question=False, negative=False, past=False,
                 marker=None, variant=None, window=None, thematic_marker=False):
        self.question = question
        self.negative = negative
        self.past = past
        self.marker = marker
        self.variant = variant
        self.window = window
        # Opt-in only. Most call sites pass a common auxiliary/modal as
        # marker ("are", "is", "was", "could"...), which WILL turn up as
        # ordinary grammatical glue in unrelated USE-row prose -- exactly
        # the class of false match Fix 2 exists to prevent (see the note
        # above _resolve_structure). Fix 6's prose search is a genuine,
        # narrow exception to guideword-only scoring, so it stays opt-in to
        # the few call sites (wish/if-only) where the marker is distinctive
        # enough that a prose match means something.
        self.thematic_marker = thematic_marker


# FIX 6 (24 Aug 2026) -- THE FORM-ONLY GATE WAS DISCARDING THE ONLY ROW THAT
# COULD BE RIGHT.
#
# Fix 2's gate blanket-excluded every USE:/FORM/USE: row from a family's
# candidate pool whenever the family had ANY row starting "FORM:". That
# over-corrected: for `wish` (10 of 24 rows discarded, including the
# wish/regret row itself), `conditional` (23 of 27 discarded, including
# every second/third-conditional row), and `past_perfect_simple` (12 of 20,
# including both "if only" rows), the excluded rows were not incidental --
# they were the only rows that actually describe the fired construction. A
# genuine second conditional was resolving to a2 "if + present simple"
# because nothing else was left to compete with it. Root-caused and
# regression-fixtured in docs/23.
#
# The fix is not "stop excluding rows" alone -- that reopens the ORIGINAL
# bug Fix 2 existed for (a USE row winning by incidental vocabulary overlap
# in its own guideword, not real evidence). So every row stays in the pool,
# and scoring stays guideword-only for the generic AFFIRMATIVE/NEGATIVE/
# QUESTION/PAST signals and the existing marker/variant/quoted-word checks
# -- unchanged, still guideword-only, still narrow.
#
# What's new is one ADDITIONAL, narrowly-scoped signal: some rows (`USE:
# REGRET`, the shared "AFTER 'IF ONLY' AND 'WISH'" row) name their own
# construction only in the can-do prose, never in the guideword -- so no
# guideword-only signal can ever tell them apart from a generic row. For
# those, and only when the row's own can-do prose contains the ALREADY-KNOWN
# trigger word from match time (never a generic vocabulary scan -- exactly
# one specific word, chosen by the detector, not guessed by the resolver),
# award a bonus large enough to beat a same-family row's largest realistic
# generic-only score. Where a can-do sentence covers more than one
# construction/polarity in one breath (the shared wish/if-only row covers
# both), the polarity check is scoped to the clause that actually names the
# marker, not the whole sentence -- otherwise "if only" and "wish" bleed
# into each other's affirmative/negative claims.
_CLAUSE_SPLIT = re.compile(r"[,.]")

# Scoped, not universal. The brief's own diagnosis (docs/23) names three
# families as broken by the blanket exclusion: `wish` (past_simple,
# past_perfect_simple), `conditional`, and the modals-past sub-families
# (all 8 modal names). Widening the pool for every other family too surfaced
# an UNRELATED, pre-existing scoring quirk -- `question-tags` rows are
# penalised for containing the word "QUESTION" in their own guideword, since
# ctx.question is never set true for tag detection, and that penalty used to
# be masked only because the form-only gate excluded the row it was hurting
# most. That is a real, separate bug, not this brief's to fix -- flagged,
# not silently patched alongside this one. Keeping the pool restriction for
# every family outside this set preserves their exact prior behaviour.
_UNGATE_FAMILIES = {"past_simple", "past_perfect_simple", "conditional"} | set(MODAL_FAMILY.values())


def _resolve_structure(fam, ctx):
    rows = _FAMILY_ROWS.get(fam)
    if not rows:
        return None
    form_only = [r for r in rows if _is_form_only_row(r)]
    # No blanket exclusion for the families Fix 6 targets (see
    # _UNGATE_FAMILIES above) -- every row in those families competes.
    # Every other family keeps the original fallback-only-if-empty gate.
    pool = rows if fam in _UNGATE_FAMILIES else (form_only if form_only else rows)
    marker_re = None
    if ctx.marker:
        marker_re = re.compile(r"(?<![A-Z])" + re.escape(ctx.marker.upper()) + r"(?![A-Z])")

    win = (ctx.window or "").lower()
    best, best_score, basis_bits = None, float("-inf"), []
    for r in pool:
        # GUIDEWORD ONLY for every generic/marker/variant signal below --
        # never the can-do prose (see the note above the function).
        T = (r.get("guideword") or "").upper()
        can_do = r.get("can_do") or ""
        sc = 0
        has_q = bool(re.search(r"QUESTION", T))
        has_n = bool(re.search(r"NEGATIV", T))
        has_a = bool(re.search(r"AFFIRMATIVE|STATEMENT", T))
        has_past = bool(re.search(r"PAST", T))
        if ctx.question:
            sc += 3 if has_q else 0
        else:
            sc -= 3 if has_q else 0
        if ctx.negative:
            sc += 3 if has_n else 0
        else:
            sc -= 3 if has_n else 0
        if not ctx.question and not ctx.negative and has_a:
            sc += 2
        if ctx.past:
            sc += 2 if has_past else 0
        else:
            sc -= 2 if has_past else 0
        guideword_marker_hit = bool(marker_re and marker_re.search(T))
        if guideword_marker_hit:
            sc += 2
        # rows citing a specific quoted word that is NOT in the matched window are penalised
        quoted = [m.group(1).lower() for m in re.finditer(r"'([A-Za-z][A-Za-z ()-]*)'", r.get("guideword") or "")]
        if quoted and not any(re.sub(r"\(.*\)", "", q).strip() in win for q in quoted):
            sc -= 2
        # every guideword probe is word-anchored: unanchored /REAL/ also
        # matches "UNREAL" and unanchored /PAST/ also matches "PAST
        # PARTICIPLE". Same discipline as families.py's norm_key.
        if ctx.variant == "real":
            if re.search(r"(REAL|IMPERATIVE|PRESENT SIMPLE)", T) and not re.search(r"PAST", T):
                sc += 3
            elif re.search(r"(PAST SIMPLE|PAST PERFECT|IMAGIN)", T):
                sc -= 3
        if ctx.variant == "unreal":
            if re.search(r"(PAST SIMPLE|PAST PERFECT|IMAGIN|UNREAL)", T):
                sc += 3
            elif re.search(r"(REAL|IMPERATIVE)", T):
                sc -= 3
        # FIX 6 -- the named-construction signal. Guideword-only signals above
        # are unconditional; this is additive, and only ever searches for the
        # one word ctx.marker already names.
        #
        # The base bonus is gated to "guideword alone didn't already reveal
        # it" -- otherwise a row that already earns the ordinary +2 above
        # (e.g. a genuine FORM-only row that happens to quote the marker
        # word, like the 'had it not been for' fixed expression matching a
        # plain `marker="had"` past-perfect detection) would double-count the
        # same evidence and spuriously outrank a row with real signal but no
        # quoted marker. The polarity refinement below is NOT re-gated the
        # same way: it is a separate, useful differentiator needed even when
        # the guideword already carries the marker (the shared "if only"/
        # "wish" row does, but its guideword alone can't tell an affirmative
        # "if only" claim from a negative one -- only the prose, clause by
        # clause, can).
        prose_marker_hit = bool(
            ctx.thematic_marker and marker_re and marker_re.search(can_do.upper())
        )
        if marker_re and not guideword_marker_hit and prose_marker_hit:
            sc += 5
        if ctx.thematic_marker and marker_re and (guideword_marker_hit or prose_marker_hit):
            for clause in _CLAUSE_SPLIT.split(can_do):
                CU = clause.upper()
                if not marker_re.search(CU):
                    continue
                c_has_a = "AFFIRMATIVE" in CU
                c_has_n = "NEGATIVE" in CU
                if ctx.negative:
                    if c_has_n:
                        sc += 2
                    if c_has_a and not c_has_n:
                        sc -= 2
                else:
                    if c_has_a:
                        sc += 2
                    if c_has_n and not c_has_a:
                        sc -= 2
        # TIE-BREAK: strictly-greater keeps the FIRST best, and `pool` is
        # level-ascending, so a tie resolves to the LOWEST row -- the
        # governing "where the evidence does not decide, under-state" rule.
        if sc > best_score:
            best_score = sc
            best = r
    if best is None:
        return None
    if ctx.question:
        basis_bits.append("question form")
    elif ctx.negative:
        basis_bits.append("negative form")
    else:
        basis_bits.append("affirmative form")
    if ctx.past:
        basis_bits.append("past/perfect")
    if ctx.variant:
        basis_bits.append(ctx.variant + " conditional")
    if ctx.marker:
        basis_bits.append("marker '%s'" % ctx.marker)
    # Confidence flag: true whenever the winning row's own identification
    # rested on more than a pure form declaration -- either it is not a
    # FORM:-only row (Fix 6 above), or its can-do states a condition the
    # fired evidence cannot verify (Fix 5, unchanged).
    best_is_form_only = _is_form_only_row(best)
    prose_ok = _prose_condition_holds(best.get("can_do"), ctx.window or "", win, fam)
    condition_unverified = (not best_is_form_only) or (not prose_ok)
    if not best_is_form_only:
        basis_bits.append("selected via a non-form-only row -- condition unverified")
    if not prose_ok:
        basis_bits.append("can-do states an unverifiable condition -- description withheld")
    return {
        "structure_id": best["id"],
        "level": best.get("level"),
        "level_num": level_num(best.get("level")),
        "guideword": best.get("guideword"),
        "can_do": None if condition_unverified else best.get("can_do"),
        "basis": " + ".join(basis_bits),
        "condition_unverified": condition_unverified,
    }


# ---------------------------------------------------------------------------
# form machinery
# ---------------------------------------------------------------------------

IRREG_PP = set((
    "been done gone made taken seen given known found told thought become shown "
    "left felt kept brought begun written spoken broken chosen eaten forgotten "
    "gotten got hidden stolen swum drunk sung fought sought dealt dug hung shot "
    "slid crept swept wept swung stuck stung struck spun spat sped fled flung "
    "clung sprung sunk shrunk sworn torn ridden blown bitten bred bent bound "
    "awoken woken arisen frozen forbidden forgiven mistaken overcome shaken knelt "
    "lent burnt dreamt trodden withdrawn lain laid beaten borne born ground "
    "grown thrown drawn fallen flown driven risen worn sold read put cut let "
    "set hit shut cost spent meant lit led fed hid held stood understood "
    "built lost won paid met sent slept sat caught taught bought heard said "
    "had travelled visited signed announced"
).split())
ADJ_PARTICIPLE = set(
    "tired interested excited bored worried married scared surprised pleased "
    "disappointed confused embarrassed satisfied frightened relaxed closed open".split()
)
# FIX 8 (25 Aug 2026, Accuracy v1 Task 2 cross-verification, docs/31) --
# "stole"/"forgot"/"woke" were absent from this set entirely (their
# participles "stolen"/"forgotten" were already present above in IRREG_PP;
# only the past-simple forms were missing here). Found not by inspection
# but by asserting Accuracy's new irregular-verb starter mapping against
# this set programmatically before trusting it -- the same "verify, don't
# hand-trace" discipline as the gate fix. "woken" added to IRREG_PP to
# match, since "awoken" already had both its past-simple ("awoke") and
# participle forms present and "woke"/"woken" deserved the same parity.
IRREG_PAST = set((
    "was were had did went said made got came took saw knew thought bought "
    "brought caught taught found left felt kept told became began ran wrote "
    "spoke broke chose sat ate drank swam sang sent slept met paid flew drove "
    "gave won lost built held stood understood grew threw drew fell rose wore "
    "sold spent meant lit led fed hid heard fought sought dealt dug hung shot "
    "slid crept swept wept swung stuck stung struck spun spat sped fled flung "
    "clung sank shrank stank swore tore rode blew bit bred bent awoke woke arose "
    "froze forbade forgave mistook overcame shook knelt lent burnt dreamt trod withdrew "
    "stole forgot"
).split())


def is_pp(w):
    return w in IRREG_PP or (len(w) > 3 and w.endswith("ed"))


def is_ing(w):
    return len(w) > 4 and w.endswith("ing")


SKIP = set("not never ever just already recently also often usually always still only really certainly probably definitely all both since now n t".split())
DET = set("the a an my your his her its our their this that these those some any".split())
PRON_SUBJ = set("i you he she it we they there".split())
FREQ_ADV = set("always usually often sometimes rarely never seldom frequently occasionally".split())
SUBORDINATORS = set("because when while unless until whenever wherever whether".split())  # after/before/since excluded: usually prepositional (FP risk)

SUBJ_PRON_3SG = set("he she it".split())
SUBJ_PRON_ANY = set("i you he she it we they".split())
SING_DET = set("the a an this that my your his her its our their every each".split())
AUX_S = set("is was has does".split())
AUX_PAST = set("was were had did been being".split())
SUBJ_PRON_BARE = set("i you we they".split())
AUX_OR_MODAL = set(
    "am is are was were be been being have has had do does did will would can "
    "could may might must shall should ought used".split()
)

# Promoted from closures inside detect_grammar_structures() (Task 0, docs/29,
# 25 Aug 2026) so Accuracy's subject-verb-agreement check (accuracy.py) can
# reuse the exact same anchoring logic Range's own baseline-tense pass uses,
# rather than a second, potentially-drifting copy. Pure extraction -- same
# bodies, `pos_of` (and `orig`/`w`/`i` for the last one) now explicit
# parameters instead of captured from the enclosing function's scope. Zero
# behavior change, verified against the full 92-example fixture set staying
# byte-identical.
def is_third_s(x, strict, pos_of):
    if not x or len(x) < 4 or not x.endswith("s") or x.endswith("ss") or x in AUX_S:
        return False
    if not pos_of:
        return False
    info = pos_of(x)
    return (info["verb_dominant"] and not info["noun"]) if strict else info["verb"]


def is_past_form(x, pos_of):
    if not x or x in AUX_PAST or x in ADJ_PARTICIPLE:
        return False
    if x in IRREG_PAST:
        return True
    if len(x) > 3 and x.endswith("ed") and pos_of:
        info = pos_of(x)
        return info["verb"] and not info["surface_verb"]
    return False


def is_bare_verb(x, pos_of):
    if not x or len(x) <= 1 or x in AUX_OR_MODAL or x in ADJ_PARTICIPLE:
        return False
    if x.endswith("s") and not x.endswith("ss"):
        return False
    if x.endswith("ing") or is_past_form(x, pos_of):
        return False
    return bool(pos_of and pos_of(x)["verb"])


def is_singular_noun(x, pos_of):
    return bool(x and not x.endswith("s") and pos_of and pos_of(x)["noun"])


def is_proper_noun_subject(orig, w, i, pos_of):
    if len(orig) != len(w):
        return False
    tok = orig[i] if i < len(orig) else ""
    return bool(re.match(r"^[A-Z]", tok or "")) and bool(pos_of) and not pos_of(w[i])["known"]


# Clause-level coordination.
CLAUSE_COORD = re.compile(
    r"(,\s*(and|but|or|so|yet)\b|\b(and|but|or|so|yet)\s+(i|you|he|she|it|we|they|the|a|an|this|that|these|those|my|your|his|her|its|our|their)\b)",
    re.I,
)

NAMES = {
    "present-simple": "Present Simple", "past-simple": "Past Simple",
    "present-continuous": "Present Continuous", "past-continuous": "Past Continuous",
    "present-perfect": "Present Perfect", "present-perfect-continuous": "Present Perfect Continuous",
    "past-perfect": "Past Perfect", "past-perfect-continuous": "Past Perfect Continuous",
    "future-will-going-to": "Future: will & going to", "future-continuous": "Future Continuous",
    "future-perfect": "Future Perfect", "passive": "The Passive",
    "modals-ability": "Modal: ability/permission", "modals-obligation": "Modal: obligation/advice",
    "modals-deduction": "Modal: possibility/deduction", "modals-past": "Modal + have + participle",
    "would-like": "'Would like'", "used-to": "'used to'", "wish": "'wish' / 'if only'",
    "there-is-are": "There is / There are", "question-tags": "Question Tags",
    "comparatives-superlatives": "Comparatives & Superlatives",
    "conditionals-real": "Conditional: real (zero/first)", "conditionals-unreal": "Conditional: unreal (second/third)",
    "relative-clauses": "Relative Clause", "reported-speech": "Reported Speech",
    "concessive-clauses": "Concessive Clause", "subordination": "Subordinate Clause",
    "coordinating-conjunctions": "Clause Coordination", "adverbs-of-frequency": "Adverbs of Frequency",
}

# Structures that DO carry a subordinate clause (for the derived 2.3 classification).
SUBORDINATE_STRUCTS = {
    "subordination", "concessive-clauses", "relative-clauses",
    "reported-speech", "conditionals-real", "conditionals-unreal", "wish",
}

# PARTIAL -- detected, but only over a stated subset of their forms.
PARTIAL = [
    {
        "id": "present-simple", "name": "Present Simple",
        "detects": "any form with an adjacent subject — third-person singular "
                   "(“she bakes”, “the shop opens”, “Maria works”) and bare "
                   "forms after a subject pronoun (“I go”, “they buy”)",
        "misses": "plural noun-phrase subjects (“the children play”), and negatives "
                  "and questions carrying ‘do/does’",
    },
    {
        "id": "past-simple", "name": "Past Simple",
        "detects": "past forms directly after their subject and not after have/has/had/be "
                   "(“they bought”, “the teacher explained”)",
        "misses": "forms shared with the past participle after an auxiliary, and -ed words "
                  "that are commonly adjectives (“closed”, “tired”)",
    },
]

DEFERRED = [
    {"id": "imperatives", "reason": "sentence-initial base verb is too ambiguous"},
    {"id": "questions", "reason": "interrogative word order needs a parse (tags ARE detected)"},
    {"id": "gerunds-infinitives", "reason": "verb-pattern disambiguation is semantic"},
    {"id": "phrasal-verbs", "reason": "particle vs preposition needs a lexicon pass"},
    {"id": "inversion", "reason": "fronted-inversion patterns under design — high FP risk"},
    {"id": "intensifiers", "reason": "open-class degree words"},
    {"id": "adverbial-phrases", "reason": "word-order analysis, not marker detection"},
    {"id": "adverbs", "reason": "manner/comment adverbs need POS context"},
    {"id": "pronouns", "reason": "always present — uninformative as a detection"},
    {"id": "possessives", "reason": "always present — uninformative as a detection"},
    {"id": "prepositions", "reason": "always present — uninformative as a detection"},
    {"id": "articles", "reason": "always present — uninformative as a detection"},
    {"id": "quantifiers", "reason": "high-frequency function words — uninformative"},
    {"id": "demonstratives", "reason": "high-frequency function words — uninformative"},
    {"id": "verb-to-be", "reason": "always present — uninformative as a detection"},
    {"id": "adverbs-of-frequency", "reason": "detected by presence only — position analysis deferred"},
]

_WORD = re.compile(r"[a-z]+")
_WORD_CASED = re.compile(r"[A-Za-z]+")


# FIX 7 (25 Aug 2026, Task 3c) -- '\d' IS AMBIGUOUS BETWEEN "HAD" AND "WOULD".
#
# LENS's own `expand()` (grammarDetect.ts:443, confirmed identical -- this is
# upstream, not a porting artifact) unconditionally maps 'd -> " would". That
# is right for "'d + bare verb" ("they'd love to come" = "they would love to
# come", "I'd rather stay" = idiom, always "would") but wrong for "'d + past
# participle" ("they'd already mentioned it" = "they had already mentioned
# it", "she'd finished" = "she had finished") -- those were resolving to a
# spurious modals-ability/would hit ("would already", "would finished") while
# the real past-perfect went entirely undetected.
#
# Disambiguated the same way the rest of this file already looks past an
# aux to its participle: skip any SKIP-listed adverb, then check whether the
# next word is a past participle via the existing is_pp()/IRREG_PP -- no new
# data, reusing exactly what the "had"/"have" branches already use for the
# identical judgment call.
def _next_word_after(s, pos):
    for m in re.finditer(r"[A-Za-z']+", s[pos:]):
        w = m.group(0).lower()
        if w not in SKIP:
            return w
    return ""


def _expand_d(m):
    return " had" if is_pp(_next_word_after(m.string, m.end())) else " would"


def _expand(s):
    s = re.sub(r"\bcan't\b", "can not", s, flags=re.I)
    s = re.sub(r"\bwon't\b", "will not", s, flags=re.I)
    s = re.sub(r"n't\b", " not", s, flags=re.I)
    s = re.sub(r"'ll\b", " will", s, flags=re.I)
    s = re.sub(r"'d\b", _expand_d, s, flags=re.I)
    s = re.sub(r"'ve\b", " have", s, flags=re.I)
    s = re.sub(r"'re\b", " are", s, flags=re.I)
    s = re.sub(r"'m\b", " am", s, flags=re.I)
    return s


def _level_evidence(raw_hits):
    """
    PASS 2 of 2. Takes Pass 1's raw evidence (one entry per fired
    explorer_id+family, each carrying the FireCtx the detector captured at
    match time under "_ctx") and resolves an EGP row/level for each,
    independently -- one family's resolve failing or changing does not
    touch another's. Returns the same per-hit shape `add()` used to build
    inline before this split, minus the internal "_ctx" field.
    """
    out = []
    for h in raw_hits:
        ctx = h["_ctx"]
        rep = _resolve_structure(h["family_id"], ctx)
        out.append({
            "explorer_id": h["explorer_id"],
            "name": h["name"],
            "matched": h["matched"],
            "matched_spans": h["matched_spans"],
            "count": h["count"],
            "family_id": h["family_id"],
            "egp_structure_id": rep["structure_id"] if rep else None,
            "level": rep["level"] if rep else None,
            "level_num": rep["level_num"] if rep else 0,
            "guideword": rep["guideword"] if rep else None,
            "can_do": rep["can_do"] if rep else None,
            "selection_basis": rep["basis"] if rep else None,
            "condition_unverified": rep["condition_unverified"] if rep else False,
            "general_description": SHORT_DESCRIPTION.get(h["explorer_id"]) if (rep and not rep["can_do"]) else None,
        })
    return out


def detect_grammar_structures(sentences, pos_of=None):
    """Detect grammar structures across sentences. Pure and deterministic.

    Returns {"detected": [...], "per_sentence": [...], "coverage": {...}} --
    same shape as the TS original's return value, snake_cased.
    """
    hits = {}
    per_sentence = []
    # C3b -- which PARTIAL limits could actually bite on THIS input.
    partial_relevant = set()

    # PASS 1 -- EVIDENCE ONLY. `add()` records that a family fired, its
    # matched span(s), and the context the resolver will eventually need --
    # it does not call the resolver itself. Mirrors the Vocab/Spelling split
    # between interpretation and scoring: token-matching stays separable
    # from EGP-row selection, so either stage can be inspected, tested, or
    # changed on its own. See _level_evidence() below for Pass 2.
    def add(explorer_id, family, matched, ctx=None):
        ctx = ctx or FireCtx()
        key = explorer_id + "|" + family
        cur = hits.get(key)
        if cur:
            cur["count"] += 1
            if matched and matched not in cur["matched_spans"] and len(cur["matched_spans"]) < 8:
                cur["matched_spans"].append(matched)
            return
        hits[key] = {
            "explorer_id": explorer_id,
            "name": ("%s (%s)" % (NAMES[explorer_id], family)) if explorer_id == "modals-past"
                    else NAMES.get(explorer_id, explorer_id),
            "matched": matched,
            "matched_spans": [matched] if matched else [],
            "count": 1,
            "family_id": family,
            "_ctx": FireCtx(
                question=ctx.question, negative=ctx.negative, past=ctx.past,
                marker=ctx.marker, variant=ctx.variant, window=ctx.window or matched,
                thematic_marker=ctx.thematic_marker,
            ),
        }

    for sentence in sentences:
        low = _expand(sentence.lower())
        w = _WORD.findall(low)
        orig = _WORD_CASED.findall(_expand(sentence))
        sent_fired = set()
        is_question = bool(re.search(r"\?\s*$", sentence.strip()))

        # F7 -- A DEFERRED STRUCTURE MUST NOT FIRE A DIFFERENT ONE.
        INVERSION_OPENERS = set("had were should".split())
        FRONTED_NEGATIVE = re.compile(r"^(never|rarely|seldom|hardly|scarcely|little|no sooner|not only)\b")
        inverted = (
            (not is_question and w and w[0] in INVERSION_OPENERS and len(w) > 1
             and (w[1] in PRON_SUBJ or w[1] in DET))
            or bool(FRONTED_NEGATIVE.match(low.strip()))
        )
        inverted_until = min(len(w), 4) if inverted else -1

        def in_inverted(i):
            return i <= inverted_until

        def nextIdx(i):
            j = i + 1
            while j < len(w) and w[j] in SKIP:
                j += 1
            return j

        def fire(id_, fam, i, length=2, **kw):
            matched = " ".join(w[i:i + length])
            window_words = " ".join(w[max(0, i - 1):i + length + 1])
            ctx = FireCtx(
                question=is_question,
                negative="not" in window_words.split(" "),
                past=(id_ == "modals-past"),
                marker=w[i],
                window=window_words,
            )
            for k, v in kw.items():
                setattr(ctx, k, v)
            add(id_, fam, matched, ctx)
            sent_fired.add(id_)

        def after_subject(j):
            if j < len(w) and w[j] in PRON_SUBJ:
                return nextIdx(j)
            if j < len(w) and w[j] in DET:
                k = j + 1
                if k + 1 < len(w) and w[k + 1] and not is_pp(w[k]) and not is_ing(w[k]):
                    k += 1
                return k
            return j

        i = 0
        while i < len(w):
            if inverted and in_inverted(i):
                i += 1
                continue
            t = w[i]
            j = nextIdx(i)
            n = w[j] if j < len(w) else None

            if t in ("have", "has") and n:
                k = after_subject(j)
                m = w[k] if k < len(w) else None
                if n == "to" and j + 1 < len(w) and w[j + 1]:
                    fire("modals-obligation", "have_got_to", i, 3)
                elif n == "been" and j + 1 < len(w) and w[j + 1] and is_ing(w[j + 1]):
                    fire("present-perfect-continuous", "present_perfect_continuous", i, 3)
                elif n == "been" and j + 1 < len(w) and w[j + 1] and is_pp(w[j + 1]):
                    fire("present-perfect", "present_perfect_simple", i, 3)
                    fire("passive", "passives_form", i, 3)
                elif is_pp(n):
                    fire("present-perfect", "present_perfect_simple", i, j - i + 1)
                elif k > j and m == "been" and k + 1 < len(w) and w[k + 1] and is_ing(w[k + 1]):
                    fire("present-perfect-continuous", "present_perfect_continuous", i, k - i + 2)
                elif k > j and m and is_pp(m):
                    fire("present-perfect", "present_perfect_simple", i, k - i + 1)
            elif t == "had" and n:
                k = after_subject(j)
                m = w[k] if k < len(w) else None
                if n == "to" and j + 1 < len(w) and w[j + 1]:
                    fire("modals-obligation", "have_got_to", i, 3)
                elif n == "been" and j + 1 < len(w) and w[j + 1] and is_ing(w[j + 1]):
                    fire("past-perfect-continuous", "past_perfect_continuous", i, 3)
                elif is_pp(n) and n != "to":
                    fire("past-perfect", "past_perfect_simple", i, j - i + 1)
                elif k > j and m and is_pp(m):
                    fire("past-perfect", "past_perfect_simple", i, k - i + 1)
            elif t in ("am", "is", "are") and n:
                k = after_subject(j)
                m = w[k] if k < len(w) else None
                if n == "there" and j + 1 < len(w) and w[j + 1] and (w[j + 1] in DET or w[j + 1] in ("any", "some", "no", "many", "much", "enough")):
                    fire("there-is-are", "there_isare", i, 3)
                elif n == "going" and j + 1 < len(w) and w[j + 1] == "to" and j + 2 < len(w) and w[j + 2] and w[j + 2] not in DET:
                    fire("future-will-going-to", "future_with_be_going_to", i, 4)
                elif is_ing(n):
                    fire("present-continuous", "present_continuous", i, j - i + 1)
                elif n == "being" and j + 1 < len(w) and w[j + 1] and is_pp(w[j + 1]):
                    fire("passive", "passives_form", i, 3)
                elif is_pp(n) and n not in ADJ_PARTICIPLE:
                    fire("passive", "passives_form", i, j - i + 1)
                elif k > j and m and is_ing(m):
                    fire("present-continuous", "present_continuous", i, k - i + 1)
                elif k > j and m and is_pp(m) and m not in ADJ_PARTICIPLE:
                    fire("passive", "passives_form", i, k - i + 1)
            elif t in ("was", "were") and n:
                k = after_subject(j)
                m = w[k] if k < len(w) else None
                if n == "there" and j + 1 < len(w) and w[j + 1] and (w[j + 1] in DET or w[j + 1] in ("any", "some", "no", "many", "much", "enough")):
                    fire("there-is-are", "there_isare", i, 3)
                elif is_ing(n):
                    fire("past-continuous", "past_continuous", i, j - i + 1)
                elif n == "being" and j + 1 < len(w) and w[j + 1] and is_pp(w[j + 1]):
                    fire("passive", "passives_form", i, 3)
                elif is_pp(n) and n not in ADJ_PARTICIPLE:
                    fire("passive", "passives_form", i, j - i + 1)
                elif k > j and m and is_ing(m):
                    fire("past-continuous", "past_continuous", i, k - i + 1)
                elif k > j and m and is_pp(m) and m not in ADJ_PARTICIPLE:
                    fire("passive", "passives_form", i, k - i + 1)
            elif t == "will" and n:
                if n == "have" and j + 1 < len(w) and w[j + 1] and is_pp(w[j + 1]):
                    fire("future-perfect", "future_perfect_simple", i, 3)
                elif n == "be" and j + 1 < len(w) and w[j + 1] and is_ing(w[j + 1]):
                    fire("future-continuous", "future_continuous", i, 3)
                elif (w[i - 1] if i > 0 else None) != "there":
                    fire("future-will-going-to", "future_simple_with_will_and_shall", i, 2)
            elif t in MODAL_FAMILY and t != "will" and n:
                if t == "would" and n == "like":
                    fire("would-like", "would", i, 2)
                elif t == "would" and n in PRON_SUBJ and (w[nextIdx(j)] if nextIdx(j) < len(w) else None) == "like":
                    fire("would-like", "would", i, 3)
                elif n == "have" and j + 1 < len(w) and w[j + 1] and is_pp(w[j + 1]):
                    fire("modals-past", MODAL_FAMILY[t], i, 3)
                elif t in ("can", "could"):
                    fire("modals-ability", MODAL_FAMILY[t], i, 2)
                elif t in ("must", "should"):
                    fire("modals-obligation", MODAL_FAMILY[t], i, 2)
                elif t in ("may", "might"):
                    fire("modals-deduction", MODAL_FAMILY[t], i, 2)
                elif t in ("shall", "would"):
                    fire("modals-ability", MODAL_FAMILY[t], i, 2)
            elif t == "ought" and n == "to":
                fire("modals-obligation", "ought", i, 2)
            elif t == "used" and n == "to" and (w[i - 1] if i > 0 else None) not in ("be", "is", "are", "was", "get"):
                fire("used-to", "used_to", i, 3)
            elif t == "there" and n and n in ("is", "are", "was", "were", "will", "has", "have"):
                fire("there-is-are", "there_isare", i, 2)
            elif t in ("wish", "wishes", "wished") and n:
                # FIX 6b -- family selection has to look at the COMPLEMENT's
                # own tense, not just the trigger word: "I wish I knew" is
                # simple past, "she wished she had brought her notes" is past
                # perfect, and this branch used to send both to past_simple.
                # marker is canonicalised to "wish" (not the inflected surface
                # form) because the EGP can-do prose that names this
                # construction always quotes the dictionary form -- see Fix 6
                # in _resolve_structure.
                k = after_subject(j)
                m = w[k] if k < len(w) else None
                if k > j and m == "had" and k + 1 < len(w) and is_pp(w[k + 1]):
                    fire("wish", "past_perfect_simple", i, 2, marker="wish", past=True, thematic_marker=True)
                else:
                    fire("wish", "past_simple", i, 2, marker="wish", past=True, thematic_marker=True)
            elif t == "if" and i + 1 < len(w) and w[i + 1] == "only":
                # FIX 6c -- "only" sits in SKIP, so nextIdx() always skips
                # past it when computing `n` above: `n == "only"` could never
                # be true, meaning this branch was dead code (confirmed
                # against the live LENS detector too -- same bug upstream,
                # not introduced by the port; see docs/23). Check the literal
                # next token instead of the SKIP-filtered one, since "if only"
                # is a fixed two-word collocation, not a case where an
                # intervening adverb should be skipped over.
                #
                # ctx.negative also needs its own look-ahead: fire()'s default
                # only checks a 3-token window centred on "if only" itself,
                # which never reaches a "not" sitting after the subject and
                # auxiliary ("if only she HAD NOT changed...").
                k = after_subject(i + 2)
                neg = k + 1 < len(w) and w[k + 1] == "not"
                fire("wish", "past_perfect_simple", i, 2, marker="if", past=True, negative=neg, thematic_marker=True)
            elif t in FREQ_ADV:
                fire("adverbs-of-frequency", "adverbs_and_adverb_phrases_types_and_meanings", i, 1)
            elif t in SUBORDINATORS and i > 0:
                fire("subordination", "subordinating", i, 2)
            elif t in SUBORDINATORS and i == 0 and "," in sentence and n and n not in (
                "did", "do", "does", "is", "are", "was", "were", "will", "can", "could",
                "should", "would", "have", "has", "had",
            ):
                fire("subordination", "subordinating", i, 2)
            elif t in ("although", "though", "whereas") and not (t == "though" and (w[i - 1] if i > 0 else None) == "even"):
                fire("concessive-clauses", "subordinating", i, 2)
            elif t == "even" and n == "though":
                fire("concessive-clauses", "subordinating", i, 2)
            elif t in ("who", "which", "whose") and i > 0 and w[i - 1] not in ("the", "a", "an"):
                fire("relative-clauses", "relative", i, 2)
            elif t.endswith("er") and len(t) > 4 and n == "than":
                fire("comparatives-superlatives", "comparatives", i, 2)
            elif t in ("more", "less") and (w[i + 2] if i + 2 < len(w) else None) == "than":
                fire("comparatives-superlatives", "comparatives", i, 3)
            elif t == "the" and n and (
                (n.endswith("est") and len(n) > 4 and not (pos_of(n)["noun"] if pos_of else False))
                or n == "most"
            ):
                fire("comparatives-superlatives", "superlatives", i, 3 if n == "most" else 2)
            elif t in ("neither", "either") and (("nor" if t == "neither" else "or") in w[i + 1:i + 8]):
                fire("coordinating-conjunctions", "coordinated", i, 4)
            elif t == "as" and (w[i + 1] if i + 1 < len(w) else None) and (w[i + 2] if i + 2 < len(w) else None) == "as" and w[i + 1] not in (
                "well", "long", "soon", "far", "such", "much", "many",
            ):
                fire("comparatives-superlatives", "comparatives", i, 3)
            i += 1

        # ---- baseline tenses, high-precision subset ----
        # is_third_s/is_past_form/is_bare_verb/is_singular_noun/
        # is_proper_noun_subject are module-level now (Task 0, docs/29) --
        # pos_of/orig/w passed explicitly at each call site below.

        for i in range(len(w)):
            if inverted and in_inverted(i):
                continue
            cands = []
            if w[i] in SUBJ_PRON_ANY:
                cands.append({"v": nextIdx(i), "third": w[i] in SUBJ_PRON_3SG,
                              "strict": False, "bare": w[i] in SUBJ_PRON_BARE})
            elif w[i] in SING_DET and pos_of:
                if i + 1 < len(w) and is_singular_noun(w[i + 1], pos_of):
                    cands.append({"v": i + 2, "third": True, "strict": True, "bare": False})
                if i + 2 < len(w) and is_singular_noun(w[i + 2], pos_of):
                    cands.append({"v": i + 3, "third": True, "strict": True, "bare": False})
            elif is_proper_noun_subject(orig, w, i, pos_of):
                cands.append({"v": nextIdx(i), "third": True, "strict": False, "bare": False})

            for c in cands:
                verb = w[c["v"]] if c["v"] < len(w) else None
                if not verb:
                    continue
                if c["strict"] and w[c["v"] - 1] in SUBJ_PRON_ANY:
                    continue
                if c["third"] and is_third_s(verb, c["strict"], pos_of):
                    fire("present-simple", "present_simple", i, c["v"] - i + 1, past=False, marker=None)
                    break
                if c["bare"] and is_bare_verb(verb, pos_of):
                    fire("present-simple", "present_simple", i, c["v"] - i + 1, past=False, marker=None)
                    break
                if is_past_form(verb, pos_of):
                    fire("past-simple", "past_simple", i, c["v"] - i + 1, past=True, marker=None)
                    break

        # C3b -- near-miss bookkeeping
        for i in range(len(w)):
            if "present-simple" not in sent_fired:
                if w[i] in SING_DET and pos_of and pos_of(w[i + 1] if i + 1 < len(w) else "")["noun"] and is_bare_verb(w[i + 2] if i + 2 < len(w) else None, pos_of):
                    partial_relevant.add("present-simple")
                if w[i] in ("do", "does") and any(is_bare_verb(x, pos_of) for x in w[i + 1:i + 4]):
                    partial_relevant.add("present-simple")
            if "past-simple" not in sent_fired and w[i].endswith("ed") and w[i] in ADJ_PARTICIPLE:
                partial_relevant.add("past-simple")

        # sentence-level patterns (token-joined string)
        ts = " ".join(w)
        rep = re.search(
            r"\b(said|says|told (?:me|us|him|her|them)|asked|explained|added|claimed|wondered)"
            r"(?: that| if| whether)? (?:i|you|he|she|it|we|they|there)\b", ts)
        if rep:
            add("reported-speech", "reported_speech", rep.group(0)[:30], FireCtx(window=ts))
            sent_fired.add("reported-speech")

        tag_m = re.search(
            r",\s*(is|are|was|were|do|does|did|have|has|had|will|would|can|could|should|must)"
            r"( not)? (i|you|he|she|it|we|they)\s*[?]", low)
        if tag_m:
            add("question-tags", "tags", re.sub(r"^,\s*", "", tag_m.group(0)).strip())
            sent_fired.add("question-tags")

        reported_if = bool(re.search(r"\b(asked?|asks|wonder(?:ed|s)?|know|knows|knew|see|check(?:ed)?|sure) (?:if|whether)\b", ts))
        if re.search(r"\bif\b", low) and not re.search(r"\bif only\b", low) and not reported_if:
            if_m = re.search(r"\bif\b[^,.?!;]*", low)
            if_span = " ".join(((if_m.group(0) if if_m else "if").strip().split())[:6])
            if re.search(r"\b(would|could|might) (have\s+)?\w+", low):
                # FIX 6d -- past=True: second/third conditionals are
                # inherently past-shifted ("if" + past simple/perfect), so
                # the second/third-conditional rows' own guideword PAST
                # mentions should count as evidence, not go unscored. Real
                # (zero/first) conditionals below are NOT past-shifted, so
                # that branch is left alone.
                add("conditionals-unreal", "conditional", if_span, FireCtx(variant="unreal", marker="if", past=True, window=ts))
                sent_fired.add("conditionals-unreal")
            else:
                add("conditionals-real", "conditional", if_span, FireCtx(variant="real", marker="if", window=ts))
                sent_fired.add("conditionals-real")

        that_comp = bool(re.search(
            r"\b(said|says|know|knows|knew|think|thinks|thought|believe|believes|establish|"
            r"establishes|established|means|shows|showed|hopes|hoped|agree|agrees|agreed|"
            r"confirm|confirms|confirmed) that\b", ts))

        def has_verb_near(frm, span):
            for k in range(frm, min(len(w), frm + span)):
                t2 = w[k]
                if not t2:
                    continue
                if t2 in AUX_OR_MODAL:
                    return True
                if t2 in IRREG_PAST:
                    return True
                if pos_of and pos_of(t2)["verb"]:
                    return True
                if re.search(r"(?:ed|ing|s)$", t2) and pos_of and pos_of(t2)["verb"]:
                    return True
            return False

        AMBIGUOUS_SUBORDINATORS = set("as before after since once though although".split())
        clause_subordination = False
        for i in range(len(w)):
            if w[i] not in AMBIGUOUS_SUBORDINATORS:
                continue
            nx = w[i + 1] if i + 1 < len(w) else None
            if not nx:
                continue
            if nx in PRON_SUBJ and has_verb_near(i + 2, 2):
                clause_subordination = True
                break

        clause_coord_wide = False
        for i in range(1, len(w) - 1):
            if w[i] not in ("and", "but", "or", "so", "yet"):
                continue
            if has_verb_near(i + 1, 5):
                clause_coord_wide = True
                break

        that_relative = False
        for i in range(1, len(w) - 1):
            if w[i] != "that":
                continue
            prev = w[i - 1] if i > 0 else None
            if not prev or not pos_of or not pos_of(prev)["noun"]:
                continue
            info = pos_of(prev)
            if info["verb"] and not info["noun"]:
                continue
            if has_verb_near(i + 1, 3):
                that_relative = True
                break
        if that_relative:
            ti = w.index("that")
            span = " ".join([x for x in [w[ti], w[ti + 1] if ti + 1 < len(w) else None] if x])
            add("relative-clauses", "relative", span, FireCtx(marker="that", window=ts))
            sent_fired.add("relative-clauses")

        vp_coord = any(
            w[i] in ("and", "but", "or") and i + 1 < len(w) and w[i + 1]
            and (w[i + 1] in IRREG_PAST or (w[i + 1].endswith("ed") and len(w[i + 1]) > 3))
            for i in range(len(w))
        )
        coord_m = CLAUSE_COORD.search(sentence)
        vp_idx = -1
        for i in range(len(w)):
            if w[i] in ("and", "but", "or") and i + 1 < len(w) and w[i + 1] and (
                w[i + 1] in IRREG_PAST or (w[i + 1].endswith("ed") and len(w[i + 1]) > 3)
            ):
                vp_idx = i
                break
        coord = bool(coord_m) or vp_coord or clause_coord_wide or "coordinating-conjunctions" in sent_fired
        if coord:
            if coord_m:
                span = re.sub(r"^,\s*", "", coord_m.group(0)).strip()
            elif vp_idx >= 0:
                span = " ".join(w[vp_idx:vp_idx + 2])
            else:
                span = "and"
            add("coordinating-conjunctions", "coordinating", span, FireCtx(window=ts))
            sent_fired.add("coordinating-conjunctions")

        sub = that_comp or clause_subordination or that_relative or any(
            id_ in SUBORDINATE_STRUCTS for id_ in sent_fired
        )
        per_sentence.append({"subordination": sub, "coordination": coord})

    # PASS 2 -- LEVELLING. Maps Pass 1's raw evidence onto an EGP row/level
    # per hit, via the (now gate-fixed, Fix 6) resolver.
    detected = sorted(_level_evidence(hits.values()), key=lambda d: (-d["level_num"], d["name"]))
    return {
        "detected": detected,
        "per_sentence": per_sentence,
        "coverage": {
            "detected_types": len({d["explorer_id"] for d in detected}),
            "total_types": 45,
            "deferred": DEFERRED,
            "partial": [p for p in PARTIAL if p["id"] in partial_relevant],
        },
    }


def derive_clause_type(sig):
    """Derived clause classification (2.3): from the structures that fired --
    one detector, one truth."""
    if sig["subordination"] and sig["coordination"]:
        return "Compound-Complex"
    if sig["subordination"]:
        return "Complex"
    if sig["coordination"]:
        return "Compound"
    return "Simple"
