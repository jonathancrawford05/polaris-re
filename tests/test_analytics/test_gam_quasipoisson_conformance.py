"""Capability ladder slice **3b** — ``quasipoisson(log)`` at free ``sp`` against
``mgcv`` (``docs/PLAN_mgcv_capability_ladder.md``).

Provenance gate (ADR-193): every quantity :data:`QUASIPOISSON_FREE_SP_CLAIM`
declares is ``INDEPENDENT``, and :func:`fit_quasipoisson_free_sp_case` cannot see
``mgcv``'s fit. These tests pin that structure and the measurement's power to
discriminate; the agreement magnitude belongs in the ledger.
"""

import json
import subprocess
import typing
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_model import fit_polaris_gam
from polaris_re.analytics.gam_quasipoisson_conformance import (
    QUASIPOISSON_FREE_SP_CLAIM,
    RQuasiPoissonFreeSpPayload,
    RQuasiPoissonFreeSpRecipe,
    compare_quasipoisson_free_sp_case,
    fit_quasipoisson_free_sp_case,
    quasipoisson_model_spec,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_YEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]

_MGCV_PRODUCED_KEYS = ("eta", "sp", "edf_total", "term_edf", "offset_gap", "coef", "scale")
_MGCV_DIAGNOSTIC_KEYS = ("mgcv_version", "r_version", "schema_version")


def _recipe(n: int = 300, seed: int = 20260930) -> RQuasiPoissonFreeSpRecipe:
    """An overdispersed-count recipe of the probe's own shape, R-free."""
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
    size = 4.0
    y = rng.negative_binomial(size, size / (size + mu)).astype(np.float64)
    return RQuasiPoissonFreeSpRecipe(
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
        QUASIPOISSON_FREE_SP_CLAIM.quantities, claim=QUASIPOISSON_FREE_SP_CLAIM.claim
    )
    assert QUASIPOISSON_FREE_SP_CLAIM.is_parity_claim
    assert QUASIPOISSON_FREE_SP_CLAIM.reference_internal_quantities == ()


def test_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_quasipoisson_free_sp_case)
    assert hints["r_case"] is RQuasiPoissonFreeSpRecipe
    recipe_keys = set(RQuasiPoissonFreeSpRecipe.__annotations__)
    payload_keys = set(RQuasiPoissonFreeSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_MGCV_PRODUCED_KEYS)
    assert set(_MGCV_PRODUCED_KEYS) <= payload_keys
    assert recipe_keys.isdisjoint(_MGCV_DIAGNOSTIC_KEYS)


def test_the_fit_is_unchanged_when_every_mgcv_key_is_planted() -> None:
    """Runtime complement to the structural test: planting hostile values under
    every mgcv-produced key must leave the Python fit bit-identical."""
    recipe = _recipe()
    clean = fit_quasipoisson_free_sp_case(recipe)
    n = recipe["n"]
    planted = dict(recipe)
    planted.update(
        eta=[99.0] * n,
        sp=[1e-3] * 4,
        edf_total=1.0,
        term_edf=[9.0] * 3,
        offset_gap=0.0,
        coef=[0.0],
        scale=1.0,
        converged=True,
        **{k: "x" for k in _MGCV_DIAGNOSTIC_KEYS},
    )
    hostile = fit_quasipoisson_free_sp_case(typing.cast(RQuasiPoissonFreeSpRecipe, planted))
    np.testing.assert_array_equal(clean.eta, hostile.eta)
    np.testing.assert_array_equal(clean.log_lambda, hostile.log_lambda)
    np.testing.assert_array_equal(clean.edf_total, hostile.edf_total)


def test_model_spec_is_quasipoisson_log_on_the_three_term_design() -> None:
    spec = quasipoisson_model_spec(tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS))
    assert (spec.family, spec.link) == ("quasipoisson", "log")
    assert [t.basis for t in spec.terms] == ["cr", "cr", "ti"]


def test_the_measurement_discriminates_a_scale_fixed_at_one() -> None:
    """The comparison has power: on an overdispersed response, the SAME design
    under ``poisson`` (scale fixed at 1) selects different smoothing than
    ``quasipoisson`` (scale estimated). A criterion that silently ignored the
    dispersion would make this test fail."""
    recipe = _recipe()
    qp = fit_quasipoisson_free_sp_case(recipe)
    data = {
        k: np.asarray(recipe[k], dtype=np.float64)  # type: ignore[literal-required]
        for k in ("AttdAge", "PolYear", "StudyYear_C")
    }
    spec = replace(quasipoisson_model_spec(tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS)), family="poisson")
    pois = fit_polaris_gam(spec, data, np.asarray(recipe["y"], dtype=np.float64))
    assert float(np.max(np.abs(qp.log_lambda - pois.log_lambda))) > 0.1


def test_compare_rejects_a_length_mismatch() -> None:
    recipe = _recipe(n=200)
    fit = fit_quasipoisson_free_sp_case(recipe)
    bad = dict(recipe)
    bad.update(
        eta=[0.0] * 5,
        sp=[1.0] * 4,
        edf_total=1.0,
        term_edf=[1.0] * 3,
        offset_gap=0.0,
        coef=[0.0],
        scale=1.0,
        converged=True,
    )
    with pytest.raises(PolarisValidationError):
        compare_quasipoisson_free_sp_case(fit, typing.cast(RQuasiPoissonFreeSpPayload, bad))


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1: run the probe and measure against it."""
    out = tmp_path / "gam_quasipoisson_free_sp_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_quasipoisson_free_sp_probe.R"), str(out)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    payload = typing.cast(RQuasiPoissonFreeSpPayload, json.loads(out.read_text()))
    result = compare_quasipoisson_free_sp_case(fit_quasipoisson_free_sp_case(payload), payload)
    assert result["agrees"], result
    assert result["r_scale"] > 1.2  # genuinely overdispersed, else the test is vacuous
    assert result["offset_gap"] < 1e-9
