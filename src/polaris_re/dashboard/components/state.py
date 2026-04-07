"""Session state initialisation and validation helpers for the Polaris RE dashboard."""

import streamlit as st  # type: ignore[import-untyped]

__all__ = ["DEFAULTS", "KEYS", "get_deal_config", "init_session_state"]

KEYS = [
    "inforce_block",
    "assumption_set",
    "projection_config",
    "gross_result",
    "mortality_source",
    "lapse_source",
    "ml_mortality_model",
    "ml_lapse_model",
    "pricing_result",
    "pricing_net_result",
    "pricing_ceded_result",
    "pricing_treaty_type",
    # Centralised deal configuration — set on the Assumptions page
    "deal_config",
]

# Default deal configuration values (treaty, expenses, projection)
DEFAULTS: dict[str, object] = {
    "product_type": "TERM",
    "treaty_type": "YRT",
    "cession_pct": 0.90,
    "yrt_loading": 0.10,
    "yrt_rate_per_1000": None,  # None = derive from mortality
    "yrt_rate_basis": "Mortality-based",
    "modco_rate": 0.045,
    "discount_rate": 0.06,
    "hurdle_rate": 0.10,
    "projection_years": 20,
    "acquisition_cost": 500.0,
    "maintenance_cost": 75.0,
}


def init_session_state() -> None:
    """Ensure all expected session-state keys exist with a default of None."""
    for key in KEYS:
        if key not in st.session_state:
            st.session_state[key] = None
    # Initialise deal_config with defaults if not yet set
    if st.session_state["deal_config"] is None:
        st.session_state["deal_config"] = dict(DEFAULTS)


def get_deal_config() -> dict[str, object]:
    """Return the current deal configuration dict (never None)."""
    cfg = st.session_state.get("deal_config")
    if cfg is None:
        cfg = dict(DEFAULTS)
        st.session_state["deal_config"] = cfg
    return cfg
