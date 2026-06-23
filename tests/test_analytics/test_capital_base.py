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
