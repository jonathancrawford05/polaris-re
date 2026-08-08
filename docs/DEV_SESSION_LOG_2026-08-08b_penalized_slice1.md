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

## Review response (PR #187)

The automated review returned **one P0 and three P1s**, and the P0 is the one worth
recording: `_margin_edf`'s `axis` argument was **inert**. `diag.sum(axis=1-axis).sum()`
collapses to the grand total whichever axis goes first, so `edf_age == edf_year`
always, and at a saturating calendar penalty `edf_year` still read 14.0 while that
margin had provably collapsed to a 2-dimensional null space.

**Eleven tests passed over it, because every one asserted on `edf_total`.** The two
tests that would have caught it both had the fitted object in hand.

The reviewer's diagnosis of *how* it shipped is the part to keep: I wrote a caveat
saying the split was "descriptive, not orthogonal", and that caveat was composed
from what the code was *meant* to do rather than from what it did. It was also
strictly too generous — the fields were not imprecise, they were identical — so it
would have reassured a reader out of checking. **Writing the limitation substituted
for testing it.** That is a failure mode worth naming because it looks like
diligence from the outside.

Replaced with a definition — `edf_j = tr(H) − tr(H | λⱼ = ∞)` — and two guards
parametrised in both directions, for the same reason the penalty transposition guard
is: a quantity that responds correctly to one margin can still be reading the wrong
one.

Also fixed: the clamped path let patsy recompute knots on a prediction grid (silent
on a complete rectangle, wrong by 3.2e-2 on ragged coverage, and slices 2-3 use that
path as their oracle); IRLS returned pre-update weights; and the plan-specified
isotropy test had been dropped without a line recording it — the exact silent
omission the PLAN/CONTINUATION contract exists to catch. The CONTINUATION was also
still carrying the *un-amended* Anchor 1, which would have started slice 2 from the
premise slice 1 spent its effort falsifying.

## Next

Slice 2 — REML λ selection, and Anchor 3's determinism problem. The plan's warning
that an optimiser threatens byte-stability harder than BLAS jitter now has a second
reason behind it: slice 1 showed the penalised directions are exactly where
numerical noise lives.
