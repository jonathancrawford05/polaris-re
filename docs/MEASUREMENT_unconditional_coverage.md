# Measurement — unconditional coverage of the penalized MI band

**Produced by:** `scripts/unconditional_coverage_study.py` (slice 4, `docs/PLAN_penalized_mi_surface.md`).
**Companion to:** ADR-187's conditional study, and the gate PLAN Anchor 7 sets.

## What this measures, and how it differs from ADR-187

ADR-187 selected λ **once** on a held-out replicate and fit every replicate at it, which is what `Vb` claims — a coverage rate *given* the smoothing parameters. This study selects λ on **every replicate**, because that is the procedure a user runs. All four bands below come from the same fits and differ only in the covariance:

| band | covariance | `J` from |
|---|---|---|
| conditional | `Vb = (XᵀWX + S)⁻¹φ` | — |
| unconditional | `Vb + J V_rho Jᵀ` (Kass-Steffey) — **the shipped band** | central differences |
| ks-analytic | `Vb + J V_rho Jᵀ`, same formula | Wood (2011) 3.4, analytic |
| wps2016 | `Vb + V' + V''` — Wood, Pya & Saefken (2016) eq. (7) | Wood (2011) 3.4, analytic |

**The last two rows separate the two mechanisms** that re-pointing production would change at once. `ks-analytic` differs from `unconditional` only in how `J` is obtained, and from `wps2016` only in the missing `V''`. Without it a coverage movement could not be attributed to the formula rather than to the derivative method — and only the formula is what ADR-202 verified against `mgcv`.

**No production path changed to produce this** (PLAN Anchor 7). `experience_gam_penalized` is untouched; the two new bands come from `polaris_re.analytics.gam_uncertainty_mi.wps_correction`, which reads a fit that module produced and returns a covariance beside it.

**Replicates:** 200 (the planned figure). Monte-Carlo SE on a single cell ≈ 1.54pp.
**Nominal level:** 0.95.  **gamma:** 1.0.  **Basis:** `k_age=7`, `k_year=6`.

## Results

| truth | band | overall | young ≤50 | old ≥80 | mean width |
|---|---|---:|---:|---:|---:|
| age-flat | conditional | 0.7435 | 0.8571 | 0.6256 | 0.00550 |
| age-flat | unconditional | 0.7815 | 0.8783 | 0.6821 | 0.00618 |
| age-flat | ks-analytic | 0.7818 | 0.8780 | 0.6829 | 0.00619 |
| age-flat | wps2016 | 0.8167 | 0.9065 | 0.7145 | 0.00704 |
| age-varying | conditional | 0.7781 | 0.8843 | 0.6263 | 0.00745 |
| age-varying | unconditional | 0.8090 | 0.8993 | 0.6823 | 0.00814 |
| age-varying | ks-analytic | 0.8091 | 0.8992 | 0.6829 | 0.00814 |
| age-varying | wps2016 | 0.8354 | 0.9188 | 0.7165 | 0.00893 |
| age-flat | *unpenalized delta-method (ADR-187)* | *0.9586* | *0.9574* | *0.9533* | *0.03044* |

The last row is **not** re-measured here — it is quoted from ADR-187, which ran the unpenalized `TensorMIModel(age_df=6, year_df=3)` over the identical truth and the identical replicate seeds (1000..1199). It belongs beside these numbers because it is the estimator the penalized one is proposed to replace, and because it needs no unconditional variant: having no λ, it has no smoothing-parameter uncertainty to leave out.

## This supersedes the 2026-08-09 edition, and not because the study changed

| truth | conditional, then -> now | unconditional, then -> now |
|---|---|---|
| age-flat | 0.8201 -> 0.7435 | 0.8516 -> 0.7815 |
| age-varying | 0.8200 -> 0.7781 | 0.8581 -> 0.8090 |

`ce0b9f1` (2026-08-19) added Wood (2011) eq. (4)'s penalized-deviance term to `experience_gam_penalized.reml_score` — the maintainer-authorized ADR-197 fix. It is **correct**: ADR-197's resolution verified the criterion bit-for-bit against `gam_reml.reml_score_general` and moved conformance level 5 from DISAGREES to AGREES. But a different REML criterion selects a different λ on every replicate, so coverage moved with it — measured at -0.0432 / -0.0410 on the age-flat truth by restoring the pre-fix criterion under monkeypatch and re-running the identical seeds.

**The shipped band's real baseline was therefore ~0.78, not ~0.85, for four days before this run.** Every document that cited 0.8516 / 0.8581 as the current state of the gate — including ADR-190 decision 4, whose registered prediction is resolved below — was quoting a superseded number. Nothing re-runs this study in CI or the `Makefile`, which is why the drift was silent and why this section now ships with the report.

## How much each correction inflates the variance

Mean coefficient-variance inflation over replicates, `mean(diag(Vb + C)) / mean(diag(Vb))`. ADR-190 measured the *size* of the gap against `mgcv` (3.2-4.1x on the correction term) on the conformance fixtures; this is the same quantity on the production path, so a coverage change with no inflation change would mean the two studies are not looking at the same object.

| truth | unconditional | ks-analytic | wps2016 | eq. (7) correction vs Kass-Steffey | floored Hessian directions |
|---|---:|---:|---:|---:|---:|
| age-flat | 1.2285x | 1.2294x | 1.6324x | 2.76x | 1.025 |
| age-varying | 1.1023x | 1.1022x | 1.3207x | 3.14x | 0.390 |

The `unconditional` and `ks-analytic` columns are the **same formula** taken two different ways, so the gap between them is the entire cost of the derivative-method change — mechanism 2. The gap between `ks-analytic` and `wps2016` is mechanism 1, the `V''` term.

## ADR-190 decision 4's registered prediction

**CONFIRMED IN DIRECTION, REFUTED IN SUFFICIENCY** — eq. (7) moves coverage upward on every truth, which is what ADR-190 decision 4 registered, so decision 1's diagnosis was pointing at something real. But the gate still fails by up to 0.1025, so the formula was **a** gap and not **the** gap. ADR-190 decision 4's contingency therefore applies in substance even though its literal trigger did not fire: a second cause remains, and closing it is not a covariance problem eq. (7) can reach. **Coverage is not a reason to re-point production** — mgcv parity (ADR-202) is the case for that, and it is a different case.

- **age-flat**: 0.7815 -> 0.8167 (+0.0352), floor 0.9192; correction inflation 1.2285x -> 1.6324x
- **age-varying**: 0.8090 -> 0.8354 (+0.0264), floor 0.9192; correction inflation 1.1023x -> 1.3207x

## Selection behaviour across replicates

| truth | log10 λ_age spread | log10 λ_year spread | replicates with a rejected grid point | mean rejected | max rejected | mean grid points scored | mean floored Hessian directions |
|---|---:|---:|---:|---:|---:|---:|---:|
| age-flat | 5.25 | 5.50 | 1/200 | 0.005 | 1 | 172.6 | 1.025 |
| age-varying | 1.25 | 5.75 | 1/200 | 0.005 | 1 | 189.8 | 0.390 |

The rejected-grid-point columns are the direct evidence for slice 4's first piece: before the fix, **any** replicate in that column would have aborted the whole study (ADR-187 finding 5).

## Anchor 7 verdict

**GATE NOT PASSED** — no interval here may be labelled a 95% band (PLAN Anchor 7). Report the direction and the measured rate instead.

- **age-flat**: wps2016 0.8167 vs floor 0.9192 — FAIL (shipped Kass-Steffey 0.7815, conditional 0.7435)
- **age-varying**: wps2016 0.8354 vs floor 0.9192 — FAIL (shipped Kass-Steffey 0.8090, conditional 0.7781)

## Reading this honestly

- A band that reaches nominal by being **very wide** has not become a good band. Read the width column beside the coverage column; the penalized band's claim was always precision, and paying all of it back for calibration is a result, not a success.
- The λ spreads here are measured under **selection per replicate**, so they are the honest version of ADR-187 finding 2 rather than the conditional study's single draw.
- **The shipped `unconditional` band was REFUTED against `mgcv`, and still is.** Level 4 measured it inflating the mean variance 1.11-1.21x where `mgcv` inflates 1.49-1.87x, in the same direction on every cell (ADR-189 amendment 1, ADR-190). It is tabulated above because it is what production ships, not because it is verified — and the ten-cell suite still reads `level 4: DISAGREES` on it, correctly. This sentence was missing between 2026-08-23's first and second editions of this report, which left the document's only verification status attached to a band production does not use (PR #207 review [P1]).
- The `wps2016` covariance is **verified against `mgcv`**, not adopted from it: ADR-202 measured `unconditional_covariance` against `vcov(m, unconditional = TRUE)` on the tier-3 pinned oracle at 0.023-0.904% element-wise. That is what PLAN Anchor 8 asked for, and it is why the adopted-and-unverified caveat that stood here until 2026-08-23 is gone.
- **`mgcv` parity and coverage are different claims.** The row above says this band is the same object `mgcv` computes. It does not say that object is well-calibrated — that is what the coverage column measures, and the two could in principle disagree. Read them as two facts, not one.
