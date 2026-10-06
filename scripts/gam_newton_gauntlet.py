#!/usr/bin/env python3
"""Outer-solver epic Slice 4 (ADR-245): the gauntlet — ONE Newton start
(``fit_polaris_gam(outer="newton")``, ``initial.spg``, no multistart, no second
start) against ``mgcv``'s own free-``sp`` REML fit on the six free-scale cells,
quasipoisson fixed scale (2 and 6), and the ``select=TRUE`` N=7 fixture,
under ADR-221's ``eta``/``edf_total`` gate.

Usage: gam_newton_gauntlet.py <probe_dir> [report.md] [--gate]

Provenance (ADR-193): every case re-runs an existing INDEPENDENT fit/compare
pair with ``outer="newton"``; the headline is derived from each comparison's own
declared claim via ``evidence_markdown`` and the word "parity" is gated by
``require_parity_evidence``. Reports and exits 0 by default; with ``--gate`` it
exits 1 if a ``REQUIRED_CASE_PREFIXES`` row (quasipoisson fixed scale, PLAN
Slice 4 case 2) fails ADR-221 — the only blocking row (ADR-246).
"""

import json
import sys
from pathlib import Path

from polaris_re.analytics.gam_newton_gauntlet_conformance import (
    GauntletReading,
    gate_failures,
    gauntlet_claims,
    payloads_from_probe_dir,
    require_gauntlet_parity_evidence,
    run_gauntlet,
)
from polaris_re.core.verification import evidence_markdown


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _per_block_lines(readings: list[GauntletReading]) -> list[str]:
    """``log10(sp)`` per block on ``select=TRUE`` (ADR-248): INDEPENDENT, declared on
    the case's own claim, reported and NOT gated (ADR-221 gates eta/edf_total)."""
    lines: list[str] = []
    for r in readings:
        if r.case.startswith("select=TRUE") and r.log10_sp_diff_per_block is not None:
            lines += [
                f"**{r.case} — log10(sp) per block, Polaris minus mgcv (reported, not "
                "gated):** "
                + ", ".join(f"b{i}: {d:+.3f}" for i, d in enumerate(r.log10_sp_diff_per_block)),
                "",
            ]
    return lines


def main(probe_dir: Path, out: Path | None, gate: bool = False) -> None:
    readings = run_gauntlet(
        payloads_from_probe_dir(lambda name: json.loads((probe_dir / name).read_text()))
    )
    require_gauntlet_parity_evidence(readings)
    all_agree = all(r.agrees for r in readings)
    lines = [
        "",
        "### Outer-solver slice 4 — the gauntlet: one Newton start vs mgcv",
        "",
        "**Claim (ADR-193):** each case's Polaris producer takes a recipe that excludes "
        'mgcv\'s eta/coef/sp/edf, runs ONE `outer="newton"` start, and is compared with '
        "mgcv's own free-sp (or fixed-scale) REML fit on eta and edf_total under ADR-221. "
        "The search under test is Newton; the per-claim producer text below names the "
        "fit_polaris_gam call.",
        "",
        *[evidence_markdown(c) + "\n" for c in gauntlet_claims(readings)],
        "**Gauntlet verdict: "
        + ("ALL CASES AGREE (ADR-221)" if all_agree else "DISAGREEMENT — see rows")
        + "**",
        "",
        "| case | max abs eta diff | edf_total diff | max abs log10(sp) diff (reported) "
        "| fits | converged | at bound | agrees (ADR-221) | error |",
        "|---|---:|---:|---:|---:|---|---|---|---|",
        *[
            f"| {r.case} | {r.max_abs_eta_diff:.3e} | {r.edf_total_diff:+.4f} "
            f"| {_fmt(r.max_abs_log10_sp_diff)} "
            f"| {r.n_function_evals} | {r.converged} | {r.at_bound} | {r.agrees} "
            f"| {r.error or ''} |"
            for r in readings
        ],
        "",
        *_per_block_lines(readings),
    ]
    report = "\n".join(lines)
    print(report)
    if out is not None:
        out.write_text(report)
    if gate:
        failures = gate_failures(readings)
        for f in failures:
            print(f"GATE FAILED: {f}")
        if failures:
            sys.exit(1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--gate"]
    main(Path(args[0]), Path(args[1]) if len(args) > 1 else None, gate="--gate" in sys.argv[1:])
