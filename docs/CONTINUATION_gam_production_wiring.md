# Continuation — wiring the mgcv-parity engine to the production MI surface

**Plan:** `docs/PLAN_gam_production_wiring.md`
**Created:** 2026-09-15, by the session that started slice 1 (the plan defers its
creation to exactly that point, so the epic cannot look active while
`CONTINUATION_mgcv_parity_engine.md` is still IN PROGRESS — one-active-epic rule).
**Status:** SLICE 1 DONE — and it **refuted** the hypothesis slices 2-5 were
built on. Slices 2-5 are NOT STARTED and **slice 2 should not start** until the
decision below is taken.

---

## Slice 1 — the result in one paragraph

The dashboard's MI form was expressed as a `ModelSpec` and measured against
`mgcv` for the first time. **Our engine reproduces the spec it can express
essentially exactly** — `max_abs_eta_diff 3.1824e-05` against ADR-221's `2e-2`
bound, the largest margin this epic has ever recorded. **But the spec it can
express is not the target spec.** `te(x,z)` and `s(x)+s(z)+ti(x,z)` are not the
same fit, and the gap between them (`3.7213e-02`) is nearly **1.9x ADR-221's own
bound** — so **Anchor W6 is NOT satisfied**, and it is not satisfied for a
reason no solver work can reach.

## The three-axis reading (headline recipe, `n=1260`)

| axis | what it asks | `max_abs_eta_diff` | `edf_total` diff | verdict |
|---|---|---:|---:|---|
| (1) Polaris vs `mgcv` `s+s+ti` | does our engine reproduce the spec we CAN express? | **3.1824e-05** | −0.0029 | **AGREES**, 629x margin |
| (2) Polaris vs `mgcv` `te()` | does that reproduce the TARGET? (**Anchor W6**) | **3.7201e-02** | +0.5200 | **FAILS**, 1.86x over |
| (3) `mgcv` `te()` vs `mgcv` `s+s+ti` | are the two forms the same fit at all? | **3.7213e-02** | +0.5230 | **NOT equivalent** |

**Attribution: our engine contributes 0.086% of the target-form gap; the
re-expression contributes 100.03%.** Axis (3) has `mgcv` on **both** sides —
Polaris appears nowhere in it — so it is evidence about `mgcv`'s own two formula
forms and none about this engine (`docs/VERIFICATION_STANDARD.md` §5's own
category for the R-side `smoothCon`/`lpmatrix` guard).

## Why it is a real refutation and not one unlucky cell

Swept entirely inside R:

- **Draw axis** (8 Poisson draws, headline `k`): **6 of 8 FAIL** ADR-221's
  criterion, median `2.90e-02`, range `6.0e-06` … `5.51e-02`. The two forms
  coincide on *some* draws and not others — **worse than a consistent bias**,
  because a single fit gives no way to tell which case you are in.
- **k axis** (4 basis dimensions, anchored on a draw that *disagrees*):
  `5.06e-02` … `5.57e-02` across `p = 24` … `70`. The gap does **not** shrink as
  the basis grows, so it is **not a basis-size artefact**.
- **Internal control:** `s(duration_years)` is structurally identical in both
  formulas (it is not part of what `te` decomposes). Its own `edf` agrees to
  `≤ 4.5e-03` throughout, while the decomposed age×year block does not. **The
  disagreement is confined exactly to the re-expressed term.**

Spans match in every cell — and **measured, not inferred from equal column
counts**: the two-way projection residual between the two designs' column spaces
is `2.953e-13`/`2.949e-13` (tier 1) and `1.021e-14` (tier 3), with
`rank(X_te) = rank(X_anova) = rank([X_te X_anova]) = 39`. The
smoothing-parameter count, by contrast, never matches: 3 for `te`, 5 for the
decomposition.

**Same span, different penalty** — which is precisely the mechanism PLAN slice
1's registered prediction said the difference would localise to if the
equivalence failed. **Its fallback was right and its conclusion was wrong:** it
predicted agreement within `2e-2`.

**It is also not an artefact of how the decomposition is spelled** — the first
thing anyone will ask, because `mgcv`'s own `?ti` writes it as
`ti(x) + ti(z) + ti(x,z)` rather than the plan's `s(x) + s(z) + ti(x,z)`, and
demonstrates it beside `te(x,z)` as a *different* model. Measured: the two
spellings are **the same fit to `8.8818e-16`** (`edf_total` diff exactly `0`),
and **mgcv's own spelling misses `te()` by the same `3.7213e-02`**. Neither is
expressible here anyway — a one-margin `ti` is rejected by `TermSpec`, which
requires ≥ 2 variables for `basis="ti"`.

## What this means for the rest of the epic

**Slice 1's own DoD says to stop here rather than proceed to slice 2**, and that
is what this session did. The decision now owed is a maintainer one, because it
is a choice between two unequal costs:

- **(b) Build a `te` basis producer.** The target spec becomes expressible and
  Anchor W6 becomes reachable. This is real numerical work (`te`'s penalty is the
  Kronecker-padded marginal penalty over the full tensor, not the ANOVA
  decomposition's per-block set) and it is now registered as **slice 1b**.
- **Re-point the dashboard onto `s+s+ti`.** Cheaper, and it makes Anchor W6
  satisfiable immediately — but it changes the shipped model, so it is a
  modelling judgement `ROUTINE_MGCV_PARITY.md` explicitly reserves to the
  maintainer ("whether a term belongs in the target model form"), and it would
  need slice 2's old-vs-new measurement to say what a user would see.

**Do not read axis (1) as permission to wire.** It says the engine is sound on
this structure; Anchor W6 gates on the *target spec*, and axis (2) is the one
that answers it.

## Second expressibility gap, found on the way

`assemble_model_design` builds an unpenalized intercept and then penalized
`cr`/`ti`/`sz` terms. It has **no route for unpenalized parametric columns**, so
the dashboard's `Σ factors` block (`sex`, `smoker`, `band`, …) cannot be
expressed either. Not measured here — the recipe carries no factor column, which
is what the page fits when its candidate factors are single-level — but it is a
blocker for any real cedant frame, and it is registered as **slice 1c**.

## A trap worth not re-discovering

`eta` from `mgcv` must be read as **`m$linear.predictors`, never
`predict(m, type="link")`** — the latter does not add back an offset supplied
through `gam()`'s `offset=` argument. Using it made `max_abs_eta_diff` read
`1.9751` against a `2e-2` bound: a spurious 99x "failure" that was entirely
`max(log(exposure * q_base))`. No earlier probe in the parity epic could hit
this, because the parity target formula uses **weights and no offset** (PLAN
Anchor 5's table) — the dashboard's Poisson-offset form is where it first
appears. `scripts/gam_production_mi_probe.R` now carries a tripwire that reports
`m$linear.predictors − (predict(type="link") + offset)`, so a future `mgcv`
changing this behaviour says so rather than moving a number silently.

## Blocker D, measured on this structure rather than assumed

`multistart=True, n_starts=9` is pinned (`fit_production_mi_case` defaults it on,
unlike `fit_polaris_gam`). The single-start reading is recorded beside it and,
**on this 5-block non-`select` structure, the two agree to ~1e-5** — `3.18e-05`
against `3.25e-05` on axis (1), and both `converged`, neither `at_bound`. So the
~20x single-start penalty ADR-221 measured on the `select=TRUE` N=7 structure
**does not appear here**. Pinning multistart remains correct (ADR-226: it is the
only configuration passing both reproducibility axes, and that argument is about
reproducibility, not this structure's search difficulty), but slice 3 should not
expect single-start to be the risk it was on N=7.

## NEXT

**A maintainer decision between slice 1b and re-pointing the model form.** Slice
2 is not the next work: it measures old-vs-new on the Polaris side, and which
"new" it should measure is exactly what is undecided.

**Still open, inherited, and not touched by this slice:** blocker B (the amount
basis / quasi-Poisson REML), blocker C (the band's coverage, Anchor W2), and
ADR-224's registered tier-3 cross-runner dispatch on the parity epic.
