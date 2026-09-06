# Resolvable tolerances — derive the threshold from the noise, not from taste

> **Status: PROPOSED.** Not adopted; it binds nothing until an ADR adopts it
> (the `VERIFICATION_STANDARD.md` / ADR-193 precedent). Written at maintainer
> request, 2026-09-05: *"this is a better approach to ground our development."*
>
> **Scope: portable.** Drawn from this project's `mgcv` parity epic, but the
> pattern is about any acceptance criterion expressed as a numeric tolerance —
> a parity gate, a convergence flag, a regression bound, a coverage target.
> Companion to `VERIFICATION_STANDARD.md`, which governs what counts as
> evidence; this governs whether the *number* in a criterion means anything.

---

## 1. The observation, from two independent instances

**Instance 1 — slice 7c (ADR-219).** `SELECT_FREE_SP_MODEL_CLAIM` gated on raw
`log10(sp)` agreement at `1e-2`. On the `select=TRUE` structure the residual sat
at `1.48` — two orders outside — while `eta` agreed to `0.0027` and `edf_total`
to `0.11`. The diagnosis was not a worse fit: **5 of 7 directions were
identified**, and in the other two the criterion is flat, so `log10(sp)` there is
not determined by the data at all. The gate demanded precision from a quantity
the machinery cannot resolve.

**Instance 2 — slice 7f (ADR-222).** `converged` was to be re-pointed at a
`gtol` test on the projected gradient. The well-conditioned N=4 control plateaus
at `2.040e-04` while being optimal to `1e-6`; the bound-active N=7 case plateaus
at `4.9e-01`. `gtol = 1e-8` is below what the objective resolves at all. Any
absolute threshold between the two plateaus is arbitrary.

**Same shape, twice, in one epic.** In both cases a real number was demanded of
a quantity that does not carry that many digits of information — and in both, the
tempting fix (move the threshold) would have hidden the finding instead of
recording it.

## 2. The failure mode, named

**A tolerance is only meaningful on a quantity the machinery can resolve, and
"can resolve" is measurable rather than a matter of judgement.**

The failure has a signature worth recognising early: *the same criterion gives
wildly different readings on problems that are equally well solved.* That is not
noise in the results — it is the criterion measuring something other than
quality. Instance 1 read `1.48` and `0.0027` on the same fit; instance 2 read
`2.0e-04` and `4.9e-01` on two fits that were both as good as their problems
allow.

**And the second, subtler error: reporting "flat" and "failed" as the same
thing.** In instance 2 the `2.040e-04` plateau is a direction with *no optimum
to find* — every point in it is optimal, so a large gradient component there is
not a defect. The `4.9e-01` plateau is a search that *did not reach* an optimum
that exists. Collapsing both into `converged = False` destroys the distinction
that tells you whether to fix the solver or leave it alone.

## 3. The method

Four steps, each producing something committable.

1. **Measure the noise floor `ε` of the quantity itself.** Evaluate it under
   perturbations that are mathematically no-ops but numerically distinct — BLAS
   thread count, summation reordering, an orthogonal similarity transform. The
   spread *is* the floor. (Established practice: Moré & Wild 2011, "Estimating
   computational noise".) Nothing below `ε` is knowable, whatever the criterion
   says.
2. **Identify which components carry signal above `ε`.** For a vector quantity
   this is a curvature or eigenvalue reading — which directions the data
   actually determines. Instance 1 did exactly this and found 5 of 7.
3. **State the tolerance relatively, on the resolvable subspace only.**
   `||r||/(1+|f|) ≤ ε_rel` rather than `||r|| ≤ c`. Absolute thresholds are not
   portable across problems, parameterisations, or data scales; relative ones
   are.
4. **When something is unresolvable, say so — do not move the tolerance to
   cover it.** The finding is the deliverable. Widening a tolerance to make a
   measurement pass is forbidden here anyway (`PLAN_mgcv_parity_engine.md`
   Anchor 8; `PLAN_gam_production_wiring.md` Anchor W5), and this pattern
   explains *why* that prohibition is not merely procedural: a widened tolerance
   still measures the wrong thing, just more permissively.

**Report three outcomes, not two.** `PASS` / `FAIL` cannot express "optimal in
every direction that has an optimum". A criterion built this way needs a verdict
like `PASS_ON_RESOLVED_SUBSPACE`, carrying the count of unresolved components.
`PROPOSAL_convergence_certificate.md` is the worked example.

## 4. What this costs, honestly

Steps 1 and 2 are measurements, and they are not free — a curvature reading is
`O(N²)` evaluations of the underlying quantity where a threshold comparison is
`O(1)`. That is a real argument for computing the certificate **on request
rather than in every code path**, not an argument against the method. The cost
also falls sharply when the surrounding algorithm already computes the second
derivatives for its own reasons, which is why the convergence certificate is
staged to land with the Newton-based solver rather than before it.

**And a limit worth stating.** This pattern makes a criterion *meaningful*. It
does not make a computation *right* — the same epic's slice 7h buys nine orders
of reproducibility while being slightly *less* accurate against `float128`.
Resolvability and correctness are different properties with different fixes, and
a criterion that is honest about what it can resolve can still be measuring a
quantity computed wrongly.

## 5. Where it already applies in this repository

- `SELECT_FREE_SP_MODEL_CLAIM` — re-gated onto `eta`/`edf` by ADR-221, which is
  step 3 of this method applied before the method was written down.
- `converged` on the outer REML search — `PROPOSAL_convergence_certificate.md`.
- **Untested, and worth checking against this pattern before it is trusted:**
  the coverage target in `MEASUREMENT_unconditional_coverage.md`. Its nominal is
  `0.95` with a Monte-Carlo standard error of ≈1.54pp at 200 replicates, so
  differences below roughly 3pp are not resolved by that study — a fact that
  bears directly on `PLAN_gam_production_wiring.md`'s slice 4, where readings
  like `0.9586` against `0.7815` are far outside it (safe) but any future
  narrower comparison may not be.

## 6. Verification provenance (ADR-193)

No comparison is published here. Every figure is quoted from a committed ADR-219,
ADR-221, ADR-222 or `MEASUREMENT_unconditional_coverage.md` row, each a
single-producer `MEASUREMENT (own criterion)` reading. **Nothing in this document
is parity evidence.**
