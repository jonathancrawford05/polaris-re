"""How far does Wood's "numerical zero leakage" actually reach in THIS model?

DIAGNOSTIC ONLY, never committed parity evidence — it reads ``mgcv``'s own ``eta``.
Same status as ``gam_deriv_probe.R`` (ADR-201) and ``gam_vc_probe.R`` (ADR-202).

WHY IT EXISTS. Wood (2011) §3.1 says the leakage "leads to serious errors in
evaluation of beta-hat, ``|S|+`` AND ``|X'WX + S|`` and their derivatives" — so
scoping PLAN slice 5c means knowing which of those are true *here*, not in general.
The maintainer asked for the full Appendix B reparameterisation "especially if we
need to do it for parity"; this answers the conditional.

It reports, per fixed-``sp`` point:

* **max abs ``eta`` difference against mgcv** — is the FITTER degraded? Appendix B's
  reparameterisation-through-the-fit and §3.3's stable least squares are what a
  degraded fitter would need.
* **``log|X'WX + S|``, naive ``slogdet`` vs a diagonally-preconditioned Cholesky** —
  is the OTHER log-determinant in the REML score degraded? Wood's preconditioning
  (``P_ii = |S_ii|^(1/2)``, Cholesky of ``P^-1 S P^-1``) is the cheap stand-in for
  the full transform, and a material gap between the two would implicate it.
* **``cond(X'WX + S)`` and the rank of ``S`` at the shipped ``1e-10`` cut** — the two
  quantities that say how hard the point is.

The ``extreme`` point is deliberately harsher than anything the epic has measured
(12 decades of λ spread) and is still inside
``gam_model.PRODUCTION_LOG10_BOUNDS = (-2, 12)``, so it is genuinely reachable rather
than a strawman.

Usage:
    Rscript scripts/gam_spread_lambda_probe.R out.json
    uv run python scripts/gam_spread_lambda_compare.py out.json
"""

import json
import pathlib
import sys

import numpy as np

from polaris_re.analytics.gam_fit import penalized_irls_general
from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
from polaris_re.analytics.gam_model_conformance import _multiterm_model_spec

SHIPPED_TOL = 1e-10
"""The null-space cut ``gam_reml.reml_score_general`` ships with."""


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
    p = design["x"].shape[1]

    print(f"n={len(y)}  p={p}  mgcv {payload['mgcv_version']}")
    print()
    print(
        f"{'point':<13}{'spread':>7}{'max|d eta|':>13}{'logdet gap':>13}"
        f"{'cond':>12}{'rank@1e-10':>12}"
    )
    print("-" * 70)

    for row in payload["points"]:
        log_lambda = np.asarray(row["log10_sp"], dtype=np.float64)
        penalty = np.zeros((p, p), dtype=np.float64)
        for lam, block in zip(10.0**log_lambda, design["penalty_blocks"], strict=True):
            penalty = penalty + lam * block

        fit = penalized_irls_general(
            design["x"], y, family=family, penalty=penalty, weights=weights
        )
        eta_ours = design["x"] @ fit.coef
        d_eta = np.abs(eta_ours - np.asarray(row["eta"], dtype=np.float64))

        mu = family.link.linkinv(eta_ours)
        irls_weights = weights * family.link.mu_eta(eta_ours) ** 2 / family.variance(mu)
        h = design["x"].T @ (irls_weights[:, None] * design["x"]) + penalty

        _sign, naive = np.linalg.slogdet(h)
        # Wood's diagonal preconditioning, §3.1: P_ii = |H_ii|^(1/2), Cholesky of
        # P^-1 H P^-1, so logdet(H) = 2*sum(log diag(L)) + 2*sum(log P_ii).
        scale = np.sqrt(np.abs(np.diag(h)))
        chol = np.linalg.cholesky(h / np.outer(scale, scale))
        preconditioned = 2.0 * np.sum(np.log(np.diag(chol))) + 2.0 * np.sum(np.log(scale))

        eigenvalues = np.linalg.eigvalsh(penalty)
        rank = int((eigenvalues > max(eigenvalues.max(), 1e-300) * SHIPPED_TOL).sum())

        print(
            f"{row['name']:<13}{log_lambda.max() - log_lambda.min():>7.1f}"
            f"{d_eta.max():>13.3e}{abs(naive - preconditioned):>13.2e}"
            f"{np.linalg.cond(h):>12.2e}{rank:>12d}"
        )

    print("-" * 70)
    print(
        "A 'logdet gap' that stays tiny as cond climbs means |X'WX + S| is NOT\n"
        "affected — it is full rank and positive definite, so unlike log|S|+ it has\n"
        "no null-space decision to get wrong. A rank that MOVES with lambda is the\n"
        "defect PLAN slice 5c fixes."
    )


if __name__ == "__main__":
    main(sys.argv[1])
