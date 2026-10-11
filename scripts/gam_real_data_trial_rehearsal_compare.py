#!/usr/bin/env python3
"""Slice R2 (ADR-259): the tier-3 SYNTHETIC rehearsal of the ILEC trial, Polaris vs ``mgcv``.

Usage: gam_real_data_trial_rehearsal_compare.py <rehearsal_probe.json> [report.md]

``mgcv`` fits the trial formula strings on synthetic cells with the real data's structure (integer
issue ages, banded-duration representatives, age = issue + duration - 1); this script fits the
SAME strings through ``gam()`` on the same columns via ``fit_polaris`` and reduces both with
``real_data_trial.compare`` — the function the maintainer's run uses. Nothing here is ILEC.

Provenance (ADR-193): ``real_data_trial.CLAIM`` (printed below by ``evidence_markdown``).
INDEPENDENT: eta, edf_total, Vp se.fit, per-smooth edf, log10(sp). Score gap: MEASUREMENT of
Polaris against its own criterion. A disagreement is a result, not an error: exits 0.
"""

import json
import sys
from pathlib import Path

import polars as pl

from polaris_re.core.verification import evidence_markdown
from polaris_re.gam import real_data_trial as trial


def build_report(probe: Path) -> str:
    payload = json.loads(probe.read_text())
    table = {f.name: f for f in trial.FORMULAS}
    rows = []
    for cell in payload["cells"]:
        spec = table[cell["formula_name"]]
        # the R probe copies the formula strings; a drift between the copies must fail loudly
        r_form = " ".join(cell["formula"].split())
        py_form = " ".join(spec.formula.split())
        if r_form != py_form or bool(cell["select"]) != spec.select:
            raise SystemExit(f"formula drift for {spec.name}: R {r_form!r} != Python {py_form!r}")
        data = pl.DataFrame({k: v for k, v in cell["data"].items()})
        data = trial.to_factor_frame(data, ["face_band", "smoker"])
        side = trial.fit_polaris(spec, data, repeats=1, profile=False)
        if side.status != "fitted":
            rows.append((cell["name"], "REFUSED", spec.role, None))
            continue
        rows.append((cell["name"], "fitted", spec.role, trial.compare(side, cell["mgcv"])))
    lines = [
        "",
        "### Slice R2 — the ILEC trial pipeline, synthetic rehearsal (tier 3, NOT ILEC data)",
        "",
        evidence_markdown(trial.CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Gates (imported, none widened): "
        f"eta < {trial.ETA_GATE:g}, |edf_total diff| < {trial.EDF_GATE:g}, Vp se rel < "
        f"{trial.SE_REL_GATE:g}, max |d eta|/se.fit <= {trial.SCALED_ETA_GATE:g} "
        f"(flag above {trial.SCALED_ETA_FLAG:g}). `score gap` = Polaris's REML at mgcv's sp minus "
        "at its own (MEASUREMENT of Polaris against its own criterion; negative = mgcv's point "
        "scores better, positive = Polaris's does).",
        "",
        "| cell | status | role | max abs d eta | max d eta/se | edf_total diff | se rel | "
        "term edf diff | log10(sp) diff | score gap | coef count (mgcv - Polaris) | gates met |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    met = 0
    for name, status, role, a in rows:
        if a is None:
            lines.append(f"| {name} | {status} | {role} | | | | | | | | | |")
            continue
        ok = a.eta_gate_met and a.edf_gate_met and a.se_gate_met and a.scaled_gate_met
        met += int(ok)
        lines.append(
            f"| {name} | {status} | {role} | {a.eta_max_abs:.2e} | {a.eta_scaled_max:.2e} | "
            f"{a.edf_total_abs:.2e} | {a.se_rel_max:.2e} | {a.term_edf_max_abs:.2e} | "
            f"{a.log10_sp_max_abs:.2e} | {a.score_gap_at_mgcv_sp:+.3f} | {a.n_coef_diff:+d} | "
            f"{'yes' if ok else 'NO'} |"
        )
    fitted = [r for r in rows if r[3] is not None]
    lines += [
        "",
        f"{met} of {len(fitted)} fitted cells meet all four gates; "
        f"{sum(r[1] == 'REFUSED' for r in rows)} refused by name "
        "(T3 itself is not in this rehearsal: `gam()` refuses it, ADR-258).",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    report = build_report(Path(argv[0]))
    if len(argv) > 1:
        Path(argv[1]).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
