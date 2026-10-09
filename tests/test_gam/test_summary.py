"""``GamFit.summary()`` — preview Slice P4 (ADR-253).

Closed-form checks (a Gaussian null deviance is the weighted TSS; a Poisson intercept with an
offset has the closed-form MLE ``log(sum y / sum(w exp(off)))``), the provenance gate
(ADR-193) and the layering. The ``summary.gam`` comparison itself is the tier-3 CI reading
(``scripts/gam_summary_compare.py``); these tests are MEASUREMENT (own criterion), not parity.
"""

import typing

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.gam_family import gaussian_identity, poisson_log
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import ComparisonProvenance, require_parity_evidence
from polaris_re.gam import gam
from polaris_re.gam.formula_conformance import FormulaRecipe
from polaris_re.gam.summary import EPSILON_REL, null_deviance
from polaris_re.gam.summary_conformance import (
    SUMMARY_CLAIM,
    fit_summary_case,
    implied_gates,
)


def _frame(n: int = 300, seed: int = 3) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 10, n)
    return pl.DataFrame(
        {
            "x": x,
            "f": rng.choice(["a", "b", "c"], n),
            "y": np.sin(x) + rng.normal(0, 0.3, n),
            "wt": rng.uniform(0.5, 2.0, n),
        }
    )


def test_gaussian_null_deviance_is_the_weighted_total_sum_of_squares() -> None:
    y = np.array([1.0, 2.0, 4.0, 7.0])
    w = np.array([1.0, 2.0, 1.0, 3.0])
    expected = float(np.sum(w * (y - np.sum(w * y) / np.sum(w)) ** 2))
    np.testing.assert_allclose(null_deviance(y, gaussian_identity(), w, None), expected, rtol=1e-12)


def test_poisson_null_deviance_with_an_offset_matches_the_closed_form_intercept() -> None:
    rng = np.random.default_rng(5)
    off = rng.normal(0.0, 0.5, 200)
    y = rng.poisson(np.exp(0.3 + off)).astype(np.float64)
    mu0 = np.exp(off) * y.sum() / np.exp(off).sum()
    expected = poisson_log().deviance(y, mu0, np.ones_like(y))
    np.testing.assert_allclose(null_deviance(y, poisson_log(), None, off), expected, rtol=1e-10)


def test_gaussian_deviance_explained_is_one_minus_rss_over_tss() -> None:
    df = _frame()
    fit = gam('y ~ s(x, k=8, bs="cr")', df, "gaussian")
    s = fit.summary()
    y = df["y"].to_numpy()
    rss = float(np.sum((y - fit.eta) ** 2))
    tss = float(np.sum((y - y.mean()) ** 2))
    np.testing.assert_allclose(s.deviance_explained, 1.0 - rss / tss, rtol=1e-10)
    np.testing.assert_allclose(s.deviance, rss, rtol=1e-10)
    assert s.n == df.height
    assert s.scale_estimated


def test_edf_total_is_the_intercept_plus_the_per_term_edf() -> None:
    fit = gam('y ~ f + s(x, k=8, bs="cr")', _frame(), "gaussian")
    s = fit.summary()
    smooth_edf = sum(t.edf for t in s.smooths)
    parametric_edf = fit.edf_per_term["f"]
    np.testing.assert_allclose(s.edf_total, 1.0 + smooth_edf + parametric_edf, rtol=1e-9)
    assert [t.label for t in s.smooths] == ["s(x)"]
    assert s.n_parametric == 3


def test_a_fixed_scale_family_reports_scale_one_and_the_newton_report() -> None:
    rng = np.random.default_rng(8)
    x = rng.uniform(0, 10, 400)
    df = pl.DataFrame({"x": x, "y": rng.poisson(np.exp(0.5 + 0.3 * np.sin(x))).astype(float)})
    fit = gam('y ~ s(x, k=8, bs="cr")', df, "poisson")
    s = fit.summary()
    assert s.scale == 1.0
    assert not s.scale_estimated
    assert s.converged and s.outer == "newton"
    assert s.n_iterations is not None and s.n_iterations >= 1
    assert s.rel_projected_gradient is not None
    assert s.rel_projected_gradient <= s.epsilon_rel == EPSILON_REL == 1e-6
    gates = implied_gates(fit, s)
    assert gates.scale_relative == 0.0
    assert 0.0 < gates.deviance_explained < 1.0


def test_select_true_reports_two_log_sp_for_a_penalised_smooth() -> None:
    fit = gam('y ~ s(x, k=8, bs="cr")', _frame(), "gaussian", select=True)
    (term,) = fit.summary().smooths
    assert len(term.log10_sp) == 2


def test_the_text_report_names_what_it_omits_and_what_it_found() -> None:
    text = str(gam('y ~ s(x, k=8, bs="cr")', _frame(), "gaussian").summary())
    assert "Deviance explained" in text and "log10(sp)" in text
    assert "converged" in text and "epsilon_rel" in text
    assert "No p-values" in text


def test_the_implied_gate_is_computed_from_polaris_alone_and_scale_gate_is_positive() -> None:
    fit = gam('y ~ s(x, k=8, bs="cr")', _frame(), "gaussian")
    gates = implied_gates(fit, fit.summary())
    assert gates.scale_relative > 0.0
    assert gates.per_term_edf == 1.0


def test_exactly_the_row_count_is_echo_and_the_rest_is_independent() -> None:
    echo = [q for q in SUMMARY_CLAIM.quantities if q.provenance is ComparisonProvenance.ECHO]
    assert [q.quantity.split(" ")[0] for q in echo] == ["n"]
    independent = [q for q in SUMMARY_CLAIM.quantities if q is not echo[0]]
    assert all(q.provenance is ComparisonProvenance.INDEPENDENT for q in independent)
    require_parity_evidence(independent, claim="summary vs summary.gam")
    with pytest.raises(PolarisValidationError):
        require_parity_evidence(SUMMARY_CLAIM.quantities, claim="summary incl. the echo")


def test_the_polaris_producer_takes_the_recipe_only() -> None:
    assert typing.get_type_hints(fit_summary_case)["recipe"] is FormulaRecipe
