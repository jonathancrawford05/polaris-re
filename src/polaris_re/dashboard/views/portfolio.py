"""Page: Portfolio — multi-deal portfolio overview and per-deal breakdown.

Provides two st.file_uploader widgets (YAML config + multi-file inforce
CSVs), an alignment-mode selectbox, a Run button, aggregate tiles, and a
per-deal breakdown table. Delegates to the Slice-1 loader
(load_portfolio_from_uploaded) — does not re-parse the config.

The page is excluded from coverage (ADR-032 / pyproject.toml omit rule
for dashboard/*). Widget wiring is tested in
tests/qa/test_dashboard_flows.py::TestPortfolioPage via session-state
injection, since AppTest cannot drive st.file_uploader directly.
"""

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.dashboard.components.portfolio_loader import load_portfolio_from_uploaded

__all__ = ["page_portfolio"]


def page_portfolio() -> None:
    """Portfolio page — multi-deal overview and per-deal breakdown."""
    st.header("Portfolio Analysis")

    # ── Upload & Run section ──────────────────────────────────────────────────
    st.subheader("Upload & Run")
    col1, col2 = st.columns(2)
    with col1:
        yaml_file = st.file_uploader(
            "Portfolio config (YAML or JSON)",
            type=["yaml", "yml", "json"],
            key="portfolio_yaml_upload",
            help="The same YAML/JSON config accepted by `polaris portfolio run --config`.",
        )
    with col2:
        csv_files = st.file_uploader(
            "Inforce CSVs (one per deal)",
            type=["csv"],
            accept_multiple_files=True,
            key="portfolio_csv_upload",
            help="Upload all per-deal inforce CSVs referenced by the config.",
        )

    align = st.selectbox(
        "Alignment mode",
        options=["strict", "calendar"],
        help=(
            "**strict**: all deals must share a valuation date; cash flows "
            "sum month-by-month and aggregate PV equals the sum of per-deal "
            "PVs. "
            "**calendar**: deals are placed on a common monthly grid keyed "
            "off the earliest valuation date, accommodating staggered "
            "treaty inception dates (ADR-061/062). Per-deal grid_offset "
            "values appear in the breakdown table."
        ),
    )

    if st.button("Run portfolio", type="primary"):
        if yaml_file is None:
            st.error("Upload a portfolio config (YAML/JSON) before running.")
        elif not csv_files:
            st.error("Upload at least one inforce CSV before running.")
        else:
            with st.spinner("Running portfolio…"):
                try:
                    yaml_text = yaml_file.read().decode()
                    csv_dict = {f.name: f.read() for f in csv_files}
                    portfolio, hurdle_rate = load_portfolio_from_uploaded(yaml_text, csv_dict)
                    run_result = portfolio.run(hurdle_rate, align=align)
                    st.session_state["portfolio_result"] = run_result
                    st.success(
                        f"Portfolio run complete — {run_result.n_deals} deals, "
                        f"total PV profits ${run_result.total_pv_profits:,.0f}."
                    )
                except PolarisValidationError as exc:
                    st.error(f"Portfolio error: {exc}")

    # ── Render result from session state ─────────────────────────────────────
    result = st.session_state.get("portfolio_result")
    if result is None:
        st.info(
            "Upload a portfolio config and inforce CSVs, then click "
            "**Run portfolio** to see aggregate metrics and the per-deal "
            "breakdown."
        )
        return

    # ── Aggregate tiles ───────────────────────────────────────────────────────
    st.subheader("Overview")

    t1, t2, t3 = st.columns(3)
    t1.metric("Deals", str(result.n_deals))
    t2.metric("Total Ceded Face", f"${result.total_ceded_face:,.0f}")
    t3.metric("Total PV Profits", f"${result.total_pv_profits:,.0f}")

    t4, t5, t6 = st.columns(3)
    irr_str = f"{result.total_irr:.2%}" if result.total_irr is not None else "N/A"
    t4.metric(
        "Total IRR",
        irr_str,
        help=(
            "IRR of the aggregate reinsurer net cash flow. N/A when the "
            "aggregate NCF has no sign change (ADR-041)."
        ),
    )
    margin_str = f"{result.profit_margin:.2%}" if result.profit_margin is not None else "N/A"
    t5.metric(
        "Profit Margin",
        margin_str,
        help="PV(Aggregate NCF) / PV(Aggregate Premiums) at the hurdle rate.",
    )
    t6.metric(
        "Peak Ceded NAR",
        f"${result.peak_ceded_nar:,.0f}",
        help="Maximum aggregate ceded net-amount-at-risk across the projection.",
    )

    # ── Calendar alignment info ───────────────────────────────────────────────
    grid_origin = result.aggregate_cash_flow.valuation_date
    any_offset = any(dr.grid_offset != 0 for dr in result.deal_results)
    if any_offset:
        st.info(
            f"Grid origin: **{grid_origin.isoformat()}** (earliest deal "
            f"valuation date). Per-deal offsets (months from origin) are "
            f"shown in the table below."
        )

    # ── Per-deal breakdown table ──────────────────────────────────────────────
    st.subheader("Per-Deal Breakdown")

    rows: list[dict[str, object]] = []
    for dr in result.deal_results:
        row: dict[str, object] = {
            "Deal ID": dr.deal_id,
            "Cedant": dr.cedant,
            "Product": dr.product_type,
            "Treaty": dr.treaty_type,
            "Policies": dr.n_policies,
            "Face Amount": f"${dr.face_amount:,.0f}",
            "Ceded Face": f"${dr.ceded_face:,.0f}",
            "PV Profits": f"${dr.profit_test.pv_profits:,.0f}",
            "IRR": (f"{dr.profit_test.irr:.2%}" if dr.profit_test.irr is not None else "N/A"),
            "Profit Margin": (
                f"{dr.profit_test.profit_margin:.2%}"
                if dr.profit_test.profit_margin is not None
                else "N/A"
            ),
        }
        if any_offset:
            row["Grid Offset (months)"] = dr.grid_offset
        rows.append(row)

    st.dataframe(rows, use_container_width=True)
