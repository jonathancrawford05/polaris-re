"""Tests for the ``polaris experience improvement`` CLI surface (A4' Slice 4a).

Exercises the experience → mortality-improvement pipeline through the CLI: a
grouped-cell experience CSV is fit to a tensor MI surface (frequentist or
Bayesian) and emitted as an ``ImprovementScale.CUSTOM`` ``MortalityImprovement``
that round-trips through JSON and reproduces ``apply_improvement`` exactly. Uses
Typer's ``CliRunner`` in-process.

All fixtures pin explicit ages/years (ADR-074 guard) — no test reads the wall
clock; the base year is a literal in the synthetic CSV.
"""

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from typer.testing import CliRunner

from polaris_re.assumptions.improvement import ImprovementScale, MortalityImprovement
from polaris_re.cli import app

runner = CliRunner()

# The frequentist tensor spline perfectly separates on the noise-free synthetic
# cells (deaths == expected); statsmodels warns but the fit is exact.
pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)

_AGES = np.arange(40, 71)
_YEARS = np.arange(2010, 2021)
_BASE_YEAR = int(_YEARS.min())


def _q_base(age: int) -> float:
    """A smooth, increasing static base rate ``q_base(age)`` in (0, 1)."""
    return 0.004 * float(np.exp(0.08 * (age - 45.0)))


def _write_experience_csv(path: Path, mi: float = 0.015, *, with_q_base: bool = True) -> None:
    """Grouped cells whose actual mortality is ``q_base(age)·(1-mi)^(year-base)``.

    Deaths are set to the expected count so a fit recovers the flat improvement
    ``mi`` exactly (closed-form verification). ``with_q_base=False`` drops the
    offset column to exercise the ``--table`` attach path.
    """
    rows = []
    for a in _AGES:
        q0 = _q_base(int(a))
        for y in _YEARS:
            actual_q = q0 * (1.0 - mi) ** (int(y) - _BASE_YEAR)
            rows.append((int(a), int(y), q0, 2.0e6, 2.0e6 * actual_q))
    frame = pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "central_exposure", "death_count"],
        orient="row",
    )
    if not with_q_base:
        frame = frame.drop("q_base")
    frame.write_csv(path)


def _write_synthetic_cso_dir(data_dir: Path) -> None:
    """A minimal CSO-2001-format table dir (``age,rate``) for the attach path.

    Two files (``cso_2001_male.csv`` / ``cso_2001_female.csv``) spanning ages
    0-100 — enough for ``MortalityTable.load(CSO_2001)`` and the 40-70 cells.
    """
    tables_dir = data_dir / "mortality_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    ages = np.arange(0, 101)
    rate = 0.0004 * np.exp(0.09 * (ages - 40.0))
    rate = np.clip(rate, 1e-5, 0.5)
    for sex in ("male", "female"):
        pl.DataFrame({"age": ages.astype(np.int64), "rate": rate.astype(np.float64)}).write_csv(
            tables_dir / f"cso_2001_{sex}.csv"
        )


# --------------------------------------------------------------------------- #
# Frequentist surface → CUSTOM scale (closed-form verification)
# --------------------------------------------------------------------------- #


def test_frequentist_improvement_recovers_flat_mi_and_emits_scale(tmp_path: Path) -> None:
    """A flat 1.5%/yr improvement is recovered and the emitted CUSTOM scale
    reproduces ``q·(1-mi)^n`` under ``apply_improvement``."""
    exp = tmp_path / "exp.csv"
    out = tmp_path / "scale.json"
    _write_experience_csv(exp, mi=0.015)

    result = runner.invoke(app, ["experience", "improvement", "-e", str(exp), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "CUSTOM" in result.output

    scale = MortalityImprovement.model_validate_json(out.read_text())
    assert scale.scale is ImprovementScale.CUSTOM
    # The MI surface reports interior steps (years 2011..2020), so the emitted
    # scale's base year is first-grid-year - 1 == 2011 - 1 == 2010.
    assert scale.base_year == _BASE_YEAR

    # apply_improvement accumulates Z = base+1..Y, so Y = base+4 is 4 flat steps.
    ages = np.array([50, 60], dtype=np.int64)
    q = np.array([0.01, 0.02], dtype=np.float64)
    improved = scale.apply_improvement(q, ages, _BASE_YEAR + 4)
    expected = q * (1.0 - 0.015) ** 4
    np.testing.assert_allclose(improved, expected, rtol=1e-9)


def test_grid_out_writes_long_format(tmp_path: Path) -> None:
    """``--grid-out`` writes the MI_x(y) surface in long format with the band."""
    exp = tmp_path / "exp.csv"
    grid = tmp_path / "grid.csv"
    _write_experience_csv(exp, mi=0.02)

    result = runner.invoke(
        app, ["experience", "improvement", "-e", str(exp), "--grid-out", str(grid)]
    )
    assert result.exit_code == 0, result.output

    df = pl.read_csv(grid)
    assert set(df.columns) == {"attained_age", "calendar_year", "mi", "mi_lower", "mi_upper"}
    # One row per (age, interior step-end year): ages x (years - 1).
    assert df.height == len(_AGES) * (len(_YEARS) - 1)
    # Interior improvement recovers the flat 2%.
    interior = df.filter(
        (pl.col("attained_age").is_between(48, 62))
        & (pl.col("calendar_year").is_between(2013, 2018))
    )
    np.testing.assert_allclose(interior["mi"].to_numpy().mean(), 0.02, atol=5e-4)


def test_ultimate_rate_override_flows_into_scale(tmp_path: Path) -> None:
    """``--ultimate-rate`` sets the emitted scale's beyond-grid improvement."""
    exp = tmp_path / "exp.csv"
    out = tmp_path / "scale.json"
    _write_experience_csv(exp)

    result = runner.invoke(
        app,
        ["experience", "improvement", "-e", str(exp), "--ultimate-rate", "0.005", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    scale = MortalityImprovement.model_validate_json(out.read_text())
    assert scale.custom_ultimate_rate == pytest.approx(0.005)


# --------------------------------------------------------------------------- #
# Bayesian surface + projection
# --------------------------------------------------------------------------- #


def test_bayesian_surface_emits_custom_scale(tmp_path: Path) -> None:
    """The Bayesian reduced-rank-GP surface emits a valid CUSTOM scale."""
    exp = tmp_path / "exp.csv"
    out = tmp_path / "scale.json"
    _write_experience_csv(exp, mi=0.015)

    result = runner.invoke(
        app, ["experience", "improvement", "-e", str(exp), "--bayesian", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "bayesian" in result.output
    scale = MortalityImprovement.model_validate_json(out.read_text())
    assert scale.scale is ImprovementScale.CUSTOM
    assert scale.base_year == _BASE_YEAR


def test_bayesian_projection_emits_future_grid(tmp_path: Path) -> None:
    """``--project-horizon`` emits a scale anchored on the last observed year,
    mean-reverting to ``--long-term-rate`` (the beyond-grid ultimate)."""
    exp = tmp_path / "exp.csv"
    out = tmp_path / "scale.json"
    _write_experience_csv(exp, mi=0.015)

    result = runner.invoke(
        app,
        [
            "experience",
            "improvement",
            "-e",
            str(exp),
            "--bayesian",
            "--project-horizon",
            "8",
            "--long-term-rate",
            "0.006",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    scale = MortalityImprovement.model_validate_json(out.read_text())
    # Projection base year is the last observed calendar year (2020).
    assert scale.base_year == int(_YEARS.max())
    # Grid covers the 8 projected future years 2021..2028.
    assert scale.custom_years == tuple(range(2021, 2029))
    # Beyond the horizon, improvement continues at the long-term rate.
    assert scale.custom_ultimate_rate == pytest.approx(0.006)


# --------------------------------------------------------------------------- #
# --table attach path
# --------------------------------------------------------------------------- #


def test_table_attach_path_builds_q_base(tmp_path: Path) -> None:
    """A CSV lacking ``q_base`` attaches the static base from ``--table``."""
    exp = tmp_path / "exp.csv"
    out = tmp_path / "scale.json"
    _write_experience_csv(exp, with_q_base=False)
    data_dir = tmp_path / "data"
    _write_synthetic_cso_dir(data_dir)

    result = runner.invoke(
        app,
        [
            "experience",
            "improvement",
            "-e",
            str(exp),
            "--table",
            "cso_2001",
            "--data-dir",
            str(data_dir / "mortality_tables"),
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    scale = MortalityImprovement.model_validate_json(out.read_text())
    assert scale.scale is ImprovementScale.CUSTOM


# --------------------------------------------------------------------------- #
# Effect-shape diagnostics — `polaris experience fit` (A4' Slice 4b-1)
# --------------------------------------------------------------------------- #


def _write_factor_experience_csv(
    path: Path, *, mi: float = 0.015, female_mult: float = 0.8
) -> None:
    """Grouped cells with a ``sex`` factor whose female A/E multiplier is exact.

    Actual mortality is ``q_base(age)·sex_mult·(1-mi)^(year-base)`` with the
    male level at 1.0 and the female level at ``female_mult`` — so a fitted
    ``ExperienceGAM`` recovers ``female_mult`` on the ``sex`` factor exactly
    (closed-form verification of the effect-shape diagnostics).
    """
    rows = []
    for a in _AGES:
        q0 = _q_base(int(a))
        for y in _YEARS:
            for sex, mult in (("M", 1.0), ("F", female_mult)):
                actual_q = q0 * mult * (1.0 - mi) ** (int(y) - _BASE_YEAR)
                rows.append((int(a), int(y), q0, sex, 2.0e6, 2.0e6 * actual_q))
    pl.DataFrame(
        rows,
        schema=[
            "attained_age",
            "calendar_year",
            "q_base",
            "sex",
            "central_exposure",
            "death_count",
        ],
        orient="row",
    ).write_csv(path)


def test_fit_reports_overall_ae_and_active_factors(tmp_path: Path) -> None:
    """``experience fit`` renders the fit summary (A/E, dispersion, factors)."""
    exp = tmp_path / "exp.csv"
    _write_factor_experience_csv(exp, female_mult=0.8)

    result = runner.invoke(app, ["experience", "fit", "-e", str(exp)])
    assert result.exit_code == 0, result.output
    # Summary surfaces the headline diagnostics and the active `sex` factor.
    assert "A/E" in result.output
    assert "Dispersion" in result.output
    assert "sex" in result.output


def test_fit_effects_out_recovers_factor_multiplier(tmp_path: Path) -> None:
    """The ``--effects-out`` long-format CSV recovers the exact factor multiplier."""
    exp = tmp_path / "exp.csv"
    effects = tmp_path / "effects.csv"
    _write_factor_experience_csv(exp, female_mult=0.75)

    result = runner.invoke(
        app, ["experience", "fit", "-e", str(exp), "--effects-out", str(effects)]
    )
    assert result.exit_code == 0, result.output

    df = pl.read_csv(effects)
    assert set(df.columns) == {
        "feature",
        "term_type",
        "x",
        "x_value",
        "multiplier",
        "lower",
        "upper",
    }
    # Both a smooth (attained_age) and a factor (sex) effect are present.
    assert set(df["term_type"].unique().to_list()) == {"smooth", "factor"}
    assert "attained_age" in df["feature"].unique().to_list()

    # factor_effect reports each level relative to the modal reference level
    # (which of M/F is reference is a tie here), so the *contrast* F/M — not the
    # absolute multiplier — is the invariant the fit recovers.
    female = df.filter((pl.col("feature") == "sex") & (pl.col("x") == "F"))
    male = df.filter((pl.col("feature") == "sex") & (pl.col("x") == "M"))
    assert female.height == 1 and male.height == 1
    ratio = female["multiplier"].to_numpy()[0] / male["multiplier"].to_numpy()[0]
    np.testing.assert_allclose(ratio, 0.75, atol=1e-3)
    # Exactly one level is the reference — it sits at exactly 1.0.
    mults = df.filter(pl.col("feature") == "sex")["multiplier"].to_numpy()
    assert np.isclose(mults, 1.0).sum() == 1


def test_fit_smooth_grid_spans_observed_range(tmp_path: Path) -> None:
    """Smooth effects are sampled across the observed feature range at --grid-points."""
    exp = tmp_path / "exp.csv"
    effects = tmp_path / "effects.csv"
    _write_factor_experience_csv(exp)

    result = runner.invoke(
        app,
        ["experience", "fit", "-e", str(exp), "--effects-out", str(effects), "--grid-points", "25"],
    )
    assert result.exit_code == 0, result.output

    df = pl.read_csv(effects)
    age = df.filter((pl.col("feature") == "attained_age") & (pl.col("term_type") == "smooth"))
    assert age.height == 25
    assert age["x_value"].min() == float(_AGES.min())
    assert age["x_value"].max() == float(_AGES.max())


def test_fit_amount_basis(tmp_path: Path) -> None:
    """``--basis amount`` fits the face-weighted experience (dispersion widens)."""
    exp = tmp_path / "exp.csv"
    rows = []
    for a in _AGES:
        q0 = _q_base(int(a))
        for y in _YEARS:
            actual_q = q0 * (1.0 - 0.015) ** (int(y) - _BASE_YEAR)
            rows.append((int(a), int(y), q0, 5.0e8, 5.0e8 * actual_q))
    pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "q_base", "amount_exposed", "death_amount"],
        orient="row",
    ).write_csv(exp)

    result = runner.invoke(app, ["experience", "fit", "-e", str(exp), "--basis", "amount"])
    assert result.exit_code == 0, result.output
    assert "amount" in result.output


def test_fit_table_attach_path_builds_q_base(tmp_path: Path) -> None:
    """A CSV lacking ``q_base`` attaches the static base from ``--table``."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp, with_q_base=False)
    data_dir = tmp_path / "data"
    _write_synthetic_cso_dir(data_dir)

    result = runner.invoke(
        app,
        [
            "experience",
            "fit",
            "-e",
            str(exp),
            "--table",
            "cso_2001",
            "--data-dir",
            str(data_dir / "mortality_tables"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "A/E" in result.output


def test_fit_error_bad_basis(tmp_path: Path) -> None:
    """An unknown ``--basis`` is rejected, exit 1."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp)
    result = runner.invoke(app, ["experience", "fit", "-e", str(exp), "--basis", "bogus"])
    assert result.exit_code == 1
    assert "basis" in result.output.lower()


def test_fit_error_missing_experience_file(tmp_path: Path) -> None:
    """A missing experience file is a clear error, exit 1."""
    result = runner.invoke(app, ["experience", "fit", "-e", str(tmp_path / "nope.csv")])
    assert result.exit_code == 1
    assert "not found" in result.output


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #


def test_error_no_qbase_no_table(tmp_path: Path) -> None:
    """No ``q_base`` column and no ``--table`` is a clear error, exit 1."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp, with_q_base=False)
    result = runner.invoke(app, ["experience", "improvement", "-e", str(exp)])
    assert result.exit_code == 1
    assert "q_base" in result.output


def test_error_project_without_bayesian(tmp_path: Path) -> None:
    """``--project-horizon`` requires ``--bayesian``, exit 1."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp)
    result = runner.invoke(
        app, ["experience", "improvement", "-e", str(exp), "--project-horizon", "5"]
    )
    assert result.exit_code == 1
    assert "project-horizon requires --bayesian" in result.output


def test_error_bad_basis(tmp_path: Path) -> None:
    """An unknown ``--basis`` is rejected, exit 1."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp)
    result = runner.invoke(app, ["experience", "improvement", "-e", str(exp), "--basis", "bogus"])
    assert result.exit_code == 1
    assert "basis" in result.output.lower()


def test_error_missing_experience_file(tmp_path: Path) -> None:
    """A missing experience file is a clear error, exit 1."""
    result = runner.invoke(app, ["experience", "improvement", "-e", str(tmp_path / "nope.csv")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_error_unknown_table(tmp_path: Path) -> None:
    """An unknown ``--table`` source is rejected, exit 1."""
    exp = tmp_path / "exp.csv"
    _write_experience_csv(exp, with_q_base=False)
    result = runner.invoke(
        app, ["experience", "improvement", "-e", str(exp), "--table", "not_a_table"]
    )
    assert result.exit_code == 1
    assert "unknown mortality table" in result.output.lower()
