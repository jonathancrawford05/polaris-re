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
    3.12 and 3.13), but at ``n=900`` — the R probe's own sample size
    (``scripts/gam_select_multiterm_free_sp_probe.R``), matching the scale
    this session's own tier-1 AND tier-3 (GitHub Actions) measurements both
    ran clean at, on two independently-provisioned runners in the same CI
    run. **Measured, not guessed, and revised once already (PR #223
    review):** at ``n=150``, ``select=True``'s three extra null-space blocks
    landed EXACTLY at the search's own lower bound; at ``n=300`` the
    null-space blocks cleared it in THIS session's own sandbox, but PR
    #223's own CI (a different BLAS/thread environment) landed a DIFFERENT
    block — ``s(AttdAge)``'s own EXISTING wiggliness block — exactly on the
    lower bound instead, on Python 3.12, 3.13 AND the Docker build, all
    three. This is the same class of environment-dependent search-path
    sensitivity ADR-211/212 found for the free-`sp` search generally
    (``OPENBLAS_NUM_THREADS`` alone moves which trial points a blind search
    reaches) — a fixture-robustness property of a SMALL, marginally-signed
    sample, not a defect in the guard, the search, or this slice's own
    measurement (which used ``n=900`` throughout and never hit a bound at
    either tier). ``n=300`` is not reused as "probably enough" a second
    time; ``n=900`` matches the one scale this epic has actual
    cross-runner evidence for."""
    n = 900
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
    assert params == {"r_case", "multistart", "n_starts", "analytic_gradient"}

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
    assert fit.design["x"].shape == (900, 86)
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


def test_compare_select_free_sp_case_agrees_is_now_eta_edf_not_log10_sp() -> None:
    """PLAN slice 7e (ADR-221): ``agrees`` is the eta/edf gate;
    ``agrees_log10_sp`` preserves the OLD ``log10(sp)``-only gate so a
    reading can be shown under both. R-free -- built directly from
    synthetic, hand-supplied R-shaped values rather than a live fit, so this
    test exercises the gate arithmetic in isolation from the search."""
    recipe = _small_recipe()
    fit = fit_select_free_sp_case(recipe)
    n_blocks = fit.log_lambda.shape[0]
    n_terms = len(fit.edf_per_term)

    # A payload whose eta/edf are close to Python's own (passes the new
    # gate) but whose sp is deliberately far away (fails the old one) --
    # the exact shape ADR-220's multistart(9) reading has on the real
    # fixture.
    close_payload: RSelectFreeSpPayload = {
        **recipe,
        "eta": (fit.eta + 1.0e-3).tolist(),
        "coef": fit.coef.tolist(),
        "sp": (10.0 ** (fit.log_lambda + 3.0)).tolist(),  # 3 decades away
        "edf_total": fit.edf_total - 0.1,
        "term_edf": [1.0] * n_terms,
        "converged": True,
    }
    close = compare_select_free_sp_case(fit, close_payload)
    assert close.agrees is True
    assert close.agrees_log10_sp is False
    assert close.max_abs_log10_sp_diff == pytest.approx(3.0, abs=1e-9)

    # A payload whose sp matches exactly (passes the old gate) but whose
    # eta is far off (fails the new one).
    far_eta_payload: RSelectFreeSpPayload = {
        **recipe,
        "eta": (fit.eta + 5.0).tolist(),
        "coef": fit.coef.tolist(),
        "sp": (10.0**fit.log_lambda).tolist(),
        "edf_total": fit.edf_total,
        "term_edf": list(fit.edf_per_term.values()),
        "converged": True,
    }
    far_eta = compare_select_free_sp_case(fit, far_eta_payload)
    assert far_eta.agrees is False
    assert far_eta.agrees_log10_sp is True
    assert far_eta.max_abs_log10_sp_diff == pytest.approx(0.0, abs=1e-9)
    assert n_blocks == 7  # sanity: still the select=True 7-block structure


def test_compare_select_free_sp_case_reports_derived_tolerances() -> None:
    """The tolerances actually applied are on the returned comparison, not
    only implicit in module constants -- so a reader of one comparison
    object can audit what bar it was read against (ADR-221 DoD)."""
    recipe = _small_recipe()
    fit = fit_select_free_sp_case(recipe)
    payload: RSelectFreeSpPayload = {
        **recipe,
        "eta": fit.eta.tolist(),
        "coef": fit.coef.tolist(),
        "sp": (10.0**fit.log_lambda).tolist(),
        "edf_total": fit.edf_total,
        "term_edf": list(fit.edf_per_term.values()),
        "converged": True,
    }
    comparison = compare_select_free_sp_case(fit, payload, eta_tolerance=0.05, edf_tolerance=2.0)
    assert comparison.eta_tolerance == 0.05
    assert comparison.edf_tolerance == 2.0
    assert comparison.log10_sp_tolerance == 1.0e-2


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
    assert np.isfinite(comparison.max_abs_eta_diff)
    assert isinstance(comparison.agrees, bool)
    assert isinstance(comparison.agrees_log10_sp, bool)
