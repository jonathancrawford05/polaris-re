# Dev session log — 2026-09-19 — capability ladder slice 1 (rung L1)

**Epic:** `docs/PLAN_mgcv_capability_ladder.md` (slice 1)
**Branch:** `claude/ladder-slice-1` → PR #237
**ADR:** ADR-229
**Ledger:** one row, both quantities `INDEPENDENT`
**Preceded by:** PR #236 (ADR-228, `REFERENCE_INTERNAL`) — the core-contract fix
the maintainer authorised as a separate branch so it stayed independently
reviewable.

---

## What the slice was asked for, and what it delivered

Rung **L1** of the capability ladder: `gaussian(identity)` — the simplest family
in `mgcv`, and until today absent from `_FAMILY_LINKS` entirely. Acceptance was
Stage B `eta` + `edf_total` against `mgcv` on ADR-221's committed criterion, at
**tier 3**, at **fixed `sp`**.

Delivered: the family, its four derivative registry entries, 13 closed-form
tests, an R probe, a conformance module with a declared `VerificationClaim`, 10
tests over that module, a `mgcv-conformance.yml` step, and the tier-3
measurement. The rung is climbed and its ceiling is named.

---

## The measurement

Tier 3, pinned digest `sha256:0d54c192…`, R 4.6.1 / mgcv 1.9.4,
run [35446265890](https://github.com/jonathancrawford05/polaris-re/actions/runs/35446265890):

| quantity | reading | ADR-221's bound |
|---|---|---|
| `max_abs_eta_diff` | `2.442e-14` | `< 2e-2` (≈ `8.19e11×` headroom) |
| `abs(edf_total_diff)` | `7.105e-15` | `< 1.0` |

Polaris `edf_total` `55.972550`, `mgcv` `sum(m$edf)` `55.972550`. Offset
tripwire `0.000e+00`.

Tier 1 (mgcv 1.9.1) read `2.265e-14` and **exactly `0.0`** on the same recipe.
See ADR-229 for why the two tiers differing in that last figure is the better
outcome, not a discrepancy to explain away.

**No new tolerance was declared.** The bounds are imported from
`gam_select_free_sp_conformance`; Anchor W5 forbids this epic re-gating
anything.

---

## Three things worth carrying forward

### 1. An exact zero is a suspicion, not a triumph

At tier 1, `edf_total_diff` came back **exactly** `0.0`. Between two supposedly
independent producers, an exact zero is the signature of an echo — so it was
checked rather than reported:

- stripping every `mgcv`-produced key from the payload (`eta`, `edf_total`,
  `offset_gap`, `coef`, `converged`) leaves the Polaris number bit-identical;
- perturbing the first block's `sp` from `2.0` to `20.0` moves `edf_total` from
  `55.97` to `55.10`, in the direction a stiffer penalty requires — so it is not
  a constant that would survive the first check and still be worthless.

Both are tests now. The structural guarantee (`fit_gaussian_case` takes
`RGaussianRecipe`, which has no `eta`/`edf_total` key) is a claim about the
*type*, and Python does not enforce `TypedDict` at runtime; the strip test is
its runtime complement.

On reflection the near-exact agreement is what the mathematics predicts — at
fixed `sp` under a constant-weight family, `tr(F)` is a deterministic function
of `X` and `S_lambda` with no iteration in it — but the check had to come before
the explanation, not after.

**And tier 3 makes the point better than tier 1 did.** On the pinned build the
difference is `-7.105e-15`, not zero: the floating-point floor *without* bit
coincidence, which is what two independent implementations of the same algebra
should look like. An echo would have reproduced the zero on both.

### 2. Registering a family without its derivatives is a latent, badly-placed failure

Adding `("gaussian","identity")` to `_FAMILY_LINKS` left `resolve_family()`
succeeding while **four** `gam_derivatives` functions raised. PR #237's review
named two; sweeping the module found the other two.

The timing is the point: the free-scale path that reaches those registries is
*currently unreachable*, because `reml_score_general` raises on
`dispersion_fixed=False`. It would have surfaced at **slice 3**, when L5 lifts
that block — i.e. as a mysterious failure in a slice that did not cause it.

So the fix that matters is not the four entries but
`test_every_registered_family_link_has_its_derivative_entries`, which walks
`_FAMILY_LINKS` and demands all four for every registered pair. The next family
cannot be registered without them.

Two pre-existing tests broke when `gaussian` became registered — they used it as
their example of an *unregistered* family. The property under test is unchanged,
so only the stand-in moved (to `tweedie`, verified absent). Not weakened.

### 3. "Not measured" can be stale in either direction

PR #237 review [P1-2] caught the coverage row **under**-claiming: it held
`gaussian(identity)` at `expressible? = NO` after the family had been
registered. I had been watching only for the over-claiming direction — a Stage B
cell moving before the measurement earned it. Both are drift; the table is
either current or it is not.

The row now separates the two claims explicitly: `expressible?` moved when the
registration landed, Stage B moved only when this measurement did, and it reads
**fixed `sp` only** because that is what was measured.

---

## What this rung does NOT reach

**Fixed `sp` only**, and the reason is worth stating precisely rather than as a
hedge. Gaussian estimates its scale, and `gam_reml.reml_score_general` raises on
a free scale (`gam_reml.py:263`), so free-`sp` selection under this family is
blocked until rung **L5** (slice 3).

But at a fixed `sp` **the scale never enters the fit**. The Gaussian penalized
fit is ordinary penalized least squares, `(X'WX + S)^-1 X'Wz` with `W = I` and
`z = y`; the scale is what the REML criterion needs in order to *choose* `sp`,
not what the fitter needs in order to fit at a given one. So this slice measures
the whole of what L1 claims, and the part it cannot reach is exactly the part L5
owns.

`test_gaussian_estimates_its_scale` pins that premise. If it ever flips, the
plan's §2.2 argument is void and must be re-derived.

---

## Process notes

- **The "part 1 of 2" split was withdrawn.** I had opened PR #237 as a build-only
  half, treating "start the first slice" as a scope boundary. The maintainer
  asked why completing the slice in one PR would not be cleaner. It would, and
  is: a registered-but-unmeasured family is not a climbed rung, and splitting it
  would have published a PR whose own coverage row said "not measured".
- **The provenance gate (ADR-203) fired twice**, from `gam_family.py` and then
  `gam_derivatives.py`, both inside `unconditional_coverage_study.py`'s closure.
  Both times the study was **re-run** rather than the change asserted inert.
  Bit-identical both times: 0.7435 / 0.7815 / 0.7781 / 0.8090.
- **One over-broad `ruff format`.** I ran it across `scripts/` as well as
  `src/ tests/` and reformatted six unrelated diagnostic scripts. Reverted before
  the index. The mandated gate is `src/ tests/`; widening it silently rewrites
  files the PR has no business touching.
- **One dangling ADR citation, self-caught.** A docstring cited ADR-229 before it
  existed (`grep -c "^## ADR-229" docs/DECISIONS.md` → 0). Rewritten to state the
  closed-form verification and record the ADR as owed — which it now is not, as
  this slice wrote it.
- **One perf row** appended for HEAD (`perf/history.jsonl`, 47 rows). `peak_mib`
  33 → 33 (the only gating metric) and `output_fingerprint` unchanged, as it must
  be: nothing in this slice touches the `TermLife` hot path. The wall-time
  advisory flag fired at `2.061x` recent/baseline; this row's `0.0546s` is in
  fact the **fastest** in the whole 47-row series, and the flag reflects the two
  preceding rows having been recorded on a slower machine. Advisory-only for
  exactly this reason — see `scripts/perf_history.py`'s own docstring. No
  backfill for #235/#236 (maintainer's explicit direction).

---

## Verification

Daily-dev step 4. **The baseline is the load-bearing line here** — it is what the
next session diffs against, and the reason this section exists rather than
leaving the number in a commit message where nobody looks for it (PR #237 review
[P1-B]).

| check | result |
|---|---|
| `uv run pytest tests/ -m "not slow"` | **3696 passed, 3 skipped, 128 deselected, 0 failed** |
| collection, this branch | **3699 non-slow / 3827 total** |
| collection, `0eba928` (the commit before the measurement half) | **3690 non-slow / 3817 total** |
| delta | **+9 fast, +1 `@slow`** — exactly `test_gam_gaussian_conformance.py` |
| `uv run ruff format src/ tests/` | clean |
| `uv run ruff check src/ tests/` | All checks passed |
| `uv run mypy` on `gam_gaussian_conformance.py` | **0 errors attributable to the file** |
| `scripts/measurement_stamp.py check` | **5 ok, 1 unstamped (pre-existing backlog), 0 drifted** |
| `scripts/gam_gaussian_probe.R`, tier 1 | `n=900, mgcv 1.9.1, edf_total=55.972550, offset_gap=0.000e+00` |
| tier 3, run [35446265890](https://github.com/jonathancrawford05/polaris-re/actions/runs/35446265890) | `2.442e-14` / `-7.105e-15`, `agrees=True` |
| CI on `b033e0a` | 8 success + `Upload coverage` skipped by design; `mergeable_state` clean |

The delta reconciles **measured on both revisions with `--collect-only`**, not
inferred — an off-by-one in a stated baseline defeats the next session's own
reconciliation, which is how the "12 vs 13 tests" error earlier in this slice was
caught.

Two things the green checks do **not** establish, recorded so a later reader does
not over-read them:

1. **The conformance compare step is `continue-on-error: true`**, the house
   contract throughout that workflow. A green check proves the step *ran*, not
   that it *agreed*. The agreement above was read out of the run's own log.
2. **`measurement_stamp.py` reports 1 unstamped** — `MEASUREMENT_engine_recursion_prework.md`,
   a pre-existing backlog item whose producing scripts were never committed. Not
   this slice's, and not regenerable.

## Where slice 2 picks up

`docs/CONTINUATION_mgcv_capability_ladder.md`. Rung **L2**, `bs="re"` — random
effects as a smooth with an identity penalty. The nearest template is this
slice: R probe, conformance module with a declared claim, workflow step, tier 3.

Carried constraint that does **not** relax at L2: the tolerances stay imported.
