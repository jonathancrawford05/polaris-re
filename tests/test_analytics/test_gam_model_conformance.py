"""``docs/WORK_ORDER_multi_term_assembly.md`` — PLAN slice 5b's free-``sp``
conformance: does ``PolarisGAM`` choosing its own smoothing parameters agree
with ``mgcv`` choosing its own, on the identical three-term formula?

The provenance gate (ADR-193): every quantity :data:`FREE_SP_MODEL_CLAIM`
declares is INDEPENDENT, and :func:`fit_free_sp_case`'s signature structurally
cannot see ``mgcv``'s own fit (:class:`RFreeSpRecipe` has no ``eta``/``coef``/
``sp``/``edf`` key). Gated on R being present, same discipline as
``test_gam_multiterm_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_model_conformance import (
    FREE_SP_MODEL_CLAIM,
    RFreeSpPayload,
    RFreeSpRecipe,
    compare_free_sp_case,
    fit_free_sp_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95]
_YEAR_KNOTS = [1, 2, 3, 5, 10, 21]


def _small_recipe() -> RFreeSpRecipe:
    """A minimal, R-free recipe with genuine signal.

    Earlier drew ``y`` as pure uniform noise, independent of every covariate.
    With no real curvature for the free-``sp`` search to find, at least one
    block's REML optimum is legitimately unbounded (infinite smoothing,
    i.e. "no signal here") — a plausible answer, but one that pins
    ``log10(sp)`` at a bound of :data:`~polaris_re.analytics.gam_model_conformance._SEARCH_BOUNDS`
    and therefore trips :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s
    at-bound guard (PR #212 review [P1]). Locally this landed just inside the
    bound (BLAS/optimizer-path dependent); on CI's different numerics it
    landed exactly on it. `eta_true` gives every term real dependence on its
    own covariate, the same pattern `test_gam_model.py`'s own fit smoke test
    already uses, so the search has a genuine interior optimum to find on any
    platform.
    """
    n = 40
    rng = np.random.default_rng(20260825)
    age = rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n)
    year = rng.uniform(_YEAR_KNOTS[0], _YEAR_KNOTS[-1], size=n)
    study_year_c = rng.uniform(-5.0, 5.0, size=n)
    expos = rng.uniform(50.0, 500.0, size=n)
    eta_true = (
        -4.5
        + 0.03 * age
        - 0.02 * year
        + 0.01 * study_year_c * (age - 50) / 50
        + 0.15 * np.sin(age / 10) * np.cos(year / 3)
    )
    prob_true = 1.0 - np.exp(-np.exp(eta_true))
    death = rng.binomial(expos.astype(int), np.clip(prob_true, 0.0, 1.0))
    y = death / expos
    return RFreeSpRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=study_year_c.tolist(),
        ExposCnt=expos.tolist(),
        y=y.tolist(),
        age_knots=[float(v) for v in _AGE_KNOTS],
        year_knots=[float(v) for v in _YEAR_KNOTS],
    )


def test_free_sp_model_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(FREE_SP_MODEL_CLAIM.quantities, claim=FREE_SP_MODEL_CLAIM.claim)
    assert FREE_SP_MODEL_CLAIM.is_parity_claim


def test_fit_free_sp_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type — the same
    discipline PR #202/#210 established for the family and multi-term
    conformance modules: :class:`RFreeSpRecipe` has no ``eta``/``coef``/
    ``sp``/``edf_total``/``term_edf`` key at all."""
    import inspect
    import typing

    params = set(inspect.signature(fit_free_sp_case).parameters)
    assert params == {"r_case"}

    hints = typing.get_type_hints(fit_free_sp_case)
    assert hints["r_case"] is RFreeSpRecipe

    recipe_keys = set(RFreeSpRecipe.__annotations__)
    payload_keys = set(RFreeSpPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "sp", "edf_total", "term_edf", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys
    # And explicitly NOT the same recipe shape as the fixed-sp harness —
    # `sp` is what this comparison measures, never a shared input here
    # (module docstring, the work order's own asymmetry, Sec. 3).
    assert "sp" not in recipe_keys


def test_fit_free_sp_case_produces_a_design_matching_the_recipe() -> None:
    """R-free: the assembled design has the expected shape (p=86, same
    arithmetic ADR-206 pinned) and the search converges on a small case."""
    recipe = _small_recipe()
    fit = fit_free_sp_case(recipe)
    assert fit.design["x"].shape == (40, 86)
    assert fit.log_lambda.shape == (4,)
    assert set(fit.edf_per_term) == {
        "s(AttdAge)",
        "s(AttdAge,by=StudyYear_C)",
        "ti(AttdAge,PolYear)",
    }


def test_compare_free_sp_case_rejects_eta_shape_mismatch() -> None:
    """R-free: :func:`compare_free_sp_case`'s own guard against a payload
    whose ``eta`` doesn't match the Python fit's row count."""
    recipe = _small_recipe()
    fit = fit_free_sp_case(recipe)
    bad_payload: RFreeSpPayload = {
        **recipe,
        "eta": [0.0] * (recipe["n"] - 1),
        "coef": [0.0] * len(fit.coef),
        "sp": [1.0, 1.0, 1.0, 1.0],
        "edf_total": 5.0,
        "term_edf": [1.0, 1.0, 1.0],
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="shape"):
        compare_free_sp_case(fit, bad_payload)


def test_compare_free_sp_case_rejects_sp_count_mismatch() -> None:
    """R-free: a payload naming the wrong number of smoothing parameters."""
    recipe = _small_recipe()
    fit = fit_free_sp_case(recipe)
    bad_payload: RFreeSpPayload = {
        **recipe,
        "eta": fit.eta.tolist(),
        "coef": fit.coef.tolist(),
        "sp": [1.0, 1.0, 1.0],  # 3, not 4
        "edf_total": 5.0,
        "term_edf": [1.0, 1.0, 1.0],
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="smoothing parameter"):
        compare_free_sp_case(fit, bad_payload)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    Does NOT assert ``agrees`` — the work order's own registered prediction
    (Sec. 4) may be refuted, and a refutation is a real, reportable result
    (ADR-193), not a test failure to paper over. This test only proves the
    round trip completes: the probe runs, the Python side reads its recipe,
    fits, and compares without raising.
    """
    out_path = tmp_path / "gam_multiterm_free_sp_probe.json"
    done = subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_multiterm_free_sp_probe.R"), str(out_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit = fit_free_sp_case(payload)
    comparison = compare_free_sp_case(fit, payload)
    assert comparison.converged
    assert np.isfinite(comparison.max_abs_log10_sp_diff)
