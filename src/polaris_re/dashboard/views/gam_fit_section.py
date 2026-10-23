"""GAM (HGAM fitter) section of the experience-improvement page — dashboard slice D1.

Read-only (``docs/PLAN_gam_dashboard.md`` §3): fits ``polaris_re.gam.gam`` on the data the
user loaded and shows the fit. Nothing here feeds pricing. Every number shown is
``polaris_re.gam``'s (verified against ``mgcv`` elsewhere); what this section adds, the
pre-run cost estimate and the effect profiles, is MEASUREMENT (own criterion), not parity.
The older ``ExperienceGAM`` fit elsewhere on the page is a different model: every figure in
this section is labelled with its engine.
"""

import warnings
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import cast

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
import polars as pl
import streamlit as st  # type: ignore[import-untyped]

from polaris_re.core.exceptions import PolarisComputationError, PolarisValidationError
from polaris_re.gam import GamFit, gam
from polaris_re.gam.cost_model import (
    CostModel,
    Engine,
    default_engine,
    estimate_n_coef,
    fit_cost_model,
    physical_memory_gb,
    pre_run_warning,
)
from polaris_re.gam.formula import SmoothCall, TensorCall, parse_formula

__all__ = ["GamRunResult", "render_gam_section", "run_gam_request"]

GAM_CACHE_KEY = "gam_hgam_fit_cache"
FAMILIES = ("poisson", "quasipoisson", "binomial", "gaussian")
DEFAULT_FORMULA = (
    'death_count ~ s(attained_age, bs="cr", k=8) + s(calendar_year, bs="cr", k=5) '
    "+ offset(log_exposure)"
)
HELP = (
    'Verified subset only: s(x, bs="cr"|"tp", k=), numeric/factor by=, s(f, bs="re"), '
    'ti(x, z, bs="cr"), factors a, a:b, offset(col). Anything else is refused by name '
    "(docs/GAM_USER_GUIDE.md §5-§6)."
)


@dataclass(frozen=True)
class GamRunResult:
    """Outcome of one explicit run: a fit, or a refusal/failure message (never both)."""

    engine: Engine
    fit: GamFit | None
    message: str | None
    warnings_seen: tuple[str, ...]
    seconds: float


def prepare_frame(cells: pl.DataFrame) -> pl.DataFrame:
    """Add ``log_exposure`` from ``central_exposure`` when absent, so the default formula runs."""
    if "log_exposure" not in cells.columns and "central_exposure" in cells.columns:
        return cells.with_columns(pl.col("central_exposure").log().alias("log_exposure"))
    return cells


def run_gam_request(data: pl.DataFrame, formula: str, family: str, engine: Engine) -> GamRunResult:
    """Fit once. Refusals are RESULTS shown by name; ``bam`` is never replaced by ``gam``."""
    import time

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            if engine == "bam":
                fit = gam(formula, data, family, method="fREML", discrete=True)
            else:
                fit = gam(formula, data, family)
        except (PolarisValidationError, PolarisComputationError) as exc:
            return GamRunResult(
                engine,
                None,
                str(exc),
                tuple(str(w.message) for w in caught),
                time.perf_counter() - t0,
            )
    return GamRunResult(
        engine, fit, None, tuple(str(w.message) for w in caught), time.perf_counter() - t0
    )


def fit_signature(data: pl.DataFrame, formula: str, family: str, engine: str) -> int:
    """Content+config hash keying a fit, as ``_fit_signature`` does for the older models."""
    row_hashes = data.hash_rows()
    return hash((int(row_hashes.sum()), data.height, formula, family, engine))


def effect_profiles(
    fit: GamFit, data: pl.DataFrame, formula: str, points: int = 50
) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    """Profile of the linear predictor along each single-covariate smooth.

    Other numeric columns sit at their median, factors at their first level, the offset at 0
    (so the level is a profile, not a population average). Returns
    ``(covariate, grid, link, link_se)``. MEASUREMENT of the fitted model against itself.
    """
    parsed = parse_formula(formula)
    out: list[tuple[str, np.ndarray, np.ndarray, np.ndarray]] = []
    seen: set[str] = set()
    for term in parsed.terms:
        if isinstance(term, TensorCall) or not isinstance(term, SmoothCall) or term.basis == "re":
            continue
        if term.variable in seen:
            continue
        seen.add(term.variable)
        col = data.get_column(term.variable).cast(pl.Float64)
        grid = np.linspace(float(col.min()), float(col.max()), points)  # type: ignore[arg-type]
        base: dict[str, object] = {}
        for name in fit.numeric_columns:
            base[name] = float(data.get_column(name).cast(pl.Float64).median())  # type: ignore[arg-type]
        for name, levels in fit.factor_levels.items():
            base[name] = levels[0]
        if parsed.offset is not None:
            base[parsed.offset] = 0.0
        frame = pl.DataFrame({k: [v] * points for k, v in base.items()}).with_columns(
            pl.Series(term.variable, grid)
        )
        for name in fit.factor_levels:
            frame = frame.with_columns(pl.col(name).cast(pl.String))
        link, se = fit.predict(frame, "link", se_fit=True)
        out.append((term.variable, grid, np.asarray(link), np.asarray(se)))
    return out


def _model() -> CostModel:
    return fit_cost_model()


def render_gam_section(cells: pl.DataFrame) -> None:
    """Render the section. ``cells`` is the frame the page already loaded."""
    st.divider()
    st.header("GAM (HGAM fitter) — read-only")
    st.caption(
        "Fits `polaris_re.gam` (the mgcv-parity engine) on the loaded data. This is a "
        "DIFFERENT model from the experience GAM above; numbers here are labelled with their "
        "engine. Nothing on this section feeds pricing."
    )
    data = prepare_frame(cells)
    n_rows = data.height
    if "log_exposure" in data.columns and "log_exposure" not in cells.columns:
        st.caption("`log_exposure` = ln(`central_exposure`) was added for the offset.")
    formula = st.text_input("Formula", value=DEFAULT_FORMULA, help=HELP, key="gam_formula")
    c1, c2 = st.columns(2)
    family = c1.selectbox("Family", list(FAMILIES), key="gam_family")
    dflt = default_engine(n_rows)
    engine = cast(
        Engine,
        c2.selectbox(
            "Engine",
            ["gam", "bam"],
            index=0 if dflt == "gam" else 1,
            key=f"gam_engine_{dflt}",
            help="Default: gam at or below 300,000 rows, bam above. Select either at any size.",
        ),
    )
    try:
        n_coef = estimate_n_coef(formula, data)
        warn = pre_run_warning(
            _model(),
            engine,
            n_rows,
            n_coef,
            formula=formula,
            family=family,
            available_gb=physical_memory_gb(),
        )
    except PolarisValidationError as exc:
        st.error(f"Formula refused: {exc}")
        return
    body = "\n\n".join(f"- {line}" for line in warn.lines)
    {"info": st.info, "warning": st.warning, "error": st.error}[warn.level](body)
    override = (
        st.checkbox("Attempt anyway", value=False, key="gam_override") if warn.blocked else False
    )
    if st.button("Run GAM fit", disabled=warn.blocked and not override, key="gam_run"):
        with st.spinner(f"Fitting with {engine}…"):
            res = run_gam_request(data, formula, family, engine)
        cast(MutableMapping[str, object], st.session_state)[GAM_CACHE_KEY] = (
            fit_signature(data, formula, family, engine),
            res,
        )
    cached = st.session_state.get(GAM_CACHE_KEY)
    if not (
        isinstance(cached, tuple) and cached[0] == fit_signature(data, formula, family, engine)
    ):
        if cached is not None:
            st.caption("Inputs changed since the last run; press Run again.")
        return
    _show(cached[1], data, formula)


def _show(res: GamRunResult, data: pl.DataFrame, formula: str) -> None:
    st.subheader(f"Result — engine: {res.engine}")
    if res.fit is None:
        st.error(f"Refused / failed: {res.message}")
        return
    fit = res.fit
    st.caption(f"Fit took {res.seconds:.1f} s (MEASUREMENT on this machine).")
    for w in res.warnings_seen:
        st.warning(w)
    m1, m2, m3 = st.columns(3)
    m1.metric("edf total", f"{fit.edf_total:.2f}")
    m2.metric("Converged", "yes" if fit.converged else "NO")
    m3.metric("Iterations", f"{fit.n_function_evals}")
    st.dataframe(
        pl.DataFrame(
            {"term": list(fit.edf_per_term), "edf": [float(v) for v in fit.edf_per_term.values()]}
        ).to_pandas(),
        use_container_width=True,
    )
    try:
        st.code(str(fit.summary()))
    except PolarisValidationError as exc:
        st.info(str(exc))
    for name, grid, link, se in effect_profiles(fit, data, formula):
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.plot(grid, link, label="link")
        ax.fill_between(grid, link - 2 * se, link + 2 * se, alpha=0.25, label="±2 se")
        ax.set_xlabel(name)
        ax.set_title(f"{res.engine}: profile of η along {name}")
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)
    st.caption(
        "Profiles hold other numeric covariates at their median, factors at the first level "
        "and the offset at 0. Standard errors are the Bayesian Vp (conditional)."
    )
