#!/usr/bin/env python3
"""Write the synthetic data set behind ``docs/GAM_USER_GUIDE.md`` (preview slice P5).

Usage: gam_guide_example_data.py [output_dir]      (default: data/gam_preview)

Synthetic mortality-style claims: overdispersed counts at (age, duration, sex) with an
exposure column. NOT experience data and not derived from any (DATA_LICENSING.md §1).
Continuous columns are rounded before writing so Polars and R's ``read.csv`` parse
identical decimal strings; the committed CSVs are what both sides of the guide's
mgcv comparison read.
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl

_SEED = 20261010
_N_TRAIN = 800
_N_NEW = 60


def _draw(rng: np.random.Generator, n: int, *, in_range_only: bool) -> pl.DataFrame:
    lo_age, hi_age = (47.0, 83.0) if in_range_only else (45.0, 85.0)
    lo_dur, hi_dur = (2.0, 19.0) if in_range_only else (1.0, 20.0)
    age = np.round(rng.uniform(lo_age, hi_age, n), 3)
    duration = np.round(rng.uniform(lo_dur, hi_dur, n), 3)
    sex = rng.choice(np.array(["F", "M"]), n)
    exposure = np.round(rng.uniform(200.0, 4000.0, n), 1)
    q = (
        0.0015
        * np.exp(0.085 * (age - 45.0))
        * np.where(sex == "M", 1.25, 1.0)
        * (1.0 + 0.5 * np.exp(-duration / 5.0))
        * np.exp(0.5 * np.sin(age * duration / 90.0))
    )
    mu = exposure * q
    deaths = rng.negative_binomial(6.0, 6.0 / (6.0 + mu)).astype(np.float64)
    return pl.DataFrame(
        {
            "deaths": deaths,
            "age": age,
            "duration": duration,
            "sex": sex.tolist(),
            "log_exposure": np.round(np.log(exposure), 6),
        }
    )


def main(out_dir: Path) -> None:
    rng = np.random.default_rng(_SEED)
    train = _draw(rng, _N_TRAIN, in_range_only=False)
    new = _draw(rng, _N_NEW, in_range_only=True).drop("deaths")
    out_dir.mkdir(parents=True, exist_ok=True)
    train.write_csv(out_dir / "guide_example_train.csv")
    new.write_csv(out_dir / "guide_example_new.csv")
    print(f"Wrote {len(train)} training rows and {len(new)} new rows to {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/gam_preview"))
