"""``select=TRUE`` with a factor-``by`` smooth (Slice R1, ADR-258).

Own-criterion checks (MEASUREMENT of Polaris, not parity): the structural claim R1-a (the
by-level null-space penalties identify the direction a bare smooth leaves free), that the
accepted forms are not pivoted, and the closed-form shape of the added penalties. The
INDEPENDENT comparison with ``mgcv`` is the ``*_select_factor_by_*`` cells of
``polaris_re.gam.formula_conformance`` and the draws probe
``scripts/gam_select_bare_by_draws_compare.py`` (tier 3).
"""

import warnings

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.gam_model import assemble_model_design
from polaris_re.analytics.gam_rank_pivot import unidentified_directions
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.exceptions import PolarisRankDeficiencyWarning, PolarisValidationError
from polaris_re.gam import gam

N_LEVELS = 3


@pytest.fixture(scope="module")
def frame() -> pl.DataFrame:
    rng = np.random.default_rng(11)
    n = 360
    x = rng.uniform(0, 10, n)
    f = rng.choice(["a", "b", "c"], n)
    shift = np.where(f == "b", 0.6, np.where(f == "c", -0.5, 0.0))
    y = np.sin(x + shift) + rng.normal(0, 0.3, n)
    return pl.DataFrame({"x": x, "f": f, "y": y})


def _design(select: bool, *, bare: bool, main: bool):  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(3)
    n = 120
    data = {"x": rng.uniform(0, 10, n), "f": rng.integers(0, N_LEVELS, n)}
    terms: list[TermSpec] = []
    if main:
        terms.append(TermSpec(label="f", variables=("f",), basis="parametric", levels=(N_LEVELS,)))
    if bare:
        terms.append(TermSpec(label="s(x)", variables=("x",), basis="cr", k=(6,)))
    terms.extend(
        factor_by_terms(base_label="s(x):f", variable="x", k=6, by_factor="f", n_levels=N_LEVELS)
    )
    spec = ModelSpec(family="gaussian", link="identity", terms=tuple(terms), select=select)
    return assemble_model_design(spec, data)


@pytest.mark.parametrize("main", [False, True])
def test_select_identifies_the_direction_a_bare_smooth_leaves_free(main: bool) -> None:
    """R1-a, structural (no response, no sp): without select the bare + by-level smooths share
    one unidentified direction; with select the null-space penalties penalise it."""
    plain = _design(False, bare=True, main=main)
    selected = _design(True, bare=True, main=main)
    assert unidentified_directions(plain["x"], plain["penalty_blocks"]).shape[1] == 1
    assert unidentified_directions(selected["x"], selected["penalty_blocks"]).shape[1] == 0


@pytest.mark.parametrize("bare", [False, True])
def test_select_adds_exactly_one_null_space_penalty_per_by_level(bare: bool) -> None:
    plain = _design(False, bare=bare, main=True)
    selected = _design(True, bare=bare, main=True)
    n_smooths = N_LEVELS + int(bare)
    assert len(selected["penalty_blocks"]) == len(plain["penalty_blocks"]) + n_smooths
    # each added block is PSD of rank = the smooth's null-space dimension (the linear trend: the
    # constant is removed by the sum-to-zero constraint, as in mgcv)
    added = [
        b
        for b in selected["penalty_blocks"]
        if not any(np.array_equal(b, p) for p in plain["penalty_blocks"])
    ]
    assert len(added) == n_smooths
    for block in added:
        eig = np.linalg.eigvalsh(block)
        assert eig.min() > -1e-10
        assert int((eig > 1e-10 * eig.max()).sum()) == 1


@pytest.mark.parametrize(
    "formula", ['y ~ f + s(x, by=f, bs="cr", k=6)', 'y ~ s(x, by=f, bs="cr", k=6)']
)
def test_the_accepted_forms_are_fitted_without_a_pivot_or_a_warning(
    frame: pl.DataFrame, formula: str
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", PolarisRankDeficiencyWarning)
        fit = gam(formula, frame, "gaussian", select=True)
    assert fit.converged
    assert fit.pivoted_columns == ()
    # one wiggliness + one null-space penalty per level
    assert len(fit.log_lambda) == 2 * N_LEVELS
    # unconditional covariance is NOT refused (it is for a pivoted fit)
    assert fit.vcov(unconditional=True).shape[0] == fit.coef.size


def test_the_refusal_names_the_construct_and_the_alternative(frame: pl.DataFrame) -> None:
    with pytest.raises(PolarisValidationError) as err:
        gam('y ~ s(x, bs="cr", k=6) + s(x, by=f, bs="cr", k=6)', frame, "gaussian", select=True)
    text = str(err.value)
    assert "s(x)" in text and "ADR-258" in text and "by=f" in text
