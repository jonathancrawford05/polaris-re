"""S1 fit-report honesty (ADR-265): saturation flag, surface mask, exposure message.

MEASUREMENT (own criterion), not parity: there is no second producer. The tests assert the
arithmetic of the pre-registered rules (0.95 x coefficients; 5 x the median band) on
constructed inputs, the messages, and one real fit on each side of saturation.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.gam import gam
from polaris_re.gam.effects import ImprovementSurface, improvement_surface
from polaris_re.gam.fit_report import (
    MASK_BAND_MULTIPLE,
    SATURATION_THRESHOLD,
    drop_nonpositive_exposure,
    mask_surface,
    nonpositive_exposure,
    nonpositive_exposure_message,
    saturated_terms,
    saturation_lines,
    term_saturation,
)
from polaris_re.gam.summary import SmoothSummary


def test_constants_are_the_preregistered_values() -> None:
    np.testing.assert_allclose(SATURATION_THRESHOLD, 0.95, rtol=0)
    np.testing.assert_allclose(MASK_BAND_MULTIPLE, 5.0, rtol=0)


@pytest.mark.parametrize(
    ("edf", "n_coef", "expected"),
    [(6.65, 7, True), (6.64, 7, False), (7.0, 7, True), (1.0, 7, False), (18.83, 19, True)],
)
def test_saturated_is_edf_at_least_095_of_coefficients(
    edf: float, n_coef: int, expected: bool
) -> None:
    # 0.95 * 7 = 6.65; the maintainer's k=20 age smooth (18.83 of 19) is flagged.
    assert SmoothSummary("s(x)", edf, (0.0,), n_coef).saturated is expected


def _poisson_frame(truth, n: int = 1500, seed: int = 11) -> pl.DataFrame:  # type: ignore[no-untyped-def]
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 1, n)
    return pl.DataFrame({"x": x, "y": rng.poisson(np.exp(truth(x)) * 5.0).astype(np.float64)})


def test_a_wiggly_truth_on_a_small_basis_is_flagged_and_a_straight_one_is_not() -> None:
    wiggly = _poisson_frame(lambda x: 1.2 * np.sin(14 * x))
    f_small = gam('y ~ s(x, bs="cr", k=5)', wiggly, "poisson")
    flagged = saturated_terms(f_small)
    assert [t.label for t in flagged] == ["s(x)"]
    assert flagged[0].n_coef == 4  # k - 1 after the sum-to-zero constraint
    assert flagged[0].edf >= 0.95 * 4
    assert "consider a larger k" in saturation_lines(f_small)[0]
    assert "Basis saturation" in str(f_small.summary())

    straight = _poisson_frame(lambda x: 0.5 + 0.8 * x)
    f_line = gam('y ~ s(x, bs="cr", k=8)', straight, "poisson")
    assert saturated_terms(f_line) == []
    assert saturation_lines(f_line) == []
    assert "Basis saturation" not in str(f_line.summary())
    (t,) = term_saturation(f_line)
    assert t.n_coef == 7 and t.ratio < 0.95


def test_term_saturation_serves_a_bam_fit() -> None:
    d = _poisson_frame(lambda x: 0.5 + 0.8 * x, n=2000)
    fit = gam('y ~ s(x, bs="cr", k=6)', d, "poisson", method="fREML", discrete=True)
    (t,) = term_saturation(fit)
    assert t.n_coef == 5 and t.edf <= 5.0


def _surface(width: np.ndarray) -> ImprovementSurface:
    ages = np.array([30.0, 31.0, 32.0])
    years = np.array([2011.0, 2012.0, 2013.0, 2014.0])
    mid = np.full(width.shape, 0.01)
    return ImprovementSurface(
        ages=ages,
        years=years,
        mi=mid,
        mi_lower=mid - width / 2,
        mi_upper=mid + width / 2,
        mi_se=width / 4,
        d=-mid,
        d_se=width / 4,
        level=0.95,
        age_var="attained_age",
        year_var="calendar_year",
        step=1.0,
        reference={},
    )


def _cells(missing: set[tuple[int, int]]) -> pl.DataFrame:
    rows = [
        (a, y, 100.0)
        for a in (30, 31, 32)
        for y in (2010, 2011, 2012, 2013, 2014)
        if (a, y) not in missing
    ]
    a, y, e = zip(*rows, strict=True)
    return pl.DataFrame(
        {
            "attained_age": [float(v) for v in a],
            "calendar_year": [float(v) for v in y],
            "central_exposure": e,
        }
    )


def test_wide_band_cells_are_masked_at_exactly_5x_the_median() -> None:
    width = np.full((3, 4), 0.02)
    width[0, 0] = 0.1000001  # just over 5 x 0.02 -> masked
    width[2, 3] = 0.1  # exactly 5 x the median -> kept
    m = mask_surface(_surface(width), _cells(set()))
    assert m.median_band == pytest.approx(0.02)
    assert m.wide_band[0, 0] and not m.wide_band[2, 3]
    assert m.n_wide == 1 and m.n_no_exposure == 0
    assert np.isnan(m.apply(np.ones((3, 4)))[0, 0])
    assert "1 of 12 cells masked" in m.summary()


def test_a_cell_is_masked_when_either_contrast_point_has_no_exposure() -> None:
    # age 31 has no exposure in 2012: cell (31, 2012) lacks (x, y); cell (31, 2013) lacks (x, y-1).
    m = mask_surface(_surface(np.full((3, 4), 0.02)), _cells({(31, 2012)}))
    assert m.no_exposure[1, 1] and m.no_exposure[1, 2]
    assert int(m.no_exposure.sum()) == 2
    assert set(m.reason()[1, 1:3]) == {"no_exposure"}
    # An empty cell's (huge) band must not drag the median: the reference is the covered cells.
    width = np.full((3, 4), 0.02)
    width[1, 1] = 9.0
    m2 = mask_surface(_surface(width), _cells({(31, 2012)}))
    assert m2.median_band == pytest.approx(0.02)
    assert m2.n_wide == 0  # that cell is counted once, as no_exposure


def test_zero_exposure_rows_do_not_count_as_exposure() -> None:
    cells = _cells(set()).with_columns(
        pl.when((pl.col("attained_age") == 30.0) & (pl.col("calendar_year") == 2012.0))
        .then(0.0)
        .otherwise(pl.col("central_exposure"))
        .alias("central_exposure")
    )
    m = mask_surface(_surface(np.full((3, 4), 0.02)), cells)
    assert m.no_exposure[0, 1] and m.no_exposure[0, 2]


def test_without_an_exposure_column_the_page_says_it_did_not_check() -> None:
    m = mask_surface(_surface(np.full((3, 4), 0.02)), _cells(set()).drop("central_exposure"))
    assert not m.exposure_known and not m.no_exposure.any()
    assert "not checked for exposure" in m.summary()


def test_mask_on_a_real_surface_masks_what_it_counts() -> None:
    rng = np.random.default_rng(2)
    ages = np.repeat(np.arange(30.0, 40.0), 8)
    years = np.tile(np.arange(2010.0, 2018.0), 10)
    expo = rng.uniform(500, 1500, ages.size)
    deaths = rng.poisson(expo * 0.01 * np.exp(-0.02 * (years - 2010))).astype(np.float64)
    d = pl.DataFrame(
        {
            "attained_age": ages,
            "calendar_year": years,
            "central_exposure": expo,
            "death_count": deaths,
        }
    ).with_columns(pl.col("central_exposure").log().alias("log_exposure"))
    fit = gam(
        'death_count ~ s(attained_age, bs="cr", k=4) + s(calendar_year, bs="cr", k=4)'
        " + offset(log_exposure)",
        d,
        "poisson",
    )
    s = improvement_surface(fit, d)
    m = mask_surface(s, d)
    shown = m.apply(s.mi)
    assert int(np.isnan(shown).sum()) == int(m.masked.sum())


def test_nonpositive_exposure_is_counted_named_and_droppable() -> None:
    d = pl.DataFrame(
        {"central_exposure": [10.0, 0.0, -2.0, None, float("nan"), 5.0], "x": range(6)}
    )
    assert nonpositive_exposure(d) == 4
    kept = drop_nonpositive_exposure(d)
    assert kept.get_column("x").to_list() == [0, 5]
    assert nonpositive_exposure(kept) == 0
    msg = nonpositive_exposure_message(4, 6)
    assert "4 of 6 rows" in msg and "zero, negative or missing" in msg and "Drop" in msg
    assert "non-finite" not in msg  # names the cause, not the downstream symptom
    with pytest.raises(PolarisValidationError):
        nonpositive_exposure_message(0, 6)
    assert nonpositive_exposure(pl.DataFrame({"x": [1, 2]})) == 0


def test_fractional_step_does_not_lose_cells_to_float_drift() -> None:
    ages = np.array([30.0])
    years = np.array([2010.1, 2010.2, 2010.3])
    n = (1, 3)
    base = _surface(np.full(n, 0.02))
    surf = ImprovementSurface(**{**base.__dict__, "ages": ages, "years": years, "step": 0.1})
    data = pl.DataFrame(
        {
            "attained_age": [30.0] * 4,
            "calendar_year": [0.1 + 2010.0, 2010.2, 2010.3, 2010.0],
            "central_exposure": [1.0] * 4,
        }
    )
    assert not mask_surface(surf, data).no_exposure.any()
