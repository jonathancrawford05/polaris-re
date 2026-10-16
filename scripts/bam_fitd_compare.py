#!/usr/bin/env python3
"""Slice R3 Stage B (ADR-260 amendments 2-4): Polaris's ``bgam.fitd`` port vs
``bam(method="fREML", discrete=TRUE)``, from ``bam_fitd_probe.R``'s JSON.

Usage: bam_fitd_compare.py <bam_fitd_probe.json> [report.md]

Two tables, each headed by ``evidence_markdown`` of its declared claim:
the END-TO-END table (Polaris builds its own design; every column INDEPENDENT) and the
DESIGN-CONDITIONED table (Polaris is handed ``bam``'s own X and S: ECHO, a harness-type
diagnostic that isolates the algorithm from the design). Exits 0 on a completed comparison
(CI annotates; it does not gate here); the gate verdict is printed per cell.
"""

import json
import sys
from pathlib import Path

from polaris_re.core.verification import evidence_markdown, require_parity_evidence
from polaris_re.gam.bam_fitd_conformance import (
    END_TO_END_CLAIM,
    ISOLATION_CLAIM,
    SEED_CLAIM,
    DesignConditionedComparison,
    EndToEndComparison,
    compare_design_conditioned,
    compare_end_to_end,
    compare_seed_sensitivity,
)
from polaris_re.gam.real_data_trial import (
    ETA_GATE,
    SCALED_ETA_FLAG,
    SCALED_ETA_GATE,
    SE_REL_GATE,
)


def build_report(probe: Path) -> tuple[str, list[EndToEndComparison]]:
    payload = json.loads(probe.read_text())
    cells = payload["cells"]
    e2e: list[EndToEndComparison] = [compare_end_to_end(c) for c in cells]
    iso: list[DesignConditionedComparison] = [
        compare_design_conditioned(c) for c in cells if c.get("X_unique") and c.get("pen")
    ]
    parity_cols = tuple(q for q in END_TO_END_CLAIM.quantities if q.provenance.is_parity_evidence)
    require_parity_evidence(parity_cols, claim="bam_fitd end-to-end vs bam(discrete=TRUE) (R3-B)")
    lines = [
        "",
        "### R3 Stage B: Polaris `bam` (performance iteration) vs `bam(discrete=TRUE)` — end to end",
        "",
        evidence_markdown(END_TO_END_CLAIM),
        "",
        f"mgcv {payload['mgcv_version']} / {payload['r_version']}. Gates (ADR-260 decision 2, "
        f"unchanged): max|eta diff| < {ETA_GATE:g}; |edf_total diff| < 1; max relative Vp se diff < "
        f"{SE_REL_GATE:g}; max|eta diff|/se <= {SCALED_ETA_GATE:g} (flag above {SCALED_ETA_FLAG:g}). "
        "`gam vs bam` is the exact-REML baseline (mgcv against mgcv, REFERENCE_INTERNAL); a cell "
        "discriminates only if it is well above Polaris's own eta diff.",
        "",
        "| cell | rows | iterations Polaris / mgcv | max abs eta | max eta/se | abs edf_total | "
        "max rel se | log(sp) (not gated) | gam vs bam (eta) | gates |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in e2e:
        lines.append(
            f"| {r.name} | {r.n} | {r.iter_polaris} / {r.iter_mgcv} | {r.eta_max_abs:.2e} | "
            f"{r.eta_scaled_max:.2e}{' (FLAG)' if r.scaled_flag else ''} | {r.edf_total_abs:.2e} | "
            f"{r.se_rel_max:.2e} | {r.log_sp_max_abs:.2e} | {r.gam_vs_bam_eta:.2e} | "
            f"{'ALL MET' if r.gates_met else 'NOT MET'} |"
        )
    lines += [
        "",
        "### R3 Stage B: the algorithm on `bam`'s own design (diagnostic)",
        "",
        evidence_markdown(ISOLATION_CLAIM),
        "",
        "Per-iteration max abs differences (iteration 1 first). A difference that grows by about "
        "a decade per iteration from ~1e-15 is round-off amplified along flat `log(sp)` "
        "directions, which is why `log(sp)` is never gated.",
        "",
        "| cell | iterations Polaris / mgcv | final max abs eta | abs edf_total | "
        "log(sp) per iteration | eta per iteration |",
        "|---|---|---:|---:|---|---|",
    ]
    for d in iso:
        lines.append(
            f"| {d.name} | {d.iter_polaris} / {d.iter_mgcv} | {d.eta_max_abs:.2e} | "
            f"{d.edf_total_abs:.2e} | {' '.join(f'{v:.0e}' for v in d.log_sp_diff_by_iteration)} | "
            f"{' '.join(f'{v:.0e}' for v in d.eta_diff_by_iteration)} |"
        )
    seeds = [r for c in cells if (r := compare_seed_sensitivity(c)) is not None]
    lines += [
        "",
        "### R3 Stage B: `bam`'s own seed noise floor (`discrete.mf` seed patched)",
        "",
        evidence_markdown(SEED_CLAIM),
        "",
        "Seeds: mgcv's own 8547 and six others. `spread` is the max over rows of (max - min) of "
        "`bam`'s eta across the seven fits; the Polaris columns are distances from Polaris's "
        "single deterministic fit to `bam` at the default seed and to the minimum / maximum over "
        "the six patched seeds.",
        "",
        "| cell | seeds | bam eta spread | max dev from default seed | edf_total spread | "
        "Polaris vs seed 8547 | Polaris vs other seeds (min .. max) | iterations by seed |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for q in seeds:
        lines.append(
            f"| {q.name} | {q.n_seeds} | {q.spread:.2e} | {q.max_dev_from_default_seed:.2e} | "
            f"{q.edf_total_spread:.2e} | {q.polaris_vs_default_seed:.2e} | "
            f"{q.polaris_vs_seed_min:.2e} .. {q.polaris_vs_seed_max:.2e} | "
            f"{' '.join(str(i) for i in q.iter_by_seed)} |"
        )
    return "\n".join(lines) + "\n", e2e


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    md, _ = build_report(Path(argv[1]))
    if len(argv) > 2:
        Path(argv[2]).write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
