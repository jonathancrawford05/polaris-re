# Session log — 2026-08-22 — Wood (2011) `dη/dρ` and `dw/dρ`

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Spec:** `docs/WORK_ORDER_dw_drho_wood2011.md`
**ADR:** ADR-201
**Trigger:** the maintainer supplied a paper to unblock level 4.

## The first finding was about the paper itself

The attachment is **Wood (2011)**, *JRSS-B* 73(1) 3–36 — confirmed from the PDF's
own citation page, not the filename alone. **It is not Wood, Pya & Säfken (2016)**,
which is the paper ADR-190 decision 1 names for `vcov(unconditional = TRUE)`. It is
the same 2011 paper that already resolved ADR-196.

Rather than stop there, I checked whether it nonetheless carries what level 4 needs.
**It does, for the prerequisite:** §3.4 derives `dβ̂/dρ` and `dη/dρ`, Appendix D
derives `dw/dη` and the chain rule to `dw/dρ`, and §3.5.1 uses `∂w/∂ρ` directly —
which is exactly the quantity ADR-190 said "nothing in the fitter currently
computes". **It does not carry the assembly:** zero occurrences of "unconditional"
or `Vc` in the whole paper. It derives these because the REML Newton iteration needs
them, not to build a covariance correction.

So the slice built is the prerequisite. **Level 4 is not closed and this is stated
in the module docstring, the claim's own docstring, the CI report, the ledger, the
ADR and the PR body** — the caveat is placed where a reader will hit it, since
ADR-193's whole lesson is that a caveat in one paragraph does not travel.

## Setup / baseline

- Branched from `main` at `90e65fe` (PR #206 merged). R 4.3.3 / mgcv 1.9.1, the
  expected apt versions, no drift.
- Baseline `tests/test_analytics/`: 1424 passed, 1 failed — the known
  missing-data-file failure, unchanged.

## Gap Before

Slice-specific gap: **no measurement existed.** Nothing in the engine computed
`dβ̂/dρ`, `dη/dρ` or `dw/dρ`; ADR-190 named the absence but never quantified it.

Ten-cell suite, before any change (tier 1): `1 AGREES 2 AGREES 3 AGREES 4 DISAGREES
5 AGREES` — the standing state, with level 4's `rel_unconditional_inflation_diff`
at -3.2209e-01 / -3.3413e-01. Unchanged throughout this session.

## Provenance gate (ADR-193), applied before code

**Claim sentence, written in the work order first:** `gam_derivatives` computes
`dη/dρ` and `dw/dρ` analytically from Wood (2011) §3.4 and Appendix D given a
converged fit over the shared `(X, {Sⱼ})`; `mgcv` computes the same quantities by
**its own refits at perturbed `sp`**, central-differenced; compared on `d_eta_d_rho`
and `dw_drho`.

Mechanical test on the signature: `analytic_derivatives(design, penalties, y,
prior_weights, family, log_lambda)` — shared recipe only, no R payload, no mgcv
output. **INDEPENDENT**, and able to disagree.

**Compared on `dη/dρ`, not `dβ̂/dρ`** — Anchor 2 forbids coefficient agreement as an
acceptance criterion outside Stage A, and `dβ̂/dρ` would have been precisely that
mistake. Caught at design time, before the probe was written.

## Hypotheses Tried

**H1 (registered in advance, work order §3): the canonical cells agree; cloglog may
disagree materially, because Wood's derivation uses the observed (Newton) Hessian
while our fitter uses Fisher weights.**

**HELD.** Measured against a central difference of our own refits — cheap, internal,
before any R round trip: `poisson-log` 6.6e-12, `binomial-logit` 2.7e-11,
**`binomial-cloglog` 6.9e-06**. Six orders of magnitude, exactly where predicted.

**H2: the whole cloglog discrepancy is the missing `α`.** Derived Wood §3.2's `α` in
this codebase's `m ≡ dμ/dη` parameterisation and implemented
`newton_working_weights`. **CONFIRMED, two ways:** `max|α−1|` is 6.7e-16 / 0.0 /
4.3e-03 across the three cells — `α` is identically 1 on the canonical links, which
nothing in the implementation forces, so it independently confirms the algebra — and
using the observed-Hessian weights collapses cloglog from 6.9e-06 to **1.1e-11**,
the same floor as the canonical cells.

**A methodology error I made and corrected.** The first probe used `h ∈ {1e-4,
5e-5}` and reported a Richardson ratio of ~0.6 while claiming "want ~4". That ratio
is not evidence of convergence — at that scale the residual is *round-off* limited,
so halving `h` makes the reference worse. Publishing it would have been a
convergence claim the number did not support. The probe now brackets both regimes:
diffs at the smallest `h` (tightest agreement), the Richardson ratio at the largest
pair (`1e-2`/`5e-3`) where truncation dominates. It is **4.00** on all three cases.

## Gap After

Slice gap **closed on the first measurement after H2**, tier 1 and tier 3 identical
in verdict. Ten-cell suite **unchanged** — no regression, and level 4 is untouched
by construction.

## Oracle Version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt), for iteration.
**Tier 3: R 4.6.1 / mgcv 1.9.4**, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8` (build 8),
run [32586279901](https://github.com/jonathancrawford05/polaris-re/actions/runs/32586279901),
read from job-log stdout via `get_job_logs`.

| case | `d_eta_d_rho` | `dw_drho` | `eta` control | Richardson |
|---|---:|---:|---:|---:|
| `poisson-log` | 5.757e-11 | 1.725e-07 | 8.442e-13 | 4.00 |
| `binomial-logit` | 5.511e-11 | 7.397e-11 | 7.772e-15 | 4.00 |
| `binomial-cloglog` | 5.316e-11 | 5.834e-10 | 8.362e-12 | 4.00 |

## Provenance

| comparison | left producer | right producer | provenance |
|---|---|---|---|
| `d_eta_d_rho` | `gam_derivatives.d_eta_d_rho` (Wood §3.4, analytic, observed-Hessian weights) | central difference of `mgcv`'s own `predict(type="link")` at `ρ ± h` | **INDEPENDENT** |
| `dw_drho` | `gam_derivatives.dw_drho` (Wood App. D, analytic chain rule) | central difference of `mgcv`'s own `m$weights` at `ρ ± h` | **INDEPENDENT** |
| `eta` at base `ρ` | `gam_fit.penalized_irls_general` | `mgcv predict(type="link")` | INDEPENDENT (control, re-confirms ADR-195) |
| `d²μ/dη²`, `dV/dμ`, `dw/dη` vs finite differences | `gam_derivatives` | a difference of `gam_family`'s own functions | **INTERNAL self-consistency — one producer, NOT parity** |
| `dη/dρ` vs a difference of our own refits | `gam_derivatives` | `gam_fit` | **INTERNAL self-consistency — NOT parity** |

The last two rows are labelled explicitly because they are the ones most likely to
be mistaken for evidence about `mgcv`. They are pre-flight checks that catch a sign
or transcription slip cheaply; only the first three say anything about parity.

## Quality gate

- `ruff format` / `ruff check src/ tests/` — clean. (The new modules initially
  tripped 113 `RUF001/002` ambiguous-unicode errors from `ρ`, `α`, `′`, `−`;
  replaced with ASCII, matching what the existing verified modules already do.)
- `mypy` on both new modules — clean. 6 errors were introduced and fixed before
  push, including the same `no-any-return` class PR #206's review caught; the
  untyped `dict` became a `TypedDict`, following `RTermPayload`'s convention.
- `pytest -m "not slow"` — **3356 passed** (+26 new), 22 skipped, same 5
  pre-existing missing-data-file failures, no new ones.
- `pytest tests/qa/` — 85 passed, goldens byte-identical.
- Ten-cell conformance re-run — unchanged.

**All 26 new tests are R-free and run in the GATING pytest job** — PR #206's review
lesson (the conformance workflow runs on PRs but is `continue-on-error` and cannot
fail one) applied from the start rather than after the fact.

## What remains

- **Level 4 itself.** Needs Wood, Pya & Säfken (2016) for the `Vc` assembly,
  re-derived from the paper (ADR-190 decision 3 — `mgcv` is GPL, this project MIT).
  The prerequisite is now in place and verified, so that slice starts from a
  measured ingredient rather than an absent one.
- **N > 2 penalty blocks.** Same limitation ADR-199 records: written generally,
  exercised only at two blocks.
