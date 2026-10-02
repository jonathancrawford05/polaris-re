"""Capability ladder slice **3c** — the exposed dispersion and the two-stage
workflow against ``mgcv`` (``docs/PLAN_mgcv_capability_ladder.md``).

Provenance gate (ADR-193): every quantity :data:`DISPERSION_TWO_STAGE_CLAIM`
declares is ``INDEPENDENT`` and the producers cannot see ``mgcv``'s fit. These
tests pin that structure; the agreement magnitudes belong in the ledger.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_dispersion_conformance import (
    DISPERSION_TWO_STAGE_CLAIM,
    RDispersionPayload,
    RDispersionRecipe,
    compare_dispersion_two_stage_case,
    fit_dispersion_two_stage_case,
    fit_stage2_at_supplied_scale,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import ComparisonProvenance, require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_YEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]

_MGCV_PRODUCED_KEYS = ("joint", "stage1", "stage2", "phi_stage1_pearson")
_MGCV_DIAGNOSTIC_KEYS = ("mgcv_version", "r_version", "schema_version")


def _recipe(n: int = 250, seed: int = 20261002) -> RDispersionRecipe:
    rng = np.random.default_rng(seed)
    age = rng.uniform(1.0, 95.0, size=n)
    year = rng.uniform(1.0, 21.0, size=n)
    by = rng.uniform(-5.0, 5.0, size=n)
    eta = (
        1.5
        + 0.5 * np.sin(age / 12.0)
        - 0.02 * year
        + 0.08 * by * np.sin(age / 15.0)
        + 0.3 * np.sin(age / 10.0) * np.cos(year / 3.0)
    )
    mu = np.exp(eta)
    y = rng.negative_binomial(4.0, 4.0 / (4.0 + mu)).astype(np.float64)
    return RDispersionRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=by.tolist(),
        y=y.tolist(),
        age_knots=list(_AGE_KNOTS),
        year_knots=list(_YEAR_KNOTS),
    )


def test_claim_is_independent_on_every_declared_quantity() -> None:
    require_parity_evidence(
        DISPERSION_TWO_STAGE_CLAIM.quantities, claim=DISPERSION_TWO_STAGE_CLAIM.claim
    )
    assert DISPERSION_TWO_STAGE_CLAIM.is_parity_claim
    assert all(
        q.provenance is ComparisonProvenance.INDEPENDENT
        for q in DISPERSION_TWO_STAGE_CLAIM.quantities
    )


def test_producers_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_dispersion_two_stage_case)
    assert hints["r_case"] is RDispersionRecipe
    recipe_keys = set(RDispersionRecipe.__annotations__)
    payload_keys = set(RDispersionPayload.__annotations__)
    assert recipe_keys.isdisjoint(_MGCV_PRODUCED_KEYS)
    assert set(_MGCV_PRODUCED_KEYS) <= payload_keys
    assert recipe_keys.isdisjoint(_MGCV_DIAGNOSTIC_KEYS)
    # the supplied-scale producer takes a bare float, never the payload
    s2_hints = typing.get_type_hints(fit_stage2_at_supplied_scale)
    assert s2_hints["phi"] is float
    assert s2_hints["r_case"] is RDispersionRecipe


@pytest.mark.slow
def test_the_chain_is_unchanged_when_every_mgcv_key_is_planted() -> None:
    recipe = _recipe(n=200)
    clean = fit_dispersion_two_stage_case(recipe)
    planted = dict(recipe)
    planted.update(
        joint={"scale": 1.0},
        stage1={"scale": 1.0},
        stage2={"scale": 1.0},
        phi_stage1_pearson=99.0,
        **{k: "x" for k in _MGCV_DIAGNOSTIC_KEYS},
    )
    hostile = fit_dispersion_two_stage_case(typing.cast(RDispersionRecipe, planted))
    for name in ("joint", "joint_single_start", "stage1", "stage2"):
        a, b = getattr(clean, name), getattr(hostile, name)
        np.testing.assert_array_equal(a.eta, b.eta)
        np.testing.assert_array_equal(a.log_lambda, b.log_lambda)
    assert clean.phi_stage1 == hostile.phi_stage1


@pytest.mark.slow
def test_stage_two_holds_the_stage_one_pearson_dispersion_fixed() -> None:
    """The number stage 2 conditions on is exactly stage 1's exposed Pearson
    dispersion, and an overdispersed draw makes it visibly > 1 (non-vacuous)."""
    fits = fit_dispersion_two_stage_case(_recipe(n=200))
    assert fits.phi_stage1 == fits.stage1.dispersion.pearson
    assert fits.phi_stage1 > 1.2
    # a larger fixed scale is a stronger penalty relative to the likelihood:
    # stage 2 at phi > 1 cannot be MORE flexible than the unit-scale fit
    assert fits.stage2.edf_total <= fits.stage1.edf_total + 1e-6


@pytest.mark.slow
def test_supplied_scale_rejects_nonpositive() -> None:
    recipe = _recipe(n=200)
    fits = fit_dispersion_two_stage_case(recipe)
    with pytest.raises(PolarisValidationError, match="phi must be > 0"):
        fit_stage2_at_supplied_scale(recipe, 0.0, fits.stage1)


@pytest.mark.slow
def test_compare_rejects_an_eta_length_mismatch() -> None:
    recipe = _recipe(n=200)
    fits = fit_dispersion_two_stage_case(recipe)
    fit_ = {
        "eta": [0.0] * 3,
        "offset_gap": 0.0,
        "sp": [1.0] * 4,
        "edf_total": 1.0,
        "term_edf": [1.0] * 3,
        "term_labels": ["a"] * 3,
        "scale": 1.0,
        "converged": True,
        "estimators": {"pearson": 1.0, "fletcher": 1.0, "deviance": 1.0},
    }
    bad = dict(recipe, joint=fit_, stage1=fit_, stage2=fit_, phi_stage1_pearson=1.0)
    with pytest.raises(PolarisValidationError, match="eta has shape"):
        compare_dispersion_two_stage_case(fits, typing.cast(RDispersionPayload, bad), fits.stage2)


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1 round trip: the probe's estimator formula reproduces ``m$scale`` on
    mgcv's own fit (formula identification), and Polaris's chain is compared."""
    out = tmp_path / "gam_dispersion_two_stage_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_dispersion_two_stage_probe.R"), str(out)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    payload = typing.cast(RDispersionPayload, json.loads(out.read_text()))
    # formula identification (NOT parity): m$scale IS Fletcher on mgcv's own fit
    np.testing.assert_allclose(
        payload["joint"]["scale"], payload["joint"]["estimators"]["fletcher"], rtol=1e-12
    )
    assert payload["joint"]["scale"] > 1.2  # genuinely overdispersed
    fits = fit_dispersion_two_stage_case(payload)
    s2 = fit_stage2_at_supplied_scale(payload, payload["phi_stage1_pearson"], fits.stage1)
    result = compare_dispersion_two_stage_case(fits, payload, s2)
    assert result["agrees"], result
    assert result["identifies_fletcher"], result
