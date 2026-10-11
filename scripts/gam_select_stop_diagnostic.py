#!/usr/bin/env python3
# ruff: noqa: E501  (diagnostic table strings)
"""DIAGNOSTIC (ADR-258 follow-up): is Polaris's Newton stop the reason it misses ``mgcv`` on the
``select=TRUE`` factor-``by`` draws, and would a warning at the stop have caught the misses?

Usage: gam_select_stop_diagnostic.py <gam_select_bare_by_draws_probe.json> [report.md]

Two questions, each a MEASUREMENT of Polaris against ``mgcv`` on the shared draws (eta is the
INDEPENDENT column; nothing here changes what ``gam()`` ships):

1. WARNING. For every fit, the indicators available at the stop (projected gradient over its
   tolerance, penalties near the upper bound, function evaluations) against "this fit missed
   ``mgcv``" (eta >= 2e-2 or |edf diff| >= 1). Reported as sensitivity / false-alarm rate.
2. TOLERANCE. Re-run the same Newton search from the same start with a tighter ``conv_tol``
   (1e-7, 1e-8, 1e-9) and report how many misses reach ``mgcv``'s eta and how many agreeing
   fits stop agreeing. ``conv_tol`` is ``mgcv``'s own default (1e-6) in the shipped search;
   a tighter value here is an experiment, not a recommendation.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from polaris_re.analytics.gam_initial_sp import initial_log10_lambda
from polaris_re.analytics.gam_model import PRODUCTION_LOG10_BOUNDS, resolve_family
from polaris_re.analytics.gam_reml_newton import newton_select_lambdas
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "draws_cmp", _HERE / "gam_select_bare_by_draws_compare.py"
)
assert _spec is not None and _spec.loader is not None
cmp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmp)

ETA_GATE, EDF_GATE = 2e-2, 1.0
TOLS = (1e-7, 1e-8, 1e-9)


def _arr(v: float | list[float]) -> np.ndarray:
    return np.atleast_1d(np.asarray(v, dtype=np.float64))


def _auc(score: np.ndarray, miss: np.ndarray) -> float:
    pos, neg = score[miss], score[~miss]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def main(probe: Path, out: Path | None) -> None:
    payload = json.loads(probe.read_text())
    rows = []
    for cell in payload["cells"]:
        fit, y = cmp._fit(cell)
        mg = cell["mgcv"]
        eta_ref = _arr(mg["eta"])
        miss = bool(
            np.max(np.abs(fit.eta - eta_ref)) >= ETA_GATE
            or abs(fit.edf_total - mg["edf_total"]) >= EDF_GATE
        )
        tol0 = 1e-6 * (1.0 + abs(fit.reml_score))
        ratio = (fit.max_abs_projected_gradient or 0.0) / tol0
        rec = {
            "name": cell["name"],
            "form": cell["form"],
            "family": cell["family"],
            "miss": miss,
            "ratio": ratio,
            "n_evals": int(fit.n_function_evals),
            "n_high": int(np.sum(fit.log_lambda > 4.0)),
            "max_log": float(np.max(fit.log_lambda)),
        }
        fam = resolve_family(fit.model.family, fit.model.link)
        x = fit.design["x"]
        blocks = fit.design["penalty_blocks"]
        lo, hi = PRODUCTION_LOG10_BOUNDS
        x0 = np.clip(initial_log10_lambda(y, x, fam, blocks, weights=None), lo, hi)
        for tol in TOLS:
            sel = newton_select_lambdas(y, x, fam, blocks, x0=x0, bounds=(lo, hi), conv_tol=tol)
            eta = x @ sel.coef
            rec[f"agree_{tol:g}"] = bool(
                np.max(np.abs(eta - eta_ref)) < ETA_GATE
                and abs(sel.edf_total - mg["edf_total"]) < EDF_GATE
            )
            rec[f"score_{tol:g}"] = float(sel.reml_score)
        rec["score_1e-06"] = float(fit.reml_score)
        sp_mg = np.log10(_arr(mg["sp"]))
        rec["score_mgcv"] = (
            float(penalized_fit_and_score(y, x, fam, blocks, sp_mg)[1])
            if sp_mg.size == fit.log_lambda.size
            else float("nan")
        )
        rows.append(rec)

    miss = np.array([r["miss"] for r in rows])
    lines = ["", "### Diagnostic — Polaris's Newton stop on the select=TRUE factor-by draws", ""]
    lines.append(
        "MEASUREMENT of Polaris against `mgcv` (eta INDEPENDENT) and against its own search; "
        "nothing here is shipped. A miss = eta >= 2e-2 or |edf diff| >= 1."
    )
    lines += ["", f"{int(miss.sum())} misses in {len(rows)} fits.", ""]
    lines += ["#### 1. Would a warning at the stop have caught the misses?", ""]
    lines += [
        "| indicator | AUC (miss vs agree) | best threshold | catches | false alarms |",
        "|---|---:|---|---:|---:|",
    ]
    for key, label in (
        ("ratio", "projected gradient / tolerance at the stop"),
        ("n_evals", "function evaluations"),
        ("n_high", "penalties with log10(lambda) > 4"),
        ("max_log", "max log10(lambda)"),
    ):
        v = np.array([r[key] for r in rows], dtype=float)
        best = None
        for thr in np.unique(v):
            flag = v >= thr
            catch = int((flag & miss).sum())
            fa = int((flag & ~miss).sum())
            # prefer catching >= half the misses with the fewest false alarms
            if catch >= max(1, miss.sum() // 2) and (best is None or fa < best[2]):
                best = (thr, catch, fa)
        bt = f">= {best[0]:.3g}" if best else "n/a"
        lines.append(
            f"| {label} | {_auc(v, miss):.3f} | {bt} | "
            f"{best[1] if best else 0} of {int(miss.sum())} | {best[2] if best else 0} of {int((~miss).sum())} |"
        )
    lines += ["", "#### 2. Does a tighter conv_tol reach mgcv's eta?", ""]
    lines += [
        "| conv_tol | misses now agreeing | agreeing fits that stop agreeing | misses still scoring >0.01 above mgcv's point under Polaris's criterion |",
        "|---:|---:|---:|---:|",
    ]
    for tol in TOLS:
        k = f"agree_{tol:g}"
        fixed = sum(1 for r in rows if r["miss"] and r[k])
        broke = sum(1 for r in rows if not r["miss"] and not r[k])
        above = sum(1 for r in rows if r["miss"] and r[f"score_{tol:g}"] - r["score_mgcv"] > 0.01)
        lines.append(
            f"| {tol:g} | {fixed} of {int(miss.sum())} | {broke} of {int((~miss).sum())} | {above} |"
        )
    at_default = sum(1 for r in rows if r["miss"] and r["score_1e-06"] - r["score_mgcv"] > 0.01)
    lines += [
        "",
        f"At the shipped 1e-6: {at_default} of {int(miss.sum())} misses score >0.01 above mgcv's point.",
    ]
    lines += [
        "",
        "Misses by form: "
        + "; ".join(
            f"{f}: {sum(1 for r in rows if r['form'] == f and r['miss'])}/{sum(1 for r in rows if r['form'] == f)}"
            for f in sorted({r["form"] for r in rows})
        ),
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    if out is not None:
        out.write_text(text)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(Path(args[0]), Path(args[1]) if len(args) > 1 else None)
