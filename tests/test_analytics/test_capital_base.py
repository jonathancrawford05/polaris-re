"""Tests for the shared capital-model resolver (`capital_model_for`, ADR-101).

The resolver is the single registry behind the CLI ``--capital`` flag and the
API ``capital_model`` field, so a jurisdiction is added in exactly one place and
both surfaces stay in lock-step. These tests lock the registry contract: every
supported id resolves to a calculator satisfying ``CapitalModel``, the id is
case-insensitive and whitespace-tolerant, and unknown ids raise with a message
that lists the supported ids.
"""

import pytest

from polaris_re.analytics.capital import LICATCapital
from polaris_re.analytics.capital_base import (
    CAPITAL_MODEL_LABELS,
    SUPPORTED_CAPITAL_MODELS,
    CapitalModel,
    capital_model_for,
    capital_model_label,
)
from polaris_re.analytics.rbc import RBCCapital
from polaris_re.analytics.solvency2 import SolvencyIICapital
from polaris_re.core.policy import ProductType


class TestCapitalModelRegistry:
    """The supported-jurisdiction registry behind the CLI / API selector."""

    def test_supported_models_are_the_three_jurisdictions(self):
        """The registry is exactly LICAT (CA), RBC (US), Solvency II (EU)."""
        assert SUPPORTED_CAPITAL_MODELS == ("licat", "rbc", "solvency2")

    @pytest.mark.parametrize(
        ("model_id", "expected_cls"),
        [
            ("licat", LICATCapital),
            ("rbc", RBCCapital),
            ("solvency2", SolvencyIICapital),
        ],
    )
    def test_resolves_each_id_to_its_calculator(self, model_id, expected_cls):
        """Each id maps to the matching calculator class, pre-populated factors."""
        model = capital_model_for(model_id, ProductType.TERM)
        assert isinstance(model, expected_cls)

    @pytest.mark.parametrize("model_id", list(SUPPORTED_CAPITAL_MODELS))
    def test_every_supported_id_satisfies_the_protocol(self, model_id):
        """Every resolved calculator satisfies the structural CapitalModel protocol."""
        model = capital_model_for(model_id, ProductType.TERM)
        assert isinstance(model, CapitalModel)

    @pytest.mark.parametrize("raw", [" LICAT", "Rbc ", "SOLVENCY2", "  solvency2  "])
    def test_id_is_case_insensitive_and_whitespace_tolerant(self, raw):
        """Normalisation mirrors the CLI/API: strip + lower-case before lookup."""
        # Should not raise — each normalises to a supported id.
        model = capital_model_for(raw, ProductType.TERM)
        assert isinstance(model, CapitalModel)

    def test_unknown_id_raises_with_supported_list(self):
        """An unknown id raises ValueError naming the supported ids."""
        with pytest.raises(ValueError, match="Unknown capital model"):
            capital_model_for("bogus", ProductType.TERM)
        # The message lists every supported id so callers can surface it verbatim.
        try:
            capital_model_for("bogus", ProductType.TERM)
        except ValueError as exc:
            for supported in SUPPORTED_CAPITAL_MODELS:
                assert supported in str(exc)

    def test_product_type_drives_factor_defaults(self):
        """Different product types yield different per-product factor sets."""
        term = capital_model_for("rbc", ProductType.TERM)
        whole = capital_model_for("rbc", ProductType.WHOLE_LIFE)
        # The for_product constructor specialises factors per product, so the
        # two calculators are not factor-identical.
        assert term.factors != whole.factors


class TestLicatResolverUsesInterimFactors:
    """The LICAT resolver exposes the built C-1/C-3 factors (ADR-160, B1).

    ``capital_model_for("licat", …)`` resolves to the interim committee-stage
    screening basis (`LICATCapital.for_product_interim`) — the same basis the
    portfolio roll-up (`dashboard/views/portfolio.py`) already uses — rather than
    the mortality-only `for_product` basis. This closes the single-deal-vs-
    portfolio inconsistency and brings LICAT in line with US RBC / EU Solvency II,
    whose `for_product` constructors already load asset/interest components.
    """

    @pytest.mark.parametrize("product_type", list(ProductType))
    def test_licat_resolver_matches_for_product_interim(self, product_type):
        """Every product resolves to the exact `for_product_interim` factor set."""
        resolved = capital_model_for("licat", product_type)
        interim = LICATCapital.for_product_interim(product_type)
        assert isinstance(resolved, LICATCapital)
        assert resolved.factors == interim.factors

    @pytest.mark.parametrize("product_type", list(ProductType))
    def test_licat_resolver_carries_non_zero_c1(self, product_type):
        """The built C-1 asset-default factor is now surfaced on the priced path."""
        resolved = capital_model_for("licat", product_type)
        assert resolved.factors.c1_asset_default > 0.0

    @pytest.mark.parametrize(
        ("product_type", "expected_c3"),
        [
            (ProductType.TERM, 0.005),
            (ProductType.WHOLE_LIFE, 0.010),
            (ProductType.UNIVERSAL_LIFE, 0.015),
            (ProductType.ANNUITY, 0.020),
        ],
    )
    def test_licat_resolver_c3_scales_with_reserve_duration(self, product_type, expected_c3):
        """C-3 scales with effective reserve duration (TERM short … ANNUITY long)."""
        resolved = capital_model_for("licat", product_type)
        assert resolved.factors.c3_interest_rate == pytest.approx(expected_c3)

    def test_licat_resolver_consistent_with_portfolio_path(self):
        """The single-deal resolver and the portfolio roll-up agree on LICAT factors.

        `dashboard/views/portfolio.py` constructs `for_product_interim` directly;
        the resolver behind the single-deal CLI/API/dashboard price must now use
        the identical basis so a deal's stand-alone capital equals its
        contribution basis inside a portfolio.
        """
        for product_type in ProductType:
            resolved = capital_model_for("licat", product_type)
            portfolio_basis = LICATCapital.for_product_interim(product_type)
            assert resolved.factors == portfolio_basis.factors

    def test_licat_resolver_capital_exceeds_mortality_only_basis(self):
        """The priced-path required capital strictly exceeds the old mortality-only basis.

        Closed-form sanity: the interim basis adds C-2 lapse (0.05 * reserve for
        TERM) plus C-1 (0.005 * reserve) and C-3 (0.005 * reserve) on top of the
        C-2 mortality component, so peak required capital must be strictly larger
        than the pre-B1 `for_product` basis on an identical cash-flow stream.
        """
        from datetime import date

        import numpy as np

        from polaris_re.core.cashflow import CashFlowResult

        months = 12
        reserve = np.full(months, 1_000_000.0, dtype=np.float64)
        nar = np.full(months, 500_000.0, dtype=np.float64)
        cashflows = CashFlowResult(
            run_id="b1-closed-form",
            valuation_date=date(2025, 1, 1),
            basis="GROSS",
            assumption_set_version="test-v1",
            product_type="TERM",
            projection_months=months,
            reserve_balance=reserve,
        )

        old_basis = LICATCapital.for_product(ProductType.TERM)
        new_basis = capital_model_for("licat", ProductType.TERM)
        old_cap = old_basis.required_capital(cashflows, nar=nar)
        new_cap = new_basis.required_capital(cashflows, nar=nar)
        assert new_cap.peak_capital > old_cap.peak_capital


class TestCapitalModelLabels:
    """The shared display labels behind the dashboard tiles / Excel header (ADR-102)."""

    def test_labels_cover_every_supported_id(self):
        """Every selectable jurisdiction has a presentation label."""
        assert set(CAPITAL_MODEL_LABELS) == set(SUPPORTED_CAPITAL_MODELS)

    @pytest.mark.parametrize(
        ("model_id", "expected"),
        [
            ("licat", "LICAT (Canada)"),
            ("rbc", "US RBC"),
            ("solvency2", "EU Solvency II"),
            (" Solvency2 ", "EU Solvency II"),  # normalised before lookup
        ],
    )
    def test_label_for_known_id(self, model_id, expected):
        assert capital_model_label(model_id) == expected

    def test_none_defaults_to_licat(self):
        """An un-tagged schedule is LICAT — every pre-ADR-098 capital run was."""
        assert capital_model_label(None) == "LICAT (Canada)"

    def test_unknown_id_is_not_a_validation_boundary(self):
        """Labels are display-only: an unknown id is upper-cased, not raised."""
        assert capital_model_label("ifrs") == "IFRS"
