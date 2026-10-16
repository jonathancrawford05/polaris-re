"""Compare one cell's gam and bam probe outputs (scratch, maintainer's machine only).

Prints scalars only: the agreement and the time/memory difference. The per-row arrays stay in
the scratch JSON files, which are never committed.

USAGE: python scripts/bam_discrete_probe_compare.py <cell_dir>
(optional: also run bam_discrete_probe_run.sh <cell_dir> bam_nodisc to attribute the gap)
"""

import json
import re
import sys
from pathlib import Path


def _peak_rss_mb(time_file: Path) -> float:
    text = time_file.read_text()
    match = re.search(r"(\d+)\s+maximum resident set size", text)
    if match is None:
        raise SystemExit(f"no 'maximum resident set size' in {time_file}")
    return int(match.group(1)) / 1024**2


def main(cell_dir: Path) -> None:
    for name in ("probe_gam.json", "probe_bam.json"):
        if not (cell_dir / name).is_file():
            raise SystemExit(
                f"missing {cell_dir / name}: run scripts/bam_discrete_probe_run.sh first"
            )
    gam = json.loads((cell_dir / "probe_gam.json").read_text())
    bam = json.loads((cell_dir / "probe_bam.json").read_text())
    assert len(gam["eta"]) == len(bam["eta"]), "row counts differ: not the same cell"
    d_eta = max(abs(a - b) for a, b in zip(gam["eta"], bam["eta"], strict=True))
    rel_se = max(abs(b - a) / a for a, b in zip(gam["se_fit"], bam["se_fit"], strict=True) if a > 0)
    print(f"cell: {cell_dir.name}  rows: {gam['n_rows']}")
    print(f"coef  gam {gam['n_coef']}   bam {bam['n_coef']}")
    print(f"time  gam {gam['elapsed_s']:.1f} s   bam {bam['elapsed_s']:.1f} s")
    print(
        f"peak  gam {_peak_rss_mb(cell_dir / 'probe_gam.time'):.0f} MB   "
        f"bam {_peak_rss_mb(cell_dir / 'probe_bam.time'):.0f} MB"
    )
    print(f"edf_total  gam {gam['edf_total']:.3f}   bam {bam['edf_total']:.3f}")
    print(f"max |d eta| = {d_eta:.4g}   max rel |d se.fit| = {rel_se:.4g}")
    print(f"unique values per covariate (sizes): {gam.get('n_unique')}  (<= 1000 means no binning)")
    nd = cell_dir / "probe_bam_nodisc.json"
    if nd.is_file():
        nod = json.loads(nd.read_text())
        pairs = {
            "gam vs bam(discrete=FALSE)": (gam, nod),
            "bam(discrete=FALSE) vs bam(discrete=TRUE)": (nod, bam),
        }
        for label, (x, y) in pairs.items():
            e = max(abs(a - b) for a, b in zip(x["eta"], y["eta"], strict=True))
            print(f"max |d eta| {label} = {e:.4g}")
        print(
            f"iterations: gam n/a   bam(discrete=FALSE) {nod.get('iter')}   bam {bam.get('iter')}"
        )
    print("per-smooth edf (gam, bam):")
    for g, b in zip(gam["smooths"], bam["smooths"], strict=True):
        print(f"  {g['label']}: {g['edf']:.3f}, {b['edf']:.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
