"""Page: Portfolio — multi-deal portfolio overview, concentration, scenarios, capital.

Provides two st.file_uploader widgets (YAML config + multi-file inforce
CSVs), an alignment-mode selectbox, a Run button, aggregate tiles, a
per-deal breakdown table, and three interactive sub-sections:
Concentration (ADR-069 / ADR-073), Scenarios (ADR-064), and LICAT
Capital (ADR-060 / ADR-072). Delegates to the Slice-1 loader
(load_portfolio_from_uploaded) — does not re-parse the config.

The Portfolio object is held in session state across reruns
(``portfolio_runtime``) so the Scenarios and Capital sub-sections can
re-invoke ``run_scenarios`` / ``run_with_capital`` without re-uploading
the config. The full result objects are stored under
``portfolio_result``, ``portfolio_scenarios``, and
``portfolio_capital_result`` (see ``components/state.py``).

The page is excluded from coverage (ADR-032 / pyproject.toml omit rule
for dashboard/*). Widget wiring is tested in
tests/qa/test_dashboard_flows.py::TestPortfolioPage* via session-state
injection, since AppTest cannot drive st.file_uploader directly.
"""

import csv
import io

import streamlit as st  # type: ignore[import-untyped]

from polaris_re.analytics.capital import LICATCapital
from polaris_re.analytics.portfolio import Portfolio, PortfolioResult
from polaris_re.analytics.scenario import ScenarioAdjustment, ScenarioRunner
from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.core.policy import ProductType
from polaris_re.dashboard.components.charts import (
    concentration_bar,
    portfolio_capital_chart,
)
from polaris_re.dashboard.components.portfolio_loader import load_portfolio_from_uploaded

__all__ = ["page_portfolio"]

_DIMENSIONS: tuple[str, ...] = ("cedant", "product", "treaty")
_BASES: tuple[str, ...] = ("ceded_face", "ceded_nar_peak", "pv_premium")
_BASIS_TITLES: dict[str, str] = {
    "ceded_face": "Ceded Face",
    "ceded_nar_peak": "Ceded NAR (peak)",
    "pv_premium": "PV Premiums",
}
_BASIS_COLORS: dict[str, str] = {
    "ceded_face": "#3498db",
    "ceded_nar_peak": "#e67e22",
    "pv_premium": "#27ae60",
}
_PRODUCT_TYPE_LABELS: dict[str, str] = {pt.value: pt.name for pt in ProductType}


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
                    st.session_state["portfolio_runtime"] = {
                        "portfolio": portfolio,
                        "hurdle_rate": hurdle_rate,
                        "align": align,
                    }
                    # Drop stale derived results — they belong to the previous run.
                    st.session_state["portfolio_scenarios"] = None
                    st.session_state["portfolio_capital_result"] = None
                    st.success(
                        f"Portfolio run complete — {run_result.n_deals} deals, "
                        f"total PV profits ${run_result.total_pv_profits:,.0f}."
                    )
                except (PolarisValidationError, PolarisComputationError) as exc:
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

    irr_note = _irr_explanation(result.total_irr)
    if irr_note:
        st.caption(irr_note)

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

    # ── Concentration sub-section ─────────────────────────────────────────────
    _render_concentration(result)

    # ── Scenarios sub-section ─────────────────────────────────────────────────
    _render_scenarios(result)

    # ── Capital sub-section ───────────────────────────────────────────────────
    _render_capital(result)


def _irr_explanation(irr: float | None) -> str | None:
    """Explanatory note when the aggregate portfolio IRR is undefined.

    Matches the ``views/pricing._irr_explanation`` pattern (ADR-041). The
    portfolio aggregate NCF often has no sign change — the reinsurer
    earns net premiums from day one with no upfront capital deployment —
    so the IRR root-finder returns ``None``. The capital-adjusted IRR
    surfaced in the Capital sub-section is the canonical portfolio IRR
    in that case.
    """
    if irr is not None:
        return None
    return (
        "Total IRR is undefined because the aggregate reinsurer net "
        "cash flow has no sign change (ADR-041). Enable **Include "
        "LICAT capital metrics** in the Capital sub-section below to "
        "surface the capital-adjusted IRR, which subtracts per-period "
        "capital strain and releases residual capital at the terminal "
        "month."
    )


def _render_concentration(result: PortfolioResult) -> None:
    """Concentration sub-section — dimension picker, multi-basis bars, HHI."""
    st.subheader("Concentration")
    st.caption(
        "Pick a grouping dimension to see how the book splits across its "
        "labels under three weight bases: ceded face, peak ceded NAR, and "
        "PV premiums (ADR-069)."
    )

    # ADR-073: this page is the primary consumer of concentration_by_dimension().
    by_dimension = result.concentration_by_dimension()
    hhi_by_dimension = result.hhi_by_dimension()

    if not by_dimension:
        st.info("Concentration metrics unavailable for this portfolio.")
        return

    dim_label_to_key = {"Cedant": "cedant", "Product": "product", "Treaty": "treaty"}
    dim_label = st.selectbox(
        "Group by",
        options=list(dim_label_to_key.keys()),
        key="portfolio_concentration_dim",
    )
    dim_key = dim_label_to_key[dim_label]

    shares_by_basis = by_dimension.get(dim_key, {})
    cols = st.columns(len(_BASES))
    for col, basis in zip(cols, _BASES, strict=True):
        shares = shares_by_basis.get(basis, {})
        with col:
            if shares:
                fig = concentration_bar(
                    shares,
                    title=f"{dim_label} — {_BASIS_TITLES[basis]}",
                    color=_BASIS_COLORS[basis],
                )
                st.pyplot(fig)
            else:
                st.caption(f"No data for {_BASIS_TITLES[basis]}.")

    st.markdown("**Herfindahl-Hirschman Index (HHI) by basis x dimension**")
    hhi_rows = []
    for basis in _BASES:
        row: dict[str, str] = {"Basis": _BASIS_TITLES[basis]}
        for dim in _DIMENSIONS:
            value = hhi_by_dimension.get(dim, {}).get(basis)
            row[dim.title()] = f"{value:.4f}" if value is not None else "N/A"
        hhi_rows.append(row)
    st.dataframe(hhi_rows, use_container_width=True)
    st.caption(
        "HHI ranges from 1/k (perfectly diversified across k labels) to "
        "1.0 (fully concentrated). Values above 0.25 indicate high "
        "concentration."
    )

    csv_bytes = _concentration_to_csv_bytes(by_dimension)
    st.download_button(
        "Export concentration as CSV",
        data=csv_bytes,
        file_name="portfolio_concentration.csv",
        mime="text/csv",
        key="portfolio_concentration_csv",
    )


def _concentration_to_csv_bytes(
    by_dimension: dict[str, dict[str, dict[str, float]]],
) -> bytes:
    """Flatten ``{dimension: {basis: {label: share}}}`` to long-format CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["dimension", "basis", "label", "share"])
    for dimension in sorted(by_dimension.keys()):
        for basis in sorted(by_dimension[dimension].keys()):
            for label, share in by_dimension[dimension][basis].items():
                writer.writerow([dimension, basis, label, f"{share:.6f}"])
    return buf.getvalue().encode("utf-8")


def _render_scenarios(result: PortfolioResult) -> None:
    """Scenarios sub-section — standard six-scenario stress + worst-case callout."""
    st.subheader("Scenarios")
    st.caption(
        "Apply correlated mortality / lapse stresses to every deal "
        "simultaneously, then re-aggregate (ADR-064). The shape matches "
        "`polaris portfolio scenarios`."
    )

    runtime = st.session_state.get("portfolio_runtime")
    standard = ScenarioRunner.standard_stress_scenarios()
    standard_names = [s.name for s in standard]

    selected = st.multiselect(
        "Scenarios",
        options=standard_names,
        default=standard_names,
        key="portfolio_scenario_picker",
    )

    if st.button("Run scenarios", key="portfolio_run_scenarios"):
        if runtime is None:
            st.warning(
                "Scenario runner needs the live Portfolio object. Re-run "
                "the portfolio above (Upload & Run) before running scenarios."
            )
        elif not selected:
            st.error("Select at least one scenario.")
        else:
            portfolio: Portfolio = runtime["portfolio"]
            hurdle_rate: float = runtime["hurdle_rate"]
            align: str = runtime["align"]
            scenarios_to_run: list[ScenarioAdjustment] = [
                s for s in standard if s.name in set(selected)
            ]
            with st.spinner("Running scenarios…"):
                try:
                    scen_result = portfolio.run_scenarios(
                        hurdle_rate, scenarios_to_run, align=align
                    )
                    st.session_state["portfolio_scenarios"] = scen_result
                except (PolarisValidationError, PolarisComputationError) as exc:
                    st.error(f"Scenario error: {exc}")

    scen_result = st.session_state.get("portfolio_scenarios")
    if scen_result is None:
        return

    rows: list[dict[str, object]] = []
    for name, scen_r in scen_result.scenarios:
        rows.append(
            {
                "Scenario": name,
                "PV Profits": f"${scen_r.total_pv_profits:,.0f}",
                "IRR": (f"{scen_r.total_irr:.2%}" if scen_r.total_irr is not None else "N/A"),
                "Profit Margin": (
                    f"{scen_r.profit_margin:.2%}" if scen_r.profit_margin is not None else "N/A"
                ),
                "Peak Ceded NAR": f"${scen_r.peak_ceded_nar:,.0f}",
            }
        )
    # Pin BASE at the top so it reads as the reference line.
    rows.sort(key=lambda row: 0 if row["Scenario"] == "BASE" else 1)
    st.dataframe(rows, use_container_width=True)
    if any(row["Scenario"] == "BASE" for row in rows):
        st.caption("BASE row is the unstressed reference; other rows are deviations from BASE.")

    worst = scen_result.worst_case()
    if worst is None:
        st.info("Worst case: N/A (no scenario has a comparable IRR).")
    else:
        worst_name, worst_r = worst
        st.warning(
            f"**Worst case:** {worst_name} — Total IRR "
            f"{worst_r.total_irr:.2%}, PV Profits "
            f"${worst_r.total_pv_profits:,.0f}."
        )


def _render_capital(result: PortfolioResult) -> None:
    """LICAT capital sub-section — tiles + capital-by-period chart."""
    st.subheader("LICAT Capital")
    st.caption(
        "Apply a single LICAT factor schedule to the aggregate cash flow "
        "(ADR-060). The interim schedule populates C-1 / C-3 placeholders "
        "alongside the C-2 components (ADR-072)."
    )

    runtime = st.session_state.get("portfolio_runtime")

    include = st.checkbox(
        "Include LICAT capital metrics",
        value=st.session_state.get("portfolio_capital_result") is not None,
        key="portfolio_capital_toggle",
    )
    product_choices = list(_PRODUCT_TYPE_LABELS.keys())
    default_idx = product_choices.index("TERM") if "TERM" in product_choices else 0
    product_value = st.selectbox(
        "LICAT product factor schedule",
        options=product_choices,
        index=default_idx,
        format_func=lambda v: _PRODUCT_TYPE_LABELS[v],
        help=(
            "Portfolio.run_with_capital applies one LICATCapital model to "
            "the aggregate cash flow. For a mixed-product book, the "
            "selected product's interim factors are applied uniformly — "
            "pick the dominant exposure (ADR-060 out-of-scope: per-deal "
            "factor maps)."
        ),
        key="portfolio_capital_product",
    )

    if include and st.button("Compute LICAT capital", key="portfolio_run_capital"):
        if runtime is None:
            st.warning(
                "Capital sub-section needs the live Portfolio object. Re-run "
                "the portfolio above (Upload & Run) before computing capital."
            )
        else:
            portfolio: Portfolio = runtime["portfolio"]
            hurdle_rate: float = runtime["hurdle_rate"]
            align: str = runtime["align"]
            try:
                product_type_enum = ProductType(product_value)
            except ValueError:
                product_type_enum = ProductType.TERM
            capital_model = LICATCapital.for_product_interim(product_type_enum)
            with st.spinner("Computing LICAT capital…"):
                try:
                    capital_result = portfolio.run_with_capital(
                        hurdle_rate, capital_model, align=align
                    )
                    st.session_state["portfolio_capital_result"] = capital_result
                except (PolarisValidationError, PolarisComputationError) as exc:
                    st.error(f"Capital error: {exc}")

    if not include:
        st.session_state["portfolio_capital_result"] = None
        return

    capital_result = st.session_state.get("portfolio_capital_result")
    if capital_result is None:
        st.info(
            "Click **Compute LICAT capital** to roll the chosen interim "
            "factor schedule onto the aggregate cash flow."
        )
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Initial Capital", f"${capital_result.initial_capital:,.0f}")
    c2.metric("Peak Capital", f"${capital_result.peak_capital:,.0f}")
    c3.metric("PV Capital", f"${capital_result.pv_capital:,.0f}")

    c4, c5 = st.columns(2)
    roc_str = (
        f"{capital_result.return_on_capital:.2%}"
        if capital_result.return_on_capital is not None
        else "N/A"
    )
    c4.metric(
        "Return on Capital",
        roc_str,
        help="PV(Total Profits) / PV(Required Capital) at the hurdle rate (ADR-048).",
    )
    cai_str = (
        f"{capital_result.capital_adjusted_irr:.2%}"
        if capital_result.capital_adjusted_irr is not None
        else "N/A"
    )
    c5.metric(
        "Capital-Adjusted IRR",
        cai_str,
        help=(
            "IRR of distributable cash flow (NCF - capital strain) with "
            "terminal release of residual capital. Canonical portfolio IRR "
            "for a book with capital deployment (ADR-060)."
        ),
    )

    if capital_result.capital_by_period.size > 0:
        st.pyplot(portfolio_capital_chart(capital_result.capital_by_period))
