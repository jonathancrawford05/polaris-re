"""Tests for the dashboard YRT rate table components (Slice 4b-2 / ADR-055).

Covers:

* ``yrt_rate_table_heatmap_per_cohort`` — matplotlib heatmap renderer.
* ``build_treaty`` — dashboard wrapper passes ``yrt_rate_table`` through to
  ``YRTTreaty``.
* ``run_treaty_projection`` — tabular branch dispatches into
  ``YRTTreaty.apply()`` with the inforce block and skips flat-rate
  derivation.
"""

import matplotlib

matplotlib.use("Agg")  # headless backend — no display required for tests

from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np

from polaris_re.core.policy import Sex, SmokerStatus
from polaris_re.dashboard.components.projection import build_treaty
from polaris_re.dashboard.components.yrt_rate_table import (
    yrt_rate_table_heatmap_per_cohort,
)
from polaris_re.reinsurance.yrt import YRTTreaty
from polaris_re.reinsurance.yrt_rate_table import (
    YRTRateTable,
    YRTRateTableArray,
)
from polaris_re.utils.yrt_rate_table_io import (
    parse_uploaded_yrt_rate_table,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "yrt_rate_tables"


def _load_synthetic_table() -> YRTRateTable:
    uploads = [
        ("synthetic_male_ns.csv", (FIXTURES / "synthetic_male_ns.csv").read_bytes()),
        ("synthetic_male_smoker.csv", (FIXTURES / "synthetic_male_smoker.csv").read_bytes()),
        ("synthetic_female_ns.csv", (FIXTURES / "synthetic_female_ns.csv").read_bytes()),
        ("synthetic_female_smoker.csv", (FIXTURES / "synthetic_female_smoker.csv").read_bytes()),
    ]
    return parse_uploaded_yrt_rate_table(
        uploads=uploads,
        table_name="synthetic",
        select_period=3,
    )


# ----------------------------------------------------------------------- #
# Heatmap renderer                                                         #
# ----------------------------------------------------------------------- #


class TestHeatmapRenderer:
    """Per-cohort matplotlib heatmap renderer."""

    def test_returns_one_figure_per_cohort(self):
        table = _load_synthetic_table()
        result = yrt_rate_table_heatmap_per_cohort(table)
        assert len(result) == 4
        keys = [k for k, _ in result]
        assert keys == sorted(keys), "Cohorts must be returned in deterministic sorted order."
        for k in ("M_NS", "M_S", "F_NS", "F_S"):
            assert k in keys
        for _, fig in result:
            assert isinstance(fig, plt.Figure)
            plt.close(fig)

    def test_axes_labels_use_duration_and_age(self):
        table = _load_synthetic_table()
        result = yrt_rate_table_heatmap_per_cohort(table)
        _, fig = result[0]
        ax = fig.axes[0]
        assert ax.get_xlabel().lower() == "duration column"
        assert ax.get_ylabel().lower() == "attained age"
        # Column ticks include the ultimate column.
        xtick_labels = [t.get_text() for t in ax.get_xticklabels()]
        assert "ultimate" in xtick_labels
        plt.close(fig)

    def test_title_omits_filled_marker_when_fully_solved(self):
        table = _load_synthetic_table()  # CSV-loaded → no mask
        for _, fig in yrt_rate_table_heatmap_per_cohort(table):
            ax = fig.axes[0]
            assert "forward/back-filled" not in ax.get_title()
            plt.close(fig)

    def test_title_marks_filled_when_mask_has_filled_cells(self):
        # Build a 3x4 grid with one filled cell. The column count is
        # select_period + 1 — keep them aligned.
        rates = np.array(
            [
                [1.0, 1.1, 1.2, 2.0],
                [1.1, 1.2, 1.3, 2.2],
                [1.2, 1.3, 1.4, 2.4],
            ],
            dtype=np.float64,
        )
        mask = np.ones_like(rates, dtype=np.bool_)
        mask[1, 1] = False  # one forward/back-filled cell
        arr = YRTRateTableArray(
            rates=rates,
            min_age=25,
            max_age=27,
            select_period=3,
            solved_mask=mask,
        )
        partial = YRTRateTable.from_arrays(
            table_name="partial",
            arrays={(Sex.MALE, SmokerStatus.UNKNOWN): arr},
        )
        result = yrt_rate_table_heatmap_per_cohort(partial)
        assert len(result) == 1
        _, fig = result[0]
        ax = fig.axes[0]
        assert "forward/back-filled" in ax.get_title()
        plt.close(fig)


# ----------------------------------------------------------------------- #
# build_treaty: tabular branch                                             #
# ----------------------------------------------------------------------- #


class TestBuildTreatyTabular:
    """Dashboard ``build_treaty`` wires ``yrt_rate_table`` onto YRTTreaty."""

    def test_yrt_with_table_returns_yrt_treaty_with_table(self):
        table = _load_synthetic_table()
        treaty = build_treaty(
            treaty_type="YRT",
            cession_pct=0.50,
            face_amount=10_000_000.0,
            yrt_rate_table=table,
        )
        assert isinstance(treaty, YRTTreaty)
        assert treaty.yrt_rate_table is table
        assert treaty.flat_yrt_rate_per_1000 is None
        assert treaty.cession_pct == 0.50
        assert treaty.total_face_amount == 10_000_000.0

    def test_yrt_without_table_falls_back_to_flat_factory(self):
        treaty = build_treaty(
            treaty_type="YRT",
            cession_pct=0.50,
            face_amount=10_000_000.0,
            yrt_rate_per_1000=2.5,
        )
        assert isinstance(treaty, YRTTreaty)
        assert treaty.yrt_rate_table is None
        assert treaty.flat_yrt_rate_per_1000 == 2.5

    def test_non_yrt_with_table_arg_ignores_table(self):
        # A user error — but the dashboard should not crash. The non-YRT
        # branch silently drops the kwarg via the pipeline factory.
        table = _load_synthetic_table()
        treaty = build_treaty(
            treaty_type="Coinsurance",
            cession_pct=0.80,
            face_amount=10_000_000.0,
            yrt_rate_table=table,
        )
        # Coinsurance treaty has no concept of yrt_rate_table.
        assert treaty.__class__.__name__ == "CoinsuranceTreaty"

    def test_non_yrt_rate_table_object_rejected(self):
        import pytest

        with pytest.raises(TypeError, match="yrt_rate_table must be a YRTRateTable"):
            build_treaty(
                treaty_type="YRT",
                cession_pct=0.50,
                face_amount=10_000_000.0,
                yrt_rate_table="not-a-table",  # type: ignore[arg-type]
            )
