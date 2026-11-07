"""D1 GAM section of the experience-improvement page (ADR-262): UI and run behaviour.

Own-criterion checks (no mgcv comparison): the section renders, the pre-run warning is shown
before any fit, a fit only runs on the explicit button, a refusal is shown by name and a
`bam` request it cannot serve is never replaced by `gam`.
"""

import polars as pl
import pytest

from polaris_re.dashboard.views.experience_improvement import _sample_cells
from polaris_re.dashboard.views.gam_fit_section import (
    effect_profiles,
    prepare_frame,
    run_gam_request,
)

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

APP = "src/polaris_re/dashboard/app.py"


def _data() -> pl.DataFrame:
    return prepare_frame(_sample_cells())


def test_prepare_frame_adds_log_exposure() -> None:
    assert "log_exposure" in _data().columns


def test_gam_run_fits_and_profiles() -> None:
    d = _data()
    f = 'death_count ~ s(attained_age, bs="cr", k=6) + offset(log_exposure)'
    res = run_gam_request(d, f, "poisson", "gam")
    assert res.fit is not None
    assert res.fit.converged
    prof = effect_profiles(res.fit, d, f)
    assert [p[0] for p in prof] == ["attained_age"]


def test_refusal_is_a_result_with_the_construct_named() -> None:
    res = run_gam_request(
        _data(), "death_count ~ te(attained_age, calendar_year)", "poisson", "gam"
    )
    assert res.fit is None
    assert "te" in (res.message or "")


def test_bam_is_not_silently_replaced_by_gam() -> None:
    res = run_gam_request(
        _data(),
        'death_count ~ s(attained_age, bs="cr", k=6) + offset(log_exposure)',
        "gaussian",
        "bam",
    )
    assert res.fit is None
    assert res.engine == "bam"


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_page_shows_warning_before_run_and_fits_only_on_click() -> None:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Mortality Improvement")
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in list(at.info) + list(at.warning))
    assert "Expected runtime" in text
    assert "Result — engine" not in " ".join(s.value for s in at.subheader)
    run = next(b for b in at.button if b.key == "gam_run")
    run.click()
    at.run()
    assert not at.exception
    assert any("Result — engine: gam" in s.value for s in at.subheader)


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_frame_without_q_base_still_offers_the_gam_section() -> None:
    def app() -> None:
        import polars as pl

        from polaris_re.dashboard.views.experience_improvement import (
            _missing_columns_fallback,
        )

        cells = pl.DataFrame(
            {
                "attained_age": [40, 41, 42, 43] * 5,
                "calendar_year": [2015] * 20,
                "death_count": [1.0, 2.0, 1.0, 3.0] * 5,
                "central_exposure": [1000.0] * 20,
            }
        )
        _missing_columns_fallback(cells, "count", {"q_base"})

    at = AppTest.from_function(app, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("skipped" in w.value for w in at.warning)
    assert any(b.key == "gam_run" for b in at.button)


def test_cloglog_link_is_kept_end_to_end(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import importlib.util
    import json
    from pathlib import Path

    from polaris_re.dashboard.views.gam_fit_section import FAMILY_CHOICES

    assert 'binomial(link="cloglog")' in FAMILY_CHOICES
    script = Path(__file__).parents[2] / "scripts" / "gam_dashboard_local_check.py"
    mod_spec = importlib.util.spec_from_file_location("local_check", script)
    assert mod_spec is not None and mod_spec.loader is not None
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)

    cell = tmp_path
    (cell / "spec.json").write_text(
        json.dumps({"formula": "y ~ s(x, bs='cr', k=5)", "family": 'binomial(link="cloglog")'})
    )
    assert mod._spec(cell) == ("y ~ s(x, bs='cr', k=5)", 'binomial(link="cloglog")')
    (cell / "spec.json").write_text(
        json.dumps({"formula": "y ~ s(x)", "family": "poisson", "weights": "w"})
    )
    with pytest.raises(SystemExit, match="weights"):
        mod._spec(cell)
    (cell / "spec.json").write_text(json.dumps({"formula": "y ~ s(x)", "family": "gamma"}))
    with pytest.raises(SystemExit, match="not one the page offers"):
        mod._spec(cell)


def test_cloglog_family_string_reaches_the_fit() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    x = rng.uniform(0, 1, 400)
    p = 1 - np.exp(-np.exp(-1.0 + 1.5 * x))
    df = pl.DataFrame({"x": x, "y": (rng.uniform(size=400) < p).astype(float)})
    res = run_gam_request(df, 'y ~ s(x, bs="cr", k=5)', 'binomial(link="cloglog")', "gam")
    assert res.fit is not None
    assert res.fit.model.link == "cloglog"


def test_default_formula_uses_q_base_offset_when_present() -> None:
    from polaris_re.dashboard.views.gam_fit_section import default_formula

    d = _data()
    assert "log_expected" in d.columns
    assert "offset(log_expected)" in default_formula(d)
    assert "offset(log_exposure)" in default_formula(d.drop("log_expected", "q_base"))


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_d2_page_shows_effects_surface_download_and_labelled_legacy_expander() -> None:
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Mortality Improvement")
    at.run()
    assert any(
        "Legacy model" in e.label and "not the HGAM" in e.label for e in at.expander
    )  # old views stay reachable, labelled
    next(b for b in at.button if b.key == "gam_run").click()
    at.run()
    assert not at.exception
    heads = " | ".join(s.value for s in at.subheader)
    assert "Partial effects — engine: gam" in heads
    assert "Improvement surface MI_x(y) — engine: gam" in heads
    assert any("not fed to pricing" in w.value for w in at.warning)
    assert len(at.get("download_button")) >= 1  # the HGAM MI surface download (AppTest: generic)


# ---------------------------------------------------------------------------
# R-04 regression: numerical warning filter
# ---------------------------------------------------------------------------


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_r04_numerical_warnings_suppressed_on_converged_fit() -> None:
    """When a fit converges, slogdet/overflow raw text must NOT appear on-screen.

    The fix: show a plain caption, not the raw NumPy warning text.
    Own-criterion check (not a parity comparison).
    """
    import streamlit as st  # noqa: F401 — verify streamlit available before test body

    from polaris_re.dashboard.views.gam_fit_section import GamRunResult, _show
    from polaris_re.gam import GamFit

    # Build a minimal converged fit stub by actually fitting a small model
    d = _data().head(80)
    res = run_gam_request(
        d,
        'death_count ~ s(attained_age, bs="cr", k=5) + offset(log_exposure)',
        "poisson",
        "gam",
    )
    if res.fit is None or not res.fit.converged:
        pytest.skip("fit did not converge on stub data — skip R-04 check")

    # Inject synthetic numerical warnings into a copy of the result
    numerical_res = GamRunResult(
        engine=res.engine,
        fit=res.fit,
        message=res.message,
        warnings_seen=(
            "overflow encountered in exp",
            "slogdet: matrix is near singular",
        ),
        seconds=res.seconds,
    )

    def _app() -> None:
        _show(numerical_res, d, 'death_count ~ s(attained_age, bs="cr", k=5) + offset(log_exposure)')

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Raw NumPy warning text must not appear in any warning widget
    warning_texts = " ".join(w.value for w in at.warning)
    assert "overflow" not in warning_texts
    assert "slogdet" not in warning_texts

    # A caption noting numerical events should appear
    caption_texts = " ".join(c.value for c in at.caption)
    assert "numerical events" in caption_texts.lower()


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_r04_numerical_warnings_in_expander_on_failed_convergence() -> None:
    """When a fit does NOT converge, raw numerical warnings must appear in an expander.

    Own-criterion check (not a parity comparison).
    """
    from polaris_re.dashboard.views.gam_fit_section import GamRunResult, _show
    from polaris_re.gam import GamFit
    from unittest.mock import MagicMock

    # Build a mock fit that is marked as not converged
    mock_fit = MagicMock(spec=GamFit)
    mock_fit.converged = False
    mock_fit.edf_total = 2.0
    mock_fit.n_function_evals = 10
    mock_fit.edf_per_term = {"s(attained_age)": 1.5}
    mock_fit.summary.side_effect = Exception("no summary")

    diverged_res = GamRunResult(
        engine="gam",
        fit=mock_fit,
        message=None,
        warnings_seen=("overflow encountered in exp", "slogdet: near singular"),
        seconds=0.1,
    )

    def _app() -> None:
        _show(diverged_res, _data().head(20), 'death_count ~ s(attained_age, bs="cr", k=4)')

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Raw warning text should appear inside an expander, not a bare warning widget
    # (AppTest surfaces expander labels; we check the label contains the key phrase)
    expander_labels = " ".join(e.label for e in at.expander)
    assert "did not converge" in expander_labels.lower() or "not converge" in expander_labels.lower()


# ---------------------------------------------------------------------------


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_surface_refusal_without_year_smooth_is_shown_by_name() -> None:
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Mortality Improvement")
    at.run()
    at.text_input(key="gam_formula_qbase").set_value(
        'death_count ~ s(attained_age, bs="cr", k=6) + offset(log_expected)'
    )
    at.run()
    next(b for b in at.button if b.key == "gam_run").click()
    at.run()
    assert not at.exception
    assert any("no smooth term of 'calendar_year'" in i.value for i in at.info)
