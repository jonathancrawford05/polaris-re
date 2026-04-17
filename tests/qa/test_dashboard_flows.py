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
