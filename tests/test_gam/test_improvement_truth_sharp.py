"""S3 truth recovery against a SHARPLY varying improvement law (ADR-267).

Everything below is fixed BEFORE the first run (plan §5.6); a miss is a result.

Claim sentence (``sharp_truth_claim()``): the data generator computes ``MI_x(y)`` from a closed
logistic step law in age; ``improvement_surface`` computes it from the HGAM fitted to a draw of
that data; compared on MI at each (age, year) cell, on band coverage and on whether the fit
report flagged saturation. INDEPENDENT producers, closed-form truth, NOT ``mgcv`` parity.

Truth: ``log(1 - MI_x) = -(B_LO + (B_HI - B_LO) * sigmoid((x - X0) / W))``, constant in year;
MI runs 1.0% below age 45 to 4.9% above 65, with the step centred at 55 (width W = 2 ages).

The pre-registered GATED property (derived, not tuned): *an unflagged miss is a failure*. At a
basis too small for the step, the fit WILL be biased, and the claim S1 makes (ADR-265) is that
the report says so. So per fit: if ``max |MI - truth| / mi_se > 4.5`` (the D2 bound, ADR-263
amendment 1: 496 cells, a Gaussian tail of 7e-6 at 4.5), then at least one smooth block must be
flagged saturated (edf >= 0.95 x its coefficients). A miss that is NOT flagged is a result
reported as a finding, not repaired by retuning. Recovery itself (z, coverage) is MEASUREMENT,
reported but not gated: no recovery bound is asserted for a basis that cannot represent the
truth, and none is invented after seeing the numbers.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam import GamFit, gam
from polaris_re.gam.effects import improvement_surface
from polaris_re.gam.fit_report import saturated_terms

B_LO, B_HI, X0, W = 0.01, 0.05, 55.0, 2.0
AGES = np.arange(40, 71)
YEARS = np.arange(2005, 2021)
EXPOSURE = 5.0e4
Z_BOUND = 4.5
SEEDS = [20260201 + i for i in range(10)]
KS = {"default": (8, 5), "large": (20, 7)}


def formula(k_age: int, k_year: int, ti_k: tuple[int, int] | None = None) -> str:
    """The D2 default formula; ``ti_k`` sets the tensor's own margins (default: the engine's)."""
    ti = (
        'ti(attained_age, calendar_year, bs="cr")'
        if ti_k is None
        else f'ti(attained_age, calendar_year, bs="cr", k=c({ti_k[0]},{ti_k[1]}))'
    )
    return (
        f'death_count ~ s(attained_age, bs="cr", k={k_age}) + '
        f's(calendar_year, bs="cr", k={k_year}) + '
        f"{ti} + offset(log_exposure)"
    )


def b_of(age: np.ndarray) -> np.ndarray:
    """Closed form: ``-log(1 - MI_x)`` as a logistic step in age."""
    return B_LO + (B_HI - B_LO) / (1.0 + np.exp(-(age - X0) / W))


def true_mi(age: np.ndarray) -> np.ndarray:
    return 1.0 - np.exp(-b_of(age))


def q0(age: np.ndarray) -> np.ndarray:
    return 0.004 * np.exp(0.08 * (age - 45.0))


def draw(seed: int) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    a = np.repeat(AGES, YEARS.size).astype(float)
    y = np.tile(YEARS, AGES.size).astype(float)
    mu = EXPOSURE * q0(a) * np.exp(-b_of(a) * (y - 2005.0))
    return pl.DataFrame(
        {
            "attained_age": a,
            "calendar_year": y,
            "death_count": rng.poisson(mu).astype(float),
            "log_exposure": np.full(a.size, np.log(EXPOSURE)),
        }
    )


def sharp_truth_claim() -> VerificationClaim:
    return VerificationClaim(
        claim=(
            "The data generator computes MI_x(y) from a closed logistic step law in age; "
            "improvement_surface computes MI_x(y) from the HGAM fitted to a draw of that data; "
            "compared on MI at each (age, year) cell and on band coverage. Closed-form truth "
            "recovery for a sharply varying law, not mgcv parity."
        ),
        quantities=(
            ComparedQuantity(
                quantity="mi_age_year",
                left_producer="test generator closed form 1 - exp(-logistic-step b(age))",
                right_producer="polaris_re.gam.effects.improvement_surface on gam()/bam fit",
                provenance=ComparisonProvenance.INDEPENDENT,
            ),
            ComparedQuantity(
                quantity="band_coverage",
                left_producer="test generator closed form (truth inside or outside)",
                right_producer="improvement_surface delta-method band D Vp D^T",
                provenance=ComparisonProvenance.INDEPENDENT,
            ),
        ),
    )


def measure(fit: GamFit, frame: pl.DataFrame) -> dict[str, float | bool | list[str]]:
    s = improvement_surface(fit, frame)
    truth = np.repeat(true_mi(s.ages)[:, None], s.years.size, axis=1)
    return {
        "z": float(np.max(np.abs(s.mi - truth) / s.mi_se)),
        "cover": float(np.mean((s.mi_lower <= truth) & (truth <= s.mi_upper))),
        "max_err": float(np.max(np.abs(s.mi - truth))),
        "flagged": [t.label for t in saturated_terms(fit)],
    }


def test_truth_is_a_sharp_step() -> None:
    mi = true_mi(np.array([40.0, 55.0, 70.0]))
    assert mi[0] < 0.015 and mi[2] > 0.045  # 1% -> 4.9%
    assert abs(mi[1] - (1.0 - np.exp(-(B_LO + B_HI) / 2.0))) < 1.0e-12  # midpoint of the step


def test_claim_is_declared_independent_closed_form() -> None:
    claim = sharp_truth_claim()
    assert claim.is_parity_claim
    assert "not mgcv parity" in claim.claim.lower() and "closed" in claim.claim.lower()


@pytest.mark.slow
@pytest.mark.parametrize("k_label", list(KS))
@pytest.mark.xfail(
    strict=True,
    reason="ADR-267 finding: the pre-registered property FAILS (gam, default `ti` margins: "
    "unflagged misses on seeds 20260201 and 20260210, z 5.17 and 4.61 vs 4.5, at both k sets). "
    "The `ti` term (edf 3.9 of 16, 24%) carries the step and is not flagged by the 0.95 rule. "
    "Bound kept, not widened.",
)
def test_gam_unflagged_miss_is_a_failure(k_label: str) -> None:
    k_age, k_year = KS[k_label]
    for seed in SEEDS:
        frame = draw(seed)
        fit = gam(formula(k_age, k_year), frame, "poisson")
        assert fit.converged, f"gam {k_label} seed {seed} did not converge"
        m = measure(fit, frame)
        if m["z"] > Z_BOUND:
            assert m["flagged"], (
                f"gam {k_label} seed {seed}: max |MI - truth|/se = {m['z']:.2f} > {Z_BOUND} "
                "and NO smooth was flagged saturated (the report was silent about a biased fit)"
            )


@pytest.mark.slow
@pytest.mark.parametrize("k_label", list(KS))
@pytest.mark.xfail(
    strict=True,
    reason="ADR-267 finding: the pre-registered property FAILS (bam, seed 20260201, z 5.17 at "
    "both k sets, nothing flagged). The `ti` term (edf 3.9 of 16, 24%) carries the step "
    "and is not flagged by the 0.95 rule. Bound kept, not widened.",
)
def test_bam_unflagged_miss_is_a_failure(k_label: str) -> None:
    from polaris_re.core.exceptions import PolarisComputationError

    k_age, k_year = KS[k_label]
    for seed in SEEDS[:3]:
        frame = draw(seed)
        try:
            fit = gam(formula(k_age, k_year), frame, "poisson", method="fREML", discrete=True)
        except PolarisComputationError as exc:
            # A refusal is an honest outcome (ADR-266 side finding), reported, never gated.
            assert "positive definite" in str(exc)
            continue
        m = measure(fit, frame)
        if m["z"] > Z_BOUND:
            assert m["flagged"], (
                f"bam {k_label} seed {seed}: max |MI - truth|/se = {m['z']:.2f} > {Z_BOUND} "
                "and NO smooth was flagged saturated"
            )


@pytest.mark.slow
def test_posthoc_larger_ti_margins_remove_every_unflagged_miss() -> None:
    """POST-HOC (written AFTER the first run, NOT pre-registered): the follow-up hypothesis the
    finding named. With ``ti(..., k=c(12,7))`` the same ten draws show no unflagged miss and
    max |z| <= 4.5. Reported as a hypothesis check on those seeds only, not as a recovery
    guarantee."""
    for seed in SEEDS:
        frame = draw(seed)
        fit = gam(formula(8, 5, (12, 7)), frame, "poisson")
        assert fit.converged
        assert measure(fit, frame)["z"] <= Z_BOUND, f"seed {seed}"
