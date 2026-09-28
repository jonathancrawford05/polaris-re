"""Capability ladder slice 6 — ``cr`` + ``re`` + ``ti`` fit jointly against
``mgcv``, Stage B (``docs/PLAN_mgcv_capability_ladder.md``).

The provenance gate (ADR-193): every quantity both claims declare is
``INDEPENDENT``, and neither fit function's signature can structurally see
``mgcv``'s fit (the recipe types carry no ``eta``/``coef``/``mgcv_sp``/
``edf_total`` key).

**"A near-exact agreement is a suspicion before it is a result."** The
composition agrees with ``mgcv`` at float round-trip precision at fixed
``sp``, so this module carries the same two independence tests every
capability-ladder Stage-B module carries — every ``mgcv``-produced key
stripped from the payload still gives a bit-identical Polaris fit, and the
compared quantities measurably move when the term under test changes — plus
a closed-form check of the fixed-``sp`` fit against a direct penalized
least-squares solve.
"""

import json
import subprocess
import typing
from pathlib import Path

import numpy as np
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.analytics.gam_cr_re_ti_conformance import (
    CR_RE_TI_FIXED_SP_CLAIM,
    CR_RE_TI_FREE_SP_CLAIM,
    TERM_LABELS,
    RCrReTiFixedSpPayload,
    RCrReTiFixedSpRecipe,
    RCrReTiFreeSpPayload,
    RCrReTiFreeSpRecipe,
    compare_cr_re_ti_fixed_sp_case,
    compare_cr_re_ti_free_sp_case,
    cr_re_ti_model_spec,
    fit_cr_re_ti_fixed_sp_case,
    fit_cr_re_ti_free_sp_case,
)
from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import require_parity_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]

_AGE_KNOTS = [1.0, 2.0, 4.0, 7.0, 14.0, 18.0, 24.0, 35.0, 50.0, 70.0, 85.0, 90.0, 95.0]
_YEAR_KNOTS = [1.0, 2.0, 3.0, 5.0, 10.0, 21.0]
_N_LEVELS = 6
_SP = [2.0, 1.2, 1.5, 4.0]


def _base_recipe(n: int = 300, seed: int = 20260928) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    age = rng.uniform(1.0, 95.0, size=n)
    year = rng.uniform(1.0, 21.0, size=n)
    group = rng.integers(0, _N_LEVELS, size=n)
    level_effect = np.array([-0.5, -0.2, 0.05, 0.15, 0.35, 0.55])
    mu = (
        1.0
        + 0.6 * np.sin(age / 20.0)
        + level_effect[group]
        + 0.4 * np.sin(age / 15.0) * np.cos(year / 4.0)
    )
    y = mu + rng.normal(scale=0.3, size=n)
    return {
        "family": "gaussian",
        "link": "identity",
        "n": n,
        "n_levels": _N_LEVELS,
        "AttdAge": age.tolist(),
        "PolYear": year.tolist(),
        "group": group.tolist(),
        "y": y.tolist(),
        "age_knots": list(_AGE_KNOTS),
        "year_knots": list(_YEAR_KNOTS),
    }


def _fixed(**kw: object) -> RCrReTiFixedSpRecipe:
    return typing.cast(RCrReTiFixedSpRecipe, {**_base_recipe(), "sp_fixed": list(_SP), **kw})


def _free() -> RCrReTiFreeSpRecipe:
    return typing.cast(RCrReTiFreeSpRecipe, _base_recipe())


_MGCV_KEYS_FIXED = (
    "eta",
    "edf_total",
    "term_edf",
    "term_labels",
    "offset_gap",
    "coef",
    "converged",
)
_MGCV_KEYS_FREE = ("eta", "mgcv_sp", *_MGCV_KEYS_FIXED[1:])


# --------------------------------------------------------------------------
# Provenance (ADR-193 / ADR-228)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claim", "n_parity"), [(CR_RE_TI_FIXED_SP_CLAIM, 2), (CR_RE_TI_FREE_SP_CLAIM, 4)]
)
def test_claims_are_fully_parity_evidence(claim, n_parity: int) -> None:
    require_parity_evidence(claim.quantities, claim=claim.claim)
    assert claim.is_parity_claim
    assert len(claim.parity_quantities) == n_parity
    assert claim.reference_internal_quantities == ()
    assert "2e-2" in claim.claim
    assert "mgcv parity" not in claim.claim.lower()


def test_recipe_types_structurally_exclude_mgcvs_fit() -> None:
    assert typing.get_type_hints(fit_cr_re_ti_fixed_sp_case)["r_case"] is RCrReTiFixedSpRecipe
    assert typing.get_type_hints(fit_cr_re_ti_free_sp_case)["r_case"] is RCrReTiFreeSpRecipe
    assert set(RCrReTiFixedSpRecipe.__annotations__).isdisjoint(_MGCV_KEYS_FIXED)
    assert set(RCrReTiFreeSpRecipe.__annotations__).isdisjoint(_MGCV_KEYS_FREE)
    assert set(_MGCV_KEYS_FIXED) <= set(RCrReTiFixedSpPayload.__annotations__)
    assert set(_MGCV_KEYS_FREE) <= set(RCrReTiFreeSpPayload.__annotations__)


def test_fixed_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _fixed()
    polluted = typing.cast(
        RCrReTiFixedSpRecipe,
        {
            **recipe,
            "eta": [0.0],
            "edf_total": -999.0,
            "term_edf": [-999.0],
            "term_labels": ["x"],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    a = fit_cr_re_ti_fixed_sp_case(polluted)
    b = fit_cr_re_ti_fixed_sp_case(recipe)
    assert a.edf_total == b.edf_total
    np.testing.assert_array_equal(a.fit.eta, b.fit.eta)


def test_free_fit_is_unchanged_when_every_mgcv_key_is_stripped() -> None:
    recipe = _free()
    polluted = typing.cast(
        RCrReTiFreeSpRecipe,
        {
            **recipe,
            "eta": [0.0],
            "mgcv_sp": [-999.0],
            "edf_total": -999.0,
            "term_edf": [-999.0],
            "term_labels": ["x"],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    a = fit_cr_re_ti_free_sp_case(polluted)
    b = fit_cr_re_ti_free_sp_case(recipe)
    np.testing.assert_array_equal(a.eta, b.eta)
    np.testing.assert_array_equal(a.log_lambda, b.log_lambda)


# --------------------------------------------------------------------------
# Suspicion: the compared quantities must be sensitive to each term
# --------------------------------------------------------------------------


@pytest.mark.parametrize("block", [0, 1, 2, 3])
def test_fixed_edf_total_moves_with_each_penalty_block(block: int) -> None:
    base = fit_cr_re_ti_fixed_sp_case(_fixed()).edf_total
    sp = list(_SP)
    sp[block] *= 200.0
    stiffer = fit_cr_re_ti_fixed_sp_case(_fixed(sp_fixed=sp)).edf_total
    assert stiffer < base, f"stiffening penalty block {block} must reduce edf_total"


def test_ti_block_carries_real_signal() -> None:
    """Dropping the ti term must move eta — a zero-signal ti would agree with
    mgcv trivially, which is the vacuous-agreement failure this guards."""
    recipe = _fixed()
    full = fit_cr_re_ti_fixed_sp_case(recipe).fit.eta
    without_ti = fit_cr_re_ti_fixed_sp_case(_fixed(sp_fixed=[2.0, 1.2, 1e9, 1e9])).fit.eta
    assert np.max(np.abs(full - without_ti)) > 0.05


# --------------------------------------------------------------------------
# Assembly and closed form
# --------------------------------------------------------------------------


def test_assembled_design_has_the_composed_block_structure() -> None:
    # n=900 (the probe's own size): at n=300 a sparsely-supported ti basis
    # function adds a SECOND numerical null direction -- a data-sparsity
    # artefact, not a property of the composition.
    recipe = typing.cast(RCrReTiFixedSpRecipe, {**_base_recipe(900), "sp_fixed": list(_SP)})
    model = cr_re_ti_model_spec(
        "gaussian", "identity", tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS), _N_LEVELS
    )
    data = {
        "AttdAge": np.asarray(recipe["AttdAge"]),
        "PolYear": np.asarray(recipe["PolYear"]),
        "GroupFac": np.asarray(recipe["group"], dtype=np.int64),
    }
    design = assemble_model_design(model, data)
    # intercept + cr (12) + re (6) + ti (12 * 5)
    assert design["x"].shape == (recipe["n"], 1 + 12 + 6 + 60)
    assert len(design["penalty_blocks"]) == 4
    assert tuple(tb["label"] for tb in design["term_blocks"]) == TERM_LABELS
    # re's indicator columns sum to the intercept column: the composition's one
    # known, penalised collinearity (mgcv carries it identically).
    assert np.linalg.matrix_rank(design["x"]) == design["x"].shape[1] - 1


def test_fixed_fit_matches_a_direct_penalized_least_squares_solve() -> None:
    """Closed form: gaussian(identity) has no iteration, so the fit is
    ``(X'X + S)^-1 X'y`` exactly."""
    recipe = _fixed()
    model = cr_re_ti_model_spec(
        "gaussian", "identity", tuple(_AGE_KNOTS), tuple(_YEAR_KNOTS), _N_LEVELS
    )
    data = {
        "AttdAge": np.asarray(recipe["AttdAge"]),
        "PolYear": np.asarray(recipe["PolYear"]),
        "GroupFac": np.asarray(recipe["group"], dtype=np.int64),
    }
    design = assemble_model_design(model, data)
    x = design["x"]
    s = sum(sp * b for sp, b in zip(_SP, design["penalty_blocks"], strict=True))
    y = np.asarray(recipe["y"])
    beta = np.linalg.solve(x.T @ x + s, x.T @ y)
    np.testing.assert_allclose(
        fit_cr_re_ti_fixed_sp_case(recipe).fit.eta, x @ beta, rtol=0, atol=1e-9
    )


def test_fixed_fit_rejects_a_wrong_block_count() -> None:
    with pytest.raises(PolarisValidationError, match="expected 4 sp values"):
        fit_cr_re_ti_fixed_sp_case(_fixed(sp_fixed=[1.0, 2.0]))


def test_fixed_comparison_gates_on_both_quantities() -> None:
    recipe = _fixed()
    fit = fit_cr_re_ti_fixed_sp_case(recipe)
    good = typing.cast(
        RCrReTiFixedSpPayload,
        {
            **recipe,
            "eta": fit.fit.eta.tolist(),
            "edf_total": fit.edf_total,
            "term_edf": [0.0, 0.0, 0.0],
            "term_labels": list(TERM_LABELS),
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    assert compare_cr_re_ti_fixed_sp_case(fit, good).agrees
    bad_edf = typing.cast(RCrReTiFixedSpPayload, {**good, "edf_total": fit.edf_total + 5.0})
    assert not compare_cr_re_ti_fixed_sp_case(fit, bad_edf).agrees
    bad_eta = typing.cast(RCrReTiFixedSpPayload, {**good, "eta": (fit.fit.eta + 0.5).tolist()})
    assert not compare_cr_re_ti_fixed_sp_case(fit, bad_eta).agrees


def test_free_comparison_rejects_misaligned_term_labels() -> None:
    recipe = _free()
    fit = fit_cr_re_ti_free_sp_case(recipe)
    payload = typing.cast(
        RCrReTiFreeSpPayload,
        {
            **recipe,
            "eta": fit.eta.tolist(),
            "mgcv_sp": fit.lambda_.tolist(),
            "edf_total": fit.edf_total,
            "term_edf": [1.0, 1.0, 1.0],
            "term_labels": [TERM_LABELS[1], TERM_LABELS[0], TERM_LABELS[2]],
            "offset_gap": 0.0,
            "coef": [0.0],
            "converged": True,
        },
    )
    with pytest.raises(PolarisValidationError, match="out of alignment"):
        compare_cr_re_ti_free_sp_case(fit, payload)
    aligned = typing.cast(RCrReTiFreeSpPayload, {**payload, "term_labels": list(TERM_LABELS)})
    result = compare_cr_re_ti_free_sp_case(fit, aligned)
    assert result.max_abs_eta_diff == 0.0
    assert result.max_abs_log10_sp_diff == pytest.approx(0.0, abs=1e-12)
    assert len(result.per_block_log10_sp_diff) == 4


# --------------------------------------------------------------------------
# End-to-end round trip, gated on R (tier 1 — a HYPOTHESIS; tier 3 settles it)
# --------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_round_trip_against_mgcv(tmp_path: Path) -> None:
    out = tmp_path / "gam_cr_re_ti_probe.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "gam_cr_re_ti_probe.R"), str(out)],
        check=True,
        capture_output=True,
    )
    cases = json.loads(out.read_text())["cases"]

    fixed = typing.cast(RCrReTiFixedSpPayload, cases["gaussian_fixed"])
    cf = compare_cr_re_ti_fixed_sp_case(fit_cr_re_ti_fixed_sp_case(fixed), fixed)
    assert cf.agrees, cf
    assert cf.offset_gap == 0.0

    for name in ("gaussian_free", "poisson_free"):
        payload = typing.cast(RCrReTiFreeSpPayload, cases[name])
        c = compare_cr_re_ti_free_sp_case(fit_cr_re_ti_free_sp_case(payload), payload)
        assert c.agrees, (name, c)
        assert c.offset_gap < 1e-6
