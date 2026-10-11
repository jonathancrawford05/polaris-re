"""Slice R2 (ADR-259): the ILEC trial harness, on SYNTHETIC cells only.

Pins the derived-scalars-only contract (PLAN §3), the trial formula table, the provenance
declaration, the data rules, and — when R is installed — an end-to-end run of
``scripts/gam_real_data_trial.py`` against the R companion. No licensed data is read.
"""

import importlib.util
import json
import sys
from pathlib import Path

import polars as pl
import pytest

from polaris_re.analytics.experience_loaders import ILEC_2012_19_COLUMN_MAP, load_ilec
from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import ComparisonProvenance
from polaris_re.gam import real_data_trial as t

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "test_analytics"))
from _ilec_trial_fixture import write_synthetic_ilec  # noqa: E402


@pytest.fixture(scope="module")
def loader_cells(tmp_path_factory: pytest.TempPathFactory) -> pl.DataFrame:
    path = write_synthetic_ilec(
        tmp_path_factory.mktemp("ilec") / "ilec.txt", ages=range(30, 46), years=range(2014, 2016)
    )
    return load_ilec(path, separator="\t", column_map=ILEC_2012_19_COLUMN_MAP)


def _by_name(name: str) -> t.TrialFormula:
    return next(f for f in t.FORMULAS if f.name == name)


# --- the contract ---------------------------------------------------------------------------


def test_whitelist_accepts_a_well_formed_result() -> None:
    ok = {
        "schema_version": 1,
        "tier": "tier L",
        "oracle_image_digest": "sha256:" + "a" * 64,
        "polaris_commit": "0b0a50e",
        "results": [
            {
                "formula": "T1",
                "granularity": "full",
                "status": "fitted",
                "n_cells": 100,
                "terms": [{"index": 0, "kind": "cr", "edf": 3.2, "log10_sp_min": 1.0}],
            }
        ],
    }
    t.assert_derived_scalars_only(ok)
    assert json.loads(t.dumps(ok))["results"][0]["formula"] == "T1"


@pytest.mark.parametrize(
    "bad",
    [
        {"cell_key": 1},
        {"results": [{"coefficients": [0.1, 0.2]}]},
        {"results": [{"status": "10000-24999"}]},
        {"results": [{"formula": "smokerS"}]},
        {"results": [{"terms": [{"index": i} for i in range(t.MAX_SEQUENCE + 1)]}]},
        {"oracle_image_digest": "latest"},
        {"machine": {"chip": "Apple M2; rm -rf /" + "x" * 80}},
    ],
)
def test_whitelist_rejects_anything_else(bad: dict[str, object]) -> None:
    with pytest.raises(PolarisValidationError):
        t.assert_derived_scalars_only(bad)


def test_every_result_the_pipeline_can_build_passes_the_whitelist(
    loader_cells: pl.DataFrame,
) -> None:
    spec = _by_name("T3c")
    data = t.to_factor_frame(t.aggregate_cells(loader_cells, spec, "mid"), ["face_band", "smoker"])
    side = t.fit_polaris(spec, data, repeats=1, profile=True)
    assert side.status == "fitted" and side.fit is not None
    summ = side.fit.summary()
    result = {
        "formula": spec.name,
        "granularity": "mid",
        "role": spec.role,
        "status": "fitted",
        "n_cells": data.height,
        "terms": t.terms_block(summ.smooths),
        "polaris": {"phase_seconds": side.phase_seconds, "peak_rss_mb": side.peak_rss_mb},
    }
    t.assert_derived_scalars_only(t.clean(result))
    # no label of a factor-by smooth (they carry level names) survives
    text = t.dumps(result)
    assert "smokerS" not in text and "smokerNS" not in text and "B0" not in text


def test_refusal_text_is_redacted_when_it_quotes_a_level() -> None:
    assert "redacted" in t.sanitise_refusal("level 'B01' not seen", ["B01"])
    assert t.sanitise_refusal("select=True with a factor-by smooth", ["B01"]).startswith("select")


# --- the formula table ----------------------------------------------------------------------


def test_the_gates_are_the_imported_ones_and_the_scaled_gate_is_the_maintainers() -> None:
    assert (t.ETA_GATE, t.EDF_GATE, t.SE_REL_GATE) == (2.0e-2, 1.0, 2.0e-2)
    assert (t.SCALED_ETA_GATE, t.SCALED_ETA_FLAG) == (0.1, 0.01)


def test_formula_table_matches_the_plan() -> None:
    names = [f.name for f in t.FORMULAS]
    assert names == ["T1", "T2", "T3a", "T3b", "T3c", "S1", "S2", "S3"]
    assert [f.role for f in t.FORMULAS] == ["main"] * 3 + ["candidate"] * 2 + ["sensitivity"] * 3
    assert _by_name("S1").family == 'binomial(link="cloglog")' and _by_name("S1").weights
    assert _by_name("T3b").select and not _by_name("T3a").select and not _by_name("T2").select
    assert (
        _by_name("T3b").allow_unverified_select
        and _by_name("T3a").formula == _by_name("T3b").formula
    )
    assert "offset(log_exposure)" in _by_name("T1").formula


def test_rehearsal_probe_formula_strings_equal_the_python_table() -> None:
    r = (REPO / "scripts" / "gam_real_data_trial_rehearsal_probe.R").read_text()
    assert t._T1_SMOOTH in r
    assert t._T2_BLOCK in r
    assert t._BY in r


@pytest.mark.parametrize("granularity", t.GRANULARITIES)
def test_each_granularity_aggregates_losslessly(
    loader_cells: pl.DataFrame, granularity: str
) -> None:
    spec = _by_name("T2")
    cells = t.aggregate_cells(loader_cells, spec, granularity)
    wanted = {"face_band" if c == "band" else c for c in t.required_columns(spec, granularity)}
    assert wanted <= set(cells.columns)
    assert cells["exposure"].sum() == pytest.approx(loader_cells["central_exposure"].sum())
    assert cells["deaths"].sum() == pytest.approx(loader_cells["death_count"].sum())
    assert {"log_exposure", "death_rate", "duration", "face_band"} <= set(cells.columns)


def test_s2_drops_the_unknown_smoker_level_and_nothing_else(loader_cells: pl.DataFrame) -> None:
    with_u = t.aggregate_cells(loader_cells, _by_name("T3a"), "mid")
    without = t.aggregate_cells(loader_cells, _by_name("S2"), "mid")
    assert "U" in with_u["smoker"].to_list() and "U" not in without["smoker"].to_list()


def test_s3_adds_the_derived_cohort_column(loader_cells: pl.DataFrame) -> None:
    cells = t.aggregate_cells(loader_cells, _by_name("S3"), "mid")
    assert "issue_year" in cells.columns
    assert (cells["issue_year"] == cells["calendar_year"] - cells["duration"] + 1).all()


def test_duration_is_numeric_integer_policy_year_capped_not_banded(
    loader_cells: pl.DataFrame,
) -> None:
    cells = t.aggregate_cells(loader_cells, _by_name("T1"), "mid")
    got = sorted(cells["duration"].unique().to_list())
    assert got == [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 11.0, 14.0, 17.0, 21.0, 24.0, 26.0]  # 27 -> 26
    assert max(got) == float(t.DURATION_CAP)


def test_the_binned_face_band_never_reaches_the_engine_under_its_own_name(
    loader_cells: pl.DataFrame,
) -> None:
    data = t.to_factor_frame(
        t.aggregate_cells(loader_cells, _by_name("T2"), "mid"), ["face_band", "smoker"]
    )
    assert data["face_band"].cat.get_categories().to_list() == ["B00", "B01", "B02"]


# --- the data rules -------------------------------------------------------------------------


def test_data_rules_pass_on_the_fixture_and_fail_when_broken(loader_cells: pl.DataFrame) -> None:
    t.assert_data_rules(loader_cells)
    broken = loader_cells.with_columns((pl.col("attained_age") + 1).alias("attained_age"))
    with pytest.raises(PolarisValidationError, match="rule 1"):
        t.assert_data_rules(broken)
    odd = loader_cells.with_columns(pl.lit("X").alias("smoker"))
    with pytest.raises(PolarisValidationError, match="rule 2"):
        t.assert_data_rules(odd)
    dead = loader_cells.with_columns(pl.lit(0.0).alias("central_exposure"))
    with pytest.raises(PolarisValidationError, match="rule 3"):
        t.assert_data_rules(dead)


# --- the Polaris side -----------------------------------------------------------------------


def test_t3_as_written_is_refused_unless_the_diagnostic_switch_is_on(
    loader_cells: pl.DataFrame,
) -> None:
    """The ADR-258 refusal is about the smooth structure (a plain s(age) and a ti over age beside
    s(age, by=smoker) under select=TRUE), not about basis syntax. T3b skips it on purpose."""
    from polaris_re.gam import gam

    spec = _by_name("T3b")
    data = t.to_factor_frame(t.aggregate_cells(loader_cells, spec, "mid"), ["face_band", "smoker"])
    with pytest.raises(PolarisValidationError, match="select=True"):
        gam(spec.formula, data, "poisson", select=True)
    side = t.fit_polaris(_by_name("T3c"), data, repeats=1, profile=False)
    assert side.status == "fitted"


def test_provenance_is_declared_per_column() -> None:
    assert all(q.provenance is ComparisonProvenance.INDEPENDENT for q in t.CLAIM.quantities)
    assert not any("seconds" in q.quantity or "RSS" in q.quantity for q in t.CLAIM.quantities)


def test_fit_polaris_takes_no_mgcv_payload() -> None:
    import inspect

    params = set(inspect.signature(t.fit_polaris).parameters)
    assert params == {"formula", "data", "repeats", "budget_s", "profile"}


# --- end to end, against the R companion ----------------------------------------------------


@pytest.mark.skipif(not rscript_mgcv_available(), reason="R with mgcv and jsonlite not installed")
def test_end_to_end_run_cell_writes_only_whitelisted_scalars(
    tmp_path: Path, loader_cells: pl.DataFrame
) -> None:
    spec = importlib.util.spec_from_file_location(
        "gam_real_data_trial_cli", REPO / "scripts" / "gam_real_data_trial.py"
    )
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    work = tmp_path / "work"
    work.mkdir()
    loader_cells.write_parquet(work / cli.LOADER_CELLS)
    for name, gran in (("T3c", "mid"), ("T1", "coarse")):
        rc = cli.main(
            [
                "run-cell",
                "--work",
                str(work),
                "--formula",
                name,
                "--granularity",
                gran,
                "--repeats",
                "1",
                "--no-profile",
                "--mgcv-env",
                "native",
                "--polaris-env",
                "native",
            ]
        )
        assert rc == 0
    ok = json.loads((work / "results" / "T3c_mid.json").read_text())
    assert ok["status"] == "fitted" and ok["agreement"]["n_terms_unmatched"] == 0
    assert ok["agreement"]["ratio_comparable"] is True
    assert ok["agreement"]["eta_scaled_max"] < 0.1
    assert json.loads((work / "results" / "T1_coarse.json").read_text())["status"] == "fitted"
    # the committed collation passes the whitelist and holds no per-row array
    rc = cli.main(
        [
            "collect",
            "--work",
            str(work),
            "--out",
            str(tmp_path / "out.json"),
            "--digest",
            "sha256:" + "0" * 64,
            "--threads",
            "1",
            "--host-arch",
            "x86_64",
            "--mgcv-env",
            "native",
        ]
    )
    assert rc == 0
    out = json.loads((tmp_path / "out.json").read_text())
    t.assert_derived_scalars_only(out)
    assert len(out["results"]) == 2
