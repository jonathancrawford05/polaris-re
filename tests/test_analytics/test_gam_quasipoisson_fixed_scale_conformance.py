"""Capability ladder slice **7** — ``quasipoisson(log)`` at a supplied FIXED
``scale`` against ``mgcv``.

Provenance gate (ADR-193): every quantity the claim declares is ``INDEPENDENT``
and the fit function cannot see ``mgcv``'s fit. These tests pin that structure
and the measurement's power to discriminate; the agreement magnitudes belong in
the ledger, not here.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_quasipoisson_fixed_scale_conformance import (
    QUASIPOISSON_FIXED_SCALE_CLAIM,
    RQuasiPoissonFixedScalePayload,
    RQuasiPoissonFixedScaleRecipe,
    _model_and_data,
    compare_quasipoisson_fixed_scale_case,
    fit_quasipoisson_fixed_scale_case,
    fixed_scale_model_spec,
    score_at_both_points,
)
from polaris_re.analytics.gam_reml_optimize import penalized_fit_score_and_gradient
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_YEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]

_MGCV_PRODUCED_KEYS = ("fits", "poisson_scale_arg_reported", "poisson_ignores_scale")
_MGCV_DIAGNOSTIC_KEYS = ("mgcv_version", "r_version", "schema_version")


def _recipe(n: int = 250, seed: int = 20261001) -> RQuasiPoissonFixedScaleRecipe:
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
    return RQuasiPoissonFixedScaleRecipe(
        n=n,
        AttdAge=age.tolist(),
        PolYear=year.tolist(),
        StudyYear_C=by.tolist(),
        y=y.tolist(),
        age_knots=list(_AGE_KNOTS),
        year_knots=list(_YEAR_KNOTS),
        scales=[2.0, 6.0],
    )


def _self_payload(recipe: RQuasiPoissonFixedScaleRecipe, fits: list) -> dict:  # type: ignore[type-arg]
    """A payload whose 'mgcv' side is Polaris's own fit — for shape/guard tests only."""
    out = dict(recipe)
    out["fits"] = [
        {
            "eta": f.eta.tolist(),
            "offset_gap": 0.0,
            "sp": (10.0**f.log_lambda).tolist(),
            "edf_total": f.edf_total,
            "term_edf": list(f.edf_per_term.values()),
            "term_labels": list(f.edf_per_term),
            "scale": phi,
            "converged": True,
        }
        for f, phi in zip(fits, recipe["scales"], strict=True)
    ]
    out["poisson_scale_arg_reported"] = 1.0
    out["poisson_ignores_scale"] = True
    return out


def test_claim_is_independent_on_every_declared_quantity() -> None:
    require_parity_evidence(
        QUASIPOISSON_FIXED_SCALE_CLAIM.quantities, claim=QUASIPOISSON_FIXED_SCALE_CLAIM.claim
    )
    assert QUASIPOISSON_FIXED_SCALE_CLAIM.is_parity_claim
    assert QUASIPOISSON_FIXED_SCALE_CLAIM.reference_internal_quantities == ()


def test_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_quasipoisson_fixed_scale_case)
    assert hints["r_case"] is RQuasiPoissonFixedScaleRecipe
    recipe_keys = set(RQuasiPoissonFixedScaleRecipe.__annotations__)
    payload_keys = set(RQuasiPoissonFixedScalePayload.__annotations__)
    assert recipe_keys.isdisjoint(_MGCV_PRODUCED_KEYS)
    assert set(_MGCV_PRODUCED_KEYS) <= payload_keys
    assert recipe_keys.isdisjoint(_MGCV_DIAGNOSTIC_KEYS)
    assert "scales" in recipe_keys  # phi is a supplied INPUT to both sides


def test_the_fit_is_unchanged_when_every_mgcv_key_is_planted() -> None:
    recipe = _recipe()
    clean = fit_quasipoisson_fixed_scale_case(recipe)
    planted = dict(recipe)
    planted.update(
        fits=[{"eta": [99.0], "sp": [1e-3]}],
        poisson_scale_arg_reported=7.0,
        poisson_ignores_scale=False,
        **{k: "x" for k in _MGCV_DIAGNOSTIC_KEYS},
    )
    hostile = fit_quasipoisson_fixed_scale_case(typing.cast(RQuasiPoissonFixedScaleRecipe, planted))
    for a, b in zip(clean, hostile, strict=True):
        np.testing.assert_array_equal(a.eta, b.eta)
        np.testing.assert_array_equal(a.log_lambda, b.log_lambda)


def test_model_spec_is_poisson_log_on_the_three_term_design() -> None:
    spec = fixed_scale_model_spec(tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS))
    assert (spec.family, spec.link) == ("poisson", "log")
    assert [t.basis for t in spec.terms] == ["cr", "cr", "ti"]


def test_the_measurement_discriminates_the_supplied_scale() -> None:
    """Power: the same data at phi=2 and phi=6 selects different smoothing. A
    producer that ignored ``gamma`` (as mgcv's own ``poisson(scale=)`` ignores
    ``scale``) would make the two fits identical and this test fail."""
    fits = fit_quasipoisson_fixed_scale_case(_recipe())
    assert float(np.max(np.abs(fits[0].log_lambda - fits[1].log_lambda))) > 0.1
    assert fits[1].edf_total < fits[0].edf_total  # larger phi => smoother


def test_compare_passes_shape_checks_and_rejects_misalignment() -> None:
    recipe = _recipe(n=200)
    fits = fit_quasipoisson_fixed_scale_case(recipe)
    good = _self_payload(recipe, fits)
    results = compare_quasipoisson_fixed_scale_case(
        fits, typing.cast(RQuasiPoissonFixedScalePayload, good)
    )
    assert [r["scale"] for r in results] == [2.0, 6.0]
    assert all(r["max_abs_eta_diff"] < 1e-12 for r in results)

    bad = _self_payload(recipe, fits)
    bad["fits"][0]["term_labels"] = list(reversed(bad["fits"][0]["term_labels"]))
    with pytest.raises(PolarisValidationError, match="do not align"):
        compare_quasipoisson_fixed_scale_case(
            fits, typing.cast(RQuasiPoissonFixedScalePayload, bad)
        )

    unheld = _self_payload(recipe, fits)
    unheld["fits"][0]["scale"] = 1.0
    with pytest.raises(PolarisValidationError, match="did not hold the scale fixed"):
        compare_quasipoisson_fixed_scale_case(
            fits, typing.cast(RQuasiPoissonFixedScalePayload, unheld)
        )


def test_stationarity_diagnostic_reports_python_point_as_stationary() -> None:
    """The diagnostic's gradient at Polaris's converged point must be small
    RELATIVE to the gradient one decade away along the same coordinates — a
    scale-free check (an absolute bound would be a tuned constant: the
    achievable gradient depends on BLAS and the finite-difference noise floor,
    and a first draft's ``1e-2`` failed at ``1.26e-2`` on CI)."""
    recipe = _recipe(n=200)
    fits = fit_quasipoisson_fixed_scale_case(recipe)
    payload = typing.cast(RQuasiPoissonFixedScalePayload, _self_payload(recipe, fits))
    diag = score_at_both_points(fits, payload)
    model, data, y = _model_and_data(recipe)
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    for d, fit in zip(diag, fits, strict=True):
        assert d["python_score"] == pytest.approx(d["mgcv_score"], abs=1e-9)
        displaced = penalized_fit_score_and_gradient(
            y,
            design["x"],
            family,
            design["penalty_blocks"],
            fit.log_lambda + 1.0,
            gamma=d["scale"],
        )[2]
        assert d["python_max_abs_grad"] < 0.1 * float(np.max(np.abs(displaced)))


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1 (hypothesis only). The near-phi fit must agree; the far-phi fit is
    a RECORDED disagreement (ledger / ADR-236), so it is reported, not asserted."""
    out = tmp_path / "gam_quasipoisson_fixed_scale_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_quasipoisson_fixed_scale_probe.R"), str(out)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    payload = typing.cast(RQuasiPoissonFixedScalePayload, json.loads(out.read_text()))
    assert payload["poisson_ignores_scale"] is True
    results = compare_quasipoisson_fixed_scale_case(
        fit_quasipoisson_fixed_scale_case(payload), payload
    )
    assert results[0]["scale"] == 2.0
    assert results[0]["agrees"], results[0]
    assert results[0]["offset_gap"] < 1e-9
