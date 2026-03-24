"""
Polaris RE Interactive Dashboard (Streamlit).

Main entry point — configures the page, initialises session state,
and delegates to per-page modules via sidebar navigation.

Run with:
    streamlit run src/polaris_re/dashboard/app.py
"""

import sys

# Streamlit is an optional dependency — check at runtime
try:
    import streamlit as st  # type: ignore[import-untyped]

    _STREAMLIT_AVAILABLE = True
except ImportError:
    _STREAMLIT_AVAILABLE = False

try:
    import matplotlib  # type: ignore[import-untyped]  # noqa: F401

    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False


def _check_deps() -> None:
    """Verify required optional dependencies are installed."""
    if not _STREAMLIT_AVAILABLE:
        print(
            "Streamlit is required for the dashboard. Install with:\n"
            "    pip install streamlit\n"
            "or:\n"
            "    uv pip install streamlit",
            file=sys.stderr,
        )
        sys.exit(1)
    if not _MATPLOTLIB_AVAILABLE:
        print("matplotlib is required for charts. Install with: pip install matplotlib")
        sys.exit(1)


def main() -> None:
    """Launch the Polaris RE Streamlit dashboard."""
    _check_deps()

    from polaris_re.dashboard.components.state import init_session_state
    from polaris_re.dashboard.pages.assumptions import page_assumptions
    from polaris_re.dashboard.pages.ifrs17 import page_ifrs17
    from polaris_re.dashboard.pages.inforce import page_inforce
    from polaris_re.dashboard.pages.pricing import page_pricing
    from polaris_re.dashboard.pages.scenario import page_scenario
    from polaris_re.dashboard.pages.treaty_compare import page_treaty_compare
    from polaris_re.dashboard.pages.uq import page_uq

    st.set_page_config(
        page_title="Polaris RE Dashboard",
        page_icon="\U0001f3d4",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()

    st.sidebar.title("Polaris RE")
    st.sidebar.caption("Life Reinsurance Pricing Engine")

    page = st.sidebar.radio(
        "Navigation",
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

    if page == "Inforce Block":
        page_inforce()
    elif page == "Assumptions":
        page_assumptions()
    elif page == "Deal Pricing":
        page_pricing()
    elif page == "Treaty Comparison":
        page_treaty_compare()
    elif page == "Scenario Analysis":
        page_scenario()
    elif page == "Monte Carlo UQ":
        page_uq()
    elif page == "IFRS 17":
        page_ifrs17()


if __name__ == "__main__":
    main()
