"""PLAN slice 5e — does `select_lambdas_continuous`'s single default start
still suffice once a design has more than the N=4 blocks ADR-211/ADR-212
measured it on, and does best-of-N multi-start
(`select_lambdas_continuous_multistart`) measurably help?

THIS SCRIPT MAKES NO mgcv COMPARISON. Every design below is fit by Polaris's
own search alone, against itself, across `OPENBLAS_NUM_THREADS`. There is no
`VerificationClaim` here because there is no second producer (ADR-193's own
mechanical test has nothing to apply to) -- this is an internal robustness
measurement of one component, the same class as ADR-211's own BLAS-thread
table, not a parity reading. `docs/CONFORMANCE_LEDGER.md`'s row for this
script says so explicitly.

PART 1 -- N=4, the ACTUAL structure ADR-211/212 measured (the committed
`tests/fixtures/gam_reml_optimize_near_flat_direction.json` recipe, the same
one `scripts/gam_multiterm_free_sp_probe.R` draws). Single default-start vs.
best-of-9 multi-start, at 1/2/4 OpenBLAS threads -- the same table shape
ADR-211 built, replayed through the now-reusable multi-start function
instead of a one-off diagnostic, so a reader can compare this slice's own
POST-FIX baseline against ADR-211's PRE-FIX numbers directly.

PART 2 -- N=8, SYNTHETIC. No mgcv fit exists for this design; it exists
purely to ask "does the single-start-vs-multistart gap PART 1 shows get
worse, better, or unchanged with twice as many blocks?" Built by literally
DUPLICATING PART 1's own three-term shape (ref + numeric-by + ti, the exact
structure ADR-211/212 measured) onto a SECOND, independent synthetic
covariate draw (own pinned seed, same row count, same response `y`) and
fitting both copies jointly. Independent draws keep the two copies'
columns from overlapping in span (unlike reusing AttdAge/PolYear under a
different scaling, which risked exact rank-deficiency -- tried first, and
rejected after it produced a singular design at the search's own selected
point):

  ref  : s(AttdAge, k=13, cr)                                     1 block
  by1  : s(AttdAge, by=StudyYear_C, k=13, cr)                     1 block
  ti1  : ti(AttdAge, PolYear, k=(13,6), cr)                       2 blocks
  ref2 : s(AttdAge2, k=13, cr)              -- second draw        1 block
  by2  : s(AttdAge2, by=StudyYear_C2, k=13, cr)                   1 block
  ti2  : ti(AttdAge2, PolYear2, k=(13,6), cr)                     2 blocks
                                                          total: 8 blocks

`y` is unchanged from PART 1 -- the second copy's own terms are not
generatively related to it, which is irrelevant to what this part measures
(the search's own convergence behaviour at N=8), the same way a synthetic
toy design elsewhere in this module's test suite need not be a realistic
model.

Usage:
    OPENBLAS_NUM_THREADS=1 uv run python scripts/gam_multistart_robustness_diagnostic.py
    (loops threads {1, 2, 4} itself via subprocess re-exec -- see `_THREAD_SWEEP`)
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

_FIXTURE = (
    pathlib.Path(__file__).parent.parent
    / "tests"
    / "fixtures"
    / "gam_reml_optimize_near_flat_direction.json"
)
_THREAD_SWEEP = (1, 2, 4)


def _run_one(n_threads: int) -> dict[str, object]:
    """Executed as a subprocess re-exec per thread count -- `OPENBLAS_NUM_THREADS`
    only reliably governs OpenBLAS's own thread pool if set BEFORE the process
    that first imports NumPy starts, which is why this script re-execs itself
    rather than looping in-process (the same lesson
    `tests/test_analytics/test_gam_reml_optimize.py`'s `TestFiniteDiffStep`
    class names for `threadpoolctl` inside a single process)."""
    env = dict(os.environ)
    env["OPENBLAS_NUM_THREADS"] = str(n_threads)
    result = subprocess.run(
        [sys.executable, __file__, "--worker", str(n_threads)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=str(pathlib.Path(__file__).parent.parent),
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _worker(n_threads: int) -> None:
    import numpy as np

    from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
    from polaris_re.analytics.gam_multiterm_conformance import _multiterm_model_spec
    from polaris_re.analytics.gam_reml_optimize import (
        select_lambdas_continuous,
        select_lambdas_continuous_multistart,
    )
    from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec
    from polaris_re.core.exceptions import PolarisComputationError

    payload = json.loads(_FIXTURE.read_text())
    age_knots = tuple(float(v) for v in payload["age_knots"])
    year_knots = tuple(float(v) for v in payload["year_knots"])
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    y = np.asarray(payload["y"], dtype=np.float64)
    weights = data["ExposCnt"]

    out: dict[str, object] = {"n_threads": n_threads}

    # ---- PART 1: N=4, the actual ADR-211/212 structure -------------------
    model4 = _multiterm_model_spec(age_knots, year_knots)
    design4 = assemble_model_design(model4, data)
    family4 = resolve_family(model4.family, model4.link)
    blocks4 = tuple(design4["penalty_blocks"])
    bounds4 = (-2.0, 11.0)

    single4 = select_lambdas_continuous(
        y, design4["x"], family4, blocks4, weights=weights, bounds=bounds4
    )
    try:
        multi4 = select_lambdas_continuous_multistart(
            y, design4["x"], family4, blocks4, weights=weights, bounds=bounds4, n_starts=9
        )
        out["n4_multi_score"] = multi4.best.reml_score
        out["n4_multi_log10_sp"] = multi4.best.log_lambda.tolist()
        out["n4_multi_any_converged"] = multi4.any_converged
        out["n4_multi_total_evals"] = multi4.total_function_evals
    except PolarisComputationError:
        out["n4_multi_score"] = None
        out["n4_multi_any_converged"] = False
        out["n4_multi_total_evals"] = None
    out["n4_single_score"] = single4.reml_score
    out["n4_single_log10_sp"] = single4.log_lambda.tolist()
    out["n4_single_converged"] = single4.converged
    out["n4_single_evals"] = single4.n_function_evals

    # ---- PART 2: N=8, synthetic -- PART 1's own shape, duplicated onto a
    # second, INDEPENDENT synthetic draw (pinned seed, ADR-074) ------------
    rng2 = np.random.default_rng(20260830)
    n = data["AttdAge"].shape[0]
    data8 = dict(data)
    data8["AttdAge2"] = rng2.uniform(1.0, 95.0, size=n)
    data8["PolYear2"] = rng2.uniform(1.0, 21.0, size=n)
    data8["StudyYear_C2"] = rng2.uniform(-5.0, 5.0, size=n)

    def _ref_by_ti(suffix: str, age_var: str, year_var: str, by_var: str) -> tuple[TermSpec, ...]:
        return (
            TermSpec(
                label=f"ref{suffix}",
                variables=(age_var,),
                basis="cr",
                k=(len(age_knots),),
                knots=((age_var, age_knots),),
            ),
            TermSpec(
                label=f"by{suffix}",
                variables=(age_var,),
                basis="cr",
                k=(len(age_knots),),
                knots=((age_var, age_knots),),
                by=by_var,
            ),
            TermSpec(
                label=f"ti{suffix}",
                variables=(age_var, year_var),
                basis="ti",
                k=(len(age_knots), len(year_knots)),
                knots=((age_var, age_knots), (year_var, year_knots)),
            ),
        )

    model8 = ModelSpec(
        family="binomial",
        link="cloglog",
        weights_column="ExposCnt",
        terms=_ref_by_ti("1", "AttdAge", "PolYear", "StudyYear_C")
        + _ref_by_ti("2", "AttdAge2", "PolYear2", "StudyYear_C2"),
    )
    design8 = assemble_model_design(model8, data8)
    family8 = resolve_family(model8.family, model8.link)
    blocks8 = tuple(design8["penalty_blocks"])
    out["n8_blocks"] = len(blocks8)
    bounds8 = (-2.0, 11.0)

    single8 = select_lambdas_continuous(
        y, design8["x"], family8, blocks8, weights=weights, bounds=bounds8
    )
    out["n8_single_score"] = single8.reml_score
    out["n8_single_log10_sp"] = single8.log_lambda.tolist()
    out["n8_single_converged"] = single8.converged
    out["n8_single_evals"] = single8.n_function_evals
    try:
        multi8 = select_lambdas_continuous_multistart(
            y, design8["x"], family8, blocks8, weights=weights, bounds=bounds8, n_starts=9
        )
        out["n8_multi_score"] = multi8.best.reml_score
        out["n8_multi_log10_sp"] = multi8.best.log_lambda.tolist()
        out["n8_multi_any_converged"] = multi8.any_converged
        out["n8_multi_total_evals"] = multi8.total_function_evals
    except PolarisComputationError:
        out["n8_multi_score"] = None
        out["n8_multi_any_converged"] = False
        out["n8_multi_total_evals"] = None

    print(json.dumps(out))


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        _worker(int(sys.argv[2]))
        return

    rows = [_run_one(n) for n in _THREAD_SWEEP]

    print(f"OPENBLAS_NUM_THREADS sweep: {_THREAD_SWEEP}")
    print()
    print("PART 1 -- N=4 (ADR-211/212's own structure), post-ADR-212-fix baseline")
    header = (
        f"{'threads':>7}  {'single score':>13}  {'multi score':>12}  "
        f"{'gap':>9}  {'single conv':>11}  {'multi evals':>11}"
    )
    print(header)
    for r in rows:
        gap = r["n4_single_score"] - (
            r["n4_multi_score"] if r["n4_multi_score"] is not None else float("nan")
        )
        print(
            f"{r['n_threads']:>7}  {r['n4_single_score']:>13.6f}  "
            f"{(r['n4_multi_score'] or float('nan')):>12.6f}  {gap:>9.6f}  "
            f"{r['n4_single_converged']!s:>11}  {r['n4_multi_total_evals']!s:>11}"
        )
    single_scores4 = [r["n4_single_score"] for r in rows]
    multi_scores4 = [r["n4_multi_score"] for r in rows if r["n4_multi_score"] is not None]
    spread4 = max(single_scores4) - min(single_scores4)
    print(f"\nSingle-start score spread across threads: {spread4:.6f}")
    if multi_scores4:
        mspread4 = max(multi_scores4) - min(multi_scores4)
        print(f"Multi-start score spread across threads:  {mspread4:.6f}")

    print()
    print(f"PART 2 -- N={rows[0]['n8_blocks']} (synthetic, no mgcv comparison)")
    print(header)
    for r in rows:
        m = r["n8_multi_score"]
        gap = r["n8_single_score"] - (m if m is not None else float("nan"))
        print(
            f"{r['n_threads']:>7}  {r['n8_single_score']:>13.6f}  "
            f"{(m or float('nan')):>12.6f}  {gap:>9.6f}  "
            f"{r['n8_single_converged']!s:>11}  {r['n8_multi_total_evals']!s:>11}"
        )
    single_scores8 = [r["n8_single_score"] for r in rows]
    multi_scores8 = [r["n8_multi_score"] for r in rows if r["n8_multi_score"] is not None]
    spread8 = max(single_scores8) - min(single_scores8)
    print(f"\nSingle-start score spread across threads: {spread8:.6f}")
    if multi_scores8:
        mspread8 = max(multi_scores8) - min(multi_scores8)
        print(f"Multi-start score spread across threads:  {mspread8:.6f}")

    print()
    print("READING (no mgcv comparison, no ADR-193 provenance claim -- see module docstring):")
    print(
        "if the N=8 single-vs-multi gap and/or the N=8 single-start thread spread exceed "
        "the N=4 ones, that is direct evidence the pathology gets WORSE with more blocks, "
        "not merely present; if they are comparable, one start's shortfall does not appear "
        "to compound with N in this particular synthetic stress case."
    )


if __name__ == "__main__":
    main()
