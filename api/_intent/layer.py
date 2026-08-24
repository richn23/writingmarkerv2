"""
Orchestration: pick the tokens, ask, validate, and build the fourth reading.

The three deterministic readings are untouched -- this module only ever reads
them. `intent` is built on top of `lenient` by applying the proposals that
survived validation, so the spread between `original` and `intent` is the honest
statement of how much of a score depends on reading through the spelling.
"""

import hashlib
import json
import re

from _engine.analyse import _resummarise                        # noqa: E402
from _engine.scoring import score as score_profile              # noqa: E402
from _engine.scoring import CREDIBLE_MIN                        # noqa: E402
from _engine.spelling import (joinable_pairs,                   # noqa: E402
                              proper_noun_candidates,
                              suspicious_real_words)
from _engine.gse import clean_band                              # noqa: E402
from _engine.scoring import band_for_gse                        # noqa: E402
from _engine.views import (FUNCTION_WORDS, build_profile,       # noqa: E402
                           highest_band, level_measures, tokenize)

from . import client, review, spelling_score, vocab_fit


B2_PLUS_GSE = 59        # B2 starts at 59 on the assessment bands

READINGS = ("original", "cautious", "lenient", "intent")


class IncompleteResult(AssertionError):
    """A valid script came back with a reading or a score missing."""


def assert_complete(result, intent_expected):
    """
    COMPLETENESS INVARIANT. Every valid script produces every reading.

    This exists because the failure it catches was silent AND biased toward the
    scripts we are surest about: a script clean enough that no token needed a
    second reading returned early, and 34 of 100 got no score at all. Nothing
    errored, nothing logged, and the missing ones were the well-spelled ones.

    A partial result must not be returned. `intent` is exempt only when the
    layer genuinely could not run -- and in that case the absence is stamped on
    the record, never inferred.
    """
    if not result.get("valid"):
        return                      # noise legitimately has no level
    name = result.get("name", "?")
    missing, empty = [], []
    for r in READINGS:
        if r == "intent" and not intent_expected:
            continue
        prof = result.get(r)
        if not isinstance(prof, dict) or "score" not in prof:
            missing.append(r)
        elif not prof.get("full"):
            empty.append(r)
    # Both scores are computed in the same pass as the intent reading, so they
    # are only required when that pass ran. When it did not, the absence is
    # visible in reference.intent.available -- not inferred from a blank.
    absent = ([k for k in ("vocabulary_score", "spelling_score")
               if not isinstance(result.get(k), dict)] if intent_expected else [])
    if missing or empty or absent:
        raise IncompleteResult(
            "script %r is valid but incomplete: missing readings %s; empty "
            "readings %s; missing scores %s. Present: %s. intent_expected=%s, "
            "note=%r" % (name, missing or "none", empty or "none",
                         absent or "none",
                         [r for r in READINGS if isinstance(result.get(r), dict)],
                         intent_expected, result.get("intent_note")))


def vocabulary_features(result):
    """
    SCORE 1. The 0-100 now comes from `vocab_fit`, which carries two mappings --
    the refit (default) and the original calibrated one, selectable by
    VOCAB_SCORE_MODEL. Both are always computed: `legacy_score` sits alongside
    `score` on every result so the two can be compared on any batch without
    re-running anything.

    Every feature the fit could use is exposed here regardless of which mapping
    is active, so a future refit needs no changes outside `vocab_fit`.

    `reading` is stamped on every result. A script must not score differently
    depending on whether an API was reachable, and if it does, the record has to
    say which reading produced the number.
    """
    prof = result.get("intent") or result["lenient"]
    reading = "intent" if result.get("intent") else "lenient"
    sc, lv = prof["score"], prof.get("levels") or {}
    distinct = prof["distinct"]
    matched = [r for r in distinct if r.get("matched") and r.get("gse") is not None]
    cov = (result.get("coverage") or {}).get("coverage")
    legacy = sc["confident"]["score"] if sc["assigned"] else None
    base = {
        "reading": reading,
        "assigned": sc["assigned"],
        "credible_words": sc["credible_count"],
        "distinct_gse_matched": len(matched),
        "words_at_b2_plus": sum(1 for r in matched if r["gse"] >= B2_PLUS_GSE),
        "p80_gse": sc["confident"]["gse"] if sc["assigned"] else None,
    }
    score, provenance = vocab_fit.apply(base, legacy)
    return {
        "reading": reading,
        "assigned": sc["assigned"],
        "score": score,
        "score_model": provenance,
        "legacy_score": legacy,
        "refit_score": provenance.get("refit_score"),
        "band": sc["confident"]["band"] if sc["assigned"] else None,
        "credible_words": sc["credible_count"],
        "distinct_gse_matched": len(matched),
        "words_at_b2_plus": sum(1 for r in matched if r["gse"] >= B2_PLUS_GSE),
        "total_words": prof["counts"]["tokens"],
        "content_words": prof["counts"]["content_tokens"],
        "p80_gse": sc["confident"]["gse"] if sc["assigned"] else None,
        "p90_gse": sc["upper"]["gse"] if sc["assigned"] else None,
        "median_gse": lv.get("median_gse"),
        "coverage": cov,
        "composite_confidence": sc["confidence"]["composite"],
    }

MAX_TOKENS_PER_SCRIPT = 24      # a script needing more than this is noise


# ---------------------------------------------------------------------------
# 1. Which tokens get asked about
# ---------------------------------------------------------------------------

def flag(text, result, bank, corrector):
    """
    The two candidate sets, each already singled out by the engine:

      1. non-words it abstained on         (sophi, intead)
      2. suspicious real words             (bast, hared)

    Anything outside this set is never shown to the model, so it structurally
    cannot be changed.
    """
    toks = tokenize(text)
    where = {}
    for t in toks:
        where.setdefault(t["lower"], t)

    items, seen = [], set()

    for row in result["audit"]["lenient"]:
        w = row["original"]
        if w in seen or w not in where:
            continue
        abstained = row["decision"] == "abstained" and not row.get("corrected")
        # A correction the grammar tie-break settled is uncertain by
        # construction -- letters and sound could not separate the readings, so
        # something that can read the sentence should have the final word. This
        # is what lets the interpretation override `shoud`->`shoed` with
        # `should`, rather than the tie-break's answer standing unchallenged.
        settled = bool(row.get("slot_settled"))
        if not (abstained or settled):
            continue
        seen.add(w)
        items.append({
            "token": w,
            "sentence": review.sentence_for(text, where[w]["start"],
                                            where[w]["end"]),
            "why": ("read mechanically as '%s', but only by breaking a tie on "
                    "grammar -- confirm or correct it" % row.get("corrected")
                    if settled else
                    "not an English word; the corrector abstained (%s)"
                    % (row.get("reason") or "no confident candidate")),
            "real_word": False,
        })

    # PROPER NOUNS. The corrector turns a name into a reference word and it is
    # then counted as vocabulary the student demonstrated -- `Bodrum` ->
    # `bedroom`, `Afnan` -> `avian`. The corrector's answer is withheld until the
    # interpretation says whether it is a name or a misspelling.
    names_maybe = proper_noun_candidates(text, toks)
    for w, why in sorted(names_maybe.items()):
        if w in seen or w not in where:
            continue
        seen.add(w)
        items.append({
            "token": w,
            "sentence": review.sentence_for(text, where[w]["start"],
                                            where[w]["end"]),
            "why": "%s -- say `proper_noun` if it is a name" % why,
            "real_word": False,
        })

    # WEAK CORRECTIONS. A correction below CREDIBLE_MIN never counted toward the
    # level, but it was still applied to the good-spelling version and shown as
    # done. Several are right (`indivisual` -> `individual` at 0.57), so the
    # answer is not to drop them but to get them confirmed properly.
    for row in result["audit"]["lenient"]:
        w = row["original"]
        if w in seen or w not in where:
            continue
        if row["decision"] not in ("corrected", "split") or not row.get("corrected"):
            continue
        if row["confidence"] >= CREDIBLE_MIN:
            continue
        seen.add(w)
        items.append({
            "token": w,
            "sentence": review.sentence_for(text, where[w]["start"],
                                            where[w]["end"]),
            "why": "read mechanically as '%s' but only at confidence %.2f, below "
                   "the %.2f bar -- confirm or correct it"
                   % (row["corrected"], row["confidence"], CREDIBLE_MIN),
            "real_word": False,
        })

    # JUNK IS A VERDICT, NOT A FACT. The noise detector is statistical: `byby`
    # trips "only 2 different letters", the same rule that catches `rgrg`, and
    # junk is never corrected AND never asked about -- so a real attempt
    # misread as noise was unrecoverable. The corrector would have resolved it
    # (baby 0.90 against by 0.70) if it had been allowed to look.
    #
    # So junk gets a second opinion too. If the interpretation recovers a word
    # and the form gates accept it, it was never noise; if it cannot, the
    # verdict stands and nothing is scored.
    for j in result["junk"]:
        w = j["token"]
        if w in seen or w not in where or not w.isalpha() or len(w) < 3:
            continue
        seen.add(w)
        items.append({
            "token": w,
            "sentence": review.sentence_for(text, where[w]["start"],
                                            where[w]["end"]),
            "why": "the noise detector rejected this as not-language (%s) -- say "
                   "if it is actually an attempt at a word" % j["why"],
            "real_word": False,
        })

    for s in suspicious_real_words(toks, result["original"]["distinct"],
                                   bank, corrector):
        w = s["token"]
        if w in seen or w not in where:
            continue
        seen.add(w)
        items.append({
            "token": w,
            "sentence": review.sentence_for(text, where[w]["start"],
                                            where[w]["end"]),
            "why": "a real word, but under suspicion: %s" % s["reason"],
            "real_word": True,
        })

    # The error that lives BETWEEN two tokens. Both halves are real words, so
    # nothing else in the pipeline can see it -- and left alone "play grand"
    # credits a Pre-A1 script with "grand" at B1+.
    joins = []
    for pr in joinable_pairs(toks, result["original"]["distinct"], bank, corrector):
        if pr["written"] in seen:
            continue
        seen.add(pr["written"])
        joins.append({
            "token": pr["written"],
            "sentence": review.sentence_for(text, pr["start"], pr["end"]),
            "why": "two words that may be one: %s" % pr["reason"],
            "real_word": True,
            "pair": pr,
        })

    return (items + joins)[:MAX_TOKENS_PER_SCRIPT]


# ---------------------------------------------------------------------------
# Multi-word lexical units
#
# `gse_vocabulary.json` carries 6,109 levelled multi-word entries -- phrasal
# verbs, fixed phrases, compound nouns -- which GseBank loads into
# `bank.multi_word` and then excludes from matching. gse.py's own docstring says
# why: matching phrases in running text is a separate problem, and doing it
# inside the bank would change every per-token `knows()`/`resolve()` call the
# spelling corrector makes. So it happens here instead, on the corrected stream,
# after the corrector has finished.
#
# WHAT A MATCH DOES. The same thing an accepted join already does: the unit
# replaces its constituent tokens in the stream, so `task force` reaches the
# scorer as one B2+ item and `task` and `force` never arrive separately. That is
# not a new convention -- `corrected_sample()` has collapsed spans this way for
# joins since it was written -- and it is what stops a span being counted twice.
#
# WHAT IS DELIBERATELY LEFT OUT of this first pass:
#
#   * Entries carrying punctuation -- `get off!`, `I abhor...`,
#     `if it's any comfort (to you)`. 1,091 of the 6,109. They are not plain
#     word sequences and cannot be matched as stored.
#   * Any phrase containing a function word, unless it is allowlisted below.
#     This is the guard that matters. `the sick` is a real B2+ entry meaning
#     "people who are ill", and without the guard it fires inside "the sick man
#     went home" and credits B2+ for an A2 construction. Over-crediting is worse
#     than the under-crediting we have today, because the whole engine is built
#     to refuse levels it cannot evidence.
#   * Inflection inside the phrase. The entries store literal strings, no lemma
#     field, so `paid up` will not match `pay up`. Generating inflected variants
#     would multiply the false-positive surface; not in a first pass.
#
# The guard costs real coverage: 1,778 of the 6,109 entries are active, and most
# phrasal verbs are excluded because their particles are function words. That is
# the conservative direction on purpose. `go out` spans GSE 19-65 across seven
# senses, and crediting it on a bare particle match would be a guess.

# Phrases worth crediting despite containing a function word. Kept short and
# explicit: each one has to earn its place by being common, unambiguous, and
# wrong under the current single-word scoring.
#
# `a lot` is the founding case. Today it scores as `a` plus `lot`, and `lot`
# alone resolves to its lowest single-word sense at GSE 50 (B1) -- so the
# commonest low-level quantifier in the language credits as a mid-level word.
# As a unit it is GSE 26, A1.
_PHRASE_ALLOW = {"a lot"}

_PUNCT_IN_PHRASE = re.compile(r"[()!?/,.']")


def _phrase_eligible(phrase):
    """Whether a reference phrase may be matched against running text."""
    if _PUNCT_IN_PHRASE.search(phrase):
        return False
    words = phrase.split()
    if len(words) < 2:
        return False
    if phrase in _PHRASE_ALLOW:
        return True
    return all(w not in FUNCTION_WORDS for w in words)


def _phrase_index(bank):
    """
    {phrase: lowest-GSE sense} for every eligible multi-word entry, plus the
    longest phrase length so the scan knows how far to look ahead.

    Cached on the bank, which is built once per warm instance.
    """
    cached = getattr(bank, "_mw_index", None)
    if cached is not None:
        return cached
    by_phrase = {}
    for e in bank.multi_word:
        phrase = (e.get("word") or "").strip().lower()
        if not _phrase_eligible(phrase):
            continue
        by_phrase.setdefault(phrase, []).append(e)
    index = {}
    for phrase, senses in by_phrase.items():
        # Lowest sense wins, exactly as it does for single words: `take off`
        # spans GSE 22-67 and awarding the top of that on a bare string match
        # would credit a level the text does not evidence.
        primary = bank._primary(senses)
        if isinstance(primary.get("gse"), (int, float)):
            index[phrase] = primary
    longest = max((len(p.split()) for p in index), default=0)
    out = (index, longest)
    setattr(bank, "_mw_index", out)
    return out


def _merge_phrases(stream, bank):
    """
    Collapse every eligible multi-word unit in the stream into one entry.

    Longest match wins, so `a whole lot` beats `a lot`. Junk tokens never take
    part -- a span containing noise is not a lexical unit.
    """
    index, longest = _phrase_index(bank)
    if not index:
        return stream
    out, i, n = [], 0, len(stream)
    while i < n:
        hit = None
        for size in range(min(longest, n - i), 1, -1):
            span = stream[i:i + size]
            if any(t.get("junk") for t in span):
                continue
            phrase = " ".join(t["lower"] for t in span)
            sense = index.get(phrase)
            if sense is not None:
                hit = (size, phrase, sense, span)
                break
        if hit is None:
            out.append(stream[i])
            i += 1
            continue
        size, phrase, sense, span = hit
        out.append({
            "raw": " ".join(t["raw"] for t in span),
            "lower": phrase,
            # The unit is only as trustworthy as its least trustworthy token.
            "confidence": min(t.get("confidence", 1.0) for t in span),
            "junk": False,
            "phrase": sense,
        })
        i += size
    return out


def _credit_phrase(rec, sense):
    """Turn the unmatched record for a merged span into a matched one."""
    gse = sense.get("gse")
    rec["matched"] = True
    rec["matched_form"] = rec["token"]
    rec["gse"] = gse
    rec["band"] = clean_band(sense.get("cefr"))
    rec["coarse"] = band_for_gse(gse)
    rec["pos"] = (sense.get("grammatical_category") or "").strip() or None
    rec["definition"] = sense.get("definition") or None
    rec["senses"] = 1
    rec["collision"] = None
    # Flagged so the UI can say this credit came from a phrase rather than a
    # word, and so nothing downstream mistakes it for a single-word match.
    rec["multi_word"] = True
    return rec


# ---------------------------------------------------------------------------
# 2. Cache -- a re-run reproduces exactly and is not re-billed
# ---------------------------------------------------------------------------

_CACHE = {}
_CACHE_MAX = 2000


def cache_key(text, items, cfg):
    h = hashlib.sha256()
    h.update(("%s\x1f%s\x1f" % (cfg["model"], cfg["effort"])).encode("utf-8"))
    h.update(text.encode("utf-8", "replace"))
    h.update(b"\x1f")
    h.update("\x1e".join(sorted(i["token"] for i in items)).encode("utf-8"))
    return h.hexdigest()


def _cache_get(k):
    return _CACHE.get(k)


def _cache_put(k, v):
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[k] = v


# ---------------------------------------------------------------------------
# 3. Asking
# ---------------------------------------------------------------------------

def _index(raw, items):
    """Map the model's verdicts back onto the tokens we asked about."""
    by_token = {}
    for v in (raw or {}).get("verdicts", []):
        t = (v.get("token") or "").strip().lower()
        if t:
            by_token.setdefault(t, v)
    out = {}
    for it in items:
        out[it["token"]] = by_token.get(it["token"], {
            "answer": "unrecoverable", "replacement": "", "confidence": 0.0,
            "reason": "no verdict returned for this token",
        })
    return out


# ---------------------------------------------------------------------------
# 4. The fourth reading
# ---------------------------------------------------------------------------

def _stream_lower(word):
    """
    The lookup key for a stream token, normalised exactly as
    `_engine/views.tokenize` normalises the as-written ones.

    Both readings have to key on the same form or the same word matches in one
    and not the other.
    """
    return word.lower().replace("'", "")


def _match_case(written, replacement):
    if written.isupper() and len(written) > 1:
        return replacement.upper()
    if written[:1].isupper():
        return replacement.capitalize()
    return replacement


def corrected_sample(text, result, decisions):
    """
    STAGE 2 OUTPUT: the good-spelling version of the sample.

    Spelling only. Every token is either left exactly as the student wrote it or
    replaced by a word it was a misspelling of -- one the engine resolved, or one
    the model resolved and the form gates accepted. Nothing is inserted, no
    grammar is touched, and no word is upgraded: `me` stays `me`.

    Returns (corrected_text, stream, changes). The stream is what the scorer
    consumes; the text is for a human to read. They are built from the same
    decisions, so they cannot disagree.
    """
    det = {}
    for row in result["audit"]["lenient"]:
        if row["decision"] in ("corrected", "split") and row.get("corrected"):
            det[row["original"]] = row

    junk_forms = {j["token"] for j in result["junk"]}
    names = {d["original"] for d in decisions.values()
             if d["answer"] == "proper_noun"}
    fixes = {d["original"]: d for d in decisions.values() if d.get("corrected")}
    # DEFERENCE. A mechanical correction that only survived a grammar tie-break
    # is dropped when the interpretation declines to confirm it: the tie-break
    # was a guess between readings letters could not separate, and something
    # that read the sentence has now disagreed. Leaving both in would let the
    # less-informed component win, which is the whole thing being fixed.
    unconfirmed = {d["original"] for d in decisions.values()
                   if not d.get("corrected") and d["answer"] != "proper_noun"}

    # Accepted joins, keyed by where the FIRST of the two tokens begins. This is
    # the one place a token count changes -- two written words become one word.
    joins = {}
    for d in decisions.values():
        if d.get("join") and d.get("corrected"):
            joins[d["start"]] = d

    toks = tokenize(text)
    # Answers the corrector is not entitled to keep on its own.
    maybe_names = set(proper_noun_candidates(text, toks))

    out, stream, changes, cursor = [], [], [], 0
    skip = -1
    for idx, t in enumerate(toks):
        if idx == skip:
            cursor = t["end"]         # swallowed by the join before it
            continue
        written, w = t["raw"], t["lower"]
        out.append(text[cursor:t["start"]])
        cursor = t["end"]

        jn = joins.get(t["start"])
        if jn and idx + 1 < len(toks):
            one = _match_case(written, jn["corrected"])
            cursor = toks[idx + 1]["end"]
            skip = idx + 1
            out.append(one)
            stream.append({"raw": one, "lower": _stream_lower(one),
                           "confidence": jn["confidence"], "junk": False})
            changes.append({"written": jn["original"], "read_as": one,
                            "confidence": round(jn["confidence"], 3),
                            "source": "model (joined)"})
            continue

        parts, conf, source = [written], 1.0, None
        if w in names:
            # A name is not vocabulary. Excluded the way noise is, so it stops
            # counting as a word the student failed to spell.
            stream.append({"raw": written, "lower": w, "confidence": 1.0,
                           "junk": True})
            out.append(written)
            continue
        if w in fixes:
            d = fixes[w]
            parts, conf, source = [_match_case(written, d["corrected"])], \
                d["confidence"], "model"
        elif w in det and not _withheld(det[w], w, unconfirmed, maybe_names):
            row = det[w]
            got = row.get("split") or [row["corrected"]]
            parts = [_match_case(written, p) if i == 0 else p
                     for i, p in enumerate(got)]
            conf, source = row["confidence"], "engine"

        out.append(" ".join(parts))
        for p in parts:
            stream.append({"raw": p, "lower": _stream_lower(p),
                           "confidence": conf,
                           "junk": p.lower() in junk_forms and source is None})
        if source:
            changes.append({"written": written, "read_as": " ".join(parts),
                            "confidence": round(conf, 3), "source": source})
    out.append(text[cursor:])
    return _tidy(" ".join("".join(out).split(" "))), stream, changes



def _withheld(row, w, unconfirmed, maybe_names):
    """
    Is the corrector's answer one it may not keep unless the interpretation
    confirmed it? Three cases, all of them uncertain by construction:

      - a grammar tie-break the interpretation declined to confirm
      - a correction below CREDIBLE_MIN, which never counted toward the level
        anyway but was being displayed as though it had
      - a Title-case mid-sentence token that is probably a name
    """
    if w not in unconfirmed:
        return False                      # the interpretation backed it
    if row.get("slot_settled"):
        return True
    if row.get("confidence", 1.0) < CREDIBLE_MIN:
        return True
    return w in maybe_names


def _tidy(s):
    """
    Sentence spacing, for the version a human reads. DISPLAY ONLY -- the token
    stream the scorer consumes is built above and is untouched by this, so
    punctuation can never move a score. Spelling is corrected; the student's
    words and grammar are not.
    """
    import re
    s = re.sub(r"\s+([.,!?;:])", r"\1", s)          # "baby ." -> "baby."
    s = re.sub(r"([.,!?;:])(?=[A-Za-z])", r"\1 ", s)  # ".I see" -> ". I see"
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def _profile(stream, bank):
    prof = build_profile(stream, bank)
    for rec, tok in zip(prof["full"], stream):
        rec["junk"] = tok.get("junk", False)
        # A merged span arrives unmatched, because the bank's index holds single
        # words only. Credit it here, before the views below are derived from
        # these same record objects.
        if tok.get("phrase"):
            _credit_phrase(rec, tok["phrase"])
    # The tallies build_profile computed are stale for any span just credited.
    prof["counts"]["matched"] = sum(1 for r in prof["full"] if r["matched"])
    prof["counts"]["unmatched"] = sum(1 for r in prof["full"] if not r["matched"])
    prof["counts"]["content_matched"] = sum(
        1 for r in prof["content_only"] if r["matched"])
    prof["distinct"] = [r for r in prof["distinct"] if not r.get("junk")]
    prof["summary"] = _resummarise(prof["distinct"])
    prof["highest"] = highest_band(prof["distinct"])
    prof["levels"] = level_measures(prof["distinct"])
    prof["score"] = score_profile(prof["distinct"])
    return prof


# ---------------------------------------------------------------------------
# 5. Spelling profile -- descriptive, never scored
# ---------------------------------------------------------------------------

def attempts(result, decisions, bank):
    """
    One record per DISTINCT written form the student actually attempted.

    Over ALL word tokens, not just content words: orthographic control covers
    "becuase" and "teh" as much as "enviroment". That is a deliberate departure
    from the vocabulary score, which counts content words only.

    Excluded entirely -- proper nouns (a name is not an orthography failure),
    junk, and anything non-alphabetic.
    """
    det = {}
    for row in result["audit"]["lenient"]:
        if row["decision"] in ("corrected", "split") and row.get("corrected"):
            det[row["original"]] = row

    junk_forms = {j["token"] for j in result["junk"]}
    names = {d["original"] for d in decisions.values()
             if d["answer"] == "proper_noun"}

    occ = {}
    for rec in result["original"]["full"]:
        w = (rec.get("token") or "").lower()
        if w and w.isalpha():
            occ[w] = occ.get(w, 0) + 1

    recovered = {d["original"] for d in decisions.values() if d.get("corrected")}
    out = []
    for w, n in occ.items():
        # Junk recovered by the interpretation is a spelling error, not noise --
        # it has to count, or a student whose attempts look like mash is scored
        # as if they wrote nothing.
        if (w in junk_forms and w not in recovered) or w in names:
            continue
        intended, category, split = w, "correct", False
        if w in decisions:
            d = decisions[w]
            intended = d.get("corrected") or w
            category = review.categorise(w, d.get("corrected"), d["answer"],
                                         was_real_word=d.get("was_real_word", False))
        elif w in det:
            row = det[w]
            split = row["decision"] == "split"
            intended = row["corrected"]
            category = review.categorise(w, row.get("corrected"), "replacement",
                                         was_real_word=False, split=split)
        d0 = bank.describe(intended.split()[0] if intended else w)
        out.append({
            "written": w,
            "intended": intended if category != "correct" else w,
            "category": category,
            "band": d0.get("coarse") if d0.get("matched") else None,
            "occurrences": n,
        })
    return out


def spelling_profile(result, decisions):
    """
    One category per distinct content form the script actually used, counting
    the engine's own repairs as well as the model's verdicts. Junk is excluded:
    noise is not a spelling error.

    PROPER NOUNS ARE EXCLUDED FROM THE POPULATION, not just from the error
    count. `attempts()` (which feeds the scored spelling index, doc 10)
    already does this -- `or w in names: continue` removes the word entirely
    rather than counting it as correct. This function used to count
    `proper_noun` into `total` without excluding it from the "not correct"
    error numerator either, so a script with confirmed names and zero real
    spelling mistakes still reported a non-zero "carried an error" rate: a
    name isn't "correct" as a category, so it was read as an error by the
    (total - correct) formula. Approved 24 Aug 2026.
    """
    counts = {c: 0 for c in review.CATEGORIES}
    rows = []

    det = {}
    for row in result["audit"]["lenient"]:
        if row["decision"] in ("corrected", "split"):
            det[row["original"]] = row

    junk = {j["token"] for j in result["junk"]}
    seen = set()

    for rec in result["original"]["distinct"]:
        w = rec.get("token")
        if not w or w in seen or w in junk:
            continue
        seen.add(w)

        if w in decisions:
            d = decisions[w]
            cat = review.categorise(w, d.get("corrected"), d["answer"],
                                    was_real_word=d.get("was_real_word", False))
            source = "model"
        elif w in det:
            row = det[w]
            cat = review.categorise(w, row.get("corrected"), "replacement",
                                    was_real_word=False,
                                    split=row["decision"] == "split")
            source = "engine"
        else:
            cat = "correct"
            source = "engine"

        counts[cat] += 1
        if cat != "correct":
            rows.append({"word": w, "category": cat, "source": source})

    # The row for `proper_noun` is kept below -- a marker can still see which
    # words were treated as names, and how many -- but names are removed from
    # `total` itself, so neither the headline error rate nor any row's Share
    # reports against a population that still includes them.
    total = (sum(counts.values()) - counts["proper_noun"]) or 1
    profile = [{
        "category": c,
        "label": review.CATEGORY_LABEL[c],
        "count": counts[c],
        "pct": round(100.0 * counts[c] / total, 1),
    } for c in review.CATEGORIES if counts[c]]

    return {
        "examined": total,
        "profile": profile,
        "errors": sorted(rows, key=lambda r: (r["category"], r["word"])),
        "error_rate": round(100.0 * (total - counts["correct"]) / total, 1),
    }


# ---------------------------------------------------------------------------
# 6. Entry points
# ---------------------------------------------------------------------------

def _apply(result, items, raw, bank, corrector, note):
    """
    Fold a set of raw verdicts (or a failure) into one deterministic result.

    Always returns the result. On failure the three readings stand untouched and
    a note explains why the fourth is absent.
    """
    # NOTHING TO ASK IS NOT NOTHING TO REPORT. A script clean enough that no
    # token was flagged still has a good-spelling version -- the mechanical one
    # -- and both scores are computable from it. Returning early here left 34 of
    # 100 scripts with no vocabulary score and no spelling score at all, which
    # is precisely backwards: those are the scripts we are surest about.
    if items and raw is None:
        result["intent_note"] = note or "the intent reading was unavailable"
        return result
    if not items:
        result["intent_note"] = ("no tokens needed a second reading; the "
                                 "mechanical version is the good-spelling one")

    real = {i["token"]: i["real_word"] for i in items}
    pairs = {i["token"]: i["pair"] for i in items if i.get("pair")}
    decisions = {}
    for tok, verdict in _index(raw, items).items() if items else ():
        if tok in pairs:
            d = review.validate_join(pairs[tok], verdict, corrector)
        else:
            d = review.validate(tok, verdict, corrector)
        d["was_real_word"] = real.get(tok, False)
        decisions[tok] = d

    # STAGE 2 -> STAGE 4. The scorer is handed tokens, never text, so the two
    # stages stay separable and the good-spelling version is a real artifact
    # rather than an intermediate the scorer happens to see.
    text = result["text"]
    corrected, stream, changes = corrected_sample(text, result, decisions)
    # Multi-word units are collapsed after the corrector has finished, so the
    # phrase is matched against the reading that will actually be scored.
    stream = _merge_phrases(stream, bank)
    result["corrected_sample"] = corrected
    result["corrections"] = changes
    result["intent"] = _profile(stream, bank)
    result["intent_decisions"] = decisions
    result["coverage"] = _coverage(result, decisions)
    result["spelling"] = spelling_profile(result, decisions)
    # SCORE 2. Computed from the same intent reading as the vocabulary score,
    # and deliberately independent of it: a student can be A2 vocabulary with
    # poor spelling, or Pre-A1 spelled accurately, and the two numbers have to
    # be able to say so.
    result["spelling_score"] = spelling_score.score(
        attempts(result, decisions, bank))
    result["vocabulary_score"] = vocabulary_features(result)
    return result


def _coverage(result, decisions):
    """
    How much of the sample the level actually rests on.

    score-eligible distinct content words / distinct content words written. A
    level built from half the sample is a level built from the half that
    happened to be spelled well, and that has to be visible.

    Approved 24 Aug 2026 (three fixes, root cause confirmed by live repro
    before this brief -- see docs/19):

      1. `unresolved` is returned for DISPLAY as well as used internally for
         the coverage fraction. The internal set stays keyed on `token` (the
         normalised, matching identity -- that part was never wrong and must
         not change). The returned list now maps each token back to the
         written form (`raw`) carried on the same `written` records, the same
         field `score.py`'s `_words()` already uses for the word-chip grid.
      2. Clause (b) used to scan every distinct content word for an unmatched,
         uncorrected one, regardless of whether `flag()` ever asked about it.
         `decisions` is keyed on exactly the tokens `flag()` produced a
         candidate for -- `_apply()`'s loop covers every item in `items`, so
         `decisions` IS that candidate set, nothing further needs threading
         through. A word the corrector already calls "known" (real word, just
         outside the GSE list) never reaches `flag()` at all and now can't
         land in `unresolved` with no review row to correspond to it.
      3. `names` (confirmed proper nouns) was excluded from the coverage
         fraction's numerator and denominator, but clause (b) had no matching
         check -- a proper noun is unmatched and was never "corrected", so it
         satisfied clause (b) regardless of being resolved. `names` now builds
         before clause (b) runs, and clause (b) excludes it the same way the
         fraction already does.
    """
    written = [r for r in result["original"]["distinct"]
               if not r.get("junk")]
    if not written:
        return {"coverage": None, "resolved": 0, "written": 0,
                "indicative_only": True}
    # Written form for display, keyed the same way `unresolved` is -- built
    # once, from the same records `eligible`/`denom` already read below.
    raw_of = {(r.get("token") or ""): (r.get("raw") or r.get("token") or "")
              for r in written}
    names = {d["original"] for d in decisions.values()
             if d["answer"] == "proper_noun"}
    unresolved = {d["original"] for d in decisions.values()
                  if d["answer"] in ("unrecoverable",) or
                  (d["answer"] == "replacement" and not d["accepted"])}
    # Anything a correction was actually applied to, mechanically or in context.
    # These are unmatched as written but resolved in the reading that scored.
    corrected = {row["original"] for row in result["audit"]["lenient"]
                 if row.get("corrected")}
    corrected |= {d["original"] for d in decisions.values() if d.get("corrected")}
    # NEVER RESOLVED: no match of its own, and no correction to give it one.
    # Coverage's own definition is score-eligible words, and a word the scorer
    # never saw is not one. Restricted to words `flag()` actually put forward
    # (`in decisions`) and not a confirmed name (`not in names`) -- a word
    # nobody was ever asked about, or one already settled as a proper noun, is
    # not "awaiting review".
    unresolved |= {(r.get("token") or "") for r in written
                   if not r.get("matched") and (r.get("token") or "") not in corrected
                   and (r.get("token") or "") in decisions
                   and (r.get("token") or "") not in names}
    eligible = [r for r in written
                if (r.get("token") or "") not in unresolved
                and (r.get("token") or "") not in names]
    denom = [r for r in written if (r.get("token") or "") not in names]
    cov = round(len(eligible) / float(len(denom)), 3) if denom else None
    return {
        "coverage": cov,
        "resolved": len(eligible),
        "written": len(denom),
        "unresolved": sorted(raw_of.get(tok, tok) for tok in unresolved),
        # Advisory, not a gate: the level is still reported, but a level built
        # from a fraction of the sample must say so next to itself.
        "indicative_only": bool(cov is not None and cov < 0.80),
    }


def enrich(pairs, bank, corrector):
    """
    Add the intent reading to a list of (text, deterministic_result).

    One request per script, run concurrently inside a single deadline. Cached
    scripts never reach the network. Never raises: a script whose request fails
    keeps its three deterministic readings and carries a note.

    Returns a stats dict for the caller to report.
    """
    stats = {"model": None, "scripts": len(pairs), "asked": 0, "cached": 0,
             "failed": 0, "proposals": 0, "accepted": 0, "rejected": 0,
             "available": client.available()}

    plans = [(text, result, flag(text, result, bank, corrector))
             for text, result in pairs]

    if not client.available():
        for text, result, items in plans:
            _apply(result, items, None, bank, corrector,
                   "no API key configured; the deterministic readings stand")
            assert_complete(result, intent_expected=False)
        return stats

    cfg = client.config()
    stats["model"] = cfg["model"]
    stats["effort"] = cfg["effort"]

    jobs, pending, ready = [], {}, {}
    for i, (text, result, items) in enumerate(plans):
        if not items:
            continue
        key = cache_key(text, items, cfg)
        hit = _cache_get(key)
        if hit is not None:
            ready[i] = hit
            stats["cached"] += 1
            continue
        pending[i] = key

        def thunk(deadline_at, items=items, text=text):
            return client.call(review.SYSTEM,
                               review.build_question(text, items),
                               review.SCHEMA, cfg, deadline_at)

        jobs.append((i, thunk))

    stats["asked"] = len(jobs)
    errors = {}
    for i, value, err in client.fan_out(jobs, cfg):
        if err:
            errors[i] = err
            stats["failed"] += 1
        else:
            ready[i] = value
            _cache_put(pending[i], value)

    for i, (text, result, items) in enumerate(plans):
        _apply(result, items, ready.get(i), bank, corrector, errors.get(i))
        # A script only escapes the intent reading if its request actually
        # failed. "Nothing to ask" is not a failure and must still produce one.
        assert_complete(result, intent_expected=(i not in errors))
        for d in (result.get("intent_decisions") or {}).values():
            if d["answer"] == "replacement" or d.get("rejected_because"):
                stats["proposals"] += 1
                if d["accepted"] and d.get("corrected"):
                    stats["accepted"] += 1
                else:
                    stats["rejected"] += 1

    return stats
