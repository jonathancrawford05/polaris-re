"""Tests for :mod:`polaris_re.analytics.gam_term_spec` (mgcv-parity engine, slice 1).

Anchor 3: a term specification is data, not code. These tests exercise the validation
that keeps a malformed spec from reaching the (not yet written) basis layer or the
R-side exchange looking well-formed.
"""

import pytest

from polaris_re.analytics.gam_term_spec import SUPPORTED_BASES, ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError


def _cr(label: str = "s(AttdAge)", variable: str = "AttdAge", k: int = 13) -> TermSpec:
    return TermSpec(label=label, variables=(variable,), basis="cr", k=(k,))


def test_a_well_formed_single_margin_term_constructs() -> None:
    term = _cr()
    assert term.label == "s(AttdAge)"
    assert term.variables == ("AttdAge",)
    assert term.k == (13,)
    assert term.knots is None
    assert term.by is None
    assert not term.factor


def test_a_well_formed_ti_term_carries_one_k_per_variable() -> None:
    term = TermSpec(
        label="ti(AttdAge,PolYear)",
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(13, 6),
    )
    assert term.variables == ("AttdAge", "PolYear")
    assert term.k == (13, 6)


def test_a_by_variable_term_is_distinct_from_a_factor_term() -> None:
    mi_term = TermSpec(
        label="s(AttdAge):StudyYear_C",
        variables=("AttdAge",),
        basis="cr",
        k=(13,),
        by="StudyYear_C",
    )
    assert mi_term.by == "StudyYear_C"
    assert not mi_term.factor

    sz_term = TermSpec(
        label="s(FaceSize,AttdAge)",
        variables=("FaceSize", "AttdAge"),
        basis="sz",
        k=(13,),  # sz takes ONE k — the smoothed margin's dimension, not per-variable.
        factor=True,
    )
    assert sz_term.factor
    assert sz_term.by is None


def test_sz_takes_exactly_two_variables_and_one_k() -> None:
    with pytest.raises(PolarisValidationError, match="names exactly two"):
        TermSpec(label="s(x)", variables=("AttdAge",), basis="sz", k=(13,))
    with pytest.raises(PolarisValidationError, match="exactly one k"):
        TermSpec(
            label="s(FaceSize,AttdAge)",
            variables=("FaceSize", "AttdAge"),
            basis="sz",
            k=(13, 6),
        )


def test_sz_n_levels_is_optional_and_only_valid_on_sz() -> None:
    """PLAN slice 6b: ``n_levels`` lets ``ModelSpec``-driven assembly
    (``gam_model.assemble_model_design``) build an ``sz`` term without
    re-deriving the factor-level count from a sample. Optional (ADR-215's
    own Stage-A harness passes it separately, not via the spec), and only
    an ``sz`` term may carry it."""
    sz_term = TermSpec(
        label="s(FaceSize,AttdAge)",
        variables=("FaceSize", "AttdAge"),
        basis="sz",
        k=(13,),
        n_levels=2,
    )
    assert sz_term.n_levels == 2

    with pytest.raises(PolarisValidationError, match="at least 2 factor levels"):
        TermSpec(
            label="s(FaceSize,AttdAge)",
            variables=("FaceSize", "AttdAge"),
            basis="sz",
            k=(13,),
            n_levels=1,
        )

    with pytest.raises(PolarisValidationError, match="only a basis='sz' term"):
        TermSpec(label="s(AttdAge)", variables=("AttdAge",), basis="cr", k=(13,), n_levels=2)


def test_supplied_knots_may_omit_a_margin_to_mean_default_for_that_margin_only() -> None:
    term = TermSpec(
        label="ti(AttdAge,PolYear)",
        variables=("AttdAge", "PolYear"),
        basis="ti",
        k=(13, 6),
        knots=(("AttdAge", (1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)),),
    )
    assert term.knots is not None
    assert "PolYear" not in term.knots_by_variable()
    assert term.knots_by_variable()["AttdAge"] == (1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)


def test_knots_are_immutable_and_the_spec_is_hashable() -> None:
    term = TermSpec(
        label="s(AttdAge)",
        variables=("AttdAge",),
        basis="cr",
        k=(13,),
        knots=(("AttdAge", (1.0, 2.0, 3.0)),),
    )
    with pytest.raises((TypeError, AttributeError)):
        term.knots["AttdAge"] = (9.9,)  # type: ignore[index]
    hash(term)  # a dict-valued field would make this raise TypeError.

    # knots_by_variable() computes a fresh dict every call — mutating it must not
    # touch the spec.
    borrowed = term.knots_by_variable()
    borrowed["AttdAge"] = (9.9,)
    assert term.knots_by_variable()["AttdAge"] == (1.0, 2.0, 3.0)


def test_a_variable_supplied_twice_in_knots_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="more than once"):
        TermSpec(
            label="s(AttdAge)",
            variables=("AttdAge",),
            basis="cr",
            k=(13,),
            knots=(("AttdAge", (1.0, 2.0)), ("AttdAge", (3.0, 4.0))),
        )


def test_a_raw_term_carries_no_k_and_no_knots() -> None:
    term = TermSpec(label="tensor(age,year)", variables=("age", "year"), basis="raw")
    assert term.k == ()
    assert term.knots is None


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"label": ""}, "non-empty label"),
        ({"variables": ()}, "names no variables"),
        ({"basis": "te"}, "supported bases are"),
        ({"k": (13, 6)}, r"names 2; one k per variable"),
        ({"k": ()}, r"names 0; one k per variable"),
    ],
)
def test_malformed_terms_are_refused(kwargs: dict[str, object], match: str) -> None:
    base = {"label": "s(AttdAge)", "variables": ("AttdAge",), "basis": "cr", "k": (13,)}
    base.update(kwargs)
    with pytest.raises(PolarisValidationError, match=match):
        TermSpec(**base)  # type: ignore[arg-type]


def test_ti_needs_at_least_two_margins() -> None:
    with pytest.raises(PolarisValidationError, match="at least two margins"):
        TermSpec(label="ti(AttdAge)", variables=("AttdAge",), basis="ti", k=(13,))


def test_a_raw_term_with_k_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="must not carry k"):
        TermSpec(label="tensor(age,year)", variables=("age", "year"), basis="raw", k=(7, 6))


def test_a_raw_term_with_knots_is_refused() -> None:
    with pytest.raises(PolarisValidationError, match="must not carry knots"):
        TermSpec(
            label="tensor(age,year)",
            variables=("age", "year"),
            basis="raw",
            knots=(("age", (1.0, 2.0)),),
        )


def test_knots_for_an_unknown_variable_are_refused() -> None:
    with pytest.raises(PolarisValidationError, match="not in its variables"):
        TermSpec(
            label="s(AttdAge)",
            variables=("AttdAge",),
            basis="cr",
            k=(13,),
            knots=(("PolYear", (1, 2, 3)),),
        )


def test_by_and_factor_together_are_refused() -> None:
    with pytest.raises(PolarisValidationError, match="a term is one or the other"):
        TermSpec(
            label="s(AttdAge)",
            variables=("AttdAge",),
            basis="cr",
            k=(13,),
            by="StudyYear_C",
            factor=True,
        )


def test_every_supported_basis_constructs_a_minimal_term() -> None:
    for basis in SUPPORTED_BASES:
        if basis == "raw":
            TermSpec(label=f"term-{basis}", variables=("x",), basis=basis)
        elif basis == "sz":
            TermSpec(label=f"term-{basis}", variables=("id", "x"), basis=basis, k=(8,))
        elif basis == "ti":
            TermSpec(label=f"term-{basis}", variables=("x", "y"), basis=basis, k=(8, 6))
        else:
            TermSpec(label=f"term-{basis}", variables=("x",), basis=basis, k=(8,))


# --- ModelSpec -------------------------------------------------------------------


def test_a_well_formed_model_spec_constructs() -> None:
    spec = ModelSpec(
        family="binomial",
        link="cloglog",
        terms=(_cr(), _cr(label="s(PolYear)", variable="PolYear", k=6)),
        weights_column="ExposCnt",
    )
    assert spec.weights_column == "ExposCnt"
    assert spec.offset_column is None
    assert len(spec.terms) == 2


def test_weights_and_offset_are_orthogonal_and_both_may_be_set() -> None:
    spec = ModelSpec(
        family="poisson",
        link="log",
        terms=(_cr(),),
        weights_column="exposure",
        offset_column="log_q_base",
    )
    assert spec.weights_column == "exposure"
    assert spec.offset_column == "log_q_base"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"family": ""}, "non-empty family"),
        ({"link": ""}, "non-empty link"),
        ({"terms": ()}, "at least one term"),
    ],
)
def test_malformed_model_specs_are_refused(kwargs: dict[str, object], match: str) -> None:
    base = {"family": "binomial", "link": "cloglog", "terms": (_cr(),)}
    base.update(kwargs)
    with pytest.raises(PolarisValidationError, match=match):
        ModelSpec(**base)  # type: ignore[arg-type]


def test_duplicate_term_labels_are_refused() -> None:
    with pytest.raises(PolarisValidationError, match="duplicate term labels"):
        ModelSpec(
            family="binomial",
            link="cloglog",
            terms=(_cr(), _cr()),
        )
