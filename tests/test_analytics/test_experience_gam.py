"""
Tests for the Slice-1 Experience GAM — the interpretable additive A/E layer.

Covers the Slice-1 acceptance criteria from docs/PLAN_experience_gam.md:
- grouped-vs-seriatim sufficiency (identical coefficients within tolerance)
- synthetic multiplier recovery (known A/E level recovered)
- by-amount overdispersion handled (dispersion φ > 1 recovered; bands widen)
- round-trip export→load identity (blended basexmultiplier CSV loads back)
- per-feature smooth effect + confidence-band ordering / coverage
- import-guard when the [ml] extra (statsmodels) is absent
- aggregate_seriatim and attach_base_rate contract helpers

All randomness is seeded; no test depends on the wall clock (ADR-074 guard).
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    AMOUNT_MEASURES,
    ExperienceGAM,
    aggregate_seriatim,
    attach_base_rate,
)
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.utils.table_io import load_mortality_csv

SEED = 20260721


# --------------------------------------------------------------------------- #
# Synthetic data helpers
# --------------------------------------------------------------------------- #


def _balanced_seriatim(
    *,
    ages: np.ndarray,
    per_age: int,
    q_base: float,
    multiplier_fn,
    seed: int = SEED,
) -> pl.DataFrame:
    """
    Build a *balanced* seriatim experience set: exactly ``per_age`` single-policy
    rows per attained age, each with exposure 1 and a Bernoulli death.

    Balancing (equal replication per age) means the empirical age-quantiles of the
    seriatim set equal those of the collapsed grouped set, so the B-spline knots —
    and therefore the fitted coefficients — coincide. This makes the
    grouped-vs-seriatim sufficiency comparison exact.
    """
    rng = np.random.default_rng(seed)
    rows_age = np.repeat(ages, per_age)
    mult = multiplier_fn(rows_age.astype(float))
    p = np.clip(q_base * mult, 0.0, 1.0)
    deaths = (rng.random(rows_age.size) < p).astype(np.float64)
    return pl.DataFrame(
        {
            "attained_age": rows_age.astype(np.int64),
            "central_exposure": np.ones(rows_age.size, dtype=np.float64),
            "death_count": deaths,
            "q_base": np.full(rows_age.size, q_base, dtype=np.float64),
        }
    )


def _grouped_from_seriatim(seriatim: pl.DataFrame) -> pl.DataFrame:
    """Collapse a seriatim frame to one row per (attained_age, q_base) cell."""
    return (
        seriatim.group_by(["attained_age", "q_base"])
        .agg(
            pl.col("central_exposure").sum().alias("central_exposure"),
            pl.col("death_count").sum().alias("death_count"),
        )
        .sort("attained_age")
    )


# --------------------------------------------------------------------------- #
# Grouped-vs-seriatim sufficiency (anchor 7)
# --------------------------------------------------------------------------- #


def test_grouped_and_seriatim_fits_are_identical():
    """Grouping is sufficiency: identical coefficients within tolerance."""
    ages = np.arange(40, 65)
    seriatim = _balanced_seriatim(
        ages=ages,
        per_age=300,
        q_base=0.01,
        multiplier_fn=lambda a: 1.2 + 0.01 * (a - 40),
    )
    grouped = _grouped_from_seriatim(seriatim)

    fit_ser = ExperienceGAM(seriatim, basis="count", age_df=5).fit()
    fit_grp = ExperienceGAM(grouped, basis="count", age_df=5).fit()

    params_ser = np.asarray(fit_ser._result.params, dtype=np.float64)
    params_grp = np.asarray(fit_grp._result.params, dtype=np.float64)
    np.testing.assert_allclose(params_ser, params_grp, rtol=1e-6, atol=1e-8)
    # And the aggregate A/E must match exactly.
    np.testing.assert_allclose(fit_ser.overall_ae, fit_grp.overall_ae, rtol=1e-10)


def test_aggregate_seriatim_matches_manual_grouping():
    """aggregate_seriatim sums measures over covariate keys."""
    seriatim = pl.DataFrame(
        {
            "attained_age": [50, 50, 51, 51, 51],
            "sex": ["M", "M", "M", "F", "F"],
            "central_exposure": [1.0, 1.0, 1.0, 1.0, 1.0],
            "death_count": [0.0, 1.0, 1.0, 0.0, 1.0],
        }
    )
    grouped = aggregate_seriatim(seriatim)
    assert grouped.height == 3  # (50,M), (51,M), (51,F)
    row_50m = grouped.filter((pl.col("attained_age") == 50) & (pl.col("sex") == "M"))
    assert row_50m["central_exposure"][0] == 2.0
    assert row_50m["death_count"][0] == 1.0


def test_aggregate_seriatim_requires_a_measure():
    with pytest.raises(PolarisValidationError, match="no recognised measure"):
        aggregate_seriatim(pl.DataFrame({"attained_age": [50], "sex": ["M"]}))


# --------------------------------------------------------------------------- #
# Synthetic multiplier recovery
# --------------------------------------------------------------------------- #


def test_recovers_known_flat_multiplier():
    """A constant A/E multiplier is recovered by the fit."""
    ages = np.arange(35, 80)
    true_mult = 1.35
    rng = np.random.default_rng(SEED)
    q_base = 0.004 * np.exp(0.06 * (ages - 35))
    exposure = np.full(ages.size, 5000.0)
    expected = exposure * q_base * true_mult
    deaths = rng.poisson(expected).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": exposure,
            "death_count": deaths,
            "q_base": q_base,
        }
    )
    fit = ExperienceGAM(cells, basis="count", age_df=5).fit()
    # Overall A/E and the fitted multiplier across ages both recover ~1.35.
    assert fit.overall_ae == pytest.approx(true_mult, rel=0.05)
    mult = fit.predict_multiplier(cells)
    assert float(np.mean(mult)) == pytest.approx(true_mult, rel=0.06)


def test_recovers_age_varying_multiplier_shape():
    """A rising A/E gradient in age is recovered as a rising smooth effect."""
    ages = np.arange(35, 85)
    rng = np.random.default_rng(SEED + 1)
    q_base = 0.003 * np.exp(0.07 * (ages - 35))
    exposure = np.full(ages.size, 20000.0)
    true_mult = 0.8 + 0.02 * (ages - 35)  # 0.8 → 1.78
    deaths = rng.poisson(exposure * q_base * true_mult).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": exposure,
            "death_count": deaths,
            "q_base": q_base,
        }
    )
    fit = ExperienceGAM(cells, basis="count", age_df=6).fit()
    eff = fit.smooth_effect("attained_age", grid=np.array([40.0, 60.0, 80.0]))
    # Monotone increasing multiplier across the grid.
    assert eff.multiplier[0] < eff.multiplier[1] < eff.multiplier[2]
    # Band brackets the point estimate.
    assert np.all(eff.lower <= eff.multiplier)
    assert np.all(eff.multiplier <= eff.upper)


def test_smooth_features_lists_fitted_smooth_terms():
    """``smooth_features`` is the public, drift-free list of fitted smooth terms.

    It mirrors :attr:`factors`, is authoritative for :meth:`smooth_effect`
    (every listed name resolves; nothing else does), and grows to include
    ``duration_years`` exactly when a varying duration enters the fit.
    """
    ages = np.arange(40, 70)
    rng = np.random.default_rng(SEED + 9)
    q_base = 0.004 * np.exp(0.06 * (ages - 40))
    exposure = np.full(ages.size, 30000.0)
    deaths = rng.poisson(exposure * q_base * 1.1).astype(np.float64)
    base = {
        "attained_age": ages.astype(np.int64),
        "central_exposure": exposure,
        "death_count": deaths,
        "q_base": q_base,
    }

    # Age-only fit: exactly the attained-age smooth, and every listed name works.
    fit = ExperienceGAM(pl.DataFrame(base), basis="count", age_df=5).fit()
    assert fit.smooth_features == ["attained_age"]
    for feature in fit.smooth_features:
        fit.smooth_effect(feature, grid=np.array([45.0, 60.0]))  # resolves
    with pytest.raises(PolarisValidationError):
        fit.smooth_effect("duration_years", grid=np.array([1.0]))  # not fitted

    # Add a varying duration → the duration smooth joins the public list.
    with_dur = pl.DataFrame({**base, "duration_months": (12 * ((ages - 40) % 5 + 1))})
    fit_dur = ExperienceGAM(with_dur, basis="count", age_df=5, duration_df=4).fit()
    assert set(fit_dur.smooth_features) == {"attained_age", "duration_years"}


# --------------------------------------------------------------------------- #
# Multi-factor path (regression guard for the __levels__ bookkeeping bug)
# --------------------------------------------------------------------------- #


def test_factor_path_predict_smooth_and_export_with_varying_factor():
    """
    With a varying categorical factor in the fit, smooth_effect / factor_effect /
    export_to_mortality_csv all succeed and recover the injected factor multiplier.

    Guards the bug where the ``__levels__<factor>`` bookkeeping entries leaked into
    the reference frame as ragged columns, crashing every prediction/export path
    the moment a factor entered the model.
    """
    ages = np.arange(40, 75)
    rng = np.random.default_rng(SEED + 6)
    q_base = 0.004 * np.exp(0.06 * (ages - 40))
    exposure = np.full(ages.size, 40000.0)
    female_ratio = 0.7  # females run 0.7x the male A/E level

    frames = []
    for sex, ratio in (("M", 1.0), ("F", female_ratio)):
        deaths = rng.poisson(exposure * q_base * 1.2 * ratio).astype(np.float64)
        frames.append(
            pl.DataFrame(
                {
                    "attained_age": ages.astype(np.int64),
                    "sex": [sex] * ages.size,
                    "central_exposure": exposure,
                    "death_count": deaths,
                    "q_base": q_base,
                }
            )
        )
    cells = pl.concat(frames)

    fit = ExperienceGAM(cells, basis="count", age_df=5).fit()
    assert "sex" in fit.factors

    # factor_effect recovers the injected ratio; reference level pinned to 1.0.
    fe = fit.factor_effect("sex")
    fe_map = {row["sex"]: row["multiplier"] for row in fe.to_dicts()}
    band = {row["sex"]: (row["lower"], row["upper"]) for row in fe.to_dicts()}
    # One level is the reference (multiplier exactly 1.0, zero-width band).
    ref_level = next(k for k, v in fe_map.items() if v == pytest.approx(1.0, abs=1e-12))
    other = "F" if ref_level == "M" else "M"
    expected_ratio = female_ratio if other == "F" else 1.0 / female_ratio
    assert fe_map[other] == pytest.approx(expected_ratio, rel=0.12)
    # Reference-level band is degenerate (pinned).
    assert band[ref_level][0] == pytest.approx(1.0, abs=1e-9)
    assert band[ref_level][1] == pytest.approx(1.0, abs=1e-9)

    # smooth_effect works with a factor present (others held at modal level).
    eff = fit.smooth_effect("attained_age", grid=np.array([45.0, 65.0]))
    assert np.all(eff.lower <= eff.multiplier)
    assert np.all(eff.multiplier <= eff.upper)

    # export succeeds with a factor in the fit.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        out = fit.export_to_mortality_csv(Path(d) / "blended.csv", ages=ages, q_base_by_age=q_base)
        assert out.exists()


# --------------------------------------------------------------------------- #
# By-amount overdispersion
# --------------------------------------------------------------------------- #


def test_by_amount_overdispersion_recovered_and_widens_bands():
    """The by-amount basis recovers φ > 1 and widens confidence bands vs count."""
    ages = np.arange(40, 75)
    rng = np.random.default_rng(SEED + 2)
    q_base = 0.005 * np.exp(0.05 * (ages - 40))
    amount_exposed = np.full(ages.size, 1.0e8)
    expected = amount_exposed * q_base * 1.1
    # Gamma-mixed Poisson → strong overdispersion on the amount basis.
    gamma = rng.gamma(shape=0.5, scale=2.0, size=ages.size)
    death_amount = rng.poisson(expected * gamma).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "amount_exposed": amount_exposed,
            "death_amount": death_amount,
            "q_base": q_base,
        }
    )
    fit_amount = ExperienceGAM(cells, basis="amount", age_df=4).fit()
    assert fit_amount.overdispersion_applied is True
    assert fit_amount.dispersion > 1.5

    # Same cell structure fit WITHOUT overdispersion → narrower age-effect band.
    fit_plain = ExperienceGAM(cells, basis="amount", age_df=4, overdispersion=False).fit()
    grid = np.array([50.0])
    band_od = fit_amount.smooth_effect("attained_age", grid)
    band_plain = fit_plain.smooth_effect("attained_age", grid)
    width_od = float(band_od.upper[0] - band_od.lower[0])
    width_plain = float(band_plain.upper[0] - band_plain.lower[0])
    assert width_od > width_plain


def test_count_basis_default_no_overdispersion():
    ages = np.arange(40, 60)
    q_base = np.full(ages.size, 0.01)
    rng = np.random.default_rng(SEED + 4)
    deaths = rng.poisson(1000.0 * q_base * 1.1).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": np.full(ages.size, 1000.0),
            "death_count": deaths,
            "q_base": q_base,
        }
    )
    fit = ExperienceGAM(cells, basis="count").fit()
    assert fit.overdispersion_applied is False


# --------------------------------------------------------------------------- #
# Export round-trip
# --------------------------------------------------------------------------- #


def test_export_roundtrips_through_mortality_loader(tmp_path):
    """export_to_mortality_csv writes a table that load_mortality_csv reads back."""
    from polaris_re.utils.table_io import load_mortality_csv

    ages = np.arange(40, 80)
    rng = np.random.default_rng(SEED + 3)
    q_base = 0.004 * np.exp(0.06 * (ages - 40))
    exposure = np.full(ages.size, 10000.0)
    deaths = rng.poisson(exposure * q_base * 1.2).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": exposure,
            "death_count": deaths,
            "q_base": q_base,
        }
    )
    fit = ExperienceGAM(cells, basis="count", age_df=5).fit()

    out = tmp_path / "blended.csv"
    fit.export_to_mortality_csv(out, ages=ages, q_base_by_age=q_base)
    assert out.exists()

    # Expected blended rate = q_base x fitted multiplier at reference.
    ref_frame = pl.DataFrame({"attained_age": ages.astype(np.float64)})
    expected_blended = q_base * fit.predict_multiplier(ref_frame)

    loaded = load_mortality_csv(out, select_period=0, min_age=int(ages.min()))
    got = loaded.get_rate_vector(ages.astype(np.int32), np.zeros(ages.size, dtype=np.int32))
    np.testing.assert_allclose(got, expected_blended, rtol=1e-9, atol=1e-12)


def test_export_rejects_non_contiguous_ages(tmp_path):
    ages = np.arange(40, 60)
    rng = np.random.default_rng(SEED + 5)
    deaths = rng.poisson(1000.0 * 0.01 * 1.1, size=ages.size).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": np.full(ages.size, 1000.0),
            "death_count": deaths,
            "q_base": np.full(ages.size, 0.01),
        }
    )
    fit = ExperienceGAM(cells, basis="count").fit()
    bad_ages = np.array([40, 41, 43])
    with pytest.raises(PolarisValidationError, match="contiguous"):
        fit.export_to_mortality_csv(
            tmp_path / "x.csv", ages=bad_ages, q_base_by_age=np.full(3, 0.01)
        )


# --------------------------------------------------------------------------- #
# attach_base_rate with a real table
# --------------------------------------------------------------------------- #


FIXTURES = Path(__file__).parent.parent / "fixtures"


def _fixture_table() -> MortalityTable:
    """Build a select-and-ultimate MortalityTable from the shared fixture CSV."""
    table_array = load_mortality_csv(
        FIXTURES / "synthetic_select_ultimate.csv",
        select_period=3,
        min_age=18,
        max_age=60,
    )
    return MortalityTable.from_table_array(
        source=MortalityTableSource.SOA_VBT_2015,
        table_name="Synthetic Test",
        table_array=table_array,
        sex=Sex.MALE,
        smoker_status=SmokerStatus.NON_SMOKER,
    )


def test_attach_base_rate_matches_direct_annual_lookup():
    """attach_base_rate matches the table's annual select-and-ultimate rate."""
    table = _fixture_table()
    ages = np.array([45, 55, 60], dtype=np.int64)
    dur_months = np.array([0, 24, 48], dtype=np.int64)
    cells = pl.DataFrame(
        {
            "attained_age": ages,
            "duration_months": dur_months,
            "sex": ["M", "M", "M"],
            "smoker": ["NS", "NS", "NS"],
            "central_exposure": [100.0, 100.0, 100.0],
            "death_count": [1.0, 1.0, 1.0],
        }
    )
    out = attach_base_rate(cells, table)
    assert "q_base" in out.columns
    q_base = out["q_base"].to_numpy()
    assert np.all(q_base > 0.0)
    assert np.all(q_base <= 1.0)

    # Compare to a direct monthly→annual conversion of the same lookup.
    q_monthly = table.get_qx_vector(
        ages.astype(np.int32),
        Sex.MALE,
        SmokerStatus.NON_SMOKER,
        dur_months.astype(np.int32),
    )
    q_annual = 1.0 - np.power(1.0 - q_monthly, 12.0)
    np.testing.assert_allclose(q_base, q_annual, rtol=1e-12)


def test_attach_base_rate_requires_attained_age():
    with pytest.raises(PolarisValidationError, match="attained_age"):
        attach_base_rate(pl.DataFrame({"sex": ["M"]}), None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Contract validation
# --------------------------------------------------------------------------- #


def test_missing_measure_columns_raise():
    cells = pl.DataFrame({"attained_age": [50], "q_base": [0.01]})
    with pytest.raises(PolarisValidationError, match="missing required columns"):
        ExperienceGAM(cells, basis="count")


def test_invalid_q_base_rejected():
    cells = pl.DataFrame(
        {
            "attained_age": [50, 51],
            "central_exposure": [100.0, 100.0],
            "death_count": [1.0, 1.0],
            "q_base": [0.0, 1.5],
        }
    )
    with pytest.raises(PolarisValidationError, match="q_base"):
        ExperienceGAM(cells, basis="count")


def test_bad_basis_rejected():
    cells = pl.DataFrame(
        {"attained_age": [50], "central_exposure": [100.0], "death_count": [1.0], "q_base": [0.01]}
    )
    with pytest.raises(PolarisValidationError, match="basis"):
        ExperienceGAM(cells, basis="frequency")


def test_amount_measures_constant_is_exposed():
    assert AMOUNT_MEASURES == ("amount_exposed", "death_amount")


# --------------------------------------------------------------------------- #
# Import guard ([ml] extra absent)
# --------------------------------------------------------------------------- #


def test_fit_without_statsmodels_raises_actionable_error(monkeypatch):
    """When statsmodels is unimportable, fit() raises an actionable error."""
    cells = pl.DataFrame(
        {
            "attained_age": [50, 55, 60],
            "central_exposure": [1000.0, 1000.0, 1000.0],
            "death_count": [10.0, 12.0, 15.0],
            "q_base": [0.01, 0.012, 0.015],
        }
    )
    gam = ExperienceGAM(cells, basis="count")
    # Setting the module to None makes `import statsmodels.api` raise ImportError.
    monkeypatch.setitem(sys.modules, "statsmodels.api", None)
    with pytest.raises(PolarisComputationError, match="statsmodels"):
        gam.fit()


# --------------------------------------------------------------------------- #
# Slice 4d-1: public feature_ranges + all_effects (PR #148 review option-3)
# --------------------------------------------------------------------------- #


def _rich_cells() -> pl.DataFrame:
    """A cells frame exercising all effect branches: age + varying duration + factor."""
    ages = np.arange(40, 75)
    rng = np.random.default_rng(SEED + 21)
    q_base = 0.004 * np.exp(0.06 * (ages - 40))
    exposure = np.full(ages.size, 40000.0)
    frames = []
    for sex, ratio in (("M", 1.0), ("F", 0.7)):
        deaths = rng.poisson(exposure * q_base * 1.2 * ratio).astype(np.float64)
        frames.append(
            pl.DataFrame(
                {
                    "attained_age": ages.astype(np.int64),
                    "sex": [sex] * ages.size,
                    "central_exposure": exposure,
                    "death_count": deaths,
                    "q_base": q_base,
                    "duration_months": (12 * ((ages - 40) % 5 + 1)).astype(np.int64),
                }
            )
        )
    return pl.concat(frames)


def test_feature_ranges_captured_at_fit():
    """``feature_ranges`` records each smooth's observed span at fit time, keyed
    by the same names as ``smooth_features`` — including the fit-derived
    ``duration_years`` (which never appears in the source cells)."""
    cells = _rich_cells()
    fit = ExperienceGAM(cells, basis="count", age_df=5, duration_df=4).fit()

    assert set(fit.feature_ranges) == set(fit.smooth_features)
    # attained_age span matches the cells directly.
    age = cells["attained_age"].to_numpy().astype(np.float64)
    assert fit.feature_ranges["attained_age"] == (float(age.min()), float(age.max()))
    # duration_years is derived (duration_months / 12) and not a cells column.
    assert "duration_years" not in cells.columns
    dur = (cells["duration_months"] / 12.0).to_numpy().astype(np.float64)
    lo, hi = fit.feature_ranges["duration_years"]
    np.testing.assert_allclose([lo, hi], [dur.min(), dur.max()])


def test_feature_ranges_age_only_fit():
    """With no varying duration, only the attained-age smooth carries a range."""
    ages = np.arange(45, 70)
    rng = np.random.default_rng(SEED + 22)
    q_base = 0.005 * np.exp(0.05 * (ages - 45))
    exposure = np.full(ages.size, 25000.0)
    deaths = rng.poisson(exposure * q_base * 1.1).astype(np.float64)
    cells = pl.DataFrame(
        {
            "attained_age": ages.astype(np.int64),
            "central_exposure": exposure,
            "death_count": deaths,
            "q_base": q_base,
        }
    )
    fit = ExperienceGAM(cells, basis="count", age_df=5).fit()
    assert list(fit.feature_ranges) == ["attained_age"]
    assert fit.feature_ranges["attained_age"] == (float(ages.min()), float(ages.max()))


def test_all_effects_tidy_schema_and_grid():
    """``all_effects`` returns the tidy long-format frame: a smooth block per
    smooth feature (sampled over its fitted range) plus one row per factor level,
    with first-class ``lower``/``upper`` bands."""
    cells = _rich_cells()
    fit = ExperienceGAM(cells, basis="count", age_df=5, duration_df=4).fit()
    gp = 30
    eff = fit.all_effects(grid_points=gp, confidence_level=0.95)

    assert eff.columns == [
        "feature",
        "term_type",
        "x",
        "x_value",
        "multiplier",
        "lower",
        "upper",
    ]
    # Each smooth contributes gp rows spanning exactly its feature_ranges.
    for feature in fit.smooth_features:
        block = eff.filter((pl.col("feature") == feature) & (pl.col("term_type") == "smooth"))
        assert block.height == gp
        lo, hi = fit.feature_ranges[feature]
        xs = block["x_value"].to_numpy()
        np.testing.assert_allclose([xs.min(), xs.max()], [lo, hi])
    # The factor contributes one row per level, all with a null x_value.
    fac = eff.filter(pl.col("term_type") == "factor")
    assert set(fac["feature"].unique().to_list()) == {"sex"}
    assert fac["x_value"].null_count() == fac.height
    # Bands bracket the point estimate everywhere.
    assert (eff["lower"] <= eff["multiplier"]).all()
    assert (eff["multiplier"] <= eff["upper"]).all()


def test_all_effects_matches_legacy_cells_derived_frame():
    """Regression guard: ``all_effects`` reproduces the exact frame the CLI used to
    build by reaching back into the source cells for smooth spans — so the
    ``--effects-out`` artifact is byte-identical after the refactor."""

    def _legacy_collect(result, cells, *, grid_points, confidence_level):
        frames = []
        for feature in result.smooth_features:
            if feature == "duration_years" and feature not in cells.columns:
                span = (cells["duration_months"] / 12.0).to_numpy().astype(np.float64)
            elif feature in cells.columns:
                span = cells[feature].to_numpy().astype(np.float64)
            else:
                span = cells["attained_age"].to_numpy().astype(np.float64)
            grid = np.linspace(float(span.min()), float(span.max()), grid_points)
            e = result.smooth_effect(feature, grid, confidence_level=confidence_level)
            frames.append(
                pl.DataFrame(
                    {
                        "feature": [feature] * grid_points,
                        "term_type": ["smooth"] * grid_points,
                        "x": [f"{g:g}" for g in e.grid],
                        "x_value": e.grid.astype(np.float64),
                        "multiplier": e.multiplier.astype(np.float64),
                        "lower": e.lower.astype(np.float64),
                        "upper": e.upper.astype(np.float64),
                    }
                )
            )
        for factor in result.factors:
            fe = result.factor_effect(factor, confidence_level=confidence_level)
            frames.append(
                pl.DataFrame(
                    {
                        "feature": [factor] * fe.height,
                        "term_type": ["factor"] * fe.height,
                        "x": fe[factor].cast(pl.Utf8),
                        "x_value": pl.Series([None] * fe.height, dtype=pl.Float64),
                        "multiplier": fe["multiplier"],
                        "lower": fe["lower"],
                        "upper": fe["upper"],
                    }
                )
            )
        return pl.concat(frames, how="vertical")

    cells = _rich_cells()
    fit = ExperienceGAM(cells, basis="count", age_df=5, duration_df=4).fit()
    legacy = _legacy_collect(fit, cells, grid_points=50, confidence_level=0.9)
    new = fit.all_effects(grid_points=50, confidence_level=0.9)

    assert legacy.columns == new.columns
    assert legacy.schema == new.schema
    for col in ("feature", "term_type", "x"):
        assert legacy[col].to_list() == new[col].to_list()
    for col in ("x_value", "multiplier", "lower", "upper"):
        np.testing.assert_allclose(
            new[col].to_numpy().astype(np.float64),
            legacy[col].to_numpy().astype(np.float64),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        )
