"""Rank pivoting (parity-engine Slice 9, ADR-255).

Own-criterion checks (MEASUREMENT, not parity): closed forms for the null directions and
for the pivoted covariance. The INDEPENDENT comparison against ``mgcv`` is
``gam_predict_conformance`` / ``polaris_re.gam.formula_conformance`` (tier 3)."""

import warnings

import numpy as np
import pytest

import polaris_re.analytics.gam_rank_pivot as rank_pivot
from polaris_re.analytics.gam_model import assemble_model_design, fit_polaris_gam, pivot_design
from polaris_re.analytics.gam_predict import predict_design
from polaris_re.analytics.gam_rank_pivot import (
    choose_pivot_columns,
    pivot_out,
    unidentified_directions,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisComputationError, PolarisRankDeficiencyWarning


def _model() -> tuple[ModelSpec, dict[str, np.ndarray], np.ndarray]:
    rng = np.random.default_rng(11)
    n = 300
    x = rng.uniform(0, 10, n)
    f = rng.integers(0, 3, n)
    y = np.sin(x + 0.5 * f) + rng.normal(0, 0.3, n)
    model = ModelSpec(
        family="gaussian",
        link="identity",
        terms=(
            TermSpec(label="s(x)", variables=("x",), basis="cr", k=(7,)),
            *factor_by_terms(base_label="s(x):f", variable="x", k=7, by_factor="f", n_levels=3),
        ),
    )
    return model, {"x": x, "f": f}, y


def test_duplicate_column_direction_is_found_in_closed_form() -> None:
    t = np.linspace(0.0, 1.0, 20)
    x = np.column_stack([np.ones(20), t, t])
    v = unidentified_directions(x, [])
    assert v.shape == (3, 1)
    np.testing.assert_allclose(np.abs(v[:, 0]), [0.0, 2**-0.5, 2**-0.5], atol=1e-12)
    x_kept, blocks, kept = pivot_out(x, [])
    assert x_kept.shape == (20, 2) and len(kept) == 2 and blocks == ()
    # penalising one copy identifies the pair: nothing is pivoted
    pen = np.zeros((3, 3))
    pen[2, 2] = 1.0
    assert unidentified_directions(x, [pen]).shape[1] == 0
    assert pivot_out(x, [pen])[2] == (0, 1, 2)


def test_the_smooth_plus_factor_by_design_loses_exactly_one_coefficient() -> None:
    model, data, _ = _model()
    design = assemble_model_design(model, data)
    # X alone is deficient in several directions (the penalised ones are identified through
    # S); exactly one lies in the penalty null space AND in the null space of X
    assert np.linalg.matrix_rank(design["x"]) < design["x"].shape[1]
    assert unidentified_directions(design["x"], design["penalty_blocks"]).shape[1] == 1
    pivoted = pivot_design(design)
    assert pivoted["x"].shape[1] == design["x"].shape[1] - 1
    assert pivoted["full_width"] == design["x"].shape[1]
    assert pivoted["term_blocks"] == design["term_blocks"]  # the full layout is kept
    # the identified design is returned unchanged
    ident = ModelSpec(family="gaussian", link="identity", terms=model.terms[:1])
    d = assemble_model_design(ident, data)
    assert pivot_design(d) is d


def test_pivoted_fit_converges_and_the_pivot_choice_moves_no_vp_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, data, y = _model()
    ref = fit_polaris_gam(model, data, y)
    assert ref.converged and len(ref.pivoted_columns) == 1
    results = []
    for column in (3, 12, 20):
        monkeypatch.setattr(rank_pivot, "choose_pivot_columns", lambda v, c=column: (c,))
        alt = fit_polaris_gam(model, data, y)
        assert alt.pivoted_columns == (column,)
        results.append(alt)
    for alt in results:
        np.testing.assert_allclose(alt.eta, ref.eta, atol=1e-5)
        assert abs(alt.edf_total - ref.edf_total) < 1e-3
        _, se_ref = ref.predict(data, se_fit=True)
        _, se_alt = alt.predict(data, se_fit=True)
        np.testing.assert_allclose(se_alt, se_ref, rtol=1e-3)


def test_vp_projection_equals_the_moore_penrose_form_on_the_full_design() -> None:
    """Closed form: for an estimable function x'beta, Var = phi x' (X'WX+S)^+ x on the
    full (singular) information — the pivoted covariance projects to the same number."""
    model, data, y = _model()
    fit = fit_polaris_gam(model, data, y)
    full = assemble_model_design(model, data)
    lam = 10.0**fit.log_lambda
    s_total = sum(lw * b for lw, b in zip(lam, full["penalty_blocks"], strict=True))
    info = full["x"].T @ full["x"] + s_total  # unit weights (identity-link Gaussian)
    x_new = predict_design(model, fit.term_states, data)
    phi = float(fit.dispersion.fletcher)
    pinv_cov = phi * np.linalg.pinv(info, rcond=1e-10)
    se_pinv = np.sqrt(np.einsum("ij,jk,ik->i", x_new, pinv_cov, x_new))
    _, se = fit.predict(data, se_fit=True)
    np.testing.assert_allclose(se, se_pinv, rtol=1e-6)
    v = fit.vcov()
    assert v.shape == (full["x"].shape[1],) * 2
    (dropped,) = fit.pivoted_columns
    assert np.all(v[dropped] == 0.0) and np.all(v[:, dropped] == 0.0)
    np.testing.assert_allclose(x_new @ fit.coef_full, fit.eta, atol=1e-10)


def test_unconditional_covariance_is_refused_for_a_pivoted_fit() -> None:
    model, data, y = _model()
    fit = fit_polaris_gam(model, data, y)
    with pytest.raises(PolarisComputationError, match="pivoted-out"):
        fit.vcov(unconditional=True)
    with pytest.raises(PolarisComputationError, match="pivoted-out"):
        fit.predict(data, se_fit=True, unconditional=True)


def test_per_term_edf_sums_to_the_total_less_the_intercept() -> None:
    model, data, y = _model()
    fit = fit_polaris_gam(model, data, y)
    assert abs(sum(fit.edf_per_term.values()) + 1.0 - fit.edf_total) < 1e-8


def test_the_pivot_choice_is_not_decided_by_rounding_noise() -> None:
    """Two tier-3 runs of identical code once eliminated different columns, because the
    candidate rows had equal norms in exact arithmetic. Ties go to the highest index and
    the choice is stable under perturbations far above rounding noise."""
    model, data, _ = _model()
    design = assemble_model_design(model, data)
    v = unidentified_directions(design["x"], design["penalty_blocks"])
    base = choose_pivot_columns(v)
    rng = np.random.default_rng(0)
    for _ in range(25):
        noisy = v * (1.0 + 1e-12 * rng.standard_normal(v.shape))
        assert choose_pivot_columns(noisy) == base
    # an exact tie between rows resolves to the highest index
    tied = np.zeros((6, 1))
    tied[[1, 3, 4], 0] = 0.5
    assert choose_pivot_columns(tied) == (4,)
    # two independent directions: two distinct rows, V[D] invertible
    two = np.linalg.qr(rng.standard_normal((8, 2)))[0]
    chosen = choose_pivot_columns(two)
    assert len(set(chosen)) == 2 and abs(np.linalg.det(two[list(chosen)])) > 1e-6


def test_a_rank_deficient_specification_warns_once_and_names_the_term() -> None:
    model, data, y = _model()
    with pytest.warns(PolarisRankDeficiencyWarning, match=r"1 redundant direction") as rec:
        fit_polaris_gam(model, data, y)
    assert len([w for w in rec if issubclass(w.category, PolarisRankDeficiencyWarning)]) == 1
    assert "s(x)" in str(rec[0].message)
    assert rec[0].filename == __file__  # attributed to the caller, not to the library


def test_an_identified_specification_does_not_warn() -> None:
    model, data, y = _model()
    ident = ModelSpec(family="gaussian", link="identity", terms=model.terms[:1])
    with warnings.catch_warnings():
        warnings.simplefilter("error", PolarisRankDeficiencyWarning)
        fit_polaris_gam(ident, data, y)
