"""Dashboard flow tests using Streamlit AppTest.

These tests drive the Streamlit app headlessly, verifying that:
- Widget values propagate through session_state correctly
- Page navigation renders without error
- Deal config changes on Assumptions page reach Deal Pricing
- Inforce upload populates the expected session state keys

AppTest limitations:
- Cannot test matplotlib chart rendering (use golden output tests)
- Cannot test file_uploader directly (use session state injection)
- Cannot test real SOA table loading (mock or use flat mortality)
"""

import pytest

# NOTE: AppTest is available from streamlit >= 1.28
# Import will fail on older versions — skip gracefully.
try:
    from streamlit.testing.v1 import AppTest

    _HAS_APPTEST = True
except ImportError:
    _HAS_APPTEST = False

pytestmark = pytest.mark.skipif(
    not _HAS_APPTEST,
    reason="streamlit.testing.v1 not available",
)

APP_PATH = "src/polaris_re/dashboard/app.py"


class TestAppBootstrap:
    """Verify the app starts and renders the default page."""

    def test_app_starts_without_error(self):
        """App should start and render the Inforce Block page."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception, f"App raised: {at.exception}"

    def test_sidebar_navigation_exists(self):
        """Sidebar should have a radio widget with all 7 pages."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        # Radio widget for navigation
        assert len(at.sidebar.radio) >= 1
        nav = at.sidebar.radio[0]
        assert "Inforce Block" in nav.options
        assert "Deal Pricing" in nav.options
        assert "IFRS 17" in nav.options


class TestPageNavigation:
    """Verify each page renders without error when navigated to."""

    @pytest.mark.parametrize(
        "page_name",
        [
            "Inforce Block",
            "Assumptions",
            "Deal Pricing",
            "Treaty Comparison",
            "Scenario Analysis",
            "Monte Carlo UQ",
            "IFRS 17",
            "Experience Study",
        ],
    )
    def test_page_renders(self, page_name):
        """Each page should render without raising exceptions."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value(page_name)
        at.run()
        assert not at.exception, f"Page '{page_name}' raised: {at.exception}"


class TestSessionStateDefaults:
    """Verify session state initialisation from DealConfig."""

    def test_deal_config_initialised(self):
        """deal_config should be initialised with DealConfig defaults."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()

        # Session state should have deal_config
        assert "deal_config" in at.session_state
        cfg = at.session_state["deal_config"]
        assert cfg is not None
        assert cfg["product_type"] == "TERM"
        assert cfg["treaty_type"] == "YRT"
        assert cfg["cession_pct"] == 0.90
        assert cfg["discount_rate"] == 0.06

    def test_inforce_block_initially_none(self):
        """inforce_block should be None before any CSV is uploaded."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        # AppTest's SafeSessionState doesn't expose dict-style .get() — use
        # membership test + indexing instead.
        if "inforce_block" in at.session_state:
            assert at.session_state["inforce_block"] is None


class TestAssumptionsPageWidgets:
    """Verify widget rendering and state updates on Page 2."""

    def test_mortality_selectbox_renders(self):
        """Mortality table selectbox should render on Assumptions page."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Assumptions")
        at.run()
        assert not at.exception

    def test_cession_slider_bounds(self):
        """Cession slider must allow values from 0% to 100%.

        This is the regression test for the <50% slider floor bug.
        """
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Assumptions")
        at.run()
        # Find the cession slider — look for sliders on the page
        # The exact slider index depends on rendering order;
        # search by examining slider labels or values.
        sliders = at.slider
        cession_sliders = [
            s for s in sliders if hasattr(s, "label") and "cession" in str(s.label).lower()
        ]
        if cession_sliders:
            cs = cession_sliders[0]
            # Verify the slider allows sub-50% values
            cs.set_value(0.10)
            at.run()
            assert not at.exception, "Cession slider rejected 10%"
            # Verify it reaches the full range
            cs.set_value(1.0)
            at.run()
            assert not at.exception, "Cession slider rejected 100%"


class TestDealPricingWithInjectedState:
    """Test Deal Pricing page with pre-injected session state.

    Since AppTest cannot drive file_uploader, we inject a pre-built
    InforceBlock and AssumptionSet into session state before navigating
    to the Deal Pricing page. This mirrors what Pages 1 and 2 would do.
    """

    @pytest.fixture()
    def app_with_inforce(self):
        """App with a synthetic inforce block injected into state."""
        from polaris_re.core.pipeline import (
            DealConfig,
            LapseConfig,
            MortalityConfig,
            PipelineInputs,
            build_pipeline,
            load_inforce,
        )

        # Build a minimal single-policy block with flat mortality
        policies = [
            {
                "policy_id": "TEST-001",
                "issue_age": 40,
                "attained_age": 40,
                "sex": "M",
                "smoker": False,
                "face_amount": 500000.0,
                "annual_premium": 1200.0,
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
            deal=DealConfig(product_type="TERM", projection_years=10),
        )
        inf, assumptions, _config = build_pipeline(inforce, inputs)

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()

        # Inject state
        at.session_state["inforce_block"] = inf
        at.session_state["assumption_set"] = assumptions

        return at

    def test_pricing_page_renders_with_state(self, app_with_inforce):
        """Deal Pricing page should render when state is populated."""
        at = app_with_inforce
        at.sidebar.radio[0].set_value("Deal Pricing")
        at.run()
        assert not at.exception, f"Deal Pricing raised with injected state: {at.exception}"

    def test_pricing_resolves_block_valuation_date(self, app_with_inforce):
        """A pricing run projects from the block's valuation date, not the clock.

        ADR-074 QA-gap regression: deal_config starts with
        valuation_date=None, and the projection helper must resolve the
        inforce block's date (2026-04-01 in this fixture) — never
        date.today() — so the same CSV prices identically on any run day.
        """
        from datetime import date

        at = app_with_inforce
        assert at.session_state["deal_config"]["valuation_date"] is None
        at.sidebar.radio[0].set_value("Deal Pricing")
        at.run()
        run_buttons = [b for b in at.button if b.label == "Run Pricing"]
        assert run_buttons, f"Run Pricing button not found; saw {[b.label for b in at.button]}"
        run_buttons[0].click()
        at.run()
        assert not at.exception, f"Pricing run raised: {at.exception}"
        gross = at.session_state["gross_result"]
        assert gross is not None, "Pricing run did not store gross_result"
        assert gross.valuation_date == date(2026, 4, 1)


class TestExperienceStudyPage:
    """ADR-056 — Experience Study (A/E) page end-to-end via AppTest."""

    def test_experience_study_in_navigation(self):
        """Sidebar nav should expose 'Experience Study' as a page option."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        nav = at.sidebar.radio[0]
        assert "Experience Study" in nav.options

    def test_sample_data_path_runs_overall_ae(self):
        """Switching to Sample data should run an overall A/E without error."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Experience Study")
        at.run()
        assert not at.exception, f"Experience Study raised: {at.exception}"

        # Find the data-source radio (separate from the sidebar nav).
        ds_radios = [
            r for r in at.radio if hasattr(r, "label") and "data source" in str(r.label).lower()
        ]
        assert ds_radios, "Data source radio not found"
        ds_radios[0].set_value("Sample data")
        at.run()
        assert not at.exception, f"Sample data run raised: {at.exception}"

    def test_groupby_renders_summary_chart(self):
        """Selecting a grouping dimension should render the A/E chart cleanly."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Experience Study")
        at.run()
        ds_radios = [
            r for r in at.radio if hasattr(r, "label") and "data source" in str(r.label).lower()
        ]
        assert ds_radios
        ds_radios[0].set_value("Sample data")
        at.run()

        # Group by 'sex' via the multiselect.
        msel = [
            m for m in at.multiselect if hasattr(m, "label") and "group by" in str(m.label).lower()
        ]
        assert msel, "Group By multiselect not found"
        msel[0].set_value(["sex"])
        at.run()
        assert not at.exception, f"Group-by run raised: {at.exception}"

    def test_multi_dimension_groupby_renders(self):
        """Grouping by two dimensions (sex + age) must render cleanly.

        Regression for the reported bug: charts collapsed the per-age bars
        within one sex onto a single x position when more than one grouping
        dimension was selected.
        """
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Experience Study")
        at.run()
        ds_radios = [
            r for r in at.radio if hasattr(r, "label") and "data source" in str(r.label).lower()
        ]
        assert ds_radios
        ds_radios[0].set_value("Sample data")
        at.run()

        msel = [
            m for m in at.multiselect if hasattr(m, "label") and "group by" in str(m.label).lower()
        ]
        assert msel, "Group By multiselect not found"
        msel[0].set_value(["sex", "age"])
        at.run()
        assert not at.exception, f"Multi-dimension group-by raised: {at.exception}"


class TestPortfolioPage:
    """Slice 2 — Portfolio page smoke tests via AppTest session-state injection.

    AppTest cannot drive st.file_uploader directly, so a pre-built
    PortfolioResult is injected into st.session_state["portfolio_result"]
    before navigating to the page. The fixture builds the result using the
    Slice-1 loader against the committed sample portfolio, giving a realistic
    4-deal result that exercises all rendering paths.
    """

    @pytest.fixture(scope="class")
    def sample_portfolio_result(self):
        """Build the 4-deal sample portfolio result once for the whole class."""
        from pathlib import Path

        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        sample_config = Path("data/inputs/portfolio_sample/portfolio.yaml")
        portfolio, hurdle_rate = load_portfolio_from_config_path(sample_config)
        return portfolio.run(hurdle_rate, align="strict")

    def test_portfolio_in_navigation(self):
        """Sidebar nav must expose 'Portfolio' as a page option."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        nav = at.sidebar.radio[0]
        assert "Portfolio" in nav.options

    def test_portfolio_empty_state_renders(self):
        """Portfolio page renders without exception when no result is in state."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception, f"Portfolio empty state raised: {at.exception}"

    def test_portfolio_tiles_with_injected_result(self, sample_portfolio_result):
        """Page renders all six aggregate tiles when result is in session state."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception, f"Portfolio page with injected result raised: {at.exception}"
        labels = [m.label for m in at.metric]
        assert "Deals" in labels
        assert "Total Ceded Face" in labels
        assert "Total PV Profits" in labels
        assert "Total IRR" in labels
        assert "Profit Margin" in labels
        assert "Peak Ceded NAR" in labels

    def test_aggregate_tile_n_deals(self, sample_portfolio_result):
        """'Deals' metric displays the correct deal count from the injected result."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        metrics = {m.label: m.value for m in at.metric}
        assert metrics["Deals"] == str(sample_portfolio_result.n_deals)

    def test_aggregate_tile_pv_profits(self, sample_portfolio_result):
        """'Total PV Profits' metric displays the formatted value from the result."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        metrics = {m.label: m.value for m in at.metric}
        expected = f"${sample_portfolio_result.total_pv_profits:,.0f}"
        assert metrics["Total PV Profits"] == expected

    def test_per_deal_table_rendered(self, sample_portfolio_result):
        """A dataframe (per-deal breakdown table) is rendered when result is present."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        assert len(at.dataframe) > 0

    def test_per_deal_table_contains_all_deal_ids(self, sample_portfolio_result):
        """Per-deal table contains a row for every deal_id in the result."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        assert len(at.dataframe) > 0
        df = at.dataframe[0].value
        expected_ids = {dr.deal_id for dr in sample_portfolio_result.deal_results}
        actual_ids = set(df["Deal ID"].tolist())
        assert actual_ids == expected_ids


class TestPortfolioPageCalendarAlignment:
    """Calendar-aligned UI path (ADR-061) via the staggered-date sample.

    The canonical sample (``portfolio_sample/``) has uniform deal
    valuation dates, so every ``grid_offset`` is 0 and the grid-origin
    banner / "Grid Offset (months)" column are suppressed. The
    staggered sample sets explicit deal-level valuation dates two
    months apart (DEAL_A / DEAL_B at 2026-01-01, DEAL_C / DEAL_D at
    2026-03-01) so ``align="calendar"`` produces non-zero offsets and
    the calendar-mode rendering path is exercised end to end.
    """

    @pytest.fixture(scope="class")
    def staggered_portfolio_result(self):
        """Run the staggered-date sample under align='calendar' once per class."""
        from pathlib import Path

        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        portfolio, hurdle_rate = load_portfolio_from_config_path(
            Path("data/inputs/portfolio_staggered_sample/portfolio.yaml")
        )
        return portfolio.run(hurdle_rate, align="calendar")

    def _open_page(self, result):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        return at

    def test_grid_origin_banner_renders(self, staggered_portfolio_result):
        """The grid-origin st.info banner fires when any grid_offset is non-zero."""
        at = self._open_page(staggered_portfolio_result)
        assert not at.exception, f"Calendar-aligned page raised: {at.exception}"
        info_texts = [str(i.value) for i in at.info]
        banner = [t for t in info_texts if "Grid origin" in t]
        assert banner, f"Grid-origin banner not rendered; saw info boxes: {info_texts}"
        assert "2026-01-01" in banner[0], (
            f"Banner should name the earliest valuation date; got: {banner[0]}"
        )

    def test_per_deal_table_has_grid_offset_column(self, staggered_portfolio_result):
        """The breakdown table includes 'Grid Offset (months)' when offsets exist."""
        at = self._open_page(staggered_portfolio_result)
        assert not at.exception
        deal_dfs = [df for df in at.dataframe if "Deal ID" in df.value.columns]
        assert deal_dfs, "Per-deal breakdown dataframe not found"
        assert "Grid Offset (months)" in deal_dfs[0].value.columns

    def test_deal_c_and_d_offset_by_two_months(self, staggered_portfolio_result):
        """DEAL_C / DEAL_D land two months from the origin; DEAL_A / DEAL_B at zero."""
        at = self._open_page(staggered_portfolio_result)
        assert not at.exception
        deal_dfs = [df for df in at.dataframe if "Deal ID" in df.value.columns]
        assert deal_dfs
        df = deal_dfs[0].value
        offsets = dict(zip(df["Deal ID"], df["Grid Offset (months)"], strict=True))
        assert offsets == {"DEAL_A": 0, "DEAL_B": 0, "DEAL_C": 2, "DEAL_D": 2}


class TestPortfolioPageConcentration:
    """Slice 3 — Concentration sub-section (ADR-069 / ADR-073)."""

    @pytest.fixture(scope="class")
    def sample_portfolio_result(self):
        from pathlib import Path

        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        portfolio, hurdle_rate = load_portfolio_from_config_path(
            Path("data/inputs/portfolio_sample/portfolio.yaml")
        )
        return portfolio.run(hurdle_rate, align="strict")

    def _open_page(self, sample_portfolio_result):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = sample_portfolio_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        return at

    def test_dimension_selector_renders_default_cedant(self, sample_portfolio_result):
        """Default dimension (Cedant) is selected and the page renders cleanly."""
        at = self._open_page(sample_portfolio_result)
        assert not at.exception, f"Concentration default raised: {at.exception}"
        dim_boxes = [
            sb
            for sb in at.selectbox
            if hasattr(sb, "label") and "group by" in str(sb.label).lower()
        ]
        assert dim_boxes, "Concentration dimension selectbox not found"
        assert dim_boxes[0].value == "Cedant"

    def test_dimension_selector_switches_to_product(self, sample_portfolio_result):
        """Switching Group By to Product re-renders without exception."""
        at = self._open_page(sample_portfolio_result)
        dim_boxes = [
            sb
            for sb in at.selectbox
            if hasattr(sb, "label") and "group by" in str(sb.label).lower()
        ]
        assert dim_boxes
        dim_boxes[0].set_value("Product")
        at.run()
        assert not at.exception, f"Switching to Product raised: {at.exception}"

    def test_dimension_selector_switches_to_treaty(self, sample_portfolio_result):
        """Switching Group By to Treaty re-renders without exception."""
        at = self._open_page(sample_portfolio_result)
        dim_boxes = [
            sb
            for sb in at.selectbox
            if hasattr(sb, "label") and "group by" in str(sb.label).lower()
        ]
        assert dim_boxes
        dim_boxes[0].set_value("Treaty")
        at.run()
        assert not at.exception, f"Switching to Treaty raised: {at.exception}"

    def test_hhi_table_has_three_bases_and_three_dimensions(self, sample_portfolio_result):
        """HHI matrix contains 3 bases (rows) by 3 dimensions (columns)."""
        at = self._open_page(sample_portfolio_result)
        assert not at.exception
        # The page renders two dataframes: per-deal breakdown and HHI table.
        # The HHI table is the one whose first column is 'Basis'.
        hhi_dfs = [df for df in at.dataframe if "Basis" in df.value.columns]
        assert hhi_dfs, "HHI dataframe not found"
        hhi = hhi_dfs[0].value
        assert len(hhi) == 3, f"Expected 3 basis rows, got {len(hhi)}"
        # Three dimension columns: Cedant, Product, Treaty.
        for col in ("Cedant", "Product", "Treaty"):
            assert col in hhi.columns, f"HHI table missing column {col!r}"

    def test_csv_export_contains_every_basis_dimension_label(self, sample_portfolio_result):
        """CSV export contains a row for every (basis, dimension, label) triple."""
        from polaris_re.dashboard.views.portfolio import _concentration_to_csv_bytes

        by_dim = sample_portfolio_result.concentration_by_dimension()
        csv_bytes = _concentration_to_csv_bytes(by_dim)
        text = csv_bytes.decode("utf-8")
        lines = [line for line in text.splitlines() if line]
        # Header + one row per (dimension, basis, label).
        expected_rows = sum(len(labels) for dim in by_dim.values() for labels in dim.values())
        assert lines[0] == "dimension,basis,label,share"
        assert len(lines) - 1 == expected_rows
        # Sanity check: every dimension key appears.
        for dim_key in ("cedant", "product", "treaty"):
            assert (
                f",{dim_key}," in text or text.startswith(dim_key + ",") or f"\n{dim_key}," in text
            )


class TestPortfolioPageScenarios:
    """Slice 3 — Scenarios sub-section (ADR-064)."""

    @pytest.fixture(scope="class")
    def sample_runtime(self):
        from pathlib import Path

        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        portfolio, hurdle_rate = load_portfolio_from_config_path(
            Path("data/inputs/portfolio_sample/portfolio.yaml")
        )
        result = portfolio.run(hurdle_rate, align="strict")
        return portfolio, hurdle_rate, result

    def test_scenarios_runs_and_renders_table(self, sample_runtime):
        """Pre-injecting a scenario result renders the scenario table cleanly."""
        portfolio, hurdle_rate, result = sample_runtime
        # Pre-compute scenarios so the test does not need to drive the button.
        scen_result = portfolio.run_scenarios(hurdle_rate, align="strict")

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = result
        at.session_state["portfolio_scenarios"] = scen_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception, f"Scenarios sub-section raised: {at.exception}"

        # The scenario dataframe is the one whose first column is 'Scenario'.
        scen_dfs = [df for df in at.dataframe if "Scenario" in df.value.columns]
        assert scen_dfs, "Scenarios dataframe not found"
        df = scen_dfs[0].value
        scenario_names = set(df["Scenario"].tolist())
        for expected in ("BASE", "MORT_110", "MORT_90"):
            assert expected in scenario_names

    def test_worst_case_callout_renders(self, sample_runtime):
        """Worst-case callout appears when scenarios produce a valid worst case."""
        portfolio, hurdle_rate, result = sample_runtime
        scen_result = portfolio.run_scenarios(hurdle_rate, align="strict")

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = result
        at.session_state["portfolio_scenarios"] = scen_result
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        worst = scen_result.worst_case()
        worst_messages = list(at.warning) + list(at.info)
        rendered_text = " ".join(str(m.value) for m in worst_messages)
        if worst is None:
            assert "Worst case: N/A" in rendered_text
        else:
            assert "Worst case" in rendered_text


class TestPortfolioPageCapital:
    """Slice 3 — Capital sub-section (ADR-060 / ADR-072)."""

    @pytest.fixture(scope="class")
    def capital_result(self):
        from pathlib import Path

        from polaris_re.analytics.capital import LICATCapital
        from polaris_re.core.policy import ProductType
        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        portfolio, hurdle_rate = load_portfolio_from_config_path(
            Path("data/inputs/portfolio_sample/portfolio.yaml")
        )
        capital_model = LICATCapital.for_product_interim(ProductType.TERM)
        return portfolio.run_with_capital(hurdle_rate, capital_model, align="strict")

    def test_capital_tiles_rendered(self, capital_result):
        """Capital tiles (Initial / Peak / PV / RoC / Capital-Adjusted IRR) render."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        # Toggle the checkbox via session state pre-population.
        at.session_state["portfolio_result"] = capital_result
        at.session_state["portfolio_capital_result"] = capital_result
        at.session_state["portfolio_capital_toggle"] = True
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception, f"Capital sub-section raised: {at.exception}"
        labels = [m.label for m in at.metric]
        assert "Initial Capital" in labels
        assert "Peak Capital" in labels
        assert "PV Capital" in labels
        assert "Return on Capital" in labels

    def test_capital_adjusted_irr_tile_present(self, capital_result):
        """capital_adjusted_irr is surfaced as its own tile (Refinement Backlog)."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["portfolio_result"] = capital_result
        at.session_state["portfolio_capital_result"] = capital_result
        at.session_state["portfolio_capital_toggle"] = True
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        assert not at.exception
        labels = [m.label for m in at.metric]
        assert "Capital-Adjusted IRR" in labels


class TestTabularYRTUpload:
    """Slice 4b-2 / ADR-055 — tabular YRT upload UI on the Assumptions page."""

    def test_yrt_basis_selector_includes_tabular(self):
        """The YRT Rate Basis selector exposes the new 'Tabular Schedule' option."""
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.sidebar.radio[0].set_value("Assumptions")
        at.run()
        assert not at.exception
        # YRT is the default treaty type, so the basis selector renders.
        basis_selectboxes = [
            sb
            for sb in at.selectbox
            if hasattr(sb, "label") and "yrt rate basis" in str(sb.label).lower()
        ]
        assert basis_selectboxes, "YRT Rate Basis selectbox not found on Assumptions page"
        opts = list(basis_selectboxes[0].options)
        assert "Tabular Schedule" in opts
        assert "Mortality-based" in opts
        assert "Manual Rate" in opts

    def test_pricing_with_uploaded_table_via_session_state(self):
        """End-to-end: injecting a YRTRateTable into deal_config drives pricing."""
        from datetime import date
        from pathlib import Path

        from polaris_re.core.inforce import InforceBlock
        from polaris_re.core.pipeline import (
            DealConfig,
            LapseConfig,
            MortalityConfig,
            PipelineInputs,
            build_pipeline,
        )
        from polaris_re.core.policy import Policy, ProductType, Sex, SmokerStatus
        from polaris_re.utils.yrt_rate_table_io import parse_uploaded_yrt_rate_table

        fixtures = Path(__file__).parent.parent / "fixtures" / "yrt_rate_tables"
        uploads = [
            (name, (fixtures / name).read_bytes())
            for name in (
                "synthetic_male_ns.csv",
                "synthetic_male_smoker.csv",
                "synthetic_female_ns.csv",
                "synthetic_female_smoker.csv",
            )
        ]
        table = parse_uploaded_yrt_rate_table(
            uploads=uploads,
            table_name="dashboard-fixture",
            select_period=3,
        )

        # Build a single-policy aged-30 block (covered by the fixture's
        # ages 25-35) with reinsurance_cession_pct=None so the tabular
        # treaty resolves cession from the treaty default (ADR-051).
        val_date = date(2026, 1, 1)
        policies = [
            Policy(
                policy_id="UPLOAD-001",
                issue_age=30,
                attained_age=30,
                sex=Sex.MALE,
                smoker_status=SmokerStatus.NON_SMOKER,
                underwriting_class="STANDARD",
                face_amount=500_000.0,
                annual_premium=1200.0,
                product_type=ProductType.TERM,
                policy_term=20,
                duration_inforce=0,
                reinsurance_cession_pct=None,
                issue_date=val_date,
                valuation_date=val_date,
            )
        ]
        inforce = InforceBlock(policies=policies)
        inputs = PipelineInputs(
            mortality=MortalityConfig(source="flat", flat_qx=0.005),
            lapse=LapseConfig(),
            deal=DealConfig(product_type="TERM", projection_years=5),
        )
        inf, assumptions, _config = build_pipeline(inforce, inputs)

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        at.session_state["inforce_block"] = inf
        at.session_state["assumption_set"] = assumptions

        # Inject the uploaded table into the deal config so the pricing
        # page picks it up via the tabular branch.
        cfg = dict(at.session_state["deal_config"])
        cfg["yrt_rate_table"] = table
        cfg["yrt_rate_basis"] = "Tabular Schedule"
        cfg["projection_years"] = 5
        at.session_state["deal_config"] = cfg

        at.sidebar.radio[0].set_value("Deal Pricing")
        at.run()
        assert not at.exception, f"Deal Pricing raised with tabular state: {at.exception}"


def _raise_computation(*_args, **_kwargs):
    """Stand-in engine entry point that simulates a numerical failure."""
    from polaris_re.core.exceptions import PolarisComputationError

    raise PolarisComputationError("forced numerical failure (singular matrix in IRR solve)")


class TestDashboardComputationErrorHandling:
    """Regression: dashboard Run buttons render a friendly ``st.error`` tile
    (rather than propagating a raw traceback) when the engine raises
    ``PolarisComputationError``.

    Each test monkeypatches the relevant engine entry point to raise
    ``PolarisComputationError``, drives the page's Run button via AppTest,
    and asserts the page caught it and surfaced an ``st.error`` with no
    propagated exception. This guards the widened
    ``(PolarisValidationError, PolarisComputationError)`` catches.

    The Portfolio page's primary "Run portfolio" button is gated behind a
    ``file_uploader`` (undriveable by AppTest, per the module docstring), so
    it is covered indirectly via the session-state-driven "Run scenarios"
    sub-button, which shares the same widened catch tuple.
    """

    @staticmethod
    def _term_pipeline():
        """Build a minimal single-TERM-policy (inforce, assumptions, config)."""
        from polaris_re.core.pipeline import (
            DealConfig,
            LapseConfig,
            MortalityConfig,
            PipelineInputs,
            build_pipeline,
            load_inforce,
        )

        policies = [
            {
                "policy_id": "CERR-001",
                "issue_age": 40,
                "attained_age": 40,
                "sex": "M",
                "smoker": False,
                "face_amount": 500000.0,
                "annual_premium": 1200.0,
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
            deal=DealConfig(product_type="TERM", projection_years=10),
        )
        return build_pipeline(inforce, inputs)

    def _app_with_term_state(self):
        inf, assumptions, config = self._term_pipeline()
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.session_state["inforce_block"] = inf
        at.session_state["assumption_set"] = assumptions
        return at, config

    @staticmethod
    def _click(at, label):
        matches = [b for b in at.button if b.label == label]
        assert matches, f"Run button {label!r} not found; saw {[b.label for b in at.button]}"
        matches[0].click()
        at.run()

    @staticmethod
    def _assert_friendly_error(at, prefix):
        assert not at.exception, f"Page propagated a raw exception: {at.exception}"
        messages = [str(e.value) for e in at.error]
        assert any(prefix in m for m in messages), (
            f"Expected an st.error starting with {prefix!r}; saw {messages}"
        )

    def test_pricing_page(self, monkeypatch):
        monkeypatch.setattr(
            "polaris_re.dashboard.views.pricing._run_pricing_for_cohort",
            _raise_computation,
        )
        at, _config = self._app_with_term_state()
        at.sidebar.radio[0].set_value("Deal Pricing")
        at.run()
        self._click(at, "Run Pricing")
        self._assert_friendly_error(at, "Pricing error:")

    def test_scenario_page(self, monkeypatch):
        monkeypatch.setattr(
            "polaris_re.dashboard.views.scenario.run_gross_projection",
            _raise_computation,
        )
        at, _config = self._app_with_term_state()
        at.sidebar.radio[0].set_value("Scenario Analysis")
        at.run()
        self._click(at, "Run Scenarios")
        self._assert_friendly_error(at, "Scenario error:")

    def test_uq_page(self, monkeypatch):
        monkeypatch.setattr(
            "polaris_re.dashboard.views.uq.run_gross_projection",
            _raise_computation,
        )
        at, _config = self._app_with_term_state()
        at.sidebar.radio[0].set_value("Monte Carlo UQ")
        at.run()
        self._click(at, "Run Monte Carlo")
        self._assert_friendly_error(at, "Monte Carlo error:")

    def test_treaty_compare_page(self, monkeypatch):
        monkeypatch.setattr(
            "polaris_re.dashboard.views.treaty_compare.run_gross_projection",
            _raise_computation,
        )
        at, _config = self._app_with_term_state()
        at.sidebar.radio[0].set_value("Treaty Comparison")
        at.run()
        self._click(at, "Run Comparison")
        self._assert_friendly_error(at, "Treaty comparison error:")

    def test_ifrs17_page(self, monkeypatch):
        from polaris_re.dashboard.components.projection import run_gross_projection

        # IFRS 17 measures a cached gross projection; inject one into state.
        inf, assumptions, config = self._term_pipeline()
        gross = run_gross_projection(inf, assumptions, config)

        monkeypatch.setattr(
            "polaris_re.analytics.ifrs17.IFRS17Measurement",
            _raise_computation,
        )
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.session_state["gross_result"] = gross
        at.sidebar.radio[0].set_value("IFRS 17")
        at.run()
        self._click(at, "Run IFRS 17 Measurement")
        self._assert_friendly_error(at, "IFRS 17 measurement error:")

    def test_portfolio_scenarios_button(self, monkeypatch):
        from pathlib import Path

        from polaris_re.analytics.portfolio import Portfolio
        from polaris_re.dashboard.components.portfolio_loader import (
            load_portfolio_from_config_path,
        )

        portfolio, hurdle_rate = load_portfolio_from_config_path(
            Path("data/inputs/portfolio_sample/portfolio.yaml")
        )
        result = portfolio.run(hurdle_rate, align="strict")

        # Force the scenario engine to fail numerically.
        monkeypatch.setattr(Portfolio, "run_scenarios", _raise_computation)

        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.session_state["portfolio_result"] = result
        at.session_state["portfolio_runtime"] = {
            "portfolio": portfolio,
            "hurdle_rate": hurdle_rate,
            "align": "strict",
        }
        at.sidebar.radio[0].set_value("Portfolio")
        at.run()
        self._click(at, "Run scenarios")
        self._assert_friendly_error(at, "Scenario error:")


class TestScenarioUQPerspective:
    """ADR-078: the Scenario and Monte Carlo UQ dashboard pages expose a
    profit-test perspective selector (default reinsurer, matching Deal Pricing
    and the CLI) and thread the chosen perspective through to the runner.

    The closed-form correctness of each perspective is covered at the analytics
    layer (``test_scenario_uq_perspective.py``) and the API layer
    (``test_api/test_scenario_uq_perspective.py``). These tests verify the
    dashboard wiring: that the selector value reaches the runner, evidenced by
    the perspective the result reports back in the page caption.
    """

    @staticmethod
    def _term_pipeline():
        from polaris_re.core.pipeline import (
            DealConfig,
            LapseConfig,
            MortalityConfig,
            PipelineInputs,
            build_pipeline,
            load_inforce,
        )

        policies = [
            {
                "policy_id": "PERSP-001",
                "issue_age": 40,
                "attained_age": 40,
                "sex": "M",
                "smoker": False,
                "face_amount": 500000.0,
                "annual_premium": 1200.0,
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
            deal=DealConfig(product_type="TERM", projection_years=10),
        )
        return build_pipeline(inforce, inputs)

    def _app(self):
        inf, assumptions, _config = self._term_pipeline()
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.run()
        at.session_state["inforce_block"] = inf
        at.session_state["assumption_set"] = assumptions
        return at

    @staticmethod
    def _set_perspective(at, key, label):
        sb = next(s for s in at.selectbox if s.key == key)
        sb.set_value(label)
        at.run()

    @staticmethod
    def _click(at, label):
        matches = [b for b in at.button if b.label == label]
        assert matches, f"Button {label!r} not found; saw {[b.label for b in at.button]}"
        matches[0].click()
        at.run()

    @staticmethod
    def _caption_says(at, needle):
        return any(needle in str(c.value) for c in at.caption)

    def test_scenario_selector_present_default_reinsurer(self):
        at = self._app()
        at.sidebar.radio[0].set_value("Scenario Analysis")
        at.run()
        keys = [s.key for s in at.selectbox]
        assert "sc_perspective" in keys, f"perspective selector missing; saw {keys}"
        self._click(at, "Run Scenarios")
        assert not at.exception, f"Scenario page raised: {at.exception}"
        assert self._caption_says(at, "perspective: **reinsurer**"), (
            f"Expected reinsurer perspective caption; saw {[str(c.value) for c in at.caption]}"
        )

    def test_scenario_cedant_selection_threads_through(self):
        at = self._app()
        at.sidebar.radio[0].set_value("Scenario Analysis")
        at.run()
        self._set_perspective(at, "sc_perspective", "Cedant (retained net)")
        self._click(at, "Run Scenarios")
        assert not at.exception, f"Scenario page raised: {at.exception}"
        assert self._caption_says(at, "perspective: **cedant**"), (
            f"Expected cedant perspective caption; saw {[str(c.value) for c in at.caption]}"
        )

    def test_uq_selector_present_default_reinsurer(self):
        at = self._app()
        at.sidebar.radio[0].set_value("Monte Carlo UQ")
        at.run()
        keys = [s.key for s in at.selectbox]
        assert "uq_perspective" in keys, f"perspective selector missing; saw {keys}"
        self._click(at, "Run Monte Carlo")
        assert not at.exception, f"UQ page raised: {at.exception}"
        assert self._caption_says(at, "perspective: **reinsurer**"), (
            f"Expected reinsurer perspective caption; saw {[str(c.value) for c in at.caption]}"
        )

    def test_uq_cedant_selection_threads_through(self):
        at = self._app()
        at.sidebar.radio[0].set_value("Monte Carlo UQ")
        at.run()
        self._set_perspective(at, "uq_perspective", "Cedant (retained net)")
        self._click(at, "Run Monte Carlo")
        assert not at.exception, f"UQ page raised: {at.exception}"
        assert self._caption_says(at, "perspective: **cedant**"), (
            f"Expected cedant perspective caption; saw {[str(c.value) for c in at.caption]}"
        )
