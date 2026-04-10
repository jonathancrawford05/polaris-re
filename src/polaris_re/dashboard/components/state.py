"""Session state initialisation and validation helpers for the Polaris RE dashboard."""

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.core.pipeline import DealConfig

__all__ = [
    "DEFAULTS",
    "KEYS",
    "get_deal_config",
    "init_session_state",
    "require_single_product_cohort",
]

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

# Default deal configuration values — derived from the shared DealConfig
# so CLI and dashboard can never drift. DealConfig is the single source of truth.
DEFAULTS: dict[str, object] = DealConfig().to_dict()


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


def require_single_product_cohort(inforce: object, page_name: str) -> bool:
    """Warn and return False if the inforce block has more than one product type.

    Used by dashboard pages that operate on a single aggregated
    CashFlowResult (Scenario, Monte Carlo UQ, IFRS17, Treaty Comparison)
    and cannot coherently combine cash flows across product types. The
    Deal Pricing page is cohort-aware and does NOT use this guard.

    Returns:
        True if the block is homogeneous (page should proceed), False
        otherwise (page should return after the guard is shown).
    """
    product_types = getattr(inforce, "product_types", None)
    if product_types is None or len(product_types) <= 1:
        return True
    detected = ", ".join(sorted(pt.value for pt in product_types))
    st.warning(
        f"**{page_name}** does not support mixed product-type blocks "
        f"(detected: {detected}). Run **Deal Pricing** for a cohort-aware "
        f"view, or reload Page 1 with a CSV filtered to a single "
        f"`product_type` first."
    )
    return False
