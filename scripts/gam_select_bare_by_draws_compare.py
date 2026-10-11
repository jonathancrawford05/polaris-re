#!/usr/bin/env python3
"""Slice R1 (ADR-258): ``select=TRUE`` + factor-``by`` over repeated draws, Polaris vs ``mgcv``.

Usage: gam_select_bare_by_draws_compare.py <gam_select_bare_by_draws_probe.json> [report.md]

Seven forms x two families x 30 draws (two independent sets of 15). Polaris receives the
formula-equivalent ``ModelSpec`` (built here from the form name, the shared recipe) and the
data; ``mgcv`` fits the same string.
``gam()`` REFUSES the four non-allowlisted forms (ADR-258), so this script builds the ``ModelSpec``
itself and calls ``fit_polaris_gam`` to measure what the refusal protects against.

Provenance (ADR-193):
  eta, edf_total        INDEPENDENT (gated: ADR-221)
  log10(sp)             INDEPENDENT (reported, never gated)
  score gap             MEASUREMENT of Polaris against its OWN criterion: the REML score
                        evaluated at ``mgcv``'s sp minus at Polaris's sp. ``mgcv``'s sp enters
                        only as the evaluation point of Polaris's criterion; nothing is fitted
                        from it. Negative = ``mgcv``'s point scores better under Polaris's
                        criterion (mechanism class iii, ADR-241).
Always exits 0 on a completed comparison.
"""

import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

from polaris_re.analytics.gam_model import fit_polaris_gam, resolve_family
from polaris_re.analytics.gam_reml_optimize import penalized_fit_and_score
from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec, factor_by_terms
from polaris_re.core.verification import (
    ComparedQuantity,
    ComparisonProvenance,
    VerificationClaim,
    evidence_markdown,
)
from polaris_re.gam import api as gam_api

_ETA_GATE = 2e-2
_EDF_GATE = 1.0
CLAIM = VerificationClaim(
    claim=(
        "Polaris (fit_polaris_gam on the ModelSpec of the formula form, Newton REML) fits "
        "select=TRUE with a factor-by smooth on each draw; mgcv fits "
        "gam(<same string>, method='REML', select=TRUE) on the same data; compared on eta, "
        "edf_total and log10(sp), per form, over 30 draws per family."
    ),
    quantities=(
        ComparedQuantity(
            quantity="eta at the training rows (gated, ADR-221)",
            left_producer="fit_polaris_gam(ModelSpec, data).eta",
            right_producer="mgcv m$linear.predictors from gam(as.formula(formula), select=TRUE)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="edf_total (gated, ADR-221)",
            left_producer="PolarisGAMFit.edf_total",
            right_producer="mgcv sum(m$edf)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
        ComparedQuantity(
            quantity="log10(sp) per penalty (reported, never gated)",
            left_producer="PolarisGAMFit.log_lambda from the Newton search",
            right_producer="mgcv log10(m$sp)",
            provenance=ComparisonProvenance.INDEPENDENT,
        ),
    ),
)


def _spec(form: str, levels: int, family: str, link: str, g_levels: int = 2) -> ModelSpec:
    terms: list[TermSpec] = []
    if form.startswith("main"):
        terms.append(TermSpec(label="f", variables=("f",), basis="parametric", levels=(levels,)))
        if "two_by" in form:
            terms.append(
                TermSpec(label="g", variables=("g",), basis="parametric", levels=(g_levels,))
            )
    if "bare" in form:
        terms.append(TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,)))
    terms.extend(
        factor_by_terms(base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=levels)
    )
    if "two_by" in form:
        terms.extend(
            factor_by_terms(
                base_label="s(x):g", variable="x", k=8, by_factor="g", n_levels=g_levels
            )
        )
    if form.endswith("_ti"):
        terms.append(TermSpec(label="ti(x,z)", variables=("x", "z"), basis="ti", k=(5, 5)))
    return ModelSpec(family=family, link=link, terms=tuple(terms), select=True)


def _fit(cell: dict) -> tuple[object, np.ndarray]:  # type: ignore[type-arg]
    df = pl.DataFrame({k: v for k, v in cell["data"].items()})
    coding = gam_api._factor_coding(df, "f")
    fam, link = gam_api._family(cell["family"])
    g_coding = gam_api._factor_coding(df, "g")
    spec = _spec(cell["form"], len(coding.levels), fam, link, len(g_coding.levels))
    arrays = {
        "x": df["x"].to_numpy().astype(np.float64),
        "f": coding.encode(df["f"], "f"),
        "g": g_coding.encode(df["g"], "g"),
        "z": df["z"].to_numpy().astype(np.float64),
    }
    y = df["y"].to_numpy().astype(np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fit_polaris_gam(spec, arrays, y), y


def _bucket(form: str) -> str:
    """``core`` = the two allowlisted forms; ``ti`` = ``ti(x,z)`` beside the by smooth (ADR-258
    re-review P2; refused after one recorded miss); anything else is also refused."""
    if form in ("by_only", "main_by"):
        return "core"
    return "ti" if form.endswith("_ti") else "refused"


def _asarray(v: float | list[float]) -> np.ndarray:
    return np.atleast_1d(np.asarray(v, dtype=np.float64))


def build_report(probe: Path) -> tuple[str, int, int]:
    """``(markdown, accepted-form fits that agree, accepted-form fits)``: the refused forms'
    disagreement is the recorded limitation, reported in the table and not counted as a miss."""
    payload = json.loads(probe.read_text())
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)  # type: ignore[type-arg]
    for cell in payload["cells"]:
        fit, y = _fit(cell)
        mg = cell["mgcv"]
        eta_diff = float(np.max(np.abs(fit.eta - _asarray(mg["eta"]))))  # type: ignore[attr-defined]
        edf_diff = float(fit.edf_total - mg["edf_total"])  # type: ignore[attr-defined]
        sp_mg = np.log10(_asarray(mg["sp"]))
        sp_diff = (
            float(np.max(np.abs(fit.log_lambda - sp_mg)))  # type: ignore[attr-defined]
            if fit.log_lambda.size == sp_mg.size  # type: ignore[attr-defined]
            else None
        )
        gap = None
        if fit.log_lambda.size == sp_mg.size:  # type: ignore[attr-defined]
            fam = resolve_family(fit.model.family, fit.model.link)  # type: ignore[attr-defined]
            _, s_mg = penalized_fit_and_score(
                y,
                fit.design["x"],  # type: ignore[attr-defined]
                fam,
                fit.design["penalty_blocks"],  # type: ignore[attr-defined]
                sp_mg,
            )
            gap = float(s_mg - fit.reml_score)  # type: ignore[attr-defined]
        groups[(cell["family"], cell["form"])].append(
            {
                "eta": eta_diff,
                "edf": edf_diff,
                "sp": sp_diff,
                "conv": bool(fit.converged),  # type: ignore[attr-defined]
                "gap": gap,
                "agrees": eta_diff < _ETA_GATE and abs(edf_diff) < _EDF_GATE,
                "draw": int(cell["name"].split("_draw")[1].split("_")[0]),
            }
        )
    lines = [
        "",
        "### Slice R1 — select=TRUE + factor-by over repeated draws",
        "",
        evidence_markdown(CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Gates: eta < 2e-2, "
        "|edf_total diff| < 1 (ADR-221, imported). `score gap` = Polaris's own REML score at "
        "mgcv's sp minus at Polaris's sp (MEASUREMENT of Polaris against its own criterion; "
        "negative = mgcv's point scores better).",
        "",
        "| family | form | gam() accepts | draws | agree | not converged | max eta diff | "
        "median eta diff | max edf diff | most negative score gap |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (fam, form), rows in sorted(groups.items()):
        etas = sorted(r["eta"] for r in rows)
        gaps = [r["gap"] for r in rows if r["gap"] is not None]
        accepted = _bucket(form) == "core"
        lines.append(
            f"| {fam} | {form} | {'yes' if accepted else 'REFUSED (ADR-258)'} | {len(rows)} | "
            f"{sum(r['agrees'] for r in rows)} | {sum(not r['conv'] for r in rows)} | "
            f"{etas[-1]:.3e} | {etas[len(etas) // 2]:.3e} | "
            f"{max(abs(r['edf']) for r in rows):.3e} | "
            f"{(min(gaps) if gaps else float('nan')):+.3f} |"
        )
    tot = {"core": [0, 0], "ti": [0, 0], "refused": [0, 0]}
    for (_, form), rows in groups.items():
        k = _bucket(form)
        tot[k][0] += sum(r["agrees"] for r in rows)
        tot[k][1] += len(rows)
    lines += [
        "",
        f"Accepted forms (`by_only`, `main_by`): {tot['core'][0]} of {tot['core'][1]} fits agree. "
        f"Refused forms (a bare or second smooth of the covariate beside the factor-by "
        f"smooth): {tot['refused'][0]} of {tot['refused'][1]} fits agree. "
        f"`ti(x,z)` beside the by smooth (`main_by_ti`): {tot['ti'][0]} of {tot['ti'][1]} fits "
        "agree.",
        "",
        "Misses by form (draw number, max eta diff; draws 1-15 are the first set, 16-30 the "
        "second): "
        + "; ".join(
            f"{fam}/{form}: "
            + (
                ", ".join(f"{r['draw']} ({r['eta']:.2e})" for r in rows if not r["agrees"])
                or "none"
            )
            for (fam, form), rows in sorted(groups.items())
        ),
    ]
    return "\n".join(lines) + "\n", tot["core"][0], tot["core"][1]


def main(probe: Path, out: Path | None) -> None:
    report, _, _ = build_report(probe)
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(Path(args[0]), Path(args[1]) if len(args) > 1 else None)
