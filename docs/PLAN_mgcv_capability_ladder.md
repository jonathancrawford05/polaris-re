# Plan: climb the mgcv capability ladder — L1 through L5, reopened for a narrow near-term target formula

> **STATUS: IN PROGRESS (REOPENED 2026-09-27) — Slice 6 DONE 2026-09-28 (ADR-234); Slice 3b DONE 2026-09-30 (ADR-235); NEXT: Slice 7.** L1-L5 (the
> original five slices) are COMPLETE — ADR-229 (L1), ADR-230 (L2), ADR-231
> (L5), ADR-232 (L3), ADR-233 (L4). `docs/MGCV_FEATURE_COVERAGE.md` §4 marks
> all five rungs climbed. **Nothing about Slices 1-5 or their ADRs changes
> below — this reopening only appends.** Slices 6-7 are registered below and
> this is this epic's own next work — **not a queue-empty state.**

> **REOPENED 2026-09-27, maintainer direction.** The maintainer's own
> near-term dev target is a formula built from `cr` + `re` (+ already-verified
> `ti`) — **not** the L6-L11 breadth track this plan's §5 names as the
> expected follow-on — plus quasi-Poisson dispersion handling in BOTH modes
> mgcv supports: estimated and externally-supplied/fixed. Two things justify
> reopening this file rather than starting a separate epic: (1) the new work
> is compositional/family-axis, not a new basis, so it does not fit
> `MGCV_FEATURE_COVERAGE.md`'s own "L-rung" numbering without distorting it,
> and (2) every piece of harness this needs — the R-probe/conformance-module/
> workflow-step shape, the provenance discipline, the ADR-221 gate — is this
> epic's own, freshly exercised five times. Splitting it into a new plan file
> would duplicate scaffolding this file already has. **L6-L11 are not
> abandoned** — they remain named in §5, now explicitly BEHIND Slices 6-7
> rather than immediately next, because the maintainer's actual target
> formula touches none of `fs`/`tp`/`te`/`t2`/`bam`/`sz`-free-`sp`. See the
> new §2.3 below for the full reasoning and `docs/CONTINUATION_mgcv_capability_ladder.md`
> for the reopening's own record.

> **This epic exists because feature coverage stopped moving.** The last nine
> registered slices of `PLAN_mgcv_parity_engine.md` — 7b through 8 — are all
> outer-optimiser work on **one N=7 structure**, while the stated objective is
> *"really any hierarchical gam (or bam) specification in mgcv"* and the target
> formula carries 13–21 penalty blocks. The engine today expresses **3 of ~14
> mgcv bases** and cannot express a bare `s(x)`. `MGCV_FEATURE_COVERAGE.md` §3
> makes that case with the numbers; this plan is the response to it.

**Source:** maintainer direction, 2026-09-18 — *"I will merge the PR once you
confirm that the next epic will be the ladder."* This is the decision the
PR #235 body and its review both flagged as owed: the ladder existed as a map
with no plan behind it, so the one-active-epic slot had no epic in it.
**Predecessors:** `docs/MGCV_FEATURE_COVERAGE.md` (the ladder itself, §4 — this
plan does not restate it, it sequences it); `docs/MGCV_NOTATION_PRIMER.md` (what
the notation denotes, with its assertion probe); `PLAN_mgcv_parity_engine.md`
(the engine, the conformance harness and every rung already standing).
**Demotes:** nothing. `PLAN_gam_production_wiring.md` was already demoted
2026-09-16 (ADR-227 amendment 1) and its slices 2–5 sit behind this epic. The
L6-L11 breadth rungs (§5) are not demoted either — they are simply no longer
next, per the reopening above.
**Total slices:** **7** — the original **5**, covering ladder rungs **L1–L5**
(closed), plus **Slices 6-7**, added 2026-09-27 for the narrow target
formula's own composition and dispersion-handling gaps (neither is a new
L-rung — see §2.3).
**Estimated scope:** ~6–9 dev-days autonomous for Slices 1-5 (spent), plus
tier-3 dispatches. Slices 6-7 are each small-to-medium and unsized in detail
until their own MEASURE FIRST step runs — see each slice's own text for why.

---

## 1. The objective, unchanged and restated only to fix the target

From `MGCV_FEATURE_COVERAGE.md` §1, in the maintainer's words:

> 1. **mgcv parity for a suite of model forms**, including `ti`, `s(..., bs='re')`, etc.
> 2. **`fREML` and `discrete=TRUE` as well as `bam`** are also desirable for efficient fitting.
> 3. **`select=TRUE`** helps to incorporate credibility into parameter estimates automatically.

Item 3 is **done**. Item 2 is rungs L9–L10 and is **not in this epic**. This epic
is item 1, from the bottom.

**The dashboard is not a target.** It may be re-pointed later as a *consequence*
of the ladder, never as a driver. §5 of the coverage file records what that
confusion already cost.

---

## 2. Rung order versus slice order — why L5 runs third

The ladder numbers rungs by **capability dependency**: each rung is verifiable
with the rungs below it already trusted. Slice order here departs from it in one
place — **L5 runs third, ahead of L3 and L4** — and the reasoning is set out in
full below, including the argument against, because a sequencing choice stated as
if it were a derivation is the failure mode this epic's predecessor died of.

| slice | rung | |
|---|---|---|
| 1 | **L1** `gaussian(identity)` | first, as the ladder has it — but **fixed `sp` only**, see the blocker below |
| 2 | **L2** `bs="re"` | unchanged; its free-`sp` search runs under an already-supported fixed-dispersion family, so it does **not** wait on slice 3 |
| 3 | **L5** Scale-estimated REML | **pulled forward from rung 5** — see §2.1 |
| 4 | **L3** factor-`by` | unchanged in substance, just later in the running order |
| 5 | **L4** Unpenalized parametric block | last because it is the one rung whose value is entirely about the *target formula*, not about the basis suite |

**This does not renumber the ladder.** `MGCV_FEATURE_COVERAGE.md` §4 keeps L1–L11
as written; PR #235 spent a finding on six cross-references left pointing at a
renumbered rung, and the cure is to not renumber.

### 2.1 Why L5 runs third

> **What this argument is NOT.** An earlier revision of this plan justified the
> position by the L1 dependency alone — *"L5 closes slice 1's gap, and a gap left
> open across three slices gets forgotten."* **That argument does not hold**, and
> it is recorded here rather than quietly replaced. The blocker below is real,
> but it only establishes *L5 after L1*, which every candidate ordering satisfies.
> Nothing in slices 2, 4 or 5 needs Gaussian free-`sp`: L2, L3 and L4 all take
> their free-`sp` exercise under Poisson or binomial, both fixed-dispersion and
> both already working. The dependency does not order L5 against L3/L4 at all.
> It was a preference dressed as a derivation.

**The two reasons that do hold:**

1. **L5 is on the critical path to L9/L10, not a leaf.** `fREML` is `bam`'s
   criterion and free-scale handling is intrinsic to it, so **objective item 2
   sits behind this rung.** §6 flags L5 as the one item in this epic sized by
   inspection rather than measurement — the estimate could be wrong by a
   multiple. An unmeasured estimate on the critical path is what you want to hit
   **early**: blowing up at slice 3 means replanning with two rungs banked
   instead of four.

2. **It closes a live hole, not a hypothetical one.** `quasipoisson` carries
   `dispersion_fixed=False` (`gam_family.py:264`), is marked **expressible** in
   the coverage table, and **raises** at free `sp` today — the standing ⚠️ in
   `MGCV_FEATURE_COVERAGE.md` §2.2/§2.3. L5 earns its slot independently of
   Gaussian.

   > **Amended 2026-09-19 (slice 1, PR #237).** This read *"the only registered
   > family with `dispersion_fixed=False`… the other three are `True`"*, which
   > was true of a four-entry `_FAMILY_LINKS` and which **slice 1 itself
   > falsified** by registering `gaussian`/`identity` as a second free-scale
   > family. The argument is unaffected — `quasipoisson` is still a live hole
   > whether or not Gaussian exists — but it is now **stronger**, because L5
   > unblocks **two** registered families rather than one.

Supporting this, on the repo's own record rather than on assertion: **`sz` is
what a fixed-`sp` qualifier looks like when it lingers.** Stage A verified,
Stage B fixed-`sp` only since ADR-215/217, free-`sp` never exercised — and it has
now been deprioritised to L11. That is the demonstrated failure mode, not a
worry about one.

**The argument against, stated fairly.** L3 and L4 are **coverage** rungs —
objective item 1, the thing this epic exists for. L5 is **fitting machinery** and
adds no basis. This epic's whole premise (`MGCV_FEATURE_COVERAGE.md` §3) is that
coverage has not moved in two weeks, so a machinery slice at position 3 partly
reproduces the complaint. Someone weighting steady visible coverage over
de-risking should run plain rung order and put L5 last; the ladder itself does
not change either way.

**The call, and it is a judgement not a derivation:** L5 stays at slice 3.
Fail-fast on an unmeasured critical-path item beats banking cheap certain wins,
and reason 2 means the slice pays for itself even if Gaussian never needed it.
The counter-argument is mitigated but not answered — L1 and L2 land first, and L2
is the highest value-to-effort rung on the board, so coverage does move before
the machinery slice.

*(Maintainer-reviewed 2026-09-18: order confirmed, justification rewritten.
PR #235 review round 2 flagged this sequencing for human review.)*

### 2.2 The blocker, stated before it is discovered the expensive way

`gam_reml.reml_score_general` **raises** when `family.dispersion_fixed` is
`False` (`gam_reml.py:263`). Gaussian has an unknown scale. Therefore:

> **L1 at free `sp` is blocked by L5.** Slice 1 can verify `gaussian(identity)`
> at **fixed `sp`** and nothing more. It must say so in its own acceptance
> criteria rather than claim a rung it did not climb.

This is written here, at the top, on purpose. Blocker A of the wiring epic was a
premise nobody tested for two weeks; the antidote is to state a dependency where
the plan is read, and to have already checked it in the code rather than recalled
it. The citation above is the check.

**Note what it does and does not license.** It constrains slice 1's acceptance
criteria — that is its whole job here. It is **not** the reason L5 runs third;
§2.1 says why that is, and says why this was the wrong argument for it.

### 2.3 Reopened 2026-09-27 — why Slices 6-7 outrank L6-L11, stated before it is re-litigated

**Naming note, so this section is not re-litigated by a term collision:**
`MGCV_FEATURE_COVERAGE.md` §1 already uses "the target formula" /
"the concrete reference point" for `hgam_formula` — the full
`bam(..., discrete = TRUE, select = TRUE)` call, which DOES include four
`s(…, bs="sz")` terms. This section is about a DIFFERENT, narrower thing:
the maintainer's near-term dev target. Everywhere below, "target formula"
means **the narrow near-term target formula** — `cr` + `re` (+ `ti`) plus
quasi-Poisson dispersion handling — never §1's `hgam_formula`. This is also
*why* L6-L11 are reordered rather than dropped: §1's own reference formula
still needs `sz`/`bam` eventually, just not for this narrower, nearer-term
piece of work.

`MGCV_FEATURE_COVERAGE.md` §4 names the L6-L11 breadth rungs (`fs`, `tp`,
`te`/`t2`, `fREML`, `bam`+`discrete`, `sz` free-`sp`) as this epic's expected
successor, and §5 below still calls that "the expected follow-on." That is
still true **in general** — it is not true **for the narrow near-term
target formula**, which is built from `cr` + `re` (+ `ti`, already climbed
before this epic existed) and needs quasi-Poisson dispersion handling in both
directions mgcv supports. Checking the narrow near-term target formula
against L6-L11's own membership: **it uses none of them.** `fs`/`tp`/`te`/`t2`
are marginal- or construction-axis bases it never calls; `bam`/`discrete`/
`fREML` are a fitting *algorithm* it does not require; `sz` free-`sp` is a
different basis entirely — all four remain part of §1's own reference
formula, just not this narrower one.

**What the narrow near-term target formula DOES still need that nothing in
this epic or its predecessor has measured:**

1. **`cr` + `re` + `ti` fit jointly, in one model.** Individually verified —
   `cr` (ADR-194), `re` (ADR-230), `ti` (ADR-205/ADR-206) — but never all
   three together. The only scripts that mention `re` and `ti` in the same
   file (`gam_term_extract.R`, `mgcv_penalty_count_probe.R`) extract penalty
   *structure*, they do not fit anything. This is Slice 6.
2. **Quasi-Poisson with an externally-supplied, fixed dispersion** — mgcv's
   `scale = <value>` argument, as distinct from the already-scoped
   "estimate the dispersion" mode (Slice 3b, registered, not yet run).
   Neither mode has a committed measurement today. This is Slice 7.

**Why append here rather than open a new epic.** Both gaps are
*compositional/family-axis*, not a new basis — `MGCV_FEATURE_COVERAGE.md`'s
`§4` ladder table has no row shape for "three already-verified bases, fit
together" or "an existing family, given a fixed instead of profiled scale."
Forcing them into new `L`-numbers would misrepresent what they are. And every
piece of scaffolding they need — the R-probe / conformance-module /
workflow-step / `VerificationClaim` shape, the ADR-221 gate, the tier
discipline — is this epic's own, freshly exercised five times running. A new
plan file would either duplicate that scaffolding narrative or point back
here for all of it, so the slice sequence continues here instead
(`PLAN_gam_production_wiring.md`'s own precedent for extending rather than
forking — see its slices 1b/1c note).

**What this does NOT do:** it does not renumber or deprioritize L1-L5, does
not delete L6-L11 from §5, and does not decide that L6-L11 will never
happen — only that they are not next. If a future target formula needs
`bs="fs"` or `te`, that work is still exactly where §5 leaves it.

---

## 3. The slices

Each slice is one PR. A slice is DONE when its coverage row has moved, not when
its code lands — see §4.

> **There is deliberately no `CONTINUATION_mgcv_capability_ladder.md` yet.** The
> session that starts **slice 1** creates it, the same way
> `PLAN_gam_production_wiring.md` §slice-3 states for its own epic and the
> one-active-epic rule requires. Until then this plan is the whole record: an
> epic with a plan and no state file has not started, and `ACTIVE EPIC` in
> `MGCV_FEATURE_COVERAGE.md` §4 means *next*, not *in progress*. (PR #235 review
> round 2, [P2-5] — the precedent was right but unstated, and an unstated
> convention is the thing this epic's predecessor lost two weeks to.)

### Slice 1 — L1 `gaussian(identity)` at fixed `sp` — ✅ **DONE 2026-09-19 (ADR-229, PR #237)**

**Why first.** At Gaussian identity the penalized fit is a **single linear
solve**: no IRLS iteration at all. That makes it the one regime where a basis or
penalty disagreement cannot hide behind a convergence artifact, which is what
makes every rung above it cheaper to diagnose. It is also what every mgcv
textbook check uses, and it is the simplest family in the library — currently
absent from a four-entry `_FAMILY_LINKS` dict.

**Build:** a `gaussian_identity()` `Family`, registered in `_FAMILY_LINKS`.

**Measure:** Stage B `eta` + `edf_total` against `mgcv::gam(..., method="REML")`
at **fixed `sp`**, on an existing multi-term recipe so the comparison isolates
the family rather than introducing a new design at the same time.

**Acceptance:** ADR-221's committed criterion, tier 3.
**Explicitly NOT claimed:** free `sp`. Blocked by slice 3; the coverage row says
"fixed `sp` only" until then, the way `sz`'s row already does.

### Slice 2 — L2 `bs="re"` — ✅ **DONE 2026-09-21 (ADR-230)**

**Why this is the highest value-to-effort item on the board.** It is named in
objective item 1. It is the **cheapest basis in mgcv**: the model matrix is the
level indicators, the penalty is the identity, and it carries **exactly one
smoothing parameter regardless of level count** (measured — the ladder's L2 row
and `MGCV_NOTATION_PRIMER.md` §4, asserted by
`scripts/mgcv_penalty_count_probe.R`). And it is the backbone of hierarchical
structure: without it, none of the HGAM taxonomy's group-level models (primer §5)
is expressible.

**It is also credibility.** A Bühlmann–Straub random-effects model *is* a GAM
with a ridge penalty over level indicators, and the smoothing parameter *is* the
credibility constant. For an actuarial engine this rung is not a parity
checkbox — it is the mechanism by which experience gets credibility-weighted,
arrived at by estimation rather than by a hand-set Z.

**Build:** an `re` basis producer (design = level indicators, penalty = `I`), its
`TermSpec` dispatch in `assemble_model_design`.

**Measure:** Stage A against `smoothCon(...)`'s own `X`/`S`; Stage B `eta` +
`edf_total` at fixed **and free** `sp`. Free `sp` runs here under an existing
fixed-dispersion family (Poisson-log or binomial), so this slice does **not**
wait on slice 3.

**Acceptance:** ADR-221, tier 3, both `sp` regimes.

**Landed:** Stage A exact (`0.000e+00` on `design_X`/`penalty_S`, `rank_diff
= 0`, at both 4 and 7 factor levels) — `mgcv` was confirmed first, by direct
probe, to absorb NO identifiability constraint on `bs="re"` regardless of
`absorb.cons` (`nrow($C) == 0`, bit-identical `$X` either way), so the claim
names one `mgcv` producer, not two. Stage B fixed `sp` (`gaussian(identity)`,
matching slice 1's own regime): `max_abs_eta_diff = 2.176e-14`,
`edf_total_diff = 1.066e-14`. Stage B free `sp` (`poisson(log)`, chosen so
this half does not wait on slice 3): `max_abs_eta_diff = 3.226e-05`,
`max_abs_log10_sp_diff = 0.0010`, `edf_total_diff = -0.0010`, single-start
sufficed. All tier 3, oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`,
run 35553707543. See ADR-230 for the full measurement and the two
independence tests (strip every `mgcv` key; `edf_total` moves with the `re`
block's own penalty) that make the near-machine-precision fixed-`sp` reading
reportable rather than merely green.

### Slice 3 — L5 Scale-estimated REML

**Why pulled forward — §2.1 in one line:** it is on the critical path to L9/L10
and it is the epic's least-measured estimate, so it is the one to hit early; and
it closes a live hole rather than only Gaussian's. `quasipoisson` carries
`dispersion_fixed=False` (`gam_family.py:264`), is marked expressible, and
raises at free `sp` **today** — the standing ⚠️ in §2.2/§2.3 of the coverage
file. Closing slice 1's own gap is a *consequence* of this slice, not the
argument for its position. (This sentence called `quasipoisson` the **sole**
such family until 2026-09-19; slice 1 registered `gaussian`/`identity` as a
second one, so L5 now unblocks two. See §2.2's amendment note.)

It unblocks four families at once — Gaussian, quasi-Poisson, Gamma, Tweedie —
though only the first two are registered today.

**Build:** the free-scale REML criterion, replacing the raise at
`gam_reml.py:263`.

**Measure:** the REML score itself against `mgcv`'s, then slice 1's Gaussian
recipe re-run at **free** `sp`.

**Acceptance:** ADR-221 on the re-run, tier 3. Slice 1's coverage row loses its
"fixed `sp` only" qualifier **in this slice's PR** — that is the deliverable, not
a follow-up.

### Slice 3b — quasi-Poisson fit-level free-`sp` re-run — ✅ **DONE 2026-09-30 (ADR-235)**

**Landed:** INDEPENDENT, tier 3 (run 36704353339): `eta` diff 4.236e-06, `agrees=True`. See ADR-235.

**Registered 2026-09-26 (PR #240 review), per ADR-209 decision 1** — a gap
opened is closed or registered, never merely filed. Slice 3 closed the
free-scale REML criterion and measured it at the SCORE level for both
free-scale families (`gaussian(identity)`, `quasipoisson(log)`), then lifted
slice 1's "fixed `sp` only" qualifier with a FIT-level free-`sp` re-run —
but only for Gaussian. `MGCV_FEATURE_COVERAGE.md` §2.2 now carries
`quasipoisson(log)` at "✅ tier 3, **score-level only**" — a new, named
half-open state that `CONTINUATION_mgcv_capability_ladder.md`'s carried
constraint 6 flagged as a future item without registering it, which is
exactly the CONTINUATION-note-is-not-a-registration gap ADR-209 exists to
close.

**Build:** none — no new code. `GAUSSIAN_FREE_SP_CLAIM` / `fit_gaussian_free_sp_case`
(`gam_gaussian_conformance.py`, slice 3) is the direct template; the same
shape against `quasipoisson_log()` is the whole slice.

**Release condition:** a `quasipoisson(log)` fit-level free-`sp` measurement
against `mgcv`, tier 3, gated on ADR-221 (imported, not redeclared), with its
own `VerificationClaim` (INDEPENDENT, structurally excluding every
`mgcv`-produced key — same pattern as `GAUSSIAN_FREE_SP_CLAIM`). Lands the
coverage row from "score-level only" to unqualified tier 3, matching
Gaussian's own row.

**Why not folded into slice 3 itself:** found during PR #240's review, after
slice 3 had already landed and its PR body's Definition of Done was
reproduced verbatim from the plan's own text — which named only the score
measurement plus Gaussian's fit re-run for this slice's acceptance. Extending
scope post-hoc inside a landed PR is exactly the "widen on your own"
this project's routines refuse; a registered follow-up slice is the correct
container instead.

### Slice 3c — expose and verify the estimated dispersion, and the two-stage Poisson -> fixed-scale workflow (registered, not started)

**Registered 2026-09-30 (PR #245, maintainer request), per ADR-209 decision 1.**
Slice 3b verified that a free-scale quasi-Poisson FIT agrees with `mgcv`, but
the dispersion estimate itself is not an output: `reml_score_general` computes
`phi_hat = penalized_deviance / residual_df` (`gam_reml.py`) to profile the
scale out of the score and then discards it, `PolarisGAMFit` has no field for
it, and `mgcv`'s `m$scale` is reported by the probe but never compared. The
maintainer needs the estimate as a **product**, not an internal:

> Fit a Poisson model to the dispersed counts, obtain the dispersion estimate
> from it, then supply that estimate as the fixed `scale` when fitting the
> quasi-Poisson model — where the severity of the dispersion justifies it.

**Two separable pieces, one slice:**

1. **Expose and verify the estimate.** Add a `dispersion` (name TBD) to the
   fit result, computed Polaris-side, and compare it INDEPENDENT against
   `mgcv`'s own estimate. **MEASURE FIRST, do not assume which estimator:**
   the `phi_hat` the criterion profiles out is a deviance-based quantity,
   while a Pearson-residual estimate (`sum((y-mu)^2/V(mu)) / (n - edf)`) is the
   classical quasi-Poisson one and is what `mgcv` reports for `quasipoisson`
   by default (`m$scale`; confirm on the probe, and confirm which `scale.est`
   applies under `method="REML"`). They are not the same number. Read
   `mgcv`'s own definition off the pinned image, compare like with like, and
   record the difference between the two estimators if it is not negligible.
   Compare on the slice 3b recipe at tier 3.
2. **The two-stage workflow.** Stage 1: `fit_polaris_gam` under `poisson(log)`
   (scale fixed at 1), extract the Pearson dispersion `phi_hat` from that fit.
   Stage 2: refit with `phi_hat` supplied as a fixed scale — the
   `dispersion_fixed=True` + `gamma=phi_hat` route slice 7 measures against
   `mgcv`'s `scale=`. Verify INDEPENDENT at tier 3 by giving `mgcv` the SAME
   number Polaris produced (`gam(family=quasipoisson, scale=phi_hat)`) and
   comparing the fits; also report how far the two-stage fit lands from the
   joint free-scale fit of slice 3b, since the workflow is a modelling choice
   whose cost is exactly that gap.

**Why the order matters.** Stage 2 is slice 7's mode, so **slice 7 runs first**;
this slice consumes it. (Sequencing: 7 -> 3c.)

**Release condition.** (a) The Polaris-side dispersion estimate is an exposed,
tested output; (b) its comparison against `mgcv`'s estimate is INDEPENDENT at
tier 3 with the estimator definitions stated; (c) the two-stage workflow is
measured at tier 3 against `mgcv` at the same supplied scale, with the gap to
the joint fit reported, and documented as optional/non-standard; (d) the coverage row for `quasipoisson(log)` states
which estimator is exposed.

**Policy, per the maintainer (2026-09-30): no threshold is imposed on users.**
Whether the dispersion is severe enough to justify the two-stage route, or
whether plain Poisson or another family is preferable, is **the user's call**
and this slice does not encode it: no cutoff, no default, no warning that
gates behaviour. The deliverable is that the estimate is **reported** — an
exposed, documented output on the fit — so a user CAN run the two-stage
workflow if they choose. The workflow is **optional and non-standard** (it is
not what `mgcv` does, which estimates the scale jointly); the docs must say so
plainly rather than present it as the recommended path. The slice's gap
report (two-stage vs joint free-scale fit) is information for that user
decision, not a verdict.

### Slice 4 — L3 factor-`by` — ✅ **DONE 2026-09-26 (ADR-232)**

**Note what it is**, because the name misleads: `s(x, by = f)` on a factor is not
a term *parameter* but a term **multiplier**. A 3-level factor produces **three
separate smooths**, each with its own `sp` (measured; primer §4). Numeric `by` is
already done and verified (ADR-200) and is a different construction.

**Build:** a representation for a factor `by`, then its branch in
`assemble_model_design`.

> **Sized on the code, and it is bigger than the coverage file said.** There is
> no half-built route to widen: `TermSpec.by` is documented as a *numeric*
> `by` variable, and `TermSpec.factor` is **not** a factor-`by` flag — it marks
> the `sz`/`fs` construction and is explicitly *mutually exclusive* with `by`
> (`gam_term_spec.py:74-79`), and `sz` already has its branch. So this slice owns
> a contract decision — widen `by` to accept a factor, or add a field — before it
> owns any basis work. `MGCV_FEATURE_COVERAGE.md` §2.1 said otherwise until
> 2026-09-18 and is corrected in this epic's own first commit.

**Measure:** Stage A per generated smooth; Stage B at fixed and free `sp`.

**Acceptance:** ADR-221, tier 3. The block count multiplying with level count is
a property to *verify*, not to work around.

**Landed:** the contract decision is a new field, not a widened `by` —
`TermSpec.by_factor`/`.by_level`, and `gam_term_spec.factor_by_terms` is the
one place a factor-`by` term expands into its `n_levels` separate `TermSpec`s.
Construction measured against `mgcv` before any code (Anchor 8): the shared
no-`by` `cr` smooth built on the WHOLE covariate column (identical across
every level — `mgcv`'s own identifiability constraint for a factor-`by` term
equals the ordinary no-`by` `colMeans` constraint, not a per-level-subset
one, refuted first), then masked to one level AFTER the constraint is
absorbed; the penalty is NOT rescaled per level, unlike `sz`. Stage A: exact
per level (`0.000e+00` at print precision on `design_X`, `penalty_S` and
`rank`, both tiers, 5 levels across 2 cases). Stage B fixed `sp`:
`max_abs_eta_diff=1.510e-14`, `edf_total_diff=-1.421e-14`, tier 3. Stage B
free `sp` (ONE family, `gaussian(identity)`, throughout both regimes — L5
already closed the free-scale blocker, unlike L2's own two-family split):
`max_abs_eta_diff=1.596e-05`, `edf_total_diff=+0.0003`, `agrees=True`, tier
3. No iteration needed at either stage. See ADR-232 and
`docs/CONFORMANCE_LEDGER.md`.

### Slice 5 — L4 Unpenalized parametric block — ✅ **DONE 2026-09-27 (ADR-233)**

**Why last, and why it is not optional.** The target formula opens with
`FaceSize + Smoke + FaceSize:Smoke`. `assemble_model_design` builds an intercept
and then penalized terms only — there is no route for parametric *columns* at
all, so the target formula is inexpressible for this reason quite independently
of any basis. (This was wiring slice 1c, re-homed here by ADR-227 amendment 1.)

**Build:** unpenalized columns in the assembled design, outside the penalty
block structure.

**Measure:** Stage B against a `mgcv` fit carrying the same parametric terms.

**Acceptance:** ADR-221, tier 3.

**Landed:** `TermSpec` gained `basis="parametric"` and a new `levels` field
(one factor-level count per named variable — distinct from the existing
`n_levels`, since an interaction names two or more counts); the design is
`mgcv`'s own `contr.treatment` dummy coding (`gam_basis_parametric.py`), with
the interaction's columns the outer product of each variable's own dummy
block, first-named variable fastest — measured directly against R's
`model.matrix(~A+B+A:B)` before any code was written. Zero penalty blocks are
contributed, which surfaced and fixed a real edge case:
`null_space_penalty` raises on an empty input rather than returning `None`,
so `assemble_model_design`'s `select=True` branch needed a guard for a term
with no existing blocks at all — the first basis this function has ever built
with none. **Stage A** (no fit needed — the block doesn't depend on `sp`/`y`/
the smooth): exact per term (`0.000e+00` at print precision on `design_X`,
all 3 terms of the target formula's own `FaceSize + Smoke + FaceSize:Smoke`),
both tiers, reusing the SAME `compare_term_extract` machinery every other
basis's Stage A uses (the R export already matches `RTermPayload`'s shape).
**Stage B fixed `sp`** (paired with the already-verified `s(AttdAge, k=13,
bs="cr")`, deliberately unrelated to FaceSize/Smoke): `max_abs_eta_diff=
1.066e-14`, `edf_total_diff=-7.105e-15`, tier 3 (tier 1: `2.698e-14` /
`0.000e+00`). **Stage B free `sp`** (ONE family, `gaussian(identity)`,
matching L3/L5 — L5 already closed the free-scale blocker):
`max_abs_eta_diff=3.261e-07`, `edf_total_diff=+0.0000` (tier 1: `+2.45e-05`),
`agrees=True`, tier 3 — the tightest free-`sp` reading this epic has
produced. No iteration needed at either stage. See ADR-233 and
`docs/CONFORMANCE_LEDGER.md`. **This was the last rung the ORIGINAL five-slice
plan named — L1 through L5 are all climbed.** Slices 6-7 below are the
2026-09-27 reopening's own scope (§2.3).

---

### Slice 6 — `cr` + `re` + `ti` joint Stage-B composition — ✅ **DONE 2026-09-28 (ADR-234)**

> Landed as a pure measurement slice (no production code). INDEPENDENT, tier 1 and tier 3 identical in verdict; see ADR-234 and `docs/CONFORMANCE_LEDGER.md`. `select=TRUE` on the composition was not run (target's use of it unconfirmed) — registered below as Slice 6b.

**Why.** The three bases are each independently tier-3 verified (ADR-194,
ADR-230, ADR-205/206), but never fit together in one model. `assemble_model_design`
already dispatches all three independently, so this slice's own first
question is whether MEASURE FIRST finds anything to build at all, or whether
this is purely a measurement gap.

**Build:** none anticipated. If MEASURE FIRST surfaces a real interaction —
for example `re`'s identity-penalty block sized or ordered incorrectly
alongside `ti`'s tensor block under `select=TRUE`'s null-space augmentation —
that finding becomes this slice's actual scope, sized after the probe, not
guessed at here.

**Measure:** a new R probe fitting the shared design
(`s(x1, k=.., bs="cr") + s(fac, bs="re") + ti(x1, x2, k=.., bs="cr")`, or the
caller's real covariates once named) natively in `mgcv`; the Polaris side via
`assemble_model_design` + `fit_polaris_gam`. `gaussian(identity)` first —
decouples the composition check from IRLS convergence, matching every prior
slice's own reasoning for starting there (L1/L5 already closed the free-scale
blocker for it) — then the production family if different. Both fixed and
free `sp`, and under `select=TRUE` if the target formula uses it (confirm
before writing the probe, not after).

**Acceptance:** ADR-221, tier 3, INDEPENDENT on `eta`, `edf_total`, and
per-block `log10(sp)` at free `sp` — same shape as every joint-composition
Stage B in this epic (e.g. ADR-206, ADR-232).

**Depends on:** nothing new — every producer this slice needs already exists
and is independently verified. This is the cheapest possible slice shape:
compose, don't invent.

### Slice 6b — `select=TRUE` on the `cr` + `re` + `ti` composition (registered 2026-09-28, not started)

**Why.** Slice 6's own text said to confirm before writing the probe whether the
narrow target uses `select=TRUE`; that is unconfirmed, so the composition was
measured without it. **Release condition:** maintainer confirms the narrow
target uses `select=TRUE` (a maintainer call, per ROUTINE_MGCV_PARITY.md). If
so: same probe with `select=TRUE` (doubled blocks, ADR-217/218 multistart
caveats apply), ADR-221 gate, tier 3. Also carries the second-null-direction
sparsity note from ADR-234 if the design is shrunk.

### Slice 7 — quasi-Poisson dispersion: externally-supplied/fixed `scale` (the "estimate" mode is Slice 3b)

**Why.** mgcv's quasi-Poisson supports two distinct dispersion modes: `scale`
left unset (estimated from the Pearson residuals, mgcv's default) and
`scale = <value>` (held fixed at a caller-supplied number — used, for
example, when a dispersion estimated on a baseline period is then held
constant while scoring later data against it). **Neither is measured against
`mgcv` today.** The "estimate" mode is Slice 3b (registered 2026-09-26, PR
#240 review, not yet run — see its own entry above; nothing about it changes
here). This entry is the "fixed/supplied" mode, which is not registered
anywhere before this reopening.

**MEASURE FIRST — a hypothesis to verify before writing anything, per this
epic's own discipline (never guess a derivation).** `gam_reml.reml_score_general`'s
known-scale branch (`family.dispersion_fixed=True`) already accepts an
arbitrary `gamma`, and its own validation error states outright that "the
known-scale formula's `gamma` literally substitutes for a FIXED phi"
(`gam_reml.py`, the `dispersion_fixed=False`-and-`gamma!=1.0` raise).
`gam_family.quasipoisson_log()` and `poisson_log()` share the identical
`link`, `variance` and `deviance_terms` — `quasipoisson_log()`'s own
docstring says so — and differ **only** in `dispersion_fixed`. `gamma` is
already threaded, unmodified, all the way from `fit_polaris_gam`'s own public
signature (`gam_model.py`) down through `select_lambdas_continuous` to
`reml_score_general`. Putting those three facts together, the **hypothesis**
is: `fit_polaris_gam(ModelSpec(family="poisson", link="log", ...), data, y,
gamma=phi_fixed)` **already computes** the fixed-dispersion quasi-Poisson fit,
with zero new production code. Verify this at tier 1 first, against `mgcv`'s
own `gam(family=quasipoisson(link="log"), scale=phi_fixed)` (and confirm
whether `mgcv` itself treats `poisson(scale=phi_fixed)` and
`quasipoisson(scale=phi_fixed)` identically once `scale` is fixed — they may
not be the same call in `mgcv`, and that difference, if any, is exactly what
this step exists to catch) — **before** assuming the hypothesis and writing
any conformance code around it. If it holds, this is a measurement slice, not
a construction one. If it is refuted, the refutation is the finding, and it
resizes this slice's own Build section rather than being argued around.

**Build:** if the hypothesis holds — none at the criterion level; likely a
thin `ModelSpec`-level convenience so a caller can ask for
"quasi-Poisson, fixed scale" without needing to know the `poisson`+`gamma`
equivalence, plus the coverage-doc row. If refuted, whatever the probe shows
is missing.

**Measure:** an R probe fitting the shared design under
`gam(family=quasipoisson(link="log"), scale=<fixed value>)` at two values —
one near the data's own naive Pearson-residual dispersion estimate, one far
from it, so the comparison cannot be vacuously close — compared INDEPENDENT
against `reml_score_general`/`fit_polaris_gam` with the corresponding
`gamma`. Score-level comparison is PAIRWISE, matching ADR-231's own
precedent (quasi-likelihood carries no proper additive constant, the same
reason its "estimate" mode is compared pairwise).

**Acceptance:** ADR-221 at the fit level (`eta`/`edf_total`), the ADR-231
pairwise-score convention at the criterion level, tier 3.

**Depends on:** nothing technically (this is the `dispersion_fixed=True`
branch, Slice 3b is the `dispersion_fixed=False` one — different code paths).
Slice 3c (registered 2026-09-30) consumes this slice's mode for its two-stage workflow, so 7 runs BEFORE 3c. Running 3b first is still recommended purely so "the quasi-Poisson story" in
`MGCV_FEATURE_COVERAGE.md` closes in one pass rather than two.

---

## 4. What gates a rung, and what does not

- **ADR-221's committed criterion**, unchanged: `max_abs_eta_diff < 2e-2` **and**
  `abs(edf_total_diff) < 1.0`. **No slice introduces a new tolerance** — Anchor
  W5 forbids re-gating, and a rung that needs a looser bound has not landed.
- **Tier 3 or it did not happen.** A local apt-R reading is a hypothesis
  (`ROUTINE_MGCV_PARITY.md`); only the pinned digest settles it.
- **The coverage row moves in the same PR.** A rung that lands without its row
  moving has not landed — `MGCV_FEATURE_COVERAGE.md` §6, and this epic is the
  first test of that rule.
- **Stage A alone is never done.** `sz` is the standing example: Stage A
  verified, Stage B fixed-`sp` only, free-`sp` unexercised — and its row says so
  rather than showing a tick.
- **A golden baseline is not evidence of correctness.** Goldens are this engine's
  own prior output; they detect change, never correctness (CLAUDE.md §10).
- **Two independent producers or it is not parity.** If the function producing
  one operand takes the other side's payload as an input, the table is a harness
  check and must be titled as one (ADR-193, `VERIFICATION_STANDARD.md`).

---

## 5. Out of scope, named so the boundary is not renegotiated slice by slice

> **Reordered, not removed, 2026-09-27 (§2.3).** These rungs were "the
> expected follow-on" when L1-L5 closed. They still are, in general — just
> not before Slices 6-7, which the narrow near-term target formula needs and
> none of these rungs touch. (§1's own reference formula still needs
> `sz`/`bam` eventually — see §2.3's naming note.)

| rung | why not here |
|---|---|
| **L6** `bs="fs"` | maintainer-requested and real, but it consumes a margin and the margin axis is not finished — `tp` (L7) is still absent |
| **L7** `bs="tp"` | mgcv's **default** basis and the largest single coverage gap, but eigen-decomposition of the thin-plate penalty is its own slice-sized numerical problem |
| **L8** `te` + `t2` | checked jointly with the already-verified `ti`; cheap given `ti`, but it sits above the marginal axis |
| **L9–L10** `fREML`, `bam` + `discrete` | objective item 2, and `bam` is a different algorithm rather than a faster `gam`. Its own epic — **scheduled, not deferred indefinitely** |
| **L11** `sz` free-`sp` | deprioritised by the maintainer 2026-09-16 (*"not absolutely necessary… we come back for it"*); its penalty count grows one per factor level |

A successor epic covering L6–L8 remains a legitimate future follow-on. It is
still not registered here, because registering slices nobody has sized is how
slice 1b happened — and now it is also explicitly behind Slices 6-7 in
priority (§2.3), not merely unsized.

---

## 6. Risks

1. **L5 is sized "medium" on inspection, not on measurement.** The free-scale
   REML criterion is the one place in this epic where the estimate could be wrong
   by a multiple — which is §2.1's first reason for running it third rather than
   last. If slice 3 runs long, slices 4 and 5 are independent of it and can
   proceed — but slice 1's coverage row stays qualified until it lands, and that
   qualifier must not quietly disappear. **If it runs long enough to stall the
   epic, that is the signal to re-plan with two rungs banked**, which is the
   whole point of taking the risk early; it is not a reason to widen slice 3.
2. **Solver convergence may resurface on new block shapes.** Every convergence
   finding this project has (ADR-212 through ADR-220) was measured on `cr`/`ti`
   structures. `re` blocks are differently conditioned. A convergence failure on
   a new rung is a finding about that rung, **not** a licence to re-open the
   outer-optimiser epic mid-ladder.
3. **The temptation to widen.** Each slice's acceptance is one rung. The wiring
   epic's lesson is that a plan quoting something other than the code is a plan
   measuring the wrong thing — so if a slice finds the ladder's own description
   of a rung is wrong, **that is the finding**, and it updates
   `MGCV_FEATURE_COVERAGE.md` rather than being worked around.
