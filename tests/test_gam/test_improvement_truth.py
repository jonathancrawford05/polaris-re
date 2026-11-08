"""D2 truth recovery: the HGAM improvement surface against a CLOSED FORM
(ADR-263 amendment 1; tolerances derived and written BEFORE the first run).

Claim (``truth_recovery_claim()``): the generator computes ``MI_x(y)`` from its closed form;
``improvement_surface`` computes it from the fitted HGAM. INDEPENDENT producers, closed-form
truth, not ``mgcv`` parity.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.gam import GamFit, gam
from polaris_re.gam.effects import improvement_surface, truth_recovery_claim

B0, B1 = 0.02, 0.0005
AGES = np.arange(40, 71)
YEARS = np.arange(2005, 2021)
EXPOSURE = 5.0e4
FORMULA = (
    'death_count ~ s(attained_age, bs="cr", k=8) + s(calendar_year, bs="cr", k=5) '
    '+ ti(attained_age, calendar_year, bs="cr") + offset(log_exposure)'
)
SEEDS = [20260101 + i for i in range(10)]


def true_mi(age: np.ndarray) -> np.ndarray:
    """Closed form: log(1 - MI_x) = -(b0 + b1 (x - 40)), constant in year."""
    return 1.0 - np.exp(-(B0 + B1 * (age - 40.0)))


def q0(age: np.ndarray) -> np.ndarray:
    return 0.004 * np.exp(0.08 * (age - 45.0))


def draw(seed: int) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    a = np.repeat(AGES, YEARS.size).astype(float)
    y = np.tile(YEARS, AGES.size).astype(float)
    mu = EXPOSURE * q0(a) * np.exp(-(B0 + B1 * (a - 40.0)) * (y - 2005.0))
    return pl.DataFrame(
        {
            "attained_age": a,
            "calendar_year": y,
            "death_count": rng.poisson(mu).astype(float),
            "log_exposure": np.full(a.size, np.log(EXPOSURE)),
        }
    )


def truth_grid(surface_ages: np.ndarray, n_years: int) -> np.ndarray:
    return np.repeat(true_mi(surface_ages)[:, None], n_years, axis=1)


def check(fit_frame: pl.DataFrame, fit: GamFit, label: str) -> tuple[float, float]:
    s = improvement_surface(fit, fit_frame)
    truth = truth_grid(s.ages, s.years.size)
    zmax = float(np.max(np.abs(s.mi - truth) / s.mi_se))
    cover = float(np.mean((s.mi_lower <= truth) & (truth <= s.mi_upper)))
    assert zmax <= 4.5, f"{label}: max |MI - truth| / se = {zmax:.2f} > 4.5"
    assert cover >= 0.75, f"{label}: band coverage {cover:.3f} < 0.75"
    return zmax, cover


def test_claim_is_declared_independent_closed_form() -> None:
    claim = truth_recovery_claim()
    assert claim.is_parity_claim  # two producers; the claim text says it is closed-form
    assert "closed" in claim.claim.lower() and "not mgcv parity" in claim.claim.lower()


def sample_frame() -> pl.DataFrame:
    from polaris_re.dashboard.views.experience_improvement import _sample_cells

    cells = _sample_cells()
    return cells.with_columns(pl.col("central_exposure").log().alias("log_exposure"))


def test_a_builtin_sample_recovers_flat_1p5_percent() -> None:
    frame = sample_frame()
    fit = gam(
        'death_count ~ s(attained_age, bs="cr", k=8) + s(calendar_year, bs="cr", k=5) '
        "+ offset(log_exposure)",
        frame,
        "poisson",
    )
    s = improvement_surface(fit, frame)
    assert np.max(np.abs(s.mi - 0.015)) <= 1.0e-6
    assert np.all((s.mi_lower <= 0.015) & (s.mi_upper >= 0.015))


@pytest.mark.slow
def test_b_age_varying_truth_gam_ten_seeds() -> None:
    covers = []
    for seed in SEEDS:
        frame = draw(seed)
        fit = gam(FORMULA, frame, "poisson")
        assert fit.converged
        _, cover = check(frame, fit, f"gam seed {seed}")
        covers.append(cover)
    assert float(np.mean(covers)) >= 0.90, f"mean coverage {np.mean(covers):.3f}: {covers}"


@pytest.mark.slow
def test_b_age_varying_truth_bam_three_seeds() -> None:
    for seed in SEEDS[:3]:
        frame = draw(seed)
        fit = gam(FORMULA, frame, "poisson", method="fREML", discrete=True)
        check(frame, fit, f"bam seed {seed}")
