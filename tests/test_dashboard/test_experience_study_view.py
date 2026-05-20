"""Tests for the Experience Study dashboard view (ADR-056).

Covers the helper functions in
``polaris_re.dashboard.views.experience_study``:

- ``_sample_data`` returns a Polars DataFrame with the required columns
  and at least one grouping dimension.
- ``_read_uploaded_csv`` parses an uploaded CSV's bytes into a Polars
  DataFrame.
- ``_ae_bar_chart`` returns a matplotlib Figure with a horizontal
  reference at A/E = 1.0 and one bar per group row.

End-to-end AppTest coverage lives in
``tests/qa/test_dashboard_flows.py::TestExperienceStudyPage`` so that
the heavy Streamlit harness only spins up when the QA suite runs.
"""

import numpy as np
import polars as pl
import pytest

from polaris_re.dashboard.views.experience_study import (
    REQUIRED_COLUMNS,
    _ae_bar_chart,
    _composite_group_labels,
    _multiplier_chart,
    _read_uploaded_csv,
    _sample_data,
)


class _FakeUpload:
    """Minimal stand-in for ``streamlit.runtime.uploaded_file_manager.UploadedFile``."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


class TestSampleData:
    def test_has_required_columns(self) -> None:
        df = _sample_data()
        for col in REQUIRED_COLUMNS:
            assert col in df.columns, f"sample data missing required column {col!r}"

    def test_has_grouping_dimensions(self) -> None:
        df = _sample_data()
        # At least one categorical grouping dimension besides the required cols.
        non_required = [c for c in df.columns if c not in REQUIRED_COLUMNS]
        assert non_required, "sample data has no grouping columns"

    def test_actuals_and_expecteds_are_finite(self) -> None:
        df = _sample_data()
        for col in ("actual", "expected", "exposure"):
            arr = df[col].to_numpy()
            assert np.isfinite(arr).all(), f"{col} contains non-finite values"
            assert (arr >= 0.0).all(), f"{col} has negative entries"


class TestReadUploadedCsv:
    def test_parses_minimal_csv(self) -> None:
        csv_bytes = b"actual,expected,exposure\n10,9,1000\n20,22,2000\n"
        df = _read_uploaded_csv(_FakeUpload(csv_bytes))
        assert df.shape == (2, 3)
        assert set(df.columns) == REQUIRED_COLUMNS
        np.testing.assert_allclose(df["actual"].to_numpy(), [10.0, 20.0])

    def test_parses_csv_with_dimensions(self) -> None:
        csv_bytes = b"sex,actual,expected,exposure\nM,10,9,1000\nF,8,10,1000\n"
        df = _read_uploaded_csv(_FakeUpload(csv_bytes))
        assert "sex" in df.columns
        assert df["sex"].to_list() == ["M", "F"]


class TestAEBarChart:
    def test_returns_figure_with_one_bar_per_row(self) -> None:
        summary = pl.DataFrame(
            {
                "sex": ["M", "F"],
                "ae_ratio": [1.10, 0.85],
            }
        )
        fig = _ae_bar_chart(summary, ["sex"])
        assert fig is not None
        ax = fig.axes[0]
        # Bars: matplotlib renders one Rectangle per bar (plus the chart frame).
        bars = list(ax.patches)
        assert len(bars) == 2
        # The reference A/E=1.0 line is drawn via axhline which inserts a Line2D.
        ylines = [line for line in ax.get_lines() if line.get_linestyle() == "--"]
        assert ylines, "expected dashed reference line at A/E=1.0"

    def test_handles_single_row_summary(self) -> None:
        summary = pl.DataFrame({"sex": ["M"], "ae_ratio": [1.0]})
        fig = _ae_bar_chart(summary, ["sex"])
        assert fig is not None
        ax = fig.axes[0]
        bars = list(ax.patches)
        assert len(bars) == 1


class TestMultiDimensionGrouping:
    """Regression: charting with multiple group-by dimensions must produce
    one bar per (dim_1, dim_2, ...) combination, not collapse the repeated
    first-dimension values onto a single x tick.

    This is the bug reported on the Experience Study page: grouping the
    sample data by both `sex` and `age` produced charts where the per-age
    bars within one sex overplotted onto the same categorical position.
    """

    def test_composite_labels_unique_per_row(self) -> None:
        summary = pl.DataFrame(
            {
                "sex": ["M", "M", "F", "F"],
                "age": [35, 40, 35, 40],
                "ae_ratio": [1.1, 0.9, 1.2, 0.8],
            }
        )
        labels = _composite_group_labels(summary, ["sex", "age"])
        assert labels == ["M / 35", "M / 40", "F / 35", "F / 40"]
        assert len(set(labels)) == len(labels), "composite labels must be unique per row"

    def test_composite_labels_single_dimension(self) -> None:
        summary = pl.DataFrame({"sex": ["M", "F"], "ae_ratio": [1.0, 1.1]})
        assert _composite_group_labels(summary, ["sex"]) == ["M", "F"]

    def test_ae_bar_chart_one_bar_per_combination(self) -> None:
        """4 (sex, age) combinations must yield 4 bars, not 2."""
        import matplotlib.pyplot as plt

        summary = pl.DataFrame(
            {
                "sex": ["M", "M", "F", "F"],
                "age": [35, 40, 35, 40],
                "ae_ratio": [1.1, 0.9, 1.2, 0.8],
            }
        )
        fig = _ae_bar_chart(summary, ["sex", "age"])
        ax = fig.axes[0]
        assert len(list(ax.patches)) == 4
        # Each bar must sit at its own x position.
        assert len(ax.get_xticks()) == 4
        plt.close(fig)

    def test_multiplier_chart_one_pair_per_combination(self) -> None:
        """2 bar series x 4 combinations must yield 8 rectangles."""
        import matplotlib.pyplot as plt

        summary = pl.DataFrame(
            {
                "sex": ["M", "M", "F", "F"],
                "age": [35, 40, 35, 40],
                "ae_ratio": [1.1, 0.9, 1.2, 0.8],
                "multiplier": [1.05, 0.95, 1.10, 0.90],
            }
        )
        fig = _multiplier_chart(summary, ["sex", "age"])
        ax = fig.axes[0]
        assert len(list(ax.patches)) == 8
        plt.close(fig)


class TestRequiredColumnsConstant:
    def test_matches_experience_study_engine(self) -> None:
        from polaris_re.analytics.experience_study import ExperienceStudy

        # The view's REQUIRED_COLUMNS must be the same set the engine validates,
        # otherwise the user could upload a CSV that the view accepts but the
        # engine rejects (or vice versa).
        assert REQUIRED_COLUMNS == ExperienceStudy.REQUIRED_COLUMNS


class TestSampleDataDrivesEngine:
    """The sample data shipped with the page must produce a non-trivial A/E
    when handed to the engine. Otherwise the demo path is misleading."""

    def test_sample_runs_and_produces_finite_ae(self) -> None:
        from polaris_re.analytics.experience_study import ExperienceStudy

        df = _sample_data()
        study = ExperienceStudy(df)
        result = study.run()
        assert np.isfinite(result.overall_ae)
        assert result.total_actual > 0
        assert result.total_expected > 0

    @pytest.mark.parametrize("dim", ["sex"])
    def test_sample_groupby_runs(self, dim: str) -> None:
        from polaris_re.analytics.experience_study import ExperienceStudy

        df = _sample_data()
        if dim not in df.columns:
            pytest.skip(f"sample data does not include dimension {dim!r}")
        study = ExperienceStudy(df)
        result = study.run(group_by=[dim])
        assert len(result.summary) >= 1


class TestUploadRoundTrip:
    """An upload round-trip — bytes → DataFrame → ExperienceStudy.run() — should
    produce numerically identical A/E to a directly-constructed DataFrame."""

    def test_upload_matches_direct_construction(self) -> None:
        from polaris_re.analytics.experience_study import ExperienceStudy

        csv_bytes = b"actual,expected,exposure\n50,40,5000\n80,100,10000\n"
        df_upload = _read_uploaded_csv(_FakeUpload(csv_bytes))
        df_direct = pl.DataFrame(
            {
                "actual": [50.0, 80.0],
                "expected": [40.0, 100.0],
                "exposure": [5000.0, 10000.0],
            }
        )
        ae_upload = ExperienceStudy(df_upload).run().overall_ae
        ae_direct = ExperienceStudy(df_direct).run().overall_ae
        np.testing.assert_allclose(ae_upload, ae_direct, rtol=1e-12)


class TestAEBarChartCleanup:
    """Smoke test that closing the figure does not crash; matplotlib state
    should not leak across page invocations."""

    def test_close_after_creation(self) -> None:
        import matplotlib.pyplot as plt

        summary = pl.DataFrame({"sex": ["M", "F"], "ae_ratio": [1.0, 1.1]})
        fig = _ae_bar_chart(summary, ["sex"])
        plt.close(fig)
        assert not plt.get_fignums() or fig.number not in plt.get_fignums()
