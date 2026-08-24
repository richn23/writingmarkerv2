"""
Port of LENS's `src/lib/egpFamilies.ts`. Single source of truth for which EGP
families each Structure Explorer heading covers.

`structures.json` OWNS the coverage claim. This module resolves family ids to
EGP rows and asserts, at import time, that every family `detect.py` can fire
is declared there. A disagreement raises -- which fails to import, the same
"the build breaks" discipline `assertDetectorFamilies` gives the TS original
(there is no `next build` here, so import time is where that check has to
live).

Read-only port. Nothing here calls into api/_engine or api/_intent.
"""

import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "_data")

with open(os.path.join(_DATA, "grammar_profile.json"), encoding="utf-8") as fh:
    _GP = json.load(fh)
with open(os.path.join(_DATA, "structures.json"), encoding="utf-8") as fh:
    _STRUCTURES_DATA = json.load(fh)

EGP = _GP["structures"]
EXPLORER_STRUCTURES = _STRUCTURES_DATA["structures"]

# CEFR half-band ordering. A local copy, not a reuse of `_engine`'s GSE_BANDS --
# that scale runs over GSE points (0-100); this one is EGP's own six-band scale
# with half-bands, ported verbatim from lib/taxonomy.ts's BAND_NUM.
_BAND_NUM = {
    "pre-a1": 0.5, "<a1": 0.5, "a1": 1, "a1+": 1.5, "a2": 2, "a2+": 2.5,
    "b1": 3, "b1+": 3.5, "b2": 4, "b2+": 4.5, "c1": 5, "c1+": 5.5, "c2": 6,
    "n/a": 1,
}


def level_num(raw):
    return _BAND_NUM.get((raw or "").strip().lower(), 1)


def norm_key(s):
    """Family ids are the EGP category name with non-alphanumerics collapsed.
    Mechanical, so a new family needs no table entry -- "passives: form" <->
    `passives_form` falls out of it."""
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower())
    return s.strip("_")


# The only two ids normalisation cannot derive, kept as data rather than logic.
_IRREGULAR_ID = {
    "yesno": "yes_no",             # EGP "yes/no"
    "there_isare": "there_is_are",  # EGP "there is/are"
}

# index EGP rows under both `sub` and `super__sub`, so a family id can
# disambiguate when a sub_category name is shared.
_BY_SUB = {}
_BY_SUP_SUB = {}
for _row in EGP:
    _sub = norm_key(_row.get("sub_category") or "")
    _sup_sub = "%s__%s" % (norm_key(_row.get("super_category") or ""), _sub)
    _BY_SUB.setdefault(_sub, []).append(_row)
    _BY_SUP_SUB.setdefault(_sup_sub, []).append(_row)


def rows_for_family(family_id):
    """EGP rows for a family id, lowest level first. Empty list = unresolvable
    id. `super__sub` is split BEFORE normalising -- normalising the whole id
    would collapse the "__" separator into "_" and destroy the distinction it
    exists to make."""
    raw = _IRREGULAR_ID.get(family_id, family_id)
    parts = raw.split("__")
    if len(parts) > 1:
        key = "%s__%s" % (norm_key(parts[0]), norm_key("__".join(parts[1:])))
    else:
        key = norm_key(raw)
    rows = _BY_SUP_SUB.get(key) or _BY_SUB.get(key) or []
    return sorted(rows, key=lambda r: level_num(r.get("level")))


# explorer heading id -> the families it declares, straight from structures.json.
DECLARED_FAMILIES = {s["id"]: (s.get("egp_families") or []) for s in EXPLORER_STRUCTURES}

# Every family id any heading declares. The detector builds its lookup from
# this, so it cannot reach a family the Explorer does not also show.
ALL_DECLARED_FAMILIES = sorted({
    f for s in EXPLORER_STRUCTURES for f in (s.get("egp_families") or [])
})


def assert_detector_families(table):
    """Import-time assertion. `table` is what detect.py claims it can fire.
    Every pair must be declared in structures.json, and every family id must
    resolve to at least one EGP row. Raises with the full disagreement list
    rather than the first one -- a partial report would just hide the next
    seven."""
    problems = []
    for explorer_id, families in table.items():
        declared = DECLARED_FAMILIES.get(explorer_id)
        if declared is None:
            problems.append('"%s" fires in the detector but is not a heading in structures.json' % explorer_id)
            continue
        for f in families:
            if f not in declared:
                problems.append('"%s" fires family "%s" but structures.json does not declare it' % (explorer_id, f))
            if not rows_for_family(f):
                problems.append('family "%s" (on "%s") resolves to zero EGP rows' % (f, explorer_id))
    for f in ALL_DECLARED_FAMILIES:
        if not rows_for_family(f):
            problems.append('family "%s" is declared in structures.json but resolves to zero EGP rows' % f)
    if problems:
        raise RuntimeError(
            "EGP family keys disagree between structures.json and detect.py (%d problem%s):\n  - %s"
            % (len(problems), "" if len(problems) == 1 else "s", "\n  - ".join(problems))
        )


# Family-level description, hand-authored in structures.json, one per heading.
# Used where a row-level EGP can-do has to be withheld.
SHORT_DESCRIPTION = {
    s["id"]: s["overview"]["short_description"]
    for s in EXPLORER_STRUCTURES
    if s.get("overview", {}).get("short_description")
}
