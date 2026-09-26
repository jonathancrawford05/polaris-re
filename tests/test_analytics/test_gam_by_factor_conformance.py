"""Capability ladder rung **L3** — factor-``by`` against ``mgcv``, Stage B, both
``sp`` regimes (``docs/PLAN_mgcv_capability_ladder.md`` slice 4).

The provenance gate (ADR-193): every quantity both :data:`BY_FACTOR_FIXED_SP_CLAIM`
and :data:`BY_FACTOR_FREE_SP_CLAIM` declare is ``INDEPENDENT``, and neither
:func:`fit_by_factor_fixed_sp_case` nor :func:`fit_by_factor_free_sp_case`'s
signature can structurally see ``mgcv``'s fit (:class:`RByFactorFixedSpRecipe` /
:class:`RByFactorFreeSpRecipe` carry no ``eta``/``coef``/``sp``/``edf_total`` key).

**"A near-exact agreement is a suspicion before it is a result"** — the same
instruction every capability-ladder Stage-B module in this epic carries. Both
regimes below carry the SAME pair of independence tests: every ``mgcv``-produced
key stripped from the payload still gives a bit-identical Polaris fit, and
``edf_total`` measurably moves with the penalty.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_by_factor_conformance import (
    BY_FACTOR_FIXED_SP_CLAIM,
    BY_FACTOR_FREE_SP_CLAIM,
    RByFactorFixedSpPayload,
    RByFactorFixedSpRecipe,
    RByFactorFreeSpPayload,
    RByFactorFreeSpRecipe,
    by_factor_fixed_sp_model_spec,
    by_factor_free_sp_model_spec,
    compare_by_factor_fixed_sp_case,
    compare_by_factor_free_sp_case,
    fit_by_factor_fixed_sp_case,
    fit_by_factor_free_sp_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_POLYEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]
_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_N_LEVELS = 3
_SP = [3.0, 1.5, 2.5, 0.8]


def _fixed_sp_recipe(n: int = 240, seed: int = 20260926) -> RByFactorFixedSpRecipe:
    rng = np.random.default_rng(seed)
    polyear = rng.uniform(1.0, 21.0, size=n)
    age = rng.uniform(1.0, 95.0, size=n)
    group = rng.integers(0, _N_LEVELS, size=n)
    level_slope = np.array([0.4, -0.2, 0.6])
    mu = 1.5 + 0.05 * polyear + level_slope[group] * np.sin(age / 20.0)
    y = mu + rng.normal(scale=0.3, size=n)
    return RByFactorFixedSpRecipe(
        n=n,
        n_levels=_N_LEVELS,
        PolYear=polyear.tolist(),
        AttdAge=age.tolist(),
        group=group.tolist(),
        y=y.tolist(),
        polyear_knots=list(_POLYEAR_KNOTS),
        age_knots=list(_AGE_KNOTS),
        sp=list(_SP),
    )


def _free_sp_recipe(n: int = 240, seed: int = 20260926) -> RByFactorFreeSpRecipe:
    rng = np.random.default_rng(seed)
    polyear = rng.uniform(1.0, 21.0, size=n)
    age = rng.uniform(1.0, 95.0, size=n)
    group = rng.integers(0, _N_LEVELS, size=n)
    level_slope = np.array([0.4, -0.2, 0.6])
    mu = 1.5 + 0.05 * polyear + level_slope[group] * np.sin(age / 20.0)
    y = mu + rng.normal(scale=0.3, size=n)
    return RByFactorFreeSpRecipe(
        n=n,
        n_levels=_N_LEVELS,
        PolYear=polyear.tolist(),
        AttdAge=age.tolist(),
        group=group.tolist(),
        y=y.tolist(),
        polyear_knots=list(_POLYEAR_KNOTS),
        age_knots=list(_AGE_KNOTS),
    )


_FIXED_SP_MGCV_KEYS = ("eta", "edf_total", "term_edf", "offset_gap", "coef", "converged")
_FREE_SP_MGCV_KEYS = ("eta", "sp", "edf_total", "term_edf", "offset_gap", "coef", "converged")


# --------------------------------------------------------------------------
# Provenance (ADR-193 / ADR-228)
# --------------------------------------------------------------------------


def test_fixed_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(
        BY_FACTOR_FIXED_SP_CLAIM.quantities, claim=BY_FACTOR_FIXED_SP_CLAIM.claim
    )
    assert BY_FACTOR_FIXED_SP_CLAIM.is_parity_claim
    assert len(BY_FACTOR_FIXED_SP_CLAIM.parity_quantities) == 2
    assert BY_FACTOR_FIXED_SP_CLAIM.reference_internal_quantities == ()


def test_free_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(BY_FACTOR_FREE_SP_CLAIM.quantities, claim=BY_FACTOR_FREE_SP_CLAIM.claim)
    assert BY_FACTOR_FREE_SP_CLAIM.is_parity_claim
    assert len(BY_FACTOR_FREE_SP_CLAIM.parity_quantities) == 4
    assert BY_FACTOR_FREE_SP_CLAIM.reference_internal_quantities == ()


def test_fixed_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_by_factor_fixed_sp_case)
    assert hints["r_case"] is RByFactorFixedSpRecipe
    recipe_keys = set(RByFactorFixedSpRecipe.__annotations__)
    payload_keys = set(RByFactorFixedSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FIXED_SP_MGCV_KEYS)
    assert set(_FIXED_SP_MGCV_KEYS) <= payload_keys


def test_free_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_by_factor_free_sp_case)
    assert hints["r_case"] is RByFactorFreeSpRecipe
    recipe_keys = set(RByFactorFreeSpRecipe.__annotations__)
    payload_keys = set(RByFactorFreeSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FREE_SP_MGCV_KEYS)
    assert set(_FREE_SP_MGCV_KEYS) <= payload_keys


def test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _fixed_sp_recipe()
    payload = typing.cast(
        RByFactorFixedSpPayload,
        {
            **recipe,
            "eta": [0.0],
            "edf_total": -999.0,
            "term_edf": [-999.0],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with_payload = fit_by_factor_fixed_sp_case(typing.cast(RByFactorFixedSpRecipe, payload))
    recipe_only = fit_by_factor_fixed_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.fit.eta, recipe_only.fit.eta)
    assert with_payload.edf_total > 0.0


def test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _free_sp_recipe()
    payload = typing.cast(
        RByFactorFreeSpPayload,
        {
            **recipe,
            "eta": [0.0],
            "sp": [-999.0] * 4,
            "edf_total": -999.0,
            "term_edf": [-999.0] * 4,
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with_payload = fit_by_factor_free_sp_case(typing.cast(RByFactorFreeSpRecipe, payload))
    recipe_only = fit_by_factor_free_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.eta, recipe_only.eta)
    np.testing.assert_array_equal(with_payload.log_lambda, recipe_only.log_lambda)


def test_fixed_sp_edf_total_moves_with_the_by_term_penalty() -> None:
    recipe = _fixed_sp_recipe()
    base = fit_by_factor_fixed_sp_case(recipe).edf_total
    stiffer = fit_by_factor_fixed_sp_case({**recipe, "sp": [3.0, 50.0, 50.0, 50.0]}).edf_total
    assert stiffer < base, "stiffening every by-term level must reduce edf_total"


def test_free_sp_edf_is_sensitive_to_the_by_term() -> None:
    recipe = _free_sp_recipe()
    fit = fit_by_factor_free_sp_case(recipe)
    assert fit.edf_total > 0.0
    assert fit.edf_per_term["s(AttdAge):0"] > 0.0


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_fixed_sp_model_spec_has_one_plus_n_levels_terms() -> None:
    model = by_factor_fixed_sp_model_spec(tuple(_POLYEAR_KNOTS), tuple(_AGE_KNOTS), _N_LEVELS)
    assert model.family == "gaussian"
    assert model.link == "identity"
    assert [t.basis for t in model.terms] == ["cr"] * (1 + _N_LEVELS)
    assert model.terms[0].by_factor is None
    for level, term in enumerate(model.terms[1:]):
        assert term.by_factor == "GroupFac"
        assert term.by_level == level


def test_free_sp_model_spec_also_uses_gaussian_identity() -> None:
    """Unlike ladder rung L2, both regimes use the SAME family here — L5
    (ADR-231) already closed the free-scale blocker before this slice was
    written (module docstring)."""
    model = by_factor_free_sp_model_spec(tuple(_POLYEAR_KNOTS), tuple(_AGE_KNOTS), _N_LEVELS)
    assert model.family == "gaussian"
    assert model.link == "identity"


def test_fixed_sp_fit_rejects_a_wrong_block_count() -> None:
    recipe = _fixed_sp_recipe()
    with pytest.raises(PolarisValidationError, match="expected 4 sp values"):
        fit_by_factor_fixed_sp_case({**recipe, "sp": [1.0]})


def test_fixed_sp_comparison_gates_on_both_quantities() -> None:
    recipe = _fixed_sp_recipe()
    fit = fit_by_factor_fixed_sp_case(recipe)
    good = typing.cast(
        RByFactorFixedSpPayload,
        {
            **recipe,
            "eta": fit.fit.eta.tolist(),
            "edf_total": fit.edf_total,
            "term_edf": [0.0],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    assert compare_by_factor_fixed_sp_case(fit, good)["agrees"]
    edf_off = typing.cast(RByFactorFixedSpPayload, {**good, "edf_total": fit.edf_total + 5.0})
    result = compare_by_factor_fixed_sp_case(fit, edf_off)
    assert not result["agrees"]
    assert result["max_abs_eta_diff"] == pytest.approx(0.0, abs=1e-15)


def test_claim_sentences_name_their_tolerances() -> None:
    for claim in (BY_FACTOR_FIXED_SP_CLAIM, BY_FACTOR_FREE_SP_CLAIM):
        assert "2e-2" in claim.claim
        assert "1.0" in claim.claim
        assert "mgcv parity" not in claim.claim.lower()


# --------------------------------------------------------------------------
# The end-to-end round trips, gated on R
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_fixed_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1: run the probe and measure against it. A local reading is a
    HYPOTHESIS (``ROUTINE_MGCV_PARITY.md``); only the pinned digest settles
    it (``mgcv-conformance.yml``)."""
    out = tmp_path / "gam_by_factor_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_by_factor_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RByFactorFixedSpPayload, json.loads(out.read_text()))
    result = compare_by_factor_fixed_sp_case(fit_by_factor_fixed_sp_case(payload), payload)
    assert result["agrees"], result
    assert result["offset_gap"] == 0.0


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_free_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    out = tmp_path / "gam_by_factor_free_sp_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_by_factor_free_sp_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RByFactorFreeSpPayload, json.loads(out.read_text()))
    fit = fit_by_factor_free_sp_case(payload)
    result = compare_by_factor_free_sp_case(fit, payload)
    assert result.agrees, result
    assert result.offset_gap < 1e-6
