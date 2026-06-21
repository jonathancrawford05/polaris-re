"""
US NAIC Life Risk-Based Capital (RBC) module — simplified factor-based v1
(ADR-098, Epic 3 Slice 1).

Implements the NAIC Life RBC component model (C-0 … C-4) with the
**covariance square-root** aggregation, the US analogue of the Canadian LICAT
module (`analytics/capital.py`). Like LICAT, this is a **factor-based
committee-stage** calculator: each component is ``factor * exposure`` at every
projection month, with conservative, documented, per-product default factors
that the caller can override. The full shock-based / asset-model calibration is
deferred to the Asset/ALM epic (CVR Tier C, scheduled after the Tier-A epics).

## Components (NAIC Life RBC)

| Code | Risk | Exposure (this v1) | Default? |
|------|------|--------------------|----------|
| C-0  | Asset risk — affiliates / off-balance-sheet | reserve | 0 (stub) |
| C-1cs| Asset risk — unaffiliated common stock | reserve | 0 (stub) |
| C-1o | Asset risk — all other (bonds etc.) | reserve | per-product |
| C-2  | Insurance risk — mortality / morbidity | **NAR** | per-product |
| C-3a | Interest-rate risk | reserve | per-product |
| C-3b | Health credit risk | reserve | 0 (stub) |
| C-3c | Market risk (separate accounts) | reserve | 0 (stub) |
| C-4a | Business risk — general | reserve | 0 (stub) |
| C-4b | Business risk — health administrative | reserve | 0 (stub) |

For a typical individual-life reinsurance book the non-zero components are
**C-1o** (asset default on the assets backing reserves), **C-2** (insurance risk
on the net amount at risk), and **C-3a** (interest-rate risk on reserves); the
others are exposed as overridable factors but default to zero.

## Aggregation — the NAIC covariance square root

The components do NOT simply sum. NAIC applies a covariance adjustment that
recognises the imperfect correlation between asset and insurance risk::

    RBC = C0 + C4a
          + sqrt[ (C1o + C3a)**2 + C1cs**2 + C2**2 + C3b**2 + C3c**2 + C4b**2 ]

C-0 and C-4a sit OUTSIDE the square root (no diversification credit); C-1o is
paired with C-3a inside the root (asset / interest-rate correlation). This is
the classic pre-2021 Life RBC formula grouping. The result is the **Company
Action Level (CAL)** required capital; the **Authorized Control Level (ACL)** is
half of it, and the RBC ratio a regulator reads is
``Total Adjusted Capital / ACL``.

## Held-capital basis

`capital_by_period` is the **Company Action Level** (the covariance result). It
is the held-capital basis fed to return-on-capital (`pv_capital`), matching the
LICAT convention that `capital_by_period` is the required amount. `RBCResult`
also exposes `authorized_control_level` (= ½ CAL) as the ratio denominator.

Sign convention: required capital is a positive, time-varying scalar; it is NOT
discounted at the hurdle rate (the time-value adjustment lives in the RoC
metric). See ADR-098 in `docs/DECISIONS.md`.
"""

from dataclasses import dataclass, field

import numpy as np
from pydantic import Field

from polaris_re.analytics.capital_base import discount_stream, strain_of
from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.policy import ProductType

__all__ = ["RBCCapital", "RBCFactors", "RBCResult"]


# ----------------------------------------------------------------------
# Default C-1o asset-default factor (applied to reserve_balance)
# ----------------------------------------------------------------------
# A blended investment-grade bond default loading. Uniform across products
# because it is a property of the backing-asset portfolio, not the liability.
# NAIC's 2021 expansion to 20 designation-based factors is asset-model work;
# 1.0% is a conservative committee-stage blend for an IG portfolio.
_C1O_DEFAULT: float = 0.010

# ----------------------------------------------------------------------
# Default C-2 insurance-risk factor (applied to NAR)
# ----------------------------------------------------------------------
# NAIC individual-life C-2 grades 0.00150 / 0.00100 / 0.00075 / 0.00060 by NAR
# tier. 0.00150 (the first-tier factor) is used as a single conservative
# committee-stage blend. ANNUITY carries no NAR mortality risk → 0.
_C2_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.00150,
    ProductType.WHOLE_LIFE: 0.00150,
    ProductType.UNIVERSAL_LIFE: 0.00150,
    ProductType.DISABILITY: 0.00150,
    ProductType.CRITICAL_ILLNESS: 0.00150,
    ProductType.ANNUITY: 0.0,
}

# ----------------------------------------------------------------------
# Default C-3a interest-rate-risk factor (applied to reserve_balance)
# ----------------------------------------------------------------------
# NAIC C-3 Phase I risk categories: low 0.0077, medium 0.0154, high 0.0231 of
# reserves. Products without cash values / surrender exposure are low-risk;
# permanent and account-value products are medium; interest-sensitive
# annuities are high.
_C3A_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.0077,
    ProductType.WHOLE_LIFE: 0.0154,
    ProductType.UNIVERSAL_LIFE: 0.0154,
    ProductType.DISABILITY: 0.0077,
    ProductType.CRITICAL_ILLNESS: 0.0077,
    ProductType.ANNUITY: 0.0231,
}


class RBCFactors(PolarisBaseModel):
    """
    NAIC Life RBC component factors.

    Defaults are committee-stage approximations. A bare `RBCFactors()` carries
    only the C-2 mortality factor (0.00150) non-zero; use
    :meth:`RBCCapital.for_product` to populate the C-1o / C-2 / C-3a schedule
    per product. C-0, C-1cs, C-3b, C-3c, C-4a, C-4b are zero stubs exposed for
    override, populated by the Asset/ALM epic.

    `c2_factor` applies to NAR; every other factor applies to reserve_balance.
    """

    c0_affiliates: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-0 affiliate / off-balance-sheet asset-risk factor (x reserve). Zero stub.",
    )
    c1cs_common_stock: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-1cs unaffiliated common-stock asset-risk factor (x reserve). Zero stub.",
    )
    c1o_other_assets: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "C-1o all-other-asset (bond) default-risk factor (x reserve). "
            "Blended investment-grade default loading."
        ),
    )
    c2_factor: float = Field(
        default=0.00150,
        ge=0.0,
        le=1.0,
        description=(
            "C-2 insurance-risk factor (x NAR). NAIC individual-life first-tier "
            "factor as a conservative committee-stage blend."
        ),
    )
    c3a_interest_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-3a interest-rate-risk factor (x reserve). NAIC C-3 Phase I category.",
    )
    c3b_health_credit: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-3b health credit-risk factor (x reserve). Zero stub for life.",
    )
    c3c_market: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-3c market-risk factor (x reserve, separate accounts). Zero stub.",
    )
    c4a_business: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-4a general business-risk factor (x reserve). Zero stub.",
    )
    c4b_health_admin: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="C-4b health administrative business-risk factor (x reserve). Zero stub.",
    )


@dataclass
class RBCResult:
    """
    NAIC Life RBC required-capital schedule produced by
    `RBCCapital.required_capital`.

    All component arrays have shape ``(T,)`` (dollars per month). `capital_by_period`
    is the **Company Action Level** RBC (the covariance-aggregated result);
    `authorized_control_level` is half of it (the RBC-ratio denominator).

    Satisfies the `CapitalSchedule` protocol (ADR-098).
    """

    projection_months: int
    c0_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c1cs_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c1o_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c2_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c3a_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c3b_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c3c_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c4a_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c4b_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    capital_by_period: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    authorized_control_level: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    initial_capital: float = 0.0
    peak_capital: float = 0.0

    def pv_capital(self, discount_rate: float) -> float:
        """PV of the Company-Action-Level capital STOCK at a flat annual rate."""
        return discount_stream(self.capital_by_period, discount_rate)

    def capital_strain(self) -> np.ndarray:
        """Period-over-period change in required capital, shape ``(T,)``."""
        return strain_of(self.capital_by_period)

    def pv_capital_strain(self, discount_rate: float) -> float:
        """PV of the capital STRAIN at a flat annual rate."""
        return discount_stream(self.capital_strain(), discount_rate)

    def rbc_ratio(self, total_adjusted_capital: float) -> float:
        """
        RBC ratio = Total Adjusted Capital / initial Authorized Control Level.

        Uses the t=0 ACL as the denominator (the issue-date ratio a committee
        reads). Raises if ACL is zero (an all-stub factor set).
        """
        if len(self.authorized_control_level) == 0 or self.authorized_control_level[0] <= 0.0:
            raise PolarisComputationError(
                "RBC ratio undefined: Authorized Control Level is zero at t=0. "
                "Populate at least one non-zero factor (e.g. via for_product)."
            )
        return float(total_adjusted_capital / self.authorized_control_level[0])


class RBCCapital(PolarisBaseModel):
    """
    Factor-based NAIC Life RBC required-capital calculator.

    Required capital at each projection month is the NAIC covariance square
    root of the C-0 … C-4 components (see module docstring). `for_product`
    selects NAIC-order factor approximations per product type.
    """

    factors: RBCFactors = Field(default_factory=RBCFactors)

    @classmethod
    def for_product(cls, product_type: ProductType) -> "RBCCapital":
        """
        Construct a calculator pre-populated with the C-1o / C-2 / C-3a default
        factors for the given product type. C-0, C-1cs, C-3b, C-3c, C-4a, C-4b
        remain zero stubs (Asset/ALM epic populates them).
        """
        c2 = _C2_DEFAULT_BY_PRODUCT.get(product_type, 0.00150)
        c3a = _C3A_DEFAULT_BY_PRODUCT.get(product_type, 0.0077)
        return cls(
            factors=RBCFactors(
                c1o_other_assets=_C1O_DEFAULT,
                c2_factor=c2,
                c3a_interest_rate=c3a,
            )
        )

    def required_capital(
        self,
        cashflows: CashFlowResult,
        nar: np.ndarray | None = None,
    ) -> RBCResult:
        """
        Compute the NAIC Life RBC required-capital schedule over the horizon.

        Args:
            cashflows: GROSS or NET basis CashFlowResult. CEDED is rejected —
                capital is held against retained business, not ceded.
            nar: Optional NAR vector of shape ``(T,)`` overriding `cashflows.nar`.
                If neither is supplied, raises.

        Returns:
            RBCResult with the nine components, the covariance-aggregated
            Company Action Level (`capital_by_period`), and the Authorized
            Control Level (½ CAL).
        """
        if cashflows.basis == "CEDED":
            raise ValueError(
                "RBCCapital does not accept CEDED basis CashFlowResult. "
                "Capital is held against retained business — pass NET or GROSS."
            )

        n = cashflows.projection_months
        nar_vec = self._resolve_nar(cashflows, nar, n)
        reserve_vec = np.asarray(cashflows.reserve_balance, dtype=np.float64)
        f = self.factors

        c0 = f.c0_affiliates * reserve_vec
        c1cs = f.c1cs_common_stock * reserve_vec
        c1o = f.c1o_other_assets * reserve_vec
        c2 = f.c2_factor * nar_vec
        c3a = f.c3a_interest_rate * reserve_vec
        c3b = f.c3b_health_credit * reserve_vec
        c3c = f.c3c_market * reserve_vec
        c4a = f.c4a_business * reserve_vec
        c4b = f.c4b_health_admin * reserve_vec

        # NAIC covariance square root: C-0 and C-4a sit outside the root; C-1o
        # pairs with C-3a inside it (asset / interest-rate correlation).
        inside = (c1o + c3a) ** 2 + c1cs**2 + c2**2 + c3b**2 + c3c**2 + c4b**2
        cal = c0 + c4a + np.sqrt(inside)
        acl = 0.5 * cal

        initial = float(cal[0]) if n > 0 else 0.0
        peak = float(cal.max()) if n > 0 else 0.0

        return RBCResult(
            projection_months=n,
            c0_component=c0.astype(np.float64),
            c1cs_component=c1cs.astype(np.float64),
            c1o_component=c1o.astype(np.float64),
            c2_component=c2.astype(np.float64),
            c3a_component=c3a.astype(np.float64),
            c3b_component=c3b.astype(np.float64),
            c3c_component=c3c.astype(np.float64),
            c4a_component=c4a.astype(np.float64),
            c4b_component=c4b.astype(np.float64),
            capital_by_period=cal.astype(np.float64),
            authorized_control_level=acl.astype(np.float64),
            initial_capital=initial,
            peak_capital=peak,
        )

    @staticmethod
    def _resolve_nar(
        cashflows: CashFlowResult, nar_override: np.ndarray | None, n: int
    ) -> np.ndarray:
        if nar_override is not None:
            if len(nar_override) != n:
                raise PolarisComputationError(
                    f"NAR override length {len(nar_override)} does not match projection length {n}."
                )
            return np.asarray(nar_override, dtype=np.float64)
        if cashflows.nar is None:
            raise PolarisComputationError(
                "RBCCapital.required_capital requires NAR. Pass `nar=` explicitly "
                "or use a CashFlowResult that already has `nar` populated "
                "(e.g. post-YRTTreaty)."
            )
        return np.asarray(cashflows.nar, dtype=np.float64)
