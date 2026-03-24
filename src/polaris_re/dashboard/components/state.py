"""Session state initialisation and validation helpers for the Polaris RE dashboard."""

import streamlit as st  # type: ignore[import-untyped]

__all__ = ["KEYS", "init_session_state"]

KEYS = [
    "inforce_block",
    "assumption_set",
    "projection_config",
    "gross_result",
    "mortality_source",
    "lapse_source",
    "ml_mortality_model",
    "ml_lapse_model",
]


def init_session_state() -> None:
    """Ensure all expected session-state keys exist with a default of None."""
    for key in KEYS:
        if key not in st.session_state:
            st.session_state[key] = None
