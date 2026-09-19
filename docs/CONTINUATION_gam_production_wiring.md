# Continuation — wiring the mgcv-parity engine to the production MI surface

**Plan:** `docs/PLAN_gam_production_wiring.md`
**Created:** 2026-09-15 by the session that started slice 1.
**Status 2026-09-16: DEMOTED. Slice 1 is DONE, its gating conclusion is
RETRACTED, and this epic is not the project's next work.**

> **READ `docs/MGCV_FEATURE_COVERAGE.md` FIRST.** It carries the objective, the
> coverage table and the capability ladder. This epic is sequenced behind that
> ladder, not ahead of it.

---

## The correction, in one paragraph

**The dashboard is a placeholder, not the parity target** (maintainer,
2026-09-16). And this plan's blocker A — *"the dashboard fits
`te(attained_age, calendar_year)`"* — **was false**: the `te(...)` came from
`TensorMIModel`'s docstring prose, the code builds
`bs(age) + bs(year) + bs(age):bs(year)` (the ANOVA shape), and it is fitted
**unpenalized** by `sm.GLM`. Measured with `fx=TRUE`, `te` and `s+s+ti` agree to
**`8.88e-16`** (tier 3; `2.14e-15` tier 1); the `3.72e-02` gap slice 1 headlined is generated entirely by a
penalty the shipped model does not have. Full account: ADR-227 amendment 1.

## What slice 1 actually delivered, correctly classified

**A capability data point, not a gate verdict:** `fit_polaris_gam(multistart=True)`
against `mgcv`'s own fit of a four-term penalized ANOVA-shaped HGAM —
`s(age) + s(year) + ti(age, year) + s(duration)`, Poisson-log with offset, free
`sp` — reads **`max_abs_eta_diff = 3.18e-05`** against ADR-221's `2e-2`, tier-3
confirmed across three dispatches. **The best free-`sp` agreement this epic has
produced**, two orders better than the previous best (`5.46e-03`, ADR-220).

Also still standing, and reusable:

- **The `predict(type="link")` offset trap** — `eta` must be read as
  `m$linear.predictors`; the alternative silently drops an argument-supplied
  offset and read `1.9751` against a `2e-2` bound. Tripwired in the probe.
- **Blocker D does not bite here.** Single-start matches multistart to ~1e-5 on
  this 5-block non-`select` structure; the ~20x penalty is a property of the
  `select=TRUE` N=7 case.
- **`te` != `s+s+ti` under penalization** — a true statement about two penalized
  `mgcv` forms, with `mgcv` on both sides. It says nothing about the dashboard.
- **Span equivalence measured**, not inferred from column counts.

## Anchor W6: right anchor, wrong spec measured against it

W6 gates on *"the TARGET model specification"*. The target is the HGAM/BAM suite
(`MGCV_FEATURE_COVERAGE.md` §1), not the placeholder. So **W6 remains unmet** —
because the capability ladder is unfinished, not because anything is
inexpressible in the way blocker A claimed. Slice 1 does not bear on W6 in
either direction.

## Slice disposition

| slice | status |
|---|---|
| 1 | **DONE** — measurement kept, conclusion retracted |
| 1b (`te` basis producer) | **DROPPED** — justification was blocker A. `te` lives on as ladder rung **L8**, with `t2`, checked jointly against the already-verified `ti` |
| 1c (parametric columns) | **RE-HOMED** as ladder rung **L4** — it blocks the *target formula* (`FaceSize + Smoke + FaceSize:Smoke`), not just the dashboard |
| 2-5 | **NOT STARTED**, correctly blocked — now behind the ladder |

## NEXT

**Not this epic.** The next work is the capability ladder in
`docs/MGCV_FEATURE_COVERAGE.md` §4 — L1 (`gaussian(identity)`), L2 (`bs="re"`),
L3 (factor-`by`), L4 (parametric columns) are the cheap, high-value rungs.

Blockers B and C are unchanged and still real: B (quasi-Poisson / scale-estimated
REML) is ladder rung **L5**; C (the band's coverage) remains
`PLAN_penalized_mi_surface.md`'s standing BLOCKER and is untouched by any of this.
