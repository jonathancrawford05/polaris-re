"""R-free tests for ``vcov`` / ``predict(se_fit=True)`` — preview epic Slice P2
(ADR-250).

These are Polaris's own closed-form invariants (MEASUREMENT, own criterion — not
parity). The INDEPENDENT comparison against ``mgcv``'s ``vcov`` and
``predict.gam(se.fit=TRUE)`` is ``gam_predict_conformance.py`` /
``scripts/gam_predict_probe.R``.
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_model import (
    PolarisGAMFit,
    assemble_model_design,
    fit_polaris_gam,
    resolve_family,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.analytics.gam_vcov import coefficient_covariance, linear_predictor_se
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError


def _cr(label: str, var: str, k: int) -> TermSpec:
    return TermSpec(label=label, variables=(var,), basis="cr", k=(k,))


def _gaussian_fit(n: int = 200, seed: int = 11) -> tuple[PolarisGAMFit, dict[str, np.ndarray]]:
    rng = np.random.default_rng(seed)
    data = {"x": rng.uniform(0, 10, n), "z": rng.uniform(0, 5, n)}
    y = np.sin(data["x"]) + 0.2 * data["z"] + rng.normal(0, 0.3, n)
    model = ModelSpec(
        family="gaussian",
        link="identity",
        terms=(_cr("s(x)", "x", 8), _cr("s(z)", "z", 6)),
    )
    return fit_polaris_gam(model, data, y), data


def _poisson_fit(n: int = 300, seed: int = 5) -> tuple[PolarisGAMFit, dict[str, np.ndarray]]:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 10, n)
    off = rng.uniform(0.0, 1.0, n)
    data = {"x": x, "off": off}
    y = rng.poisson(np.exp(off + 0.5 + 0.4 * np.sin(x / 2))).astype(np.float64)
    model = ModelSpec(
        family="poisson", link="log", terms=(_cr("s(x)", "x", 8),), offset_column="off"
    )
    return fit_polaris_gam(model, data, y), data


def _penalized_information(fit: PolarisGAMFit) -> np.ndarray:
    x = fit.design["x"]
    s = sum(
        10.0**ll * b for ll, b in zip(fit.log_lambda, fit.design["penalty_blocks"], strict=True)
    )
    return np.asarray(x.T @ x + s)


def test_gaussian_vp_is_phi_times_penalized_information_inverse() -> None:
    fit, _ = _gaussian_fit()
    expected = fit.dispersion.fletcher * np.linalg.inv(_penalized_information(fit))
    np.testing.assert_allclose(fit.vcov(), expected, rtol=1e-9, atol=1e-12)


def test_vp_is_symmetric_positive_definite() -> None:
    fit, _ = _gaussian_fit()
    vp = fit.vcov()
    np.testing.assert_allclose(vp, vp.T, atol=1e-14)
    assert np.linalg.eigvalsh(vp)[0] > 0.0


def test_trace_of_influence_matrix_equals_edf_total() -> None:
    """tr(W X (X'WX+S)^-1 X') = edf_total: ties the covariance's information matrix
    to the EDF the fit reports, from the training rows (Gaussian: W = I)."""
    fit, data = _gaussian_fit()
    _, se = fit.predict(data, "link", se_fit=True)
    assert float(np.sum(se**2) / fit.dispersion.fletcher) == pytest.approx(fit.edf_total, rel=1e-9)


def test_se_fit_is_sqrt_of_projected_variance() -> None:
    fit, _ = _gaussian_fit()
    new = {"x": np.array([1.0, 4.0, 9.0]), "z": np.array([0.5, 2.0, 4.5])}
    fitted, se = fit.predict(new, "link", se_fit=True)
    np.testing.assert_allclose(fitted, fit.predict(new, "link"))
    from polaris_re.analytics.gam_predict import predict_design

    x_new = predict_design(fit.model, fit.term_states, new)
    np.testing.assert_allclose(se**2, np.diag(x_new @ fit.vcov() @ x_new.T), rtol=1e-10, atol=1e-14)
    np.testing.assert_allclose(se, linear_predictor_se(x_new, fit.vcov()))


def test_fixed_dispersion_family_has_unit_scale() -> None:
    fit, _ = _poisson_fit()
    expected = np.linalg.inv(_poisson_information(fit))
    np.testing.assert_allclose(fit.vcov(), expected, rtol=1e-8, atol=1e-12)


def _poisson_information(fit: PolarisGAMFit) -> np.ndarray:
    # canonical log link: Newton weights == Fisher weights == mu
    x = fit.design["x"]
    mu = np.exp(fit.eta)
    s = sum(
        10.0**ll * b for ll, b in zip(fit.log_lambda, fit.design["penalty_blocks"], strict=True)
    )
    return np.asarray(x.T @ (mu[:, None] * x) + s)


def test_response_scale_se_is_the_delta_method_and_offset_adds_no_variance() -> None:
    fit, _ = _poisson_fit()
    new = {"x": np.array([2.0, 5.0]), "off": np.array([0.0, 3.0])}
    eta, se_link = fit.predict(new, "link", se_fit=True)
    mu, se_resp = fit.predict(new, "response", se_fit=True)
    np.testing.assert_allclose(mu, np.exp(eta))
    np.testing.assert_allclose(se_resp, se_link * np.exp(eta), rtol=1e-12)
    # the offset moves eta by 3 but not the link-scale variance
    _, se_same_x = fit.predict(
        {"x": np.array([2.0, 2.0]), "off": np.array([0.0, 3.0])}, "link", se_fit=True
    )
    assert se_same_x[0] == pytest.approx(se_same_x[1], rel=1e-12)


def test_unconditional_covariance_is_vp_plus_a_psd_correction() -> None:
    fit, _ = _poisson_fit()
    vp, vc = fit.vcov(), fit.vcov(unconditional=True)
    corr = vc - vp
    np.testing.assert_allclose(corr, corr.T, atol=1e-12)
    assert np.linalg.eigvalsh((corr + corr.T) / 2.0)[0] > -1e-9 * np.abs(corr).max()
    assert np.all(np.diag(vc) >= np.diag(vp) - 1e-14)
    assert np.diag(vc).sum() > np.diag(vp).sum()


def test_unconditional_se_is_at_least_conditional() -> None:
    fit, data = _gaussian_fit()
    _, se = fit.predict(data, "link", se_fit=True)
    _, se_u = fit.predict(data, "link", se_fit=True, unconditional=True)
    assert np.all(se_u >= se - 1e-12)


def test_scale_enters_vp_linearly_and_the_second_order_term_linearly() -> None:
    """Pins where the scale is applied (PLAN P2, third bullet): Vp ~ phi, the
    scale-free J Vrho J' term does not move, the V'' term ~ phi."""
    fit, _ = _gaussian_fit()
    assert fit.y is not None
    kwargs = dict(
        y=fit.y,
        x=fit.design["x"],
        family=resolve_family("gaussian", "identity"),
        penalty_blocks=fit.design["penalty_blocks"],
        log10_lambda=fit.log_lambda,
        coef=fit.coef,
        offset=None,
        weights=None,
        unconditional=True,
    )
    a = coefficient_covariance(scale=1.0, **kwargs)  # type: ignore[arg-type]
    b = coefficient_covariance(scale=3.5, **kwargs)  # type: ignore[arg-type]
    np.testing.assert_allclose(b.vp, 3.5 * a.vp, rtol=1e-12)
    assert a.first_order is not None and b.first_order is not None
    np.testing.assert_allclose(b.first_order, a.first_order, rtol=1e-12)
    assert a.second_order is not None and b.second_order is not None
    np.testing.assert_allclose(b.second_order, 3.5 * a.second_order, rtol=1e-10)


def test_a_numerically_singular_information_is_refused_not_inverted() -> None:
    """A smooth and a factor-`by` smooth of the same covariate: their linear null
    spaces coincide, rank(X) < p and X'WX + S has an exactly null direction. mgcv
    pivots it out; this engine refuses (ADR-250). Built at fixed lambda: the fit
    itself is fragile on this structure (ADR-249), which is not under test here."""
    rng = np.random.default_rng(2)
    n = 450
    data = {"x": rng.uniform(0, 10, n), "f": rng.integers(0, 3, n)}
    model = ModelSpec(
        family="gaussian",
        link="identity",
        terms=(
            _cr("s(x)", "x", 8),
            *factor_by_terms(base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=3),
        ),
    )
    design = assemble_model_design(model, data)
    x = design["x"]
    assert np.linalg.matrix_rank(x) < x.shape[1]
    kwargs = dict(
        y=rng.normal(size=n),
        x=x,
        family=resolve_family("gaussian", "identity"),
        penalty_blocks=design["penalty_blocks"],
        log10_lambda=np.ones(len(design["penalty_blocks"])),
        coef=np.zeros(x.shape[1]),
        offset=None,
        weights=None,
        scale=1.0,
    )
    for unconditional in (False, True):
        with pytest.raises(PolarisComputationError, match="numerically singular"):
            coefficient_covariance(unconditional=unconditional, **kwargs)  # type: ignore[arg-type]


def test_a_hand_built_fit_without_a_response_refuses() -> None:
    fit, _ = _gaussian_fit()
    import dataclasses

    bare = dataclasses.replace(fit, y=None)
    with pytest.raises(PolarisValidationError, match="no training response"):
        bare.vcov()


def test_prior_weights_enter_the_information() -> None:
    rng = np.random.default_rng(9)
    n = 200
    w = rng.uniform(0.5, 2.0, n)
    data = {"x": rng.uniform(0, 10, n), "w": w}
    y = np.sin(data["x"]) + rng.normal(0, 0.3 / np.sqrt(w))
    model = ModelSpec(
        family="gaussian", link="identity", terms=(_cr("s(x)", "x", 8),), weights_column="w"
    )
    fit = fit_polaris_gam(model, data, y)
    x = fit.design["x"]
    s = sum(
        10.0**ll * b for ll, b in zip(fit.log_lambda, fit.design["penalty_blocks"], strict=True)
    )
    expected = fit.dispersion.fletcher * np.linalg.inv(x.T @ (w[:, None] * x) + s)
    np.testing.assert_allclose(fit.vcov(), expected, rtol=1e-9, atol=1e-12)
