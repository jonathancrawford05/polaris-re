# Plan: wire the mgcv-parity engine to the production MI surface

> **This epic exists because the parity evidence and the shipped dashboard are
> currently attached to two different implementations.** Slices 1–7e of
> `PLAN_mgcv_parity_engine.md` validated `gam_model.fit_polaris_gam`. The
> Experience Improvement page renders `experience_gam.TensorMIModel` /
> `BayesianTensorMIModel`. They share no code. Nothing downstream of slice 7e
> changes that — the epic could run to completion and the dashboard would still
> be showing statsmodels output with no `mgcv` evidence behind it.

**Source:** maintainer direction, 2026-09-04 — *"I always planned to wire our
best mgcv parity candidate."* Raised from the PR #225/#226 review conversation.
**Predecessors:** `PLAN_mgcv_parity_engine.md` (the engine and its evidence);
`PLAN_penalized_mi_surface.md` (the band and its coverage gate);
`PLAN_mi_dashboard.md` (the surface being re-pointed).
**Total slices:** 5, of which slice 4 may legitimately end in "change nothing".
**Estimated scope:** ~4–6 dev-days autonomous, plus tier-3 dispatches.
**Status: REGISTERED, NOT STARTED.** Its `CONTINUATION_gam_production_wiring.md`
is created by whichever session starts slice 1 — deliberately not created here,
so this epic cannot be mistaken for active while
`CONTINUATION_mgcv_parity_engine.md` is still IN PROGRESS (one-active-epic
rule).

---

## The gate this epic exists to pass

**Can the GAM on the dashboard be shown to an external audience?** That is not
the same question as "is the engine correct", and this epic exists because the
project has been answering the second one. The gate has four parts, and today
the project passes none of them *for the code a user can actually reach*:

1. The surface on screen is produced by code with committed `mgcv` evidence.
2. The configuration on screen is one that passes the committed acceptance gate.
3. Whatever uncertainty is drawn on screen is defensible as what it claims to be.
4. The claim made in the UI names its quantity, tolerance and structure
   (`ADR-219` amendment 1's marketing constraint).

---

## What was measured before writing this (2026-09-04, import-graph audit)

Not asserted — read off the source tree at `40f14d8`:

- **`gam_model` (the validated engine) has zero production consumers.** It is
  imported by exactly five conformance modules
  (`gam_model_conformance`, `gam_multiterm_conformance`,
  `gam_multiterm_sz_conformance`, `gam_select_free_sp_conformance`,
  `gam_select_multiterm_conformance`) and three test files. It is not exported
  from `analytics/__init__.py`; `ExperienceGAM` and `BayesianTensorMIModel` are.
- **None of `gam_model`, `experience_gam_penalized`, `gam_uncertainty` or
  `gam_uncertainty_mi` is referenced from any user-facing layer** — checked
  across `dashboard/`, `api/`, `cli.py`, `mcp/`, `services/`, `pipeline.py`
  and `viz/`.
- **`dashboard/views/experience_improvement.py` imports only from
  `experience_gam`** (`ExperienceGAM`, `TensorMIModel`, `GAMFitResult`,
  `MISurfaceResult`, plus `BayesianTensorMIModel` lazily at line 443), which is
  statsmodels-backed (`ExperienceGAM._require_backend`).

### Four substantive blockers, not one wiring job

**A. The formula gap is real, not cosmetic.** The dashboard fits
`deaths ~ offset(log[exposure * q_base]) + te(attained_age, calendar_year) +
s(duration_years) + Σ factors`. `assemble_model_design` accepts `basis` in
`{"cr", "ti", "sz"}` and **raises on anything else — there is no `te`**. `te`
is not `ti`: `ti` is the interaction-only tensor, `te` is the full tensor
including margins. The standard equivalent is
`s(age) + s(year) + ti(age, year)`, which spans the same space but carries a
*different penalty structure*, so it is a different fit and needs its own
measurement rather than an assumed equivalence.

**B. The by-amount basis cannot use the validated selection at all today.**
The amount basis is quasi-Poisson. `quasipoisson_log()` sets
`dispersion_fixed=False`, and `gam_reml.reml_score_general` **raises** on
exactly that (`gam_reml.py:167`). `reml_score_gradient` carries the same
guard. So the free-`sp` REML search this epic validated is unavailable for
half the dashboard's basis toggle. `mgcv` handles scale-estimated families
with a different criterion; supplying one is new numerical work, not wiring.

**C. Re-pointing the band would make coverage worse, and this is measured.**
From `docs/MEASUREMENT_unconditional_coverage.md` (200 replicates, nominal
0.95, MC SE ≈ 1.54pp):

| estimator | overall | ages ≥80 | mean width |
|---|---:|---:|---:|
| unpenalized `TensorMIModel` — **what ships today** ‡ | **0.9586** (age-flat only) | 0.9533 | 0.03044 |
| penalized, unconditional (Kass-Steffey) — the shipped penalized band | 0.7815 / 0.8090 | 0.6821 / 0.6823 | ~0.0062 / 0.0081 |
| penalized, `wps2016` — the best correction measured | 0.8167 / 0.8354 | 0.7145 / 0.7165 | ~0.0070 / 0.0089 |

Paired cells are *age-flat / age-varying* truth. **‡ Two caveats the source
attaches to that first row, and they matter because it carries the whole
argument for slice 4's default.** It is **age-flat truth only** — there is no
age-varying counterpart anywhere, which is why it shows one value where the
others show two — and it is **not re-measured by that study**: it is quoted
from ADR-187, which ran `TensorMIModel(age_df=6, year_df=3)` over the identical
truth and the identical replicate seeds (1000..1199).

**The like-for-like comparison is therefore age-flat against age-flat: 0.9586
against 0.7815**, and it is a same-seeds, same-truth comparison rather than a
loose one. The conclusion survives the caveats, but state it in that shape and
not as a bare 0.96-vs-0.78. Slice 4 should also treat the missing age-varying
unpenalized figure as a gap to close before it recommends anything: on the
age-varying truth we know what the penalized band does (0.8090) and do **not**
know what today's shipped band does.

The dashboard's *current* band covers correctly because it is wide. The
penalized band under-covers, worst at the ages life reinsurance cares about
most. **Wiring the point estimate and wiring the band are therefore separate
decisions and must be separate slices** — a naive re-point would trade a
0.96-covering band for a 0.68-covering one at age 80+, on the page intended
as a marketing surface.

**D. The default configuration is the one that fails the gate.** ADR-221's
re-gate is passed only by `multistart=True`; a plain single-start
`fit_polaris_gam` reads `max_abs_eta_diff = 0.4456` against the `2e-2` bound
(over 20x). `analytic_gradient` also defaults `False`. Any wiring must pin
`multistart=True` explicitly and record why.

---

## Anchors

**Anchor W1 — inherited from `PLAN_mgcv_parity_engine.md` Anchor 7, and it is
this epic's own precondition.** *"A caller moves to it only when the new path
has been measured against the old one on the same input and the comparison is
committed."* Slice 2 exists solely to discharge this. No caller moves before it.

**Anchor W2 — the point estimate and the interval are wired separately, and
never in the same slice.** Blocker C is the reason. A slice that moves both at
once cannot attribute a coverage change to either.

**Anchor W3 — the old path is not deleted.** `TensorMIModel` /
`BayesianTensorMIModel` stay, the QA goldens keep depending on them, and the
new path arrives behind a flag that defaults to the old behaviour until slice 5.

**Anchor W4 — no claim reaches the UI that is not in the ledger.** The reverse
is already true and is not enough: the ledger is where evidence lives, the UI is
where an external reader looks, and today nothing carries a claim to them.

**Anchor W5 — this epic may not widen a tolerance or re-gate anything.**
Re-gating is `ROUTINE_MGCV_PARITY.md`'s maintainer-reserved territory and
ADR-221 has just exercised it. If a measurement here fails a committed gate,
the finding is the deliverable.

---

## Slice 1 — express the dashboard's MI formula as a `ModelSpec`, and measure it

- **Depends on:** ADR-217 (`select=TRUE` block structure), ADR-221 (the gate).
- **Deliverable:** the dashboard's own model form, built through
  `assemble_model_design`, measured against `mgcv` on the same recipe.
- **The `te` decision is the substance.** Either (a) re-express
  `te(age, year)` as `s(age) + s(year) + ti(age, year)` and *measure* that the
  fit matches `mgcv`'s own `te()` on the same data, or (b) build a `te` basis
  producer. (a) is cheaper and is what `mgcv`'s own documentation describes as
  the equivalent decomposition — but "equivalent in span" is not "equivalent in
  penalty", so it is a hypothesis to test, not an assumption to make. **State
  which branch was taken and why.**
- **Count basis only.** Blocker B puts the amount basis out of scope here.
- **DoD:**
  - `[machine]` A `ModelSpec` reproducing the dashboard's count-basis formula
    assembles, fits, and its `eta`/`edf` are compared against `mgcv` fitting the
    same formula on the same recipe, tier 1 AND tier 3, with a new ledger row and
    a declared `VerificationClaim`.
  - `[machine]` `multistart=True` pinned; the single-start reading recorded
    beside it so the gap stays visible (blocker D).
  - `[judgement]` If the `te` ≡ `s+s+ti` re-expression does **not** reproduce
    `mgcv`'s `te()` within ADR-221's tolerances, that is the slice's result and
    it stops here rather than proceeding to slice 2.
- **Registered prediction (write before measuring):** the re-expression
  reproduces `mgcv`'s `te()` on `eta` within ADR-221's `2e-2`, because both are
  the same span under a penalty this engine already assembles per-margin. If it
  does not, the difference localises to the penalty construction, not the basis.
- **Out of scope:** the amount basis; any band; any dashboard edit.

## Slice 2 — old vs new on the same input (Anchor 7's precondition)

- **Depends on:** slice 1.
- **Deliverable:** a committed comparison of `TensorMIModel` (old) against the
  slice-1 `ModelSpec` fit (new) **on the same cells**, reporting the fitted
  `MI_x(y)` surface difference — not against `mgcv`, against *each other*.
- This is the quantity a user would actually experience as a change, and
  Anchor 7 requires it to exist before any caller moves. It is a
  `MEASUREMENT (own criterion)` comparison — two Polaris implementations —
  and must be labelled as such, never as parity.
- **DoD:**
  - `[machine]` Committed script + report giving the max and distributional
    difference in `MI_x(y)` between old and new over the shipped sample study,
    by age band.
  - `[judgement]` A written answer to "would a user notice, and where?" — with
    the age bands where the two differ most named explicitly.
  - `[machine]` Provenance label `MEASUREMENT (own criterion)`; no parity
    language anywhere in it.
- **Out of scope:** deciding which is better. That is slice 3's gate and, if
  the difference is material, the maintainer's.

## Slice 3 — wire the point estimate behind a flag, default off

- **Depends on:** slices 1 and 2.
- **Deliverable:** the Experience Improvement page can render its MI surface
  from the validated path, selected by an explicit flag, defaulting to the
  existing behaviour.
- `multistart=True` pinned (blocker D). Consider `analytic_gradient=True` for
  the ~9x cost saving, but only once slice 7f of the parity epic has resolved
  the `ftol` early-exit — **a page that silently reports a non-converged fit is
  worse than a slow one.** If 7f is unresolved, use `multistart=True` alone and
  record the cost.
- **DoD:**
  - `[machine]` Flag exists, defaults to the old path, and a test pins that the
    default render is byte-identical to today's.
  - `[machine]` `tests/qa/golden_outputs/` byte-identical (Anchor W3).
  - `[machine]` The new path renders end-to-end in the dashboard flow tests.
  - `[judgement]` The band shown alongside is **still the old estimator's** —
    slice 4 owns that decision (Anchor W2). If that pairing is not coherent
    (a new surface with an old band), say so and stop for a maintainer call.
- **Out of scope:** the band; making it the default; the amount basis.

## Slice 4 — the band decision (may end in "change nothing")

- **Depends on:** slice 3; `MEASUREMENT_unconditional_coverage.md`.
- **The honest default outcome is to keep the old band**, and this slice should
  be written expecting that. Blocker C's table is the reason: on the age-flat
  truth the shipped unpenalized band covers at 0.9586 against the penalized
  band's 0.7815, and every penalized variant measured under-covers worst at
  ages ≥80 (0.68–0.72 against a nominal 0.95).
- **First, close blocker C's own gap.** The 0.9586 figure exists for the
  age-flat truth only. Before recommending anything, measure the shipped
  unpenalized estimator's coverage on the **age-varying** truth over the same
  seeds (1000..1199) — otherwise the recommendation rests on a comparison that
  exists on one truth and is assumed on the other, which is the shape of
  reasoning this project's own standard exists to stop.
- **What this slice actually decides:** whether the dashboard should draw a
  penalized band at all, and if not, whether pairing a validated surface with
  the old estimator's band is defensible or whether the page should draw no
  band until coverage is fixed.
- **DoD:**
  - `[machine]` Unpenalized coverage measured on the age-varying truth, same
    seeds, committed — closing the gap above before any recommendation rests
    on it.
  - `[judgement]` A written recommendation with the coverage table beside it,
    filed for the maintainer, **not taken** — re-pointing an interval is an
    Anchor-7-class change.
  - `[machine]` If any band changes, coverage is re-measured on the same
    replicate seeds and committed before the change lands.
- **Out of scope:** fixing coverage. That is `PLAN_penalized_mi_surface.md`'s
  standing BLOCKER and is not this epic's to close.

## Slice 5 — what the surface may claim, in the UI

- **Depends on:** slices 1–4.
- **Deliverable:** the claim, in the page, in the shape ADR-219 amendment 1
  requires — naming the quantity, the tolerance and the structure, with a link
  to the ledger row.
- **Must state what is *not* claimed**, in the UI and not only in a doc: no
  unqualified "mgcv parity"; conformance level 4's standing disagreement; and,
  if slice 4 leaves the old band in place, that the interval is not produced by
  the validated path.
- **DoD:**
  - `[judgement]` Claim sentence written before the UI copy, narrower than any
    claim the project has published, reviewed against amendment 1's three
    consequences one at a time.
  - `[machine]` Every number in the UI copy traces to a committed ledger row.
  - `[judgement]` A reader who follows the link can reconstruct the claim from
    the ledger without reading a session log.

---

## Out of scope for this epic, stated up front

- **quasi-Poisson REML (blocker B)** — the amount basis stays on the old path
  until a scale-estimated criterion exists. Needs its own slice in the parity
  epic, or a maintainer decision that the dashboard's amount toggle may run a
  different engine from its count toggle (and say so in the UI).
- **The coverage gap (blocker C's cause)** — standing BLOCKER in
  `PRODUCT_DIRECTION_2026-07-24.md`, owned by `PLAN_penalized_mi_surface.md`.
- **Run-to-run reproducibility** (ADR-219 amendment 3) — but see the open
  question below; it may gate slice 5.
- **Deleting or re-pointing anything by default** (Anchor W3).
- **Any re-gating or tolerance change** (Anchor W5).

## Open questions for the maintainer

1. **Does reproducibility gate the UI claim?** ADR-219 amendment 3 measured a
   four-decade swing on the multistart row between two identical tier-3 runs;
   ADR-220's two runs then reproduced bit-identically. Unresolved. A dashboard
   that re-fits per session could show one user two different numbers. **My
   recommendation: it gates slice 5 (the published claim) but not slices 1–3
   (the wiring).**
2. **Is a validated surface with an unvalidated band acceptable as an interim?**
   Slice 3 produces exactly that pairing. It may be the right trade — the
   surface improves, the band is no worse than today — but it is a judgement
   about what a reinsurer reads off a chart, not a technical one.
3. **Does this epic outrank the parity epic's remaining slices?** 7f and beyond
   improve an engine no user can reach. Slices 1–3 here are what make any of it
   visible. Sequencing is yours; the routine's one-active-epic rule means only
   one of the two advances at a time.
