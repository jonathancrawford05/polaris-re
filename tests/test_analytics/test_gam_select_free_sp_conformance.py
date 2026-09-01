"""PLAN slice 7b's free-``sp`` conformance under ``select = TRUE``: does
``PolarisGAM`` choosing its own 7 smoothing parameters (each term's existing
block(s) plus its null-space block, ADR-217) agree with ``mgcv`` choosing its
own, on the identical three-term formula?

The provenance gate (ADR-193): every quantity
:data:`SELECT_FREE_SP_MODEL_CLAIM` declares is INDEPENDENT, and
:func:`fit_select_free_sp_case`'s signature structurally cannot see ``mgcv``'s
own fit (:class:`RSelectFreeSpRecipe` has no ``eta``/``coef``/``sp``/``edf``
key). Gated on R being present for the end-to-end round trip, same discipline
as ``test_gam_model_conformance.py``.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_select_free_sp_conformance import (
    SELECT_FREE_SP_MODEL_CLAIM,
    RSelectFreeSpPayload,
    RSelectFreeSpRecipe,
    compare_select_free_sp_case,
    fit_select_free_sp_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95]
_YEAR_KNOTS = [1, 2, 3, 5, 10, 21]


def _small_recipe() -> RSelectFreeSpRecipe:
    """Same covariate recipe as ``test_gam_model_conformance._small_recipe``
    (proven robust for the non-``select`` 4-block search on CI, both Python
    3.12 and 3.13), but at ``n=300`` rather than 150. **Measured, not
    guessed:** at ``n=150``, ``select=True``'s three extra null-space blocks
    (one per term) land EXACTLY at the search's own lower bound on this
    exact recipe — the null-space direction (the term's low-order, linear
    component) is well enough determined by so few points that the REML
    criterion genuinely wants zero extra penalty there, which
    :func:`~polaris_re.analytics.gam_model.fit_polaris_gam`'s at-bound guard
    (written for a term's own EXISTING wiggliness block, PR #212) reads as a
    conditioning defect and raises on. ``n=300`` already clears every block
    off the bound (checked up to ``n=900``, the R probe's own sample size,
    which also never hits it) — this is a small-sample fixture property, not
    a defect in the guard or the search, and is named rather than silently
    routed around (ADR-218)."""
    n = 300
    rng = np.random.default_rng(20260825)
    age = rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n)
    year = rng.uniform(_YEAR_KNOTS[0], _YEAR_KNOTS[-1], size=n)
    study_year_c = rng.uniform(-5.0, 5.0, size=n)
    expos = rng.uniform(50.0, 500.0, size=n)
    death_rng = np.random.default_rng(7)
    eta_true = -4.5 + 0.03 * age - 0.02 * year + 0.01 * study_year_c * (age - 50) / 50
    prob_true = 1.0 - np.exp(-np.exp(eta_true))
    death = death_rng.binomial(expos.astype(int), np.clip(prob_true, 0.0, 1.0))
    y = death / expos
    return RSelectFreeSpRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=study_year_c.tolist(),
        ExposCnt=expos.tolist(),
        y=y.tolist(),
        age_knots=[float(v) for v in _AGE_KNOTS],
        year_knots=[float(v) for v in _YEAR_KNOTS],
    )


def test_select_free_sp_model_claim_is_independent_on_every_declared_quantity() -> None:
    """ADR-193's gate: a harness result must not be able to satisfy this."""
    require_parity_evidence(
        SELECT_FREE_SP_MODEL_CLAIM.quantities, claim=SELECT_FREE_SP_MODEL_CLAIM.claim
    )
    assert SELECT_FREE_SP_MODEL_CLAIM.is_parity_claim


def test_fit_select_free_sp_case_signature_takes_no_r_fit_output() -> None:
    """ADR-193's mechanical test, applied structurally at the type:
    :class:`RSelectFreeSpRecipe` has no ``eta``/``coef``/``sp``/
    ``edf_total``/``term_edf`` key at all."""
    import inspect
    import typing

    params = set(inspect.signature(fit_select_free_sp_case).parameters)
    assert params == {"r_case", "multistart", "n_starts"}

    hints = typing.get_type_hints(fit_select_free_sp_case)
    assert hints["r_case"] is RSelectFreeSpRecipe

    recipe_keys = set(RSelectFreeSpRecipe.__annotations__)
    payload_keys = set(RSelectFreeSpPayload.__annotations__)
    fit_only_keys = {"eta", "coef", "sp", "edf_total", "term_edf", "converged"}
    assert recipe_keys.isdisjoint(fit_only_keys)
    assert fit_only_keys <= payload_keys
    assert recipe_keys < payload_keys
    # And explicitly NOT the same recipe shape as the fixed-sp harness --
    # `sp` is what this comparison measures, never a shared input here.
    assert "sp" not in recipe_keys


def test_fit_select_free_sp_case_produces_7_penalty_blocks() -> None:
    """R-free: select=True's own block count (2 + 2 + 3 = 7, ADR-217) is
    what the search actually gets, and the design shape matches the
    non-select recipe's (select=True adds penalty blocks, not columns)."""
    recipe = _small_recipe()
    fit = fit_select_free_sp_case(recipe)
    assert fit.design["x"].shape == (300, 86)
    assert fit.log_lambda.shape == (7,)
    assert set(fit.edf_per_term) == {
        "s(AttdAge)",
        "s(AttdAge,by=StudyYear_C)",
        "ti(AttdAge,PolYear)",
    }


def test_fit_select_free_sp_case_multistart_agrees_with_single_start_design() -> None:
    """R-free: ``multistart=True`` selects the same shapes (7 blocks, same
    design) as the default single-start path -- only the SEARCH differs, not
    the assembly (ADR-218)."""
    recipe = _small_recipe()
    single = fit_select_free_sp_case(recipe)
    multi = fit_select_free_sp_case(recipe, multistart=True, n_starts=3)
    assert multi.log_lambda.shape == single.log_lambda.shape == (7,)
    assert multi.design["x"].shape == single.design["x"].shape


def test_compare_select_free_sp_case_rejects_eta_shape_mismatch() -> None:
    """R-free: :func:`compare_select_free_sp_case`'s own guard against a
    payload whose ``eta`` doesn't match the Python fit's row count."""
    recipe = _small_recipe()
    fit = fit_select_free_sp_case(recipe)
    bad_payload: RSelectFreeSpPayload = {
        **recipe,
        "eta": [0.0] * (recipe["n"] - 1),
        "coef": [0.0] * len(fit.coef),
        "sp": [1.0] * 7,
        "edf_total": 5.0,
        "term_edf": [1.0, 1.0, 1.0],
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="shape"):
        compare_select_free_sp_case(fit, bad_payload)


def test_compare_select_free_sp_case_rejects_sp_count_mismatch() -> None:
    """R-free: a payload naming the wrong number of smoothing parameters."""
    recipe = _small_recipe()
    fit = fit_select_free_sp_case(recipe)
    bad_payload: RSelectFreeSpPayload = {
        **recipe,
        "eta": fit.eta.tolist(),
        "coef": fit.coef.tolist(),
        "sp": [1.0, 1.0, 1.0],  # 3, not 7
        "edf_total": 5.0,
        "term_edf": [1.0, 1.0, 1.0],
        "converged": True,
    }
    with pytest.raises(PolarisValidationError, match="smoothing parameter"):
        compare_select_free_sp_case(fit, bad_payload)


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv is not installed here")
def test_the_r_probe_runs_end_to_end(tmp_path) -> None:  # pragma: no cover
    """The real conformance run, when R happens to be present.

    Does NOT assert ``agrees`` -- slice 7b's own registered prediction (PLAN
    section) is about single-start underperforming multistart, and ADR-218
    found even multistart leaves a real, characterised residual on
    ``log10(sp)``. That is a reportable result (ADR-193), not a test failure
    to paper over. This test only proves the round trip completes: the probe
    runs, the Python side reads its recipe, fits (multistart, matching the
    reading ADR-218 reports as primary), and compares without raising.
    """
    out_path = tmp_path / "gam_select_multiterm_free_sp_probe.json"
    done = subprocess.run(
        [
            "Rscript",
            str(REPO_ROOT / "scripts" / "gam_select_multiterm_free_sp_probe.R"),
            str(out_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr

    payload = json.loads(out_path.read_text())
    fit = fit_select_free_sp_case(payload, multistart=True, n_starts=3)
    comparison = compare_select_free_sp_case(fit, payload)
    assert comparison.converged
    assert np.isfinite(comparison.max_abs_log10_sp_diff)
