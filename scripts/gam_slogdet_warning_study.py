"""S2 study (ADR-266): what do the `slogdet` warnings mean? MEASUREMENT (own criterion), no mgcv.

Wraps np.linalg.slogdet inside the REML modules to record each call's sign, logdet and
condition number, and captures the RuntimeWarnings the page's R-04 caption counts.
    uv run python scripts/gam_slogdet_warning_study.py
"""

import warnings
from collections import Counter

import numpy as np
import polars as pl

from polaris_re.gam import gam

AGES = np.arange(40, 71)
WIDE = False  # H2: ages 0-120 with exposure fading in the tails (sparse edge cells)
YEARS = np.arange(2005, 2021)
F = (
    'death_count ~ s(attained_age, bs="cr", k={ka}) + s(calendar_year, bs="cr", k={ky}) '
    '+ ti(attained_age, calendar_year, bs="cr") + offset(log_exposure)'
)


def draw(seed: int, expo: float, n_sub: int) -> pl.DataFrame:
    """n_sub sub-cells per (age, year), each with exposure `expo` (row-level: small, many)."""
    rng = np.random.default_rng(seed)
    ages = np.arange(0, 121) if WIDE else AGES
    a = np.repeat(ages, YEARS.size * n_sub).astype(float)
    y = np.tile(np.repeat(YEARS, n_sub), ages.size).astype(float)
    q = 0.004 * np.exp(0.08 * (a - 45.0)) * np.exp(-(0.02 + 0.0005 * (a - 40)) * (y - 2005))
    e = expo * (np.exp(-(((a - 60.0) / 18.0) ** 2)) if WIDE else 1.0) * np.ones(a.size)
    return pl.DataFrame(
        {
            "attained_age": a,
            "calendar_year": y,
            "death_count": rng.poisson(e * q).astype(float),
            "log_exposure": np.log(e),
        }
    )


REC: list[tuple[float, float, float]] = []
_orig = np.linalg.slogdet


def spy(m: np.ndarray):  # noqa: ANN201
    s, ld = _orig(m)
    try:
        c = float(np.linalg.cond(m))
    except Exception:
        c = float("nan")
    REC.append((float(s), float(ld), c))
    return s, ld


def run(label: str, ka: int, ky: int, expo: float, n_sub: int, engine: str, seed: int) -> None:
    REC.clear()
    d = draw(seed, expo, n_sub)
    np.linalg.slogdet = spy  # type: ignore[assignment]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        kw = {"method": "fREML", "discrete": True} if engine == "bam" else {}
        try:
            fit = gam(F.format(ka=ka, ky=ky), d, "poisson", **kw)
        except Exception as e:
            np.linalg.slogdet = _orig  # type: ignore[assignment]
            print(
                f"| {label} | {engine} | {seed} | {d.height} | {ka}/{ky} | RAISED | - | - | - | "
                f"{type(e).__name__}: {str(e)[:60]} |"
            )
            return
    np.linalg.slogdet = _orig  # type: ignore[assignment]
    cat = Counter(str(x.message)[:50] for x in w)
    bad = [r for r in REC if not np.isfinite(r[1]) or r[0] <= 0]
    conds = np.array([r[2] for r in REC]) if REC else np.array([np.nan])
    print(
        f"| {label} | {engine} | {seed} | {d.height} | {ka}/{ky} | {fit.converged} | "
        f"{len(REC)} | {len(bad)} | {np.nanmax(conds):.2e} | {dict(cat)} |"
    )


if __name__ == "__main__":
    print(
        "| grain | engine | seed | rows | k | converged | slogdet calls "
        "| non-finite/sign<=0 | max cond | warnings |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    import sys

    if "wide" in sys.argv:
        WIDE = True
    for grain, expo, nsub in (
        (("wide-aggregated", 5.0e4, 1), ("wide-row-level", 40.0, 1))
        if WIDE
        else (("aggregated", 5.0e4, 1), ("row-level", 40.0, 6))
    ):
        for ka, ky in ((8, 5), (20, 7)):
            for engine in ("gam", "bam"):
                for seed in (1, 2, 3):
                    run(grain, ka, ky, expo, nsub, engine, seed)
