# Work order — from conformance harness to production path (`PolarisGAM`)

**Status:** **DONE, 2026-08-25** (ADR-208, tier 1 AND tier 3 both confirmed, CI
run 32855338611). `PolarisGAM` exists
(`src/polaris_re/analytics/gam_model.py`), fits the three-term `cr`+`by`+`ti`
model from a `ModelSpec`, and selects its own smoothing parameters. The §4
registered prediction below is **REFUTED at both tiers**. **The original
diagnosis (a flat REML surface, no criterion gap) was corrected same-day, PR
#212 review [P1]:** the discriminating measurement the review named shows
`mgcv`'s own score and ours RANK `mgcv`'s point and Python's point in
OPPOSITE order — evidence of an `sp`-dependent criterion discrepancy at this
N=4 / `ti()`-sharing-a-span structure, **CONFIRMED at tier 3 same day** (CI
run 32874213883, identical to tier 1 at every printed digit). Slice 6 remains
blocked until this is localised or closed. See ADR-208's amendment and
`docs/CONFORMANCE_LEDGER.md`. This
document is kept as the specification that was executed, not rewritten in the
past tense throughout; §7's Definition of Done states what was and was not met.

Registered as **PLAN slice 5b** so the routine's "next unchecked slice" rule could
reach it. Registering it in the ordered list is not the same as designating it for
a session — that remained a `ROUTINE_MGCV_PARITY.md` call (ADR-207 decision 4).
Before 2026-08-25 this work order sat outside the slice list entirely, which meant
the routine's selection rule would have walked past it to slice 6 no matter how
ready it was.
**Predecessors:** ADR-206 (the multi-term assembly, built and Stage-B verified),
ADR-207 (the Anchor 7 amendment that permits a production path).
**Rewritten 2026-08-24** after ADR-206 landed. The first version of this work
order asked for the assembler. **It exists.** What is left is narrower and
better defined — read §1 before assuming otherwise.

---

## 1. What exists, and the exact gap

ADR-206 built and tier-3-verified the assembly:
`gam_multiterm_conformance.assemble_multiterm_design` fits three of the target's
eight terms together — reference age, the numeric-`by` MI term, `ti()` — and
agrees with `mgcv` on `eta` at `1.242e-10` on the first measurement. That is the
epic's first Stage-B multi-term result and it is not in question here.

**Two things make it a harness rather than an engine, and both are narrow:**

| | today | needed |
|---|---|---|
| model definition | `RMultiTermRecipe` — an R script's JSON payload | `ModelSpec`, which already exists and already declares family / link / terms / weights / offset |
| smoothing parameters | fixed, externally supplied | selected, via `select_lambdas_continuous` — already verified, already takes arbitrary N blocks |

So it cannot fit a model `mgcv` has not already defined, and it does not choose
its own λ. Everything else — the bases, the fitter, the criterion, the search,
the covariance — is tier-3 verified and stays exactly as it is.

**This is not a criticism of ADR-206.** Under the unamended Anchor 7 a harness
was the only available framing: there was no production path a component was
permitted to belong to. ADR-207 removed that constraint, hours later. The work
here is to re-drive verified code from a different input, not to write new
numerics.

## 2. Scope

**In:**

- `analytics/gam_model.py` — `PolarisGAM`, taking `ModelSpec` + a dataframe.
- Design and penalty assembly **reusing ADR-206's logic**. If that means
  extracting `assemble_multiterm_design`'s body into a shared function that both
  the harness and the engine call, do that — do not fork it.
- λ via `select_lambdas_continuous`; fit via `penalized_irls_general`;
  covariance via `unconditional_covariance`.
- A conformance case at **free `sp`**, which is the genuinely new measurement:
  ADR-206 compared at fixed `sp`, so our own selection has never been exercised
  on a multi-term design.

**Out:**

- `bs = "sz"` (slice 6) and `select = TRUE` (slice 7) — unbuilt, so the full
  8-term target still cannot be fitted. Three terms is the honest scope.
- Re-pointing any existing caller (ADR-207 decision 3: no swap, ever).
- Touching `experience_gam_penalized` or `experience_gam`.
- Re-deriving any basis, fitter, criterion or search. If this work starts
  producing new numerics, stop — that is a sign the reuse in §2 was skipped.

## 3. What to compare

Per PLAN Anchor 2, **never compare coefficients**. ADR-206 established the
Stage-B precedent; extend it to free `sp`:

| quantity | why |
|---|---|
| `eta` element-wise | ADR-206's metric; the direct extension |
| selected `log10(sp)` per block | **the new one** — first exercise of our λ selection at N=4 |
| `edf_total` and per-term `edf` | `mgcv`'s own headline diagnostic |

Declare these in a `VerificationClaim` before writing the comparison (ADR-193,
`docs/VERIFICATION_STANDARD.md`). Note the asymmetry: `mgcv`'s `sp` was a
**shared input** to ADR-206 and becomes a **compared quantity** here. That
changes the provenance classification, and the claim must say so.

## 4. The registered prediction

> The assembly is already verified at fixed `sp`, so a disagreement at free `sp`
> localises to **λ selection on a multi-term design** — not to the bases, the
> fitter or the criterion. ADR-199 measured `select_lambdas_continuous` against
> `mgcv` at 6.9e-04 to 9.8e-04 on 2-block designs; the prediction is that N=4
> lands in the same range.
>
> If it does not, the 2-block result was narrower than it appeared — the search
> may scale differently with block count — and **that** is the finding.

Register it before running. ADR-190 decision 4 is the precedent; ADR-203 is the
reminder that a prediction must be registered against a *re-measurement*, never
against a stored number.

## 5. Sequencing

1. **Extract the shared assembly** so the harness and the engine cannot drift.
   ADR-206's tests must still pass unchanged — that is the check that the
   extraction was behaviour-preserving.
2. **`PolarisGAM` from `ModelSpec`**, R-free tests: block widths sum to `p`,
   penalties land in the right spans, a `by` term is unconstrained (ADR-200), a
   plain `cr` term is constrained, `ti` margins carry their own (ADR-205).
   Mutation-test each.
3. **Free-`sp` conformance**, tier 1 then tier 3 per `ROUTINE_MGCV_PARITY.md`
   SETUP step 2. **Only tier-3 numbers may be committed.**
4. **Ledger rows at both tiers + an ADR.**

Steps 1-2 are R-free and land independently of any oracle. **That is a statement about
those two steps, not about the slice.** Parity is claimed at step 3 and nowhere else, it is
measured against `mgcv`, and only a tier-3 number may be committed — so the oracle is
required for every claim this slice exists to make. What "R-free" buys is narrower: steps
1-2 assert *internal* structure (widths sum to `p`, penalties land in the right spans, a
`by` term is unconstrained, `ti` margins carry their own), which is checkable without
`mgcv` because it is our own invariant rather than an agreement. So an oracle outage delays
the measurement without idling the session. **A slice that stopped after step 2 would have
built the engine and verified nothing about parity** — steps 1-2 are the thing being
measured, never the measurement.

## 6. Two traps already paid for

- **A scalar summary is not an element-wise check.** ADR-202 read 0.39% on an
  inflation ratio while the element-wise residual was 26.7%. Report max absolute
  difference, not a mean.
- **Do not hand-replicate `mgcv` reparameterisations from its source.** ADR-205's
  hand-replica of `ti()` was out by 182 in `X` until instrumenting
  `mgcv:::smooth.construct.tensor.smooth.spec` found that `cr` sets `noterp`.
  Instrument, then re-derive — transcription is barred by licensing anyway.

## 7. Definition of done

- [x] `PolarisGAM` fits a three-term `cr` + `by` + `ti` model from a `ModelSpec`,
  selecting its own λ. (`gam_model.fit_polaris_gam`)
- [x] Free-`sp` conformance at **tier 1 AND tier 3**, with a `VerificationClaim`
  (`FREE_SP_MODEL_CLAIM`) classifying each compared quantity, and `sp`'s move
  from shared input to compared quantity stated explicitly (module docstring,
  ADR-208). Tier 3 confirmed identical in verdict, CI run 32855338611 — see
  ADR-208's confirmation amendment for the digest and full numbers.
- [x] The §4 prediction resolved in those words — **REFUTED**. First
  diagnosis (a flat REML surface, no criterion gap) was corrected same-day
  (PR #212 review [P1]): the discriminating measurement shows `mgcv`'s own
  criterion and ours rank the two candidate points in OPPOSITE order — real
  evidence of an `sp`-dependent criterion discrepancy at this term
  structure, not merely optimiser path-sensitivity. **CONFIRMED at tier 3,
  same day** (CI run 32874213883, identical to tier 1). See ADR-208's
  amendment.
- [x] ADR-206's tests pass unchanged, proving the extraction preserved behaviour
  (`tests/test_analytics/test_gam_multiterm_conformance.py`, unmodified).
- [x] `experience_gam_penalized` and `experience_gam` untouched; `tests/qa/`
  goldens byte-identical (neither file changed in this slice's diff).
