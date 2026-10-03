#!/usr/bin/env python3
"""Outer-solver epic, slice 0 (ADR-241): is the start-dependence a BARRIER in
the REML landscape, or a SOLVER that stops early?

Usage: gam_outer_solver_landscape_probe.py <probe_dir> [report.md]

On the two free-scale cells where ladder slice 3e (ADR-240) found a start that
disagrees with ``mgcv`` — gaussian L1 under the ``initial.spg`` seed, and the
quasipoisson slice-3c draw under the bounds-centre start — this evaluates
Polaris's OWN free-scale REML score:

1. along the straight segment, in ``log10(lambda)``, from the point Polaris's
   search stopped at (``a``) to the point ``mgcv`` selected (``b``); and
2. as a central-difference gradient at ``a``; and
3. along the search's own path: the first trial point the line search
   evaluated AND the first iterate L-BFGS-B accepted, and how far each went.
   (A trial point can be rejected by the line search; only an accepted iterate
   says where the search actually moved — PR #250 review [P1].)

The two outcomes it discriminates, registered before the run (ADR-241):

* **No barrier** (the segment profile never rises above ``score(a)`` by more
  than the criterion's own noise, and ``score(b) < score(a)``): ``a`` is not a
  separate basin. Some descent path from ``a`` reaches ``mgcv``'s point, so the
  disagreement is the SEARCH stopping early — the defect a Newton outer solver
  with exact derivatives exists to remove. Multistart and seeded starts treat
  the symptom.
* **Barrier** (the profile rises materially above ``score(a)`` before falling):
  ``a`` is at least segment-separated from ``b``. A straight segment can show a
  barrier that a curved path avoids, so this does NOT prove a true local
  minimum — but it does mean a better local solver alone is not guaranteed to
  close the gap, and the start remains a live variable.

Provenance (ADR-193, ``docs/VERIFICATION_STANDARD.md`` §2.1):
``MEASUREMENT (own criterion)``. ``mgcv``'s ``sp`` enters only as a point of
evaluation; nothing ``mgcv`` computed is compared against anything Polaris
computed. Remove ``mgcv`` and every number here still exists for any ``b``. No
parity claim can rest on it. Reports; gates nothing.
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from polaris_re.analytics import gam_reml_optimize
from polaris_re.analytics.gam_gaussian_conformance import fit_gaussian_free_sp_case
from polaris_re.analytics.gam_initial_sp_default_conformance import dispersion_draw_payload
from polaris_re.analytics.gam_model import PolarisGAMFit, resolve_family
from polaris_re.analytics.gam_quasipoisson_conformance import fit_quasipoisson_free_sp_case
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

type ScoreFn = Callable[[np.ndarray], float]

N_SEGMENT_POINTS = 41
"""Segment resolution: 40 equal steps from ``a`` (t=0) to ``b`` (t=1)."""

GRADIENT_STEP = 0.01
"""Central-difference step in ``log10(lambda)`` for the gradient at ``a``."""


@dataclass(frozen=True)
class SegmentProfile:
    """Own-criterion score along ``a + t (b - a)``, ``t`` in ``[0, 1]``."""

    t: np.ndarray
    score: np.ndarray
    barrier: float
    """``max_t score(t) - score(0)``: how far the profile rises above the
    stopping point before reaching ``b``. ``0.0`` when it never rises."""
    descent: float
    """``score(0) - score(1)``: how much lower ``mgcv``'s point scores."""
    n_rises: int
    """Steps where the score increases by more than ``rise_tol``."""


def segment_profile(
    score: ScoreFn, a: np.ndarray, b: np.ndarray, *, n: int = N_SEGMENT_POINTS, rise_tol: float
) -> SegmentProfile:
    """Evaluate ``score`` along the segment from ``a`` to ``b``.

    ``rise_tol`` is the criterion's own noise allowance for counting a rise —
    supplied by the caller, never fitted here.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)
    values = np.array([score(a + ti * (b - a)) for ti in t], dtype=np.float64)
    return SegmentProfile(
        t=t,
        score=values,
        barrier=float(max(0.0, np.max(values) - values[0])),
        descent=float(values[0] - values[-1]),
        n_rises=int(np.sum(np.diff(values) > rise_tol)),
    )


def central_gradient(
    score: ScoreFn, x: np.ndarray, *, h: float, upper: float | None = None
) -> np.ndarray:
    """Central difference of ``score`` at ``x``; one-sided (backward) for any
    coordinate within ``h`` of ``upper``, so the probe never steps outside the
    search box the solver itself was confined to."""
    x = np.asarray(x, dtype=np.float64)
    grad = np.empty_like(x)
    f0 = score(x)
    for i in range(x.size):
        e = np.zeros_like(x)
        e[i] = h
        if upper is not None and x[i] + h > upper:
            grad[i] = (f0 - score(x - e)) / h
        else:
            grad[i] = (score(x + e) - score(x - e)) / (2.0 * h)
    return grad


FIRST_MOVE_TOL = 1e-3
"""A trial point counts as a MOVE (not a finite-difference probe) when some
coordinate differs from the start by more than this, in ``log10(lambda)``.
L-BFGS-B's own forward-difference step is ~1.5e-8, five orders smaller."""

_LOWER_BOUND = -2.0
_UPPER_BOUND = 12.0
"""The free-sp search box (``fit_polaris_gam``'s ``PRODUCTION_LOG10_BOUNDS``,
which neither cell's fit helper overrides)."""


@dataclass(frozen=True)
class FirstMove:
    """One step away from the search's start: either the first TRIAL point
    (what the line search evaluated) or the first ACCEPTED iterate (where
    L-BFGS-B actually moved). The two differ when the line search rejects or
    shortens its first trial — which is why the probe reports both."""

    start: np.ndarray
    point: np.ndarray
    max_abs_step: float
    """Largest single-coordinate change, in decades of ``lambda``."""
    n_at_upper: int
    """How many coordinates sit on the upper bound at ``point``."""
    n_at_lower: int
    """How many coordinates sit on the lower bound at ``point``."""


def first_move(trace: list[np.ndarray], *, upper: float, lower: float = _LOWER_BOUND) -> FirstMove:
    """The first entry of ``trace`` that moved more than :data:`FIRST_MOVE_TOL`
    from ``trace[0]`` (the start). Applied to the evaluation trace it gives the
    first trial point; applied to the accepted-iterate trace, the first step."""
    start = trace[0]
    for point in trace[1:]:
        step = np.abs(point - start)
        if np.max(step) > FIRST_MOVE_TOL:
            return FirstMove(
                start=start,
                point=point,
                max_abs_step=float(np.max(step)),
                n_at_upper=int(np.sum(point >= upper)),
                n_at_lower=int(np.sum(point <= lower)),
            )
    return FirstMove(start=start, point=start, max_abs_step=0.0, n_at_upper=0, n_at_lower=0)


@dataclass(frozen=True)
class SearchTrace:
    """What the search did, recorded from outside it."""

    evaluated: list[np.ndarray]
    """Every ``log10(lambda)`` the scorer was called at, in order — trial
    points AND finite-difference probes."""
    accepted: list[np.ndarray]
    """The start, then every iterate L-BFGS-B ACCEPTED (its ``callback``), in
    order, concatenated across any restarts the search makes."""
    exits: list[str]
    """SciPy's own termination message and iteration count, one per
    ``minimize`` call — names WHICH stopping rule ended the search."""


def _traced_fit(
    fit_fn: Callable[..., PolarisGAMFit], payload: dict[str, object], *, seeded: bool
) -> tuple[PolarisGAMFit, SearchTrace]:
    """Run the fit while recording every point the search evaluates and every
    iterate it accepts. Wraps the two module-level names the search calls
    (``penalized_fit_and_score`` and SciPy's ``minimize``) and restores both."""
    evaluated: list[np.ndarray] = []
    accepted: list[np.ndarray] = []
    exits: list[str] = []
    original_score = gam_reml_optimize.penalized_fit_and_score
    original_minimize = gam_reml_optimize.minimize

    def recording_score(*args: object, **kwargs: object) -> tuple[np.ndarray, float]:
        log_lambda = args[4] if len(args) > 4 else kwargs["log_lambda"]
        evaluated.append(np.array(log_lambda, dtype=np.float64))
        return original_score(*args, **kwargs)  # type: ignore[arg-type]

    def recording_minimize(fun: object, x0: np.ndarray, *args: object, **kwargs: object) -> object:
        if not accepted:
            accepted.append(np.array(x0, dtype=np.float64))

        def callback(xk: np.ndarray) -> None:
            accepted.append(np.array(xk, dtype=np.float64))

        result = original_minimize(fun, x0, *args, callback=callback, **kwargs)  # type: ignore[arg-type]
        exits.append(f"{result.message} (nit={result.nit}, success={result.success})")
        return result

    gam_reml_optimize.penalized_fit_and_score = recording_score  # type: ignore[assignment]
    gam_reml_optimize.minimize = recording_minimize  # type: ignore[assignment]
    try:
        fit = fit_fn(payload, initial_sp_start=seeded)
    finally:
        gam_reml_optimize.penalized_fit_and_score = original_score
        gam_reml_optimize.minimize = original_minimize
    return fit, SearchTrace(evaluated=evaluated, accepted=accepted, exits=exits)


def _score_fn(fit: PolarisGAMFit, y: np.ndarray) -> ScoreFn:
    family = resolve_family(fit.model.family, fit.model.link)
    x = fit.design["x"]
    blocks = fit.design["penalty_blocks"]

    def score(log_lambda: np.ndarray) -> float:
        return float(penalized_fit_and_score(y, x, family, blocks, log_lambda)[1])

    return score


CELLS: dict[str, tuple[str, Callable[..., PolarisGAMFit], bool]] = {
    "gaussian L1 (seeded start)": (
        "gam_gaussian_free_sp_probe.json",
        fit_gaussian_free_sp_case,
        True,
    ),
    "quasipoisson 3c draw (centre start)": (
        "gam_dispersion_two_stage_probe.json",
        fit_quasipoisson_free_sp_case,
        False,
    ),
}
"""The two (cell, start) pairs ADR-240 found disagreeing with ``mgcv``."""


def _fmt_move(label: str, move: FirstMove) -> str:
    return (
        f"- {label}: `{np.array2string(move.point, precision=3)}` — largest step "
        f"`{move.max_abs_step:.2f}` decades; on upper bound: `{move.n_at_upper}`, "
        f"on lower bound: `{move.n_at_lower}`"
    )


def main(probe_dir: Path, out: Path | None) -> None:
    lines = [
        "",
        "### Outer-solver slice 0 — REML landscape between Polaris's stopping point and mgcv's",
        "",
        "**Provenance: `MEASUREMENT (own criterion)`** (VERIFICATION_STANDARD §2.1). "
        "`mgcv`'s `sp` is only the point of evaluation; every score is Polaris's own. "
        "Not a comparison and not parity evidence.",
        "",
    ]
    for cell, (probe_name, fit_fn, seeded) in CELLS.items():
        probe = json.loads((probe_dir / probe_name).read_text())
        payload = dispersion_draw_payload(probe) if "joint" in probe else probe
        y = np.asarray(payload["y"], dtype=np.float64)
        fit, trace = _traced_fit(fit_fn, payload, seeded=seeded)
        trial = first_move(trace.evaluated, upper=_UPPER_BOUND)
        step = first_move(trace.accepted, upper=_UPPER_BOUND)
        score = _score_fn(fit, y)
        a = np.asarray(fit.log_lambda, dtype=np.float64)
        b = np.log10(np.asarray(payload["sp"], dtype=np.float64))
        # Noise allowance for counting a rise: 1e-9 relative to the score —
        # four orders above slice 7h's measured criterion noise floor (~6.8e-13
        # absolute), so float jitter is never counted and a real rise always is.
        profile = segment_profile(score, a, b, rise_tol=1e-9 * abs(score(a)))
        grad_a = central_gradient(score, a, h=GRADIENT_STEP, upper=_UPPER_BOUND)
        grad_b = central_gradient(score, b, h=GRADIENT_STEP, upper=_UPPER_BOUND)
        lines += [
            f"#### {cell}",
            "",
            f"- Polaris stop `a` log10(lambda): `{np.array2string(a, precision=3)}` "
            f"(converged={fit.converged}, at_bound={fit.at_bound}, "
            f"evals={fit.n_function_evals})",
            f"- search start: `{np.array2string(trial.start, precision=3)}` "
            "(mgcv's `gam.control()$newton$maxNstep` = 5 natural-log units, ~2.17 decades)",
            _fmt_move("first TRIAL point (line search's first evaluation)", trial),
            _fmt_move("first ACCEPTED iterate (L-BFGS-B callback)", step),
            "- SciPy exit(s): " + "; ".join(f"`{e}`" for e in trace.exits),
            "- first accepted iterates: "
            + "; ".join(f"`{np.array2string(x, precision=2)}`" for x in trace.accepted[:6]),
            f"- mgcv point `b` log10(sp): `{np.array2string(b, precision=3)}`",
            f"- own score: `a` = `{profile.score[0]:.6f}`, `b` = `{profile.score[-1]:.6f}`, "
            f"descent a->b = `{profile.descent:.6f}`",
            f"- barrier above `score(a)` on the segment: `{profile.barrier:.3e}`; "
            f"rising steps: `{profile.n_rises}` of {N_SEGMENT_POINTS - 1}",
            f"- central-diff gradient at `a` (h={GRADIENT_STEP}): "
            f"`{np.array2string(grad_a, precision=4)}`",
            f"- central-diff gradient at `b` (h={GRADIENT_STEP}): "
            f"`{np.array2string(grad_b, precision=4)}`",
            "",
            "| t | own REML score |",
            "|---:|---:|",
            *(
                f"| {ti:.3f} | {si:.6f} |"
                for ti, si in zip(profile.t[::4], profile.score[::4], strict=True)
            ),
            "",
        ]
    report = "\n".join(lines)
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
