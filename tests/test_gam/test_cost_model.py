"""Cost model for the dashboard GAM section (D1, ADR-262): MEASUREMENT (own criterion) checks.

The tolerance below was fixed before the model was first scored: leave-one-out predictions of
the fitted R2 cells must lie within a factor of 3 for every cell (a factor-2 tolerance would
not be achievable from rows alone: cells of one size differ 3.6x between formulas).
"""

import json
from pathlib import Path

import polars as pl
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import gam
from polaris_re.gam.cost_model import (
    BAM_DEFAULT_THRESHOLD_ROWS,
    GAM_MEASURED,
    bam_refusal,
    default_engine,
    estimate_n_coef,
    fit_cost_model,
    pre_run_warning,
)

TRIAL = Path(__file__).parents[2] / "docs" / "measurements" / "gam_real_data_trial_2026-10-15.json"


def test_measured_table_equals_committed_json() -> None:
    d = json.loads(TRIAL.read_text())
    rows = {
        (f"{x['formula']} {x['granularity']}", x["n_cells"], x["n_coef"]): x["polaris"][
            "best_seconds"
        ]
        for x in d["results"]
        if x["status"] == "fitted"
    }
    assert len(rows) == len(GAM_MEASURED)
    for name, n, p, sec in GAM_MEASURED:
        assert rows[(name, n, p)] == pytest.approx(sec, abs=1e-3)


def test_leave_one_out_within_factor_three_and_band_reported() -> None:
    m = fit_cost_model()
    assert m.gam_loo_within_3x == 1.0
    assert 1.0 < m.gam_band < 3.0


@pytest.mark.parametrize(
    ("n", "engine"), [(1, "gam"), (BAM_DEFAULT_THRESHOLD_ROWS, "gam"), (300_001, "bam")]
)
def test_default_engine_threshold(n: int, engine: str) -> None:
    assert default_engine(n) == engine


def test_extrapolation_is_flagged() -> None:
    m = fit_cost_model()
    assert m.estimate("gam", 886_189, 110).extrapolated is False
    assert m.estimate("gam", 5_000_000, 110).extrapolated is True
    assert m.estimate("bam", 20_000_000, 100).extrapolated is True


def test_bam_refusals_are_stated_not_substituted() -> None:
    assert bam_refusal('y ~ s(x, bs="cr")', "poisson") is None
    assert "poisson and binomial" in (bam_refusal('y ~ s(x, bs="cr")', "gaussian") or "")
    assert "thin-plate" in (bam_refusal("y ~ s(x)", "poisson") or "")


@pytest.mark.parametrize("engine", ["gam", "bam"])
@pytest.mark.parametrize("n", [10_000, 300_000, 3_000_000])
def test_warning_text_for_each_engine_by_size(engine: str, n: int) -> None:
    m = fit_cost_model()
    w = pre_run_warning(
        m,
        engine,
        n,
        20,
        formula='y ~ s(x, bs="cr")',
        family="poisson",
        available_gb=64.0,  # type: ignore[arg-type]
    )
    text = " ".join(w.lines)
    assert "Expected runtime" in text
    assert "Apple M4" in text
    if engine == "bam":
        assert "different algorithm" in text
        assert "Expected peak memory" in text
    else:
        assert "NOT modelled" in text


def test_machine_that_cannot_hold_request_is_blocked_loudly() -> None:
    w = pre_run_warning(
        fit_cost_model(),
        "bam",
        3_000_000,
        20,
        formula='y ~ s(x, bs="cr")',
        family="poisson",
        available_gb=4.0,
    )
    assert w.level == "error"
    assert w.blocked


def test_estimate_n_coef_matches_fit() -> None:
    n = 400
    df = pl.DataFrame(
        {
            "y": [float(i % 5) for i in range(n)],
            "x": [i / n for i in range(n)],
            "z": [(i * 7 % n) / n for i in range(n)],
            "g": ["a", "b", "c", "d"] * (n // 4),
        }
    )
    formula = 'y ~ g + s(x, bs="cr", k=6) + s(z, bs="cr", k=5, by=g)'
    fit = gam(formula, df, "gaussian")
    assert estimate_n_coef(formula, df) == len(fit.coef)


def test_estimate_n_coef_unknown_column_refused() -> None:
    with pytest.raises(PolarisValidationError):
        estimate_n_coef('y ~ s(x, bs="cr", by=g)', pl.DataFrame({"y": [1.0], "x": [1.0]}))


def test_bam_measured_matches_adr_260_tables() -> None:
    from polaris_re.gam.cost_model import BAM_MEASURED

    adr = Path(__file__).parents[2] / "docs" / "DECISIONS.md"
    if not adr.exists():
        pytest.skip("docs/DECISIONS.md not present (container image)")
    text = adr.read_text()
    for name, n, sec, gb in BAM_MEASURED:
        rows = [ln for ln in text.splitlines() if name in ln and f"{n:,}" in ln and "GB" in ln]
        # earlier amendments quote the same cell at a different (superseded) time
        assert any(f"{sec} s / {gb} GB" in ln for ln in rows), name


def test_gam_block_uses_stated_multiplier_and_bam_band() -> None:
    from polaris_re.gam.cost_model import GAM_MEMORY_FLOOR_MULTIPLIER

    m = fit_cost_model()
    # floor 0.8 GB x 12 = 9.6 GB > 0.8 x 8 GB: blocked, and the assumption is printed.
    w = pre_run_warning(
        m, "gam", 500_000, 200, formula='y ~ s(x, bs="cr")', family="poisson", available_gb=8.0
    )
    assert w.blocked
    assert f"ASSUMES {GAM_MEMORY_FLOOR_MULTIPLIER:.0f}x" in " ".join(w.lines)
