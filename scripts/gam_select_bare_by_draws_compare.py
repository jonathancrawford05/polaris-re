#!/usr/bin/env python3
"""Slice R1 (ADR-258): ``select=TRUE`` + factor-``by`` over repeated draws, Polaris vs ``mgcv``.

Usage: gam_select_bare_by_draws_compare.py <gam_select_bare_by_draws_probe.json> [report.md]

Four forms x two families x 15 draws. Polaris receives the formula-equivalent ``ModelSpec``
(built here from the form name, the shared recipe) and the data; ``mgcv`` fits the same string.
``gam()`` REFUSES the two bare-smooth forms (ADR-258), so this script builds the ``ModelSpec``
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
        "edf_total and log10(sp), per form, over 15 draws per family."
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


def _spec(form: str, levels: int, family: str, link: str) -> ModelSpec:
    terms: list[TermSpec] = []
    if form.startswith("main"):
        terms.append(TermSpec(label="f", variables=("f",), basis="parametric", levels=(levels,)))
    if "bare" in form:
        terms.append(TermSpec(label="s(x)", variables=("x",), basis="cr", k=(8,)))
    terms.extend(
        factor_by_terms(base_label="s(x):f", variable="x", k=8, by_factor="f", n_levels=levels)
    )
    return ModelSpec(family=family, link=link, terms=tuple(terms), select=True)


def _fit(cell: dict) -> tuple[object, np.ndarray]:  # type: ignore[type-arg]
    df = pl.DataFrame({k: v for k, v in cell["data"].items()})
    coding = gam_api._factor_coding(df, "f")
    fam, link = gam_api._family(cell["family"])
    spec = _spec(cell["form"], len(coding.levels), fam, link)
    arrays = {"x": df["x"].to_numpy().astype(np.float64), "f": coding.encode(df["f"], "f")}
    y = df["y"].to_numpy().astype(np.float64)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fit_polaris_gam(spec, arrays, y), y


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
        accepted = "bare" not in form
        lines.append(
            f"| {fam} | {form} | {'yes' if accepted else 'REFUSED (ADR-258)'} | {len(rows)} | "
            f"{sum(r['agrees'] for r in rows)} | {sum(not r['conv'] for r in rows)} | "
            f"{etas[-1]:.3e} | {etas[len(etas) // 2]:.3e} | "
            f"{max(abs(r['edf']) for r in rows):.3e} | "
            f"{(min(gaps) if gaps else float('nan')):+.3f} |"
        )
    tot = {True: [0, 0], False: [0, 0]}
    for (_, form), rows in groups.items():
        k = "bare" not in form
        tot[k][0] += sum(r["agrees"] for r in rows)
        tot[k][1] += len(rows)
    lines += [
        "",
        f"Accepted forms (no bare smooth): {tot[True][0]} of {tot[True][1]} fits agree. "
        f"Refused forms (bare smooth beside the by-smooth): {tot[False][0]} of {tot[False][1]} "
        "fits agree.",
    ]
    return "\n".join(lines) + "\n", tot[True][0], tot[True][1]


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
