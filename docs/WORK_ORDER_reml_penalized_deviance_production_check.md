# Work order — does the shipped tensor-MI REML score have the same missing term?

**Raised by:** maintainer direction, 2026-08-18, following ADR-196's resolution (PR #203).
**Epic:** `docs/PLAN_mgcv_parity_engine.md` / `docs/CONTINUATION_mgcv_parity_engine.md`
**Gate:** run this **before** slice 4 part B (the N-dimensional outer search) opens. Per
the maintainer's own direction: assign this as the next `ROUTINE_MGCV_PARITY.md` firing,
ahead of the search — mirroring how slice 1b was inserted ahead of slice 2.
**Disposition of PR #203:** merges on its own terms once green; this work order is
deliberately a separate, later PR, not a follow-up commit to #203.

---

## 1. Why this exists — what ADR-196 found, and what it does not yet tell us

ADR-196 (`docs/DECISIONS.md`) found and fixed a real bug in `gam_reml.reml_score_general`:
the REML score used the plain deviance `D(β̂)` where Wood (2011), *JRSS-B* 73(1) 3-36,
"Fast stable restricted maximum likelihood and marginal likelihood estimation of
semiparametric generalized linear models", §2 eq. (4), requires the **penalized** deviance
`Dₚ = D(β̂) + β̂ᵀSβ̂`. Adding the missing `β̂ᵀSβ̂` term closed a ~0.74 / ~9.3e-4 disagreement
to ~1e-12 (float round-trip noise) on every tested point, tier 1 and tier 3 identical.

**`gam_reml.reml_score_general`'s formula was written verbatim from
`experience_gam_penalized.reml_score`** — the Poisson-log-link, two-hardcoded-block REML
score the tensor MI surface's own 2-D grid smoothing-parameter selector
(`select_lambdas_reml`) has been using in production since the penalized-MI-surface epic.
That module's formula has the **identical** shape, and the identical omission: plain
deviance, no `β̂ᵀSβ̂` term (`experience_gam_penalized.py`, `reml_score`, the `deviance`
variable is never combined with `coef @ penalty @ coef`).

**This is not yet confirmed as the same bug in that module** — it is a strong, precisely
targeted hypothesis, not a finding. Two things distinguish it from ADR-196's own
measurement and must not be assumed:

1. ADR-196's fixture is this epic's own, purpose-built two-block binomial/logit design.
   The production module fits a different family (Poisson log-link with an offset) on a
   different design (a two-margin tensor product with two difference penalties). The
   formula shape is the same; the actual numbers are not transferable.
2. **ADR-189 amendment 1 already recorded circumstantial evidence pointing the same way**,
   and explicitly declined to treat it as a finding: "the convention offset found in every
   cell — ≈ -l_sat/gamma ... A residual of 0.93-3.17 survives after removing it and is
   unexplained ... `reml_score` is not a compared metric." That residual is consistent in
   *order of magnitude* with a missing `β̂ᵀSβ̂` term (β̂ᵀSβ̂/2 at a typical fitted λ on that
   fixture would plausibly fall in a similar range), but "consistent with" is not "measured
   to be" — this work order's first job is closing that gap with an actual measurement, the
   same discipline ADR-196 required of itself before calling anything a fix.

---

## 2. What this work order is, and — just as importantly — what it is not

**Is:** a measurement-and-recommendation task, following the same hypothesis → measure →
tier 1 → tier 3 discipline as every other session in this epic.

**Is not:** a license to patch `experience_gam_penalized.py`. That module is explicitly
protected by **PLAN Anchor 7** ("the existing engine stays... every committed report was
produced by them, the QA goldens depend on nothing moving"). `tests/qa/golden_outputs/`
was fitted using the CURRENT (possibly-buggy) formula; changing `reml_score` would move
every λ selection the 2-D grid makes, which moves `edf`, which moves every downstream
number `tests/qa/` pins byte-identical. **A session running this work order may measure,
characterize, and recommend. It may NOT edit `experience_gam_penalized.reml_score` or
re-baseline any golden without the maintainer's explicit, separate sign-off** — the same
boundary CLAUDE.md draws around `tests/qa/golden_outputs/` generally, sharpened here
because the specific change under discussion is exactly the kind that would silently move
every golden it touches.

---

## 3. Scope — three measurements, in order

### 3.1 Does the existing conformance fixture's REML score have the same gap?

The existing ten-cell conformance suite (`docs/RUNBOOK_mgcv_conformance.md`,
`scripts/mgcv_conformance.R`) already exports `reml_score` (`m$gcv.ubre`) per cell — see
`experience_mgcv_conformance.py`'s `PythonCellResult.reml_score`, currently computed via
the potentially-buggy `reml_score()` and NOT a compared/gating metric (ADR-189 amendment
1's own note). Re-derive it there:

1. Take the exported `DesignExport` (design, penalties, deaths, offset) and the fitted
   `coef` for each free-`sp` cell (`l2-free-sp`, `l2-free-sp-factors`, `l2-free-sp-kb`).
2. Compute `Dp = deviance + coef @ penalty @ coef` (the exact expression ADR-196 added)
   and the corrected score, as a **diagnostic-only** side computation — do not modify
   `reml_score` itself in this step.
3. Compare, per cell: `mgcv`'s reported `reml_score` (`m$gcv.ubre`) minus the CURRENT
   Python score, and minus the CORRECTED (`Dp`-based) score. If the corrected version's
   residual collapses the way ADR-196's did, that confirms the hypothesis on the
   production fixture, not just by analogy.
4. This is read-only against committed exchange files (`data/mgcv_exchange/synthetic`) —
   no new R work needed beyond re-running the existing suite, which already happens on
   every `mgcv-conformance.yml` dispatch.

### 3.2 Does the missing term change which `λ` the shipped grid search selects?

This is the question that actually matters for correctness, and it does not follow
automatically from 3.1 — a formula bug in the *score's value* only matters for *selection*
if it changes which grid point scores lowest.

1. Write a **diagnostic-only** corrected scorer (do not touch `select_lambdas_reml` or
   `reml_score` themselves) and re-run the SAME 2-D grid search the shipped selector uses,
   scoring each point with the corrected criterion instead.
2. Compare the selected `(λ_age, λ_year)` and `edf_total`/`edf_tensor`/`edf_factors`
   against (a) the CURRENT shipped selection and (b) `mgcv`'s own free-`sp` selection
   (already in the existing suite, level 2 — `max_abs_log10_sp_diff` and
   `abs_edf_total_diff_free_sp`).
3. **Register the prediction before running it, per this epic's own Anchor 9 discipline:**
   if the missing term is a real bug, the corrected selection should land measurably
   *closer* to `mgcv`'s than the current one does — level 2's own tolerance
   (`max_abs_log10_sp_diff` 4.32e-01 against 0.5, "narrowly passing" per ADR-189
   amendment 1) is loose enough that a real improvement or a real non-improvement should
   both be visible. If the corrected selection is not closer, or lands on the SAME grid
   point as today (plausible, since the grid's own resolution is coarse — 0.25 decades —
   and could already be absorbing a small formula error), that is itself the finding:
   write "the bug is real but does not change production behavior at this resolution,"
   not "no bug."

### 3.3 Does the missing term change the Kass-Steffey (level 4) picture?

`smoothing_uncertainty` (ADR-190's territory) evaluates its own REML-adjacent quantities
at a **fixed** `sp` (the selected one), via finite differences of the score across
neighboring grid points (`KS_LOG_STEP`). If the corrected score's *shape* near the optimum
differs from the current one's, the Kass-Steffey correction's finite-difference Hessian
could be affected even without changing which grid point is selected. **Measure whether
`smoothing_uncertainty`'s inputs change under the corrected score before concluding the
standing level-4 BLOCKER (ADR-190) is unrelated** — it may not be, and ruling it out is
cheaper than assuming it.

---

## 4. Acceptance criteria

- §3.1's per-cell residual measured and reported, both current and corrected, tier 1 AND
  tier 3 (this is exactly the class of "does a specific mgcv version's arithmetic have
  this property" claim the routine's tier discipline requires — no magnitude carve-out,
  ADR-190 decision 5).
- §3.2's registered prediction (closer / not closer to `mgcv`'s selection) measured and
  reported as a result, not assumed either way.
- §3.3 measured, at minimum a scoped statement of whether it was checked and what was
  found, even if the answer is "checked, no material change at this fixture's scale."
- A written recommendation: fix `experience_gam_penalized.reml_score` (re-baselining
  goldens, a maintainer-gated decision named explicitly as such), leave it as a known,
  bounded, documented gap (if §3.2 shows no material selection change), or something
  in between — **not a code change to that module**, regardless of which recommendation
  the measurement supports.
- `docs/CONFORMANCE_LEDGER.md` carries the measurement, `docs/DECISIONS.md` gets an ADR
  (or an ADR-190/ADR-196 amendment, whichever the finding's shape fits) recording the
  result and the recommendation.
- `tests/qa/` untouched, goldens byte-identical — this session does not touch production
  code, only diagnostics.

---

## 5. Non-goals

- **Do not** edit `experience_gam_penalized.py`. Any change there is a separate, later,
  explicitly maintainer-directed piece of work, not an autonomous extension of this one.
- **Do not** re-baseline `tests/qa/golden_outputs/` under any circumstance this session.
- **Do not** start slice 4 part B (the N-dimensional search) in the same session — this
  work order is deliberately scoped narrower than that, and the search should build on
  a criterion whose production analogue's status is understood, not guessed at.
- **Do not** treat ADR-189 amendment 1's "0.93-3.17 residual" as already-confirmed
  evidence of this bug — it is motivation for §3.1, not a substitute for running it.

---

## 6. Suggested first hypothesis, stated in the routine's own form

*"The production tensor-MI REML score (`experience_gam_penalized.reml_score`) is missing
the same `β̂ᵀSβ̂` penalized-deviance term ADR-196 found and fixed in
`gam_reml.reml_score_general`, and adding it (diagnostically, not in the shipped function)
collapses the `reml_score` residual against `mgcv` the same way it did for the new epic's
own fixture."*

Falsifiable by §3.1 directly. If it holds, §3.2 is the next, harder question — whether it
matters for anything anyone has actually relied on.
