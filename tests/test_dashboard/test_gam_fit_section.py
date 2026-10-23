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
