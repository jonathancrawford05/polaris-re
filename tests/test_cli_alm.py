"""Tests for the CLI asset-liability duration-gap surface (Asset/ALM Slice 4b).

Covers the ``deal.asset_portfolio`` config input wired through ``polaris price``:
the duration-gap block is emitted per cohort (and at the top level for a
single-cohort run) only when an ``AssetPortfolio`` is supplied, and is purely
additive — the priced numbers are byte-identical to a run without it.

The asset side of the gap is deterministic given the portfolio and the
valuation yield (independent of the liability), so the closed-form checks anchor
on a single zero-coupon bond: its Macaulay duration is its term in years and its
modified duration is ``Macaulay / (1 + y)``.

Slice 4b-2a switched the liability from the gross-premium benefit-outgo stream
to the **reserve-backed** run-off stream (Option B, ADR-113), whose present value
ties to the held reserve. Both golden cohorts (TERM and WHOLE_LIFE) carry a
positive reserve, so both now carry a duration-gap block — the graceful skip is
now a true edge case (a non-positive opening reserve, e.g. a brand-new block).
"""

import json
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polaris_re.cli import _build_pipeline_from_config, app
from polaris_re.core.exceptions import PolarisValidationError

runner = CliRunner()

# Golden fixtures (see tests/qa/conftest.py), relative to the repo root (the
# pytest invocation cwd). The golden block is mixed TERM + WHOLE_LIFE.
GOLDEN_DIR = Path("data/qa")
GOLDEN_CSV = GOLDEN_DIR / "golden_inforce.csv"
GOLDEN_CONFIG_FLAT = GOLDEN_DIR / "golden_config_flat.json"

# A single 10-year zero-coupon bond carried at par. Its duration is independent
# of the liability, so the asset-side measures are exact closed forms.
_ZERO_BOND_PORTFOLIO = {
    "bonds": [
        {
            "face_value": 1_000_000.0,
            "coupon_rate": 0.0,
            "coupon_frequency": 1,
            "term_months": 120,
            "bond_id": "ZERO-10Y",
        }
    ],
    "portfolio_id": "TEST-ALM",
}


def _config_with_asset_portfolio(
    tmp_path: Path,
    *,
    portfolio: dict | None = _ZERO_BOND_PORTFOLIO,  # type: ignore[type-arg]
    valuation_yield: float | None = None,
) -> Path:
    """Write a copy of the golden flat config with an optional asset portfolio."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = json.loads(GOLDEN_CONFIG_FLAT.read_text())
    deal = raw.setdefault("deal", {})
    if portfolio is not None:
        deal["asset_portfolio"] = portfolio
    if valuation_yield is not None:
        deal["alm_valuation_yield"] = valuation_yield
    cfg_path = tmp_path / "alm_config.json"
    cfg_path.write_text(json.dumps(raw))
    return cfg_path


def _run_price(tmp_path: Path, config_path: Path) -> dict:  # type: ignore[type-arg]
    """Invoke ``polaris price`` on a config; return the JSON payload."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "result.json"
    result = runner.invoke(
        app,
        [
            "price",
            "--config",
            str(config_path),
            "--inforce",
            str(GOLDEN_CSV),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
    return json.loads(out.read_text())  # type: ignore[no-any-return]


# Closed-form expectations for the 10-year zero at the default 6% discount rate.
_DISCOUNT_RATE = 0.06
_EXPECTED_ASSET_MACAULAY = 10.0  # single cash flow at month 120 → 10 years
_EXPECTED_ASSET_MODIFIED = 10.0 / (1.0 + _DISCOUNT_RATE)
_EXPECTED_ASSET_MV = 1_000_000.0 * (1.0 + _DISCOUNT_RATE) ** (-10.0)


class TestConfigParsing:
    """The asset portfolio + valuation yield round-trip through DealConfig."""

    def test_asset_portfolio_parsed_into_deal_config(self, tmp_path: Path) -> None:
        cfg = _config_with_asset_portfolio(tmp_path, valuation_yield=0.05)
        _inforce, _assumptions, _config, inputs = _build_pipeline_from_config(
            cfg, inforce_path=GOLDEN_CSV
        )
        assert inputs.deal.asset_portfolio is not None
        assert len(inputs.deal.asset_portfolio.bonds) == 1
        assert inputs.deal.asset_portfolio.bonds[0].term_months == 120
        np.testing.assert_allclose(inputs.deal.alm_valuation_yield, 0.05)

    def test_no_asset_portfolio_leaves_fields_none(self, tmp_path: Path) -> None:
        cfg = _config_with_asset_portfolio(tmp_path, portfolio=None)
        _inforce, _assumptions, _config, inputs = _build_pipeline_from_config(
            cfg, inforce_path=GOLDEN_CSV
        )
        assert inputs.deal.asset_portfolio is None
        assert inputs.deal.alm_valuation_yield is None

    def test_malformed_bond_rejected_at_parse(self, tmp_path: Path) -> None:
        """A bond with an invalid coupon frequency raises before pricing."""
        bad = {
            "bonds": [
                {
                    "face_value": 1_000.0,
                    "coupon_rate": 0.04,
                    "coupon_frequency": 5,
                    "term_months": 60,
                }
            ]
        }
        cfg = _config_with_asset_portfolio(tmp_path, portfolio=bad)
        with pytest.raises((PolarisValidationError, ValueError)):
            _build_pipeline_from_config(cfg)


def _gaps_by_product(payload: dict) -> dict:  # type: ignore[type-arg]
    """Map product_type → duration-gap block for cohorts that have one."""
    return {
        c["product_type"]: c["alm_duration_gap"]
        for c in payload["cohorts"]
        if "alm_duration_gap" in c
    }


class TestDurationGapOutput:
    """The duration-gap block appears per cohort with closed-form asset measures.

    Both golden cohorts carry a positive reserve, so the reserve-backed liability
    discounts to a positive PV (= the held reserve) and both carry a block.
    """

    def test_term_cohort_has_duration_gap(self, tmp_path: Path) -> None:
        gaps = _gaps_by_product(_run_price(tmp_path, _config_with_asset_portfolio(tmp_path)))
        assert "TERM" in gaps

    def test_whole_life_cohort_has_duration_gap(self, tmp_path: Path) -> None:
        """The reserve-backed stream (Option B) makes the WHOLE_LIFE block defined.

        Under the old gross-premium stream this cohort was skipped (its
        gross-premium outgo discounts to a non-positive PV). Backed by the held
        reserve, its liability PV is the reserve (positive), so it carries a
        block — the central win of Slice 4b-2a.
        """
        gaps = _gaps_by_product(_run_price(tmp_path, _config_with_asset_portfolio(tmp_path)))
        assert "WHOLE_LIFE" in gaps
        assert gaps["WHOLE_LIFE"]["liability_present_value"] > 0.0

    def test_asset_measures_are_closed_form(self, tmp_path: Path) -> None:
        gaps = _gaps_by_product(_run_price(tmp_path, _config_with_asset_portfolio(tmp_path)))
        assert gaps
        for gap in gaps.values():
            # Asset side is independent of the liability — exact for the zero.
            np.testing.assert_allclose(gap["asset_macaulay_duration"], _EXPECTED_ASSET_MACAULAY)
            np.testing.assert_allclose(gap["asset_modified_duration"], _EXPECTED_ASSET_MODIFIED)
            np.testing.assert_allclose(gap["asset_market_value"], _EXPECTED_ASSET_MV, rtol=1e-9)

    def test_default_valuation_yield_is_discount_rate(self, tmp_path: Path) -> None:
        gaps = _gaps_by_product(_run_price(tmp_path, _config_with_asset_portfolio(tmp_path)))
        assert gaps
        for gap in gaps.values():
            np.testing.assert_allclose(gap["valuation_yield"], _DISCOUNT_RATE)

    def test_liability_side_and_gap_identities(self, tmp_path: Path) -> None:
        gaps = _gaps_by_product(_run_price(tmp_path, _config_with_asset_portfolio(tmp_path)))
        assert gaps
        for gap in gaps.values():
            assert gap["liability_present_value"] > 0.0
            assert gap["liability_macaulay_duration"] > 0.0
            # The headline gap is asset minus liability modified duration.
            np.testing.assert_allclose(
                gap["duration_gap"],
                gap["asset_modified_duration"] - gap["liability_modified_duration"],
            )
            np.testing.assert_allclose(
                gap["dollar_duration_gap"],
                gap["dollar_duration_asset"] - gap["dollar_duration_liability"],
            )


class TestValuationYieldOverride:
    """An explicit alm_valuation_yield overrides the discount-rate default."""

    def test_override_changes_valuation_yield_and_measures(self, tmp_path: Path) -> None:
        override = 0.08
        payload = _run_price(
            tmp_path, _config_with_asset_portfolio(tmp_path, valuation_yield=override)
        )
        expected_modified = 10.0 / (1.0 + override)
        gaps = [c["alm_duration_gap"] for c in payload["cohorts"] if "alm_duration_gap" in c]
        assert gaps, "expected at least one cohort with a duration-gap block"
        for gap in gaps:
            np.testing.assert_allclose(gap["valuation_yield"], override)
            np.testing.assert_allclose(gap["asset_modified_duration"], expected_modified)


class TestGracefulSkipNeverAborts:
    """A degenerate liability never aborts pricing.

    The non-positive-opening-reserve skip trigger is exercised deterministically
    at the analytics boundary in ``tests/test_analytics/test_alm.py``
    (``test_duration_gap_on_nonpositive_reserve_raises``), which pins the
    ``PolarisComputationError`` the CLI catches. Here we only assert the
    higher-level property: a real price run always succeeds and emits priced
    numbers, whether or not the additive block is present.
    """

    def test_price_run_succeeds_and_prices_every_cohort(self, tmp_path: Path) -> None:
        payload = _run_price(tmp_path, _config_with_asset_portfolio(tmp_path))
        assert payload["cohorts"]
        for cohort in payload["cohorts"]:
            assert "cedant" in cohort
            assert "reinsurer" in cohort


class TestPurelyAdditive:
    """Supplying an asset portfolio does not move any priced number."""

    def test_no_portfolio_omits_block(self, tmp_path: Path) -> None:
        payload = _run_price(tmp_path, _config_with_asset_portfolio(tmp_path, portfolio=None))
        for cohort in payload["cohorts"]:
            assert "alm_duration_gap" not in cohort
        assert "alm_duration_gap" not in payload

    def test_priced_numbers_byte_identical(self, tmp_path: Path) -> None:
        """Cedant/reinsurer/summary blocks match with and without the asset side."""
        without = _run_price(
            tmp_path / "a", _config_with_asset_portfolio(tmp_path / "a", portfolio=None)
        )
        with_assets = _run_price(tmp_path / "b", _config_with_asset_portfolio(tmp_path / "b"))
        # Strip the additive block, then the payloads must be identical.
        for cohort in with_assets["cohorts"]:
            cohort.pop("alm_duration_gap", None)
        with_assets.pop("alm_duration_gap", None)
        assert without == with_assets


class TestSingleCohortTopLevelMirror:
    """A single-product run mirrors the duration gap at the top level."""

    def _term_only_csv(self, tmp_path: Path) -> Path:
        """A one-policy TERM inforce block (so n_cohorts == 1)."""
        header = (
            "policy_id,issue_age,attained_age,sex,smoker_status,underwriting_class,"
            "face_amount,annual_premium,product_type,policy_term,duration_inforce,"
            "reinsurance_cession_pct,issue_date,valuation_date\n"
        )
        row = "T-1,30,35,M,NS,PREFERRED,500000.00,300.00,TERM,20,60,,2021-04-01,2026-04-01\n"
        csv_path = tmp_path / "term_only.csv"
        csv_path.write_text(header + row)
        return csv_path

    def test_single_cohort_top_level_block(self, tmp_path: Path) -> None:
        cfg = _config_with_asset_portfolio(tmp_path)
        out = tmp_path / "result.json"
        result = runner.invoke(
            app,
            [
                "price",
                "--config",
                str(cfg),
                "--inforce",
                str(self._term_only_csv(tmp_path)),
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, f"CLI failed:\n{result.stdout}"
        payload = json.loads(out.read_text())
        assert payload["summary"]["n_cohorts"] == 1
        assert "alm_duration_gap" in payload
        np.testing.assert_allclose(
            payload["alm_duration_gap"]["asset_modified_duration"], _EXPECTED_ASSET_MODIFIED
        )
