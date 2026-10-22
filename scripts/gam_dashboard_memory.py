"""Measure Polaris ``gam`` / ``bam`` peak RSS and wall time on synthetic data — dashboard D1.

MEASUREMENT (own criterion): Polaris against itself on the machine this runs on, one fit per
subprocess so ``ru_maxrss`` is that fit's own high-water mark (the R2 trial's process-wide
number is not). Compares nothing with ``mgcv``. Synthetic data only; no experience data.

    uv run python scripts/gam_dashboard_memory.py --out docs/measurements/gam_dashboard_memory.json
"""

import argparse
import json
import platform
import resource
import subprocess
import sys
import time

import numpy as np
import polars as pl

from polaris_re.gam import gam

FORMULA = 's(age, bs="cr", k=10) + s(year, bs="cr", k=8) + sex + offset(log_exposure)'


def make_data(n: int) -> pl.DataFrame:
    rng = np.random.default_rng(20261022)
    age = rng.integers(30, 90, n).astype(np.float64)
    year = rng.integers(2000, 2020, n).astype(np.float64)
    sex = rng.choice(["F", "M"], n)
    expo = rng.uniform(50.0, 500.0, n)
    mu = (
        expo
        * 0.002
        * np.exp(0.07 * (age - 60) - 0.01 * (year - 2000))
        * np.where(sex == "M", 1.2, 1)
    )
    return pl.DataFrame(
        {
            "deaths": rng.poisson(mu).astype(np.float64),
            "age": age,
            "year": year,
            "sex": sex,
            "log_exposure": np.log(expo),
        }
    )


def one(engine: str, n: int) -> None:
    data = make_data(n)
    t0 = time.perf_counter()
    if engine == "bam":
        fit = gam("deaths ~ " + FORMULA, data, "poisson", method="fREML", discrete=True)
    else:
        fit = gam("deaths ~ " + FORMULA, data, "poisson")
    sec = time.perf_counter() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_gb = rss / (1024.0**3 if sys.platform == "darwin" else 1024.0**2)
    print(
        json.dumps(
            {
                "engine": engine,
                "n_rows": n,
                "n_coef": len(fit.coef),
                "seconds": sec,
                "peak_rss_gb": rss_gb,
                "converged": bool(fit.converged),
            }
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--one", nargs=2, metavar=("ENGINE", "N"))
    ap.add_argument("--sizes", default="gam:2000,gam:10000,gam:40000,bam:40000,bam:200000")
    a = ap.parse_args()
    if a.one:
        one(a.one[0], int(a.one[1]))
        return
    rows = []
    for spec in a.sizes.split(","):
        eng, n = spec.split(":")
        r = subprocess.run(
            [sys.executable, __file__, "--one", eng, n], capture_output=True, text=True, check=True
        )
        rows.append(json.loads(r.stdout.strip().splitlines()[-1]))
        print(rows[-1], flush=True)
    base = subprocess.run(
        [
            sys.executable,
            "-c",
            "import resource,polaris_re.gam;"
            "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    out = {
        "kind": "MEASUREMENT (own criterion): Polaris against itself, synthetic data, "
        "one fit per subprocess",
        "formula": FORMULA,
        "import_baseline_rss_kb": int(base),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "results": rows,
    }
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
