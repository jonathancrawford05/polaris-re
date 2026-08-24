# Work order — the multi-term assembler (`PolarisGAM`)

**Status:** READY. Not yet a designated slice — that is a
`ROUTINE_MGCV_PARITY.md` call (ADR-206 decision 4).
**Predecessor:** ADR-206 (the Anchor 7 amendment this depends on).
**Blocks:** slice 2 Stage B, slice 5 Stage B, slice 4 part B above N=2, PLAN
Anchor 5's weights/offset comparison.

---

## 1. Why this is one function, not a project

`ModelSpec` already declares family, link, terms, weights column and offset
column. `select_lambdas_continuous` already accepts
`penalty_blocks: tuple[np.ndarray, ...]` — arbitrary N, by construction.
`penalized_irls_general` already fits any family/link with prior weights and an
offset. `unconditional_covariance` already forms the corrected covariance.

Every one of those is verified INDEPENDENT at tier 3.

**The gap is `ModelSpec + data -> (design, penalty_blocks)`** — build each term's
block with the basis function already verified for it, concatenate, and place
each penalty into a full-width `(p, p)` block. That is the whole missing piece.

Do not let it grow. If it starts to acquire a fitting rule, a scoring rule or a
constraint rule of its own, stop: those live in modules that are already
verified, and re-deriving one here silently creates a second implementation of a
thing this epic spent five slices proving.

## 2. Scope

**In:**

- `analytics/gam_model.py` — the assembler plus a `PolarisGAMFit` result.
- Terms: `cr` (verified ADR-194), `ti` (ADR-205), numeric-`by` (ADR-200), and
  parametric/factor columns.
- Fitting via `penalized_irls_general`; λ via `select_lambdas_continuous`;
  covariance via `unconditional_covariance`.
- A Stage-B conformance case against a **real multi-term `mgcv::gam()`**.

**Out:**

- `bs = "sz"` (slice 6) and `select = TRUE` (slice 7) — not built, so the full
  8-term target cannot be fitted yet. Fit the `cr` + `ti` + `by` subset and say
  so.
- Re-pointing any existing caller. ADR-206 decision 3: no swap, ever. Callers
  migrate later, on measured evidence, as separate work.
- Touching `experience_gam_penalized` or `experience_gam` at all.

## 3. What to compare, and what not to

Per PLAN Anchor 2, **never compare coefficients**. The Stage-B acceptance
criteria are the basis-invariant quantities:

| quantity | why it is the right one |
|---|---|
| `eta` (linear predictor) | invariant to basis parameterisation; the thing the model actually predicts |
| `edf_total` and per-term `edf` | `mgcv`'s own headline diagnostic; already verified for the legacy engine to 7.2e-13 (ADR-189 am. 1) |
| selected `log10(sp)` per block | the slice-4B claim, now at N > 2 for the first time |
| `dispersion` where `mgcv` estimates it | the ADR-195 precedent |

Declare these in a `VerificationClaim` before writing the comparison, per ADR-193
and `docs/VERIFICATION_STANDARD.md`. The shared recipe is the data, the term
specs and the knots. **`mgcv`'s selected `sp` is a shared input only if you are
comparing something other than `sp`** — comparing our λ against theirs requires
that we select our own, which is the point of including it above.

## 4. The registered prediction (write the outcome down before running)

> Assembly is the only unverified step. Every component is tier-3 verified in
> isolation, so a Stage-B disagreement localises to the assembler — block
> ordering, penalty placement, constraint absorption, or the weights/offset
> wiring — and **not** to the basis, the fitter, the criterion or the search.
>
> If a disagreement instead traces to a component, that component's existing
> tier-3 result was narrower than it appeared, and *that* is the finding.

Recording this in advance is what makes the run informative either way. ADR-190
decision 4 is the precedent, and ADR-203 is the reminder that a prediction must
be registered against a *re-measurement*, never against a stored number.

## 5. Sequencing

1. **Assembler + R-free tests.** Block widths sum to `p`; each penalty lands in
   the right span; a `by` term is unconstrained (ADR-200) while a plain `cr` term
   is constrained; `ti` margins carry their own constraint (ADR-205). Mutation
   test each — a penalty placed in the wrong block should fail something.
2. **Fit on synthetic data**, no `mgcv`. Assert only what is checkable without a
   reference: convergence, the EDF identity `edf_total == sum(per-term edf)`,
   determinism (ADR-074).
3. **Stage B against `mgcv`**, tier 1 first, then tier 3 per `ROUTINE_MGCV_PARITY.md`
   SETUP step 2. **Only tier-3 numbers may be committed.**
4. **Ledger row + ADR.** Both tiers, with the provenance classification.

Steps 1-2 are R-free and land independently of any oracle. If step 3 disagrees,
steps 1-2 still stand and the disagreement is the result.

## 6. Two traps this epic has already paid for

- **A scalar summary is not an element-wise check.** ADR-202 read 0.39% on an
  inflation ratio while the element-wise residual was 26.7%. Compare `eta`
  element-wise, and report the max absolute difference, not a mean.
- **Do not re-implement `mgcv`'s reparameterisations by reading its source
  cold.** ADR-205's hand-replica of `ti()` disagreed by up to 182 in `X` before
  instrumenting `mgcv:::smooth.construct.tensor.smooth.spec` directly found that
  `cr` sets `noterp`, so `np=TRUE`'s SVD reparam never fires. Instrument, then
  re-derive. The licensing constraint (GPL vs MIT) means transcription is barred
  anyway, and instrumenting is both legal and more reliable.

## 7. Definition of done

- `PolarisGAM` fits a multi-term `cr` + `ti` + `by` model end to end.
- Stage-B conformance measured at **tier 3**, with a `VerificationClaim`
  declaring each compared quantity INDEPENDENT / ECHO / TRANSPORT.
- The registered prediction in §4 resolved explicitly — confirmed *or* refuted,
  in those words.
- Ledger rows at both tiers; an ADR recording what the assembly required that
  the components did not.
- `experience_gam_penalized` and `experience_gam` untouched; `tests/qa/` goldens
  byte-identical.
