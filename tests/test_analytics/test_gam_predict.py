"""R-free tests for ``gam_predict`` — preview epic Slice P1 (ADR-249).

Polaris's own invariants, checkable without ``mgcv``: the stored-state rebuild is
bit-identical to ``assemble_model_design`` on the training rows; a natural cubic
spline reproduces a linear function everywhere including beyond the end knots
(closed form); and a row's design is independent of the other rows. The
INDEPENDENT comparison against ``predict.gam`` is
``gam_predict_conformance.py`` / ``scripts/gam_predict_probe.R``.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_basis_cr import cr_basis
from polaris_re.analytics.gam_model import assemble_model_design, fit_polaris_gam
from polaris_re.analytics.gam_predict import fit_term_state, predict_design
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisValidationError

_X_KNOTS = (0.0, 1.0, 2.5, 4.0, 6.0, 8.0, 10.0)
_Z_KNOTS = (0.0, 1.0, 2.0, 3.0, 5.0)


def _data(n: int = 120, seed: int = 7) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {
        "x": rng.uniform(0.0, 10.0, n),
        "z": rng.uniform(0.0, 5.0, n),
        "w": rng.uniform(-2.0, 2.0, n),
        "f": rng.integers(0, 3, n),
        "g": rng.integers(0, 2, n),
        "off": rng.uniform(-0.3, 0.3, n),
    }


def _terms(*, with_default_knots: bool = False) -> tuple[TermSpec, ...]:
    kx = None if with_default_knots else (("x", _X_KNOTS),)
    return (
        TermSpec(label="s(x)", variables=("x",), basis="cr", k=(7,), knots=kx),
        TermSpec(label="s(x,by=w)", variables=("x",), basis="cr", k=(7,), knots=kx, by="w"),
        TermSpec(
            label="ti(x,z)",
            variables=("x", "z"),
            basis="ti",
            k=(7, 5),
            knots=None if with_default_knots else (("x", _X_KNOTS), ("z", _Z_KNOTS)),
        ),
        *factor_by_terms(base_label="s(x,by=f)", variable="x", k=7, by_factor="f", n_levels=3),
        TermSpec(label="s(f)", variables=("f",), basis="re", n_levels=3),
        TermSpec(label="g", variables=("g",), basis="parametric", levels=(2,)),
        TermSpec(
            label="s(g,z)",
            variables=("g", "z"),
            basis="sz",
            k=(5,),
            knots=(("z", _Z_KNOTS),),
            n_levels=2,
        ),
    )


@pytest.mark.parametrize("with_default_knots", [False, True])
def test_training_design_through_stored_state_is_bit_identical(with_default_knots: bool) -> None:
    """The refactor guard: every basis, rebuilt from the stored knots and
    constraint, equals ``assemble_model_design``'s training design EXACTLY."""
    model = ModelSpec(
        family="gaussian", link="identity", terms=_terms(with_default_knots=with_default_knots)
    )
    data = _data()
    states = tuple(fit_term_state(t, data) for t in model.terms)
    np.testing.assert_array_equal(
        predict_design(model, states, data), assemble_model_design(model, data)["x"]
    )


def test_design_rows_are_independent_of_the_other_rows() -> None:
    """A new row's design depends only on the stored state, not on which other
    rows are predicted with it — the property a training-data-recomputed
    constraint would violate."""
    model = ModelSpec(family="gaussian", link="identity", terms=_terms(with_default_knots=True))
    data = _data()
    states = tuple(fit_term_state(t, data) for t in model.terms)
    full = predict_design(model, states, data)
    idx = np.array([5, 17, 3])
    subset = predict_design(model, states, {k: v[idx] for k, v in data.items()})
    np.testing.assert_array_equal(subset, full[idx])


def test_natural_cubic_spline_reproduces_a_linear_function_beyond_the_end_knots() -> None:
    """Closed form: with ``beta_j = a + b * knot_j`` the natural spline IS
    ``a + b x``, and linear extrapolation along the end slope continues it."""
    knots = np.asarray(_X_KNOTS)
    a, b = 1.5, -0.7
    x = np.array([-4.0, -0.001, 0.0, 3.3, 10.0, 10.001, 15.0])
    design, _ = cr_basis(x, knots)
    np.testing.assert_allclose(design @ (a + b * knots), a + b * x, atol=1e-12)


def test_extrapolation_is_linear_outside_the_knots() -> None:
    knots = np.asarray(_X_KNOTS)
    x = np.array([10.0, 11.0, 12.0, 13.5, -1.0, -2.0, -3.0])
    design, _ = cr_basis(x, knots)
    rng = np.random.default_rng(0)
    beta = rng.normal(size=knots.size)
    f = design @ beta
    np.testing.assert_allclose(f[1] - f[0], f[2] - f[1], atol=1e-12)
    np.testing.assert_allclose((f[3] - f[2]) / 1.5, f[2] - f[1], atol=1e-12)
    np.testing.assert_allclose(f[5] - f[4], f[6] - f[5], atol=1e-12)
    # continuity at the end knot: value and slope match the in-range cubic
    eps = 1e-6
    inner, _ = cr_basis(np.array([10.0 - eps, 10.0, 10.0 + eps]), knots)
    g = inner @ beta
    np.testing.assert_allclose(g[2] - g[1], g[1] - g[0], rtol=1e-4, atol=1e-9)


def test_fit_then_predict_at_training_rows_equals_eta() -> None:
    data = _data(n=150)
    rng = np.random.default_rng(1)
    y = np.sin(data["x"]) + 0.2 * data["w"] + rng.normal(0, 0.3, 150)
    terms = (
        TermSpec(label="s(x)", variables=("x",), basis="cr", k=(7,), knots=(("x", _X_KNOTS),)),
        TermSpec(label="s(f)", variables=("f",), basis="re", n_levels=3),
    )
    model = ModelSpec(family="gaussian", link="identity", terms=terms, offset_column="off")
    fit = fit_polaris_gam(model, data, y)
    np.testing.assert_allclose(fit.predict(data, "link"), fit.eta, rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        fit.predict(data, "response"), fit.predict(data, "link"), rtol=0, atol=0
    )


def test_response_scale_applies_the_inverse_link() -> None:
    data = _data(n=150)
    rng = np.random.default_rng(2)
    y = rng.poisson(np.exp(0.3 * np.sin(data["x"]) + 0.5)).astype(np.float64)
    model = ModelSpec(
        family="poisson",
        link="log",
        terms=(
            TermSpec(label="s(x)", variables=("x",), basis="cr", k=(7,), knots=(("x", _X_KNOTS),)),
        ),
    )
    fit = fit_polaris_gam(model, data, y)
    new = {"x": np.array([-2.0, 3.0, 12.0])}
    np.testing.assert_allclose(fit.predict(new, "response"), np.exp(fit.predict(new, "link")))


def test_unseen_factor_level_raises_and_missing_offset_raises() -> None:
    data = _data(n=100)
    y = data["x"] * 0.1 + np.random.default_rng(3).normal(0, 0.2, 100)
    terms = (TermSpec(label="s(f)", variables=("f",), basis="re", n_levels=3),)
    model = ModelSpec(family="gaussian", link="identity", terms=terms, offset_column="off")
    fit = fit_polaris_gam(model, data, y)
    with pytest.raises(PolarisValidationError, match="unseen level"):
        fit.predict({"f": np.array([0, 3]), "off": np.zeros(2)})
    with pytest.raises(PolarisValidationError, match="offset"):
        fit.predict({"f": np.array([0, 1])})
    with pytest.raises(PolarisValidationError, match="type must be"):
        fit.predict(data, "terms")  # type: ignore[arg-type]


def test_predict_term_design_rejects_an_unsupported_basis() -> None:
    with pytest.raises(PolarisValidationError, match="does not support"):
        fit_term_state(TermSpec(label="raw", variables=("x",), basis="raw"), _data())
