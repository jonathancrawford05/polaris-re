"""
LICAT regulatory capital module — simplified factor-based v1.

Implements the C-1 / C-2 / C-3 component model used in OSFI's Life
Insurance Capital Adequacy Test (LICAT). The C-2 (insurance risk)
component is split into three factor-based sub-components:

- **C-2 mortality risk** — `factor * NAR` (ADR-047, Slice 1).
- **C-2 lapse risk** — `factor * reserve_balance` (ADR-065).
- **C-2 morbidity risk** — `factor * NAR` for DI / CI products
  (ADR-065).

**C-1 (asset default)** and **C-3 (interest-rate)** default to zero so that
existing capital surfaces (`for_product`, `for_product_extended`) remain
byte-identical. Callers that need a committee-screening capital number
that includes a placeholder for asset and rate risk can opt in via
`LICATCapital.for_product_interim(product_type)`, which populates all
five factors with conservative defaults (ADR-072). Phase 5.4 will
replace these placeholders with a shock-based asset / ALM model.

Sign convention: required capital is a positive, time-varying scalar that
the reinsurer must hold against the business. It is NOT discounted at the
hurdle rate — the time-value adjustment lives in the return-on-capital
metric (`ProfitTester.run_with_capital`).

See ADR-047 / ADR-065 / ADR-072 in `docs/DECISIONS.md` for OSFI
calibration notes and the factor approximations used as defaults.
"""

from dataclasses import dataclass, field

import numpy as np
from pydantic import Field

from polaris_re.core.base import PolarisBaseModel
from polaris_re.core.cashflow import CashFlowResult
from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.policy import ProductType

__all__ = ["CapitalResult", "LICATCapital", "LICATFactors"]


# ----------------------------------------------------------------------
# Default C-2 mortality factors per product type (ADR-047)
# ----------------------------------------------------------------------
# These approximate the implicit factors derived from OSFI's shock-based
# 2024 LICAT mortality risk framework when applied to typical individual
# life books. Users should override via `LICATFactors(c2_mortality_factor=...)`
# when calibration data is available; the defaults are intentionally
# conservative for committee-stage screening.
_C2_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.15,
    ProductType.WHOLE_LIFE: 0.10,
    ProductType.UNIVERSAL_LIFE: 0.08,
    ProductType.DISABILITY: 0.05,
    ProductType.CRITICAL_ILLNESS: 0.05,
    ProductType.ANNUITY: 0.03,
}

# ----------------------------------------------------------------------
# Default C-2 lapse / morbidity factors per product type (ADR-065)
# ----------------------------------------------------------------------
# Lapse factor applies to `reserve_balance` and approximates the implicit
# mass-lapse shock from OSFI's 2024 LICAT lapse risk framework. Morbidity
# factor applies to NAR and is non-zero only for products with explicit
# morbidity coverage (DI / CI). For mortality-only products (TERM / WL /
# UL / ANN) the morbidity factor defaults to zero. Both factors are
# placeholder approximations for committee-stage screening; calibration
# against shock-based modelling is Phase 5.4 work.
_C2_LAPSE_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.05,
    ProductType.WHOLE_LIFE: 0.03,
    ProductType.UNIVERSAL_LIFE: 0.04,
    ProductType.DISABILITY: 0.02,
    ProductType.CRITICAL_ILLNESS: 0.02,
    ProductType.ANNUITY: 0.06,
}

_C2_MORBIDITY_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.00,
    ProductType.WHOLE_LIFE: 0.00,
    ProductType.UNIVERSAL_LIFE: 0.00,
    ProductType.DISABILITY: 0.15,
    ProductType.CRITICAL_ILLNESS: 0.12,
    ProductType.ANNUITY: 0.00,
}

# ----------------------------------------------------------------------
# Interim C-1 / C-3 factors per product type (ADR-072)
# ----------------------------------------------------------------------
# Conservative committee-stage placeholders that make the LICAT capital
# number less visibly incomplete before the Phase 5.4 shock-based asset /
# ALM model lands. C-1 is uniform at 0.5% of reserves — an investment-
# grade portfolio default-risk loading independent of liability product.
# C-3 scales with effective reserve duration: TERM has short reserves,
# WL longer, UL has crediting-rate exposure, and ANNUITY has the longest
# duration and the largest interest-rate sensitivity. These factors are
# only applied when the caller opts into `for_product_interim`; the
# pre-existing `for_product` / `for_product_extended` constructors keep
# C-1 / C-3 at zero.
_C1_INTERIM_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.005,
    ProductType.WHOLE_LIFE: 0.005,
    ProductType.UNIVERSAL_LIFE: 0.005,
    ProductType.DISABILITY: 0.005,
    ProductType.CRITICAL_ILLNESS: 0.005,
    ProductType.ANNUITY: 0.005,
}

_C3_INTERIM_DEFAULT_BY_PRODUCT: dict[ProductType, float] = {
    ProductType.TERM: 0.005,
    ProductType.WHOLE_LIFE: 0.010,
    ProductType.UNIVERSAL_LIFE: 0.015,
    ProductType.DISABILITY: 0.005,
    ProductType.CRITICAL_ILLNESS: 0.005,
    ProductType.ANNUITY: 0.020,
}


class LICATFactors(PolarisBaseModel):
    """
    LICAT C-1 / C-2 / C-3 risk factors.

    C-2 is split into three insurance-risk sub-factors (mortality, lapse,
    morbidity). Defaults preserve backward compatibility: the mortality
    factor defaults to 0.10 for an individual life book and the lapse /
    morbidity factors default to zero so a bare `LICATFactors()` produces
    the same capital number as before ADR-065. C-1 and C-3 are zero stubs
    populated by Phase 5.4.
    """

    c2_mortality_factor: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to NAR to produce required C-2 mortality capital. "
            "Approximates the OSFI 2024 LICAT mortality shock for an individual life book."
        ),
    )
    c2_lapse_factor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to reserve_balance to produce required C-2 lapse capital. "
            "Approximates the OSFI 2024 LICAT mass-lapse shock; zero by default to preserve "
            "pre-ADR-065 behaviour. See ADR-065."
        ),
    )
    c2_morbidity_factor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to NAR to produce required C-2 morbidity capital. "
            "Non-zero only for products with morbidity coverage (DI / CI); zero by default "
            "for mortality-only products and to preserve pre-ADR-065 behaviour. See ADR-065."
        ),
    )
    c1_asset_default: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to reserve_balance to produce required C-1 asset-default "
            "capital. Zero stub in Slice 1 — populated by Phase 5.4 asset model."
        ),
    )
    c3_interest_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Multiplier applied to reserve_balance to produce required C-3 interest-rate "
            "capital. Zero stub in Slice 1 — populated by Phase 5.4 asset model."
        ),
    )


@dataclass
class CapitalResult:
    """
    Required-capital schedule produced by `LICATCapital.required_capital`.

    All array fields have shape `(T,)` where `T = projection_months`.
    Values are in dollars at each monthly step.

    `c2_component` is the C-2 mortality sub-component (preserved name for
    backward compatibility). `c2_lapse_component` and
    `c2_morbidity_component` are the additional C-2 insurance-risk
    sub-components introduced in ADR-065. `c2_insurance_risk` is the
    aggregate of all three.
    """

    projection_months: int
    c1_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c2_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c2_lapse_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    c2_morbidity_component: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.float64)
    )
    c3_component: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    capital_by_period: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    initial_capital: float = 0.0
    peak_capital: float = 0.0

    @property
    def c2_insurance_risk(self) -> np.ndarray:
        """Aggregate C-2 insurance risk = mortality + lapse + morbidity."""
        return self.c2_component + self.c2_lapse_component + self.c2_morbidity_component

    def pv_capital(self, discount_rate: float) -> float:
        """
        Present value of the capital-held stream at a flat annual rate.

        Discounts each monthly capital balance back to t=0. This is the
        STOCK measure of capital usage and is the default denominator of
        return-on-capital (see ADR-048).
        """
        n = len(self.capital_by_period)
        if n == 0:
            return 0.0
        v = (1.0 + discount_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, n + 1, dtype=np.float64)
        return float(np.dot(self.capital_by_period, discount_factors))

    def capital_strain(self) -> np.ndarray:
        """
        Period-over-period change in required capital, shape `(T,)`.

        `strain_t = capital_t - capital_{t-1}` with `capital_{-1} = 0`.
        Positive strain represents new capital that must be injected at
        period `t`; negative strain represents capital that is released.

        Note: this does NOT include a terminal release of the residual
        capital balance at the end of the projection; the IRR helper in
        `ProfitTester.run_with_capital` adds that adjustment when
        constructing the distributable cash flow.
        """
        n = len(self.capital_by_period)
        if n == 0:
            return np.array([], dtype=np.float64)
        strain = np.empty(n, dtype=np.float64)
        strain[0] = self.capital_by_period[0]
        if n > 1:
            strain[1:] = self.capital_by_period[1:] - self.capital_by_period[:-1]
        return strain

    def pv_capital_strain(self, discount_rate: float) -> float:
        """
        Present value of the capital-strain stream at a flat annual rate.

        Strain is the period-over-period change in required capital
        (`capital_t - capital_{t-1}`, with `capital_{-1} = 0`). For a
        flat capital schedule this collapses to `capital_0 * v` (one
        initial injection, no further movements).

        See ADR-048: PV(strain) is the alternative RoC denominator to
        PV(capital). Slice 2 defaults to PV(capital) but exposes the
        strain measure for callers that prefer the incremental view.
        """
        strain = self.capital_strain()
        n = len(strain)
        if n == 0:
            return 0.0
        v = (1.0 + discount_rate) ** (-1.0 / 12.0)
        discount_factors = v ** np.arange(1, n + 1, dtype=np.float64)
        return float(np.dot(strain, discount_factors))


class LICATCapital(PolarisBaseModel):
    """
    Factor-based LICAT required-capital calculator.

    Required capital at each projection month is::

        capital_t = c1_factor * reserve_t + c2_factor * NAR_t + c3_factor * reserve_t

    where NAR_t comes from `cashflows.nar` (populated by YRT treaty
    application) or an explicit override. The `for_product` constructor
    selects an OSFI-published-factor approximation per product type.
    """

    factors: LICATFactors = Field(default_factory=LICATFactors)

    @classmethod
    def for_product(cls, product_type: ProductType) -> "LICATCapital":
        """
        Construct a calculator pre-populated with the default C-2 mortality
        factor for the given product type. Lapse / morbidity factors and
        C-1 / C-3 remain zero (pre-ADR-065 behaviour, preserved for backward
        compatibility). Use :meth:`for_product_extended` to populate all
        three C-2 sub-factors.
        """
        c2 = _C2_DEFAULT_BY_PRODUCT.get(product_type, 0.10)
        return cls(factors=LICATFactors(c2_mortality_factor=c2))

    @classmethod
    def for_product_extended(cls, product_type: ProductType) -> "LICATCapital":
        """
        Construct a calculator pre-populated with all three C-2 sub-factors
        (mortality, lapse, morbidity) per product type. See ADR-065 for the
        factor calibration and the default schedule. C-1 and C-3 remain
        zero pending Phase 5.4.
        """
        mortality = _C2_DEFAULT_BY_PRODUCT.get(product_type, 0.10)
        lapse = _C2_LAPSE_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        morbidity = _C2_MORBIDITY_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        return cls(
            factors=LICATFactors(
                c2_mortality_factor=mortality,
                c2_lapse_factor=lapse,
                c2_morbidity_factor=morbidity,
            )
        )

    @classmethod
    def for_product_interim(cls, product_type: ProductType) -> "LICATCapital":
        """
        Construct a calculator pre-populated with all five LICAT factors
        using interim committee-stage placeholders.

        Extends `for_product_extended` by adding non-zero C-1 (asset
        default) and C-3 (interest-rate) factors so the capital number
        carries a placeholder for asset and rate risk pending the Phase
        5.4 shock-based asset / ALM model. The C-2 schedule is identical
        to `for_product_extended`. See ADR-072 for the calibration
        rationale and the default schedule.
        """
        mortality = _C2_DEFAULT_BY_PRODUCT.get(product_type, 0.10)
        lapse = _C2_LAPSE_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        morbidity = _C2_MORBIDITY_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        c1 = _C1_INTERIM_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        c3 = _C3_INTERIM_DEFAULT_BY_PRODUCT.get(product_type, 0.0)
        return cls(
            factors=LICATFactors(
                c2_mortality_factor=mortality,
                c2_lapse_factor=lapse,
                c2_morbidity_factor=morbidity,
                c1_asset_default=c1,
                c3_interest_rate=c3,
            )
        )

    def required_capital(
        self,
        cashflows: CashFlowResult,
        nar: np.ndarray | None = None,
    ) -> CapitalResult:
        """
        Compute the required-capital schedule over the projection horizon.

        Args:
            cashflows: GROSS or NET basis CashFlowResult. CEDED is rejected
                because capital is held against business retained, not ceded.
            nar: Optional NAR vector of shape `(T,)`. If supplied, this
                overrides `cashflows.nar`. If neither is supplied, raises.

        Returns:
            CapitalResult with C-1, C-2 (mortality + lapse + morbidity),
            and C-3 components plus the aggregate.
        """
        if cashflows.basis == "CEDED":
            raise ValueError(
                "LICATCapital does not accept CEDED basis CashFlowResult. "
                "Capital is held against retained business — pass NET or GROSS."
            )

        n = cashflows.projection_months
        nar_vec = self._resolve_nar(cashflows, nar, n)
        reserve_vec = np.asarray(cashflows.reserve_balance, dtype=np.float64)

        c1 = self.factors.c1_asset_default * reserve_vec
        c2_mortality = self.factors.c2_mortality_factor * nar_vec
        c2_lapse = self.factors.c2_lapse_factor * reserve_vec
        c2_morbidity = self.factors.c2_morbidity_factor * nar_vec
        c3 = self.factors.c3_interest_rate * reserve_vec
        total = c1 + c2_mortality + c2_lapse + c2_morbidity + c3

        initial = float(total[0]) if n > 0 else 0.0
        peak = float(total.max()) if n > 0 else 0.0

        return CapitalResult(
            projection_months=n,
            c1_component=c1.astype(np.float64),
            c2_component=c2_mortality.astype(np.float64),
            c2_lapse_component=c2_lapse.astype(np.float64),
            c2_morbidity_component=c2_morbidity.astype(np.float64),
            c3_component=c3.astype(np.float64),
            capital_by_period=total.astype(np.float64),
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
                "LICATCapital.required_capital requires NAR. Pass `nar=` "
                "explicitly or use a CashFlowResult that already has `nar` "
                "populated (e.g. post-YRTTreaty)."
            )
        return np.asarray(cashflows.nar, dtype=np.float64)
