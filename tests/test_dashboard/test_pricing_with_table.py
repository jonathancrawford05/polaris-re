"""Tests for the dashboard tabular YRT pricing path (Slice 4b-2 / ADR-055).

Covers ``run_treaty_projection`` + ``run_gross_projection`` end-to-end with
an uploaded ``YRTRateTable``. Specifically verifies:

* The tabular branch dispatches into ``YRTTreaty.apply()`` with the
  inforce block (required when ``yrt_rate_table`` is set — ADR-051).
* Gross projection runs in seriatim mode so per-policy NAR is available
  for the tabular consumer (also ADR-051).
* Constant-rate uploaded table reproduces the flat-rate ceded premium
  series within tight tolerance — closed-form verification that the
  dashboard tabular wiring produces actuarially identical output to the
  flat rate when the table is truly flat.
"""

from datetime import date
from pathlib import Path

import numpy as np

from polaris_re.core.inforce import InforceBlock
from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
from polaris_re.dashboard.components.projection import (
    run_gross_projection,
    run_treaty_projection,
)
from polaris_re.pipeline import (
    DealConfig,
    LapseConfig,
    MortalityConfig,
    PipelineInputs,
    build_pipeline,
)
from polaris_re.products.dispatch import get_product_engine
from polaris_re.reinsurance.yrt_rate_table import (
    YRTRateTable,
    YRTRateTableArray,
)
from polaris_re.utils.yrt_rate_table_io import parse_uploaded_yrt_rate_table

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yrt_rate_tables"


def _build_test_pipeline():
    """Five-policy single-cohort term block at age 30, 5-year horizon.

    Policies are constructed with ``reinsurance_cession_pct=None`` to match
    the dashboard's CSV-upload defaults (``InforceBlock.from_csv`` defaults
    missing values to ``None``); the legacy ``load_inforce`` path defaults
    to ``0.0`` which would defeat the tabular-treaty cession resolution.
    """
    inputs = PipelineInputs(
        mortality=MortalityConfig(source="flat", flat_qx=0.005),
        lapse=LapseConfig(duration_table={1: 0.05, 2: 0.04, "ultimate": 0.03}),
        deal=DealConfig(product_type="TERM", projection_years=5),
    )
    val_date = date(2026, 1, 1)
    policies = [
        Policy(
            policy_id=f"T{i:03d}",
            issue_age=30,
            attained_age=30,
            sex=Sex.MALE,
            smoker_status=SmokerStatus.NON_SMOKER,
            underwriting_class="STANDARD",
            face_amount=1_000_000.0,
            annual_premium=1500.0,
            product_type=ProductType.TERM,
            policy_term=20,
            duration_inforce=0,
            reinsurance_cession_pct=None,
            issue_date=val_date,
            valuation_date=val_date,
        )
        for i in range(5)
    ]
    inforce = InforceBlock(policies=policies)
    # build_pipeline expects an InforceBlock; load_inforce is only needed
    # when starting from a dict / CSV path. Re-use build_pipeline for the
    # AssumptionSet + ProjectionConfig pieces.
    inf, ass, cfg = build_pipeline(inforce, inputs)
    return inf, ass, cfg


def _constant_rate_table(rate_per_1000: float) -> YRTRateTable:
    """Build a ``YRTRateTable`` covering ages 25-50 with a single flat rate.

    Used for the closed-form parity test: a constant tabular rate must
    produce the same ceded premium stream as the equivalent flat rate.
    """
    n_ages = 50 - 25 + 1
    select_period = 3
    rates = np.full((n_ages, select_period + 1), rate_per_1000, dtype=np.float64)
    arr = YRTRateTableArray(
        rates=rates,
        min_age=25,
        max_age=50,
        select_period=select_period,
    )
    return YRTRateTable.from_arrays(
        table_name="flat-equiv",
        arrays={(Sex.MALE, SmokerStatus.UNKNOWN): arr},
    )


class TestRunTreatyProjectionTabular:
    """Tabular branch of ``run_treaty_projection`` (ADR-051 / ADR-055)."""

    def test_tabular_path_dispatches_with_inforce(self):
        inforce, assumptions, config = _build_test_pipeline()
        # Must use seriatim gross projection for tabular consumption.
        engine = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
        gross = engine.project(seriatim=True)

        # Build a synthetic non-trivial table from the shipped fixtures.
        uploads = [
            ("synthetic_male_ns.csv", (FIXTURES / "synthetic_male_ns.csv").read_bytes()),
            ("synthetic_male_smoker.csv", (FIXTURES / "synthetic_male_smoker.csv").read_bytes()),
            ("synthetic_female_ns.csv", (FIXTURES / "synthetic_female_ns.csv").read_bytes()),
            (
                "synthetic_female_smoker.csv",
                (FIXTURES / "synthetic_female_smoker.csv").read_bytes(),
            ),
        ]
        # Synthetic fixture covers ages 25-35; all test policies are aged 30.
        table = parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="t",
            select_period=3,
        )
        net, ceded = run_treaty_projection(
            gross,
            inforce,
            treaty_type="YRT",
            cession_pct=0.50,
            yrt_rate_table=table,
        )
        # Both legs returned, ceded basis recorded as CEDED.
        assert ceded is not None
        assert ceded.basis == "CEDED"
        assert net.basis == "NET"
        # Ceded premiums must be strictly positive (table rates are > 0
        # for age 30 in every cohort).
        assert float(ceded.gross_premiums.sum()) > 0.0
        # Ceded claims are 50% of gross claims (face-weighted scalar).
        np.testing.assert_allclose(
            ceded.death_claims,
            gross.death_claims * 0.50,
            rtol=1e-10,
        )
        # Additivity invariant: net + ceded == gross for premiums,
        # claims, and net cash flow. Mirrors the canonical pattern in
        # ``BaseTreaty.verify_additivity`` (used by
        # ``test_reinsurance/test_yrt_tabular.py::test_ncf_additivity_preserved``).
        # In YRT, ``net.gross_premiums = gross.gross_premiums - ceded_yrt``
        # so the premium sum holds; claims are proportional; NCF nets out
        # the YRT premium transfer.
        np.testing.assert_allclose(
            net.gross_premiums + ceded.gross_premiums,
            gross.gross_premiums,
            rtol=1e-10,
            atol=1e-6,
            err_msg="net + ceded gross_premiums != gross (additivity failure)",
        )
        np.testing.assert_allclose(
            net.death_claims + ceded.death_claims,
            gross.death_claims,
            rtol=1e-10,
            err_msg="net + ceded death_claims != gross (additivity failure)",
        )
        np.testing.assert_allclose(
            net.net_cash_flow + ceded.net_cash_flow,
            gross.net_cash_flow,
            rtol=1e-10,
            atol=1e-6,
            err_msg="net + ceded net_cash_flow != gross (additivity failure)",
        )

    def test_constant_rate_table_matches_flat_rate(self):
        """Closed-form: a uniform tabular schedule reproduces the flat path.

        ADR-051 guarantees `tabular(constant) == flat(rate)` within
        numerical tolerance. This tightens that guarantee for the dashboard
        wrapper specifically — verifying the wrapper does not introduce a
        scaling bug between the cfg-level and explicit-arg paths.
        """
        inforce, assumptions, config = _build_test_pipeline()
        engine = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
        gross_seriatim = engine.project(seriatim=True)
        gross_flat = engine.project(seriatim=False)

        flat_rate = 2.50
        table = _constant_rate_table(flat_rate)

        _net_t, ceded_t = run_treaty_projection(
            gross_seriatim,
            inforce,
            treaty_type="YRT",
            cession_pct=0.50,
            yrt_rate_table=table,
        )
        _net_f, ceded_f = run_treaty_projection(
            gross_flat,
            inforce,
            treaty_type="YRT",
            cession_pct=0.50,
            yrt_rate_per_1000=flat_rate,
        )
        assert ceded_t is not None and ceded_f is not None
        # Ceded YRT premiums must agree to a few parts per million —
        # tiny numerical noise from seriatim vs. aggregate runoff is OK.
        np.testing.assert_allclose(
            ceded_t.gross_premiums,
            ceded_f.gross_premiums,
            rtol=1e-6,
            atol=1e-3,
        )

    def test_tabular_path_via_cfg_dict(self, monkeypatch):
        """``cfg["yrt_rate_table"]`` is honoured when the kwarg is omitted."""
        # Patch ``get_deal_config`` so the dashboard helpers see a YRT
        # config carrying the table without the explicit kwarg path.
        from polaris_re.dashboard.components import projection as proj_mod

        inforce, assumptions, config = _build_test_pipeline()
        engine = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
        gross = engine.project(seriatim=True)
        table = _constant_rate_table(3.0)

        fake_cfg = {
            "treaty_type": "YRT",
            "cession_pct": 0.40,
            "yrt_rate_table": table,
        }
        monkeypatch.setattr(proj_mod, "get_deal_config", lambda: fake_cfg)

        _net, ceded = run_treaty_projection(gross, inforce)
        assert ceded is not None
        assert float(ceded.gross_premiums.sum()) > 0.0
        # Cession % is taken from cfg (40%), not the default 90%.
        np.testing.assert_allclose(
            ceded.death_claims,
            gross.death_claims * 0.40,
            rtol=1e-10,
        )

    def test_seriatim_argument_propagates_to_engine(self):
        """``run_gross_projection(seriatim=True)`` must populate seriatim_lx."""
        inforce, assumptions, config = _build_test_pipeline()
        gross = run_gross_projection(inforce, assumptions, config, seriatim=True)
        assert gross.seriatim_lx is not None
        assert gross.seriatim_reserves is not None

    def test_seriatim_default_false_no_seriatim_arrays(self):
        inforce, assumptions, config = _build_test_pipeline()
        gross = run_gross_projection(inforce, assumptions, config)
        assert gross.seriatim_lx is None
        assert gross.seriatim_reserves is None

    def test_non_yrt_with_table_in_cfg_warns(self, monkeypatch):
        """Non-YRT treaty + table in cfg must surface a UX warning.

        The user might upload a tabular schedule, then switch the
        treaty type to Coinsurance — without the warning the table
        is silently ignored. Streamlit is unavailable in a bare
        pytest run, so the helper falls back to ``warnings.warn``
        (UserWarning); this test asserts on that fallback path.
        """
        import warnings as _warnings

        from polaris_re.dashboard.components import projection as proj_mod

        inforce, assumptions, config = _build_test_pipeline()
        engine = get_product_engine(inforce=inforce, assumptions=assumptions, config=config)
        gross = engine.project()
        table = _constant_rate_table(2.0)
        fake_cfg = {
            "treaty_type": "Coinsurance",
            "cession_pct": 0.50,
            "yrt_rate_table": table,
        }
        monkeypatch.setattr(proj_mod, "get_deal_config", lambda: fake_cfg)

        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            _net, _ceded = run_treaty_projection(gross, inforce)
        messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
        assert any("table is loaded but treaty type is 'Coinsurance'" in m for m in messages), (
            f"Expected UX warning about ignored YRT rate table, got: {messages}"
        )
