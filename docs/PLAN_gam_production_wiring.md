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
(Slices 1b and 1c were registered by slice 1 and are WITHDRAWN — see the status
banner and ADR-227 amendment 1.)
**Estimated scope:** ~4–6 dev-days autonomous, plus tier-3 dispatches.

> ## STATUS 2026-09-16: THIS EPIC IS DEMOTED. ITS BLOCKER A WAS FALSE, AND THE DASHBOARD IS NOT THE PARITY TARGET.
>
> **Maintainer, 2026-09-16:** *"The dashboard was 'spun up' as a placeholder
> given what is available in Python before we reach our objective, and should
> not be the target of parity unless it is part of a rigorous plan that tackles
> simpler mgcv features first."*
>
> The objective is **mgcv parity across a suite of model forms** (`ti`,
> `bs="re"`, …), **`fREML` / `discrete=TRUE` / `bam`**, and **`select=TRUE`** —
> *"really any hierarchical gam (or bam) specification in mgcv"*. That is now
> tracked in **`docs/MGCV_FEATURE_COVERAGE.md`**, which carries the capability
> ladder this epic's remaining work is sequenced behind.
>
> ### Blocker A was false (ADR-227 amendment 1)
>
> This plan asserted the dashboard "fits `te(attained_age, calendar_year)`". It
> does not, on three counts:
>
> 1. The `te(...)` came from `TensorMIModel`'s **docstring prose**, whose same
>    sentence glosses it as "a tensor-product B-spline surface".
> 2. The code builds `bs(age) + bs(year) + bs(age):bs(year)` — main effect +
>    main effect + interaction, the **ANOVA shape**. `experience_gam_penalized`'s
>    own docstring already said so.
> 3. The fit is **unpenalized** (`sm.GLM`), so "a different penalty structure"
>    describes a property the shipped model does not have.
>
> Measured with `fx=TRUE`: unpenalized, `te` and `s+s+ti` agree to **`8.88e-16`** (tier 3; `2.14e-15` tier 1).
> **100% of slice 1's headline gap is a penalty artefact.** And the target
> formula at `PLAN_mgcv_parity_engine.md` §1 contains no `te` either.
>
> ### What slice 1 is actually worth
>
> `fit_polaris_gam` against `mgcv` on a four-term penalized ANOVA-shaped HGAM:
> **`max_abs_eta_diff = 3.18e-05`**, tier-3 confirmed — the best free-`sp`
> agreement this epic has produced. **A capability data point, not a gate
> verdict.** Recorded in `MGCV_FEATURE_COVERAGE.md` §5.
>
> ### Anchor W6 was right; slice 1 measured the wrong spec against it
>
> W6 gates on *"the TARGET model specification"*. The target is the HGAM/BAM
> suite, not the placeholder dashboard — so **W6 remains unmet**, not because
> `te` is inexpressible but because the ladder is unfinished. Nothing here wires
> to a client-facing surface.
>
> ### Slice status
>
> - **Slice 1 — DONE**, measurement retained, conclusion retracted.
> - **Slice 1b (a `te` basis producer) — DROPPED.** Its entire justification was
>   blocker A. `te` is still wanted for general coverage, as rung **L7** of
>   `MGCV_FEATURE_COVERAGE.md` beside `t2`, checked jointly with the already-done
>   `ti` — not as a dashboard gate.
> - **Slice 1c — RE-HOMED as rung L4.** Unpenalized parametric columns are a real
>   gap and they block the *target formula* (`FaceSize + Smoke + FaceSize:Smoke`),
>   not merely the dashboard. It belongs on the capability ladder.
> - **Slices 2-5 — NOT STARTED and correctly blocked**, now behind the ladder
>   rather than behind a `te` producer.

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

**A. ~~The formula gap is real, not cosmetic.~~ FALSE — RETRACTED 2026-09-16
(ADR-227 amendment 1). Struck in place rather than deleted, because this
paragraph drove a whole slice and a later reader needs to see what was wrong.**

~~The dashboard fits `deaths ~ offset(log[exposure * q_base]) +
te(attained_age, calendar_year) + s(duration_years) + Σ factors`. `te` is not
`ti`: `ti` is the interaction-only tensor, `te` is the full tensor including
margins. The standard equivalent is `s(age) + s(year) + ti(age, year)`, which
spans the same space but carries a *different penalty structure*, so it is a
different fit and needs its own measurement rather than an assumed
equivalence.~~

**Why it is false.** The `te(...)` was lifted from `TensorMIModel`'s
**docstring**, whose same sentence glosses it as *"a tensor-product B-spline
surface"* — prose, not an `mgcv` formula (it likewise writes `s(duration_years)`
for `bs(duration_years, df=4)`). The code builds
`bs(age) + bs(year) + bs(age):bs(year)` — main effect + main effect +
interaction, the **ANOVA shape** — and fits it with `sm.GLM(...)`, **entirely
unpenalized**. So "carries a different penalty structure" describes a property
the shipped model does not have. Measured with `fx=TRUE`: unpenalized, the two
forms agree to **`8.88e-16`** (tier 3; `2.14e-15` tier 1), so 100% of the measured gap is a penalty
artefact. `experience_gam_penalized`'s own docstring already said the shipped
model is *"patsy's main-effects form"*.

**What remains true from it:** `assemble_model_design` does accept only
`{"cr", "ti", "sz"}` and raises otherwise, so `te` is genuinely inexpressible —
that is a real coverage gap (rung **L7** of `docs/MGCV_FEATURE_COVERAGE.md`),
just not one the dashboard was ever blocked by.

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

**E. ~~The engine is not environment-reproducible, and this BLOCKS slice 3.~~
CLOSED 2026-09-14 by measurement (ADR-226).** Slice 7h's fix was verified
end-to-end on the two-axis study, not merely at the criterion level:
`multistart(9)` now passes **both** axes — cross-thread `eta` `0.356 → 1.554e-03`
and `edf_total` `10.0 → 0.0816` (~229x and ~123x), with `12.9x`/`12.3x` margin
against ADR-221's gate — the first configuration ever to pass both. The reading
is itself reproducible (run twice, on `fc25053` and `098a06a`, bit-identical).

**Slice 3's 7h dependency is therefore discharged. Slice 3 remains blocked on
Anchor W6 alone** (parity on the target model specification), which this
measurement does not touch.

**Two limits travel with the closure.** It is one structure, one container, one
BLAS build, `n=3` thread counts — **a local proxy for the cross-runner axis,
not the cross-runner axis itself**, so `SELECT_FREE_SP_MODEL_CLAIM`'s
environment qualification is NOT lifted and ADR-224's registered tier-3
dispatch remains the right instrument. And ADR-226 decision 2 found something
new that this closure does not cover: the search now **reproducibly** prefers a
basin that is worse by our own REML criterion and further from `mgcv` than the
one it finds 3 times in 10. That passes ADR-221's gate (`0.173` against `1.0`)
and is slice 8's to close — but *reproducibly wrong* is the failure mode a
client-facing surface should worry about most, because it looks trustworthy.

The original finding, preserved:

Measured after this plan was written (ADR-222 amendment 1): on the
`select=TRUE` N=7 structure, `multistart=True` — the configuration blocker D
tells slice 3 to pin — is reproducible across seeds but **NOT across thread
counts**, moving `edf_total` by `10.0` and the REML score by `+34.34` on 2 of 4
seeds between 1 and 4 threads. Single-start is the mirror image: reproducible
across threads, not across starts. **No configuration passes both axes.**

ADR-222 amendment 2 then closed the mechanism — catastrophic cancellation in
`beta' S beta` when the `lambda` span many decades, accounting for 100% of the
criterion's cross-thread spread — and registered **parity slice 7h** (a
sum-of-squares evaluation, nine orders of reproducibility for one expression)
and **slice 8** (the Wood-shaped outer solver).

**Consequence for this epic: slice 3 must not proceed until slice 7h has
landed.** Wiring a surface whose value depends on the reader's thread count
onto a page a reinsurer reads is worse than wiring nothing — it would be
undetectable in review and reproducible only by accident. `mgcv` on the same
fixture is bit-identical across thread counts, so this is a defect of ours, not
a property of the problem.

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

**Anchor W6 — nothing wires to a client-facing surface before the TARGET model
specification reaches acceptable parity.** Maintainer, 2026-09-05 (open
question 3): *"We have a targeted model specification that needs acceptable
parity before we wire anything to the client facing dashboard (or other
surfaces)."* Two things this anchor does that Anchor W1 does not. It gates on
**parity against `mgcv` for the target spec**, where W1 gates only on an
old-vs-new comparison between two Polaris paths — a slice-2 measurement can be
perfect and this anchor still unmet. And it binds **every** external surface —
the dashboard, the API, exports, any future client deliverable — so a later
epic cannot satisfy it for the dashboard and treat another surface as
unconstrained.

**Anchor W5 — this epic may not widen a tolerance or re-gate anything.**
Re-gating is `ROUTINE_MGCV_PARITY.md`'s maintainer-reserved territory and
ADR-221 has just exercised it. If a measurement here fails a committed gate,
the finding is the deliverable.

---

## Slice 1 — express the dashboard's MI formula as a `ModelSpec`, and measure it

- **THIS IS THE NEXT WORK. Maintainer sequencing decision, 2026-09-14:** the
  parity epic yields the one-active-epic slot to this slice. Blocker E is
  closed (ADR-226), so **Anchor W6 alone gates slice 3** — and this slice
  produces the measurement W6 consumes, making it the only remaining gate that
  can be *retired* rather than merely improved. The session that starts it
  creates `CONTINUATION_gam_production_wiring.md` (it is deliberately not
  created before that, per the one-active-epic rule).
- **Expect this slice to test blocker A rather than assume it.** `te()` is not
  available and `te(x,z) ≡ s(x)+s(z)+ti(x,z)` is a **hypothesis, not an
  identity** — the ANOVA decomposition spans the same space under a different
  penalty, so it is a different fit. If that equivalence fails, it is a finding
  about the target spec, not a defect in this slice, and it lands before any
  solver work is spent on an engine that cannot render the production formula.
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

## Slices 1b and 1c — WITHDRAWN from this epic (2026-09-16)

Both were registered by slice 1 under blocker A's false premise (ADR-227
amendment 1). Neither belongs in a dashboard-wiring epic.

- **Slice 1b — a `te` basis producer — DROPPED.** Its justification was entirely
  "the dashboard fits `te()`", which is false. `te` is still wanted for general
  mgcv coverage and is **rung L7** of `docs/MGCV_FEATURE_COVERAGE.md`, grouped
  with `t2` and checked jointly against the already-verified `ti`.
- **Slice 1c — unpenalized parametric columns — RE-HOMED as rung L4.** A real
  gap: `assemble_model_design` builds an intercept then penalized terms only, so
  it cannot carry parametric columns. That blocks the **target formula**
  (`FaceSize + Smoke + FaceSize:Smoke`), which is why it belongs on the
  capability ladder and not here.

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

- **Also gated by Anchor W6** — acceptable parity on the target model
  specification (maintainer, 2026-09-05). Independent of, and additional to,
  the 7h dependency below: 7h buys reproducibility, W6 buys agreement.
- **Depends on:** slices 1 and 2. ~~**and parity slice 7h (blocker E) — a hard
  dependency, not a preference.** Until 7h lands, the surface this slice would
  wire is not reproducible across environments.~~ **The 7h dependency is
  DISCHARGED (2026-09-14, ADR-226): 7h landed and the two-axis study measured
  `multistart(9)` passing BOTH reproducibility axes.** What remains is
  **Anchor W6 alone** — acceptable parity on the target model specification,
  which slice 1 measures.
- **Deliverable:** the Experience Improvement page can render its MI surface
  from the validated path, selected by an explicit flag, defaulting to the
  existing behaviour.
- `multistart=True` pinned (blocker D). ~~but note blocker E: multistart is the
  configuration that passes ADR-221's gate AND the one that fails the
  cross-thread axis. Pinning it is necessary and not sufficient.~~
  **CORRECTED 2026-09-14 (ADR-226 decision 1): that sentence is now factually
  wrong.** Post-7h, `multistart(9)` passes the cross-thread axis too — `eta`
  `0.356 → 1.554e-03`, `edf_total` `10.0 → 0.0816` (~229x / ~123x), with
  `12.9x`/`12.3x` margin on ADR-221's gate. It is the configuration that passes
  **both** axes, and the first ever to. Pinning it remains necessary; what makes
  it not sufficient is now **Anchor W6**, not blocker E.
- **On `analytic_gradient=True`:** this originally read "only once slice 7f has
  resolved the `ftol` early-exit". **7f is DONE and did NOT resolve it**
  (ADR-222): it shipped `max_gtol_restarts` as a measured partial mitigation
  (KKT residual `2.09 -> 0.489`) and re-aimed the real fix at 7g/7h/8. So the
  original condition has no outcome to wait for. Restated: take
  `analytic_gradient=True` with `max_gtol_restarts` set, read
  `max_abs_projected_gradient` rather than `converged`, and record both — **a
  page that silently reports a non-converged fit is still worse than a slow
  one**, and `converged` alone does not carry that information (ADR-222
  finding 5).
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
  - `[judgement]` The recommendation records that the interim pairing is
    **already accepted** (open question 2, maintainer 2026-09-05) subject to
    its two conditions, and points at "The band: desired end state" — so this
    slice decides whether to draw a band at all, not whether the pairing is
    permissible.
- **Out of scope:** fixing coverage. That is `PLAN_penalized_mi_surface.md`'s
  standing BLOCKER and is not this epic's to close.

### The band: desired end state (discharges open question 2's condition (a))

**This section exists so a future epic can pick the band up without
re-deriving why it was left alone.** The maintainer accepted the interim
pairing on 2026-09-05 on condition that the end state be written down and the
old band be labelled a stop-gap. It is registered here, owned by no epic yet,
and is NOT work this epic performs.

**What "done" looks like.** One estimator produces both the surface and its
interval, the interval covers at its nominal rate uniformly in age, and the UI
claim traces to a committed ledger row for both. Concretely:

1. **One producer, not two.** The interim state has the parity engine drawing
   the surface while `TensorMIModel`'s band draws the interval — two
   estimators on one chart, whose only guarantee of mutual coherence is that
   nobody has measured the incoherence. The end state has the band derived
   from the same fit as the surface.
2. **Coverage uniform in age, at nominal.** The measured failure is not
   average coverage; it is the age profile. Penalized variants hold near
   nominal in the interior and fall to **0.68–0.72 at ages ≥80** against a
   nominal 0.95 — worst exactly where a reinsurer reads mortality improvement
   most carefully. Coverage within Monte-Carlo error of nominal across the age
   range, on both the age-flat and age-varying truths, is the target.
3. **Measured on both truths over the committed seeds** (1000..1199), so the
   result is comparable to `MEASUREMENT_unconditional_coverage.md` rather than
   starting a fresh incomparable series.
4. **Reproducible under the convergence definition** the maintainer set on
   2026-09-05 — a band computed from an irreproducible fit inherits its
   irreproducibility.

**Why it is not simply "switch the band on."** The intuitive move — re-point
the interval to the penalized estimator alongside the surface — makes the page
**worse**: it trades a 0.9586-covering band for one measured at 0.7815 on the
same truth and seeds, and 0.68–0.72 at the ages that matter most. That
inversion is the single least obvious finding in this document and the reason
Anchor W2 exists.

**Known dependency.** The underlying gap is `PLAN_penalized_mi_surface.md`'s
standing BLOCKER, whose slices 6–7 are PARKED. **The maintainer declined to
assign an owner on 2026-09-05 ("None for now")**, so this end state is
registered as a target without a scheduled path to it — deliberately, and
recorded so the absence is legible rather than looking like an oversight.

**Stop-gap labelling (condition (b)).** Wherever the interim pairing appears —
slice 3's flag documentation, slice 5's UI claim, and any surface that renders
it — the old band is to be described as a **stop-gap pending a coverage-correct
interval**, never as the intended design. Slice 5's DoD carries this.

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
  - `[judgement]` **If the interim pairing is what ships, the UI describes the
    band as a stop-gap pending a coverage-correct interval** — open question
    2's condition (b), maintainer 2026-09-05. The wording says the interval is
    not produced by the validated path AND that this is temporary by design,
    pointing at "The band: desired end state". A reader must not be able to
    infer the interval was chosen.
  - `[judgement]` **The Anchor W6 gate is stated as met, with the evidence** —
    the target spec's parity reading and its ledger row — or the claim does
    not ship. This is a client-facing surface.

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

1. ~~**Does reproducibility gate the UI claim?**~~ — **RESOLVED 2026-09-05,
   and against the recommendation this plan originally made.** It was recorded
   as unresolved, with a recommendation that reproducibility gate slice 5 (the
   published claim) but not slices 1-3 (the wiring). ADR-222 amendment 1 then
   measured it: the instability reaches the fitted **surface** (`eta`, `edf`),
   not only the smoothing parameters, so it bears directly on the WIRING. It
   now gates slice 3 via blocker E, and slice 5 as well. The original
   recommendation was wrong because it assumed a machinery-only defect.
   **Status 2026-09-14: that gate is SATISFIED, not withdrawn.** ADR-226
   measured the reproducibility this question demanded — `multistart(9)` passes
   both axes — so blocker E no longer holds slice 3. The *principle* stands:
   reproducibility does gate the wiring, and it is now met rather than waived.
2. ~~**Is a validated surface with an unvalidated band acceptable as an interim?**~~
   — **RESOLVED 2026-09-05, maintainer: YES, with two conditions.** The
   pairing is accepted as an interim *provided* (a) **the desired end state is
   documented for a future epic to pick up** — see "The band: desired end
   state" below, which exists to discharge this — and (b) **the old band is
   labelled a stop-gap wherever it appears**, not presented as the intended
   design. Slice 4's DoD carries both as `[machine]`/`[judgement]` criteria.
   The trade the maintainer accepted is narrow: the surface improves while the
   interval stays exactly as good (or bad) as today's. It is NOT an acceptance
   of the coverage gap, which remains a standing BLOCKER.
3. ~~**Does this epic outrank the parity epic's remaining slices?**~~ —
   **RESOLVED 2026-09-05, maintainer: PARITY FIRST, and the gate is stated on
   the model rather than on the epic.** *"We have a targeted model
   specification that needs acceptable parity before we wire anything to the
   client facing dashboard (or other surfaces)."* Three consequences, and the
   third is wider than this epic:
   - **The gate is parity on the TARGET model specification**, not parity on
     the engine in general. That is what slice 1 measures, so slice 1 is not
     merely "permitted in parallel" — it is on the critical path to the gate
     itself, and is the evidence the gate consumes.
   - **Slice 3 waits on two independent conditions**, not one: acceptable
     parity on the target spec (this decision) AND parity slice 7h (blocker E).
     Neither implies the other — 7h buys reproducibility, this gate buys
     agreement — and both must hold. **UPDATE 2026-09-14: the 7h condition is
     now MET (ADR-226), so this gate is down to the first alone.**
   - **The gate binds every client-facing surface, not just the dashboard.**
     Recorded as **Anchor W6** below so it cannot be read as a
     dashboard-only constraint.

   *Reading flagged for correction:* the decision states the gate, not the slice
   ordering, so the ordering above is this plan's reading of it. If slice 1 was
   meant to wait as well, say so and it will be re-gated.
