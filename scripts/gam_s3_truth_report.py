"""S3 sharp-truth report (ADR-267): runs the pre-registered draws and prints the
machine-generated evidence table. Closed-form truth, not mgcv parity.

    uv run python scripts/gam_s3_truth_report.py
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests" / "test_gam"))
import test_improvement_truth_sharp as t

from polaris_re.core.exceptions import PolarisComputationError
from polaris_re.core.verification import evidence_markdown
from polaris_re.gam import gam


def main() -> None:
    """``--ti-k A,B`` raises the ``ti`` margins (a post-hoc hypothesis, not gated)."""
    warnings.simplefilter("ignore")
    ti_k = None
    if "--ti-k" in sys.argv:
        a, b = sys.argv[sys.argv.index("--ti-k") + 1].split(",")
        ti_k = (int(a), int(b))
        print(f"ti margins k=c({a},{b}) (exploratory hypothesis, NOT pre-registered)\n")
    print(evidence_markdown(t.sharp_truth_claim()))
    print(
        "\n| engine | k (age/year) | seed | max abs z | coverage | max abs MI err | "
        "flagged smooths | unflagged miss |"
    )
    print("|---|---|---|---|---|---|---|---|")
    unflagged = 0
    fits = 0
    for eng, seeds in (("gam", t.SEEDS), ("bam", t.SEEDS[:3])):
        for _k_label, (ka, ky) in t.KS.items():
            for seed in seeds:
                f = t.draw(seed)
                try:
                    fit = (
                        gam(t.formula(ka, ky, ti_k), f, "poisson")
                        if eng == "gam"
                        else gam(
                            t.formula(ka, ky, ti_k), f, "poisson", method="fREML", discrete=True
                        )
                    )
                except PolarisComputationError as exc:
                    print(f"| {eng} | {ka}/{ky} | {seed} | REFUSED: {str(exc)[:50]} | | | | |")
                    continue
                fits += 1
                m = t.measure(fit, f)
                bad = m["z"] > t.Z_BOUND and not m["flagged"]
                unflagged += bad
                print(
                    f"| {eng} | {ka}/{ky} | {seed} | {m['z']:.2f} | {m['cover']:.3f} | "
                    f"{m['max_err']:.4f} | {', '.join(m['flagged']) or '-'} | "
                    f"{'YES' if bad else 'no'} |"
                )
    print(
        f"\n{fits} fits; unflagged misses (z > {t.Z_BOUND} with no saturated smooth): {unflagged}"
    )


if __name__ == "__main__":
    main()
