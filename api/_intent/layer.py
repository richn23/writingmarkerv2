"""
Orchestration: pick the tokens, ask, validate, and build the fourth reading.

The three deterministic readings are untouched -- this module only ever reads
them. `intent` is built on top of `lenient` by applying the proposals that
survived validation, so the spread between `original` and `intent` is the honest
statement of how much of a score depends on reading through the spelling.
"""

import hashlib
import json

from _engine.analyse import _resummarise                        # noqa: E402
from _engine.scoring import score as score_profile              # noqa: E402
from _engine.scoring import CREDIBLE_MIN                        # noqa: E402
from _engine.spelling import (joinable_pairs,                   # noqa: E402
                              proper_noun_candidates,
                              suspicious_real_words)
from _engine.views import (build_profile, highest_band,         # noqa: E402
                           level_measures, tokenize)

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
            stream.append({"raw": one, "lower": one.lower(),
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
            stream.append({"raw": p, "lower": p.lower(),
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

    total = sum(counts.values()) or 1
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
    """
    written = [r for r in result["original"]["distinct"]
               if not r.get("junk")]
    if not written:
        return {"coverage": None, "resolved": 0, "written": 0,
                "indicative_only": True}
    unresolved = {d["original"] for d in decisions.values()
                  if d["answer"] in ("unrecoverable",) or
                  (d["answer"] == "replacement" and not d["accepted"])}
    names = {d["original"] for d in decisions.values()
             if d["answer"] == "proper_noun"}
    eligible = [r for r in written
                if (r.get("token") or "") not in unresolved
                and (r.get("token") or "") not in names]
    denom = [r for r in written if (r.get("token") or "") not in names]
    cov = round(len(eligible) / float(len(denom)), 3) if denom else None
    return {
        "coverage": cov,
        "resolved": len(eligible),
        "written": len(denom),
        "unresolved": sorted(unresolved),
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
