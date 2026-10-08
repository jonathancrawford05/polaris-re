#!/usr/bin/env python3
"""Preview epic Slice P3 (ADR-251): ``polaris_re.gam.gam(<formula string>)`` vs
``mgcv::gam(<the same string>)``, from ``gam_formula_probe.R``'s JSON.

Usage: gam_formula_compare.py <gam_formula_probe.json> [report.md]

Provenance (ADR-193): every column is INDEPENDENT; the headline is derived from the
declared claim with ``evidence_markdown`` and "parity" is gated by
``require_parity_evidence``. Always exits 0 on a completed comparison.
"""

import json
import sys
from pathlib import Path

from polaris_re.core.verification import evidence_markdown, require_parity_evidence
from polaris_re.gam import api as gam_api
from polaris_re.gam.formula_conformance import (
    FORMULA_CLAIM,
    FormulaCaseComparison,
    compare_formula_case,
    fit_formula_case,
)


def _f(v: float | None, spec: str = ".3e") -> str:
    return "n/a" if v is None else format(v, spec)


def main(probe: Path, out: Path | None) -> None:
    payload = json.loads(probe.read_text())
    rows: list[FormulaCaseComparison] = []
    errors: list[str] = []
    for cell in payload["cells"]:
        try:
            rows.append(compare_formula_case(fit_formula_case(cell), cell))
        except Exception as exc:  # reported in the table, never swallowed
            errors.append(f"{cell['name']}: {exc!r}")
    require_parity_evidence(FORMULA_CLAIM.quantities, claim="formula front end vs mgcv (ADR-251)")
    probe_in = payload["sort_probe_input"]
    ref_sorted = [str(s) for s in payload["sort_probe"]]
    match = "MATCH" if list(gam_api.r_factor_levels(probe_in)) == ref_sorted else "MISMATCH"
    held_ref = [str(s) for s in payload["sort_heldout"]]
    try:
        held = (
            "MATCH"
            if list(gam_api.r_factor_levels(payload["sort_heldout_input"])) == held_ref
            else "MISMATCH"
        )
    except Exception as exc:  # a refused character is a reported result
        held = f"REFUSED ({exc})"
    mine = {c: list(gam_api.r_factor_levels(probe_in, c)) for c in ("C", "en_US")}
    lines = [
        "",
        "### Preview slice P3 — gam(<formula string>) vs mgcv::gam(<same string>)",
        "",
        evidence_markdown(FORMULA_CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Gates: eta < 2e-2 and "
        "|edf_total diff| < 1 (ADR-221, imported); structure and level order exact. "
        "Per-smooth edf and log10(sp) are reported, not gated.",
        "",
        f"Oracle LC_COLLATE: `{payload['collate']}`. R sorts `{payload['sort_probe_input']}` as "
        f"`{payload['sort_probe']}`; `r_factor_levels` gives C: `{mine['C']}`, "
        f"en_US: `{mine['en_US']}`; pinned `ORACLE_COLLATION = {gam_api.ORACLE_COLLATION}` "
        f"-> {match}.",
        "",
        f"HELD-OUT sort set (disjoint from the calibration sample): R sorts "
        f"`{payload['sort_heldout_input']}` as `{payload['sort_heldout']}`; `r_factor_levels` "
        f"gives `{list(gam_api.r_factor_levels(payload['sort_heldout_input']))}` -> {held}.",
        "",
        "| cell | eta | edf_total diff | per-smooth edf | log10(sp) | labels | bs.dim | "
        "ncoef | nsdf | levels | converged | agrees |",
        "|---|---:|---:|---:|---:|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r.refused:
            tag = "expected refusal" if r.expected_refusal else "UNEXPECTED REFUSAL"
            lines.append(
                f"| {r.name} | — | — | — | — | — | — | — | — | — | — | {tag}: {r.agrees} |"
            )
            continue
        lines.append(
            f"| {r.name} | {_f(r.max_abs_eta_diff)} | {_f(r.edf_total_diff, '+.4f')} | "
            f"{_f(r.max_abs_edf_by_smooth_diff)} | {_f(r.max_abs_log10_sp_diff)} | "
            f"{r.labels_match} | {r.bs_dim_match} | {r.ncoef_match} | {r.nsdf_match} | "
            f"{r.levels_match} | {r.converged} | {r.agrees} |"
        )
    for r in rows:
        if r.refusal:
            lines += ["", f"`{r.name}` refused: {r.refusal}"]
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
