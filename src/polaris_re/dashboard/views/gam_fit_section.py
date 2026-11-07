"""GAM (HGAM fitter) section of the experience-improvement page — dashboard slice D1.

Read-only (``docs/PLAN_gam_dashboard.md`` §3): fits ``polaris_re.gam.gam`` on the data the
user loaded and shows the fit. Nothing here feeds pricing. Every number shown is
``polaris_re.gam``'s (verified against ``mgcv`` elsewhere); what this section adds, the
pre-run cost estimate and the effect profiles, is MEASUREMENT (own criterion), not parity.
The older ``ExperienceGAM`` fit elsewhere on the page is a different model: every figure in
this section is labelled with its engine.
"""

import io
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
from polaris_re.gam.effects import ImprovementSurface, improvement_surface, partial_effects
from polaris_re.gam.formula import SmoothCall, TensorCall, parse_formula

__all__ = ["GamRunResult", "render_gam_section", "run_gam_request"]

GAM_CACHE_KEY = "gam_hgam_fit_cache"
FAMILIES = ("poisson", "quasipoisson", "binomial", "gaussian")
FAMILY_CHOICES = (*FAMILIES, 'binomial(link="cloglog")')
"""What the page offers: the families, plus the cloglog link the R2 sensitivity cell S1 used.
``gam()`` takes the family string verbatim, so the link is never dropped."""
DEFAULT_FORMULA = (
    'death_count ~ s(attained_age, bs="cr", k=8) + s(calendar_year, bs="cr", k=5) '
    '+ ti(attained_age, calendar_year, bs="cr") + offset(log_exposure)'
)
EXPECTED_OFFSET = "log_expected"
"""``ln(central_exposure * q_base)``, added when ``q_base`` is present (ADR-263 decision 4): the
fitted effects are then A/E multipliers on the static base, as on the older model; without
``q_base`` the offset is ``log_exposure`` and the effects are on the log mortality rate."""


def default_formula(data: pl.DataFrame) -> str:
    """The starting formula: ``offset(log_expected)`` when ``q_base`` was supplied."""
    if EXPECTED_OFFSET in data.columns:
        return DEFAULT_FORMULA.replace("offset(log_exposure)", f"offset({EXPECTED_OFFSET})")
    return DEFAULT_FORMULA


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
    """Add ``log_exposure`` (and ``log_expected`` when ``q_base`` is present) from
    ``central_exposure``, so the default formula runs."""
    out = cells
    if "log_exposure" not in out.columns and "central_exposure" in out.columns:
        out = out.with_columns(pl.col("central_exposure").log().alias("log_exposure"))
    if (
        EXPECTED_OFFSET not in out.columns
        and "q_base" in out.columns
        and "central_exposure" in out.columns
    ):
        out = out.with_columns(
            (pl.col("central_exposure") * pl.col("q_base")).log().alias(EXPECTED_OFFSET)
        )
    return out


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
    start = default_formula(data)
    formula = st.text_input(
        "Formula",
        value=start,
        help=HELP,
        key=f"gam_formula_{'qbase' if start != DEFAULT_FORMULA else 'plain'}",
    )
    c1, c2 = st.columns(2)
    family = c1.selectbox("Family", list(FAMILY_CHOICES), key="gam_family")
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
    _show_effects(fit, data, res.engine)
    _show_surface(fit, data, res.engine)


def _show_effects(fit: GamFit, data: pl.DataFrame, engine: Engine) -> None:
    st.subheader(f"Partial effects — engine: {engine}")
    st.caption(
        "MEASUREMENT of the fitted model (own criterion). Each term alone: intercept, offset "
        "and the other terms excluded (plot.gam convention); smooths are centred over the "
        "training rows; band = 2 x se from the term's block of the conditional Vp."
    )
    for e in partial_effects(fit, data):
        if e.kind == "curve":
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.plot(e.axes[0], e.effect)
            ax.fill_between(e.axes[0], e.effect - 2 * e.se, e.effect + 2 * e.se, alpha=0.25)
            ax.set_xlabel(e.variables[0])
            ax.set_title(f"{engine}: {e.label}")
        elif e.kind == "surface":
            fig, ax = plt.subplots(figsize=(5, 3.5))
            mesh = ax.pcolormesh(e.axes[1], e.axes[0], e.effect, shading="auto")
            fig.colorbar(mesh, ax=ax)
            ax.set_xlabel(e.variables[1])
            ax.set_ylabel(e.variables[0])
            ax.set_title(f"{engine}: {e.label}")
        else:
            fig, ax = plt.subplots(figsize=(5, 3))
            ax.errorbar(range(len(e.effect)), e.effect, yerr=2 * e.se, fmt="o")
            ax.set_xticks(range(len(e.effect)), e.level_names, rotation=45)
            ax.set_title(f"{engine}: {e.label}")
        st.pyplot(fig)
        plt.close(fig)
        if e.note:
            st.caption(e.note)


def surface_csv(s: ImprovementSurface) -> str:
    """The download: one row per (age, year) cell with the delta-method band."""
    grid = pl.DataFrame(
        {
            s.age_var: np.repeat(s.ages, s.years.size),
            s.year_var: np.tile(s.years, s.ages.size),
            "mi": s.mi.reshape(-1),
            "mi_lower": s.mi_lower.reshape(-1),
            "mi_upper": s.mi_upper.reshape(-1),
            "mi_se": s.mi_se.reshape(-1),
        }
    )
    buf = io.StringIO()
    grid.write_csv(buf)
    return buf.getvalue()


def _show_surface(fit: GamFit, data: pl.DataFrame, engine: Engine) -> None:
    st.subheader(f"Improvement surface MI_x(y) — engine: {engine}")
    st.warning(
        "MEASUREMENT: not an actuarial recommendation, not fed to pricing. "
        f"MI_x(y) = 1 - exp(eta(x,y) - eta(x,y-1)) from the {engine} fit; band = delta method "
        "on the contrast, Var = D Vp D^T."
    )
    try:
        s = improvement_surface(fit, data)
    except PolarisValidationError as exc:
        st.info(f"No improvement surface: {exc}")
        return
    fig, ax = plt.subplots(figsize=(6, 3.5))
    mesh = ax.pcolormesh(s.years, s.ages, s.mi, shading="auto")
    fig.colorbar(mesh, ax=ax, label="MI")
    ax.set_xlabel(s.year_var)
    ax.set_ylabel(s.age_var)
    ax.set_title(f"{engine}: MI_x(y)")
    st.pyplot(fig)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    width = s.mi_upper - s.mi_lower
    mesh = ax.pcolormesh(s.years, s.ages, width, shading="auto")
    fig.colorbar(mesh, ax=ax, label=f"{s.level:.0%} band width")
    ax.set_xlabel(s.year_var)
    ax.set_ylabel(s.age_var)
    ax.set_title(f"{engine}: where the surface is poorly identified")
    st.pyplot(fig)
    plt.close(fig)
    st.caption(
        "Other covariates held at: "
        + (", ".join(f"{k} {v}" for k, v in s.reference.items()) or "none")
        + ". The Bayesian projection fan is not available for the HGAM (it stays on the legacy "
        "model)."
    )
    st.download_button(
        "Download MI surface (CSV, HGAM)",
        data=surface_csv(s),
        file_name="hgam_mi_surface.csv",
        mime="text/csv",
        key="hgam_mi_download",
    )
