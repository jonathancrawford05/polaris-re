"""PLAN slice 5f -- does single-start `select_lambdas_continuous` still suffice
on an N>4-block design whose extra blocks SHARE covariates with the existing
ones, the structure ADR-213's own N=8 case (`scripts/gam_multistart_robustness_diagnostic.py`
PART 2) explicitly did NOT test?

THIS SCRIPT MAKES NO mgcv COMPARISON, the same as its ADR-213 predecessor.
Every design below is fit by Polaris's own search alone, against itself,
across `OPENBLAS_NUM_THREADS`. There is no `VerificationClaim` here because
there is no second producer (ADR-193's own mechanical test has nothing to
apply to) -- this is an internal robustness measurement of one component,
not a parity reading. `docs/CONFORMANCE_LEDGER.md`'s row for this script
says so explicitly.

**Why ADR-213's own N=8 case does not answer this slice's question.** It
duplicated the N=4 shape (ref + numeric-by + ti) onto a SECOND, INDEPENDENT
synthetic covariate draw -- chosen deliberately to rule out rank-deficiency
after a covariate-REUSE attempt failed that way (see that script's own
docstring). That is real evidence for a decoupled N=8 structure, but the
target formula's own 13-21 blocks mostly SHARE covariates (`AttdAge`,
`PolYear`, factor levels across `sz(FaceSize, AttdAge)`,
`sz(Smoke, AttdAge)`, `sz(FaceSize, PolYear)`, `sz(Smoke, PolYear)` --
`docs/PLAN_mgcv_parity_engine.md` Section 1), which decoupled draws cannot
speak to.

**The N=8 design below, and why it is argued rather than merely tried.**
Reuses the ACTUAL N=4 near-flat fixture's own three terms (reference age,
the numeric-`by` MI term, the `ti(AttdAge, PolYear)` interaction --
identical to `_multiterm_model_spec`) and adds four more `s(x, by=Group)`
terms scaled by four independent synthetic binary indicators (`GroupA`
through `GroupD`), two keyed on `AttdAge` and two on `PolYear` -- standing
in for the target's own four `sz(factor, AttdAge/PolYear)` terms without
building `sz`'s own constrained construction (that is slice 6's work, not
this one):

  ref  : s(AttdAge, k=13, cr)                                     1 block
  by   : s(AttdAge, by=StudyYear_C, k=13, cr)                     1 block
  ti   : ti(AttdAge, PolYear, k=(13,6), cr)                       2 blocks
  gA   : s(AttdAge, by=GroupA, k=13, cr)                          1 block
  gB   : s(AttdAge, by=GroupB, k=13, cr)                          1 block
  gC   : s(PolYear, by=GroupC, k=6, cr)                           1 block
  gD   : s(PolYear, by=GroupD, k=6, cr)                           1 block
                                                          total: 8 blocks

**A first attempt at this shape was exactly singular, and the fix is worth
recording (Anchor 8's "argue, don't merely try").** The first draft used
only TWO independent binary indicators (`FaceSizeInd`, `SmokeInd`) and put
each one on BOTH an `AttdAge` term and a `PolYear` term (mirroring
`sz(FaceSize, AttdAge)`/`sz(FaceSize, PolYear)` literally). That design was
rank-deficient by exactly 2 (`np.linalg.matrix_rank` on the assembled `X`,
measured directly): an UNCONSTRAINED `by`-scaled `cr` basis always contains
the constant function in its span (ADR-200's own finding -- no
identifiability constraint is absorbed on a numeric-`by` smooth), so
`s(AttdAge, by=Ind)` and `s(PolYear, by=Ind)` sharing the SAME indicator
`Ind` each contain the direction `Ind` itself in their column space -- one
exact linear dependency per repeated indicator, confirmed by SVD (the
smallest two singular values are ~1e-15 against the next at 1.3e-2, and
the corresponding null-space vectors load exclusively on the age/year
block pair sharing one indicator). `mgcv`'s own `sz` construction avoids
this by centering each level's deviation against a shared reference smooth
-- an identifiability constraint this stand-in deliberately does not build.
**The fix: never reuse the same indicator across an `AttdAge` term and a
`PolYear` term** -- four INDEPENDENT indicators instead of two reused ones.
Measured full rank (`124 == 124`) and well-conditioned
(`cond(XᵀX) ≈ 1.3e7`, ordinary for a real design, nothing near the ~1e17
the singular draft produced) before this script was written the way it is.

Usage:
    uv run python scripts/gam_multistart_shared_covariates_diagnostic.py
    (loops threads {1, 2, 4} itself via subprocess re-exec, the same
    `threadpoolctl`-vs-env-var lesson ADR-211/ADR-213 both name)
"""

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
_GROUP_SEED = 20260831
"""Pinned per ADR-074 -- drawn once, never the wall clock. A distinct seed
from ADR-213's `_MULTISTART_SEED`/`20260830` (a different draw, not a
collision), chosen the day this slice was worked."""


def _run_one(n_threads: int) -> dict[str, object]:
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


def _build_shared_covariate_model_and_data() -> tuple[object, dict]:
    import numpy as np

    from polaris_re.analytics.gam_term_spec import ModelSpec, TermSpec

    payload = json.loads(_FIXTURE.read_text())
    age_knots = tuple(float(v) for v in payload["age_knots"])
    year_knots = tuple(float(v) for v in payload["year_knots"])
    data = {
        k: np.asarray(payload[k], dtype=np.float64)
        for k in ("AttdAge", "PolYear", "StudyYear_C", "ExposCnt")
    }
    n = data["AttdAge"].shape[0]
    rng = np.random.default_rng(_GROUP_SEED)
    data["GroupA"] = (rng.uniform(size=n) < 0.5).astype(np.float64)
    data["GroupB"] = (rng.uniform(size=n) < 0.4).astype(np.float64)
    data["GroupC"] = (rng.uniform(size=n) < 0.5).astype(np.float64)
    data["GroupD"] = (rng.uniform(size=n) < 0.4).astype(np.float64)

    def _cr(label: str, var: str, knots: tuple[float, ...], by: str | None) -> TermSpec:
        return TermSpec(
            label=label,
            variables=(var,),
            basis="cr",
            k=(len(knots),),
            knots=((var, knots),),
            by=by,
        )

    model = ModelSpec(
        family="binomial",
        link="cloglog",
        weights_column="ExposCnt",
        terms=(
            _cr("ref", "AttdAge", age_knots, None),
            _cr("by", "AttdAge", age_knots, "StudyYear_C"),
            TermSpec(
                label="ti",
                variables=("AttdAge", "PolYear"),
                basis="ti",
                k=(len(age_knots), len(year_knots)),
                knots=(("AttdAge", age_knots), ("PolYear", year_knots)),
            ),
            _cr("gA", "AttdAge", age_knots, "GroupA"),
            _cr("gB", "AttdAge", age_knots, "GroupB"),
            _cr("gC", "PolYear", year_knots, "GroupC"),
            _cr("gD", "PolYear", year_knots, "GroupD"),
        ),
    )
    payload_y = np.asarray(payload["y"], dtype=np.float64)
    return model, {"data": data, "y": payload_y}


def _worker(n_threads: int) -> None:
    import numpy as np

    from polaris_re.analytics.gam_model import assemble_model_design, resolve_family
    from polaris_re.analytics.gam_reml_optimize import (
        select_lambdas_continuous,
        select_lambdas_continuous_multistart,
    )
    from polaris_re.core.exceptions import PolarisComputationError

    model, bundle = _build_shared_covariate_model_and_data()
    data, y = bundle["data"], bundle["y"]
    weights = data["ExposCnt"]

    design = assemble_model_design(model, data)
    family = resolve_family(model.family, model.link)
    blocks = tuple(design["penalty_blocks"])
    bounds = (-2.0, 11.0)

    out: dict[str, object] = {
        "n_threads": n_threads,
        "n_blocks": len(blocks),
        "n_cols": int(design["x"].shape[1]),
        "rank": int(np.linalg.matrix_rank(design["x"])),
    }

    single = select_lambdas_continuous(
        y, design["x"], family, blocks, weights=weights, bounds=bounds
    )
    out["single_score"] = single.reml_score
    out["single_log10_sp"] = single.log_lambda.tolist()
    out["single_converged"] = single.converged
    out["single_at_bound"] = single.at_bound
    out["single_evals"] = single.n_function_evals

    try:
        multi = select_lambdas_continuous_multistart(
            y, design["x"], family, blocks, weights=weights, bounds=bounds, n_starts=9
        )
        out["multi_score"] = multi.best.reml_score
        out["multi_log10_sp"] = multi.best.log_lambda.tolist()
        out["multi_any_converged"] = multi.any_converged
        out["multi_total_evals"] = multi.total_function_evals
        out["multi_best_start_index"] = multi.best_start_index
    except PolarisComputationError:
        out["multi_score"] = None
        out["multi_any_converged"] = False
        out["multi_total_evals"] = None
        out["multi_best_start_index"] = None

    print(json.dumps(out))


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        _worker(int(sys.argv[2]))
        return

    rows = [_run_one(n) for n in _THREAD_SWEEP]

    print(f"OPENBLAS_NUM_THREADS sweep: {_THREAD_SWEEP}")
    print(
        f"design: n_blocks={rows[0]['n_blocks']}, n_cols={rows[0]['n_cols']}, "
        f"rank={rows[0]['rank']} (full rank: {rows[0]['rank'] == rows[0]['n_cols']})"
    )
    print()
    header = (
        f"{'threads':>7}  {'single score':>13}  {'multi score':>12}  "
        f"{'gap':>9}  {'single conv':>11}  {'multi evals':>11}"
    )
    print(header)
    for r in rows:
        multi_score = r["multi_score"] if r["multi_score"] is not None else float("nan")
        gap = r["single_score"] - multi_score
        print(
            f"{r['n_threads']:>7}  {r['single_score']:>13.6f}  "
            f"{multi_score:>12.6f}  {gap:>9.6f}  "
            f"{r['single_converged']!s:>11}  {r['multi_total_evals']!s:>11}"
        )

    single_scores = [r["single_score"] for r in rows]
    multi_scores = [r["multi_score"] for r in rows if r["multi_score"] is not None]
    spread = max(single_scores) - min(single_scores)
    print(f"\nSingle-start score spread across threads: {spread:.6f}")
    if multi_scores:
        mspread = max(multi_scores) - min(multi_scores)
        print(f"Multi-start score spread across threads:  {mspread:.6f}")

    print()
    print("READING (no mgcv comparison, no ADR-193 provenance claim -- see module docstring):")
    print(
        "compare this spread and this single-vs-multi gap against ADR-213's own N=4 "
        "reading (single-start spread 0.001483, best-of-9 spread 0.000006, ~247x tighter) "
        "and its N=8 DECOUPLED reading (single-start spread 0.001180, best-of-9 spread "
        "0.001165, essentially unchanged): if THIS covariate-SHARING N=8 design's spread "
        "and gap sit closer to the N=4 reading than to the decoupled N=8 one, that is "
        "evidence covariate-sharing (not merely block count) drives the weak-identifiability "
        "pathology multi-start exists to mitigate."
    )


if __name__ == "__main__":
    main()
