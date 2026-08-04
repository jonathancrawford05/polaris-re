"""
Tests for the real-data diligence harness (slice 1 of PLAN_experience_gam_realdata).

The harness itself never sees real data in CI — HMD needs an account, ILEC needs
SOA terms acceptance, and neither may be committed (Design Anchor 6). So every
test here builds a *synthetic* cache in the exact on-disk shape the runbook tells
a maintainer to create, with a **known injected improvement surface**, and checks
that the harness reports what was injected. That is the only way to prove the
harness is sound before it meets data nobody in CI can hold.

The tests that matter most are the ones that could embarrass the epic:

- an injected **slowdown** is reported as a slowdown, and an injected
  **acceleration** is reported as an acceleration. A harness that says "slowdown"
  either way would confirm PLAN §2's hypothesis by construction.
- the fitted MI is **invariant to the base-rate choice** — the claim that lets the
  harness use a data-derived offset instead of a table it cannot ship.
- the window contrast **telescopes** to the annual grid exactly, so the
  early/late bands are real delta-method intervals rather than rescaled per-year
  ones.
- A/E against SOA's published expected deaths is **flat when the improvement
  agrees** and **sloped when it does not**, in the right direction.

Deaths are set deterministically to their expected value, so the Poisson GLM
recovers the generating surface to near machine precision — closed-form
verification, no seeds, no wall clock (ADR-074).
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_diligence import (
    DEFAULT_REFERENCE_AGES,
    ILEC_GROUP_KEYS,
    RUNBOOK_PATH,
    attach_empirical_base,
    default_windows,
    render_markdown,
    resolve_hmd_paths,
    resolve_ilec_path,
    run_diligence,
)
from polaris_re.analytics.experience_gam import TensorMIModel
from polaris_re.core.exceptions import PolarisValidationError

# Deterministic deaths give a perfect GLM fit; statsmodels flags that as perfect
# separation. Expected here, and not a problem.
pytestmark = pytest.mark.filterwarnings(
    "ignore::statsmodels.tools.sm_exceptions.PerfectSeparationWarning"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "experience_diligence.py"


# --------------------------------------------------------------------------- #
# Synthetic HMD cache
# --------------------------------------------------------------------------- #

_HMD_AGES = tuple(range(40, 91))
_HMD_YEARS = tuple(range(1990, 2020))
_HMD_EXPOSURE = 2.0e6


def _q_base(age: int, sex: str) -> float:
    """A smooth, increasing base rate; females a little lower."""
    scale = 1.0 if sex == "Male" else 0.85
    return 0.0008 * float(np.exp(0.085 * (age - 40))) * scale


def _cumulative_factor(year: int, mi_of_year) -> float:
    """Π over 1990..year of (1 - MI(step))."""
    factor = 1.0
    for step in range(_HMD_YEARS[0] + 1, year + 1):
        factor *= 1.0 - mi_of_year(step)
    return factor


def _write_hmd_cache(root: Path, country: str, mi_of_year, *, subdir: str = "") -> Path:
    """Write Deaths_1x1/Exposures_1x1 with a known MI(step) into the cache layout."""
    directory = root / "hmd" / country
    if subdir:
        directory = directory / subdir
    directory.mkdir(parents=True, exist_ok=True)

    death_rows: list[str] = []
    exposure_rows: list[str] = []
    for year in _HMD_YEARS:
        factor = _cumulative_factor(year, mi_of_year)
        for age in _HMD_AGES:
            female = _HMD_EXPOSURE * _q_base(age, "Female") * factor
            male = _HMD_EXPOSURE * _q_base(age, "Male") * factor
            death_rows.append(
                f"  {year}      {age:>10}  {female:>18.6f} {male:>15.6f} {female + male:>15.6f}"
            )
            exposure_rows.append(
                f"  {year}      {age:>10}  {_HMD_EXPOSURE:>18.2f} {_HMD_EXPOSURE:>15.2f} "
                f"{2 * _HMD_EXPOSURE:>15.2f}"
            )

    header = "  Year          Age             Female            Male           Total"
    (directory / "Deaths_1x1.txt").write_text(
        f"{country}, Deaths (period 1x1)\tLast modified: 01 Jan 2024\n\n"
        + header
        + "\n"
        + "\n".join(death_rows)
        + "\n"
    )
    (directory / "Exposures_1x1.txt").write_text(
        f"{country}, Exposures (period 1x1)\tLast modified: 01 Jan 2024\n\n"
        + header
        + "\n"
        + "\n".join(exposure_rows)
        + "\n"
    )
    return directory


def _constant_mi(rate: float):
    def mi(_year: int) -> float:
        return rate

    return mi


def _slowing_mi(early: float, late: float, break_year: int = 2010):
    def mi(year: int) -> float:
        return early if year < break_year else late

    return mi


# --------------------------------------------------------------------------- #
# Synthetic ILEC cache (2012-19 header spelling, tab-delimited)
# --------------------------------------------------------------------------- #

_ILEC_AGES = tuple(range(45, 81))
_ILEC_YEARS = tuple(range(2012, 2020))
_ILEC_CLASSES = (("1", "2"), ("2", "2"), ("NA", "NA"), ("U", "U"))
_ILEC_EXPOSURE = 50_000.0


def _ilec_q(age: int, sex: str, smoker: str, uw_class: str) -> float:
    """Base rate before improvement — differentiated exactly as the factors are."""
    q = 0.0009 * float(np.exp(0.082 * (age - 45)))
    q *= 1.0 if sex == "Male" else 0.82
    q *= 1.6 if smoker == "Smoker" else 1.0
    q *= {"1": 0.85, "2": 1.15, "NA": 1.0, "U": 1.05}[uw_class]
    return q


def _write_ilec_cache(
    root: Path,
    *,
    actual_mi: float,
    soa_mi: float,
    soa_level: float = 1.05,
    filename: str = "ILEC_2012_19 - synthetic.txt",
) -> Path:
    """Write a tab-delimited ILEC extract with a known actual and a known SOA MI.

    ``soa_level`` scales SOA's expected deaths relative to the truth, so the A/E
    *level* is known; ``soa_mi`` is the improvement SOA baked into their
    with-improvement column, so the A/E *drift* is known too.
    """
    directory = root / "ilec"
    directory.mkdir(parents=True, exist_ok=True)

    rows: dict[str, list[object]] = {
        key: []
        for key in (
            "Observation_Year",
            "Attained_Age",
            "Issue_Age",
            "Duration",
            "Sex",
            "Smoker_Status",
            "Insurance_Plan",
            "Face_Amount_Band",
            "Preferred_Class",
            "Number_of_Pfd_Classes",
            "Policies_Exposed",
            "Death_Count",
            "Amount_Exposed",
            "Death_Claim_Amount",
            "ExpDth_VBT2015_Cnt",
            "ExpDth_VBT2015wMI_Cnt",
            "ExpDth_VBT2015_Amt",
            "ExpDth_VBT2015wMI_Amt",
        )
    }
    base_year = _ILEC_YEARS[0]
    for year in _ILEC_YEARS:
        t = year - base_year
        actual_factor = (1.0 - actual_mi) ** t
        soa_factor = (1.0 - soa_mi) ** t
        for age in _ILEC_AGES:
            for sex in ("Male", "Female"):
                for smoker in ("Nonsmoker", "Smoker"):
                    for uw_class, n_classes in _ILEC_CLASSES:
                        q = _ilec_q(age, sex, smoker, uw_class)
                        deaths = _ILEC_EXPOSURE * q * actual_factor
                        expected = _ILEC_EXPOSURE * q * soa_level
                        rows["Observation_Year"].append(year)
                        rows["Attained_Age"].append(age)
                        rows["Issue_Age"].append(age - 5)
                        rows["Duration"].append(6)
                        rows["Sex"].append(sex)
                        rows["Smoker_Status"].append(smoker)
                        rows["Insurance_Plan"].append("Term")
                        rows["Face_Amount_Band"].append("A")
                        rows["Preferred_Class"].append(uw_class)
                        rows["Number_of_Pfd_Classes"].append(n_classes)
                        rows["Policies_Exposed"].append(_ILEC_EXPOSURE)
                        rows["Death_Count"].append(deaths)
                        rows["Amount_Exposed"].append(_ILEC_EXPOSURE * 1.0e5)
                        rows["Death_Claim_Amount"].append(deaths * 1.0e5)
                        rows["ExpDth_VBT2015_Cnt"].append(expected)
                        rows["ExpDth_VBT2015wMI_Cnt"].append(expected * soa_factor)
                        rows["ExpDth_VBT2015_Amt"].append(expected * 1.0e5)
                        rows["ExpDth_VBT2015wMI_Amt"].append(expected * soa_factor * 1.0e5)

    path = directory / filename
    pl.DataFrame(rows).write_csv(path, separator="\t")
    return path


# --------------------------------------------------------------------------- #
# Cache discovery
# --------------------------------------------------------------------------- #


def test_resolve_hmd_paths_finds_the_fetch_layout(tmp_path: Path) -> None:
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    deaths, exposures = resolve_hmd_paths("USA", cache_dir=tmp_path)
    assert deaths.name == "Deaths_1x1.txt"
    assert exposures.parent == tmp_path / "hmd" / "USA"


def test_resolve_hmd_paths_finds_the_zip_bundle_stats_subdirectory(tmp_path: Path) -> None:
    """The manual 'Statistics' bundle extracts into STATS/ — a harness that only
    knew the fetch layout would report 'not found' while staring at the file."""
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01), subdir="STATS")
    deaths, exposures = resolve_hmd_paths("USA", cache_dir=tmp_path)
    assert deaths.parent.name == "STATS"
    assert exposures.parent.name == "STATS"


def test_resolve_hmd_missing_names_every_location_and_the_runbook(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError) as exc:
        resolve_hmd_paths("USA", cache_dir=tmp_path)
    message = str(exc.value)
    assert "Deaths_1x1.txt" in message
    assert "STATS" in message
    assert RUNBOOK_PATH in message
    assert "1x1" in message


def test_resolve_ilec_path_single_candidate(tmp_path: Path) -> None:
    path = _write_ilec_cache(tmp_path, actual_mi=0.01, soa_mi=0.01)
    assert resolve_ilec_path(cache_dir=tmp_path) == path


def test_resolve_ilec_missing_directory_points_at_the_runbook(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError) as exc:
        resolve_ilec_path(cache_dir=tmp_path)
    assert RUNBOOK_PATH in str(exc.value)
    assert "unzip -d" in str(exc.value)


def test_resolve_ilec_refuses_to_guess_between_candidates(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.01, soa_mi=0.01, filename="a.txt")
    (tmp_path / "ilec" / "b.txt").write_text("x")
    with pytest.raises(PolarisValidationError) as exc:
        resolve_ilec_path(cache_dir=tmp_path)
    assert "2 candidate files" in str(exc.value)


def test_resolve_ilec_explicit_filename_wins(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.01, soa_mi=0.01, filename="a.txt")
    (tmp_path / "ilec" / "b.txt").write_text("x")
    assert resolve_ilec_path(cache_dir=tmp_path, filename="b.txt").name == "b.txt"


def test_resolve_ilec_explicit_missing_filename_raises(tmp_path: Path) -> None:
    (tmp_path / "ilec").mkdir()
    with pytest.raises(PolarisValidationError, match="not found"):
        resolve_ilec_path(cache_dir=tmp_path, filename="nope.txt")


# --------------------------------------------------------------------------- #
# Empirical base rate
# --------------------------------------------------------------------------- #


def _simple_cells() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "attained_age": [50, 50, 51, 51],
            "calendar_year": [2015, 2016, 2015, 2016],
            "central_exposure": [1000.0, 1000.0, 2000.0, 2000.0],
            "death_count": [6.0, 4.0, 30.0, 10.0],
        }
    )


def test_empirical_base_is_the_pooled_crude_rate() -> None:
    """Closed form: q_base = Σ deaths / Σ exposure within the stratum."""
    base = attach_empirical_base(
        _simple_cells(), exposure_col="central_exposure", deaths_col="death_count"
    )
    by_age = base.cells.sort("attained_age", "calendar_year")
    np.testing.assert_allclose(
        by_age.filter(pl.col("attained_age") == 50)["q_base"].to_numpy(),
        np.full(2, 10.0 / 2000.0),
    )
    np.testing.assert_allclose(
        by_age.filter(pl.col("attained_age") == 51)["q_base"].to_numpy(),
        np.full(2, 40.0 / 4000.0),
    )
    assert base.n_strata == 2
    assert base.keys == ("attained_age",)


def test_empirical_base_is_constant_across_calendar_years() -> None:
    """Anchor 1: the offset must be static, so the calendar gradient is improvement
    rather than residual-vs-assumed improvement. Asserted behaviourally — the
    model's own static-base guard accepts it without the override."""
    base = attach_empirical_base(
        _simple_cells(), exposure_col="central_exposure", deaths_col="death_count"
    )
    TensorMIModel(base.cells, age_df=3, year_df=2)  # constructs => guard passed


def test_empirical_base_drops_zero_death_strata_and_reports_the_share() -> None:
    cells = pl.DataFrame(
        {
            "attained_age": [50, 50, 30, 30],
            "calendar_year": [2015, 2016, 2015, 2016],
            "central_exposure": [1000.0, 1000.0, 500.0, 500.0],
            "death_count": [6.0, 4.0, 0.0, 0.0],
        }
    )
    base = attach_empirical_base(cells, exposure_col="central_exposure", deaths_col="death_count")
    assert base.n_strata == 1
    assert base.n_strata_dropped == 1
    assert base.cells.height == 2
    assert base.dropped_exposure_share == pytest.approx(1000.0 / 3000.0)


def test_empirical_base_clips_a_crude_rate_above_one() -> None:
    cells = pl.DataFrame(
        {
            "attained_age": [110, 110],
            "calendar_year": [2015, 2016],
            "central_exposure": [10.0, 10.0],
            "death_count": [12.0, 11.0],
        }
    )
    base = attach_empirical_base(cells, exposure_col="central_exposure", deaths_col="death_count")
    assert base.n_clipped == 1
    assert base.cells["q_base"].max() == pytest.approx(1.0)


def test_empirical_base_requires_attained_age() -> None:
    with pytest.raises(PolarisValidationError, match="attained_age"):
        attach_empirical_base(
            pl.DataFrame({"central_exposure": [1.0], "death_count": [0.5]}),
            exposure_col="central_exposure",
            deaths_col="death_count",
        )


def test_empirical_base_all_zero_deaths_raises() -> None:
    cells = pl.DataFrame(
        {
            "attained_age": [50, 50],
            "calendar_year": [2015, 2016],
            "central_exposure": [1000.0, 1000.0],
            "death_count": [0.0, 0.0],
        }
    )
    with pytest.raises(PolarisValidationError, match="not estimable"):
        attach_empirical_base(cells, exposure_col="central_exposure", deaths_col="death_count")


def test_fitted_mi_is_invariant_to_the_base_choice() -> None:
    """The claim that lets the harness use a data-derived offset instead of a
    table it cannot ship: MI is a calendar contrast, so any *static* base cancels.

    Halving q_base changes ``overall_ae`` by a factor of two and leaves the
    improvement surface bit-for-bit alone.
    """
    ages = np.arange(45, 66)
    years = np.arange(2000, 2016)
    rows = []
    for age in ages:
        q = 0.001 * float(np.exp(0.08 * (age - 45)))
        for year in years:
            deaths = 1.0e6 * q * (1.0 - 0.015) ** (year - years[0])
            rows.append((int(age), int(year), 1.0e6, deaths))
    cells = pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "central_exposure", "death_count"],
        orient="row",
    )
    base = attach_empirical_base(cells, exposure_col="central_exposure", deaths_col="death_count")
    halved = base.cells.with_columns((pl.col("q_base") * 0.5).alias("q_base"))

    fit_a = TensorMIModel(base.cells, age_df=5, year_df=4).fit()
    fit_b = TensorMIModel(halved, age_df=5, year_df=4).fit()

    np.testing.assert_allclose(
        fit_a.improvement_surface().mi_grid,
        fit_b.improvement_surface().mi_grid,
        rtol=1e-10,
        atol=1e-12,
    )
    assert fit_b.overall_ae == pytest.approx(2.0 * fit_a.overall_ae)


# --------------------------------------------------------------------------- #
# Comparison windows
# --------------------------------------------------------------------------- #


def test_default_windows_long_range_uses_the_decade_ends() -> None:
    assert default_windows(1990, 2019) == ((1990, 1999), (2010, 2019))


def test_default_windows_short_range_splits_in_half() -> None:
    assert default_windows(2012, 2019) == ((2012, 2015), (2016, 2019))


def test_default_windows_too_short_returns_none() -> None:
    assert default_windows(2015, 2017) is None


def test_window_contrast_telescopes_to_the_annual_grid(tmp_path: Path) -> None:
    """The window band is exact, not a rescaled per-year one.

    Asking ``improvement_surface`` for the two-year grid ``[start, end]`` makes its
    single step the contrast ``η(end) - η(start)``. Because the per-year steps
    telescope, annualising that must equal the geometric mean of the annual grid's
    own steps — verified here to machine precision.
    """
    from polaris_re.analytics.experience_diligence import _window_mi

    ages = np.arange(50, 61)
    years = np.arange(2000, 2011)
    rows = []
    for age in ages:
        q = 0.001 * float(np.exp(0.08 * (age - 50)))
        for year in years:
            rows.append((int(age), int(year), 1.0e6, 1.0e6 * q * 0.985 ** (year - years[0])))
    cells = pl.DataFrame(
        rows,
        schema=["attained_age", "calendar_year", "central_exposure", "death_count"],
        orient="row",
    )
    base = attach_empirical_base(cells, exposure_col="central_exposure", deaths_col="death_count")
    result = TensorMIModel(base.cells, age_df=4, year_df=4).fit()

    ref = np.array([52, 56, 59], dtype=np.int64)
    window = _window_mi(result, ref, 2002, 2008, 0.95)

    annual = result.improvement_surface(ages=ref, years=np.arange(2002, 2009, dtype=np.int64))
    # Geometric mean of the annual (1 - MI) steps == the annualised window value.
    geometric = 1.0 - np.exp(np.mean(np.log1p(-annual.mi_grid), axis=1))
    np.testing.assert_allclose(np.array(window.annualised_mi), geometric, rtol=1e-12, atol=1e-14)


# --------------------------------------------------------------------------- #
# End to end — HMD
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def hmd_slowdown_report(tmp_path_factory: pytest.TempPathFactory):
    """One fit of an injected 2.0%/yr -> 0.5%/yr slowdown, shared by several tests."""
    root = tmp_path_factory.mktemp("hmd_slowdown")
    _write_hmd_cache(root, "USA", _slowing_mi(0.020, 0.005))
    return run_diligence(
        source="hmd",
        cache_dir=root,
        country="USA",
        min_year=1990,
        max_year=2019,
        min_age=45,
        max_age=85,
    )


def test_hmd_run_detects_an_injected_slowdown(hmd_slowdown_report) -> None:
    comparison = hmd_slowdown_report.window_comparison
    assert comparison is not None
    assert comparison.verdict == "slowdown"
    assert comparison.n_ages_slower == comparison.n_ages
    # The injected step is 1.5 points; the fitted windows must see most of it.
    assert all(delta < -0.005 for delta in comparison.delta)
    assert (comparison.early.start_year, comparison.early.end_year) == (1990, 1999)
    assert (comparison.late.start_year, comparison.late.end_year) == (2010, 2019)


def test_hmd_run_reports_the_stated_aggregation_and_fit(hmd_slowdown_report) -> None:
    assert hmd_slowdown_report.aggregation["group_keys"] == [
        "attained_age",
        "calendar_year",
        "sex",
    ]
    assert hmd_slowdown_report.fit["factors"] == ["sex"]
    assert hmd_slowdown_report.fit["observed_years"] == [1990, 2019]
    assert hmd_slowdown_report.fit["observed_ages"] == [45, 85]
    # The base is fitted to the same cells, so A/E is ~1 by construction — which
    # the report says out loud rather than presenting as a validation.
    assert hmd_slowdown_report.fit["overall_ae"] == pytest.approx(1.0, abs=1e-6)


def test_hmd_run_detects_an_injected_acceleration(tmp_path: Path) -> None:
    """The two-sided check: the harness must not report 'slowdown' regardless."""
    _write_hmd_cache(tmp_path, "USA", _slowing_mi(0.005, 0.020))
    report = run_diligence(
        source="hmd",
        cache_dir=tmp_path,
        country="USA",
        min_year=1990,
        max_year=2019,
        min_age=50,
        max_age=80,
        reference_ages=(55, 65, 75),
    )
    assert report.window_comparison is not None
    assert report.window_comparison.verdict == "acceleration"
    assert all(delta > 0.005 for delta in report.window_comparison.delta)


def test_hmd_constant_improvement_shows_no_material_change(tmp_path: Path) -> None:
    """No injected structure => no reported structure, to within a rounding error."""
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.012))
    report = run_diligence(
        source="hmd",
        cache_dir=tmp_path,
        country="USA",
        min_year=1990,
        max_year=2019,
        min_age=50,
        max_age=80,
        reference_ages=(55, 65, 75),
    )
    assert report.window_comparison is not None
    assert all(abs(delta) < 5e-4 for delta in report.window_comparison.delta)
    # And the level itself is the injected 1.2%.
    for value in report.window_comparison.early.annualised_mi:
        assert value == pytest.approx(0.012, abs=5e-4)


def test_hmd_report_json_is_deterministic_and_path_free(hmd_slowdown_report) -> None:
    """Two renderings agree byte for byte (no timestamp), and nothing carries an
    absolute path — a committed finding must not leak a home directory."""
    first = hmd_slowdown_report.to_json()
    assert first == hmd_slowdown_report.to_json()
    payload = json.loads(first)
    assert payload["schema_version"] == 1
    assert payload["inputs"]["deaths_file"] == "Deaths_1x1.txt"
    assert "/" not in json.dumps(payload["inputs"])


def test_hmd_report_markdown_leads_with_the_verdict(hmd_slowdown_report) -> None:
    text = render_markdown(hmd_slowdown_report)
    assert "## Improvement slowdown test" in text
    assert "**Verdict: `slowdown`**" in text
    assert "not a significance test" in text
    assert "## Caveats" in text
    # No plots — nothing here emits or references an image.
    assert ".png" not in text and ".svg" not in text


def test_hmd_amount_basis_is_rejected(tmp_path: Path) -> None:
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    with pytest.raises(PolarisValidationError, match="no face amounts"):
        run_diligence(source="hmd", cache_dir=tmp_path, country="USA", basis="amount")


def test_window_outside_the_observed_range_is_refused(tmp_path: Path) -> None:
    """The surface is not extrapolated past the data, quietly or otherwise."""
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    with pytest.raises(PolarisValidationError, match="outside the observed calendar range"):
        run_diligence(
            source="hmd",
            cache_dir=tmp_path,
            country="USA",
            min_year=2000,
            max_year=2019,
            min_age=50,
            max_age=70,
            early_window=(1980, 1989),
            late_window=(2010, 2019),
        )


def test_reversed_window_is_refused(tmp_path: Path) -> None:
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    with pytest.raises(PolarisValidationError, match="at least one annual step"):
        run_diligence(
            source="hmd",
            cache_dir=tmp_path,
            country="USA",
            min_year=2000,
            max_year=2019,
            min_age=50,
            max_age=70,
            early_window=(2005, 2005),
            late_window=(2010, 2019),
        )


def test_reference_ages_outside_the_data_are_refused(tmp_path: Path) -> None:
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    with pytest.raises(PolarisValidationError, match="No reference age"):
        run_diligence(
            source="hmd",
            cache_dir=tmp_path,
            country="USA",
            min_age=50,
            max_age=60,
            max_year=2019,
            reference_ages=(95,),
        )


def test_reference_ages_outside_the_data_are_reported_as_dropped(tmp_path: Path) -> None:
    """Quietly reporting on fewer ages than asked for would read as a thin finding
    rather than a narrow age window."""
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    report = run_diligence(
        source="hmd",
        cache_dir=tmp_path,
        country="USA",
        min_year=1990,
        max_year=2019,
        min_age=50,
        max_age=70,
    )
    assert report.fit["reference_ages"] == [55, 65]
    assert any("[45, 75, 85]" in caveat for caveat in report.caveats)


def test_covid_window_is_flagged_as_a_caveat(tmp_path: Path) -> None:
    """Leaving the window open past 2019 attributes a shock to smooth improvement.
    The harness still runs — it says so instead of refusing."""
    _write_hmd_cache(tmp_path, "USA", _constant_mi(0.01))
    report = run_diligence(
        source="hmd",
        cache_dir=tmp_path,
        country="USA",
        min_age=50,
        max_age=70,
        reference_ages=(55, 65),
    )
    assert any("COVID" in caveat for caveat in report.caveats)


def test_missing_hmd_cache_raises_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError) as exc:
        run_diligence(source="hmd", cache_dir=tmp_path, country="USA")
    assert RUNBOOK_PATH in str(exc.value)


def test_unknown_source_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError, match="Unknown source"):
        run_diligence(source="sql", cache_dir=tmp_path)


# --------------------------------------------------------------------------- #
# End to end — ILEC, and SOA's published expected deaths
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def ilec_agreeing_report(tmp_path_factory: pytest.TempPathFactory):
    """Our experience improves at exactly the rate SOA assumed: A/E must be flat."""
    root = tmp_path_factory.mktemp("ilec_agree")
    _write_ilec_cache(root, actual_mi=0.010, soa_mi=0.010)
    return run_diligence(
        source="ilec",
        cache_dir=root,
        min_age=50,
        max_age=75,
        reference_ages=(55, 65, 75),
    )


def test_ilec_run_carries_soas_expected_deaths(ilec_agreeing_report) -> None:
    ae = ilec_agreeing_report.ae_by_year
    assert ae is not None
    assert ae.frame["calendar_year"].to_list() == list(_ILEC_YEARS)
    # SOA's expected is 1.05x the truth *before* improvement, so the no-MI A/E is
    # additionally depressed by the cumulative 1%/yr the experience actually ran:
    # A/E = Σ_t (1-mi)^t / (n * 1.05). That gap between the two denominators is
    # exactly what the with-MI column exists to remove.
    steps = np.arange(len(_ILEC_YEARS), dtype=np.float64)
    expected_level = float(np.mean(0.99**steps)) / 1.05
    assert ae.overall_ae == pytest.approx(expected_level, rel=1e-9)
    assert ae.overall_ae < ae.overall_ae_mi


def test_ilec_ae_is_flat_when_the_improvement_agrees(ilec_agreeing_report) -> None:
    """Flat A/E-with-MI is agreement — the finding the epic is actually after."""
    ae = ilec_agreeing_report.ae_by_year
    assert ae is not None
    assert abs(ae.ae_mi_slope_per_year) < 1e-9
    assert ae.overall_ae_mi == pytest.approx(1.0 / 1.05, rel=1e-6)


def test_ilec_ae_drifts_when_the_improvement_disagrees(tmp_path: Path) -> None:
    """Our 2%/yr against SOA's 0.5%/yr: A/E-with-MI must fall, measurably."""
    _write_ilec_cache(tmp_path, actual_mi=0.020, soa_mi=0.005)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=75,
        reference_ages=(55, 65, 75),
    )
    ae = report.ae_by_year
    assert ae is not None
    assert ae.ae_mi_slope_per_year < -0.001
    # Closed form: A/E(y) = (1/1.05) * ((1-0.020)/(1-0.005))^t.
    ratio = (1.0 - 0.020) / (1.0 - 0.005)
    expected = [(1.0 / 1.05) * ratio ** (y - _ILEC_YEARS[0]) for y in _ILEC_YEARS]
    np.testing.assert_allclose(ae.frame["ae_mi"].to_numpy(), expected, rtol=1e-9)


def test_ilec_surface_comparison_recovers_soas_own_improvement(tmp_path: Path) -> None:
    """SOA's expected-with-MI over expected-without IS their MI assumption. Ours
    is fitted independently; on identical cells the two must agree."""
    _write_ilec_cache(tmp_path, actual_mi=0.013, soa_mi=0.013)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=75,
        reference_ages=(55, 65, 75),
        year_df=3,
    )
    soa = report.soa_comparison
    assert soa is not None
    np.testing.assert_allclose(soa.frame["soa_mi"].to_numpy(), 0.013, rtol=1e-9)
    assert abs(soa.mean_difference) < 5e-4
    assert soa.mean_absolute_difference < 5e-4


def test_ilec_surface_comparison_shows_a_disagreement(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.020, soa_mi=0.005)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=75,
        reference_ages=(55, 65, 75),
        year_df=3,
    )
    soa = report.soa_comparison
    assert soa is not None
    # We fit MORE improvement than SOA assumed, by about the injected 1.5 points.
    assert soa.mean_difference == pytest.approx(0.015, abs=1e-3)


def test_ilec_holds_the_unknown_uw_class_out_by_default(ilec_agreeing_report) -> None:
    """'U' is missing data, not a stratum. 'NA' — no preferred structure — is."""
    assert ilec_agreeing_report.aggregation["n_cells_unknown_uw_class_excluded"] > 0
    assert any("uw_class == 'U'" in caveat for caveat in ilec_agreeing_report.caveats)


def test_ilec_keeps_na_as_its_own_stratum(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
    )
    assert "uw_class" in report.aggregation["group_keys"]
    # 1of2 / 2of2 / NA survive; U does not.
    assert report.aggregation["n_cells_unknown_uw_class_excluded"] > 0
    assert report.fit["n_cells"] == report.aggregation["n_cells_fitted"]


def test_ilec_keep_unknown_uw_class_includes_it(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    kept = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
        keep_unknown_uw_class=True,
    )
    dropped = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
    )
    assert kept.aggregation["n_cells_unknown_uw_class_excluded"] == 0
    assert kept.aggregation["n_cells_fitted"] > dropped.aggregation["n_cells_fitted"]


def test_ilec_group_keys_override_changes_the_level_and_says_so(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    coarse = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
        group_keys=("attained_age", "calendar_year", "sex"),
    )
    default = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
    )
    assert coarse.aggregation["group_keys"] == ["attained_age", "calendar_year", "sex"]
    assert default.aggregation["group_keys"] == list(ILEC_GROUP_KEYS)
    assert coarse.aggregation["n_cells_fitted"] < default.aggregation["n_cells_fitted"]
    assert "smoker" in coarse.aggregation["dropped_keys"]


def test_unknown_group_key_coarsens_loudly(tmp_path: Path) -> None:
    """A typo in --group-by would otherwise coarsen the fit silently — the one
    direction PLAN §4 calls hazardous."""
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
        group_keys=("attained_age", "calendar_year", "sex", "smoker_status"),
    )
    assert report.aggregation["group_keys"] == [
        "attained_age",
        "calendar_year",
        "sex",
    ]
    assert any("COARSER than asked for" in caveat for caveat in report.caveats)


def test_ilec_duration_pooling_is_stated_as_a_caveat(ilec_agreeing_report) -> None:
    assert any("pooled across duration" in caveat for caveat in ilec_agreeing_report.caveats)


def test_ilec_no_expected_skips_the_soa_sections(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=60,
        reference_ages=(55,),
        include_expected=False,
    )
    assert report.ae_by_year is None
    assert report.soa_comparison is None
    assert "ae_by_year" not in report.to_dict()


def test_ilec_null_expected_deaths_are_reported_not_absorbed(tmp_path: Path) -> None:
    """The loader's group-and-sum turns a null expected-death value into a zero, so
    a partially-populated vintage looks like a cell that simply expects no deaths —
    it deflates the denominator and inflates every A/E. It must show up as a
    caveat, not as a flattering ratio."""
    path = _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    frame = pl.read_csv(path, separator="\t")
    holed = frame.with_columns(
        pl.when(pl.col("Attained_Age") == 60)
        .then(None)
        .otherwise(pl.col("ExpDth_VBT2015wMI_Cnt"))
        .alias("ExpDth_VBT2015wMI_Cnt")
    )
    holed.write_csv(path, separator="\t")

    report = run_diligence(
        source="ilec",
        cache_dir=tmp_path,
        min_age=50,
        max_age=70,
        reference_ages=(55, 65),
    )
    assert any("null or zero SOA expected deaths" in c for c in report.caveats)
    # And the hole does not become a 100%-improvement cell in the surface
    # comparison: age 60 is dropped from it rather than ratioed against zero.
    assert report.soa_comparison is not None
    assert 60 not in report.soa_comparison.frame["attained_age"].to_list()


def test_ilec_empty_after_filters_raises(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    with pytest.raises(PolarisValidationError, match="No cells survived"):
        run_diligence(source="ilec", cache_dir=tmp_path, min_year=2050, max_year=2060)


def test_ilec_unknown_vintage_is_refused(tmp_path: Path) -> None:
    _write_ilec_cache(tmp_path, actual_mi=0.010, soa_mi=0.010)
    with pytest.raises(PolarisValidationError, match="Unknown ILEC vintage"):
        run_diligence(source="ilec", cache_dir=tmp_path, ilec_vintage="1999")


def test_ilec_markdown_carries_the_ae_table(ilec_agreeing_report) -> None:
    text = render_markdown(ilec_agreeing_report)
    assert "## A/E against SOA's published expected deaths" in text
    assert "## Fitted MI vs SOA's own MI" in text
    assert "Expected (w/ MI)" in text


# --------------------------------------------------------------------------- #
# The command-line wrapper
# --------------------------------------------------------------------------- #


def _load_script():
    spec = importlib.util.spec_from_file_location("experience_diligence_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_script_writes_json_and_markdown(tmp_path: Path) -> None:
    script = _load_script()
    _write_hmd_cache(tmp_path, "USA", _slowing_mi(0.020, 0.005))
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"
    status = script.main(
        [
            "--source",
            "hmd",
            "--cache-dir",
            str(tmp_path),
            "--country",
            "USA",
            "--min-year",
            "1990",
            "--max-year",
            "2019",
            "--min-age",
            "50",
            "--max-age",
            "80",
            "--reference-ages",
            "55",
            "65",
            "75",
            "-o",
            str(out_json),
            "--markdown",
            str(out_md),
        ]
    )
    assert status == 0
    payload = json.loads(out_json.read_text())
    assert payload["window_comparison"]["verdict"] == "slowdown"
    assert "**Verdict: `slowdown`**" in out_md.read_text()


def test_script_exits_2_on_a_missing_cache(tmp_path: Path) -> None:
    """A first run against an empty cache should hit a sentence, not a traceback."""
    script = _load_script()
    assert script.main(["--source", "hmd", "--cache-dir", str(tmp_path)]) == 2


def test_script_window_argument_parses_both_separators() -> None:
    script = _load_script()
    args = script.build_parser().parse_args(
        ["--source", "hmd", "--early-window", "1990:1999", "--late-window", "2010-2019"]
    )
    assert args.early_window == (1990, 1999)
    assert args.late_window == (2010, 2019)


def test_script_help_names_the_defaults_and_the_runbook() -> None:
    script = _load_script()
    help_text = script.build_parser().format_help()
    assert RUNBOOK_PATH in help_text
    assert "uw_class" in help_text
    assert "COVID" in help_text


def test_reference_ages_default_is_interior_to_a_typical_fit() -> None:
    """A boundary reference age would report B-spline wiggle as improvement."""
    assert min(DEFAULT_REFERENCE_AGES) > 25
    assert max(DEFAULT_REFERENCE_AGES) < 95
