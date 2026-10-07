#!/usr/bin/env python3
"""Preview epic Slice P1 (ADR-249): ``PolarisGAMFit.predict`` vs ``mgcv``'s
``predict.gam`` at held-out rows, from ``gam_predict_probe.R``'s JSON.

Usage: gam_predict_compare.py <gam_predict_probe.json> [report.md]

Provenance (ADR-193): every column is INDEPENDENT; the headline is derived from
the declared claim with ``evidence_markdown``, and the word "parity" is gated by
``require_parity_evidence``. Always exits 0 on a completed comparison — a
disagreement is a reported result, not a crash.
"""

import json
import sys
from pathlib import Path

from polaris_re.analytics.gam_predict_conformance import (
    PREDICT_CLAIM,
    PredictCaseComparison,
    compare_predict_case,
    fit_predict_case,
)
from polaris_re.core.verification import evidence_markdown, require_parity_evidence


def _f(v: float | None, spec: str = ".3e") -> str:
    return "n/a" if v is None else format(v, spec)


def main(probe: Path, out: Path | None) -> None:
    payload = json.loads(probe.read_text())
    rows: list[PredictCaseComparison] = []
    errors: list[str] = []
    for cell in payload["cells"]:
        try:
            rows.append(compare_predict_case(fit_predict_case(cell), cell))
        except Exception as exc:  # reported in the table, never swallowed
            errors.append(f"{cell['name']}: {exc!r}")
    require_parity_evidence(PREDICT_CLAIM.quantities, claim="predict.gam parity (ADR-249)")
    lines = [
        "",
        "### Preview slice P1 — predict at held-out rows vs mgcv's predict.gam",
        "",
        evidence_markdown(PREDICT_CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Gates: lpmatrix < 1e-9 "
        "(Stage A, imported); in-range eta < 2e-2 and |edf_total diff| < 1 (ADR-221, "
        "imported). Beyond-range eta, response and the training-row control are reported, "
        "not gated.",
        "",
        "| cell | lpmatrix in | lpmatrix beyond | eta in | eta beyond | response rel in | "
        "eta train (control) | edf_total diff | converged | agrees |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.name} | {r.max_abs_lpmatrix_diff_inrange:.3e} | "
            f"{r.max_abs_lpmatrix_diff_outrange:.3e} | {_f(r.max_abs_eta_diff_inrange)} | "
            f"{_f(r.max_abs_eta_diff_outrange)} | {_f(r.max_rel_response_diff_inrange)} | "
            f"{_f(r.max_abs_eta_diff_train)} | {_f(r.edf_total_diff, '+.4f')} | "
            f"{r.converged} | {r.agrees} |"
        )
    for e in errors:
        lines += ["", f"**ERROR** {e}"]
    if not all(r.agrees for r in rows) or errors:
        lines.insert(2, "**Disagreement or error — see the table. This is a result.**")
    report = "\n".join(lines) + "\n"
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    main(Path(args[0]), Path(args[1]) if len(args) > 1 else None)
