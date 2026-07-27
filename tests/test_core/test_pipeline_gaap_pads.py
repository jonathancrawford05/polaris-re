"""Unit tests for GAAP (FAS 60) PAD plumbing in the pipeline builder.

The two GAAP provisions for adverse deviation (``gaap_mortality_pad`` and
``gaap_interest_margin``) are built onto ``ProjectionConfig`` (ADR-127/128) but,
until this surfacing work, could not be set from a ``DealConfig`` (config/CLI/API
path) — a GAAP-basis deal priced from a config always got the neutral defaults.
These tests pin that ``DealConfig`` now carries both fields, that
``build_projection_config`` threads them onto the ``ProjectionConfig``, and that
the neutral defaults are preserved (byte-identical) when they are unset. Range
validation is deferred to ``ProjectionConfig`` (exercised here for the bad case).
"""

import pytest
from pydantic import ValidationError

from polaris_re.pipeline import DealConfig, PipelineInputs, build_projection_config


class TestBuildProjectionConfigGAAPPads:
    def test_defaults_are_neutral(self) -> None:
        """A DealConfig with no PADs yields the neutral ProjectionConfig values."""
        config = build_projection_config(PipelineInputs(deal=DealConfig()))
        assert config.gaap_mortality_pad == 1.0
        assert config.gaap_interest_margin == 0.0

    def test_mortality_pad_flows_through(self) -> None:
        inputs = PipelineInputs(deal=DealConfig(gaap_mortality_pad=1.10))
        config = build_projection_config(inputs)
        assert config.gaap_mortality_pad == pytest.approx(1.10)

    def test_interest_margin_flows_through(self) -> None:
        inputs = PipelineInputs(deal=DealConfig(gaap_interest_margin=0.005))
        config = build_projection_config(inputs)
        assert config.gaap_interest_margin == pytest.approx(0.005)
        # The GAAP discount rate is the valuation rate less the interest margin.
        assert config.gaap_valuation_rate == pytest.approx(config.discount_rate - 0.005)

    def test_both_pads_flow_through(self) -> None:
        inputs = PipelineInputs(deal=DealConfig(gaap_mortality_pad=1.15, gaap_interest_margin=0.01))
        config = build_projection_config(inputs)
        assert config.gaap_mortality_pad == pytest.approx(1.15)
        assert config.gaap_interest_margin == pytest.approx(0.01)

    def test_below_one_mortality_pad_raises(self) -> None:
        """ProjectionConfig enforces gaap_mortality_pad >= 1.0."""
        inputs = PipelineInputs(deal=DealConfig(gaap_mortality_pad=0.9))
        with pytest.raises(ValidationError):
            build_projection_config(inputs)

    def test_out_of_range_interest_margin_raises(self) -> None:
        """ProjectionConfig enforces gaap_interest_margin in [0, 1]."""
        inputs = PipelineInputs(deal=DealConfig(gaap_interest_margin=1.5))
        with pytest.raises(ValidationError):
            build_projection_config(inputs)
