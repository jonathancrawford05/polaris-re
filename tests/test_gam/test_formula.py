"""``polaris_re.gam.formula`` — the parser and its refusal list (preview Slice P3, ADR-251).

One test per refused construct: each must raise ``PolarisValidationError`` naming the
construct (and, where the refusal is a coverage decision, the coverage row)."""

import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam.formula import (
    ParametricCall,
    SmoothCall,
    TensorCall,
    parse_formula,
)


def test_parses_the_verified_subset() -> None:
    p = parse_formula(
        'y ~ A + B + A:B + s(x, bs="cr", k=8) + s(x, by=w, bs="cr") + s(f, bs="re") '
        '+ ti(x, z, bs="cr", k=c(6, 5)) + offset(off)'
    )
    assert p.response == "y"
    assert p.offset == "off"
    assert p.terms == (
        ParametricCall(("A",)),
        ParametricCall(("B",)),
        ParametricCall(("A", "B")),
        SmoothCall("x", "cr", 8),
        SmoothCall("x", "cr", 10, by="w"),  # mgcv's default k for cr
        SmoothCall("f", "re", None),
        TensorCall(("x", "z"), (6, 5)),
    )


def test_ti_defaults_and_scalar_k_recycle() -> None:
    assert parse_formula('y ~ ti(x, z, bs="cr")').terms == (TensorCall(("x", "z"), (5, 5)),)
    assert parse_formula('y ~ ti(x, z, bs="cr", k=7)').terms == (TensorCall(("x", "z"), (7, 7)),)


def test_single_quotes_and_whitespace_and_dotted_names() -> None:
    p = parse_formula("  y.rate~ s( age.at , bs = 'cr' ,k=5 )  ")
    assert p.response == "y.rate"
    assert p.terms == (SmoothCall("age.at", "cr", 5),)


def test_a_bare_smooth_is_refused_and_its_explicit_equivalent_is_accepted() -> None:
    """Maintainer answer 2 (2026-10-07): bare ``s(x)`` stays refused until ``tp`` (L7),
    provided the same model can be written with an explicit basis."""
    with pytest.raises(PolarisValidationError, match=r"s\(x\).*bs='tp'.*L7"):
        parse_formula("y ~ s(x)")
    assert parse_formula('y ~ s(x, bs="cr")').terms == (SmoothCall("x", "cr", 10),)


@pytest.mark.parametrize(
    ("formula", "needle"),
    [
        ('y ~ s(x, bs="tp")', "bs='tp'"),
        ('y ~ s(x, bs="ts")', "bs='ts'"),
        ('y ~ s(x, bs="cc")', "bs='cc'"),
        ('y ~ s(x, bs="ps")', "bs='ps'"),
        ('y ~ s(f, x, bs="fs")', "bs='fs'"),
        ('y ~ s(f, x, bs="sz", k=8, xt=list(bs="cr"))', "bs='sz'"),
        ('y ~ s(x, z, bs="cr")', "multi-variable smooth"),
        ('y ~ s(x, bs="cr", sp=1)', "argument 'sp'"),
        ('y ~ s(x, bs="cr", fx=TRUE)', "argument 'fx'"),
        ('y ~ s(x, bs="cr", m=1)', "argument 'm'"),
        ('y ~ s(f, bs="re", k=3)', "takes no k"),
        ('y ~ s(f, by=g, bs="re")', "by= on a random-effect"),
        ("y ~ te(x, z)", "te()"),
        ("y ~ t2(x, z)", "t2()"),
        ('y ~ ti(x, z, w, bs="cr")', "3 margin"),
        ("y ~ ti(x, z)", "without bs="),
        ('y ~ ti(x, z, bs="tp")', "bs='tp'"),
        ('y ~ ti(x, z, bs="cr", by=w)', "argument 'by'"),
        ("y ~ a*b", "operator"),
        ("y ~ a^2", "operator"),
        ("y ~ a:b:c", "interaction"),
        ("y ~ x - 1", "'-'"),
        ("y ~ 0 + x", "'0'"),
        ("y ~ poly(x, 2)", "poly()"),
        ("y ~ log(x)", "log()"),
        ("y ~ factor(g)", "factor()"),
        ("log(y) ~ a", "response 'log(y)'"),
        ("cbind(a, b) ~ x", "response"),
        ('y ~ s(log(x), bs="cr")', "variable 'log(x)'"),
        ("y ~ offset(log(e))", "offset"),
        ("y ~ a + offset(o1) + offset(o2)", "more than one offset"),
        ("y ~ weird(x)", "weird()"),
    ],
)
def test_every_refused_construct_is_refused_by_name(formula: str, needle: str) -> None:
    with pytest.raises(PolarisValidationError) as info:
        parse_formula(formula)
    assert needle in str(info.value)


@pytest.mark.parametrize(
    "formula",
    ["", "   ", "y", "y ~", "~ x", "y ~ x ~ z", 'y ~ s(x, bs="cr"', "y ~ a + + b", "y ~ a + a"],
)
def test_malformed_formulas_raise(formula: str) -> None:
    with pytest.raises(PolarisValidationError):
        parse_formula(formula)
