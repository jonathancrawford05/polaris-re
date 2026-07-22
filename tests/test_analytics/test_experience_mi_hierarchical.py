"""
Tests for the Slice-3 hierarchical partial-pooling (credibility) MI surface.

Covers the Slice-3 acceptance criteria from docs/PLAN_experience_gam.md and
docs/CONTINUATION_experience_gam.md — segment-level MI/level deviations shrunk
toward the global reduced-rank-GP surface, with the pooling strength *estimated*
by empirical Bayes rather than imposed:

- a thin segment shrinks toward the global surface (small credibility, |pooled|
  deviation < |raw|, same sign, strictly between the raw cell and the global 0);
- a data-rich segment escapes pooling (credibility ~1, pooled ~ raw);
- credibility rises monotonically with segment exposure;
- empirical Bayes recovers a known between-segment variance component (and
  collapses toward complete pooling when segments are truly identical);
- per-segment calendar-trend (MI) deviations shrink the same way; a thin
  segment's improvement surface collapses onto the global one while a rich
  segment with a genuine faster trend separates from it;
- the global (``segment=None``) surface recovers the population improvement and
  the deviations sum to zero (sum-to-zero identifiability);
- the fit is deterministic (bit-identical on re-run);
- contract validation (missing/single-level segment, single calendar year,
  bad tau) and a valid :class:`MISurface` / credibility table are returned.

Deaths are set to their *expected* value (deterministic, deaths == exposure * q),
so the raw per-segment A/E equals the generating level/trend exactly — a
closed-form verification of the shrinkage. Shrinkage is driven by each segment's
Fisher information (its exposure), not by point-estimate noise, so deterministic
deaths still exercise credibility fully. No test depends on the wall clock
(ADR-074 guard). The model is pure NumPy/SciPy — no statsmodels / [ml] extra.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.analytics.experience_gam import (
    BayesianTensorMIModel,
    HierarchicalMIModel,
    HierarchicalMISurfaceResult,
    MISurface,
)
from polaris_re.core.exceptions import PolarisValidationError

SEED = 20260722


# --------------------------------------------------------------------------- #
# Synthetic data helpers
# --------------------------------------------------------------------------- #


def _q_base(age: np.ndarray) -> np.ndarray:
    """A smooth, increasing static base rate q_base(age) in (0, 1)."""
    return 0.004 * np.exp(0.08 * (np.asarray(age, dtype=np.float64) - 45.0))


def _segmented_cells(
    ages: np.ndarray,
    years: np.ndarray,
    segments: dict[str, dict],
) -> pl.DataFrame:
    """Grouped cells over an age x year grid for several segments.

    ``segments`` maps a segment label to ``{"exposure", "level", "mi"}`` where the
    actual mortality is ``q_base(age) * level * (1 - mi)^(year - base_year)`` and
    deaths are set to the expected count (deterministic — the raw segment A/E is
    exactly ``level`` and the raw improvement is exactly ``mi``).
    """
    base = int(years.min())
    rows = []
    for label, spec in segments.items():
        expo = float(spec["exposure"])
        level = float(spec.get("level", 1.0))
        mi = float(spec.get("mi", 0.0))
        for a in ages:
            q0 = float(_q_base(np.array([a]))[0])
            for y in years:
                actual_q = q0 * level * (1.0 - mi) ** (int(y) - base)
                rows.append(
                    {
                        "attained_age": int(a),
                        "calendar_year": int(y),
                        "q_base": q0,
                        "central_exposure": expo,
                        "death_count": expo * actual_q,
                        "segment": label,
                    }
                )
    return pl.DataFrame(rows)


_AGES = np.arange(45, 66)
_YEARS = np.arange(2008, 2019)


def _spread_segments(
    n_seg: int,
    tau_true: float,
    *,
    seed: int = SEED,
    exp_lo: float = 30.0,
    exp_hi: float = 3.0e6,
) -> tuple[dict[str, dict], np.ndarray]:
    """``n_seg`` segments with N(0, tau_true**2) log-level deviations (symmetric)
    and exposure spanning ``[exp_lo, exp_hi]`` geometrically (thin -> rich)."""
    rng = np.random.default_rng(seed)
    dev = rng.normal(0.0, tau_true, size=n_seg)
    dev -= dev.mean()  # symmetric => the unweighted global ~ the true baseline
    expo = np.geomspace(exp_lo, exp_hi, n_seg)
    segments = {
        f"s{i:02d}": {"exposure": float(expo[i]), "level": float(np.exp(dev[i]))}
        for i in range(n_seg)
    }
    return segments, dev


# --------------------------------------------------------------------------- #
# Credibility shrinkage (closed-form verification)
# --------------------------------------------------------------------------- #


def test_thin_segment_shrinks_toward_global():
    """The thinnest segment's deviation is pulled strongly toward the global 0."""
    segments, dev = _spread_segments(12, tau_true=0.15)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects().sort("exposure")

    thin = eff.row(0, named=True)
    raw_dev = dev[np.argmin([s["exposure"] for s in segments.values()])]
    # Shrunk: strictly between the raw cell estimate and the global (0), same sign.
    assert abs(thin["level_deviation"]) < abs(raw_dev)
    assert np.sign(thin["level_deviation"]) == np.sign(raw_dev)
    assert abs(thin["level_deviation"]) < 0.75 * abs(raw_dev)  # meaningful shrinkage
    assert thin["credibility"] < 0.6  # low credibility for a thin segment


def test_rich_segment_escapes_pooling():
    """A data-rich segment keeps ~all of its own signal (credibility ~1)."""
    segments, dev = _spread_segments(12, tau_true=0.15)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects().sort("exposure")

    rich = eff.row(eff.height - 1, named=True)
    raw_dev = dev[np.argmax([s["exposure"] for s in segments.values()])]
    assert rich["credibility"] > 0.95
    # Pooled deviation ~ raw deviation (barely shrunk).
    np.testing.assert_allclose(rich["level_deviation"], raw_dev, atol=0.03)


@pytest.mark.parametrize("thin_level", [np.exp(0.3), np.exp(-0.3)])
def test_pooled_estimate_lies_between_raw_and_global(thin_level):
    """A thin segment with a clear deviation is pulled strictly between its raw-cell
    estimate and the global surface (0), in both directions."""
    # Rich anchors pin the global level; one thin segment carries a real deviation.
    segments = {
        "anchor_a": {"exposure": 2.0e6, "level": 1.0},
        "anchor_b": {"exposure": 2.0e6, "level": 1.0},
        "anchor_c": {"exposure": 2.0e6, "level": 1.0},
        "anchor_d": {"exposure": 2.0e6, "level": 1.0},
        "thin": {"exposure": 60.0, "level": float(thin_level)},
    }
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects()
    by_seg = {r["segment"]: r for r in eff.iter_rows(named=True)}

    # Raw deviation is relative to the (unweighted) sum-to-zero global.
    mean_log = np.mean(np.log([s["level"] for s in segments.values()]))
    raw = float(np.log(thin_level) - mean_log)
    pooled = by_seg["thin"]["level_deviation"]
    lo, hi = sorted((0.0, raw))
    assert lo < pooled < hi  # strictly between the global (0) and the raw cell
    assert by_seg["thin"]["credibility"] < 0.7


def test_credibility_monotonic_in_exposure():
    """More exposure => higher credibility (less shrinkage)."""
    segments, _dev = _spread_segments(12, tau_true=0.15)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects().sort("exposure")
    cred = eff["credibility"].to_numpy()
    assert np.all(np.diff(cred) >= -1e-9)  # non-decreasing in exposure


# --------------------------------------------------------------------------- #
# Empirical-Bayes variance component
# --------------------------------------------------------------------------- #


def test_eb_recovers_variance_component():
    """The estimated between-segment SD tracks the true one and is far above the
    complete-pooling estimate when segments are truly identical."""
    segments_hi, _ = _spread_segments(16, tau_true=0.2, seed=SEED)
    cells_hi = _segmented_cells(_AGES, _YEARS, segments_hi)
    res_hi = HierarchicalMIModel(cells_hi, age_varying=False, segment_trend=False).fit()
    # Recovered within a small-sample REML tolerance (mild shrinkage of the estimate).
    assert 0.12 < res_hi.tau_level < 0.26

    # Identical segments (no real dispersion) => tau collapses toward the floor.
    segments_zero = {
        f"s{i:02d}": {"exposure": float(e), "level": 1.0}
        for i, e in enumerate(np.geomspace(1.0e4, 3.0e6, 10))
    }
    cells_zero = _segmented_cells(_AGES, _YEARS, segments_zero)
    res_zero = HierarchicalMIModel(cells_zero, age_varying=False, segment_trend=False).fit()
    assert res_zero.tau_level < 0.02
    assert res_hi.tau_level > 5.0 * res_zero.tau_level


def test_sum_to_zero_identifiability():
    """Per-segment level deviations sum to zero (the identifiability constraint)."""
    segments, _ = _spread_segments(10, tau_true=0.15)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects()
    assert abs(float(eff["level_deviation"].sum())) < 1e-9


# --------------------------------------------------------------------------- #
# Segment trend (MI) deviations
# --------------------------------------------------------------------------- #


def test_segment_trend_deviation_shrinks_and_separates():
    """A rich segment with a genuinely faster improvement separates from the
    global surface; a thin segment with no real trend deviation collapses onto it."""
    segments = {
        # Baseline rich segments follow the global 1%/yr improvement.
        "base_a": {"exposure": 2.0e6, "mi": 0.01},
        "base_b": {"exposure": 2.0e6, "mi": 0.01},
        "base_c": {"exposure": 2.0e6, "mi": 0.01},
        # Rich segment improving markedly faster (2%/yr).
        "fast": {"exposure": 2.0e6, "mi": 0.02},
        # Thin segment nominally on the global trend but with tiny exposure.
        "thin": {"exposure": 40.0, "mi": 0.01},
    }
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    eff = res.segment_effects()
    by_seg = {r["segment"]: r for r in eff.iter_rows(named=True)}

    # The fast segment's trend deviation is credible and positive (faster
    # improvement => a positive MI deviation vs the global trend).
    assert by_seg["fast"]["trend_credibility"] > by_seg["thin"]["trend_credibility"]
    assert by_seg["fast"]["trend_deviation"] > 0.002

    # Surfaces: the fast segment improves faster than global; the thin one ~ global.
    interior = slice(4, 16)
    global_mi = res.improvement_surface(segment=None).mi_grid[interior].mean()
    fast_mi = res.improvement_surface(segment="fast").mi_grid[interior].mean()
    thin_mi = res.improvement_surface(segment="thin").mi_grid[interior].mean()
    assert fast_mi > global_mi + 0.003  # separates upward
    assert abs(thin_mi - global_mi) < 0.002  # collapses onto the global surface


def test_global_surface_recovers_population_improvement():
    """The global surface recovers the shared calendar improvement, and matches a
    plain BayesianTensorMIModel that never saw the segment column."""
    segments = {
        "a": {"exposure": 2.0e6, "mi": 0.015, "level": 1.1},
        "b": {"exposure": 2.0e6, "mi": 0.015, "level": 0.9},
        "c": {"exposure": 2.0e6, "mi": 0.015, "level": 1.0},
    }
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    interior = slice(4, 16)
    global_mi = res.improvement_surface(segment=None).mi_grid[interior]
    np.testing.assert_allclose(global_mi.mean(), 0.015, atol=3e-3)

    # A plain model with segment dropped should see the same population trend.
    plain = (
        BayesianTensorMIModel(cells.drop("segment"), age_varying=False)
        .fit()
        .improvement_surface()
        .mi_grid[interior]
    )
    np.testing.assert_allclose(global_mi.mean(), plain.mean(), atol=2e-3)


# --------------------------------------------------------------------------- #
# Bands, determinism, surface shape
# --------------------------------------------------------------------------- #


def test_thin_segment_band_wider_than_rich():
    """The posterior credible band on a thin segment's surface is wider."""
    segments = {
        "rich_a": {"exposure": 2.0e6},
        "rich_b": {"exposure": 2.0e6},
        "thin": {"exposure": 50.0},
    }
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    interior = slice(4, 16)
    rich = res.improvement_surface(segment="rich_a")
    thin = res.improvement_surface(segment="thin")
    rich_w = (rich.mi_upper - rich.mi_lower)[interior].mean()
    thin_w = (thin.mi_upper - thin.mi_lower)[interior].mean()
    assert thin_w > rich_w
    # A valid band on both.
    assert np.all(thin.mi_lower <= thin.mi_grid + 1e-12)
    assert np.all(thin.mi_grid <= thin.mi_upper + 1e-12)


def test_surface_is_mi_surface_with_expected_shape():
    segments, _ = _spread_segments(5, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    surf = res.improvement_surface(segment=None)
    assert isinstance(surf, MISurface)
    assert surf.mi_grid.shape == (len(_AGES), len(_YEARS) - 1)
    frame = surf.to_frame()
    assert set(frame.columns) == {"attained_age", "calendar_year", "mi", "mi_lower", "mi_upper"}


def test_fit_is_deterministic():
    segments, _ = _spread_segments(8, tau_true=0.15)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    r1 = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    r2 = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    assert np.array_equal(r1._theta, r2._theta)
    assert r1.tau_level == r2.tau_level
    assert r1.tau_trend == r2.tau_trend
    s1 = r1.improvement_surface(segment="s00")
    s2 = r2.improvement_surface(segment="s00")
    assert np.array_equal(s1.mi_grid, s2.mi_grid)


def test_segment_effects_reports_volume_and_result_metadata():
    segments = {"a": {"exposure": 1.0e6}, "b": {"exposure": 2.0e5}, "c": {"exposure": 500.0}}
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=True).fit()
    assert isinstance(res, HierarchicalMISurfaceResult)
    eff = res.segment_effects().sort("segment")
    assert eff["segment"].to_list() == ["a", "b", "c"]
    # exposure column == sum of central_exposure over the grid (21 ages x 11 years).
    ncells = len(_AGES) * len(_YEARS)
    assert eff.filter(pl.col("segment") == "a")["exposure"].item() == pytest.approx(1.0e6 * ncells)
    assert eff.filter(pl.col("segment") == "a")["n_cells"].item() == ncells
    assert set(
        {
            "level_deviation",
            "level_multiplier",
            "credibility",
            "trend_deviation",
            "trend_credibility",
        }
    ).issubset(eff.columns)


def test_no_trend_option_omits_trend_columns():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False, segment_trend=False).fit()
    eff = res.segment_effects()
    assert "trend_deviation" not in eff.columns
    assert res.tau_trend == 0.0
    assert res.include_trend is False


# --------------------------------------------------------------------------- #
# Contract validation
# --------------------------------------------------------------------------- #


def test_missing_segment_column_raises():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments).drop("segment")
    with pytest.raises(PolarisValidationError, match="segment_col"):
        HierarchicalMIModel(cells)


def test_single_segment_level_raises():
    cells = _segmented_cells(_AGES, _YEARS, {"only": {"exposure": 1.0e6}})
    with pytest.raises(PolarisValidationError, match=">= 2 segment levels"):
        HierarchicalMIModel(cells)


def test_single_calendar_year_raises():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, np.array([2015]), segments)
    with pytest.raises(PolarisValidationError, match="distinct calendar_year"):
        HierarchicalMIModel(cells)


def test_bad_tau_raises():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    with pytest.raises(PolarisValidationError, match="tau_init and tau_floor must be positive"):
        HierarchicalMIModel(cells, tau_init=0.0)


def test_unknown_segment_surface_raises():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False).fit()
    with pytest.raises(PolarisValidationError, match="Unknown segment"):
        res.improvement_surface(segment="nope")


def test_single_year_surface_request_raises():
    segments, _ = _spread_segments(4, tau_true=0.1)
    cells = _segmented_cells(_AGES, _YEARS, segments)
    res = HierarchicalMIModel(cells, age_varying=False).fit()
    with pytest.raises(PolarisValidationError, match="at least two calendar years"):
        res.improvement_surface(segment=None, years=np.array([2015]))


def test_generational_base_guard_inherited():
    """The Anchor-1 static-base guard is inherited from BayesianTensorMIModel."""
    base = int(_YEARS.min())
    rows = []
    for label, expo in (("a", 1.0e6), ("b", 1.0e6)):
        for a in _AGES:
            q0 = float(_q_base(np.array([a]))[0])
            for y in _YEARS:
                # q_base drifts with calendar year => a generational (non-static) base.
                q_col = q0 * 1.01 ** (int(y) - base)
                rows.append(
                    {
                        "attained_age": int(a),
                        "calendar_year": int(y),
                        "q_base": q_col,
                        "central_exposure": expo,
                        "death_count": expo * q_col,
                        "segment": label,
                    }
                )
    cells = pl.DataFrame(rows)
    with pytest.raises(PolarisValidationError):
        HierarchicalMIModel(cells)
    # Explicit override is accepted.
    HierarchicalMIModel(cells, allow_generational_base=True)
