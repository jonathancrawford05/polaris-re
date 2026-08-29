"""Defect B: does the REML score use the wrong Hessian for a non-canonical link?

DIAGNOSTIC ONLY, never committed parity evidence — it reads ``mgcv``'s own score.
Same status as ``gam_deriv_probe.R`` (ADR-201) and ``gam_vc_probe.R`` (ADR-202).

Wood (2011) eq. (4) builds the REML criterion on ``H = -d2l/dbeta dbeta^T``, the
**observed** Hessian that Newton-based PIRLS produces as a by-product (§3.2, weights
carrying ``alpha_i = 1 + (y_i - mu_i)(V'_i/V_i + g''_i/g'_i)``).
``gam_reml.reml_score_general`` uses the **expected** (Fisher) weight instead —
Wood's ``alpha_i == 1``. He flags the substitution: the expected Hessian "gave worse
performance than GCV **when non-canonical links were used**", and binomial/cloglog is
non-canonical (binomial's canonical link is logit).

``W`` depends on ``mu``, hence on ``beta-hat``, hence on ``sp`` — so the discrepancy
is ``sp``-DEPENDENT, which is the signature the epic has chased since ADR-208.

This applies both candidate corrections and reports the spread of ``ours - mgcv``
under each, so the two defects can be separated:

* ``raw``        — as shipped
* ``+nullspace`` — Defect A only (the ``log|S|+`` cut; Wood §3.1 / Appendix B)
* ``+both``      — Defect A and Defect B together

WHY THIS IS NOT THE FIX. ``H`` is obtained here by central-differencing the
per-observation deviance in ``eta`` — the terms are independent, so every ``i``
differs at once. That is how the defect was FOUND; it is not how it should be FIXED.
The difference step's own error sits at the level being measured, so it cannot
demonstrate closure at tier 3. PLAN slice 5c requires the analytic ``alpha_i`` of
Wood §3.2 instead, with this probe as the cross-check.

Usage:
    Rscript scripts/gam_fixed_sp_score_probe.R out.json
    uv run python scripts/gam_hessian_weight_probe.py out.json
"""

import json
import pathlib
import sys

import numpy as np

from polaris_re.analytics.gam_family import _binomial_deviance_terms
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _multiterm_model_spec
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

SHIPPED_TOL = 1e-10
TIGHTER_TOL = 1e-12
DIFF_STEP = 1e-5
"""Central-difference step in ``eta`` for the observed Hessian. Its error is why
this probe diagnoses rather than fixes — see the module docstring."""


def observed_hessian_weights(
    y: np.ndarray, eta: np.ndarray, weights: np.ndarray, family: object
) -> np.ndarray:
    """``W_ii = 0.5 * d2 D_i / d eta_i^2`` — the observed Hessian's diagonal at
    ``phi = 1``, since ``l = l_sat - D/(2 phi)``. Per-observation deviance terms are
    independent, so a single vectorised perturbation differences all of them."""

    def deviance_terms(e: np.ndarray) -> np.ndarray:
        return 2.0 * weights * _binomial_deviance_terms(y, family.link.linkinv(e))

    return (
        0.5
        * (
            deviance_terms(eta + DIFF_STEP)
            - 2.0 * deviance_terms(eta)
            + deviance_terms(eta - DIFF_STEP)
        )
        / DIFF_STEP**2
    )


def main(payload_path: str) -> None:
    payload = json.loads(pathlib.Path(payload_path).read_text())
    model = _multiterm_model_spec(
        tuple(float(v) for v in payload["age_knots"]),
        tuple(float(v) for v in payload["year_knots"]),
    )
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    y = np.asarray(payload["y"], dtype=np.float64)
    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    weights = data["ExposCnt"]
    x = design["x"]
    p = x.shape[1]

    print(f"n={len(y)}  p={p}  family={model.family}/{model.link} (NON-canonical)")
    print()
    print(f"{'point':<13}{'spread':>7}{'raw':>13}{'+nullspace':>13}{'+both':>13}{'neg W':>7}")
    print("-" * 66)

    raw: list[float] = []
    null_only: list[float] = []
    both: list[float] = []
    for row in payload["points"]:
        log_lambda = np.asarray(row["log10_sp"], dtype=np.float64)
        penalty = np.zeros((p, p), dtype=np.float64)
        for lam, block in zip(10.0**log_lambda, design["penalty_blocks"], strict=True):
            penalty = penalty + lam * block
        coef, ours = penalized_fit_and_score(
            y, x, family, design["penalty_blocks"], log_lambda, weights=weights
        )
        mgcv_score = float(row["mgcv_score"])

        eigenvalues = np.linalg.eigvalsh(penalty)
        largest = max(eigenvalues.max(), 1e-300)
        extra = eigenvalues[
            (eigenvalues > largest * TIGHTER_TOL) & ~(eigenvalues > largest * SHIPPED_TOL)
        ]
        after_a = ours - np.sum(np.log(extra)) / 2.0

        eta = x @ coef
        mu = family.link.linkinv(eta)
        fisher = weights * family.link.mu_eta(eta) ** 2 / family.variance(mu)
        observed = observed_hessian_weights(y, eta, weights, family)
        _s, logdet_fisher = np.linalg.slogdet(x.T @ (fisher[:, None] * x) + penalty)
        _s, logdet_observed = np.linalg.slogdet(x.T @ (observed[:, None] * x) + penalty)
        after_b = after_a + 0.5 * (logdet_observed - logdet_fisher)

        raw.append(ours - mgcv_score)
        null_only.append(after_a - mgcv_score)
        both.append(after_b - mgcv_score)
        print(
            f"{row['name']:<13}{log_lambda.max() - log_lambda.min():>7.1f}"
            f"{ours - mgcv_score:>13.5f}{after_a - mgcv_score:>13.5f}"
            f"{after_b - mgcv_score:>13.5f}{int((observed < 0).sum()):>7d}"
        )

    print("-" * 66)
    for label, values in (("raw", raw), ("+nullspace", null_only), ("+both", both)):
        arr = np.asarray(values)
        print(f"SPREAD {label:<12}: {arr.max() - arr.min():.6f}")
    print()
    print(
        "A spread that collapses only under '+both' means there are TWO defects and\n"
        "fixing the null-space cut alone will not close the gap. The 'neg W' column\n"
        "counts observed weights below zero: Wood notes they need not all be positive\n"
        "under a non-canonical link, and that is when §3.3's stable least squares and\n"
        "Appendix B's square root E stop being optional."
    )


if __name__ == "__main__":
    main(sys.argv[1])
