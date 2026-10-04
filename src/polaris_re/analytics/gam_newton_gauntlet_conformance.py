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

Cases carried from the PLAN's gauntlet (cases 4 and 5 — the 4-term HGAM wiring
and the reproducibility axes — are NOT here; see the ADR).
"""

from collections.abc import Callable
from dataclasses import dataclass
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
    "GauntletReading",
    "gauntlet_claims",
    "payloads_from_probe_dir",
    "require_gauntlet_parity_evidence",
    "run_gauntlet",
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
    return readings


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
