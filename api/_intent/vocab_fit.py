"""
The vocabulary 0-100 mapping. Two of them, selectable, neither deleted.

    VOCAB_SCORE_MODEL=fitted   (default) the refit below
    VOCAB_SCORE_MODEL=legacy             the original calibrated mapping

WHY A REFIT. The calibrated 0-100 was losing to one of its own inputs:
`distinct_gse_matched` predicted the marker's band at r = 0.84 while the score
itself managed 0.67. A mapping that discards information on the way through is
throwing away accuracy it already had.

HOW IT WAS FITTED. Least squares of the MOE band rank on ONE feature, on 47
scripts, with 41 held out and the split stratified by band so the held-out set
could not accidentally be all low-level:

    fitted r 0.808    held out r 0.872    current mapping, same held-out set 0.711

The held-out figure being higher than the fitted one is the opposite of
overfitting -- the fit does not depend on the scripts it was fitted on. Adding
`words_at_b2_plus` and `p80_gse` moved held-out r by 0.001, so they are not in
the model: two more coefficients to buy nothing is memorisation waiting to
happen.

⚠️ THE TOP OF THE SCALE IS PROVISIONAL. Only 11 of 88 usable scripts sit at B2
or above, 4 at B2+ and 2 at C1, and the refit's spread there is wide (B2+ lands
between 39 and 97). Above B1+ this is fitted on almost nothing. Compare both
mappings on batch 2 before trusting the top end.
"""

import os

# Band ranks the fit was against: Pre-A1=0 .. C2=10.
BAND_STEPS = 10

# intercept, then one coefficient per feature.
FITTED = {
    "features": ("distinct_gse_matched",),
    "weights": (1.4531, 0.1116),
    "fitted_r": 0.808,
    "heldout_r": 0.872,
    "n_train": 47,
    "n_heldout": 41,
}


def which():
    """
    LEGACY IS THE DEFAULT, deliberately.

    The refit is a rescaled word count: one linear term on
    `distinct_gse_matched`, with no vocabulary level in it at all. Forty simple
    words outscore twenty sophisticated ones, which is why its top end breaks
    apart -- B2+ spanning 39-97, one B2+ script below several Pre-A1 ones. That
    is not thinness of data at the top; it is the model measuring productivity,
    and the error surfacing hardest where length and level diverge. MOE bands
    partly reward length and task completion, so a length proxy correlates well
    with them by construction -- which is also why its r looked strong.

    It stays computed and exposed as `refit_score` because it is a useful
    research signal. It is not the number anyone reads as a vocabulary level.
    """
    v = (os.environ.get("VOCAB_SCORE_MODEL") or "legacy").strip().lower()
    return v if v in ("fitted", "legacy") else "legacy"


def fitted_score(features):
    """
    Predicted band rank -> 0-100. Linear in a count, so monotone by
    construction: more matched reference words can never mean a lower score.
    Clamped to the band range, which is what keeps it inside 0-100.
    """
    w = FITTED["weights"]
    rank = w[0] + sum(c * float(features.get(f) or 0)
                      for c, f in zip(w[1:], FITTED["features"]))
    rank = max(0.0, min(float(BAND_STEPS), rank))
    return int(round(100.0 * rank / BAND_STEPS))


def apply(features, legacy_score):
    """
    Returns (score, provenance). The provenance is stamped on every result: an
    assessment tool has to be able to say which mapping produced a number.
    """
    # Both are always computed, whichever is reported, so the two can be
    # compared on any batch without re-running anything.
    refit = fitted_score(features) if features.get("assigned") else None
    model = which()
    if model == "legacy" or not features.get("assigned"):
        return legacy_score, {
            "model": "legacy",
            "refit_score": refit,
            "note": "the original calibrated mapping. The refit is exposed as "
                    "refit_score for research only -- it carries no vocabulary "
                    "level, so it must not be read as one.",
        }
    return refit, {
        "model": "fitted",
        "features": list(FITTED["features"]),
        "weights": list(FITTED["weights"]),
        "legacy_score": legacy_score,
        "refit_score": refit,
        "warning": "a rescaled word count with no level term; fails the "
                   "coherence gate (a B2+ script scores below the Pre-A1 "
                   "median). Selected explicitly via VOCAB_SCORE_MODEL.",
    }
