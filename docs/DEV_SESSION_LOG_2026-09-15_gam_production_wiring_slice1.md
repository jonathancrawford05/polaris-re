# Dev session log — 2026-09-15 — production wiring slice 1

**Epic:** `docs/PLAN_gam_production_wiring.md` (slice 1)
**Branch:** `claude/bold-babbage-od867w`
**ADR:** ADR-227
**Ledger:** one row, `INDEPENDENT`

> **Why this log exists at all, given the maintainer's "run this LIGHT"
> direction of 2026-09-15.** That direction said to skip the session log and
> the ADR *unless the slice finds something* — "a failed equivalence, a
> surprising disagreement, a defect". It found **all three**: the `te` ≡
> `s+s+ti` equivalence is refuted, the disagreement pattern is draw-dependent
> rather than systematic, and a probe-level `eta`-definition trap would have
> reported a spurious 99x parity failure. The trigger condition is met, so the
> log and the ADR are owed. Both are kept short.

---

## What the slice was asked to answer

**Anchor W6:** *"nothing wires to a client-facing surface before the TARGET
model specification reaches acceptable parity."* This slice produces the
measurement that gate consumes. In seven weeks of parity work, the production
formula had never been measured against `mgcv` — every result to date is on
structures the parity epic invented.

**Answer: Anchor W6 is NOT satisfied**, and the reason is not our engine.

## Gap Before

**There was no gap to state, and that is the point.** No prior measurement of
the dashboard's own model form against `mgcv` exists at any tier. The nearest
prior reading is a different structure entirely (the parity epic's three-term
`select=TRUE` formula: `eta` `5.46e-03`, ADR-220). This slice establishes the
first reading rather than closing a known gap.

## Gap After

Headline recipe: full age × calendar-year × duration grid at production grain,
`n = 1260`, `p = 39`, seed `20260915`.

| axis | what it asks | `max_abs_eta_diff` | `edf_total` diff | ADR-221 verdict |
|---|---|---:|---:|---|
| (1) Polaris vs `mgcv` `s+s+ti` | does our engine reproduce the spec we CAN express? | **3.18e-05** | −0.0029 | **AGREES** (629x margin) |
| (2) Polaris vs `mgcv` `te()` | does that reproduce the TARGET? (**W6**) | **3.72e-02** | +0.5200 | **FAILS** (1.86x over) |
| (3) `mgcv` `te()` vs `mgcv` `s+s+ti` | are the two forms the same fit at all? | **3.72e-02** | +0.5230 | **NOT equivalent** |

**Attribution: our engine contributes 0.086% of the target-form gap; the
re-expression contributes 100.03%.**

## Hypotheses Tried

1. **"`te(x,z)` and `s(x)+s(z)+ti(x,z)` are the same fit."** (PLAN slice 1's own
   registered prediction: agreement within `2e-2`.) **REFUTED.** They span the
   same space — column counts are equal on both sides in every cell measured —
   but `te` carries 3 smoothing parameters where the decomposition carries 5.
   The prediction's *fallback* was right where its conclusion was wrong: it said
   that if the equivalence failed, "the difference localises to the penalty
   construction, not the basis", and that is exactly what the equal spans plus
   unequal `sp` counts show.
2. **"The disagreement is one unlucky recipe."** **REFUTED**, by an R-internal
   sweep. Draw axis (8 Poisson draws): **6 of 8 FAIL**, median `2.90e-02`, range
   `6.00e-06` … `5.51e-02`. The forms coincide on *some* draws and not others —
   worse than a consistent bias for a client-facing surface, because a single
   fit gives no way to tell which case you are in.
3. **"The disagreement is a basis-size artefact."** **REFUTED.** k axis, anchored
   on a draw that *disagrees* at the headline `k` (anchoring on an agreeing draw
   would have proved nothing): `5.06e-02` … `5.57e-02` across `p = 24` … `70`.
   The gap does not shrink as the basis grows.
4. **"`max_abs_eta_diff = 1.9751` means the production form fails parity
   catastrophically."** **REFUTED — it was my own probe's bug**, caught before
   anything was committed. See "Defect found" below.
5. **"Single-start is the risk here that it was at N=7."** **REFUTED on this
   structure.** Single-start and `multistart(9)` agree to ~1e-5 on axis (1)
   (`3.25e-05` vs `3.18e-05`), both converged, neither at a bound. The ~20x
   single-start penalty ADR-221 measured on the `select=TRUE` N=7 structure does
   not appear on this 5-block non-`select` one. Multistart stays pinned — ADR-226's
   case for it is about cross-thread reproducibility, not search difficulty —
   but slice 3 should not inherit the N=7 expectation.

**Internal control that makes the localisation stick:** `s(duration_years)` is
structurally identical in both formulas — it is not part of what `te` decomposes
— and its own `edf` agrees to `≤ 4.5e-03` in every cell while the decomposed
age×year block does not. The disagreement is confined exactly to the re-expressed
term.

## Defect found (hypothesis 4, in full)

`mgcv`'s `predict.gam(type = "link")` does **not** add back an offset supplied
through `gam()`'s `offset=` **argument**; `m$linear.predictors` does. Polaris's
`fit_polaris_gam` computes `eta = offset + X @ coef`, so `m$linear.predictors` is
the like-for-like quantity.

Using `predict(type = "link")` made `max_abs_eta_diff` read **1.9751** against a
`2e-2` bound — a spurious 99x "failure" that was **entirely**
`max(log(exposure · q_base))`. It would have been reported as a catastrophic
parity failure of the production formula.

**No earlier probe in this epic could have hit it:** the parity epic's target
formula uses *weights and no offset* (PLAN Anchor 5's table), so the dashboard's
Poisson-offset form is the first place an offset enters. The probe now exports a
tripwire — `m$linear.predictors − (predict(type="link") + offset)` — which reads
machine epsilon at both tiers and will announce a future `mgcv` changing this.

## Oracle Version

- **Tier 1** — R 4.3.3 / mgcv 1.9.1 (local apt, the expected versions),
  `OPENBLAS_NUM_THREADS=1`. Iteration only.
- **Tier 3** — pinned digest
  `ghcr.io/jonathancrawford05/r-gam-base@sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`.
  **Two runs**: 34968814955 (`2ff1a2a`) and 34969745829 (`480cc98`, adding the
  span measurement). **Every number above is confirmed at tier 3.**

The Polaris-side `eta` reading across tier 1 and both tier-3 runs spans
`3.1764e-05`–`3.1824e-05` — three orders below the bound it is measured against
— and **every verdict is identical at both tiers and across both tier-3 runs**.
Tier-3 run 2 reproduces tier 1 exactly; run 1 differs in the last two figures
(expected BLAS/search-path variation between independently-provisioned runners).
The R-internal sweep is bit-identical between tiers except one
`duration_edf_diff` cell at the 15th significant figure (`−6.88e-15` against
`−5.11e-15`), which is itself a confirmation that the two tiers are genuinely
different environments.

## One claim I had to go back and actually measure

I first wrote `spans_match` as `n_coef_te == n_coef_anova` and the ADR text as
"column counts are equal, therefore the span is identical". **That does not
follow** — two 39-column bases can span different 39-dimensional subspaces — and
the whole localisation ("same span, DIFFERENT penalty") rests on it. So it is
now measured: project each design's columns onto the other's column space, both
ways, and report the worst residual alongside
`rank(X_te)`, `rank(X_anova)` and `rank([X_te X_anova])`.

Readings: `2.953e-13` / `2.949e-13` (tier 1), `1.021e-14` (tier 3), ranks
39/39/39 at both. Mutual containment to machine precision, so the claim stands —
but it now stands on evidence rather than on an inference that did not hold.
Two tests cover the cases the column-count version would have missed.

## Provenance (ADR-193)

**This slice IS a genuine two-producer comparison** — unlike the several before
it, which were correctly classed `MEASUREMENT (own criterion)` because no second
producer's value sat opposite ours. Here Polaris's own fit sits opposite `mgcv`'s
own fit of the same recipe.

The mechanical test, applied to the producing function's signature:
`fit_production_mi_case(r_case: RProductionMIRecipe, ...)`, and
`RProductionMIRecipe` structurally has no `te`/`anova` key, so it cannot read
either `mgcv` fit even when handed the wider payload. A test asserts this.

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `eta`, `edf_total` vs `s+s+ti` | `fit_polaris_gam` at its own selected `log_lambda` | `mgcv` `gam(s+s+ti, method="REML")` | **INDEPENDENT** |
| `eta`, `edf_total` vs `te()` | `fit_polaris_gam` at its own selected `log_lambda` | `mgcv` `gam(te()+s(), method="REML")` | **INDEPENDENT** |
| `eta`/`edf_total`, `te` vs `s+s+ti` | `mgcv` | `mgcv` | **INDEPENDENT, entirely inside R** — real evidence about `mgcv`, **none** about Polaris (the category `VERIFICATION_STANDARD.md` §5 records for the R-side `smoothCon`/`lpmatrix` guard) |

The third row is the localiser and must never be read as parity evidence for
this engine. It is what separates *our engine is wrong* from *the re-expression
is not the target form*.

## Anchors honoured

- **W5 (no re-gating, no widened tolerance):** ADR-221's `eta`/`edf` bounds are
  **imported** into `gam_production_mi_conformance`, not redeclared, so they
  cannot drift. `log10(sp)` is neither gated nor differenced — the two forms do
  not carry the same number of smoothing parameters, so it is undefined between
  them, not merely loose.
- **W2 (band separate):** no band touched.
- **W3 (old path not deleted):** nothing re-pointed; no production file changed.
- **Anchor 2:** coefficients exported for diagnostic reading, never compared.

## Test baseline

See "Baseline result" below. **Reconciled against the previous parity session's
stated baseline rather than eyeballed**, because the absolute counts move
whenever a test lands.

## What I did NOT do, deliberately

- **Did not build a `te` basis producer.** Slice 1's DoD says an equivalence
  failure "is the slice's result and it stops here rather than proceeding to
  slice 2", and the task direction repeated it. Registered as **slice 1b**
  instead (`ROUTINE_MGCV_PARITY.md` step 10: registered as a slice with a
  release condition, never merely filed in a CONTINUATION, because the
  work-selection rule cannot reach a note).
- **Did not re-point the dashboard onto `s+s+ti`.** That is the cheaper route to
  satisfying W6, and it is a **modelling** decision the routine explicitly
  reserves to the maintainer ("whether a term belongs in the target model form").
- **Did not start slice 2.** It measures old-vs-new on the Polaris side, and
  *which "new"* is precisely what is now undecided.

## Follow-ups registered

- **Slice 1b** — a `te` basis producer. Release condition stated in the PLAN.
- **Slice 1c** — unpenalized parametric columns, so the dashboard's `Σ factors`
  block can be expressed at all. Found on the way; not measured here (the recipe
  carries no factor column), but it blocks any real cedant frame.

## Baseline result

`uv run pytest tests/ -m "not slow"`, R present, `OPENBLAS_NUM_THREADS=1`:

**3660 passed, 3 skipped, 127 deselected, 5 warnings, 0 failed (778.30s).**

**Reconciled exactly against the last parity session's recorded baseline** (3646
passed / 3 skipped / 126 deselected / 0 failed, with R — `DEV_SESSION_LOG_
2026-09-15_sequencing_and_threshold_decisions.md`), rather than compared by eye:

| | non-slow collected | deselected |
|---|---:|---:|
| this branch | 3663 | 127 |
| this branch, ignoring only the new test file | 3649 | 126 |
| **this file's contribution** | **+14** | **+1** |

3649 collected with 3 skips is 3646 passing — **the previous baseline exactly**
— and this branch adds precisely the 14 non-slow tests plus the one
`@pytest.mark.slow` end-to-end test (deselected). 3646 + 14 = **3660**. ✅

**One environmental failure had to be cleared first, and it was not a
regression.** On a clean checkout, `test_loaded_ilec_feeds_tensor_mi_surface`
failed on `FileNotFoundError: data/mortality_tables/soa_vbt_2015_male_smoker.csv`
— the documented "tables are GENERATED, not committed" case, whose own error
message says so. `uv run python scripts/convert_soa_tables.py --source pymort`
cleared it and 19 further skips. Recorded here because a future session diffing
against this log needs to know the count was taken *with* the tables present.

**QA goldens:** `uv run pytest tests/qa/` — **94 passed**, byte-identical
(Anchor W3). Nothing was re-pointed; this branch adds a conformance module that
no engine path imports.

**Lint/format/type:** `ruff format` (no changes), `ruff check src/ tests/` (all
checks passed), `mypy` on the new module (no issues).
