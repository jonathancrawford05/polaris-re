#!/usr/bin/env python3
"""Ladder slice 3e (ADR-240): default vs initial.spg-seeded start on every
existing free-scale conformance cell, against mgcv's own free-sp fit.

Usage: gam_initial_sp_default_study.py <probe_dir> [report.md]

Reads the committed-recipe probe JSONs from <probe_dir>. Diagnostic: reports,
gates nothing. The headline is derived from the declared claim (ADR-193).
"""

import json
import sys
from pathlib import Path

from polaris_re.analytics.gam_initial_sp_default_conformance import (
    CELLS,
    DEFAULT_START_STUDY_CLAIM,
    best_of_two,
    cr_re_ti_payload,
    dispersion_draw_payload,
    measure_start,
)
from polaris_re.core.verification import evidence_markdown


def main(probe_dir: Path, out: Path | None) -> None:
    def load(name: str) -> dict:
        return json.loads((probe_dir / name).read_text())

    payloads = {
        "gaussian L1 (cr+by+ti)": load("gam_gaussian_free_sp_probe.json"),
        "gaussian factor-by L3": load("gam_by_factor_free_sp_probe.json"),
        "gaussian parametric L4": load("gam_parametric_free_sp_probe.json"),
        "gaussian cr+re+ti L6": cr_re_ti_payload(load("gam_cr_re_ti_probe.json"), "gaussian_free"),
        "quasipoisson 3b draw": load("gam_quasipoisson_free_sp_probe.json"),
        "quasipoisson 3c draw": dispersion_draw_payload(
            load("gam_dispersion_two_stage_probe.json")
        ),
    }
    rows = []
    for cell, (fit, compare) in CELLS.items():
        readings = []
        for seeded in (False, True):
            try:
                readings.append(
                    measure_start(cell, payloads[cell], fit, compare, initial_sp_start=seeded)
                )
            except Exception as exc:  # reported, never swallowed: the row says so
                rows.append(
                    f"| {cell} | {'seeded' if seeded else 'centre'} | ERROR: {exc!r} | | | | | |"
                )
        if len(readings) == 2:
            readings.append(best_of_two(*readings))
        for r in readings:
            rows.append(
                f"| {r.cell} | {r.start} | {r.max_abs_eta_diff:.3e} | "
                f"{r.edf_total_diff:+.4f} | {r.max_abs_log10_sp_diff:.4f} | "
                f"{r.own_reml_score:.4f} | {r.at_bound} | {r.agrees} |"
            )
    report = "\n".join(
        [
            "",
            "### Ladder slice 3e — default vs initial.spg-seeded start, every free-scale cell",
            "",
            evidence_markdown(DEFAULT_START_STUDY_CLAIM),
            "",
            "| cell | start | max abs eta diff | edf_total diff | max abs log10(sp) diff "
            "| own REML score | at bound | agrees (ADR-221) |",
            "|---|---|---:|---:|---:|---:|---|---|",
            *rows,
            "",
        ]
    )
    print(report)
    if out is not None:
        out.write_text(report)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
