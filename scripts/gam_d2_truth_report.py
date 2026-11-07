"""D2 truth-recovery report (ADR-263 amendment 1): runs the pre-registered draws and prints the
machine-generated evidence table. Closed-form truth, not mgcv parity.

    uv run python scripts/gam_d2_truth_report.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "tests" / "test_gam"))
import test_improvement_truth as t  # noqa: E402

from polaris_re.core.verification import evidence_markdown  # noqa: E402
from polaris_re.gam import gam  # noqa: E402
from polaris_re.gam.effects import improvement_surface, truth_recovery_claim  # noqa: E402


def main() -> None:
    warnings.simplefilter("ignore")
    print(evidence_markdown(truth_recovery_claim()))
    print("\n| engine | seed | max abs z (<=4.5) | coverage (>=0.75) | max abs MI error | edf |")
    print("|---|---|---|---|---|---|")
    covers: dict[str, list[float]] = {"gam": [], "bam": []}
    for eng, seeds in (("gam", t.SEEDS), ("bam", t.SEEDS[:3])):
        for seed in seeds:
            f = t.draw(seed)
            fit = (
                gam(t.FORMULA, f, "poisson")
                if eng == "gam"
                else gam(t.FORMULA, f, "poisson", method="fREML", discrete=True)
            )
            s = improvement_surface(fit, f)
            tr = t.truth_grid(s.ages, s.years.size)
            z = float(np.max(np.abs(s.mi - tr) / s.mi_se))
            cov = float(np.mean((s.mi_lower <= tr) & (tr <= s.mi_upper)))
            covers[eng].append(cov)
            print(
                f"| {eng} | {seed} | {z:.2f} | {cov:.3f} | "
                f"{np.max(np.abs(s.mi - tr)):.4f} | {fit.edf_total:.1f} |"
            )
    print(
        f"\nmean coverage gam {np.mean(covers['gam']):.3f} (>=0.90); bam {np.mean(covers['bam']):.3f}"
    )


if __name__ == "__main__":
    main()
