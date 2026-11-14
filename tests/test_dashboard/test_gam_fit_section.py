"""D1 GAM section of the experience-improvement page (ADR-262): UI and run behaviour.

Own-criterion checks (no mgcv comparison): the section renders, the pre-run warning is shown
before any fit, a fit only runs on the explicit button, a refusal is shown by name and a
`bam` request it cannot serve is never replaced by `gam`.
"""

import dataclasses

import polars as pl
import pytest

from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.dashboard.views.experience_improvement import _sample_cells
from polaris_re.dashboard.views.gam_fit_section import (
    GamRunResult,
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


# R-04 regression: numerical warning filter
# ---------------------------------------------------------------------------

_R04_FORMULA = 'death_count ~ s(attained_age, bs="cr", k=5) + offset(log_exposure)'
_R04_NUMERICAL = ("overflow encountered in exp", "slogdet: matrix is near singular")


def _show_app(res: "GamRunResult", data: "pl.DataFrame", formula: str) -> None:
    """AppTest script body. ``AppTest.from_function`` runs only this function's source,
    so everything it needs is imported inside it or passed in through ``args`` (the
    annotations are quoted because the script namespace has no module imports)."""
    from polaris_re.dashboard.views.gam_fit_section import _show

    _show(res, data, formula)


def _r04_result(*, converged: bool) -> tuple[GamRunResult, pl.DataFrame]:
    d = _data().head(80)
    res = run_gam_request(d, _R04_FORMULA, "poisson", "gam")
    if res.fit is None or not res.fit.converged:
        pytest.skip("fit did not converge on stub data — skip R-04 check")
    fit = res.fit if converged else dataclasses.replace(res.fit, converged=False)
    return (
        GamRunResult(
            engine=res.engine,
            fit=fit,
            message=res.message,
            warnings_seen=_R04_NUMERICAL,
            seconds=res.seconds,
        ),
        d,
    )


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_r04_numerical_warnings_suppressed_on_converged_fit() -> None:
    """When a fit converges, slogdet/overflow raw text must NOT appear on-screen; a plain
    caption is shown instead. Own-criterion check (not a parity comparison)."""
    res, d = _r04_result(converged=True)
    at = AppTest.from_function(_show_app, args=(res, d, _R04_FORMULA), default_timeout=60)
    at.run()
    assert not at.exception

    warning_texts = " ".join(w.value for w in at.warning)
    assert "overflow" not in warning_texts
    assert "slogdet" not in warning_texts
    assert not any("did not converge" in e.label.lower() for e in at.expander)

    caption_texts = " ".join(c.value for c in at.caption)
    assert "numerical events" in caption_texts.lower()


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_r04_numerical_warnings_in_expander_on_failed_convergence() -> None:
    """When a fit does NOT converge, the raw numerical warnings are kept, inside an
    expander. Own-criterion check (not a parity comparison)."""
    res, d = _r04_result(converged=False)
    at = AppTest.from_function(_show_app, args=(res, d, _R04_FORMULA), default_timeout=60)
    at.run()
    assert not at.exception

    expanders = [e for e in at.expander if "did not converge" in e.label.lower()]
    assert len(expanders) == 1
    inside = " ".join(w.value for w in expanders[0].warning)
    assert "overflow" in inside
    assert "slogdet" in inside
    caption_texts = " ".join(c.value for c in at.caption)
    assert "numerical events" not in caption_texts.lower()


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


# ---------------------------------------------------------------------------
# S1 (ADR-265): fit-report honesty on the page
# ---------------------------------------------------------------------------


def test_surface_csv_blanks_masked_cells_and_names_the_reason() -> None:
    import numpy as np

    from polaris_re.dashboard.views.gam_fit_section import surface_csv
    from polaris_re.gam.effects import improvement_surface
    from polaris_re.gam.fit_report import mask_surface

    d = _data()
    res = run_gam_request(
        d,
        'death_count ~ s(attained_age, bs="cr", k=5) + s(calendar_year, bs="cr", k=4)'
        " + offset(log_exposure)",
        "poisson",
        "gam",
    )
    assert res.fit is not None
    s = improvement_surface(res.fit, d)
    m = mask_surface(s, d)
    forced = dataclasses.replace(
        m,
        wide_band=np.zeros_like(m.wide_band)
        | (np.arange(m.masked.size).reshape(m.masked.shape) == 0),
    )
    csv = surface_csv(s, forced).splitlines()
    assert csv[0].endswith("mask_reason")
    first = csv[1].split(",")
    assert first[2:6] == ["", "", "", ""]
    assert first[-1] in ("wide_band", "no_exposure")
    assert len(csv) == 1 + s.mi.size


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_page_names_nonpositive_exposure_and_offers_to_drop_them() -> None:
    def app() -> None:
        import polars as pl

        from polaris_re.dashboard.views.gam_fit_section import render_gam_section

        render_gam_section(
            pl.DataFrame(
                {
                    "attained_age": [40, 41, 42, 43] * 5,
                    "calendar_year": [2015] * 20,
                    "death_count": [1.0, 2.0, 1.0, 3.0] * 5,
                    "central_exposure": [1000.0] * 17 + [0.0, -1.0, 0.0],
                }
            )
        )

    at = AppTest.from_function(app, default_timeout=60)
    at.run()
    assert not at.exception
    assert any(
        "3 of 20 rows" in e.value and "zero, negative or missing" in e.value for e in at.error
    )
    assert not any(b.key == "gam_run" for b in at.button)  # refused until the user chooses
    at.checkbox(key="gam_drop_bad_exposure").check()
    at.run()
    assert not at.exception
    assert any("Dropped 3 row(s)" in c.value for c in at.caption)
    assert any(b.key == "gam_run" for b in at.button)


def scale_invariance_claim() -> VerificationClaim:
    """Declared provenance of the amount-vs-count comparison (review P1, ADR-193).

    Both operands come from the SAME engine (``gam`` quasipoisson) on rescaled copies of one
    draw: a Polaris-against-itself MEASUREMENT (own criterion), declared as such (the
    ``MEASUREMENT`` provenance, added to ``core/verification.py`` on maintainer request)."""
    return VerificationClaim(
        claim=(
            "gam quasipoisson computes MI_x(y) on the count-basis copy of a draw; the same "
            "gam quasipoisson computes it on the amount-basis copy (x1e5); compared on MI per "
            "cell. Own-criterion MEASUREMENT of Polaris against itself, not parity."
        ),
        quantities=(
            ComparedQuantity(
                quantity="mi_age_year",
                left_producer="polaris_re.gam.gam quasipoisson, count basis",
                right_producer="polaris_re.gam.gam quasipoisson, amount basis",
                provenance=ComparisonProvenance.MEASUREMENT,
            ),
        ),
    )


# --- S3 (ADR-267): the amount basis and the bam non-PD refusal ---------------------------


def _amount_cells() -> pl.DataFrame:
    """The built-in sample re-expressed on the amount basis (average face 100,000)."""
    c = _sample_cells()
    return c.with_columns(
        (pl.col("central_exposure") * 1.0e5).alias("amount_exposed"),
        (pl.col("death_count") * 1.0e5).alias("death_amount"),
    ).drop("central_exposure", "death_count")


def test_amount_basis_frame_and_default_formula() -> None:
    from polaris_re.dashboard.views.gam_fit_section import default_formula

    d = prepare_frame(_amount_cells(), "amount")
    assert {"log_amount_exposed", "log_expected_amount"} <= set(d.columns)
    assert "log_exposure" not in d.columns  # count-basis names are not reused
    f = default_formula(d, "amount")
    assert f.startswith("death_amount ~") and "offset(log_expected_amount)" in f
    assert "offset(log_amount_exposed)" in default_formula(d.drop("log_expected_amount"), "amount")


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="ADR-267 finding: pre-registered bound MISSED (max |dMI| 6.55e-5 vs 1e-6). REML sp "
    "selection with an estimated scale is not exactly scale invariant (mgcv 1.9.1 on tier 1 "
    "moves edf 3.694 -> 3.725 under the same x1e5 rescale: hypothesis, not a result). The bound "
    "is kept, not widened.",
)
def test_amount_basis_mi_is_scale_invariant_preregistered_bound() -> None:
    """MEASUREMENT (own criterion; both sides are Polaris, so NOT parity). Closed form: with a
    constant face F, death_amount = F x death_count and amount_exposed = F x exposure, and a
    quasi-Poisson fit is scale invariant in the point estimate (score equations are linear in
    y/mu) at a FIXED smoothing parameter. Pre-registered bound (written before the first run):
    max |MI_amount - MI_count| <= 1e-6. (A second pre-registered bound, se ratio = sqrt(F), had
    an algebra error: Var(beta) = phi (X'WX)^-1 with W ~ F and phi ~ F, so se is invariant, not
    scaled; that bound was dropped, not retuned. Recorded in ADR-267.)
    NOTE (review P2): the closed form holds at a FIXED smoothing parameter, but the test runs
    REML-selected sp, so the bound tests a stronger property than the derivation gives; ADR-267
    finding 4 reads the miss accordingly. The engine has no fixed-sp path, so no variant exists.
    (The noise-free sample is NOT used: at y ~ 1e8 with zero deviance the inner IRLS stopping
    rule fails at the starting point - a degenerate case recorded in ADR-267.)"""
    assert not scale_invariance_claim().is_parity_claim  # Polaris vs Polaris: never parity
    import numpy as np

    from polaris_re.gam.effects import improvement_surface

    face, expo, seed = 1.0e5, 5.0e4, 20260301
    rng = np.random.default_rng(seed)
    ages = np.repeat(np.arange(40, 71), 16).astype(float)
    years = np.tile(np.arange(2005, 2021), 31).astype(float)
    mu = expo * 0.004 * np.exp(0.08 * (ages - 45.0)) * np.exp(-0.02 * (years - 2005.0))
    counts = rng.poisson(mu).astype(float)
    base = pl.DataFrame({"attained_age": ages, "calendar_year": years})
    cnt = base.with_columns(
        pl.Series("death_count", counts),
        pl.Series("log_exposure", np.full(ages.size, np.log(expo))),
    )
    amt = base.with_columns(
        pl.Series("death_amount", counts * face),
        pl.Series("log_amount_exposed", np.full(ages.size, np.log(expo * face))),
    )
    rhs = 's(attained_age, bs="cr", k=8) + s(calendar_year, bs="cr", k=5) + offset({o})'
    r_c = run_gam_request(
        cnt, "death_count ~ " + rhs.format(o="log_exposure"), "quasipoisson", "gam"
    )
    r_a = run_gam_request(
        amt, "death_amount ~ " + rhs.format(o="log_amount_exposed"), "quasipoisson", "gam"
    )
    assert r_c.fit is not None and r_a.fit is not None, (r_c.message, r_a.message)
    s_c, s_a = improvement_surface(r_c.fit, cnt), improvement_surface(r_a.fit, amt)
    assert np.max(np.abs(s_a.mi - s_c.mi)) <= 1.0e-6


def test_exposure_helpers_read_amount_exposed_on_the_amount_basis() -> None:
    from polaris_re.gam.fit_report import (
        drop_nonpositive_exposure,
        exposure_vector,
        nonpositive_exposure,
    )

    d = _amount_cells().with_columns(
        pl.when(pl.col("attained_age") == 40)
        .then(0.0)
        .otherwise(pl.col("amount_exposed"))
        .alias("amount_exposed")
    )
    n40 = int((d.get_column("attained_age") == 40).sum())
    assert nonpositive_exposure(d, "amount") == n40
    assert nonpositive_exposure(d.drop("amount_exposed"), "amount") == 0  # nothing to read
    assert exposure_vector(d.drop("amount_exposed"), "amount") is None
    assert drop_nonpositive_exposure(d, "amount").height == d.height - n40


def test_not_positive_definite_refusal_gets_a_plain_hint_and_no_engine_switch() -> None:
    from polaris_re.dashboard.views.gam_fit_section import failure_hint

    msg = "bam_fitd: X'WX + S_lambda is not positive definite — the design is not identified"
    hint = failure_hint(msg)
    assert hint is not None and "lower `k`" in hint and "never switches engines" in hint
    assert failure_hint("something else") is None


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_page_shows_the_hint_under_a_bam_refusal() -> None:
    def app() -> None:
        import streamlit as st

        from polaris_re.dashboard.views.gam_fit_section import GamRunResult, _show

        res = GamRunResult(
            "bam",
            None,
            "bam_fitd: X'WX + S_lambda is not positive definite — the design is not identified",
            (),
            0.1,
        )
        import polars as pl

        _show(res, pl.DataFrame({"x": [1.0]}), "y ~ s(x)")
        st.caption("done")

    at = AppTest.from_function(app, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Refused / failed" in e.value and "positive definite" in e.value for e in at.error)
    assert any("lower `k`" in i.value for i in at.info)


@pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1 not available")
def test_page_amount_basis_leads_with_death_amount_and_quasipoisson() -> None:
    def app() -> None:
        from polaris_re.dashboard.views.experience_improvement import _sample_cells
        from polaris_re.dashboard.views.gam_fit_section import render_gam_section

        c = _sample_cells()
        import polars as pl

        c = c.with_columns(
            (pl.col("central_exposure") * 1.0e5).alias("amount_exposed"),
            (pl.col("death_count") * 1.0e5).alias("death_amount"),
        ).drop("central_exposure", "death_count")
        render_gam_section(c, "amount")

    at = AppTest.from_function(app, default_timeout=120)
    at.run()
    assert not at.exception
    assert any("Amount basis" in c.value for c in at.caption)
    formula = next(t for t in at.text_input if t.key.startswith("gam_formula_amount"))
    assert formula.value.startswith("death_amount ~")
    fam = next(s for s in at.selectbox if s.key == "gam_family_amount")
    assert fam.value == "quasipoisson"
    next(b for b in at.button if b.key == "gam_run").click()
    at.run()
    assert not at.exception
    assert any("Improvement surface MI_x(y)" in s.value for s in at.subheader)
