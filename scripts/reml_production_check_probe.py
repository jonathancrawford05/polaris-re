#!/usr/bin/env python3
"""
reml_production_check_probe.py — §3.1/§3.2/§3.3 of
`docs/WORK_ORDER_reml_penalized_deviance_production_check.md`.

Diagnostic-only. Reads the already-committed ten-cell conformance exchange
(`data/mgcv_exchange/synthetic`), the committed `python_reference.json`, and
an `mgcv_reference.json` (produced by `scripts/mgcv_conformance.R`, NOT
committed — regenerate it locally or read it from a CI dispatch of
`mgcv-conformance.yml`, same as every other probe in this epic). No new R
work: `mgcv_reference.json` already exports `reml_score` (`m$gcv.ubre`) per
cell (`docs/RUNBOOK_mgcv_conformance.md`).

Prints a report to stdout — readable via `get_job_logs` on a tier-3 CI
dispatch, same discipline ADR-194's methodology fix established for every
later probe in this epic.

Usage:
    Rscript scripts/mgcv_conformance.R   # writes mgcv_reference.json locally
    uv run python scripts/reml_production_check_probe.py
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
from scipy.special import gammaln  # noqa: E402

from polaris_re.analytics.experience_mgcv_conformance import (  # noqa: E402
    DESIGNS,
    read_exchange,
    synthetic_cells,
)
from polaris_re.analytics.gam_reml_production_check import (  # noqa: E402
    PRODUCTION_REML_CHECK_CLAIM,
    CorrectedLambdaSelection,
    measure_production_score_gap,
    score_shape_diagnostic,
    select_lambdas_corrected,
)
from polaris_re.core.verification import evidence_markdown  # noqa: E402

DEFAULT_EXCHANGE = REPO_ROOT / "data" / "mgcv_exchange" / "synthetic"

FREE_SP_CELLS: dict[str, str] = {
    # cell name -> design_id. with_factor is looked up per-design off
    # DesignSpec.with_factor (via by_id below), not restated here — a second,
    # hand-maintained copy is exactly the silent-drift risk this module
    # guards against elsewhere (LAMBDA_LOG10_BOUNDS is imported, not
    # restated, and test_lambda_log10_bounds_is_the_production_default pins
    # it) — PR #204 review [P2].
    "l2-free-sp": "d1",
    "l2-free-sp-factors": "d2",
    "l2-free-sp-kb": "d3",
}


def _saturated_poisson_loglik(deaths: np.ndarray) -> float:
    """``l_sat = sum(y*log(y) - y - log(y!))`` — the saturated Poisson
    log-likelihood, matching ADR-189 amendment 1's own convention-offset
    formula (``≈ -l_sat/gamma``, found in every cell of the OLD score against
    mgcv's raw ``reml_score``). ``mgcv`` scores on deviance; the production
    score scores on the full log-likelihood, and this is the additive
    constant that separates the two conventions — recomputed here, not
    assumed, so §3.1's offset-adjusted residual is directly comparable to
    that already-documented number rather than a fresh, incomparable one."""
    y = np.asarray(deaths, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(
            np.sum(np.where(y > 0.0, y * np.log(y), 0.0)) - np.sum(y) - np.sum(gammaln(y + 1.0))
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exchange", type=Path, default=DEFAULT_EXCHANGE)
    parser.add_argument(
        "--python-reference",
        type=Path,
        default=None,
        help="Default: <exchange>/python_reference.json",
    )
    parser.add_argument(
        "--mgcv-reference", type=Path, default=None, help="Default: <exchange>/mgcv_reference.json"
    )
    args = parser.parse_args(argv)

    python_path = args.python_reference or args.exchange / "python_reference.json"
    mgcv_path = args.mgcv_reference or args.exchange / "mgcv_reference.json"
    for path, who in ((python_path, "Python"), (mgcv_path, "mgcv")):
        if not path.exists():
            print(
                f"reml_production_check_probe.py: missing {who} reference {path}.", file=sys.stderr
            )
            return 1

    bundle = read_exchange(args.exchange)
    python_ref = json.loads(python_path.read_text())
    mgcv_ref = json.loads(mgcv_path.read_text())

    lines: list[str] = []
    lines.append("docs/WORK_ORDER_reml_penalized_deviance_production_check.md — §3.1/§3.2/§3.3")
    lines.append("")
    lines.append(f"exchange: {args.exchange}")
    lines.append(f"python_reference exchange_sha256: {python_ref.get('exchange_sha256')}")
    lines.append(f"mgcv_reference exchange_sha256:   {mgcv_ref.get('exchange_sha256')}")
    lines.append(
        f"mgcv: r_version={mgcv_ref.get('r_version')!r} "
        f"mgcv_version={mgcv_ref.get('mgcv_version')!r}"
    )
    lines.append("")

    # ------------------------------------------------------------------ #
    # §3.1
    # ------------------------------------------------------------------ #
    lines.append("## §3.1 — per-cell score, current vs corrected, against mgcv's own m$gcv.ubre")
    lines.append("")
    lines.append(evidence_markdown(PRODUCTION_REML_CHECK_CLAIM))
    lines.append("")
    lines.append(
        "**Raw gap** (`mgcv_score - python_score`) carries a huge additive convention "
        "offset unrelated to this work order's question — ADR-189 amendment 1 already "
        "found `≈ -l_sat/gamma` (mgcv scores on deviance; the production score scores on "
        "the full log-likelihood) in every cell of the OLD score, with a further "
        "'unexplained' residual of 0.93-3.17 surviving after removing it. The "
        "**offset-adjusted residual** (`gap + l_sat/gamma`) below is the quantity "
        "directly comparable to that already-documented number."
    )
    lines.append("")
    lines.append(
        "| cell | mgcv score | current python | corrected python | l_sat/gamma | "
        "residual (current) | residual (corrected) | |residual| collapsed? |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")

    by_id = {d.design_id: d for d in DESIGNS}

    gaps = {}
    for cell_name, design_id in FREE_SP_CELLS.items():
        export = bundle.designs[design_id]
        p_cell = python_ref["cells"][cell_name]
        m_cell = mgcv_ref["cells"][cell_name]
        coef = np.asarray(p_cell["coef"], dtype=np.float64)
        lambda_age, lambda_year = (float(v) for v in p_cell["sp"])
        gamma = float(p_cell["gamma"])
        mgcv_score = float(m_cell["reml_score"])
        gap = measure_production_score_gap(
            cell_name, export, coef, lambda_age, lambda_year, gamma, mgcv_score
        )
        gaps[cell_name] = gap
        l_sat_over_gamma = _saturated_poisson_loglik(export.deaths) / gamma
        residual_current = gap.gap_current + l_sat_over_gamma
        residual_corrected = gap.gap_corrected + l_sat_over_gamma
        collapsed = abs(residual_corrected) < abs(residual_current)
        lines.append(
            f"| `{cell_name}` | {gap.mgcv_score:.6f} | {gap.current_python_score:.6f} | "
            f"{gap.corrected_python_score:.6f} | {l_sat_over_gamma:.6f} | "
            f"{residual_current:.6f} | {residual_corrected:.6f} | "
            f"{'yes (smaller)' if collapsed else 'NO (larger)'} |"
        )
    lines.append("")
    lines.append(
        "Both sides select a DIFFERENT lambda at this cell (ours from a 0.25-decade grid "
        "at the CURRENT, uncorrected criterion; mgcv continuously) — this residual is "
        "therefore NOT expected to collapse to float noise the way ADR-196's FIXED-sp, "
        "matched-point pairwise-difference measurement did; it mixes any remaining "
        "formula gap with the point mismatch. See §3.2 below for a matched-point-free "
        "comparison (does the SELECTED point move closer to mgcv's)."
    )
    lines.append("")

    # ------------------------------------------------------------------ #
    # §3.2
    # ------------------------------------------------------------------ #
    lines.append("## §3.2 — does the corrected criterion select a different grid point?")
    lines.append("")
    lines.append(
        "Registered prediction (work order §3.2): if the missing term is a real bug, the "
        "corrected selection should land measurably CLOSER to mgcv's own free-sp selection "
        "than the current shipped selection does. If it lands on the SAME grid point, or "
        "not closer, that is itself the finding — the grid's own resolution (0.25 decade) "
        "may already be absorbing a small formula error."
    )
    lines.append("")
    lines.append(
        "| cell | current (λ_age, λ_year) | corrected (λ_age, λ_year) | mgcv (λ_age, λ_year) | "
        "same grid point? | current dist to mgcv (log10) | corrected dist to mgcv (log10) | "
        "closer? |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---|")

    corrected_selections: dict[str, CorrectedLambdaSelection] = {}
    for cell_name, design_id in FREE_SP_CELLS.items():
        spec = by_id[design_id]
        cells = synthetic_cells(with_factor=spec.with_factor)
        p_cell = python_ref["cells"][cell_name]
        m_cell = mgcv_ref["cells"][cell_name]
        current_sp = tuple(float(v) for v in p_cell["sp"])
        mgcv_sp = tuple(float(v) for v in m_cell["sp"])
        gamma = float(p_cell["gamma"])

        corrected = select_lambdas_corrected(
            cells, gamma=gamma, k_age=spec.k_age, k_year=spec.k_year
        )
        corrected_selections[cell_name] = corrected
        corrected_sp = (corrected.lambda_age, corrected.lambda_year)

        same_point = bool(
            np.isclose(current_sp[0], corrected_sp[0], rtol=1e-9)
            and np.isclose(current_sp[1], corrected_sp[1], rtol=1e-9)
        )

        def log10_dist(sp: tuple[float, float], ref: tuple[float, float] = mgcv_sp) -> float:
            return float(
                np.sqrt(
                    (np.log10(sp[0]) - np.log10(ref[0])) ** 2
                    + (np.log10(sp[1]) - np.log10(ref[1])) ** 2
                )
            )

        dist_current = log10_dist(current_sp)
        dist_corrected = log10_dist(corrected_sp)
        closer = dist_corrected < dist_current

        lines.append(
            f"| `{cell_name}` | ({current_sp[0]:.4f}, {current_sp[1]:.4f}) | "
            f"({corrected_sp[0]:.4f}, {corrected_sp[1]:.4f}) | "
            f"({mgcv_sp[0]:.4f}, {mgcv_sp[1]:.4f}) | {same_point} | "
            f"{dist_current:.4f} | {dist_corrected:.4f} | {closer} |"
        )
    lines.append("")
    lines.append(
        "**EDF at each selection** (work order §3.2 point 2 — `edf_total`/`edf_tensor`/"
        "`edf_factors`, not only lambda). `current`/`mgcv` are read directly off "
        "`python_reference.json`/`mgcv_reference.json` (already-committed fits at each "
        "side's own selection); `corrected` is a fresh fit AT the corrected selection's "
        "own `(λ_age, λ_year)` (`select_lambdas_corrected`'s one extra fit at its "
        "selected point, PR #204 review [P1]). All three are INDEPENDENT pairwise: no "
        "producer's signature accepts another side's edf, coefficients or score — same "
        "mechanical test (ADR-193) already applied to the λ-distance columns above."
    )
    lines.append("")
    lines.append(
        "| cell | edf_total (current) | edf_total (corrected) | edf_total (mgcv) | "
        "edf_tensor (current) | edf_tensor (corrected) | edf_tensor (mgcv) | "
        "edf_factors (current) | edf_factors (corrected) | edf_factors (mgcv) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell_name in FREE_SP_CELLS:
        p_cell = python_ref["cells"][cell_name]
        m_cell = mgcv_ref["cells"][cell_name]
        corrected = corrected_selections[cell_name]
        lines.append(
            f"| `{cell_name}` | {float(p_cell['edf_total']):.4f} | "
            f"{corrected.edf_total:.4f} | {float(m_cell['edf_total']):.4f} | "
            f"{float(p_cell['edf_tensor']):.4f} | {corrected.edf_tensor:.4f} | "
            f"{float(m_cell['edf_tensor']):.4f} | {float(p_cell['edf_factors']):.4f} | "
            f"{corrected.edf_factors:.4f} | {float(m_cell['edf_factors']):.4f} |"
        )
    lines.append("")

    # ------------------------------------------------------------------ #
    # §3.3
    # ------------------------------------------------------------------ #
    lines.append("## §3.3 — does the score's shape near the optimum change under the correction?")
    lines.append("")
    lines.append(
        "Evaluated at the ALREADY-SELECTED (current, shipped) (lambda_age, lambda_year) — "
        "no re-selection. The fit (and therefore the Jacobian d(beta)/d(log lambda)) does "
        "not depend on which score formula is used, so a difference here isolates to the "
        "Hessian / eigenvalues / n_floored alone."
    )
    lines.append("")
    lines.append(
        "| cell | eigenvalues (current) | eigenvalues (corrected) | n_floored (current) | "
        "n_floored (corrected) | max abs Hessian diff | mean diag(Vb) (shipped) | "
        "inflation (current) | inflation (corrected) | mgcv inflation (reported) |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")

    for cell_name, design_id in FREE_SP_CELLS.items():
        spec = by_id[design_id]
        cells = synthetic_cells(with_factor=spec.with_factor)
        p_cell = python_ref["cells"][cell_name]
        m_cell = mgcv_ref["cells"][cell_name]
        gamma = float(p_cell["gamma"])
        lambda_age, lambda_year = (float(v) for v in p_cell["sp"])

        diag = score_shape_diagnostic(
            cells,
            lambda_age=lambda_age,
            lambda_year=lambda_year,
            gamma=gamma,
            k_age=spec.k_age,
            k_year=spec.k_year,
        )
        hessian_diff = float(np.max(np.abs(diag.hessian_current - diag.hessian_corrected)))
        eig_c = ", ".join(f"{v:.4f}" for v in diag.eigenvalues_current)
        eig_k = ", ".join(f"{v:.4f}" for v in diag.eigenvalues_corrected)

        vb_diag = np.asarray(p_cell["vcov_diag"], dtype=np.float64)
        mean_vb = float(np.mean(vb_diag))
        inflation_current = float(np.mean(vb_diag + np.diag(diag.correction_current)) / mean_vb)
        inflation_corrected = float(np.mean(vb_diag + np.diag(diag.correction_corrected)) / mean_vb)
        mgcv_unc_diag = np.asarray(m_cell["vcov_unconditional_diag"], dtype=np.float64)
        mgcv_cond_diag = np.asarray(m_cell["vcov_diag"], dtype=np.float64)
        mgcv_inflation = float(np.mean(mgcv_unc_diag) / np.mean(mgcv_cond_diag))

        lines.append(
            f"| `{cell_name}` | [{eig_c}] | [{eig_k}] | {diag.n_floored_current} | "
            f"{diag.n_floored_corrected} | {hessian_diff:.6e} | {mean_vb:.6e} | "
            f"{inflation_current:.4f}x | {inflation_corrected:.4f}x | {mgcv_inflation:.4f}x |"
        )
    lines.append("")
    lines.append(
        "`inflation (current)`/`inflation (corrected)` reuse the SHIPPED `Vb` "
        "(`python_reference.json`'s own `vcov_diag`, unaffected by the score formula — "
        "it solves `(XᵀWX + S)⁻¹`, not the REML criterion) and add the correction this "
        "diagnostic's own Hessian produces — same construction as "
        "`experience_gam_penalized.smoothing_uncertainty`'s `correction` "
        "(`J V_rho Jᵀ`), reproduced rather than called. `mgcv inflation (reported)` "
        "restates the already-documented ADR-189-amendment-1 number "
        "(`mean(diag(Vc))/mean(diag(Vb))` at mgcv's own free-sp fit) for scale — it is "
        "NOT recomputed at the corrected criterion's own selection, since mgcv's number "
        "is not a function of Polaris's score formula at all."
    )
    lines.append("")

    report = "\n".join(lines) + "\n"
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
