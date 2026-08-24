"""
Port of LENS's `makePosLookup` (src/lib/analysis.ts:1432-1462).

LENS builds this from its own Pearson GSE index. This project already loads
the SAME Pearson dataset -- confirmed by reading both files directly:
`api/_data/gse_vocabulary.json`'s `total_entries` (34795) and first record
match LENS's `pearson_gse_vocabulary.json` exactly; LENS's copy just retains
extra fields (example/topics/audience) this project's copy dropped. So this
reuses `_engine.gse.GseBank` and `_engine.lemmas.lemma_candidates` rather than
porting a second copy of the vocabulary index -- read-only imports, same as
`_intent/layer.py` already does. Nothing in `_engine/` is modified.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from _engine.lemmas import lemma_candidates  # noqa: E402


def _is_verb_sense(entry):
    """Exact tag membership, same rule as taxonomy.ts's hasTag: split on ';',
    compare atoms, never substring-match. `GseBank.categories()` already
    implements this for the general case; this is the two-tag union
    (verb-or-phrasal-verb) makePosLookup's isVerbSense needs."""
    cat = (entry.get("grammatical_category") or "").lower()
    atoms = [a.strip() for a in cat.split(";")]
    return "verb" in atoms or "phrasal verb" in atoms


def _is_noun_sense(entry):
    cat = (entry.get("grammatical_category") or "").lower()
    return "noun" in [a.strip() for a in cat.split(";")]


def make_pos_lookup(bank):
    """Returns pos_of(surface) -> {verb, noun, known, surface_verb, verb_dominant}.

    `verb`/`verb_dominant` walk the lemma chain, exactly as LENS's version
    does: unlike `GseBank.resolve()` (which stops at the FIRST candidate that
    has ANY senses), this keeps walking past a candidate that resolves but
    carries no verb sense, because a lemma collapsing to a non-verb word must
    not block a later candidate that IS a verb. `noun`/`known`/`surface_verb`
    read the SURFACE form's own senses only, never the lemma-walked one.
    """
    cache = {}

    def pos_of(surface):
        key = surface.lower()
        hit = cache.get(key)
        if hit is not None:
            return hit

        surface_senses = bank.index.get(key)
        verb = False
        verb_dominant = False
        for cand in lemma_candidates(key):
            senses = bank.index.get(cand)
            if not senses or not any(_is_verb_sense(s) for s in senses):
                continue  # keep walking the lemma chain
            verb = True
            verb_count = sum(1 for s in senses if _is_verb_sense(s))
            noun_count = sum(1 for s in senses if _is_noun_sense(s))
            verb_dominant = verb_count > noun_count
            break

        out = {
            "verb": verb,
            "verb_dominant": verb_dominant,
            "noun": bool(surface_senses) and any(_is_noun_sense(s) for s in surface_senses),
            "known": bool(surface_senses),
            "surface_verb": bool(surface_senses) and any(_is_verb_sense(s) for s in surface_senses),
        }
        cache[key] = out
        return out

    return pos_of
