"""Outer-solver epic Slice 4 (ADR-245): the gauntlet — does ONE start of the
safeguarded Newton search (``fit_polaris_gam(outer="newton")``, ``initial.spg``
its only start, no multistart, no seeded second start) meet ADR-221's
``eta``/``edf_total`` gate against ``mgcv``'s own free-``sp`` REML fit on every
free-``sp`` cell this epic has?

This module adds NO comparison of its own and declares NO tolerance. Each case
re-runs an existing, already-INDEPENDENT ``fit_*_case`` / ``compare_*_case``
pair (ADR-193's mechanical test passes on each: the fit function's signature
takes the shared recipe only, never ``mgcv``'s ``eta``/``coef``/``sp``/``edf``)
with one thing changed — ``outer="newton"``. The claim each comparison carries
is read off its own ``.evidence``; :func:`gauntlet_claims` collects them so a
published table's headline is derived (``evidence_markdown``), never written by
hand, and :func:`require_gauntlet_parity_evidence` gates the word "parity" on
every quantity being INDEPENDENT.

Cases carried from the PLAN's gauntlet: 1-3 (ADR-245) and 4, the 4-term HGAM
(ADR-246). Case 5 (the reproducibility axes, ADR-247) is :func:`run_thread_axis`:
Polaris against ITSELF across BLAS thread counts. It has no ``mgcv`` side, so it
carries no ``VerificationClaim`` and is never parity evidence — a reproducibility
MEASUREMENT (own criterion). The seed axis has no operand for Newton.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from functools import partial
from typing import cast

from polaris_re.analytics.gam_by_factor_conformance import (
    compare_by_factor_free_sp_case,
    fit_by_factor_free_sp_case,
)
from polaris_re.analytics.gam_cr_re_ti_conformance import (
    compare_cr_re_ti_free_sp_case,
    fit_cr_re_ti_free_sp_case,
)
from polaris_re.analytics.gam_gaussian_conformance import (
    compare_gaussian_free_sp_case,
    fit_gaussian_free_sp_case,
)
from polaris_re.analytics.gam_initial_sp_default_conformance import (
    cr_re_ti_payload,
    dispersion_draw_payload,
)
from polaris_re.analytics.gam_model import PolarisGAMFit
from polaris_re.analytics.gam_parametric_conformance import (
    compare_parametric_free_sp_case,
    fit_parametric_free_sp_case,
)
from polaris_re.analytics.gam_production_mi_conformance import (
    PRODUCTION_MI_NEWTON_CLAIM,
    RProductionMIPayload,
    compare_production_mi_case,
    fit_production_mi_case,
)
from polaris_re.analytics.gam_quasipoisson_conformance import (
    compare_quasipoisson_free_sp_case,
    fit_quasipoisson_free_sp_case,
)
from polaris_re.analytics.gam_quasipoisson_fixed_scale_conformance import (
    RQuasiPoissonFixedScalePayload,
    compare_quasipoisson_fixed_scale_case,
    fit_quasipoisson_fixed_scale_case,
)
from polaris_re.analytics.gam_reml_newton import newton_variant
from polaris_re.analytics.gam_select_free_sp_conformance import (
    compare_select_free_sp_case,
    fit_select_free_sp_case,
)
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    VerificationClaim,
    require_parity_evidence,
)

__all__ = [
    "REQUIRED_CASE_PREFIXES",
    "GauntletReading",
    "ThreadAxisReading",
    "gate_failures",
    "gauntlet_claims",
    "payloads_from_probe_dir",
    "require_gauntlet_parity_evidence",
    "run_gauntlet",
    "run_thread_axis",
]


@dataclass(frozen=True)
class GauntletReading:
    """One (case, scale) reading as the case's own comparator reported it."""

    case: str
    max_abs_eta_diff: float
    edf_total_diff: float
    n_function_evals: int
    at_bound: bool
    converged: bool
    agrees: bool
    evidence: VerificationClaim | None
    error: str | None = None


def _read(c: object, name: str) -> object:
    """One field of a comparison: the compare functions return either a
    TypedDict (fixed scale, Gaussian) or a dataclass."""
    return c[name] if isinstance(c, dict) else getattr(c, name)


def _reading(case: str, fit: PolarisGAMFit, comparison: object) -> GauntletReading:
    evidence = _read(comparison, "evidence")
    if not isinstance(evidence, VerificationClaim):
        raise PolarisValidationError(
            f"gauntlet case {case!r}: its comparison carries no VerificationClaim "
            f"(got {type(evidence).__name__}); a comparison without a declared claim "
            "cannot be reported as evidence."
        )
    return GauntletReading(
        case=case,
        max_abs_eta_diff=float(_read(comparison, "max_abs_eta_diff")),  # type: ignore[arg-type]
        edf_total_diff=float(_read(comparison, "edf_total_diff")),  # type: ignore[arg-type]
        n_function_evals=int(fit.n_function_evals),
        at_bound=bool(_read(comparison, "at_bound")),
        converged=bool(_read(comparison, "converged")),
        agrees=bool(_read(comparison, "agrees")),
        evidence=evidence,
    )


type _Fit = Callable[..., PolarisGAMFit]
type _Compare = Callable[..., object]

_FREE_SCALE_CELLS: tuple[tuple[str, str, _Fit, _Compare], ...] = (
    (
        "gaussian L1 (cr+by+ti)",
        "gaussian_l1",
        fit_gaussian_free_sp_case,
        compare_gaussian_free_sp_case,
    ),
    (
        "gaussian factor-by L3",
        "gaussian_l3",
        fit_by_factor_free_sp_case,
        compare_by_factor_free_sp_case,
    ),
    (
        "gaussian parametric L4",
        "gaussian_l4",
        fit_parametric_free_sp_case,
        compare_parametric_free_sp_case,
    ),
    (
        "gaussian cr+re+ti L6",
        "gaussian_l6",
        fit_cr_re_ti_free_sp_case,
        compare_cr_re_ti_free_sp_case,
    ),
    (
        "quasipoisson 3b draw",
        "quasipoisson_3b",
        fit_quasipoisson_free_sp_case,
        compare_quasipoisson_free_sp_case,
    ),
    (
        "quasipoisson 3c draw",
        "quasipoisson_3c",
        fit_quasipoisson_free_sp_case,
        compare_quasipoisson_free_sp_case,
    ),
)


def payloads_from_probe_dir(
    load: Callable[[str], dict[str, object]],
) -> dict[str, dict[str, object]]:
    """The committed-recipe probe payloads, keyed as the gauntlet's cases are.
    ``load`` maps a probe file name to its parsed JSON."""
    return {
        "gaussian_l1": load("gam_gaussian_free_sp_probe.json"),
        "gaussian_l3": load("gam_by_factor_free_sp_probe.json"),
        "gaussian_l4": load("gam_parametric_free_sp_probe.json"),
        "gaussian_l6": cr_re_ti_payload(load("gam_cr_re_ti_probe.json"), "gaussian_free"),
        "quasipoisson_3b": load("gam_quasipoisson_free_sp_probe.json"),
        "quasipoisson_3c": dispersion_draw_payload(load("gam_dispersion_two_stage_probe.json")),
        "fixed_scale": load("gam_quasipoisson_fixed_scale_probe.json"),
        "select_n7": load("gam_select_multiterm_free_sp_probe.json"),
        "production_mi": load("gam_production_mi_probe.json"),
    }


def run_gauntlet(payloads: dict[str, dict[str, object]]) -> list[GauntletReading]:
    """Every case, ONE Newton start each. A case whose fit raises is reported as
    an ``error`` row (never swallowed, never dropped): an exception is a
    disagreement of the strongest kind and the table must show it."""
    readings: list[GauntletReading] = []
    for label, key, fit, compare in _FREE_SCALE_CELLS:
        readings += _guarded(label, partial(_one_as_list, label, fit, compare, payloads, key))
    readings += _guarded("quasipoisson fixed scale", lambda: _fixed_scale(payloads["fixed_scale"]))
    select_label = "select=TRUE N=7 (cr+by+ti, 7 blocks)"
    readings += _guarded(
        select_label,
        lambda: [
            _one(
                select_label,
                fit_select_free_sp_case,
                compare_select_free_sp_case,
                payloads["select_n7"],
            )
        ],
    )
    hgam_label = "4-term HGAM s+s+ti+s (poisson, ADR-227)"
    readings += _guarded(hgam_label, lambda: [_hgam(hgam_label, payloads["production_mi"])])
    return readings


def _hgam(label: str, payload: dict[str, object]) -> GauntletReading:
    """Case 4: ADR-227's four-term HGAM, ``anova`` axis only. ``multistart=False``
    because ``outer="newton"`` is its own single start. The reading carries
    :data:`PRODUCTION_MI_NEWTON_CLAIM` (the two columns this comparison computes),
    not the comparison's own ``te``/R-internal claim."""
    typed = cast(RProductionMIPayload, payload)
    fit = fit_production_mi_case(typed, multistart=False, outer="newton")
    comparison = compare_production_mi_case(fit, typed, target="anova")
    return replace(_reading(label, fit, comparison), evidence=PRODUCTION_MI_NEWTON_CLAIM)


def _one_as_list(
    label: str, fit: _Fit, compare: _Compare, payloads: dict[str, dict[str, object]], key: str
) -> list[GauntletReading]:
    # The payload lookup stays inside the guarded call: a missing payload is an
    # error row, never a silently shorter table.
    return [_one(label, fit, compare, payloads[key])]


def _one(label: str, fit: _Fit, compare: _Compare, payload: dict[str, object]) -> GauntletReading:
    polaris_fit = fit(payload, outer="newton")
    return _reading(label, polaris_fit, compare(polaris_fit, payload))


def _fixed_scale(payload: dict[str, object]) -> list[GauntletReading]:
    typed = cast(RQuasiPoissonFixedScalePayload, payload)
    fits = fit_quasipoisson_fixed_scale_case(typed, outer="newton")
    comparisons = compare_quasipoisson_fixed_scale_case(fits, typed)
    return [
        _reading(f"quasipoisson fixed scale={c['scale']:g}", f, c)
        for f, c in zip(fits, comparisons, strict=True)
    ]


def _guarded(label: str, run: Callable[[], list[GauntletReading]]) -> list[GauntletReading]:
    try:
        return run()
    except Exception as exc:  # reported in the table, never swallowed
        return [
            GauntletReading(
                case=label,
                max_abs_eta_diff=float("nan"),
                edf_total_diff=float("nan"),
                n_function_evals=-1,
                at_bound=False,
                converged=False,
                agrees=False,
                evidence=None,
                error=repr(exc),
            )
        ]


REQUIRED_CASE_PREFIXES: tuple[str, ...] = ("quasipoisson fixed scale",)
"""The gauntlet rows a CI step BLOCKS on (PLAN Slice 4 case 2, the 2026-10-01
maintainer decision carried from parity slice 8: quasipoisson fixed ``scale``,
ADR-236's far-phi case, made a blocking check on the Newton search). Widening
this tuple is a reviewable edit; narrowing it is the move the epic has refused
twice. Every other case is reported, not gated."""

_REQUIRED_MIN_ROWS = 2  # scale = 2 and scale = 6


def gate_failures(
    readings: list[GauntletReading],
    required_prefixes: tuple[str, ...] = REQUIRED_CASE_PREFIXES,
) -> list[str]:
    """Why the blocking gate fails, empty when it passes. A required case with
    too few rows (a dropped scale), an error row, a non-converged fit or an
    ADR-221 disagreement each fail it; a missing row never passes by omission."""
    failures: list[str] = []
    for prefix in required_prefixes:
        rows = [r for r in readings if r.case.startswith(prefix)]
        if len(rows) < _REQUIRED_MIN_ROWS:
            failures.append(f"{prefix!r}: {len(rows)} row(s), expected >= {_REQUIRED_MIN_ROWS}")
        failures += [
            f"{r.case}: error={r.error}" if r.error else f"{r.case}: ADR-221 disagreement"
            for r in rows
            if not (r.agrees and r.converged)
        ]
    return failures


def gauntlet_claims(readings: list[GauntletReading]) -> list[VerificationClaim]:
    """Each DISTINCT declared claim the readings carry, with the search named as
    Newton (derived by :func:`newton_variant`, never re-written)."""
    seen: dict[str, VerificationClaim] = {}
    for r in readings:
        if r.evidence is not None:
            seen.setdefault(r.evidence.claim, newton_variant(r.evidence))
    return list(seen.values())


def require_gauntlet_parity_evidence(
    readings: list[GauntletReading],
) -> tuple[ComparedQuantity, ...]:
    """Gate the word "parity" on the gauntlet: every compared quantity of every
    claim must be INDEPENDENT (ADR-193). Raises otherwise."""
    quantities = [q for claim in gauntlet_claims(readings) for q in claim.quantities]
    return require_parity_evidence(quantities, claim="outer-solver gauntlet (ADR-245)")


@dataclass(frozen=True)
class ThreadAxisReading:
    """One case's Newton fit repeated across BLAS thread counts, each compared
    with the FIRST thread count's fit. Polaris against itself: no ``mgcv`` side."""

    case: str
    threads: tuple[int, ...]
    max_abs_eta_diff: float
    max_abs_log10_sp_diff: float
    max_abs_edf_total_diff: float
    all_converged: bool
    n_function_evals: tuple[int, ...]
    error: str | None = None


def _newton_fits_for_case(
    label: str, payloads: dict[str, dict[str, object]]
) -> list[PolarisGAMFit]:
    """The case's Newton fit(s) at the current BLAS thread count (fixed scale
    yields one fit per supplied scale; every other case yields one)."""
    for name, key, fit, _compare in _FREE_SCALE_CELLS:
        if name == label:
            return [fit(payloads[key], outer="newton")]
    if label == "quasipoisson fixed scale":
        typed = cast(RQuasiPoissonFixedScalePayload, payloads["fixed_scale"])
        return list(fit_quasipoisson_fixed_scale_case(typed, outer="newton"))
    if label == "select=TRUE N=7":
        return [fit_select_free_sp_case(payloads["select_n7"], outer="newton")]  # type: ignore[arg-type]
    if label == "4-term HGAM":
        typed_mi = cast(RProductionMIPayload, payloads["production_mi"])
        return [fit_production_mi_case(typed_mi, multistart=False, outer="newton")]
    raise PolarisValidationError(f"unknown thread-axis case {label!r}")


THREAD_AXIS_CASES: tuple[str, ...] = (
    *[c[0] for c in _FREE_SCALE_CELLS],
    "quasipoisson fixed scale",
    "select=TRUE N=7",
    "4-term HGAM",
)


def run_thread_axis(
    payloads: dict[str, dict[str, object]],
    limit_threads: Callable[[int], AbstractContextManager[object]],
    threads: tuple[int, ...] = (1, 2, 4, 1),
) -> list[ThreadAxisReading]:
    """Gauntlet case 5, thread axis (ADR-222 amendment 1's protocol, run on the
    Newton search): each case is fit once per entry of ``threads`` under
    ``limit_threads(n)`` and compared with the first. A raising case is an error
    row, never dropped. ``PolarisGAMFit.log_lambda`` is already ``log10``."""
    out: list[ThreadAxisReading] = []
    for label in THREAD_AXIS_CASES:
        try:
            runs: list[list[PolarisGAMFit]] = []
            for n in threads:
                with limit_threads(n):
                    runs.append(_newton_fits_for_case(label, payloads))
            ref = runs[0]
            d_eta = d_sp = d_edf = 0.0
            for run in runs[1:]:
                for a, b in zip(ref, run, strict=True):
                    d_eta = max(d_eta, float(abs(a.eta - b.eta).max()))
                    d_sp = max(d_sp, float(abs(a.log_lambda - b.log_lambda).max()))
                    d_edf = max(d_edf, abs(a.edf_total - b.edf_total))
            out.append(
                ThreadAxisReading(
                    case=label,
                    threads=threads,
                    max_abs_eta_diff=d_eta,
                    max_abs_log10_sp_diff=d_sp,
                    max_abs_edf_total_diff=d_edf,
                    all_converged=all(f.converged for run in runs for f in run),
                    n_function_evals=tuple(sum(f.n_function_evals for f in run) for run in runs),
                )
            )
        except Exception as exc:  # reported in the table, never swallowed
            out.append(
                ThreadAxisReading(
                    case=label,
                    threads=threads,
                    max_abs_eta_diff=float("nan"),
                    max_abs_log10_sp_diff=float("nan"),
                    max_abs_edf_total_diff=float("nan"),
                    all_converged=False,
                    n_function_evals=(),
                    error=repr(exc),
                )
            )
    return out
