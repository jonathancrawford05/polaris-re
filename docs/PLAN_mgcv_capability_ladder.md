# Plan: climb the mgcv capability ladder — L1 through L5

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
2026-09-16 (ADR-227 amendment 1) and its slices 2–5 sit behind this epic.
**Total slices:** **5**, covering ladder rungs **L1–L5**.
**Estimated scope:** ~6–9 dev-days autonomous, plus tier-3 dispatches. Slices 1,
2 and 5 are small; slice 3 is the one with real numerical content.

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

## 2. Rung order versus slice order — and the one dependency that separates them

The ladder numbers rungs by **capability dependency**: each rung is verifiable
with the rungs below it already trusted. Slice order adds a second
consideration — **what unblocks what soonest** — so the two are not identical
here, and that is deliberate rather than an oversight:

| slice | rung | why here rather than in rung order |
|---|---|---|
| 1 | **L1** `gaussian(identity)` | first, as the ladder has it — but **fixed `sp` only**, see the blocker below |
| 2 | **L2** `bs="re"` | unchanged; its free-`sp` search runs under an already-supported fixed-dispersion family, so it does **not** wait on slice 3 |
| 3 | **L5** Scale-estimated REML | **pulled forward from rung 5.** It is what closes slice 1's own gap, and leaving that gap open across three more slices is how a known limitation becomes a forgotten one |
| 4 | **L3** factor-`by` | unchanged in substance, just later in the running order |
| 5 | **L4** Unpenalized parametric block | last because it is the one rung whose value is entirely about the *target formula*, not about the basis suite |

**This does not renumber the ladder.** `MGCV_FEATURE_COVERAGE.md` §4 keeps L1–L11
as written; PR #235 spent a finding on six cross-references left pointing at a
renumbered rung, and the cure is to not renumber.

### The blocker, stated before it is discovered the expensive way

`gam_reml.reml_score_general` **raises** when `family.dispersion_fixed` is
`False` (`gam_reml.py:263`). Gaussian has an unknown scale. Therefore:

> **L1 at free `sp` is blocked by L5.** Slice 1 can verify `gaussian(identity)`
> at **fixed `sp`** and nothing more. It must say so in its own acceptance
> criteria rather than claim a rung it did not climb.

This is written here, at the top, on purpose. Blocker A of the wiring epic was a
premise nobody tested for two weeks; the antidote is to state a dependency where
the plan is read, and to have already checked it in the code rather than recalled
it. The citation above is the check.

---

## 3. The slices

Each slice is one PR. A slice is DONE when its coverage row has moved, not when
its code lands — see §4.

### Slice 1 — L1 `gaussian(identity)` at fixed `sp`

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

### Slice 2 — L2 `bs="re"`

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

### Slice 3 — L5 Scale-estimated REML

**Why pulled forward.** It closes slice 1's own gap, and it unblocks four
families at once — Gaussian, quasi-Poisson, Gamma, Tweedie. `quasipoisson_log`
is already registered and already unusable at free `sp` for this reason, which is
why the coverage table has carried a ⚠️ against it rather than a tick.

**Build:** the free-scale REML criterion, replacing the raise at
`gam_reml.py:263`.

**Measure:** the REML score itself against `mgcv`'s, then slice 1's Gaussian
recipe re-run at **free** `sp`.

**Acceptance:** ADR-221 on the re-run, tier 3. Slice 1's coverage row loses its
"fixed `sp` only" qualifier **in this slice's PR** — that is the deliverable, not
a follow-up.

### Slice 4 — L3 factor-`by`

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

### Slice 5 — L4 Unpenalized parametric block

**Why last, and why it is not optional.** The target formula opens with
`FaceSize + Smoke + FaceSize:Smoke`. `assemble_model_design` builds an intercept
and then penalized terms only — there is no route for parametric *columns* at
all, so the target formula is inexpressible for this reason quite independently
of any basis. (This was wiring slice 1c, re-homed here by ADR-227 amendment 1.)

**Build:** unpenalized columns in the assembled design, outside the penalty
block structure.

**Measure:** Stage B against a `mgcv` fit carrying the same parametric terms.

**Acceptance:** ADR-221, tier 3.

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

| rung | why not here |
|---|---|
| **L6** `bs="fs"` | maintainer-requested and real, but it consumes a margin and the margin axis is not finished — `tp` (L7) is still absent |
| **L7** `bs="tp"` | mgcv's **default** basis and the largest single coverage gap, but eigen-decomposition of the thin-plate penalty is its own slice-sized numerical problem |
| **L8** `te` + `t2` | checked jointly with the already-verified `ti`; cheap given `ti`, but it sits above the marginal axis |
| **L9–L10** `fREML`, `bam` + `discrete` | objective item 2, and `bam` is a different algorithm rather than a faster `gam`. Its own epic — **scheduled, not deferred indefinitely** |
| **L11** `sz` free-`sp` | deprioritised by the maintainer 2026-09-16 (*"not absolutely necessary… we come back for it"*); its penalty count grows one per factor level |

A successor epic covering L6–L8 is the expected follow-on. It is not registered
here, because registering slices nobody has sized is how slice 1b happened.

---

## 6. Risks

1. **L5 is sized "medium" on inspection, not on measurement.** The free-scale
   REML criterion is the one place in this epic where the estimate could be wrong
   by a multiple. If slice 3 runs long, slices 4 and 5 are independent of it and
   can proceed — but slice 1's coverage row stays qualified until it lands, and
   that qualifier must not quietly disappear.
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
