#!/usr/bin/env python3
"""Preview epic Slice P5 (ADR-254): the GAM parity report, GENERATED.

Usage:
  gam_parity_report.py <probe_dir> <out.md> --run-id ID --commit SHA --digest sha256:...
  gam_parity_report.py <probe_dir> <out.md> --local        # tier 1 scratch, not committable

``<probe_dir>`` holds the oracle's probe JSONs (the CI ``compare`` job's working directory).
The report re-runs the preview's INDEPENDENT comparisons — predict and ``se.fit`` (P1/P2),
the formula front end (P3), ``summary()`` and the target-size fit (P4), the guide's worked
example (P5) and the one-start Newton gauntlet — and concatenates their machine-generated
tables. Every headline is ``evidence_markdown(<declared claim>)``; no headline, count or
verdict below is typed by hand. Tolerances are imported from the modules that derived them.

Provenance (ADR-193): this script compares nothing itself except the guide example's
prediction columns (GUIDE_CLAIM, INDEPENDENT). Every other number is a verbatim table from
a comparison module that declares its own producers. The report as a whole is an
AGGREGATION; "N of M cells agree" is a count of those comparisons' own ``agrees`` flags.

The pinned run id, commit and oracle digest are mandatory outside ``--local`` mode: a
number with no tier and no digest is not a gap statement (ROUTINE_MGCV_PARITY, step 5).
A section whose probe is missing is reported NOT MEASURED, and the verdict becomes
INCOMPLETE — silence is never success.
"""

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from polaris_re.analytics.gam_predict_conformance import _SE_REL_TOLERANCE
from polaris_re.analytics.gam_select_free_sp_conformance import (
    _AGREEMENT_TOLERANCE_EDF,
    _AGREEMENT_TOLERANCE_ETA,
)
from polaris_re.core.verification import evidence_markdown, require_parity_evidence
from polaris_re.gam import GUIDE_FAMILY, GUIDE_FORMULA
from polaris_re.gam.formula_conformance import fit_formula_case
from polaris_re.gam.guide_conformance import (
    GUIDE_CLAIM,
    compare_guide_predict,
    predict_guide_example,
)

_HERE = Path(__file__).resolve().parent

_GAUNTLET_PROBES = (
    "gam_gaussian_free_sp_probe.json",
    "gam_by_factor_free_sp_probe.json",
    "gam_parametric_free_sp_probe.json",
    "gam_cr_re_ti_probe.json",
    "gam_quasipoisson_free_sp_probe.json",
    "gam_dispersion_two_stage_probe.json",
    "gam_quasipoisson_fixed_scale_probe.json",
    "gam_select_multiterm_free_sp_probe.json",
    "gam_production_mi_probe.json",
)
"""The probe JSONs ``payloads_from_probe_dir`` reads (the gauntlet's nine payloads)."""


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None  # a path that exists always has a loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guide_section(probe: Path) -> tuple[str, int, int]:
    payload = json.loads(probe.read_text())
    cell = next(c for c in payload["cells"] if c["name"] == "guide_example")
    require_parity_evidence(GUIDE_CLAIM.quantities, claim="guide example predict vs mgcv (ADR-254)")
    fitted = fit_formula_case(cell)
    if fitted.fit is None:
        return f"**REFUSED:** {fitted.refusal}\n", 0, 1
    result = compare_guide_predict(
        predict_guide_example(fitted.fit, cell["predict"]["newdata"]), cell["predict"]
    )
    text = "\n".join(
        [
            f"Formula: `{GUIDE_FORMULA}`, family `{GUIDE_FAMILY}`, "
            f"{len(cell['data']['age'])} training rows, "
            f"{len(cell['predict']['newdata']['age'])} held-out rows "
            "(the committed CSVs of `data/gam_preview/`).",
            "",
            evidence_markdown(GUIDE_CLAIM),
            "",
            "The fit, structure and `summary()` columns of this same cell are the row "
            "`guide_example` of the P3 and P4 tables above.",
            "",
            "| max abs link diff (gate) | link se Vp rel (gate) | link se Vc rel (gate) | "
            "response rel | response se rel | agrees |",
            "|---:|---:|---:|---:|---:|---|",
            f"| {result.max_abs_link_diff:.3e} ({_AGREEMENT_TOLERANCE_ETA:g}) | "
            f"{result.max_rel_link_se:.3e} ({_SE_REL_TOLERANCE:g}) | "
            f"{result.max_rel_link_se_unconditional:.3e} ({_SE_REL_TOLERANCE:g}) | "
            f"{result.max_rel_response_diff:.3e} | {result.max_rel_response_se:.3e} | "
            f"{result.agrees} |",
            "",
        ]
    )
    return text, int(result.agrees), 1


def build(probe_dir: Path, header: list[str]) -> tuple[str, bool]:
    """``(report, complete_and_all_agree)``."""
    predict_cmp = _load("gam_predict_compare")
    formula_cmp = _load("gam_formula_compare")
    summary_cmp = _load("gam_summary_compare")
    gauntlet = _load("gam_newton_gauntlet")

    def formula_probe() -> Path:
        return probe_dir / "gam_formula_probe.json"

    def summary_probes() -> list[Path]:
        return [
            formula_probe(),
            *(
                [probe_dir / "gam_target_size_probe.json"]
                if (probe_dir / "gam_target_size_probe.json").exists()
                else []
            ),
        ]

    sections: list[tuple[str, str, tuple[str, int, int] | None, str]] = []

    def run(
        title: str, needs: list[Path], fn: Callable[[], tuple[str, int, int]], note: str = ""
    ) -> None:
        missing = [p.name for p in needs if not p.exists()]
        if missing:
            sections.append((title, note, None, f"NOT MEASURED — missing {', '.join(missing)}."))
            return
        try:
            sections.append((title, note, fn(), ""))
        except Exception as exc:  # reported in the report, never swallowed
            sections.append((title, note, None, f"ERROR — {exc!r}"))

    def gauntlet_fn() -> tuple[str, int, int]:
        text, readings = gauntlet.build_report(probe_dir)
        return text, sum(1 for r in readings if r.agrees), len(readings)

    run(
        "1. Predict and standard errors (slices P1, P2)",
        [probe_dir / "gam_predict_probe.json"],
        lambda: predict_cmp.build_report(probe_dir / "gam_predict_probe.json"),
    )
    run(
        "2. The formula front end (slice P3)",
        [formula_probe()],
        lambda: formula_cmp.build_report(formula_probe()),
    )
    run(
        "3. summary() and the target-size fit (slice P4)",
        [formula_probe()],
        lambda: summary_cmp.build_report(summary_probes()),
    )
    run(
        "4. The user guide's worked example (slice P5)",
        [formula_probe()],
        lambda: _guide_section(formula_probe()),
    )
    run(
        "5. One Newton start vs mgcv's free-sp fit (outer-solver gauntlet)",
        [probe_dir / name for name in _GAUNTLET_PROBES],
        gauntlet_fn,
    )

    verdict_rows = ["| section | cells that agree | state |", "|---|---:|---|"]
    complete = True
    for title, _, result, problem in sections:
        if result is None:
            verdict_rows.append(f"| {title} | — | {problem} |")
            complete = False
        else:
            _, n_ok, n_all = result
            state = "all agree" if n_ok == n_all and n_all > 0 else "DISAGREEMENT — see section"
            complete = complete and n_ok == n_all and n_all > 0
            verdict_rows.append(f"| {title} | {n_ok} of {n_all} | {state} |")
    verdict = (
        "**ALL MEASURED SECTIONS AGREE (every cell inside its gate).**"
        if complete
        else "**NOT ALL SECTIONS AGREE OR WERE MEASURED — read the rows below; a disagreement "
        "is a result, and a section not measured is not a pass.**"
    )
    out = [*header, "", verdict, "", *verdict_rows, ""]
    for title, _, result, problem in sections:
        out += [f"## {title}", ""]
        out.append(result[0] if result is not None else problem)
        out.append("")
    return "\n".join(out), complete


def _header(args: argparse.Namespace, mgcv_line: str) -> list[str]:
    if args.local:
        stamp = (
            "> **TIER 1 — LOCAL SCRATCH RUN. NOT A COMMITTABLE MEASUREMENT.** Different mgcv "
            "release and BLAS from the pinned image (ROUTINE_MGCV_PARITY step 2)."
        )
    else:
        stamp = (
            f"> **TIER 3 — pinned oracle.** CI run `{args.run_id}`, commit `{args.commit}`, "
            f"oracle `{args.digest}`."
        )
    return [
        "# GAM parity report — PREVIEW",
        "",
        stamp,
        "",
        "**GENERATED by `scripts/gam_parity_report.py` — do not edit by hand.** Every "
        "headline is `evidence_markdown()` of a declared `VerificationClaim` (ADR-193); "
        "every table is the verbatim output of the comparison it reports.",
        "",
        f"{mgcv_line}",
        "",
        "**Gates (imported, not restated by hand):** "
        f"`eta` < {_AGREEMENT_TOLERANCE_ETA:g} and |`edf_total` diff| < "
        f"{_AGREEMENT_TOLERANCE_EDF:g} (ADR-221); relative `se.fit` < {_SE_REL_TOLERANCE:g} "
        "(ADR-250); summary gates derived from ADR-221 per cell (ADR-253); "
        "`log10(sp)`, REML score and deviance components are reported, never gated.",
        "",
        "**What this is not:** not a claim of general `mgcv` compatibility; not p-values, "
        "`bam`, `tp`/`te`/`t2`/`fs`, free-`sp` `sz`, or a factor-`by` beside a bare smooth of "
        "the same covariate (refused by name — `docs/GAM_USER_GUIDE.md` §6). One synthetic "
        "draw per cell: this is evidence about these cells, not a coverage guarantee.",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("probe_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--commit")
    ap.add_argument("--digest")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if not args.local and not (args.run_id and args.commit and args.digest):
        ap.error(
            "--run-id, --commit and --digest are required unless --local (no digest, no number)"
        )
    mgcv_line = "mgcv / R version: not read (no formula probe)."
    probe = args.probe_dir / "gam_formula_probe.json"
    if probe.exists():
        p = json.loads(probe.read_text())
        mgcv_line = (
            f"Oracle: mgcv {p['mgcv_version']} / {p['r_version']}, `LC_COLLATE={p['collate']}`."
        )
    report, ok = build(args.probe_dir, _header(args, mgcv_line))
    args.out.write_text(report)
    print(report)
    _ = ok  # a disagreement is a reported result, never a crash: exit 0 either way
    return 0


if __name__ == "__main__":
    sys.exit(main())
