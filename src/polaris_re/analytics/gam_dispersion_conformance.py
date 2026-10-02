"""The exposed dispersion estimate, and the optional two-stage Poisson ->
fixed-scale workflow, against ``mgcv`` — capability ladder slice **3c**
(``docs/PLAN_mgcv_capability_ladder.md``).

**Two separable questions, one probe** (``scripts/gam_dispersion_two_stage_probe.R``).

1. *Is the estimate Polaris exposes the number ``mgcv`` reports?* Polaris computes
   Pearson, Fletcher and deviance dispersion from its OWN free-sp quasi-Poisson fit
   (:attr:`PolarisGAMFit.dispersion`); ``mgcv`` reports ``m$scale`` from its own.
   The comparison is also an IDENTIFICATION: it asks which of the three Polaris
   estimators ``m$scale`` is, so the estimator is pinned by measurement and not
   by reading ``gam.fit3``.
2. *Does the two-stage workflow reproduce ``mgcv``'s own chain?* Stage 1 fits
   ``poisson(log)`` and reads its Pearson dispersion; stage 2 refits at that
   dispersion held fixed (slice 7's ``poisson`` + ``gamma = phi`` route, with
   slice 7b's two-start search). ``mgcv`` runs the same chain from the same
   recipe — ``poisson`` then ``quasipoisson(scale = phi_P)``. The workflow is
   **optional and non-standard** (it is not what ``mgcv`` does by default, which
   estimates the scale jointly) and no threshold or default selects it: whether a
   dispersion justifies it is the caller's call (maintainer, 2026-09-30).

**Claim, before the code (VERIFICATION_STANDARD §3.2)** —
:data:`DISPERSION_TWO_STAGE_CLAIM_SENTENCE`. Every producer here takes the
recipe type (data and knots only), which structurally excludes every
``mgcv``-produced key (the ADR-193 mechanical test).
:func:`fit_stage2_at_supplied_scale` takes one ``float`` — ``mgcv``'s own stage-1
dispersion, handed over as a SUPPLIED INPUT exactly as slice 7's ``phi`` was — so
the stage-2 fit can be compared with the dispersion held to the identical number
on both sides; that number is declared an input, not a compared quantity.

The gap between the two-stage and joint free-scale fits is **reported, not
compared**: it is a within-side difference (the cost of the modelling choice), so
it is information for the user's decision and not parity evidence.

Gates reuse ADR-221's committed ``eta`` / ``edf_total`` criterion, imported and
never redeclared (Anchor W5). The dispersion itself is gated on the SAME relative
scale (``2e-2``) — an imported agreement level, not a tuned one — and the
estimator identification is a derivation-free ordering test.
"""

from dataclasses import dataclass
from typing import TypedDict

import numpy as np

from polaris_re.analytics.gam_dispersion import DispersionEstimates
from polaris_re.analytics.gam_model import PolarisGAMFit, fit_polaris_gam
from polaris_re.analytics.gam_quasipoisson_conformance import (
    RQuasiPoissonFreeSpRecipe,
    fit_quasipoisson_free_sp_case,
)
from polaris_re.analytics.gam_quasipoisson_fixed_scale_conformance import (
    _fit_best_of_cold_and_unit_gamma_seed,
    fixed_scale_model_spec,
)
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.analytics.gam_term_spec import ModelSpec
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)

__all__ = [
    "DISPERSION_TWO_STAGE_CLAIM",
    "DISPERSION_TWO_STAGE_CLAIM_SENTENCE",
    "DispersionTwoStageComparison",
    "PolarisTwoStageFits",
    "RDispersionPayload",
    "RDispersionRecipe",
    "compare_dispersion_two_stage_case",
    "fit_dispersion_two_stage_case",
    "fit_stage2_at_supplied_scale",
]

_ETA_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""ADR-221's ``eta`` gate (``2e-2``), imported, not redeclared (Anchor W5)."""

_EDF_TOLERANCE = _AGREEMENT_TOLERANCE_EDF
"""ADR-221's ``edf_total`` gate (``1.0``), imported, not redeclared."""

_PHI_REL_TOLERANCE = _AGREEMENT_TOLERANCE_ETA
"""The dispersion's relative agreement level — ADR-221's ``2e-2`` reused as the
engine's committed agreement scale. Not tuned: the figures are REPORTED and the
margin to this level is part of the finding."""


class RDispersionRecipe(RQuasiPoissonFreeSpRecipe):
    """The shared recipe both sides fit — data and knots, **nothing else**
    (slice 3b's recipe verbatim: no ``sp``, no scale, no ``mgcv`` output)."""


class RDispersionEstimators(TypedDict):
    """The probe's own estimator formulas evaluated on ``mgcv``'s fit."""

    pearson: float
    fletcher: float
    deviance: float
    s_bar: float
    edf_total: float


class RDispersionFit(TypedDict):
    """One ``mgcv`` fit as the probe exports it. Read by the comparison only."""

    eta: list[float]
    offset_gap: float
    sp: list[float]
    edf_total: float
    term_edf: list[float]
    term_labels: list[str]
    scale: float
    converged: bool
    estimators: RDispersionEstimators


class RDispersionPayload(RDispersionRecipe):
    """The recipe plus ``scripts/gam_dispersion_two_stage_probe.R``'s OWN fits."""

    joint: RDispersionFit
    stage1: RDispersionFit
    phi_stage1_pearson: float
    stage2: RDispersionFit


DISPERSION_TWO_STAGE_CLAIM_SENTENCE = (
    "polaris_re's PolarisGAM (gam_model.fit_polaris_gam) fits the three-term "
    "cr / cr-by / ti design of slices 3b and 7 to an overdispersed count y from "
    "the shared recipe, and computes the Pearson, Fletcher and deviance "
    "dispersion estimates (gam_dispersion.dispersion_estimates) from ITS OWN "
    "mu and edf — jointly under quasipoisson(log) at free sp (best-of-9 starts, "
    "chosen by Polaris's own criterion; the default single start is also "
    "reported), and at stage 1 "
    "under poisson(log); stage 2 refits poisson(log) with gamma = the stage-1 "
    "Pearson dispersion (slice 7's route, slice 7b's two-start search) — never "
    "reading mgcv's own eta, sp, edf or scale; mgcv computes the same chain via "
    "gam(quasipoisson, method='REML') (m$scale), gam(poisson, method='REML') "
    "with its Pearson dispersion formed from mgcv's own mu/edf, and "
    "gam(quasipoisson, method='REML', scale = that dispersion) "
    "(scripts/gam_dispersion_two_stage_probe.R). Compared on the joint fit's "
    "eta and edf_total (multistart and single start), the dispersion "
    "(Polaris's three estimators against m$scale, which also identifies the "
    "estimator), the stage-1 Pearson dispersion, and the stage-2 eta and "
    "edf_total (each chain on its own dispersion, and Polaris at mgcv's "
    "stage-1 dispersion supplied as an input to isolate the fit from the "
    "stage-1 estimate); gated on ADR-221's committed criterion, IMPORTED and "
    "not redeclared. Coefficients are never compared (PLAN Anchor 2). The gap "
    "between each side's two-stage and joint fits is reported, not compared."
)


DISPERSION_TWO_STAGE_CLAIM = VerificationClaim(
    claim=DISPERSION_TWO_STAGE_CLAIM_SENTENCE,
    quantities=(
        ComparedQuantity(
            quantity="joint free-scale eta, multistart (Polaris vs mgcv, free sp and scale)",
            left_producer=(
                "fit_polaris_gam(quasipoisson, multistart=True) at its own selected log_lambda"
            ),
            right_producer="mgcv gam(quasipoisson, method='REML'), m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="joint free-scale eta, single start (Polaris default vs mgcv)",
            left_producer="fit_polaris_gam(quasipoisson) default single-start search",
            right_producer="mgcv gam(quasipoisson, method='REML'), m$linear.predictors",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="joint free-scale edf_total (Polaris multistart and single start vs mgcv)",
            left_producer="PolarisGAMFit.edf_total of each joint fit",
            right_producer="mgcv's own sum(m$edf) of its joint fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="joint free-scale dispersion: Polaris Fletcher vs mgcv m$scale",
            left_producer=(
                "gam_dispersion.dispersion_estimates(...).fletcher on Polaris's own "
                "free-sp quasipoisson fit's mu and edf_total"
            ),
            right_producer="mgcv's own m$scale from gam(quasipoisson, method='REML')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="joint Pearson dispersion: Polaris vs R-side formula on mgcv's fit",
            left_producer=(
                "gam_dispersion.dispersion_estimates(...).pearson on Polaris's own "
                "joint fit (reported, to say what m$scale is NOT)"
            ),
            right_producer=(
                "the probe's own sum((y-mu)^2/mu)/(n - sum(edf)) on mgcv's own joint "
                "fit's fitted.values and edf"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="joint deviance dispersion: Polaris vs R-side formula on mgcv's fit",
            left_producer=(
                "gam_dispersion.dispersion_estimates(...).deviance on Polaris's own joint fit"
            ),
            right_producer=("the probe's own m$deviance/(n - sum(edf)) on mgcv's own joint fit"),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="stage-1 Pearson dispersion (poisson fit): Polaris vs mgcv",
            left_producer=(
                "PolarisGAMFit.dispersion.pearson of Polaris's own poisson(log) free-sp fit"
            ),
            right_producer=(
                "the probe's Pearson formula on mgcv's own gam(poisson, method='REML') "
                "fitted.values and edf"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="stage-2 eta (each chain at its OWN stage-1 dispersion)",
            left_producer=(
                "fit_polaris_gam(poisson, gamma = Polaris's stage-1 Pearson dispersion) "
                "at its own selected log_lambda"
            ),
            right_producer=(
                "mgcv gam(quasipoisson, method='REML', scale = mgcv's stage-1 Pearson "
                "dispersion), m$linear.predictors"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="stage-2 edf_total (each chain at its OWN stage-1 dispersion)",
            left_producer="PolarisGAMFit.edf_total of the stage-2 fit",
            right_producer="mgcv's own sum(m$edf) of the stage-2 fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="stage-2 eta (both sides at mgcv's stage-1 dispersion, supplied)",
            left_producer=(
                "fit_stage2_at_supplied_scale: fit_polaris_gam(poisson, gamma = the "
                "supplied float) at its own selected log_lambda"
            ),
            right_producer=(
                "the same mgcv stage-2 fit, m$linear.predictors (its scale IS the "
                "supplied float; declared an input, not a compared quantity)"
            ),
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Slice 3c's provenance declaration. Every compared quantity is INDEPENDENT.
Within-side two-stage-vs-joint gaps are reported, not declared, because they are
not Polaris-vs-``mgcv`` comparisons."""


@dataclass(frozen=True)
class PolarisTwoStageFits:
    """Polaris's whole chain from the shared recipe. ``evidence`` has no default,
    so a new producer cannot skip the provenance question."""

    joint: PolarisGAMFit
    """``quasipoisson(log)``, free ``sp`` and free scale (slice 3b's producer),
    searched with ``multistart=True`` — see :data:`DISPERSION_TWO_STAGE_CLAIM_SENTENCE`
    and the module ledger entry: on this recipe the default single-start search
    settles in a worse stationary point of the SAME criterion."""
    joint_single_start: PolarisGAMFit
    """The same fit with the default single-start search (slice 3b's own
    configuration), kept because its disagreement with ``mgcv`` is a finding."""
    stage1: PolarisGAMFit
    """``poisson(log)`` at ``gamma = 1``."""
    phi_stage1: float
    """``stage1.dispersion.pearson`` — the number stage 2 holds fixed."""
    stage2: PolarisGAMFit
    """``poisson(log)`` at ``gamma = phi_stage1`` (two-start search)."""
    evidence: VerificationClaim


def _data_and_y(r_case: RDispersionRecipe) -> tuple[dict[str, np.ndarray], np.ndarray]:
    data = {
        "AttdAge": np.asarray(r_case["AttdAge"], dtype=np.float64),
        "PolYear": np.asarray(r_case["PolYear"], dtype=np.float64),
        "StudyYear_C": np.asarray(r_case["StudyYear_C"], dtype=np.float64),
    }
    return data, np.asarray(r_case["y"], dtype=np.float64)


def _poisson_spec(r_case: RDispersionRecipe) -> ModelSpec:
    return fixed_scale_model_spec(
        tuple(float(v) for v in r_case["age_knots"]),
        tuple(float(v) for v in r_case["year_knots"]),
    )


def fit_dispersion_two_stage_case(r_case: RDispersionRecipe) -> PolarisTwoStageFits:
    """The independent Python producer of the whole chain. Reads the recipe
    only; never any ``mgcv`` output."""
    data, y = _data_and_y(r_case)
    model = _poisson_spec(r_case)
    joint_single_start = fit_quasipoisson_free_sp_case(r_case)
    joint = fit_quasipoisson_free_sp_case(r_case, multistart=True)
    stage1 = fit_polaris_gam(model, data, y, gamma=1.0)
    phi = float(stage1.dispersion.pearson)
    stage2 = _fit_best_of_cold_and_unit_gamma_seed(model, data, y, phi, stage1, False)
    return PolarisTwoStageFits(
        joint=joint,
        joint_single_start=joint_single_start,
        stage1=stage1,
        phi_stage1=phi,
        stage2=stage2,
        evidence=DISPERSION_TWO_STAGE_CLAIM,
    )


def fit_stage2_at_supplied_scale(
    r_case: RDispersionRecipe, phi: float, stage1: PolarisGAMFit
) -> PolarisGAMFit:
    """Polaris's stage-2 fit at an externally supplied ``phi`` (a ``float``, not
    an ``mgcv`` payload — the ADR-193 mechanical test)."""
    if not np.isfinite(phi) or phi <= 0.0:
        raise PolarisValidationError(f"fit_stage2_at_supplied_scale: phi must be > 0, got {phi}.")
    data, y = _data_and_y(r_case)
    return _fit_best_of_cold_and_unit_gamma_seed(
        _poisson_spec(r_case), data, y, float(phi), stage1, False
    )


class DispersionTwoStageComparison(TypedDict):
    # --- the joint free-scale fit itself ---
    joint_max_abs_eta_diff: float
    joint_edf_total_diff: float
    joint_max_abs_log10_sp_diff: float
    joint_single_start_max_abs_eta_diff: float
    joint_single_start_edf_total_diff: float
    joint_single_start_agrees: bool
    # --- estimator identification, joint (multistart) fit ---
    r_scale: float
    polaris_fletcher: float
    polaris_pearson: float
    polaris_deviance: float
    fletcher_rel_diff: float
    pearson_rel_diff: float
    deviance_rel_diff: float
    identifies_fletcher: bool
    r_pearson_on_mgcv_fit: float
    r_deviance_on_mgcv_fit: float
    # --- stage 1 ---
    phi_stage1_polaris: float
    phi_stage1_r: float
    phi_stage1_rel_diff: float
    # --- stage 2, each chain at its own dispersion ---
    stage2_max_abs_eta_diff: float
    stage2_edf_total_diff: float
    stage2_max_abs_log10_sp_diff: float
    # --- stage 2, both at mgcv's stage-1 dispersion ---
    stage2_supplied_max_abs_eta_diff: float
    stage2_supplied_edf_total_diff: float
    # --- reported, NOT compared: cost of the modelling choice, per side ---
    polaris_two_stage_vs_joint_max_abs_eta: float
    r_two_stage_vs_joint_max_abs_eta: float
    polaris_two_stage_vs_joint_edf_total: float
    r_two_stage_vs_joint_edf_total: float
    r_phi_stage1_vs_joint_scale: float
    offset_gap: float
    converged: bool
    agrees: bool
    evidence: VerificationClaim


def _rel(a: float, b: float) -> float:
    return float(abs(a - b) / abs(b))


def _eta(payload: RDispersionFit, ref: PolarisGAMFit, label: str) -> np.ndarray:
    arr = np.asarray(payload["eta"], dtype=np.float64)
    if arr.shape != ref.eta.shape:
        raise PolarisValidationError(
            f"compare_dispersion_two_stage_case: R {label} eta has shape {arr.shape}, "
            f"Polaris has {ref.eta.shape}."
        )
    return arr


def compare_dispersion_two_stage_case(
    python_fits: PolarisTwoStageFits,
    r_case: RDispersionPayload,
    stage2_at_r_phi: PolarisGAMFit,
) -> DispersionTwoStageComparison:
    """Compare on every quantity :data:`DISPERSION_TWO_STAGE_CLAIM` declares.

    ``agrees`` requires: ``eta``/``edf_total`` within ADR-221's imported
    criterion at stage 2 (own-phi AND supplied-phi), the three dispersion
    comparisons within ``_PHI_REL_TOLERANCE`` where gated (Fletcher vs
    ``m$scale``; stage-1 Pearson), AND ``identifies_fletcher`` — Fletcher is
    strictly closer to ``m$scale`` than Pearson and deviance are.
    """
    joint_r, s2_r = r_case["joint"], r_case["stage2"]
    pj, p1, p2 = python_fits.joint, python_fits.stage1, python_fits.stage2
    d: DispersionEstimates = pj.dispersion

    r_scale = float(joint_r["scale"])
    fl, pe, de = (_rel(d.fletcher, r_scale), _rel(d.pearson, r_scale), _rel(d.deviance, r_scale))
    identifies = fl < pe and fl < de

    phi_r = float(r_case["phi_stage1_pearson"])
    phi_rel = _rel(python_fits.phi_stage1, phi_r)

    eta2_r = _eta(s2_r, p2, "stage 2")
    eta2_diff = float(np.max(np.abs(eta2_r - p2.eta)))
    edf2_diff = float(p2.edf_total - s2_r["edf_total"])
    log_sp_diff = float(
        np.max(np.abs(p2.log_lambda - np.log10(np.atleast_1d(np.asarray(s2_r["sp"], np.float64)))))
    )
    eta2s_diff = float(np.max(np.abs(eta2_r - stage2_at_r_phi.eta)))
    edf2s_diff = float(stage2_at_r_phi.edf_total - s2_r["edf_total"])

    eta_joint_r = _eta(joint_r, pj, "joint")
    joint_eta_diff = float(np.max(np.abs(eta_joint_r - pj.eta)))
    joint_edf_diff = float(pj.edf_total - joint_r["edf_total"])
    joint_sp_diff = float(
        np.max(
            np.abs(pj.log_lambda - np.log10(np.atleast_1d(np.asarray(joint_r["sp"], np.float64))))
        )
    )
    ss = python_fits.joint_single_start
    ss_eta_diff = float(np.max(np.abs(eta_joint_r - ss.eta)))
    ss_edf_diff = float(ss.edf_total - joint_r["edf_total"])
    ss_agrees = ss.converged and ss_eta_diff < _ETA_TOLERANCE and abs(ss_edf_diff) < _EDF_TOLERANCE
    agrees = (
        pj.converged
        and p1.converged
        and p2.converged
        and bool(joint_r["converged"])
        and bool(s2_r["converged"])
        and joint_eta_diff < _ETA_TOLERANCE
        and abs(joint_edf_diff) < _EDF_TOLERANCE
        and fl < _PHI_REL_TOLERANCE
        and identifies
        and phi_rel < _PHI_REL_TOLERANCE
        and eta2_diff < _ETA_TOLERANCE
        and abs(edf2_diff) < _EDF_TOLERANCE
        and eta2s_diff < _ETA_TOLERANCE
        and abs(edf2s_diff) < _EDF_TOLERANCE
    )
    return DispersionTwoStageComparison(
        joint_max_abs_eta_diff=joint_eta_diff,
        joint_edf_total_diff=joint_edf_diff,
        joint_max_abs_log10_sp_diff=joint_sp_diff,
        joint_single_start_max_abs_eta_diff=ss_eta_diff,
        joint_single_start_edf_total_diff=ss_edf_diff,
        joint_single_start_agrees=ss_agrees,
        r_scale=r_scale,
        polaris_fletcher=float(d.fletcher),
        polaris_pearson=float(d.pearson),
        polaris_deviance=float(d.deviance),
        fletcher_rel_diff=fl,
        pearson_rel_diff=pe,
        deviance_rel_diff=de,
        identifies_fletcher=identifies,
        r_pearson_on_mgcv_fit=float(joint_r["estimators"]["pearson"]),
        r_deviance_on_mgcv_fit=float(joint_r["estimators"]["deviance"]),
        phi_stage1_polaris=python_fits.phi_stage1,
        phi_stage1_r=phi_r,
        phi_stage1_rel_diff=phi_rel,
        stage2_max_abs_eta_diff=eta2_diff,
        stage2_edf_total_diff=edf2_diff,
        stage2_max_abs_log10_sp_diff=log_sp_diff,
        stage2_supplied_max_abs_eta_diff=eta2s_diff,
        stage2_supplied_edf_total_diff=edf2s_diff,
        polaris_two_stage_vs_joint_max_abs_eta=float(np.max(np.abs(p2.eta - pj.eta))),
        r_two_stage_vs_joint_max_abs_eta=float(np.max(np.abs(eta2_r - eta_joint_r))),
        polaris_two_stage_vs_joint_edf_total=float(p2.edf_total - pj.edf_total),
        r_two_stage_vs_joint_edf_total=float(s2_r["edf_total"] - joint_r["edf_total"]),
        r_phi_stage1_vs_joint_scale=float(phi_r - r_scale),
        offset_gap=float(max(joint_r["offset_gap"], s2_r["offset_gap"])),
        converged=pj.converged and p1.converged and p2.converged,
        agrees=agrees,
        evidence=DISPERSION_TWO_STAGE_CLAIM,
    )
