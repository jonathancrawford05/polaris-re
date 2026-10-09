"""The user guide's worked example, predicted at new rows — preview slice P5 (ADR-254).

**Claim sentence (ADR-193), written before the code.** *"Polaris
(``GamFit.predict(new_rows, type, se_fit, unconditional)`` on the fit of
:data:`polaris_re.gam.example.GUIDE_FORMULA`) computes the link- and response-scale
predictions and their standard errors from its own stored term states and its own
``Vp``/``Vc``; ``mgcv`` computes them via ``predict.gam(m, newdata, se.fit=TRUE[,
unconditional=TRUE])`` on ``gam(<the same string>, method='REML')``; compared on
those columns at 60 held-out rows."*

**Provenance.** Every column is INDEPENDENT. :func:`predict_guide_example` takes the
Polaris :class:`~polaris_re.gam.api.GamFit` and the held-out *covariates* only; the
``mgcv`` outputs live under a different key (``cell["predict"]``) and are read by
:func:`compare_guide_predict` alone. The fit, structure and ``summary()`` columns of the
same cell are the P3 and P4 comparisons (``FORMULA_CLAIM``, ``SUMMARY_CLAIM``) and are
not re-declared here: this claim adds exactly the prediction columns.

The tolerances are imported, not chosen: ADR-221's ``eta`` gate and ADR-250's relative
``se.fit`` gate (both derived before their first tier-3 run).
"""

from dataclasses import dataclass, field
from typing import TypedDict

import numpy as np
import polars as pl

from polaris_re.analytics.gam_predict_conformance import _SE_REL_TOLERANCE
from polaris_re.analytics.gam_select_free_sp_conformance import _AGREEMENT_TOLERANCE_ETA
from polaris_re.core.exceptions import PolarisValidationError
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
)
from polaris_re.gam.api import GamFit

__all__ = [
    "GUIDE_CLAIM",
    "GuidePredictComparison",
    "GuidePrediction",
    "compare_guide_predict",
    "predict_guide_example",
]


class GuideNewData(TypedDict):
    """Held-out covariates only — no ``mgcv`` output is a key here."""

    age: list[float]
    duration: list[float]
    sex: list[str]
    log_exposure: list[float]


@dataclass(frozen=True)
class GuidePrediction:
    """Polaris's side: what the guide's ``predict`` calls return."""

    link: np.ndarray
    link_se: np.ndarray
    link_se_unconditional: np.ndarray
    response: np.ndarray
    response_se: np.ndarray


def predict_guide_example(fit: GamFit, newdata: GuideNewData) -> GuidePrediction:
    """Polaris's producer. Its signature takes the fit and the held-out covariates; it
    cannot read ``mgcv``'s predictions. A caller may pass the whole probe block (a
    ``TypedDict`` does not strip keys at runtime), so the covariates are projected out."""
    frame = pl.DataFrame({k: list(newdata[k]) for k in ("age", "duration", "sex", "log_exposure")})
    link, link_se = fit.predict(frame, "link", se_fit=True)
    _, link_se_unc = fit.predict(frame, "link", se_fit=True, unconditional=True)
    response, response_se = fit.predict(frame, "response", se_fit=True)
    return GuidePrediction(
        link=link,
        link_se=link_se,
        link_se_unconditional=link_se_unc,
        response=response,
        response_se=response_se,
    )


GUIDE_CLAIM = VerificationClaim(
    claim=(
        "Polaris (GamFit.predict on the fit of the guide's formula string) computes link- and "
        "response-scale predictions and their standard errors from its own stored term states "
        "and its own Vp / Vc; mgcv computes them via predict.gam(m, newdata, se.fit=TRUE"
        "[, unconditional=TRUE]) on gam(<the same string>, method='REML'); compared on those "
        "columns at 60 held-out rows."
    ),
    quantities=(
        ComparedQuantity(
            quantity="link prediction at held-out rows (gated, ADR-221 eta)",
            left_producer="GamFit.predict(newdata, 'link') from stored knots + constraints",
            right_producer="mgcv predict.gam(m, newdata, type='link')",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="link se.fit with Vp (gated, ADR-250 relative)",
            left_producer="GamFit.predict(..., se_fit=True): sqrt(diag(X_new Vp X_new'))",
            right_producer="mgcv predict.gam(m, newdata, se.fit=TRUE)$se.fit",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="link se.fit with Vc (gated, ADR-250 relative)",
            left_producer="GamFit.predict(..., se_fit=True, unconditional=True)",
            right_producer="mgcv predict.gam(m, newdata, se.fit=TRUE, unconditional=TRUE)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="response prediction and its se.fit (reported, not gated)",
            left_producer="GamFit.predict(newdata, 'response', se_fit=True)",
            right_producer="mgcv predict.gam(m, newdata, type='response', se.fit=TRUE)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)
"""Every column INDEPENDENT; the two sides share only the formula text and the data."""


@dataclass(frozen=True)
class GuidePredictComparison:
    max_abs_link_diff: float
    max_rel_link_se: float
    max_rel_link_se_unconditional: float
    max_rel_response_diff: float
    max_rel_response_se: float
    agrees: bool
    evidence: VerificationClaim = field(default=GUIDE_CLAIM)


def _arr(value: float | list[float]) -> np.ndarray:
    return np.asarray(value if isinstance(value, list) else [value], dtype=np.float64)


def compare_guide_predict(
    python: GuidePrediction, block: dict[str, object]
) -> GuidePredictComparison:
    """Compare Polaris with ``mgcv`` on the declared prediction columns."""
    ref = {
        k: _arr(block[k])  # type: ignore[arg-type]
        for k in ("link", "link_se", "link_se_unconditional", "response", "response_se")
    }
    if python.link.shape != ref["link"].shape:
        raise PolarisValidationError(
            f"compare_guide_predict: shapes {python.link.shape} vs {ref['link'].shape}."
        )

    def rel(ours: np.ndarray, theirs: np.ndarray) -> float:
        return float(np.max(np.abs(ours - theirs) / np.abs(theirs)))

    link_diff = float(np.max(np.abs(python.link - ref["link"])))
    se = rel(python.link_se, ref["link_se"])
    se_unc = rel(python.link_se_unconditional, ref["link_se_unconditional"])
    return GuidePredictComparison(
        max_abs_link_diff=link_diff,
        max_rel_link_se=se,
        max_rel_link_se_unconditional=se_unc,
        max_rel_response_diff=rel(python.response, ref["response"]),
        max_rel_response_se=rel(python.response_se, ref["response_se"]),
        agrees=bool(
            link_diff < _AGREEMENT_TOLERANCE_ETA
            and se < _SE_REL_TOLERANCE
            and se_unc < _SE_REL_TOLERANCE
        ),
    )
