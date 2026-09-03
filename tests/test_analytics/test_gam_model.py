"""R-free tests for ``gam_model`` — mgcv-parity engine, PLAN slice 5b
(``docs/WORK_ORDER_multi_term_assembly.md`` step 2).

These assert Polaris's OWN invariants (block widths sum to ``p``, penalties
land in the right column spans, a numeric-``by`` term is unconstrained while
a plain ``cr`` term is constrained, a ``ti`` term's two margins each carry
their own penalty) — checkable without ``mgcv``, per the work order's own
framing: "an oracle outage delays the measurement without idling the
session." Free-``sp`` parity itself is a separate, R-gated test
(``test_gam_model_conformance.py``).
"""

import numpy as np
import pytest

from polaris_re.analytics.gam_model import (
    assemble_model_design,
    fit_polaris_gam,
    resolve_family,
)
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

_AGE_KNOTS = (1.0, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
_YEAR_KNOTS = (1.0, 2, 3, 5, 10, 21)


def _data(n: int = 60, seed: int = 20260825) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {
        "AttdAge": rng.uniform(_AGE_KNOTS[0], _AGE_KNOTS[-1], size=n),
        "PolYear": rng.uniform(_YEAR_KNOTS[0], _YEAR_KNOTS[-1], size=n),
        "StudyYear_C": rng.uniform(-5.0, 5.0, size=n),
        "ExposCnt": rng.uniform(50.0, 500.0, size=n),
    }


def _cr_term(label: str = "s(AttdAge)", by: str | None = None) -> TermSpec:
    return TermSpec(
        label=label,
        variables=("AttdAge",),
        basis="cr",
        k=(len(_AGE_KNOTS),),
        knots=(("AttdAge", _AGE_KNOTS),),
        by=by,
    )


def _ti_term() -> TermSpec:
    return TermSpec(
        label="ti(AttdAge,PolYear)",
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(len(_AGE_KNOTS), len(_YEAR_KNOTS)),
        knots=(("AttdAge", _AGE_KNOTS), ("PolYear", _YEAR_KNOTS)),
    )


def _sz_term(n_levels: int = 2) -> TermSpec:
    return TermSpec(
        label="s(FaceSize,AttdAge)",
        variables=("FaceSize", "AttdAge"),
        basis="sz",
        k=(len(_AGE_KNOTS),),
        knots=(("AttdAge", _AGE_KNOTS),),
        n_levels=n_levels,
    )


def _data_with_face_size(n: int = 60, seed: int = 20260825) -> dict[str, np.ndarray]:
    data = _data(n=n, seed=seed)
    rng = np.random.default_rng(seed + 1)
    data["FaceSize"] = rng.integers(0, 2, size=n)
    return data


def test_resolve_family_covers_every_slice_3_combination() -> None:
    for family, link in [
        ("poisson", "log"),
        ("quasipoisson", "log"),
        ("binomial", "logit"),
        ("binomial", "cloglog"),
    ]:
        f = resolve_family(family, link)
        assert f.link.name == link


def test_resolve_family_rejects_an_unbuilt_combination() -> None:
    with pytest.raises(PolarisValidationError, match="no Family/Link constructor"):
        resolve_family("gamma", "log")


def test_block_widths_sum_to_p_and_spans_are_contiguous() -> None:
    """The exact arithmetic ADR-206 pinned for this three-term shape: p = 1
    (intercept) + 12 (reference, k=13 constrained to k-1) + 13 (by-term,
    UNCONSTRAINED) + 60 (ti(), (13-1)*(6-1)) = 86."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    design = assemble_model_design(model, _data())
    assert design["x"].shape[1] == 86
    blocks = design["term_blocks"]
    assert [b["label"] for b in blocks] == [
        "s(AttdAge)",
        "s(AttdAge,by=StudyYear_C)",
        "ti(AttdAge,PolYear)",
    ]
    assert blocks[0]["start"] == 1 and blocks[0]["end"] == 13
    assert blocks[1]["start"] == 13 and blocks[1]["end"] == 26
    assert blocks[2]["start"] == 26 and blocks[2]["end"] == 86
    # Contiguous, no gaps and no overlap: each span starts where the last ended.
    starts = [1] + [b["end"] for b in blocks[:-1]]
    assert [b["start"] for b in blocks] == starts
    assert len(design["penalty_blocks"]) == 4  # 1 + 1 + 2 (ti carries two, ADR-205)


def test_penalty_blocks_land_only_in_their_own_term_span() -> None:
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    design = assemble_model_design(model, _data())
    p = design["x"].shape[1]
    spans = [(1, 13), (13, 26), (26, 86), (26, 86)]
    for block, (lo, hi) in zip(design["penalty_blocks"], spans, strict=True):
        assert block.shape == (p, p)
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.size > 0, "a penalty block must not be identically zero"
        assert support.min() >= lo
        assert support.max() < hi
        assert np.all(block[:lo, :] == 0.0)
        assert np.all(block[hi:, :] == 0.0)
        assert np.all(block[:, :lo] == 0.0)
        assert np.all(block[:, hi:] == 0.0)


def test_by_term_is_unconstrained_where_a_plain_cr_term_is_constrained() -> None:
    """ADR-200: mgcv absorbs NO identifiability constraint on a numeric-``by``
    smooth, so its design keeps all ``k`` columns; a plain ``cr`` term drops
    one to the sum-to-zero constraint. A regression here (e.g. constraining
    the by-term, or leaving the plain term unconstrained) changes both widths
    and would be caught by the exact-86 check above too, but this asserts the
    mechanism directly rather than only its downstream total."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr_term(), _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C")),
        weights_column="ExposCnt",
    )
    design = assemble_model_design(model, _data())
    ref_block, by_block = design["term_blocks"]
    k = len(_AGE_KNOTS)
    assert ref_block["end"] - ref_block["start"] == k - 1
    assert by_block["end"] - by_block["start"] == k


def test_ti_term_carries_two_penalty_blocks_over_the_same_span() -> None:
    """ADR-205 decision 2: ti()'s two per-margin penalties both apply to the
    SAME tensor column range — two different penalties on one design, not
    two disjoint ranges. A regression that instead padded them sequentially
    (the bug PR #210 review [P2-1] found and locked a test against for the
    fixed three-term harness) would fail the exact-86 width in the tests
    above; this checks the mechanism on its own, isolated from the other
    two terms."""
    model = ModelSpec(family="binomial", link="cloglog", terms=(_ti_term(),))
    design = assemble_model_design(model, _data())
    assert len(design["term_blocks"]) == 1
    tb = design["term_blocks"][0]
    assert tb["n_penalties"] == 2
    assert len(design["penalty_blocks"]) == 2
    (lo, hi) = tb["start"], tb["end"]
    for block in design["penalty_blocks"]:
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.min() >= lo
        assert support.max() < hi


def test_assemble_model_design_rejects_an_unbuilt_basis() -> None:
    """``"raw"`` has no recipe for this function to build from — its design
    and penalty are supplied directly (ADR-189 decision 1), unlike
    ``"cr"``/``"ti"``/``"sz"``, all three of which PLAN slice 6b now wires."""
    term = TermSpec(label="raw-term", variables=("AttdAge",), basis="raw")
    model = ModelSpec(family="binomial", link="cloglog", terms=(term,))
    with pytest.raises(PolarisValidationError, match="does not build yet"):
        assemble_model_design(model, _data())


def test_assemble_model_design_requires_n_levels_for_sz() -> None:
    """PLAN slice 6b: unlike ADR-215's own narrower Stage-A harness
    (``build_python_sz_term``, which takes ``n_levels`` as its own explicit
    argument), the ``ModelSpec``-driven path reads it off ``TermSpec.n_levels``
    and raises loudly rather than deriving it from a sample's own observed
    group codes (Anchor 4)."""
    term = TermSpec(
        label="s(FaceSize,AttdAge)",
        variables=("FaceSize", "AttdAge"),
        basis="sz",
        k=(len(_AGE_KNOTS),),
    )
    model = ModelSpec(family="binomial", link="cloglog", terms=(term,))
    with pytest.raises(PolarisValidationError, match="n_levels=None"):
        assemble_model_design(model, _data_with_face_size())


def test_sz_term_carries_one_penalty_block_per_factor_level() -> None:
    """ADR-215's own ``sz_basis`` contract: one penalty block per factor
    level (2 here), both blocks spanning the SAME ``k * (n_levels - 1)``
    columns — the same "shared span, not disjoint" shape ``ti()``'s two
    margin penalties already have (ADR-206 decision 2)."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr_term(), _sz_term()),
        weights_column="ExposCnt",
    )
    design = assemble_model_design(model, _data_with_face_size())

    ref_block, sz_block = design["term_blocks"]
    k = len(_AGE_KNOTS)
    assert ref_block["end"] - ref_block["start"] == k - 1  # constrained
    assert sz_block["end"] - sz_block["start"] == k * 1  # k * (n_levels - 1) = k
    assert sz_block["n_penalties"] == 2  # one per factor level
    assert len(design["penalty_blocks"]) == 3  # 1 (ref) + 2 (sz, one per level)

    (lo, hi) = sz_block["start"], sz_block["end"]
    for block in design["penalty_blocks"][1:]:
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.size > 0
        assert support.min() >= lo
        assert support.max() < hi


def test_assemble_model_design_ignores_select_by_default() -> None:
    """``ModelSpec.select`` defaults to ``False`` — every earlier slice's
    block count is unchanged unless a caller opts in (PLAN slice 7)."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr_term(), _ti_term()),
        weights_column="ExposCnt",
    )
    design = assemble_model_design(model, _data())
    assert len(design["penalty_blocks"]) == 3  # 1 (cr) + 2 (ti)


def test_assemble_model_design_appends_one_null_space_block_per_term_under_select() -> None:
    """PLAN slice 7 (ADR-217): under ``select=True``, each term gets exactly
    ONE extra penalty block appended after its own existing ones — the
    basis-agnostic rule measured against ``mgcv``'s own ``select=TRUE``
    setup path across every term archetype (``gam_select_penalty``'s module
    docstring), not one extra block per existing penalty."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),  # 1 existing block -> 2 under select
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),  # 1 -> 2
            _ti_term(),  # 2 existing blocks -> 3 under select
        ),
        weights_column="ExposCnt",
        select=True,
    )
    design = assemble_model_design(model, _data())
    assert len(design["penalty_blocks"]) == 7  # 2 + 2 + 3
    n_penalties = [tb["n_penalties"] for tb in design["term_blocks"]]
    assert n_penalties == [2, 2, 3]
    # Widths and column spans are otherwise unchanged from the non-select
    # case (the extra penalty adds no new COLUMN, only a new penalty over
    # the term's existing ones).
    non_select = assemble_model_design(
        ModelSpec(family="binomial", link="cloglog", terms=model.terms, weights_column="ExposCnt"),
        _data(),
    )
    assert design["x"].shape == non_select["x"].shape
    np.testing.assert_array_equal(design["x"], non_select["x"])
    for select_tb, plain_tb in zip(design["term_blocks"], non_select["term_blocks"], strict=True):
        assert (select_tb["start"], select_tb["end"]) == (plain_tb["start"], plain_tb["end"])
    # The null-space block still lands only in its own term's column span,
    # the same containment invariant every other penalty block satisfies
    # (test_penalty_blocks_land_only_in_their_own_term_span).
    p = design["x"].shape[1]
    spans = [(1, 13), (1, 13), (13, 26), (13, 26), (26, 86), (26, 86), (26, 86)]
    for block, (lo, hi) in zip(design["penalty_blocks"], spans, strict=True):
        assert block.shape == (p, p)
        support = np.flatnonzero(np.any(block != 0.0, axis=0))
        assert support.size > 0
        assert support.min() >= lo
        assert support.max() < hi


def test_fit_polaris_gam_selects_its_own_lambda_and_converges() -> None:
    """R-free smoke test of the full path (design -> continuous lambda search
    -> penalized fit -> per-term edf) on a small, well-conditioned case —
    the parity claim against mgcv is a separate, R-gated test."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    data = _data(n=150)
    rng = np.random.default_rng(7)
    eta_true = (
        -4.5
        + 0.03 * data["AttdAge"]
        - 0.02 * data["PolYear"]
        + 0.01 * data["StudyYear_C"] * (data["AttdAge"] - 50) / 50
    )
    prob = 1.0 - np.exp(-np.exp(eta_true))
    death = rng.binomial(data["ExposCnt"].astype(int), np.clip(prob, 0.0, 1.0))
    y = death / data["ExposCnt"]

    fit = fit_polaris_gam(model, data, y, maxiter=60)
    assert fit.converged
    assert fit.eta.shape == (150,)
    assert fit.edf_total > 0.0
    assert fit.log_lambda.shape == (4,)
    # Reuses the module default (PRODUCTION_LOG10_BOUNDS, wide by design,
    # PR #212 review [P1]) and still finds an interior optimum on this case.
    assert not np.any(np.isclose(fit.log_lambda, -2.0))
    assert not np.any(np.isclose(fit.log_lambda, 12.0))
    assert set(fit.edf_per_term) == {
        "s(AttdAge)",
        "s(AttdAge,by=StudyYear_C)",
        "ti(AttdAge,PolYear)",
    }
    for edf in fit.edf_per_term.values():
        assert edf >= 0.0
    # Excludes the intercept by construction (module docstring) — strictly
    # less than the total, never equal or greater.
    assert sum(fit.edf_per_term.values()) < fit.edf_total


def test_fit_polaris_gam_multistart_matches_default_shape() -> None:
    """PLAN slice 7b (ADR-218): ``multistart=True`` is an opt-in over
    :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous_multistart`
    (ADR-213) rather than the module's own default single bounds-centre
    start. R-free: proves the parameter wires through end to end (same
    design, same block count, still converges) on the identical
    well-conditioned case the single-start smoke test above uses — the
    measured N=7-block parity finding this parameter exists for is a
    separate, R-gated conformance test
    (``test_gam_select_free_sp_conformance.py``)."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    data = _data(n=150)
    rng = np.random.default_rng(7)
    eta_true = (
        -4.5
        + 0.03 * data["AttdAge"]
        - 0.02 * data["PolYear"]
        + 0.01 * data["StudyYear_C"] * (data["AttdAge"] - 50) / 50
    )
    prob = 1.0 - np.exp(-np.exp(eta_true))
    death = rng.binomial(data["ExposCnt"].astype(int), np.clip(prob, 0.0, 1.0))
    y = death / data["ExposCnt"]

    single = fit_polaris_gam(model, data, y, maxiter=60)
    multi = fit_polaris_gam(model, data, y, maxiter=60, multistart=True, n_starts=3)
    assert multi.converged
    assert multi.log_lambda.shape == single.log_lambda.shape == (4,)
    assert multi.eta.shape == single.eta.shape == (150,)
    # multistart's own reported cost is n_starts searches' worth of nfev,
    # never fewer than a single search alone would report on this case.
    assert multi.n_function_evals >= single.n_function_evals


def test_fit_polaris_gam_analytic_gradient_matches_default_shape() -> None:
    """PLAN slice 7d: ``analytic_gradient=True`` is an opt-in over
    :func:`~polaris_re.analytics.gam_reml_optimize.select_lambdas_continuous`'s
    own finite-difference default. R-free wiring check on the same
    well-conditioned case ``test_fit_polaris_gam_multistart_matches_default_shape``
    uses — the measured N=4/N=7 findings this parameter exists for are the
    slice's own ADR."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    data = _data(n=150)
    rng = np.random.default_rng(7)
    eta_true = (
        -4.5
        + 0.03 * data["AttdAge"]
        - 0.02 * data["PolYear"]
        + 0.01 * data["StudyYear_C"] * (data["AttdAge"] - 50) / 50
    )
    prob = 1.0 - np.exp(-np.exp(eta_true))
    death = rng.binomial(data["ExposCnt"].astype(int), np.clip(prob, 0.0, 1.0))
    y = death / data["ExposCnt"]

    default = fit_polaris_gam(model, data, y, maxiter=60)
    analytic = fit_polaris_gam(model, data, y, maxiter=60, analytic_gradient=True)
    assert analytic.converged
    assert analytic.log_lambda.shape == default.log_lambda.shape == (4,)
    assert analytic.eta.shape == default.eta.shape == (150,)


def test_fit_polaris_gam_rejects_x0_together_with_multistart() -> None:
    """PR #223 review [P2-1]: ``select_lambdas_continuous_multistart`` has
    no ``x0`` of its own (its first start is always the bounds-centre), so
    a caller supplying both would have ``x0`` silently dropped rather than
    used. Raises instead of misreporting what search actually ran."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr_term(),),
        weights_column="ExposCnt",
    )
    data = _data(n=150)
    y = np.zeros(150, dtype=np.float64)
    with pytest.raises(PolarisValidationError, match="x0"):
        fit_polaris_gam(model, data, y, multistart=True, x0=np.zeros(2))


def test_fit_polaris_gam_raises_loudly_when_the_search_hits_a_bound() -> None:
    """PR #212 review [P1]: a smoothing-parameter selection clamped at the
    search domain's edge is not the REML criterion's minimum, and must not
    be returned as though it were. Forces the condition with a deliberately
    narrow `bounds` on the same well-conditioned case the smoke test above
    fits cleanly at the wide default — isolating the guard from whether any
    particular design happens to need a wide search."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(
            _cr_term(),
            _cr_term(label="s(AttdAge,by=StudyYear_C)", by="StudyYear_C"),
            _ti_term(),
        ),
        weights_column="ExposCnt",
    )
    data = _data(n=150)
    rng = np.random.default_rng(7)
    eta_true = (
        -4.5
        + 0.03 * data["AttdAge"]
        - 0.02 * data["PolYear"]
        + 0.01 * data["StudyYear_C"] * (data["AttdAge"] - 50) / 50
    )
    prob = 1.0 - np.exp(-np.exp(eta_true))
    death = rng.binomial(data["ExposCnt"].astype(int), np.clip(prob, 0.0, 1.0))
    y = death / data["ExposCnt"]

    with pytest.raises(PolarisComputationError, match="a bound"):
        fit_polaris_gam(model, data, y, maxiter=60, bounds=(3.0, 3.0 + 1e-9))


def _no_signal_recipe(n: int = 150) -> tuple[ModelSpec, dict[str, np.ndarray], np.ndarray]:
    """A single ``cr`` term with NO true relationship to ``y`` — mgcv's own
    select=TRUE routinely shrinks a term like this to its null space
    (log10(lambda) -> a large value), the exact false-positive fixture PR
    #212's own review named
    (`docs/DEV_SESSION_LOG_2026-08-25_mgcv_parity_slice5b_polarisgam.md`)."""
    model = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr_term(),),
        weights_column="ExposCnt",
    )
    data = _data(n=n)
    rng = np.random.default_rng(20260825)
    prob = np.full(n, 0.05)
    death = rng.binomial(data["ExposCnt"].astype(int), prob)
    y = death / data["ExposCnt"]
    return model, data, y


def test_fit_polaris_gam_reports_rather_than_raises_at_the_upper_bound() -> None:
    """PR #212 review [P1-new], now fixed: a term with no true signal is a
    normal case for mgcv's own select=TRUE to shrink to its null space —
    this is not the same conditioning defect the lower bound signals, so
    the default (`strict=False`) reports it on the fit rather than
    raising."""
    model, data, y = _no_signal_recipe()

    fit = fit_polaris_gam(model, data, y, bounds=(-2.0, 2.0), maxiter=60)
    assert fit.at_bound
    assert fit.at_bound_blocks == ("s(AttdAge)",)
    assert np.isclose(fit.log_lambda[0], 2.0)


def test_fit_polaris_gam_strict_raises_at_the_upper_bound_too() -> None:
    """The same no-signal fixture as the reporting test above, but with
    `strict=True` — the conformance/harness mode PR #212's review named,
    where a bound hit anywhere is worth failing loudly on."""
    model, data, y = _no_signal_recipe()

    with pytest.raises(PolarisComputationError, match=r"a bound.*UPPER"):
        fit_polaris_gam(model, data, y, bounds=(-2.0, 2.0), maxiter=60, strict=True)
