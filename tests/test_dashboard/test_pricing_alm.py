"""Dashboard Deal-Pricing ALM duration-gap tests (Asset/ALM epic, Slice 4b-3b).

Slices 4b-1 / 4b-2b threaded an optional ``deal.asset_portfolio`` +
``deal.alm_valuation_yield`` through the CLI and REST API, surfacing a dual
asset-liability duration gap (reinsurer-view headline + cedant-view) per cohort;
Slice 4b-3a added the Excel "ALM Duration Gap" sheet. The Streamlit Deal Pricing
page still ignored the asset side entirely. Slice 4b-3b threads an
``AssetPortfolio`` through ``_run_pricing_for_cohort`` so the dashboard computes
and displays the same ``DualDurationGap`` the CLI/API/Excel surfaces already do.

These tests drive ``_run_pricing_for_cohort`` directly (it does not touch session
state and, with ``show_yrt_info=False``, emits no Streamlit UI), asserting that:

* supplying an ``AssetPortfolio`` populates ``cohort.alm_duration_gap`` and that it
  is **byte-identical** to a direct ``dual_duration_gap`` call on the cohort's own
  net / ceded results (the dashboard only wires the analytics, it does not
  recompute them);
* omitting the portfolio leaves the field ``None`` (an asset-free run is
  byte-identical to the pre-slice behaviour);
* the YRT path carries only the cedant side (the ceded reserve telescopes to ~0,
  so the reinsurer side is ``None``), while a proportional coinsurance treaty
  carries both;
* an explicit ``alm_valuation_yield`` overrides the deal discount rate;
* ``DealConfig.to_dict()`` now carries the two ALM fields (the PR #111 carry-forward).
"""

import numpy as np

from polaris_re.analytics.alm import DualDurationGap, dual_duration_gap
from polaris_re.core.asset import AssetPortfolio
from polaris_re.dashboard.components.state import get_deal_config
from polaris_re.dashboard.views.pricing import CohortPricingData, _run_pricing_for_cohort
from polaris_re.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
    load_inforce,
)

# A 10-year zero-coupon bond — a clean, well-defined asset side (Macaulay
# duration == term, no coupon timing to reason about). Matches the shape used in
# the CLI ALM tests so the two surfaces price the same portfolio.
_PORTFOLIO = AssetPortfolio.model_validate(
    {
        "bonds": [
            {
                "face_value": 1_000_000.0,
                "coupon_rate": 0.0,
                "coupon_frequency": 1,
                "term_months": 120,
            }
        ]
    }
)


def _term_pipeline(treaty_type: str):
    """A minimal single-cohort TERM pipeline (no wall-clock dependence).

    Sets the dashboard deal-config ``treaty_type`` so ``run_treaty_projection``
    (which reads the centralised deal config) applies the requested treaty.
    """
    cfg = get_deal_config()
    cfg["treaty_type"] = treaty_type
    cfg["cession_pct"] = 0.90
    policies = [
        {
            "policy_id": "P1",
            "issue_age": 45,
            "attained_age": 45,
            "sex": "M",
            "smoker": False,
            "face_amount": 1_000_000.0,
            "annual_premium": 3_000.0,
            "policy_term": 20,
            "duration_inforce": 0,
            "issue_date": "2026-04-01",
            "valuation_date": "2026-04-01",
            "product_type": "TERM",
        }
    ]
    inforce = load_inforce(policies_dict=policies)
    inputs = PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.003),
        lapse=LapseConfig(),
        deal=DealConfig(product_type="TERM", treaty_type=treaty_type, projection_years=10),
    )
    inf, assumptions, config = build_pipeline(inforce, inputs)
    return inf, assumptions, config


def _price(
    treaty_type: str,
    asset_portfolio: AssetPortfolio | None,
    alm_valuation_yield: float | None = None,
) -> tuple[CohortPricingData, object]:
    inf, assumptions, config = _term_pipeline(treaty_type)
    cohort = _run_pricing_for_cohort(
        cohort_id="TERM",
        cohort_inforce=inf,
        assumption_set=assumptions,
        config=config,
        treaty_type=treaty_type,
        use_policy_cession=False,
        hurdle_rate=0.10,
        parity_label="test_alm",
        show_yrt_info=False,
        asset_portfolio=asset_portfolio,
        alm_valuation_yield=alm_valuation_yield,
    )
    return cohort, config


def test_no_asset_portfolio_leaves_gap_none() -> None:
    """Omitting the asset side leaves ``alm_duration_gap`` None (byte-identical)."""
    cohort, _ = _price("YRT", asset_portfolio=None)
    assert cohort.alm_duration_gap is None


def test_asset_portfolio_populates_dual_gap() -> None:
    """A supplied portfolio yields a non-empty DualDurationGap on the cohort."""
    cohort, _ = _price("YRT", asset_portfolio=_PORTFOLIO)
    assert isinstance(cohort.alm_duration_gap, DualDurationGap)
    assert not cohort.alm_duration_gap.is_empty


def test_gap_matches_direct_dual_duration_gap() -> None:
    """The dashboard gap is byte-identical to a direct analytics call.

    Proves the dashboard only *wires* ``dual_duration_gap`` (on the cohort's own
    net / ceded results at the deal discount rate and the reserve valuation rate),
    not a re-implementation of it.
    """
    cohort, config = _price("YRT", asset_portfolio=_PORTFOLIO)
    expected = dual_duration_gap(
        _PORTFOLIO,
        cohort.net,
        cohort.ceded,
        config.discount_rate,
        config.effective_valuation_rate,
    )
    assert cohort.alm_duration_gap == expected


def test_yrt_carries_cedant_side_only() -> None:
    """For YRT the ceded reserve is ~0, so the reinsurer side is None."""
    cohort, _ = _price("YRT", asset_portfolio=_PORTFOLIO)
    gap = cohort.alm_duration_gap
    assert isinstance(gap, DualDurationGap)
    assert gap.reinsurer is None
    assert gap.cedant is not None


def test_coinsurance_carries_both_sides() -> None:
    """A proportional treaty cedes reserves, so both sides are defined."""
    cohort, _ = _price("Coinsurance", asset_portfolio=_PORTFOLIO)
    gap = cohort.alm_duration_gap
    assert isinstance(gap, DualDurationGap)
    assert gap.reinsurer is not None
    assert gap.cedant is not None


def test_alm_valuation_yield_overrides_discount_rate() -> None:
    """An explicit valuation yield is used in place of the deal discount rate."""
    override = 0.085
    cohort, config = _price("YRT", asset_portfolio=_PORTFOLIO, alm_valuation_yield=override)
    gap = cohort.alm_duration_gap
    assert isinstance(gap, DualDurationGap)
    assert gap.cedant is not None
    # The deal discount rate (default 0.06) must NOT be the yield used.
    assert not np.isclose(config.discount_rate, override)
    np.testing.assert_allclose(gap.cedant.valuation_yield, override)


def test_deal_config_to_dict_includes_alm_fields() -> None:
    """The PR #111 carry-forward: to_dict() now surfaces the two ALM fields.

    4b-1 deliberately left ``asset_portfolio`` / ``alm_valuation_yield`` out of
    ``to_dict()`` until the dashboard consumed them; this slice adds the dashboard
    widget, so the parity surface (DEFAULTS) must carry them.
    """
    d = DealConfig().to_dict()
    assert "asset_portfolio" in d
    assert "alm_valuation_yield" in d
    assert d["asset_portfolio"] is None
    assert d["alm_valuation_yield"] is None
