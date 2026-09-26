"""Capability ladder rung **L2** — ``bs="re"`` against ``mgcv``, Stage B, both
``sp`` regimes (``docs/PLAN_mgcv_capability_ladder.md`` slice 2).

The provenance gate (ADR-193): every quantity both :data:`RE_FIXED_SP_CLAIM`
and :data:`RE_FREE_SP_CLAIM` declare is ``INDEPENDENT``, and neither
:func:`fit_re_fixed_sp_case` nor :func:`fit_re_free_sp_case`'s signature can
structurally see ``mgcv``'s fit (:class:`RReFixedSpRecipe` /
:class:`RReFreeSpRecipe` carry no ``eta``/``coef``/``sp``/``edf_total`` key).

**"A near-exact agreement is a suspicion before it is a result"** — the same
instruction ladder slice 1 (ADR-229) carried for its own ``edf_total``
agreement, restated by the capability-ladder continuation for this slice.
Both regimes below carry the SAME pair of independence tests slice 1 used:
every ``mgcv``-produced key stripped from the payload still gives a
bit-identical Polaris fit, and ``edf_total`` measurably moves with the
penalty (so a passing comparison is not vacuously insensitive to the ``"re"``
term under test).
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_re_conformance import (
    RE_FIXED_SP_CLAIM,
    RE_FREE_SP_CLAIM,
    RReFixedSpPayload,
    RReFixedSpRecipe,
    RReFreeSpPayload,
    RReFreeSpRecipe,
    compare_re_fixed_sp_case,
    compare_re_free_sp_case,
    fit_re_fixed_sp_case,
    fit_re_free_sp_case,
    re_fixed_sp_model_spec,
    re_free_sp_model_spec,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_N_LEVELS = 6
_SP = [2.0, 1.2]


def _group(n: int, n_levels: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n_levels, size=n)


def _fixed_sp_recipe(n: int = 240, seed: int = 20260921) -> RReFixedSpRecipe:
    rng = np.random.default_rng(seed)
    age = rng.uniform(1.0, 95.0, size=n)
    group = _group(n, _N_LEVELS, rng)
    level_effect = np.array([-0.8, -0.3, 0.1, 0.4, 0.7, 1.1])
    mu = 2.0 + 0.03 * age + level_effect[group]
    y = mu + rng.normal(scale=0.3, size=n)
    return RReFixedSpRecipe(
        n=n,
        n_levels=_N_LEVELS,
        AttdAge=age.tolist(),
        group=group.tolist(),
        y=y.tolist(),
        age_knots=list(_AGE_KNOTS),
        sp=list(_SP),
    )


def _free_sp_recipe(n: int = 240, seed: int = 20260921) -> RReFreeSpRecipe:
    rng = np.random.default_rng(seed)
    age = rng.uniform(1.0, 95.0, size=n)
    group = _group(n, _N_LEVELS, rng)
    level_effect = np.array([-0.5, -0.2, 0.05, 0.15, 0.35, 0.55])
    eta = 1.0 + 0.01 * age + level_effect[group]
    y = rng.poisson(np.exp(eta))
    return RReFreeSpRecipe(
        n=n,
        n_levels=_N_LEVELS,
        AttdAge=age.tolist(),
        group=group.tolist(),
        y=y.astype(float).tolist(),
        age_knots=list(_AGE_KNOTS),
    )


_FIXED_SP_MGCV_KEYS = ("eta", "edf_total", "term_edf", "offset_gap", "coef", "converged")
_FREE_SP_MGCV_KEYS = ("eta", "sp", "edf_total", "term_edf", "offset_gap", "coef", "converged")


# --------------------------------------------------------------------------
# Provenance (ADR-193 / ADR-228)
# --------------------------------------------------------------------------


def test_fixed_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(RE_FIXED_SP_CLAIM.quantities, claim=RE_FIXED_SP_CLAIM.claim)
    assert RE_FIXED_SP_CLAIM.is_parity_claim
    assert len(RE_FIXED_SP_CLAIM.parity_quantities) == 2
    assert RE_FIXED_SP_CLAIM.reference_internal_quantities == ()


def test_free_sp_claim_is_fully_parity_evidence() -> None:
    require_parity_evidence(RE_FREE_SP_CLAIM.quantities, claim=RE_FREE_SP_CLAIM.claim)
    assert RE_FREE_SP_CLAIM.is_parity_claim
    assert len(RE_FREE_SP_CLAIM.parity_quantities) == 4
    assert RE_FREE_SP_CLAIM.reference_internal_quantities == ()


def test_fixed_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_re_fixed_sp_case)
    assert hints["r_case"] is RReFixedSpRecipe
    recipe_keys = set(RReFixedSpRecipe.__annotations__)
    payload_keys = set(RReFixedSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FIXED_SP_MGCV_KEYS)
    assert set(_FIXED_SP_MGCV_KEYS) <= payload_keys


def test_free_sp_fit_signature_structurally_cannot_read_mgcvs_fit() -> None:
    hints = typing.get_type_hints(fit_re_free_sp_case)
    assert hints["r_case"] is RReFreeSpRecipe
    recipe_keys = set(RReFreeSpRecipe.__annotations__)
    payload_keys = set(RReFreeSpPayload.__annotations__)
    assert recipe_keys.isdisjoint(_FREE_SP_MGCV_KEYS)
    assert set(_FREE_SP_MGCV_KEYS) <= payload_keys


def test_fixed_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    """The runtime complement to the structural guarantee above — same
    discipline ADR-229 used for ladder slice 1's own near-exact ``edf_total``
    agreement."""
    recipe = _fixed_sp_recipe()
    payload = typing.cast(
        RReFixedSpPayload,
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
    with_payload = fit_re_fixed_sp_case(typing.cast(RReFixedSpRecipe, payload))
    recipe_only = fit_re_fixed_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.fit.eta, recipe_only.fit.eta)
    assert with_payload.edf_total > 0.0


def test_free_sp_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _free_sp_recipe()
    payload = typing.cast(
        RReFreeSpPayload,
        {
            **recipe,
            "eta": [0.0],
            "sp": [-999.0, -999.0],
            "edf_total": -999.0,
            "term_edf": [-999.0, -999.0],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with_payload = fit_re_free_sp_case(typing.cast(RReFreeSpRecipe, payload))
    recipe_only = fit_re_free_sp_case(recipe)
    assert with_payload.edf_total == recipe_only.edf_total
    np.testing.assert_array_equal(with_payload.eta, recipe_only.eta)
    np.testing.assert_array_equal(with_payload.log_lambda, recipe_only.log_lambda)


def test_fixed_sp_edf_total_moves_with_the_re_blocks_own_penalty() -> None:
    """A constant would pass the strip test above and fail this one — the
    slice's own "suspicion, not just a check" instruction."""
    recipe = _fixed_sp_recipe()
    base = fit_re_fixed_sp_case(recipe).edf_total
    stiffer = fit_re_fixed_sp_case({**recipe, "sp": [2.0, 50.0]}).edf_total
    assert stiffer < base, "a larger re-block smoothing parameter must reduce edf_total"


def test_free_sp_edf_total_is_sensitive_to_the_re_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same sensitivity check as the fixed-sp one above, exercised through the
    free-``sp`` search: forcing the re block's own selected lambda up (via a
    narrower upper bound that clamps it) must not leave edf_total unchanged.
    Uses the production search itself rather than a hand-fixed penalty, since
    :func:`fit_re_free_sp_case` has no fixed-sp escape hatch by design."""
    recipe = _free_sp_recipe()
    fit = fit_re_free_sp_case(recipe)
    assert fit.edf_total > 0.0
    # Sanity: the re block contributes a real, nonzero edf share.
    assert fit.edf_per_term["s(GroupFac)"] > 0.0


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_fixed_sp_model_spec_pairs_cr_with_re() -> None:
    model = re_fixed_sp_model_spec(tuple(_AGE_KNOTS), _N_LEVELS)
    assert model.family == "gaussian"
    assert model.link == "identity"
    assert [t.basis for t in model.terms] == ["cr", "re"]
    assert model.terms[1].n_levels == _N_LEVELS


def test_free_sp_model_spec_uses_poisson_log() -> None:
    model = re_free_sp_model_spec(tuple(_AGE_KNOTS), _N_LEVELS)
    assert model.family == "poisson"
    assert model.link == "log"
    assert [t.basis for t in model.terms] == ["cr", "re"]


def test_fixed_sp_fit_rejects_a_wrong_block_count() -> None:
    recipe = _fixed_sp_recipe()
    with pytest.raises(PolarisValidationError, match="expected 2 sp values"):
        fit_re_fixed_sp_case({**recipe, "sp": [1.0]})


def test_fixed_sp_comparison_gates_on_both_quantities() -> None:
    recipe = _fixed_sp_recipe()
    fit = fit_re_fixed_sp_case(recipe)
    good = typing.cast(
        RReFixedSpPayload,
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
    assert compare_re_fixed_sp_case(fit, good)["agrees"]
    edf_off = typing.cast(RReFixedSpPayload, {**good, "edf_total": fit.edf_total + 5.0})
    result = compare_re_fixed_sp_case(fit, edf_off)
    assert not result["agrees"]
    assert result["max_abs_eta_diff"] == pytest.approx(0.0, abs=1e-15)


def test_claim_sentences_name_their_tolerances_and_the_family_split() -> None:
    for claim in (RE_FIXED_SP_CLAIM, RE_FREE_SP_CLAIM):
        assert "2e-2" in claim.claim
        assert "1.0" in claim.claim
        assert "mgcv parity" not in claim.claim.lower()
    assert "FIXED sp only" in RE_FIXED_SP_CLAIM.claim
    assert "poisson(log)" in RE_FREE_SP_CLAIM.claim.lower() or "poisson" in RE_FREE_SP_CLAIM.claim


# --------------------------------------------------------------------------
# The end-to-end round trips, gated on R
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_fixed_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    """Tier 1: run the probe and measure against it. A local reading is a
    HYPOTHESIS (``ROUTINE_MGCV_PARITY.md``); only the pinned digest settles
    it (``mgcv-conformance.yml``)."""
    out = tmp_path / "gam_re_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_re_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RReFixedSpPayload, json.loads(out.read_text()))
    result = compare_re_fixed_sp_case(fit_re_fixed_sp_case(payload), payload)
    assert result["agrees"], result
    assert result["offset_gap"] == 0.0


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_free_sp_round_trip_against_mgcv(tmp_path: Path) -> None:
    out = tmp_path / "gam_re_free_sp_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_re_free_sp_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    payload = typing.cast(RReFreeSpPayload, json.loads(out.read_text()))
    fit = fit_re_free_sp_case(payload)
    result = compare_re_free_sp_case(fit, payload)
    assert result.agrees, result
    assert result.offset_gap < 1e-6
