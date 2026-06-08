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
