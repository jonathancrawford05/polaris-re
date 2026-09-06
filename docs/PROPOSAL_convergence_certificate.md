# Proposal: a convergence certificate for the outer REML search

> **STATUS: PROPOSED. It binds nothing.** Adopting it means an ADR, because it
> defines an acceptance criterion and that is `ROUTINE_MGCV_PARITY.md`'s
> "May not decide". Written in response to maintainer direction, 2026-09-05:
> *"We've previously discussed how convergence depends on properties of the
> manifold traversed. Surely there are well established programmatic approaches
> to defining reliably 'convergent' — can you propose a solution?"*

**Source of the requirement**, maintainer 2026-09-05: convergence is *"a
property that leads to a result that is reproducible to within a stated
tolerance. The tolerance should be meaningful in context. Ideally, convergence
is guaranteed by the robustness of our algorithm to identify minimum/maximum
points on a well behaved manifold."*

---

## 1. Why the obvious approaches both failed

Two were tried and measured in slice 7f (ADR-222). Neither is salvageable by
picking a better number.

**SciPy's `success` flag** reports that L-BFGS-B's `ftol` test fired. Slice 7f
showed that exit is **state-governed, not threshold-governed**: `factr` at
`1e7`, `1e2` and `1.0` — seven orders — all produce identical `nfev = 42` and
score `524.788031`, while a plain re-entry from the same point at the *same*
`factr` improves the score by `1.110350`. The flag reports something true about
the optimiser's internal state and nothing about optimality.

**A `gtol` test on the projected gradient** was built, measured and reverted.
The well-conditioned N=4 control plateaus at `2.040e-04` while being optimal to
`1e-6`; the bound-active N=7 case plateaus at `4.9e-01`. `gtol = 1e-8` is below
what this objective resolves at all. **Any absolute threshold between the two
measured plateaus is an arbitrary number**, which is exactly why it was
escalated rather than chosen.

**The diagnosis.** Both approaches ask a single scalar question of a problem
whose difficulty is not scalar. The N=4 plateau and the N=7 plateau are not the
same phenomenon measured at different sizes — one is a **flat direction** (no
optimum exists to find), the other is a **blocked search** (an optimum exists
and was not reached). A test that cannot tell them apart will misclassify one of
them at every threshold.

## 2. What is well established

Four standard practices, each addressing one of the failures above.

**(a) Scale the first-order test; never test an absolute gradient norm.**
Absolute norms are not comparable across problems or parameterisations. Standard
forms are `||P∇f||∞ ≤ ε·(1 + |f|)` or normalisation by multiplier magnitude
(IPOPT's scaled optimality error `E_μ`, KNITRO's relative stopping test).
L-BFGS-B's own `pgtol` is **absolute**, which is the direct cause of §1's
second failure.

**(b) Certify second order, not just first.** A small gradient is consistent
with a saddle, a plateau, or a stalled line search. The textbook sufficient
condition (Nocedal & Wright ch. 12; Conn–Gould–Toint) is stationarity **plus**
a positive-definite reduced Hessian on the free variables — the variables not
pinned at a bound. This is the formal content of the maintainer's "minimum
points on a well behaved manifold".

**(c) Derive tolerances from the objective's measured noise.** When `f` carries
evaluation noise `ε_f`, no algorithm can certify a gradient below the level
`ε_f` implies — for central differences the achievable accuracy scales like
`sqrt(ε_f/h)`. The established move is to *estimate* `ε_f` and *derive* the
tolerance (Moré & Wild 2011, "Estimating computational noise"; the noise-tolerant
tests in Berahas–Byrd–Nocedal). **This is what turns a chosen constant into a
measured one**, and it is the direct answer to "the tolerance should be
meaningful in context".

**(d) How `mgcv` actually gets reliability** (Wood 2011 §3–4, `mgcv:::newton`).
Full Newton on the outer criterion with exact first *and* second derivatives by
implicit differentiation; **the Hessian perturbed to positive definite when it
is not**; step-length control; and convergence tested on a *relative* criterion
change together with a scaled gradient. Note what is absent: **no random
multistart.** `mgcv`'s bit-identical reproducibility is a consequence of
determinism plus a well-conditioned criterion — it is architectural, not a
property its convergence test measures.

## 3. The proposal

**Replace the boolean with a certificate** — a structured result computed once
at the end of a fit, on request.

### Part 1 — measure the noise floor `ε_f`

Evaluate the REML score under perturbations that are mathematically no-ops but
numerically distinct (BLAS thread count is the one this epic already uses;
summation reordering is equivalent). The spread is `ε_f`.

Already measured: **`~1e-4` today, `~1e-13` after slice 7h.** Everything below
is scaled by this number, so the certificate reports it rather than assuming it.

### Part 2 — stationarity, scaled and restricted to *identified* directions

- Take the KKT residual under box bounds from `projected_gradient`
  (`gam_reml_optimize`, shipped in slice 7f).
- **Restrict it to the identified subspace.** Eigendecompose the REML-score
  Hessian w.r.t. `rho` and drop the directions whose curvature falls below the
  noise-derived floor. In such a direction the objective is flat to within what
  can be measured, so *every* point is optimal and demanding a small gradient
  component is a category error. Machinery already exists:
  `gam_sp_identifiability` (slice 7c) and
  `gam_uncertainty_conformance.finite_difference_rho_hessian` — slice 7c already
  measured **5 identified directions of 7** on this structure.
- Test the restricted residual **relatively**: `||P g|ᵢd||∞ / (1 + |score|)`.

**This is what dissolves §1's arbitrary threshold.** The N=4 plateau at
`2.040e-04` is a flat-direction artefact and the N=7 plateau at `4.9e-01` is a
blocked search. Restricting to identified directions separates them on a
principle instead of on a number chosen to sit between them.

### Part 3 — second-order sufficiency on that same subspace

The reduced Hessian, restricted to directions that are both **free** (not pinned
at a bound) and **identified**, must be positive definite with its smallest
eigenvalue above the curvature floor. This is (b), and it is the operational
form of "well behaved manifold".

### The verdict is not boolean

| verdict | meaning |
|---|---|
| `CONVERGED` | stationary and positively curved on every identified direction; `ε_f` small enough to certify it |
| `CONVERGED_ON_IDENTIFIED_SUBSPACE` | optimal in every direction that *has* an optimum; `k` directions flat to noise. **The honest reading of the N=4 control.** |
| `NOT_CONVERGED` | a direction with real curvature still carries gradient above the derived threshold. **The N=7 bound-active case.** |
| `UNCERTIFIABLE` | `ε_f` exceeds what the test needs. **The engine's state before slice 7h** — a true statement about the engine, not a failure of the fit. |

## 4. What this does and does not deliver

**Delivers.** A tolerance that is *derived from measurement* rather than chosen;
a test that distinguishes "the algorithm failed" from "the problem has no unique
answer in this direction"; and a verdict that degrades honestly instead of
reporting `False` for a fit optimal to `1e-6`.

**Does not deliver reproducibility.** A certificate measures one fit's
optimality. Reproducibility comes from (i) a stable criterion — **slice 7h** —
and (ii) a deterministic solver — **slice 8**, i.e. Wood's Newton without random
multistart. This must be stated plainly because the maintainer's definition
names reproducibility: **no flag can create it.** `mgcv` is bit-identical because
it is deterministic, not because it tests for it. The certificate's role is to
report `ε_f` so a caller can see whether reproducibility is even achievable.

## 5. Cost, and staging

**Cost is real** — the maintainer already anticipated it ("converged may become
expensive"). A central-difference Hessian at N=7 is `O(N²)` score evaluations,
each a full penalized IRLS fit: order 100 fits. Mitigations: compute it **only
on request** (`certify=True`, never in the default path), and note that after
slice 8 the Hessian is computed anyway for the Newton step, making Part 3
close to free and exact rather than finite-difference.

| stage | depends on | what lands |
|---|---|---|
| now | nothing | report the **scaled relative** stationarity beside the existing absolute `max_abs_projected_gradient`. No flag changes. |
| after **7h** | stable criterion | `ε_f` drops ~9 orders, so a derived tolerance can certify something. Certificate becomes computable. |
| after **slice 8** | analytic 2nd derivatives, deterministic solver | Part 3 exact and cheap; reproducibility by construction; `converged` can finally be re-pointed at the certificate. |

## 6. What is still the maintainer's to decide

The proposal **reduces** the decision but does not remove it. Two numbers remain,
and both are acceptance criteria:

1. **The relative stationarity tolerance** `ε_rel` (e.g. `1e-6` relative).
2. **The curvature-to-noise ratio** that defines "identified".

These are portable, defensible quantities — unlike "a number between `2.0e-04`
and `4.9e-01`", which was the choice on offer before. **Recommendation:** do not
decide them now. Both should be set against measurements taken *after* slice 7h,
because `ε_f` moves nine orders and every derived threshold moves with it.

**The deferral is made safe by a committed criterion, not by a note.** Slice 7h's
DoD now requires `ε_f` be recorded before *and* after the fix
(`PLAN_mgcv_parity_engine.md`), because 7h is the slice that moves it and
therefore the only natural moment to capture it. Without that, this decision
would be deferred a second time for want of a measurement, and someone would
have to re-run 7h's own before/after to recover it. Both numbers are also
carried in `PRODUCT_DIRECTION_2026-07-24.md` so they survive independently of
this document.

**The general method behind this section** — measure the noise floor, identify
what carries signal above it, state the tolerance relatively on that subspace,
and report unresolvability rather than widening — is written up separately as
`docs/PATTERN_resolvable_tolerances.md` (PROPOSED), which records the two
independent instances in this epic that produced it.

## 7. Verification provenance (ADR-193)

This document publishes **no comparison**. The figures it cites (`2.040e-04`,
`4.9e-01`, `1.037e-04 → 1.954e-13`, "5 identified directions of 7") are quoted
from committed ADR-222 and ADR-219 rows, all of them single-producer
`MEASUREMENT (own criterion)` readings. The `mgcv` references in §2(d) describe
*its published algorithm* and its self-consistency across environments — which
ADR-222 classes `MEASUREMENT (external reference, self-consistency)`. **Nothing
here is parity evidence and none of it may be cited as such.**
