"""Dashboard renderers for the YRT rate table (Slice 4b-2 / ADR-055).

The Streamlit dashboard previews uploaded ``YRTRateTable`` instances as a
heatmap (one matplotlib figure per cohort) so users can sanity-check the
rate surface before running a deal. Cells whose rate was forward/back-
filled by ``YRTRateSchedule.generate_table()`` (ADR-054) are visually
disclosed via a hatched overlay; CSV-loaded uploads carry no
``solved_mask`` and render as a plain heatmap.

The renderer returns figures (rather than calling ``st.pyplot`` directly)
so the same helper is testable headlessly via ``matplotlib.figure.Figure``.
"""

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.ticker as mticker  # type: ignore[import-untyped]
import numpy as np

from polaris_re.reinsurance.yrt_rate_table import YRTRateTable

__all__ = ["yrt_rate_table_heatmap_per_cohort"]


def yrt_rate_table_heatmap_per_cohort(table: YRTRateTable) -> list[tuple[str, plt.Figure]]:
    """Render one matplotlib heatmap per (sex, smoker) cohort.

    Each figure shows the rate grid as a 2-D ``imshow`` with attained age
    on the y-axis and duration column (``dur_1..dur_N``, ``ultimate``) on
    the x-axis. Cells flagged as forward/back-filled by ``solved_mask``
    (ADR-054) get a hatched overlay so reviewers can visually distinguish
    interpolated rows from solved rows.

    Args:
        table: Validated ``YRTRateTable``.

    Returns:
        List of ``(cohort_key, figure)`` tuples, sorted by cohort key for
        deterministic display order. Callers (typically
        ``views/assumptions.py``) iterate and call ``st.pyplot(fig)`` /
        ``plt.close(fig)`` for each entry.
    """
    out: list[tuple[str, plt.Figure]] = []
    select_period = table.select_period_years
    column_labels = [f"dur_{i}" for i in range(1, select_period + 1)] + ["ultimate"]

    for cohort_key in sorted(table.arrays.keys()):
        arr = table.arrays[cohort_key]
        n_ages, n_cols = arr.rates.shape
        ages = np.arange(arr.min_age, arr.max_age + 1)

        # Width grows modestly with column count so wide select periods stay
        # legible; height grows with age count so a 60-row block is not crammed
        # into a stamp-sized axis.
        fig_w = max(6.0, 0.5 * n_cols + 4.0)
        fig_h = max(3.5, 0.18 * n_ages + 1.5)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))

        im = ax.imshow(
            arr.rates,
            aspect="auto",
            origin="upper",
            cmap="viridis",
            interpolation="nearest",
        )
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.2f}"))
        cbar.set_label("Rate ($/$1,000 NAR / year)", fontsize=8)

        # Hatched overlay for filled cells. ``imshow`` does not support a
        # ``hatch`` kwarg, so we draw ``Rectangle`` patches — the hatching
        # is a provenance disclosure rather than a value-hiding mask, so
        # the underlying viridis colour stays visible. ``generate_table``
        # currently broadcasts solver provenance row-wise (entire rows are
        # either solved or filled — ADR-051 / ADR-053), so we draw one
        # full-row patch per filled row instead of N patches per cell.
        # The fallback per-cell loop handles future per-duration solvers
        # whose mask is genuinely 2-D.
        if arr.solved_mask is not None and not arr.is_fully_solved:
            filled = ~arr.solved_mask
            row_uniform = bool(np.all(filled == filled[:, [0]]))
            if row_uniform:
                for i in range(n_ages):
                    if filled[i, 0]:
                        ax.add_patch(
                            plt.Rectangle(  # type: ignore[attr-defined]
                                (-0.5, i - 0.5),
                                n_cols,
                                1,
                                fill=False,
                                hatch="//",
                                edgecolor="white",
                                linewidth=0.5,
                            )
                        )
            else:
                for i in range(n_ages):
                    for j in range(n_cols):
                        if filled[i, j]:
                            ax.add_patch(
                                plt.Rectangle(  # type: ignore[attr-defined]
                                    (j - 0.5, i - 0.5),
                                    1,
                                    1,
                                    fill=False,
                                    hatch="//",
                                    edgecolor="white",
                                    linewidth=0.5,
                                )
                            )

        ax.set_xticks(np.arange(n_cols))
        ax.set_xticklabels(column_labels, rotation=45, ha="right", fontsize=8)
        # Tick every 5 years so a 60-row block stays legible.
        age_tick_step = max(1, n_ages // 12)
        age_tick_positions = np.arange(0, n_ages, age_tick_step)
        ax.set_yticks(age_tick_positions)
        ax.set_yticklabels(ages[age_tick_positions], fontsize=8)
        ax.set_xlabel("Duration column", fontsize=9)
        ax.set_ylabel("Attained age", fontsize=9)
        title = f"YRT Rate Heatmap — cohort {cohort_key}"
        if arr.solved_mask is not None and not arr.is_fully_solved:
            title += " (✧ = forward/back-filled, ADR-054)"
        ax.set_title(title, fontsize=10)
        fig.tight_layout()
        out.append((cohort_key, fig))

    return out
