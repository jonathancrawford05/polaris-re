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
from polaris_re.core.exceptions import PolarisValidationError

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
    term = TermSpec(
        label="s(FaceSize,AttdAge)", variables=("FaceSize", "AttdAge"), basis="sz", k=(13,)
    )
    model = ModelSpec(family="binomial", link="cloglog", terms=(term,))
    with pytest.raises(PolarisValidationError, match="does not build yet"):
        assemble_model_design(model, _data())


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
