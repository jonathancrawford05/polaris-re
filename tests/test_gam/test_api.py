"""``polaris_re.gam.gam`` — the facade (preview Slice P3, ADR-251).

Own-criterion checks (MEASUREMENT, not parity): the facade reproduces the engine it wraps,
and each refusal fires. The INDEPENDENT comparison against ``mgcv`` is
``polaris_re.gam.formula_conformance`` (tier 3)."""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.gam_model import fit_polaris_gam
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import GamFit, gam, r_factor_levels, structural_rank_deficiency
from polaris_re.gam import api as gam_api


@pytest.fixture(scope="module")
def frame() -> pl.DataFrame:
    rng = np.random.default_rng(7)
    n = 260
    x = rng.uniform(0, 10, n)
    z = rng.uniform(0, 5, n)
    g = rng.choice(["b", "a", "c"], n)
    off = rng.uniform(-0.2, 0.2, n)
    y = np.sin(x) + 0.1 * z + np.where(g == "b", 0.4, 0.0) + rng.normal(0, 0.3, n)
    return pl.DataFrame({"x": x, "z": z, "g": g, "off": off, "y": y, "wt": rng.uniform(1, 2, n)})


def test_facade_reproduces_the_engine_it_wraps(frame: pl.DataFrame) -> None:
    fit = gam('y ~ g + s(x, bs="cr", k=8)', frame, "gaussian")
    levels = r_factor_levels(frame["g"].to_list())
    codes = np.array([levels.index(v) for v in frame["g"].to_list()], dtype=np.int64)
    model = ModelSpec(
        family="gaussian",
        link="identity",
        terms=(
            TermSpec(label="g", variables=("g",), basis="parametric", levels=(3,)),
            TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,)),
        ),
    )
    ref = fit_polaris_gam(model, {"g": codes, "x": frame["x"].to_numpy()}, frame["y"].to_numpy())
    np.testing.assert_allclose(fit.eta, ref.eta, rtol=0, atol=1e-12)
    assert isinstance(fit, GamFit)
    assert fit.converged


def test_structure_matches_mgcv_conventions(frame: pl.DataFrame) -> None:
    fit = gam(
        'y ~ g + s(x, bs="cr", k=8) + s(x, by=off, bs="cr", k=6) + ti(x, z, bs="cr", k=c(5, 4))',
        frame,
        "gaussian",
    )
    assert fit.smooth_labels == ("s(x)", "s(x):off", "ti(x,z)")
    assert fit.smooth_bs_dim == (8, 6, 20)
    assert fit.n_parametric == 3  # intercept + two dummy columns for the 3-level factor
    assert fit.factor_levels == {"g": ("a", "b", "c")}


def test_factor_by_labels_and_term_multiplier(frame: pl.DataFrame) -> None:
    fit = gam('y ~ g + s(x, by=g, bs="cr", k=6)', frame, "gaussian")
    assert fit.smooth_labels == ("s(x):ga", "s(x):gb", "s(x):gc")
    assert len(fit.log_lambda) == 3  # one smoothing parameter per level


def test_predict_accepts_a_dataframe_and_matches_codes(frame: pl.DataFrame) -> None:
    fit = gam('y ~ g + s(x, bs="cr", k=8)', frame, "gaussian")
    new = frame.head(11)
    eta = fit.predict(new)
    np.testing.assert_allclose(eta, fit.eta[:11], rtol=0, atol=1e-10)
    mu, se = fit.predict(new, "response", se_fit=True)
    assert mu.shape == se.shape == (11,)
    assert np.all(se > 0)
    codes = {"g": np.array([("a", "b", "c").index(v) for v in new["g"]]), "x": new["x"].to_numpy()}
    np.testing.assert_allclose(fit.predict(codes), eta, rtol=0, atol=1e-12)


def test_unseen_level_in_newdata_is_refused(frame: pl.DataFrame) -> None:
    fit = gam('y ~ g + s(x, bs="cr", k=8)', frame, "gaussian")
    bad = frame.head(3).with_columns(g=pl.lit("zzz"))
    with pytest.raises(PolarisValidationError, match="level 'zzz'"):
        fit.predict(bad)


def test_offset_in_formula_and_as_argument_agree(frame: pl.DataFrame) -> None:
    a = gam('y ~ s(x, bs="cr", k=6) + offset(off)', frame, "gaussian")
    b = gam('y ~ s(x, bs="cr", k=6)', frame, "gaussian", offset="off")
    np.testing.assert_allclose(a.eta, b.eta, rtol=0, atol=1e-12)
    with pytest.raises(PolarisValidationError, match="both offset="):
        gam('y ~ s(x, bs="cr", k=6) + offset(off)', frame, "gaussian", offset="off")
    # predict needs the offset column, as predict.gam does
    with pytest.raises(PolarisValidationError, match="no column 'off'"):
        a.predict(frame.head(2).drop("off"))


def test_weights_column_reaches_the_fit(frame: pl.DataFrame) -> None:
    plain = gam('y ~ s(x, bs="cr", k=6)', frame, "gaussian")
    weighted = gam('y ~ s(x, bs="cr", k=6)', frame, "gaussian", weights="wt")
    assert float(np.max(np.abs(plain.eta - weighted.eta))) > 1e-6


def test_the_rank_deficient_smooth_plus_factor_by_is_fitted_with_a_pivot(
    frame: pl.DataFrame,
) -> None:
    """Slice 9: the unidentified coefficient is pivoted out (it was refused before)."""
    fit = gam('y ~ s(x, bs="cr", k=6) + s(x, by=g, bs="cr", k=6)', frame, "gaussian")
    assert len(fit.pivoted_columns) == 1
    assert fit.design["x"].shape[1] == fit.design["full_width"] - 1
    assert fit.vcov().shape == (fit.design["full_width"],) * 2
    # the identified spelling of the same model carries no pivot
    assert gam('y ~ g + s(x, by=g, bs="cr", k=6)', frame, "gaussian").pivoted_columns == ()


def test_structural_rank_deficiency_closed_form() -> None:
    n = 20
    t = np.linspace(0, 1, n)
    x = np.column_stack([np.ones(n), t, t])  # duplicate column, no penalty
    assert structural_rank_deficiency(x, []) == 1
    pen = np.zeros((3, 3))
    pen[2, 2] = 1.0  # penalising one copy identifies the pair
    assert structural_rank_deficiency(x, [pen]) == 0
    assert structural_rank_deficiency(np.column_stack([np.ones(n), t]), []) == 0


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"scale": 2.0}, "scale="),
    ],
)
def test_unverified_options_are_refused(frame: pl.DataFrame, kwargs: dict, needle: str) -> None:
    with pytest.raises(PolarisValidationError, match=needle):
        gam('y ~ s(x, bs="cr", k=6)', frame, "gaussian", **kwargs)


def test_select_is_accepted_for_cr_ti_re_and_parametric_terms(frame: pl.DataFrame) -> None:
    fit = gam('y ~ s(x, bs="cr", k=6) + s(z, bs="cr", k=5)', frame, "gaussian", select=True)
    assert len(fit.log_lambda) == 4  # each cr term gains a null-space penalty
    # re's identity penalty is full rank: nothing to double; parametric has no penalty
    mixed = gam('y ~ g + s(x, bs="cr", k=6) + s(g, bs="re")', frame, "gaussian", select=True)
    assert len(mixed.log_lambda) == 3  # cr (2) + re (1)


def test_select_with_a_factor_by_smooth_is_refused(frame: pl.DataFrame) -> None:
    with pytest.raises(PolarisValidationError, match="factor-by smooth"):
        gam('y ~ g + s(x, by=g, bs="cr", k=6)', frame, "gaussian", select=True)


@pytest.mark.parametrize(
    "family",
    ["Gamma", "nb", "tweedie", "binomial(link='probit')", "poisson(link='sqrt')", "gaussian(x=1)"],
)
def test_unsupported_families_are_refused(frame: pl.DataFrame, family: str) -> None:
    with pytest.raises(PolarisValidationError):
        gam('y ~ s(x, bs="cr", k=6)', frame, family)


def test_dtype_and_null_guards(frame: pl.DataFrame) -> None:
    with pytest.raises(PolarisValidationError, match="numeric column"):
        gam("y ~ x", frame, "gaussian")
    with pytest.raises(PolarisValidationError, match="as a number"):
        gam('y ~ s(g, bs="cr", k=4)', frame, "gaussian")
    with pytest.raises(PolarisValidationError, match="factors must be"):
        gam('y ~ s(x, bs="re")', frame, "gaussian")
    with pytest.raises(PolarisValidationError, match="nulls"):
        gam(
            'y ~ s(x, bs="cr", k=6)',
            frame.with_columns(x=pl.when(pl.col("x") > 9).then(None).otherwise(pl.col("x"))),
            "gaussian",
        )
    with pytest.raises(PolarisValidationError, match="no column 'nope'"):
        gam('y ~ s(nope, bs="cr", k=6)', frame, "gaussian")
    with pytest.raises(PolarisValidationError, match="polars DataFrame"):
        gam('y ~ s(x, bs="cr", k=6)', {"x": [1.0]}, "gaussian")  # type: ignore[arg-type]
    with pytest.raises(PolarisValidationError, match="main effects"):
        gam('y ~ g:g2 + s(x, bs="cr", k=6)', frame.with_columns(g2=pl.col("g")), "gaussian")


def test_factor_levels_follow_r_rules(frame: pl.DataFrame) -> None:
    mixed = ["b", "B", "a", "A", "10", "9", "_z", "Z"]
    assert r_factor_levels(mixed, "C") == ("10", "9", "A", "B", "Z", "_z", "a", "b")
    assert r_factor_levels(mixed, "en_US") == (
        "_z",
        "10",
        "9",
        "a",
        "A",
        "b",
        "B",
        "Z",
    )  # tier-3 order
    assert r_factor_levels(mixed) == r_factor_levels(mixed, gam_api.ORACLE_COLLATION)
    with pytest.raises(PolarisValidationError, match="Enum"):
        r_factor_levels(["é", "e"], "en_US")
    enum = pl.Enum(["z", "a", "m"])
    fit = gam(
        'y ~ g + s(x, bs="cr", k=6)',
        frame.with_columns(g=pl.Series(["z", "a", "m"] * 86 + ["z", "a"], dtype=enum)),
        "gaussian",
    )
    assert fit.factor_levels["g"] == ("z", "a", "m")  # a declared Enum order is kept
    with pytest.raises(PolarisValidationError, match="at least 2"):
        gam('y ~ g + s(x, bs="cr", k=6)', frame.with_columns(g=pl.lit("only")), "gaussian")
    with pytest.raises(PolarisValidationError, match="numeric column"):
        gam('y ~ g + s(x, bs="cr", k=6)', frame.with_columns(g=pl.col("x") > 5), "gaussian")


def test_family_with_link_and_fitted_binomial_cloglog(frame: pl.DataFrame) -> None:
    rng = np.random.default_rng(3)
    d = frame.with_columns(
        y=pl.Series(rng.binomial(1, 1 / (1 + np.exp(-np.sin(frame["x"].to_numpy())))))
    )
    fit = gam('y ~ s(x, bs="cr", k=6)', d, 'binomial(link="cloglog")')
    assert fit.model.link == "cloglog"
    assert gam('y ~ s(x, bs="cr", k=6)', d, "binomial").model.link == "logit"
