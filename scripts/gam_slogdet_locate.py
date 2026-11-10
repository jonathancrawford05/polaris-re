"""Maintainer-run locator for the `slogdet` warnings (ADR-266). MEASUREMENT, own criterion.

Fits one formula on a CSV with warnings escalated to errors, so the FIRST numerical warning
prints its call stack, and records every `np.linalg.slogdet` call (sign, logdet, condition
number, max |entry|). Prints derived scalars only (no rows), so the output is safe to paste.

    uv run python scripts/gam_slogdet_locate.py DATA.csv "<formula>" [gam|bam]
"""

import sys
import traceback
import warnings

import numpy as np
import polars as pl

from polaris_re.gam import gam

REC: list[tuple[float, float, float, float]] = []
_orig = np.linalg.slogdet


def spy(m: np.ndarray):  # noqa: ANN201
    s, ld = _orig(m)
    REC.append((float(s), float(ld), float(np.linalg.cond(m)), float(np.max(np.abs(m)))))
    return s, ld


def main() -> None:
    path, formula = sys.argv[1], sys.argv[2]
    engine = sys.argv[3] if len(sys.argv) > 3 else "gam"
    data = pl.read_csv(path)
    kw = {"method": "fREML", "discrete": True} if engine == "bam" else {}
    np.linalg.slogdet = spy  # type: ignore[assignment]
    warnings.simplefilter("error", RuntimeWarning)
    try:
        fit = gam(formula, data, "poisson", **kw)
        print(f"no RuntimeWarning raised; converged={fit.converged}")
    except RuntimeWarning as w:
        print(f"FIRST RuntimeWarning: {w}")
        traceback.print_exc(limit=-8)
    finally:
        np.linalg.slogdet = _orig  # type: ignore[assignment]
    print(f"rows={data.height} slogdet calls={len(REC)}")
    for i, (s, ld, c, mx) in enumerate(REC):
        print(f"call {i}: sign={s:+.0f} logdet={ld:.4g} cond={c:.3e} max|H|={mx:.3e}")


if __name__ == "__main__":
    main()
