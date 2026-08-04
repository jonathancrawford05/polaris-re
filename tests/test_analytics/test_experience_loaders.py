"""
Tests for the Slice-4c-1 experience data loaders (HMD + SOA ILEC).

Covers the loaders-not-data contract from docs/PLAN_experience_gam.md
"Data Sources & Strategy":
- HMD 1x1 parsing (Deaths/Exposures matrices → long format): missing "." markers
  dropped, ``Total`` column excluded, open ``110+`` age handled, sex codes
  canonicalised to Polaris ``Sex`` values.
- ``load_hmd`` join → canonical grouped cells; year/age/sex filters; determinism.
- ``load_ilec`` source→canonical mapping, gender/smoker canonicalisation,
  1-based Duration → ``duration_months``, per-basis measure selection, and
  group-and-sum aggregation over the canonical keys (Anchor 7).
- ``fetch_hmd`` network layer via an injected (non-network) downloader: cache
  paths, skip-existing / overwrite, and failure surfacing.
- The loaded cells feed the existing tensor MI surface end-to-end.

All fixtures are synthetic and written to ``tmp_path``; no large/licensed file is
used, and no test touches the network or the wall clock (ADR-074 guard).
"""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    AMOUNT_MEASURES,
    COUNT_MEASURES,
    TensorMIModel,
    attach_base_rate,
)
from polaris_re.analytics.experience_loaders import (
    HMD_BASE_URL,
    ILEC_2012_19_COLUMN_MAP,
    ILEC_COLUMN_MAP,
    ILEC_EXPECTED_AMOUNT_MEASURES,
    ILEC_EXPECTED_COUNT_MEASURES,
    default_experience_cache_dir,
    fetch_hmd,
    hmd_1x1_url,
    load_hmd,
    load_ilec,
    parse_hmd_1x1,
)
from polaris_re.assumptions.mortality import MortalityTable, MortalityTableSource
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError

SEED = 20260723


# --------------------------------------------------------------------------- #
# HMD fixtures
# --------------------------------------------------------------------------- #

_HMD_DEATHS = """USA, Deaths (period 1x1)\tLast modified: 01 Jan 2024

  Year          Age             Female            Male           Total
  2015           0              100.00           110.00          210.00
  2015           1               10.00            12.00           22.00
  2015         110+               1.00             0.50            1.50
  2016           0              105.00           115.00          220.00
  2016           1                .                12.50           12.50
"""

_HMD_EXPOSURES = """USA, Exposures (period 1x1)\tLast modified: 01 Jan 2024

  Year          Age             Female            Male           Total
  2015           0            50000.00         51000.00       101000.00
  2015           1            48000.00         49000.00        97000.00
  2015         110+               5.00             2.00            7.00
  2016           0            50500.00         51500.00       102000.00
  2016           1            48500.00         49500.00        98000.00
"""


def _write_hmd(tmp_path: Path) -> tuple[Path, Path]:
    deaths = tmp_path / "Deaths_1x1.txt"
    exposures = tmp_path / "Exposures_1x1.txt"
    deaths.write_text(_HMD_DEATHS)
    exposures.write_text(_HMD_EXPOSURES)
    return deaths, exposures


# --------------------------------------------------------------------------- #
# parse_hmd_1x1
# --------------------------------------------------------------------------- #


def test_parse_hmd_deaths_long_format(tmp_path: Path) -> None:
    deaths, _ = _write_hmd(tmp_path)
    df = parse_hmd_1x1(deaths, value_name="death_count")
    assert df.columns == ["calendar_year", "attained_age", "sex", "death_count"]
    # Total column excluded; sex codes canonical.
    assert set(df["sex"].unique().to_list()) == {"M", "F"}
    # A specific cell round-trips.
    male_2015_age0 = df.filter(
        (pl.col("calendar_year") == 2015) & (pl.col("attained_age") == 0) & (pl.col("sex") == "M")
    )
    assert male_2015_age0["death_count"][0] == pytest.approx(110.0)


def test_parse_hmd_drops_missing_marker(tmp_path: Path) -> None:
    deaths, _ = _write_hmd(tmp_path)
    df = parse_hmd_1x1(deaths, value_name="death_count")
    # The 2016 age-1 Female cell is "." → dropped; its Male sibling survives.
    fem_2016_age1 = df.filter(
        (pl.col("calendar_year") == 2016) & (pl.col("attained_age") == 1) & (pl.col("sex") == "F")
    )
    assert fem_2016_age1.height == 0
    male_2016_age1 = df.filter(
        (pl.col("calendar_year") == 2016) & (pl.col("attained_age") == 1) & (pl.col("sex") == "M")
    )
    assert male_2016_age1["death_count"][0] == pytest.approx(12.5)


def test_parse_hmd_open_age_parsed_as_integer(tmp_path: Path) -> None:
    deaths, _ = _write_hmd(tmp_path)
    df = parse_hmd_1x1(deaths, value_name="death_count")
    # parse keeps 110+ as age 110 (load_hmd drops it by default; parse does not).
    assert 110 in df["attained_age"].to_list()


def test_parse_hmd_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError, match="not found"):
        parse_hmd_1x1(tmp_path / "nope.txt", value_name="death_count")


def test_parse_hmd_no_header_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_text("not an HMD file\njust some text\n")
    with pytest.raises(PolarisValidationError, match="header"):
        parse_hmd_1x1(bad, value_name="death_count")


# --------------------------------------------------------------------------- #
# load_hmd
# --------------------------------------------------------------------------- #


def test_load_hmd_canonical_cells(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    cells = load_hmd(deaths, exposures)
    assert cells.columns == [
        "attained_age",
        "calendar_year",
        "sex",
        COUNT_MEASURES[0],
        COUNT_MEASURES[1],
    ]
    # Open age dropped by default.
    assert 110 not in cells["attained_age"].to_list()
    # The 2016 F age-1 death cell was missing → no exposure/death row survives.
    fem_2016_age1 = cells.filter(
        (pl.col("calendar_year") == 2016) & (pl.col("attained_age") == 1) & (pl.col("sex") == "F")
    )
    assert fem_2016_age1.height == 0
    # A joined cell carries both measures.
    m0 = cells.filter(
        (pl.col("calendar_year") == 2015) & (pl.col("attained_age") == 0) & (pl.col("sex") == "M")
    )
    assert m0["central_exposure"][0] == pytest.approx(51000.0)
    assert m0["death_count"][0] == pytest.approx(110.0)


def test_load_hmd_keep_open_age(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    cells = load_hmd(deaths, exposures, drop_open_age=False)
    assert 110 in cells["attained_age"].to_list()


def test_load_hmd_filters(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    cells = load_hmd(deaths, exposures, min_year=2016, max_age=0, sexes=("M",))
    assert cells["calendar_year"].unique().to_list() == [2016]
    assert cells["attained_age"].max() == 0
    assert cells["sex"].unique().to_list() == ["M"]


def test_load_hmd_deterministic_sort(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    a = load_hmd(deaths, exposures)
    b = load_hmd(deaths, exposures)
    assert a.equals(b)
    # Sorted by (calendar_year, attained_age, sex).
    keys = a.select("calendar_year", "attained_age", "sex")
    assert keys.equals(keys.sort(["calendar_year", "attained_age", "sex"]))


def test_load_hmd_bad_sex_code_raises(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    with pytest.raises(PolarisValidationError, match="sex code"):
        load_hmd(deaths, exposures, sexes=("X",))


def test_load_hmd_no_overlap_raises(tmp_path: Path) -> None:
    deaths, exposures = _write_hmd(tmp_path)
    # A year window that matches no cells → empty after filter.
    with pytest.raises(PolarisValidationError, match="no cells"):
        load_hmd(deaths, exposures, min_year=2099)


# --------------------------------------------------------------------------- #
# hmd_1x1_url
# --------------------------------------------------------------------------- #


def test_hmd_1x1_url() -> None:
    url = hmd_1x1_url("USA", "deaths")
    assert url == f"{HMD_BASE_URL}/USA/STATS/Deaths_1x1.txt"
    assert hmd_1x1_url("CAN", "exposures").endswith("/CAN/STATS/Exposures_1x1.txt")


def test_hmd_1x1_url_bad_kind_raises() -> None:
    with pytest.raises(PolarisValidationError, match="Unknown HMD 1x1 kind"):
        hmd_1x1_url("USA", "population")


# --------------------------------------------------------------------------- #
# ILEC fixtures + load_ilec
# --------------------------------------------------------------------------- #


def _write_ilec(tmp_path: Path) -> Path:
    df = pl.DataFrame(
        {
            "Observation Year": [2015, 2015, 2015, 2016],
            "Attained Age": [45, 45, 46, 45],
            "Issue Age": [40, 40, 41, 40],
            "Duration": [6, 6, 6, 7],
            "Gender": ["Male", "Male", "Female", "Male"],
            "Smoker Status": ["Nonsmoker", "Nonsmoker", "Smoker", "Nonsmoker"],
            "Insurance Plan": ["Term", "Term", "Term", "Term"],
            "Policies Exposed": [1000.0, 500.0, 800.0, 900.0],
            "Death Count": [2.0, 1.0, 3.0, 2.0],
            "Amount Exposed": [1e8, 5e7, 8e7, 9e7],
            "Death Claim Amount": [2e5, 1e5, 3e5, 2e5],
        }
    )
    path = tmp_path / "ilec.csv"
    df.write_csv(path)
    return path


def test_load_ilec_count_basis_aggregates(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="count")
    # Two Male/NS/2015/age45 rows collapse to one; measures summed.
    m45_2015 = cells.filter(
        (pl.col("attained_age") == 45) & (pl.col("calendar_year") == 2015) & (pl.col("sex") == "M")
    )
    assert m45_2015.height == 1
    assert m45_2015["central_exposure"][0] == pytest.approx(1500.0)
    assert m45_2015["death_count"][0] == pytest.approx(3.0)
    # Only the count measure pair is carried on a count basis.
    assert AMOUNT_MEASURES[0] not in cells.columns


def test_load_ilec_duration_to_months(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="count")
    assert "duration_months" in cells.columns
    assert "duration" not in cells.columns
    # Duration 6 (1-based policy year) → (6-1)*12 = 60 months.
    dur = cells.filter(
        (pl.col("attained_age") == 45) & (pl.col("calendar_year") == 2015) & (pl.col("sex") == "M")
    )["duration_months"][0]
    assert dur == 60


def test_load_ilec_canonicalises_gender_smoker(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="count")
    assert set(cells["sex"].unique().to_list()) <= {"M", "F"}
    assert set(cells["smoker"].unique().to_list()) <= {"S", "NS", "U"}
    female = cells.filter(pl.col("sex") == "F")
    assert female["smoker"].unique().to_list() == ["S"]


def test_load_ilec_amount_basis(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="amount")
    assert AMOUNT_MEASURES[0] in cells.columns
    assert COUNT_MEASURES[0] not in cells.columns
    m45_2015 = cells.filter(
        (pl.col("attained_age") == 45) & (pl.col("calendar_year") == 2015) & (pl.col("sex") == "M")
    )
    assert m45_2015["amount_exposed"][0] == pytest.approx(1.5e8)


def test_load_ilec_both_basis(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="both")
    for m in (*COUNT_MEASURES, *AMOUNT_MEASURES):
        assert m in cells.columns


def test_load_ilec_no_aggregate_keeps_grain(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    cells = load_ilec(path, basis="count", aggregate=False)
    # Native grain: 4 rows in, 4 rows out (no collapse).
    assert cells.height == 4


def test_load_ilec_custom_column_map(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "obs_yr": [2015, 2016],
            "att_age": [50, 51],
            "expo": [1000.0, 1100.0],
            "deaths": [3.0, 4.0],
        }
    )
    path = tmp_path / "custom.csv"
    df.write_csv(path)
    cmap = {
        "obs_yr": "calendar_year",
        "att_age": "attained_age",
        "expo": "central_exposure",
        "deaths": "death_count",
    }
    cells = load_ilec(path, basis="count", column_map=cmap)
    assert cells.height == 2
    assert cells["central_exposure"].sum() == pytest.approx(2100.0)


def test_load_ilec_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PolarisValidationError, match="not found"):
        load_ilec(tmp_path / "nope.csv")


def test_load_ilec_bad_basis_raises(tmp_path: Path) -> None:
    path = _write_ilec(tmp_path)
    with pytest.raises(PolarisValidationError, match="Unknown ILEC basis"):
        load_ilec(path, basis="premium")


def test_load_ilec_missing_measure_raises(tmp_path: Path) -> None:
    df = pl.DataFrame({"Attained Age": [45], "Observation Year": [2015]})
    path = tmp_path / "nomeasure.csv"
    df.write_csv(path)
    with pytest.raises(PolarisValidationError, match="missing measure"):
        load_ilec(path, basis="count")


def test_load_ilec_missing_attained_age_raises(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {"Observation Year": [2015], "Policies Exposed": [1000.0], "Death Count": [2.0]}
    )
    path = tmp_path / "noage.csv"
    df.write_csv(path)
    with pytest.raises(PolarisValidationError, match="attained_age"):
        load_ilec(path, basis="count")


def test_load_ilec_unmapped_gender_raises(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "Attained Age": [45],
            "Observation Year": [2015],
            "Gender": ["Nonbinary"],
            "Policies Exposed": [1000.0],
            "Death Count": [2.0],
        }
    )
    path = tmp_path / "badgender.csv"
    df.write_csv(path)
    with pytest.raises(PolarisValidationError, match="unmapped label"):
        load_ilec(path, basis="count")


def test_load_ilec_unmapped_smoker_raises(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "Attained Age": [45],
            "Observation Year": [2015],
            "Smoker Status": ["Vaper"],
            "Policies Exposed": [1000.0],
            "Death Count": [2.0],
        }
    )
    path = tmp_path / "badsmoker.csv"
    df.write_csv(path)
    with pytest.raises(PolarisValidationError, match="unmapped label"):
        load_ilec(path, basis="count")


# --------------------------------------------------------------------------- #
# default_experience_cache_dir (env-var precedence)
# --------------------------------------------------------------------------- #


def test_cache_dir_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLARIS_EXPERIENCE_CACHE_DIR", "/x/cache")
    monkeypatch.setenv("POLARIS_DATA_DIR", "/y/data")
    assert default_experience_cache_dir() == Path("/x/cache")


def test_cache_dir_falls_back_to_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLARIS_EXPERIENCE_CACHE_DIR", raising=False)
    monkeypatch.setenv("POLARIS_DATA_DIR", "/y/data")
    assert default_experience_cache_dir() == Path("/y/data/experience_cache")


def test_cache_dir_final_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLARIS_EXPERIENCE_CACHE_DIR", raising=False)
    monkeypatch.delenv("POLARIS_DATA_DIR", raising=False)
    assert default_experience_cache_dir() == Path("data/experience_cache")


# --------------------------------------------------------------------------- #
# fetch_hmd (injected, non-network downloader)
# --------------------------------------------------------------------------- #


def test_fetch_hmd_uses_injected_downloader(tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_downloader(url: str, dest: Path) -> None:
        calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("stub")

    paths = fetch_hmd("USA", cache_dir=tmp_path, downloader=fake_downloader)
    assert set(paths) == {"deaths", "exposures"}
    assert paths["deaths"].name == "Deaths_1x1.txt"
    assert paths["exposures"].name == "Exposures_1x1.txt"
    assert paths["deaths"].parent == tmp_path / "hmd" / "USA"
    # Both files fetched, with the country's authenticated URLs.
    assert len(calls) == 2
    assert all("/USA/STATS/" in url for url, _ in calls)


def test_fetch_hmd_skips_existing(tmp_path: Path) -> None:
    country_dir = tmp_path / "hmd" / "USA"
    country_dir.mkdir(parents=True)
    (country_dir / "Deaths_1x1.txt").write_text("cached")
    (country_dir / "Exposures_1x1.txt").write_text("cached")

    calls: list[str] = []

    def fake_downloader(url: str, dest: Path) -> None:
        calls.append(url)

    fetch_hmd("USA", cache_dir=tmp_path, downloader=fake_downloader)
    assert calls == []  # both already cached → no download


def test_fetch_hmd_overwrite_redownloads(tmp_path: Path) -> None:
    country_dir = tmp_path / "hmd" / "USA"
    country_dir.mkdir(parents=True)
    (country_dir / "Deaths_1x1.txt").write_text("cached")
    (country_dir / "Exposures_1x1.txt").write_text("cached")

    calls: list[str] = []

    def fake_downloader(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_text("fresh")

    fetch_hmd("USA", cache_dir=tmp_path, downloader=fake_downloader, overwrite=True)
    assert len(calls) == 2


def test_fetch_hmd_download_failure_raises(tmp_path: Path) -> None:
    def failing_downloader(url: str, dest: Path) -> None:
        raise OSError("network down")

    with pytest.raises(PolarisComputationError, match="Failed to fetch HMD"):
        fetch_hmd("USA", cache_dir=tmp_path, downloader=failing_downloader)


# --------------------------------------------------------------------------- #
# Integration: loaded cells feed the tensor MI surface
# --------------------------------------------------------------------------- #


def _synthetic_ilec_grid(tmp_path: Path) -> Path:
    """A modest agexyear ILEC grid so the tensor fit is identifiable."""
    rng = np.random.default_rng(SEED)
    rows = []
    for yr in range(2010, 2016):
        for age in range(45, 60):
            rows.append(
                {
                    "Observation Year": yr,
                    "Attained Age": age,
                    "Duration": 10,
                    "Gender": "Male",
                    "Smoker Status": "Nonsmoker",
                    "Policies Exposed": 5000.0,
                    "Death Count": float(rng.poisson(5.0)),
                }
            )
    path = tmp_path / "ilec_grid.csv"
    pl.DataFrame(rows).write_csv(path)
    return path


def test_loaded_ilec_feeds_tensor_mi_surface(tmp_path: Path) -> None:
    path = _synthetic_ilec_grid(tmp_path)
    cells = load_ilec(path, basis="count")
    table = MortalityTable.load(
        MortalityTableSource.SOA_VBT_2015, data_dir=Path("data/mortality_tables")
    )
    cells = attach_base_rate(cells, table)
    result = TensorMIModel(cells, age_df=4, year_df=4).fit()
    surface = result.improvement_surface()
    # A full agexyear improvement grid comes back (15 ages x 5 year-steps).
    assert surface.mi_grid.shape[0] == 15
    assert surface.mi_grid.shape[1] == 5
    assert np.all(np.isfinite(surface.mi_grid))


# ---------------------------------------------------------------------------
# Tab-delimited + 2012-19 vintage (real SOA release, 2026-08-03)
# ---------------------------------------------------------------------------


def _write_ilec_2012_19(tmp_path: Path) -> Path:
    """A TAB-delimited extract in the real 2012-19 release's header spelling.

    Mirrors the header of `ILEC_2012_19 - 20240429.txt`: underscored names,
    ``Sex`` rather than ``Gender``, and no ``Distribution Channel`` column at
    all. Written with ``.txt`` because that is what SOA ships — the extension
    carries no format information, the separator does.
    """
    df = pl.DataFrame(
        {
            "Observation_Year": [2015, 2015, 2015, 2016],
            "Attained_Age": [45, 45, 46, 45],
            "Issue_Age": [40, 40, 41, 40],
            "Duration": [6, 6, 6, 7],
            "Sex": ["Male", "Male", "Female", "Male"],
            "Smoker_Status": ["Nonsmoker", "Nonsmoker", "Smoker", "Nonsmoker"],
            "Insurance_Plan": ["Term", "Term", "Term", "Term"],
            "Face_Amount_Band": ["A", "A", "A", "A"],
            "Preferred_Class": ["1", "1", "1", "1"],
            "Policies_Exposed": [1000.0, 500.0, 800.0, 900.0],
            "Death_Count": [2.0, 1.0, 3.0, 2.0],
            "Amount_Exposed": [1e8, 5e7, 8e7, 9e7],
            "Death_Claim_Amount": [2e5, 1e5, 3e5, 2e5],
            # SOA's published expected deaths — the independent A/E denominator.
            "ExpDth_VBT2015_Cnt": [1.8, 0.9, 2.7, 1.8],
            "ExpDth_VBT2015wMI_Cnt": [1.7, 0.85, 2.6, 1.7],
            "ExpDth_VBT2015_Amt": [1.8e5, 0.9e5, 2.7e5, 1.8e5],
            "ExpDth_VBT2015wMI_Amt": [1.7e5, 0.85e5, 2.6e5, 1.7e5],
            # A column the loader ignores, as the real file has many.
            "Slct_Ult_Ind": ["S", "S", "S", "S"],
        }
    )
    path = tmp_path / "ILEC_2012_19 - sample.txt"
    df.write_csv(path, separator="\t")
    return path


def test_load_ilec_reads_tab_delimited(tmp_path: Path) -> None:
    """A tab-delimited file loads when the separator is declared."""
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP)
    m45 = cells.filter(
        (pl.col("attained_age") == 45) & (pl.col("calendar_year") == 2015) & (pl.col("sex") == "M")
    )
    assert m45.height == 1
    assert m45["central_exposure"][0] == pytest.approx(1500.0)
    assert m45["death_count"][0] == pytest.approx(3.0)


def test_tab_file_read_as_comma_raises_rather_than_silently_misparsing(
    tmp_path: Path,
) -> None:
    """The default comma separator must fail loudly on a tab file.

    A single-column misparse would otherwise surface much later as a confusing
    'missing measure column' error against a column list of one.
    """
    path = _write_ilec_2012_19(tmp_path)
    with pytest.raises((PolarisValidationError, PolarisComputationError)):
        load_ilec(path, column_map=ILEC_2012_19_COLUMN_MAP)


def test_ilec_2012_19_map_covers_every_canonical_target(tmp_path: Path) -> None:
    """The vintage map must reach every canonical column the default map does,
    minus the ones this release genuinely does not publish."""
    default_targets = set(ILEC_COLUMN_MAP.values())
    vintage_targets = set(ILEC_2012_19_COLUMN_MAP.values())
    # 2012-19 has no distribution-channel column; everything else is covered.
    assert default_targets - vintage_targets == {"channel"}


def test_ilec_2012_19_map_uses_sex_not_gender() -> None:
    """The 2012-19 release renamed Gender -> Sex; that is not just underscoring."""
    assert "Sex" in ILEC_2012_19_COLUMN_MAP
    assert ILEC_2012_19_COLUMN_MAP["Sex"] == "sex"
    assert "Gender" not in ILEC_2012_19_COLUMN_MAP


def test_load_ilec_selects_only_mapped_columns(tmp_path: Path) -> None:
    """Unmapped source columns must not be materialised.

    The real 2012-19 file is 12 GB with 30 columns; reading the ~17 that are
    never used would be most of the memory cost for none of the value.
    """
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP)
    assert "ExpDth_VBT2015_Cnt" not in cells.columns
    assert "Slct_Ult_Ind" not in cells.columns


# ---------------------------------------------------------------------------
# SOA-published expected deaths — the independent A/E denominator
# ---------------------------------------------------------------------------


def test_expected_measures_are_off_by_default(tmp_path: Path) -> None:
    """The default carry-through is unchanged — expected columns are opt-in."""
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP)
    for col in (*ILEC_EXPECTED_COUNT_MEASURES, *ILEC_EXPECTED_AMOUNT_MEASURES):
        assert col not in cells.columns


def test_include_expected_carries_and_sums_the_count_pair(tmp_path: Path) -> None:
    """``include_expected`` sums SOA's expected deaths over the same cells."""
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(
        path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP, include_expected=True
    )
    for col in ILEC_EXPECTED_COUNT_MEASURES:
        assert col in cells.columns
    # The two Male/NS/2015/age-45 source rows collapse; expected deaths sum
    # exactly as the actual deaths do, so the A/E ratio is well-defined per cell.
    m45 = cells.filter(
        (pl.col("attained_age") == 45) & (pl.col("calendar_year") == 2015) & (pl.col("sex") == "M")
    )
    assert m45.height == 1
    assert m45["expected_deaths_vbt2015"][0] == pytest.approx(1.8 + 0.9)
    assert m45["death_count"][0] == pytest.approx(3.0)


def test_expected_deaths_give_a_computable_ae_ratio(tmp_path: Path) -> None:
    """The point of the whole thing: actual/expected on identical cells.

    SOA publishes expected deaths on the VBT 2015 basis with and without
    mortality improvement, so the A/E ratio is an *independent* check on our own
    improvement surface rather than a comparison against a narrative.
    """
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(
        path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP, include_expected=True
    )
    ae = cells.select(
        (pl.col("death_count").sum() / pl.col("expected_deaths_vbt2015").sum()).alias("ae")
    )["ae"][0]
    assert ae == pytest.approx(8.0 / 7.2)


def test_amount_basis_carries_the_amount_expected_pair(tmp_path: Path) -> None:
    path = _write_ilec_2012_19(tmp_path)
    cells = load_ilec(
        path,
        separator="\t",
        column_map=ILEC_2012_19_COLUMN_MAP,
        basis="amount",
        include_expected=True,
    )
    for col in ILEC_EXPECTED_AMOUNT_MEASURES:
        assert col in cells.columns
    for col in ILEC_EXPECTED_COUNT_MEASURES:
        assert col not in cells.columns


def test_include_expected_raises_when_the_vintage_lacks_the_columns(tmp_path: Path) -> None:
    """A vintage without SOA expected deaths must fail loudly, not silently drop.

    Asking for the A/E denominator and getting a frame without it would make the
    check quietly unavailable at exactly the moment it is being relied on.
    """
    path = _write_ilec(tmp_path)  # the plain fixture has no ExpDth columns
    with pytest.raises(PolarisValidationError, match="expected-death"):
        load_ilec(path, include_expected=True)
