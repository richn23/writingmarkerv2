"""
Tokenisation and the four profile views.

Views produced for BOTH the original and the corrected version of a script:
  1. full             -- every word token, with its level
  2. content_only     -- function words stripped out
  3. distinct         -- repetition removed (distinct word types, not tokens)
  4. summary          -- how many DISTINCT words sit at each CEFR band

Nothing here computes a single headline score. The output is a description of the
text, not a judgement of it.
"""

import re
from collections import Counter, OrderedDict

from .gse import COARSE_ORDER, band_for_gse

# Function words: pronouns, prepositions, determiners, auxiliaries, conjunctions.
# An explicit list, not a part-of-speech guess -- "content word" has to mean the
# same thing in every view or the comparison is meaningless.
FUNCTION_WORDS = set("""
a an the this that these those my your his her its our their some any no every each
all both another either neither such what which whose
i you he she it we they me him us them mine yours hers ours theirs
myself yourself himself herself itself ourselves yourselves themselves
who whom somebody someone something anybody anyone anything nobody nothing
everybody everyone everything one ones
in on at from to with by for of as about into onto over under between among
through during above below across behind beyond within without against toward
towards upon off out up down near past per via than
and but or nor yet so because if when although though while since unless until
whereas whether
be am is are was were been being have has had having do does did doing
will would shall should can could may might must ought need dare
not there here too very just then
""".split())

_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def tokenize(text):
    """Word tokens with their position, original casing preserved."""
    out = []
    for m in _TOKEN.finditer(text):
        raw = m.group(0)
        out.append({
            "raw": raw,
            "lower": raw.lower().replace("'", ""),
            "start": m.start(),
            "end": m.end(),
        })
    return out


def build_profile(tokens, bank):
    """Attach a GSE match record to every token, then build the four views."""
    records = []
    for t in tokens:
        rec = bank.describe(t["lower"])
        rec["raw"] = t["raw"]
        rec["is_function_word"] = t["lower"] in FUNCTION_WORDS
        # How sure we are this is the word the student meant. 1.0 when nothing
        # was changed; the correction's own score when it was.
        rec["confidence"] = t.get("confidence", 1.0)
        records.append(rec)

    content = [r for r in records if not r["is_function_word"]]

    # Distinct = distinct matched form where we have one, else the surface token.
    # Keyed on the lemma so "study"/"studies" count once, which is what a
    # vocabulary-range question actually asks.
    distinct = OrderedDict()
    for r in content:
        key = r["matched_form"] or r["token"]
        if key not in distinct:
            distinct[key] = r
        elif r.get("confidence", 1.0) > distinct[key].get("confidence", 1.0):
            # The same word can arrive by different routes -- written correctly
            # in one sentence and corrected into existence in another. Take the
            # best evidence we have for it.
            distinct[key] = r

    return {
        "full": records,
        "content_only": content,
        "distinct": list(distinct.values()),
        "summary": _summary(list(distinct.values())),
        "counts": {
            "tokens": len(records),
            "content_tokens": len(content),
            "distinct_content_words": len(distinct),
            "matched": sum(1 for r in records if r["matched"]),
            "unmatched": sum(1 for r in records if not r["matched"]),
            "content_matched": sum(1 for r in content if r["matched"]),
            "content_unmatched": sum(1 for r in content if not r["matched"]),
        },
    }


def _summary(distinct_records):
    """Distinct words per coarse CEFR band, plus an 'unmatched' bucket."""
    counts = Counter()
    for r in distinct_records:
        counts[r["coarse"] if r["matched"] else "unmatched"] += 1
    rows = []
    for band in COARSE_ORDER + ["unmatched"]:
        if counts.get(band):
            rows.append({"band": band, "count": counts[band]})
    total = sum(c["count"] for c in rows) or 1
    for r in rows:
        r["pct"] = round(100.0 * r["count"] / total, 1)
    return rows


def level_measures(distinct_records):
    """
    Three readings of the same distinct-word list, because a single "highest
    band" is set by one token and moves the moment that token is corrected,
    mis-corrected, or turns out to be a proper noun. The percentile and the
    count are far steadier, and across a batch they separate levels that the
    ceiling cannot -- on the first real batch every script from B1 upwards
    reported a highest band of C1.
    """
    scores = sorted(r["gse"] for r in distinct_records
                    if r["matched"] and r["gse"] is not None)
    if not scores:
        return {"median_gse": None, "median_band": None,
                "p90_gse": None, "p90_band": None, "above_b1": 0, "scored": 0}

    def pct(p):
        i = min(len(scores) - 1, int(round((len(scores) - 1) * p)))
        return scores[i]

    med, p90 = pct(0.5), pct(0.9)
    return {
        "median_gse": med, "median_band": band_for_gse(med),
        "p90_gse": p90, "p90_band": band_for_gse(p90),
        "above_b1": sum(1 for g in scores if g >= 59),   # B2 and above
        "scored": len(scores),
    }


def highest_band(distinct_records):
    """Highest band reached, and the words that reach it. Reported, not scored."""
    best, words = None, []
    order = {b: i for i, b in enumerate(COARSE_ORDER) if b != "N/A"}
    for r in distinct_records:
        if not r["matched"] or r["coarse"] not in order:
            continue
        if best is None or order[r["coarse"]] > order[best]:
            best, words = r["coarse"], [r["matched_form"] or r["token"]]
        elif r["coarse"] == best:
            words.append(r["matched_form"] or r["token"])
    return {"band": best, "words": sorted(set(words))}
