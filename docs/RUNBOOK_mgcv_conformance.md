# Runbook — the `mgcv` conformance run

**What it settles:** three quantities the penalized MI surface reports were *adopted from
`mgcv` and unverified* (`PLAN_penalized_mi_surface.md` Anchor 8) — `tr(F)` as the
per-term EDF, the Kass-Steffey unconditional covariance, and Wood's `gamma`.

**The run has happened (2026-08-10, PR #193) and it is now automated.** ADR-189 +
amendment 1.

> ## Results — R 4.6.1 / mgcv 1.9.4 / jsonlite 2.0.0, CRAN snapshot 2026-08-01
>
> ```
> level 1: AGREES     level 2: AGREES     level 3: AGREES
> level 4: DISAGREES  level 5: DISAGREES
>
> (Illustrative, and both verdicts have since moved: **level 5 AGREES** since
> ADR-197 fixed the REML criterion, and level 4's DISAGREES is now about the
> SHIPPED engine not being re-pointed — ADR-190's formula gap closed in ADR-202.
> Kept as a shape-of-output example, not a current reading.)
> ```
>
> | quantity | verdict |
> |---|---|
> | **`tr(F)` as the per-term EDF** | **VERIFIED** — agrees to 7.2e-13 (tol 1e-6) |
> | **Kass-Steffey unconditional covariance** | **REFUTED — systematically under-inflates.** Ours 1.11-1.21x, mgcv 1.49-1.87x, every cell in the same direction |
> | **Wood's `gamma`** | **UNSETTLED** — misses both PROVISIONAL tolerances narrowly; the cross-cell sign check passes |
>
> **Levels 4 and 5 are not slice-5 acceptance criteria.** The comparator exits 2 on any
> disagreement, so the CI check is red **on findings, not on defects** — read the job
> summary before treating red as broken. Per Anchor 8 a run that refutes one of the three
> is a *successful* run that changes the anchor.
>
> **Do not widen `LEVEL_METRICS` tolerances to go green.** Level 5's two PROVISIONAL
> tolerances may be re-derived now that a measurement exists, but only from a stated rule
> about selection noise. A tolerance chosen because it makes a check green measures nothing.

## It runs in CI now — you do not need R

`.github/workflows/mgcv-conformance.yml` (PR #193) runs both halves on every change to a
conformance file: the R side inside a **digest-pinned** container (never a tag — a tag would
let an `mgcv` update rewrite the oracle silently), then the comparator as an ordinary `uv`
job, publishing the table to the job summary.

**ADR-151 / Anchor 5 still hold.** No job runs pytest, `rscript_mgcv_available()` still
returns `False` everywhere Python CI runs, and the trigger is path-filtered so an ordinary PR
never pulls the image. R exists only inside that container, in its own job.

The manual commands below remain valid for a local run or for the HMD/ILEC cases, which are
not in CI because their exchange must not leave the maintainer's machine.

---

## The two commands

```bash
# 1. R side — reads the committed exchange, writes one reference JSON.
#    No arguments needed; both paths default.
Rscript scripts/mgcv_conformance.R

# 2. Python side — compares, prints a pass/fail table, writes the committed report.
uv run python scripts/compare_mgcv_conformance.py \
    --markdown docs/MEASUREMENT_mgcv_conformance.md
```

Requirements for step 1: R with **`mgcv`** (a base R recommended package, usually already
present) and **`jsonlite`**. Nothing else — no `reticulate`, no `RcppCNPy`, which is why
the exchange is TSV + JSON rather than `.npz`.

Step 1 exits **non-zero** on any R-side error, so a batch that dies halfway cannot be
mistaken for a run whose numbers disagreed. Step 2 exits `0` when every level agrees, `2`
when a level disagrees (a disagreement is a *result*), and `1` when it could not compare
at all.

Commit `data/mgcv_exchange/synthetic/mgcv_reference.json` and the report. From then on the
implementer iterates **offline** against that reference — no further R runs while fixing
our arithmetic.

---

## What each level means

| level | what R does | what it settles | tolerance |
|---|---|---|---|
| 1 | `sp` fixed to ours | the penalized IRLS itself — coefficients element-wise, and `eta` | `1e-6` on coefficients, `1e-9` on `eta` |
| 2 | `sp` free, `method = "REML"` | our REML criterion and grid search | 0.5 decade on `log10 sp`, 1.0 on `edf` |
| 3 | `sum(m$edf)`, `m$edf` per block | **`tr(F)`** — Anchor 4's definition, finally checked | `1e-6` |
| 4 | `vcov(m)`, `vcov(m, unconditional = TRUE)` | `Vb`, and the Kass-Steffey correction | `1e-6` relative at fixed `sp`; 0.25 on the inflation ratio at free `sp` |
| 5 | `gamma = 1.4` | `gamma`'s reference behaviour | as level 2 |

Every tolerance and the reason for it is printed in the report, and lives in
`LEVEL_METRICS` in `src/polaris_re/analytics/experience_mgcv_conformance.py`. The two
free-`sp` tolerances were marked provisional until the first run; they now have their first
measurement and **both pass, narrowly** — `max_abs_log10_sp_diff` 4.3221e-01 against 0.5 and
`abs_edf_total_diff_free_sp` 8.7334e-01 against 1.0, roughly 13% of headroom each. Close
enough that a different seed could cross either, which is a fact about the tolerances and not
a licence to widen them.

**One thing the level table cannot show: λ travels inside `paraPen`, not through `gam()`'s
top-level `sp`.** A `paraPen`-only fit has an empty smooth list, so a top-level `sp` dies in
`gam.setup` at `fix.ind <- G$sp >= 0` — which is why every fixed-λ cell crashed on the first
real run and the suite had never executed at all (PR #193).

### Level 4 was the decisive one, and it decided — see the verdict box above

**It came out refuted, and that is the actionable result of the whole slice.** Read the
limitation below first, because it is what licenses the reading: the metric is an inflation
ratio at independently-selected λ, so it is legible only once level 2 passes — and level 2
passes. Ours inflates 1.11-1.21x where `mgcv` inflates 1.49-1.87x, every cell in the same
direction. An under-inflated covariance under-covers, which is what ADR-188 measured. So the
Anchor-7 shortfall points at **our Kass-Steffey arithmetic**, not at shrinkage bias.

### The limitation that makes level 4 weak, and why it was still enough

ADR-188's Anchor-7 gate **failed**: unconditional coverage 0.8516 / 0.8581 against a
floor of 0.9192. That fails for one of two reasons with completely different remedies —
our Kass-Steffey arithmetic is wrong, or the residual shortfall is shrinkage bias that no
covariance correction can reach. Level 4 is what separates them.

> **Both numbers here are superseded, and the answer turned out to be "both"**
> (2026-08-23, ADR-203). The 0.8516 / 0.8581 baseline went stale when `ce0b9f1`
> corrected the REML criterion on 2026-08-19; re-measured, the shipped band sits at
> 0.7815 / 0.8090. And the two remedies above are not exclusive: fixing the
> arithmetic (eq. (7), ADR-202) moved coverage to 0.8167 / 0.8354 — real, and still
> ~10 points short of the floor, so a second cause remains as well. Read the
> paragraph above as the question that was asked, not as the current state.

But `mgcv` forms `Vc` **only when the smoothing parameters were estimated** — there is no
`Vc` at fixed `sp`. And at free `sp` the two sides select *different* λ (ours from a
0.25-decade grid, R's continuously), so the two matrices differ for a reason that is not
the correction. So level 4 is two metrics:

1. **conditional `Vb` at fixed λ** — exact, tight, and it validates `(XᵀWX + S)⁻¹`;
2. **the inflation factor** `mean(diag(Vc)) / mean(diag(Vb))` at free λ — the most
   scale-free summary of the correction that survives a λ disagreement.

**Read metric 2 only after level 2 passes.** On its own it cannot distinguish a wrong
Jacobian from a λ disagreement.

---

## Why this compares `y ~ 0 + X` and not `te(attained_age, calendar_year)`

The exchange ships **our** tensor design and **our** difference penalties; `mgcv` accepts
exactly that through `paraPen`. Fitting a `te()` instead would compare two bases, two knot
placements and two identifiability constraints, and a disagreement would be
uninterpretable. With the design and the penalties supplied, the penalized Poisson
log-likelihood is strictly concave over a *shared* problem, its maximiser is unique, and
every disagreement localises to arithmetic.

That property is checkable **without R**: `penalized_score_infinity_norm` verifies
`Xᵀ(y - μ) - Sβ ≈ 0` at the exported coefficients, which is the stationarity condition of
the penalized log-likelihood. The committed reference's worst cell measures **2.2e-10**,
so the exported coefficients are the ones any conformant solver must return.

## `scalePenalty` — measured, and it is NOT load-bearing

`gam.control(scalePenalty = FALSE)` is still set. **But an earlier revision of this runbook
called it "the one setting that is load-bearing", and the 2026-08-10 run refuted that.** It
never reaches `paraPen`:

- **Structural** — `gam.setup` passes `scale.penalty` only into `smoothCon()`; `S.scale`
  does not appear anywhere in its `paraPen` path.
- **Empirical** — with penalties deliberately mismatched by `1e6` and λ fixed,
  `max|coef(scalePenalty = TRUE) − coef(FALSE)|` is **exactly 0**.

`sp` already multiplies the supplied `S` directly. **The guarantee is structural, not
configured.** Setting it `FALSE` plus the `tryCatch` is worth keeping as a **version
tripwire** — if a future `mgcv` routes rescaling through `paraPen`, the run says so instead
of quietly comparing a rescaled penalty — and that is a smaller, true claim in place of the
old one.

Three guards remain, and none of them is now claimed to be what protects the comparison:

1. the script sets `scalePenalty = FALSE`, the strictly safer direction;
2. it **fails loudly** if `gam.control` rejects the argument;
3. it **reads the manifest field directly and refuses a missing one.** `isFALSE(NULL)` is
   `FALSE` in R, so an absent field under a negation would hand `mgcv` the rescaling default
   *without* guard 2 firing (PR #192 review).

The comparator still refuses outright if the reference reports `scale_penalty` anything but
`false`.

**`penalty_scaling()` was removed as a defence, because it could never fire.**
`m$paraPen$S.scale` is absent and `length(m$smooth)` is 0, so the only field it ever returned
was `full.sp` — the **smoothing-parameter vector**, not a rescaling factor. It fired the
comparator's "sp did not multiply the supplied S" note on **all ten cells** of a run where
level 1 agreed to 1e-13. The `full_sp` probe is gone; the probe now returns empty, which is
the correct reading. **A guard that fires every time is no better than one that never fires;
both read as protection and neither is.**

## The hash guard

Both reference files record the exchange SHA-256 they were computed from. The comparator
recomputes it from the files on disk and **refuses to compare** if either disagrees:

```
The mgcv reference was computed from exchange 78dc8914de78… but
data/mgcv_exchange/synthetic now hashes to a1b2c3d4e5f6…
```

If you see that, the exchange was re-exported after R ran. Re-run step 1. Iterating
against a stale reference and declaring parity with a file R never saw is the failure mode
this construction is most exposed to, and it is silent by nature.

---

## The case matrix

Ten cells over three designs — a matrix, not a case, because a single cell can agree by
accident.

| cell | design | `sp` | `gamma` | levels |
|---|---|---|---|---|
| `l1-interior` | `d1` `k=(7,6)` | fixed `(1e1, 1e2)` | 1.0 | 1, 3, 4 |
| `l1-age-saturated` | `d1` | fixed `(1e6, 1e2)` | 1.0 | 1, 3 |
| `l1-year-saturated` | `d1` | fixed `(1e1, 1e6)` | 1.0 | 1, 3 |
| `l1-scale-convention` | `d1` | fixed `(1e3, 1e0)` | 1.0 | 1 |
| `l1-interior-factors` | `d2` `k=(7,6)` + `sex` | fixed `(1e1, 1e2)` | 1.0 | 1, 3 |
| `l1-interior-kb` | `d3` `k=(10,5)` | fixed `(1e1, 1e2)` | 1.0 | 1, 3 |
| `l2-free-sp` | `d1` | free | 1.0 | 2, 4 |
| `l2-free-sp-factors` | `d2` | free | 1.0 | 2, 4 |
| `l2-free-sp-kb` | `d3` | free | 1.0 | 2, 4 |
| `l5-gamma` | `d1` | free | **1.4** | 5 |

`l1-scale-convention` earns its place: the PR #190 review flagged that
`log|XᵀWX + S|` is evaluated at the **unscaled** penalty, fixing a convention for λ
relative to φ. Two λ of similar magnitude would hide a convention error; `(1e3, 1e0)` is
three decades apart in opposite directions and exposes it.

## Regenerating the exchange (only if the design or the penalties change)

```bash
uv run python scripts/export_mgcv_case.py --case synthetic \
    -o data/mgcv_exchange/synthetic
```

Idempotent — pinned seed, no wall clock (ADR-074), so a no-change re-run produces
byte-identical files. This **invalidates any committed `mgcv_reference.json`**, and the
comparator will say so. Two tests guard the committed copy: one re-hashes it, one
regenerates it and compares.

## The real-data scale check (HMD / ILEC)

The synthetic case is sufficient on its own to settle all five levels. Real data adds
125k cells, real overdispersion and real sparsity.

**The licensing line runs between them.** A real-data exchange contains `deaths` and
`log(exposure · q_base)` per cell — that *is* the dataset at cell grain, and it is never
committed (Design Anchor 6, `DATA_LICENSING.md` §1). Only the comparison report comes
back, because a max absolute coefficient difference is a derived scalar and not
experience. The exporter enforces this: a real-data case **requires** an explicit `-o`
outside the repository and refuses to default into it.

The exporter reads a grouped-cells file rather than re-running the ingest, so produce one
first:

```python
import polars as pl
from polaris_re.analytics.experience_diligence import (
    ILEC_VINTAGES,
    attach_empirical_base,
    resolve_ilec_path,
)
from polaris_re.analytics.experience_loaders import load_ilec

vintage = ILEC_VINTAGES["2012-19"]
cells = load_ilec(
    resolve_ilec_path(), column_map=vintage.column_map, separator=vintage.separator
).filter(pl.col("attained_age").is_between(45, 85))
grouped = cells.group_by(["attained_age", "calendar_year", "sex"]).agg(
    pl.col("central_exposure").sum(), pl.col("death_count").sum()
)
base = attach_empirical_base(
    grouped, exposure_col="central_exposure", deaths_col="death_count"
)
base.cells.write_parquet("/home/you/work/ilec_cells.parquet")
```

Then:

```bash
uv run python scripts/export_mgcv_case.py --case ilec-banded \
    --cells ~/work/ilec_cells.parquet -o ~/work/mgcv_exchange/ilec
Rscript scripts/mgcv_conformance.R ~/work/mgcv_exchange/ilec
uv run python scripts/compare_mgcv_conformance.py \
    --exchange ~/work/mgcv_exchange/ilec \
    --markdown docs/MEASUREMENT_mgcv_conformance_ilec.md
```

Note the grouping keys are yours to choose there; the manifest records which factor
columns each design actually found, so a frame with no factor column produces a design
with an empty factor block rather than a silent mismatch.

---

## Expected round trips: two to three

Run 1 establishes the deltas. The implementer fixes offline against the committed
reference. Run 2 confirms. A third only if reaching parity requires changing the design or
the penalty — which changes the exchange, and therefore needs a fresh R run by
construction.

**A run that refutes one of the three adopted quantities is a successful run.** PLAN
Anchor 8: it changes the anchor, not the slice. `tr(F)` moving from *adopted* to *refuted*
is an acceptable outcome and the reason this slice exists.

**Do not tune to pass.** `gamma`, a larger `k`, or moved λ bounds would each be choosing a
number to make a measurement come out — the same refusal ADR-188 made of its own failing
gate.
