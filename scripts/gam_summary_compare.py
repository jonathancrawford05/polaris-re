#!/usr/bin/env python3
"""Preview epic Slice P4 (ADR-253): ``GamFit.summary()`` vs ``summary.gam(m)`` and the
target-size fit, from ``gam_formula_probe.R`` and ``gam_target_size_probe.R`` JSON.

Usage: gam_summary_compare.py <gam_formula_probe.json> [<gam_target_size_probe.json>] [report.md]

Provenance (ADR-193): six columns INDEPENDENT, ``n`` ECHO; the headline is derived from the
declared claim with ``evidence_markdown``. The Newton convergence columns are a MEASUREMENT
of Polaris against its own ``epsilon_rel``, not parity. Always exits 0 on a completed run.
"""

import json
import sys
from pathlib import Path

from polaris_re.core.verification import evidence_markdown
from polaris_re.gam.summary_conformance import (
    SUMMARY_CLAIM,
    SummaryCaseComparison,
    compare_summary_case,
    fit_summary_case,
)


def _f(v: float | None, spec: str = ".3e") -> str:
    return "n/a" if v is None else format(v, spec)


def build_report(probes: list[Path]) -> tuple[str, int, int]:
    """``(markdown, cells that agree, cells compared)``: no I/O beyond reading the probe
    JSON; also used by ``scripts/gam_parity_report.py``."""
    rows: list[SummaryCaseComparison] = []
    errors: list[str] = []
    meta: list[str] = []
    mgcv_seconds: dict[str, float] = {}
    for probe in probes:
        payload = json.loads(probe.read_text())
        meta.append(f"{probe.name}: mgcv {payload['mgcv_version']} / {payload['r_version']}")
        for cell in payload["cells"]:
            if "summary" not in cell:
                continue
            if "mgcv_fit_seconds" in cell:
                mgcv_seconds[cell["name"]] = cell["mgcv_fit_seconds"]
            try:
                rows.append(compare_summary_case(fit_summary_case(cell), cell))
            except Exception as exc:  # reported in the table, never swallowed
                errors.append(f"{cell['name']}: {exc!r}")
    lines = [
        "",
        "### Preview slice P4 — GamFit.summary() vs summary.gam(m)",
        "",
        evidence_markdown(SUMMARY_CLAIM),
        "",
        "; ".join(meta) + ". Gates: derived from ADR-221's eta/edf slack at Polaris's own fit "
        "(ADR-253); `n` exact; REML score, deviance components and log10(sp) reported, not gated.",
        "",
        "| cell | n | dev.expl diff (gate) | scale rel diff (gate) | per-term edf | "
        "REML diff | deviance rel | null dev rel | log10(sp) | agrees |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        if r.refused:
            lines.append(f"| {r.name} | — | — | — | — | — | — | — | — | refused ({r.agrees}) |")
            continue
        lines.append(
            f"| {r.name} | {r.n_match} | {_f(r.dev_expl_diff)} ({_f(r.dev_expl_gate)}) | "
            f"{_f(r.scale_rel_diff)} ({_f(r.scale_gate)}) | {_f(r.max_term_edf_diff)} | "
            f"{_f(r.reml_diff, '+.3e')} | {_f(r.deviance_rel_diff)} | "
            f"{_f(r.null_deviance_rel_diff)} | {_f(r.max_abs_log10_sp_diff)} | {r.agrees} |"
        )
    lines += [
        "",
        "**Newton convergence and cost (MEASUREMENT of Polaris against its own epsilon_rel = "
        "1e-6, not parity):**",
        "",
        "| cell | penalties | iterations | fits | rel. gradient / epsilon_rel | converged | "
        "Polaris s | mgcv s |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in rows:
        if r.refused:
            continue
        lines.append(
            f"| {r.name} | {r.n_penalties} | {r.n_iterations} | {r.n_function_evals} | "
            f"{_f(r.rel_gradient_over_epsilon, '.3g')} | {r.converged} | {r.seconds:.1f} | "
            f"{_f(mgcv_seconds.get(r.name), '.2f')} |"
        )
    for e in errors:
        lines += ["", f"**ERROR** {e}"]
    if not all(r.agrees for r in rows) or errors:
        lines.insert(2, "**Disagreement or error — see the table. This is a result.**")
    n_agree = sum(1 for r in rows if r.agrees)
    return "\n".join(lines) + "\n", n_agree, len(rows) + len(errors)


def main(probes: list[Path], out: Path | None) -> None:
    report, _, _ = build_report(probes)
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    paths = [Path(a) for a in args]
    report = paths.pop() if paths and paths[-1].suffix == ".md" else None
    main(paths, report)
