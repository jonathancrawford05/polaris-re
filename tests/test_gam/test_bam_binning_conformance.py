"""``polaris_re.gam.bam_binning_conformance`` — real-data readiness Slice R3, Stage A (ADR-260).

R-free: the provenance gate (ADR-193), closed-form checks of the ported ``compress.df`` rule.
R-gated: the probe is run and read (tier 1 here, a regression check; the committed number is
the tier-3 CI reading)."""

import json
import subprocess
import sys
import typing
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_mgcv_conformance import rscript_mgcv_available
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparisonProvenance,
    VerificationClaim,
    require_parity_evidence,
)
from polaris_re.gam.bam_binning_conformance import (
    ALGORITHM_CLAIM,
    BINNING_CLAIM,
    BinningCase,
    compare_binning_case,
    compress_covariates,
    default_m,
    discretise_frame,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_binning_columns_are_independent_and_gate_parity() -> None:
    assert all(q.provenance is ComparisonProvenance.INDEPENDENT for q in BINNING_CLAIM.quantities)
    require_parity_evidence(BINNING_CLAIM.quantities, claim="bam binning")


def test_algorithm_columns_are_reference_internal_and_cannot_gate_parity() -> None:
    assert all(
        q.provenance is ComparisonProvenance.REFERENCE_INTERNAL for q in ALGORITHM_CLAIM.quantities
    )
    with pytest.raises(PolarisValidationError):
        require_parity_evidence(ALGORITHM_CLAIM.quantities, claim="mgcv vs mgcv")


def test_the_polaris_producer_takes_no_mgcv_payload() -> None:
    """ADR-193's mechanical test, on the signature."""
    hints = typing.get_type_hints(discretise_frame)
    assert set(hints) == {"formula", "data", "m", "return"}
    assert hints["formula"] is str
    assert hints["data"] is pl.DataFrame
    assert isinstance(BINNING_CLAIM, VerificationClaim)


@pytest.mark.parametrize(
    ("d", "m", "expected"),
    [(1, None, 1000), (2, None, 100), (3, None, 25), (5, None, 25), (1, 500, 500), (2, 10000, 101)],
)
def test_default_m_matches_the_source(d: int, m: int | None, expected: int) -> None:
    assert default_m(d, m) == expected


def test_default_m_three_columns_given_m_is_round_cube_root_plus_one() -> None:
    assert default_m(3, 1000) == round(1000 ** (1 / 3)) + 1 == 11


def test_integer_covariates_are_not_binned() -> None:
    """The ILEC case: far fewer than 1000 unique values means the cells ARE the unique rows."""
    age = np.tile(np.arange(30, 91, dtype=np.float64), 20)
    term = compress_covariates({"age": age})
    assert not term.binned
    assert term.nr == 61
    np.testing.assert_array_equal(term.row_values("age"), age)


def test_all_unique_below_threshold_is_the_identity_index() -> None:
    x = np.random.default_rng(0).uniform(size=800)
    term = compress_covariates({"x": x})
    assert not term.binned
    np.testing.assert_array_equal(term.index, np.arange(800))
    np.testing.assert_array_equal(term.row_values("x"), x)


def test_threshold_is_strictly_greater_than() -> None:
    """1000 unique values are not binned, 1001 are (``nrow(xu) > mm * mf``)."""
    at = compress_covariates({"x": np.arange(1, 1001, dtype=np.float64)})
    over = compress_covariates({"x": np.arange(1, 1002, dtype=np.float64)})
    assert not at.binned
    assert over.binned
    assert over.nr <= 1000


def test_binning_snaps_to_the_closed_form_grid() -> None:
    """x on [0, 1] with 2000 points, m = 1000: grid points are i/999 and no value moves more
    than half a grid step (closed form: the rule is nearest-grid-point)."""
    x = np.linspace(0.0, 1.0, 2000)
    term = compress_covariates({"x": x})
    assert term.binned
    dx = 1.0 / 999.0
    snapped = term.row_values("x")
    assert np.max(np.abs(snapped - x)) <= dx / 2 + 1e-12
    np.testing.assert_allclose(snapped * 999.0, np.round(snapped * 999.0), atol=1e-9)
    assert term.values["x"].min() == 0.0
    np.testing.assert_allclose(term.values["x"].max(), 1.0, atol=1e-15)


def test_a_factor_multiplies_the_threshold_and_is_never_binned() -> None:
    rng = np.random.default_rng(1)
    x = rng.uniform(size=6000)
    f = rng.integers(0, 3, size=6000).astype(np.float64)
    term = compress_covariates({"x": x, "f": f}, frozenset({"f"}))
    # d = 2 so m = 100; threshold = 100 * 3 = 300; 6000 unique rows exceed it.
    assert term.binned
    assert term.nr <= 100 * 3
    np.testing.assert_array_equal(term.row_values("f"), f)


def test_rows_in_one_cell_share_every_discretised_value() -> None:
    rng = np.random.default_rng(2)
    z = rng.normal(size=5000)
    term = compress_covariates({"z": z})
    v = term.row_values("z")
    for cell in np.unique(term.index)[:20]:
        assert np.unique(v[term.index == cell]).shape[0] == 1


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_non_finite_covariates_are_refused(bad: float) -> None:
    with pytest.raises(PolarisValidationError, match="non-finite"):
        compress_covariates({"x": np.array([1.0, bad, 3.0])})


def test_ragged_or_empty_input_is_refused() -> None:
    with pytest.raises(PolarisValidationError):
        compress_covariates({})
    with pytest.raises(PolarisValidationError, match="equal length"):
        compress_covariates({"a": np.zeros(3), "b": np.zeros(4)})


def test_discretise_frame_follows_the_formula_and_reuses_shared_variables() -> None:
    df = pl.DataFrame(
        {
            "y": [0.0] * 8,
            "age": [30.0, 31.0, 30.0, 31.0, 30.0, 31.0, 30.0, 31.0],
            "dur": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 2.0, 2.0],
            "smoker": ["NS", "S", "NS", "S", "NS", "S", "NS", "S"],
        }
    )
    out = discretise_frame(
        'y ~ s(age, bs="cr", k=3) + ti(age, dur, bs="cr", k=c(3,3)) + smoker', df
    )
    assert list(out) == ["age", "dur", "smoker"]
    assert [out[k].nr for k in out] == [2, 2, 2]


def test_discretise_frame_names_a_missing_column() -> None:
    df = pl.DataFrame({"y": [0.0, 1.0], "x": [0.0, 1.0]})
    with pytest.raises(PolarisValidationError, match="'age'"):
        discretise_frame('y ~ s(age, bs="cr", k=3)', df)


def test_compare_flags_a_wrong_partition() -> None:
    """The comparator can disagree: hand it an mgcv payload with a merged cell."""
    df = pl.DataFrame({"y": [0.0] * 4, "x": [1.0, 2.0, 3.0, 4.0]})
    case = BinningCase("c", 'y ~ s(x, bs="cr", k=3)', df)
    ok = compare_binning_case(case, {"x": 4}, {"x": [1, 2, 3, 4]}, {"x": [1, 2, 3, 4]})
    assert ok[0].agrees
    merged = compare_binning_case(case, {"x": 3}, {"x": [1, 2, 3, 3]}, {"x": [1, 2, 3, 3]})
    assert not merged[0].agrees


def test_compare_reports_a_variable_mgcv_discretised_and_polaris_did_not() -> None:
    df = pl.DataFrame({"y": [0.0] * 4, "x": [1.0, 2.0, 3.0, 4.0]})
    case = BinningCase("c", 'y ~ s(x, bs="cr", k=3)', df)
    rows = compare_binning_case(
        case,
        {"x": 4, "z": 4},
        {"x": [1, 2, 3, 4], "z": [1, 2, 3, 4]},
        {"x": [1, 2, 3, 4], "z": [1, 2, 3, 4]},
    )
    missing = [r for r in rows if r.variable == "z"]
    assert len(missing) == 1
    assert not missing[0].agrees


@pytest.mark.skipif(not rscript_mgcv_available(), reason="Rscript with mgcv not available")
def test_the_probe_runs_and_every_variable_agrees(tmp_path: Path) -> None:
    out = tmp_path / "bb.json"
    subprocess.run(
        ["Rscript", str(REPO_ROOT / "scripts" / "bam_binning_probe.R"), str(out)],
        check=True,
        capture_output=True,
        env={"OPENBLAS_NUM_THREADS": "1", "PATH": "/usr/bin:/usr/local/bin:/bin"},
    )
    assert json.loads(out.read_text())["cells"]
    done = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bam_binning_compare.py"),
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "RESULT: 19/19 agree" in done.stdout
