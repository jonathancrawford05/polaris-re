"""Capability ladder rung **L4** — unpenalized parametric block against
``mgcv``, Stage B, both ``sp`` regimes (``docs/PLAN_mgcv_capability_ladder.md``
slice 5).

The provenance gate (ADR-193): every quantity both :data:`PARAMETRIC_FIXED_SP_CLAIM`
and :data:`PARAMETRIC_FREE_SP_CLAIM` declare is ``INDEPENDENT``, and neither
:func:`fit_parametric_fixed_sp_case` nor :func:`fit_parametric_free_sp_case`'s
signature can structurally see ``mgcv``'s fit (:class:`RParametricFixedSpRecipe` /
:class:`RParametricFreeSpRecipe` carry no ``eta``/``coef``/``sp``/``edf_total`` key).

**"A near-exact agreement is a suspicion before it is a result"** — the same
instruction every capability-ladder Stage-B module in this epic carries. Both
regimes below carry the SAME pair of independence tests: every ``mgcv``-produced
key stripped from the payload still gives a bit-identical Polaris fit, and
``edf_total`` measurably moves with the smooth's own penalty.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_parametric_conformance import (
    PARAMETRIC_FIXED_SP_CLAIM,
    PARAMETRIC_FREE_SP_CLAIM,
    RParametricFixedSpPayload,
    RParametricFixedSpRecipe,
    RParametricFreeSpPayload,
    RParametricFreeSpRecipe,
    compare_parametric_fixed_sp_case,
    compare_parametric_free_sp_case,
    fit_parametric_fixed_sp_case,
    fit_parametric_free_sp_case,
    parametric_fixed_sp_model_spec,
    parametric_free_sp_model_spec,
    parametric_terms,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_FACE_LEVELS = ["Band1", "Band2", "Band3"]
_SMOKE_LEVELS = ["N", "Y"]
_SP = [2.5]


def _base_recipe(n: int = 240, seed: int = 20260927) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    face_group = rng.integers(0, len(_FACE_LEVELS), size=n)
    smoke_group = rng.integers(0, len(_SMOKE_LEVELS), size=n)
    age = rng.uniform(1.0, 95.0, size=n)
    face_effect = np.array([0.0, 0.6, -0.4])
    smoke_effect = np.array([0.0, 0.9])
    interaction = np.zeros((3, 2))
    interaction[1, 1] = 0.5
    interaction[2, 1] = -0.3
    mu = (
        1.2
        + face_effect[face_group]
        + smoke_effect[smoke_group]
        + interaction[face_group, smoke_group]
        + 0.4 * np.sin(age / 20.0)
    )
    y = mu + rng.normal(scale=0.3, size=n)
    return {
        "n": n,
        "face_levels": list(_FACE_LEVELS),
        "smoke_levels": list(_SMOKE_LEVELS),
        "face_group": face_group.tolist(),
        "smoke_group": smoke_group.tolist(),
        "AttdAge": age.tolist(),
        "y": y.tolist(),
        "age_knots": list(_AGE_KNOTS),
    }


def _fixed_sp_recipe(n: int = 240, seed: int = 20260927) -> RParametricFixedSpRecipe:
    return typing.cast(RParametricFixedSpRecipe, {**_base_recipe(n, seed), "sp": list(_SP)})


def _free_sp_recipe(n: int = 240, seed: int = 20260927) -> RParametricFreeSpRecipe:
    return typing.cast(RParametricFreeSpRecipe, _base_recipe(n, seed))


_FIXED_SP_MGCV_KEYS = ("eta", "edf_total", "term_edf", "offset_gap", "coef", "converged")
_FREE_SP_MGCV_KEYS = ("eta", "sp", "edf_total", "term_edf", "offset_gap", "coef", "converged")


# --------------------------------------------------------------------------
# Provenance (ADR-193 / ADR-228)
# --------------------------------------------------------------------------


def test_fixed_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(
        PARAMETRIC_FIXED_SP_CLAIM.quantities, claim=PARAMETRIC_FIXED_SP_CLAIM.claim
    )
    assert PARAMETRIC_FIXED_SP_CLAIM.is_parity_claim
    assert len(PARAMETRIC_FIXED_SP_CLAIM.parity_quantities) == 2
    assert PARAMETRIC_FIXED_SP_CLAIM.reference_internal_quantities == ()


def test_free_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(
        PARAMETRIC_FREE_SP_CLAIM.quantities, claim=PARAMETRIC_FREE_SP_CLAIM.claim
    )
    assert PARAMETRIC_FREE_SP_CLAIM.is_parity_claim
    assert len(PARAMETRIC_FREE_SP_CLAIM.parity_quantities) == 4
    assert PARAMETRIC_FREE_SP_CLAIM.reference_internal_quantities == ()


def test_fixed_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_parametric_fixed_sp_case)
    assert hints["r_case"] is RParametricFixedSpRecipe
    recipe_keys = set(RParametricFixedSpRecipe.__annotations__)
    payload_keys = set(RParametricFixedSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FIXED_SP_MGCV_KEYS)
    assert set(_FIXED_SP_MGCV_KEYS) <= payload_keys


def test_free_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_parametric_free_sp_case)
    assert hints["r_case"] is RParametricFreeSpRecipe
    recipe_keys = set(RParametricFreeSpRecipe.__annotations__)
    payload_keys = set(RParametricFreeSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FREE_SP_MGCV_KEYS)
    assert set(_FREE_SP_MGCV_KEYS) <= payload_keys


def test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _fixed_sp_recipe()
    payload = typing.cast(
        RParametricFixedSpPayload,
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
    with_payload = fit_parametric_fixed_sp_case(typing.cast(RParametricFixedSpRecipe, payload))
    recipe_only = fit_parametric_fixed_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.fit.eta, recipe_only.fit.eta)
    assert with_payload.edf_total > 0.0


def test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _free_sp_recipe()
    payload = typing.cast(
        RParametricFreeSpPayload,
        {
            **recipe,
            "eta": [0.0],
            "sp": [-999.0],
            "edf_total": -999.0,
            "term_edf": [-999.0],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with_payload = fit_parametric_free_sp_case(typing.cast(RParametricFreeSpRecipe, payload))
    recipe_only = fit_parametric_free_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.eta, recipe_only.eta)
    np.testing.assert_array_equal(with_payload.log_lambda, recipe_only.log_lambda)


def test_fixed_sp_edf_total_moves_with_the_smooth_penalty() -> None:
    recipe = _fixed_sp_recipe()
    base = fit_parametric_fixed_sp_case(recipe).edf_total
    stiffer = fit_parametric_fixed_sp_case({**recipe, "sp": [500.0]}).edf_total
    assert stiffer < base, "stiffening the smooth's own penalty must reduce edf_total"


def test_free_sp_edf_is_sensitive_to_the_smooth() -> None:
    recipe = _free_sp_recipe()
    fit = fit_parametric_free_sp_case(recipe)
    assert fit.edf_total > 0.0
    assert fit.edf_per_term["s(AttdAge)"] > 0.0
    # The parametric block is unpenalized -- its edf is exactly its own
    # column count regardless of the smooth's own selected lambda.
    assert fit.edf_per_term["FaceSize"] == pytest.approx(2.0)
    assert fit.edf_per_term["Smoke"] == pytest.approx(1.0)
    assert fit.edf_per_term["FaceSize:Smoke"] == pytest.approx(2.0)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_parametric_terms_builds_a_main_effect_per_factor_plus_the_interaction() -> None:
    terms = parametric_terms(3, 2)
    assert [t.label for t in terms] == ["FaceSize", "Smoke", "FaceSize:Smoke"]
    assert [t.basis for t in terms] == ["parametric"] * 3
    assert terms[0].levels == (3,)
    assert terms[1].levels == (2,)
    assert terms[2].levels == (3, 2)


def test_fixed_sp_model_spec_has_three_parametric_terms_plus_the_smooth() -> None:
    model = parametric_fixed_sp_model_spec(3, 2, tuple(_AGE_KNOTS))
    assert model.family == "gaussian"
    assert model.link == "identity"
    assert [t.basis for t in model.terms] == ["parametric", "parametric", "parametric", "cr"]
    assert model.terms[-1].label == "s(AttdAge)"


def test_free_sp_model_spec_also_uses_gaussian_identity() -> None:
    """Same family as the fixed-`sp` regime — ladder rung L5 (ADR-231)
    already closed the free-scale blocker before this slice was written
    (module docstring)."""
    model = parametric_free_sp_model_spec(3, 2, tuple(_AGE_KNOTS))
    assert model.family == "gaussian"
    assert model.link == "identity"


def test_fixed_sp_fit_rejects_a_wrong_block_count() -> None:
    recipe = _fixed_sp_recipe()
    with pytest.raises(PolarisValidationError, match="expected 1 sp value"):
        fit_parametric_fixed_sp_case({**recipe, "sp": [1.0, 2.0]})


def test_fixed_sp_comparison_gates_on_both_quantities() -> None:
    recipe = _fixed_sp_recipe()
    fit = fit_parametric_fixed_sp_case(recipe)
    good = typing.cast(
        RParametricFixedSpPayload,
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
    assert compare_parametric_fixed_sp_case(fit, good)["agrees"]
    edf_off = typing.cast(RParametricFixedSpPayload, {**good, "edf_total": fit.edf_total + 5.0})
    result = compare_parametric_fixed_sp_case(fit, edf_off)
    assert not result["agrees"]
    assert result["max_abs_eta_diff"] == pytest.approx(0.0, abs=1e-15)


def test_claim_sentences_name_their_tolerances() -> None:
    for claim in (PARAMETRIC_FIXED_SP_CLAIM, PARAMETRIC_FREE_SP_CLAIM):
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
    out = tmp_path / "gam_parametric_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_parametric_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RParametricFixedSpPayload, json.loads(out.read_text()))
    result = compare_parametric_fixed_sp_case(fit_parametric_fixed_sp_case(payload), payload)
    assert result["agrees"], result
    assert result["offset_gap"] == 0.0


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_free_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    out = tmp_path / "gam_parametric_free_sp_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_parametric_free_sp_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RParametricFreeSpPayload, json.loads(out.read_text()))
    fit = fit_parametric_free_sp_case(payload)
    result = compare_parametric_free_sp_case(fit, payload)
    assert result.agrees, result
    assert result.offset_gap < 1e-6


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_stage_a_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Stage A: the parametric block's own design against R's
    ``model.matrix()``, via the SHARED :func:`compare_term_extract` machinery
    (RTermPayload's shape, same as every other basis's Stage-A comparison in
    this module) -- no bespoke comparator needed since this script's own
    per-term export already matches that shape exactly."""
    from polaris_re.analytics.gam_stage_a import build_python_parametric_term, compare_term_extract
    from polaris_re.analytics.gam_term_spec import TermSpec

    out = tmp_path / "gam_parametric_stage_a_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_parametric_stage_a_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = json.loads(out.read_text())
    face = np.asarray(payload["face_group"], dtype=np.int64)
    smoke = np.asarray(payload["smoke_group"], dtype=np.int64)
    n_face = len(payload["face_levels"])
    n_smoke = len(payload["smoke_levels"])

    cases = {
        "FaceSize": (
            TermSpec(
                label="FaceSize", variables=("FaceSize",), basis="parametric", levels=(n_face,)
            ),
            (face,),
        ),
        "Smoke": (
            TermSpec(label="Smoke", variables=("Smoke",), basis="parametric", levels=(n_smoke,)),
            (smoke,),
        ),
        "FaceSize:Smoke": (
            TermSpec(
                label="FaceSize:Smoke",
                variables=("FaceSize", "Smoke"),
                basis="parametric",
                levels=(n_face, n_smoke),
            ),
            (face, smoke),
        ),
    }
    for label, (term, groups) in cases.items():
        extract = build_python_parametric_term(groups, term)
        comparison = compare_term_extract(extract, payload["param_terms"][label])
        assert comparison.agrees, (label, comparison)
        assert comparison.max_abs_design_diff == 0.0
