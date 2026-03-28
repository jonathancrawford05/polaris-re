"""Reusable chart helpers for the Polaris RE dashboard."""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np

__all__ = ["cashflow_waterfall", "scenario_tornado", "uq_histogram"]


def cashflow_waterfall(
    profit_by_year: np.ndarray,
    title: str = "Annual Profit Waterfall",
) -> plt.Figure:
    """Stacked waterfall chart of annual profits."""
    fig, ax = plt.subplots(figsize=(10, 5))
    years = np.arange(1, len(profit_by_year) + 1)
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in profit_by_year]
    ax.bar(years, profit_by_year, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Policy Year")
    ax.set_ylabel("Profit ($)")
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig


def uq_histogram(
    pv_profits: np.ndarray,
    var_95: float,
    cvar_95: float,
    base_pv_profit: float,
    title: str = "Monte Carlo PV Profit Distribution",
) -> plt.Figure:
    """Histogram of simulated PV profits with VaR/CVaR markers."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(pv_profits, bins=40, color="#3498db", edgecolor="white", linewidth=0.5, alpha=0.8)
    ax.axvline(
        var_95, color="#e74c3c", linestyle="--", linewidth=1.5, label=f"VaR 95%: ${var_95:,.0f}"
    )
    ax.axvline(
        cvar_95,
        color="#c0392b",
        linestyle=":",
        linewidth=1.5,
        label=f"CVaR 95%: ${cvar_95:,.0f}",
    )
    ax.axvline(
        base_pv_profit,
        color="#2ecc71",
        linestyle="-",
        linewidth=1.5,
        label=f"Base: ${base_pv_profit:,.0f}",
    )
    ax.set_xlabel("PV Profit ($)")
    ax.set_ylabel("Frequency")
    ax.set_title(title)
    ax.legend()
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig


def scenario_tornado(
    scenario_results: dict,  # type: ignore[type-arg]
    base_pv: float,
    title: str = "Scenario Sensitivity (PV Profit)",
) -> plt.Figure:
    """Tornado chart showing PV profit deviation from base for each scenario."""
    names = list(scenario_results.keys())
    deviations = [scenario_results[n].pv_profits - base_pv for n in names]

    # Sort by absolute deviation
    pairs = sorted(zip(deviations, names, strict=False), key=lambda x: abs(x[0]))
    deviations_sorted = [p[0] for p in pairs]
    names_sorted = [p[1] for p in pairs]

    fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.6)))
    colors = ["#2ecc71" if d >= 0 else "#e74c3c" for d in deviations_sorted]
    y_pos = np.arange(len(names_sorted))
    ax.barh(y_pos, deviations_sorted, color=colors, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names_sorted)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("PV Profit Deviation from Base ($)")
    ax.set_title(title)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    fig.tight_layout()
    return fig
