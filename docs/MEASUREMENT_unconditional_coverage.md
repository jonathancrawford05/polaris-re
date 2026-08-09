# Measurement — unconditional coverage of the penalized MI band

**Produced by:** `scripts/unconditional_coverage_study.py` (slice 4, `docs/PLAN_penalized_mi_surface.md`).
**Companion to:** ADR-187's conditional study, and the gate PLAN Anchor 7 sets.

## What this measures, and how it differs from ADR-187

ADR-187 selected λ **once** on a held-out replicate and fit every replicate at it, which is what `Vb` claims — a coverage rate *given* the smoothing parameters. This study selects λ on **every replicate**, because that is the procedure a user runs. Both bands below come from the same fits and differ only in the covariance:

| band | covariance |
|---|---|
| conditional | `Vb = (XᵀWX + S)⁻¹φ` |
| unconditional | `Vb + J V_rho Jᵀ` (Kass–Steffey) |

**Replicates:** 200 (the planned figure). Monte-Carlo SE on a single cell ≈ 1.54pp.
**Nominal level:** 0.95.  **gamma:** 1.0.  **Basis:** `k_age=7`, `k_year=6`.

## Results

| truth | band | overall | young ≤50 | old ≥80 | mean width |
|---|---|---:|---:|---:|---:|
| age-flat | conditional | 0.8201 | 0.8928 | 0.7479 | 0.00619 |
| age-flat | unconditional | 0.8516 | 0.9115 | 0.7930 | 0.00694 |
| age-varying | conditional | 0.8200 | 0.8517 | 0.7456 | 0.00764 |
| age-varying | unconditional | 0.8581 | 0.8843 | 0.7948 | 0.00856 |
| age-flat | *unpenalized delta-method (ADR-187)* | *0.9586* | *0.9574* | *0.9533* | *0.03044* |

The last row is **not** re-measured here — it is quoted from ADR-187, which ran the unpenalized `TensorMIModel(age_df=6, year_df=3)` over the identical truth and the identical replicate seeds (1000..1199). It belongs beside these numbers because it is the estimator the penalized one is proposed to replace, and because it needs no unconditional variant: having no λ, it has no smoothing-parameter uncertainty to leave out.

## Selection behaviour across replicates

| truth | log10 λ_age spread | log10 λ_year spread | replicates with a rejected grid point | mean rejected | max rejected | mean grid points scored | mean floored Hessian directions |
|---|---:|---:|---:|---:|---:|---:|---:|
| age-flat | 5.00 | 5.75 | 1/200 | 0.005 | 1 | 189.2 | 0.460 |
| age-varying | 1.25 | 6.25 | 1/200 | 0.005 | 1 | 197.1 | 0.150 |

The rejected-grid-point columns are the direct evidence for slice 4's first piece: before the fix, **any** replicate in that column would have aborted the whole study (ADR-187 finding 5).

## Anchor 7 verdict

**GATE NOT PASSED** — no interval here may be labelled a 95% band (PLAN Anchor 7). Report the direction and the measured rate instead.

- **age-flat**: unconditional 0.8516 vs floor 0.9192 — FAIL (conditional 0.8201)
- **age-varying**: unconditional 0.8581 vs floor 0.9192 — FAIL (conditional 0.8200)

## Reading this honestly

- A band that reaches nominal by being **very wide** has not become a good band. Read the width column beside the coverage column; the penalized band's claim was always precision, and paying all of it back for calibration is a result, not a success.
- The λ spreads here are measured under **selection per replicate**, so they are the honest version of ADR-187 finding 2 rather than the conditional study's single draw.
- Everything about `J V_rho Jᵀ` is **adopted from `mgcv` and unverified** (PLAN Anchor 8). Slice 5's conformance run against `vcov(m, unconditional = TRUE)` is what converts it.
