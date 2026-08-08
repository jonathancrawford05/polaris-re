# Dev session log — 2026-08-08 — penalized MI surface, slice 1

**Branch:** `claude/quirky-ramanujan-5zhsw3` (reset onto `main` @ `97b203f` after PR #186 merged)
**Epic:** `PLAN_penalized_mi_surface.md` — slice 1 of 5
**ADR:** ADR-185

## Baseline and end state

| | |
|---|---|
| Baseline (`main` @ `97b203f`) | 3068 passed, 3 skipped, 125 deselected |
| `tests/test_analytics/` after slice 1 | 1211 passed, 2 skipped, +11 new |
| ruff | clean (`src/`, `tests/`) |
| perf row | `peak_mib` 33 (Δ+0), fingerprint `8331a13f7ce7` **unchanged**, best-of-5 0.0858 s |
| `tests/qa/` goldens | untouched — nothing in `products/` moves |

Known flake seen once in the analytics run: `test_scaling_is_near_linear`, the
wall-clock ratio gate already logged in PRODUCT_DIRECTION. Passes in isolation and
is off this path.

## What shipped

`src/polaris_re/analytics/experience_gam_penalized.py` — marginal B-spline bases, a
row-wise Kronecker tensor design, Eilers-Marx second-difference penalties lifted as
`DᵀD ⊗ I` / `I ⊗ DᵀD`, penalized IRLS, Bayesian covariance and `edf = tr(H)`. Fixed
λ only; selection is slice 2.

## The two things the plan had wrong

**1. patsy cannot build a P-spline basis.** The plan's route to Anchor 1 — a
Kronecker design spanning patsy's column space — works for the *span* (fitted values
agree to 6.4e-15) but the difference penalty over that basis does not annihilate
linear trends, because patsy always clamps boundary knots. Measured 5.6e-01 against
8.9e-16 on a properly extended uniform sequence. The symptom was the λ→∞ limit
retaining a 3.0-point span instead of collapsing to constant. Two knot schemes now
ship, and **Anchor 1 is amended**: it holds in the clamped scheme, which is the
oracle-testing mode, not the production one.

**2. IRLS must converge on deviance.** At λ=1e12 the coefficients rattle at
round-off in the penalised directions forever while the deviance settles within 8
iterations. `max|Δβ|` never trips. Deviance is also the quantity being optimised, so
this is the right criterion rather than a workaround.

Both were found by writing the tests the plan specified, which is the argument for
specifying them before the code.

## Next

Slice 2 — REML λ selection, and Anchor 3's determinism problem. The plan's warning
that an optimiser threatens byte-stability harder than BLAS jitter now has a second
reason behind it: slice 1 showed the penalised directions are exactly where
numerical noise lives.
