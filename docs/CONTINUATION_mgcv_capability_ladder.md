# CONTINUATION: mgcv capability ladder (L1–L5)

**Plan:** `docs/PLAN_mgcv_capability_ladder.md`
**Created:** 2026-09-19, by the session that started slice 1 — as the plan's §3
requires, and not before (the one-active-epic rule).
**Status:** **ACTIVE.** Slices 1 and 2 complete; slice 3 (L5, scale-estimated
REML) not started.

---

## Slice status

| slice | rung | status |
|---|---|---|
| **1** | **L1** `gaussian(identity)` | **DONE** (2026-09-19, ADR-229) — family built, closed-form verified, and measured against `mgcv` at **tier 3**. **Fixed `sp` only** |
| **2** | **L2** `bs="re"` | **DONE** (2026-09-21, ADR-230) — basis built, measured against `mgcv` at **tier 3**, Stage A AND Stage B, **fixed AND free `sp` both landed in this slice** |
| 3 | L5 scale-estimated REML | not started |
| 4 | L3 factor-`by` | not started |
| 5 | L4 unpenalized parametric block | not started |

---

## Slice 1 — what landed

### Built

- **`gam_family.gaussian_identity()`** — identity link, `V(mu) = 1`,
  `V'(mu) = 0`, `dispersion_fixed=False`.
- **Registered** in `gam_model._FAMILY_LINKS` as `("gaussian", "identity")`, so
  `ModelSpec(family="gaussian", link="identity")` now resolves where it
  previously raised.
- **The four `gam_derivatives` registries extended** — `second_deriv_mu_eta`
  and `third_deriv_mu_eta` for the `identity` link, `variance_deriv` and
  `variance_second_deriv` for `gaussian` (all four vanish identically). PR #237
  review [P1-3] caught two of these; sweeping found the other two. A new test
  **walks `_FAMILY_LINKS`** and demands all four entries, so the next family
  cannot be registered without them.
- **13 collected closed-form tests** (10 functions, one parametrised ×4) in
  `tests/test_analytics/test_gam_family.py`. These
  compare against **the algebra, not against a reference**:
  - unpenalized IRLS ≡ OLS (`lstsq`), to `1e-12`;
  - penalized IRLS ≡ the closed-form ridge `(X'X + S)^-1 X'y`, to `1e-12`, and
    again across `log10(lambda) ∈ {-4, 0, 4, 8}` so a penalty-scaling error
    cannot hide at `lambda = 1`;
  - observed ≡ expected Hessian weight (canonical link ⇒ Wood's `alpha_i ≡ 1`);
  - `d2mu_deta2` exactly zero, `V(mu)` exactly one;
  - the deviance's factor-of-2 convention, pinned so nobody "fixes" it;
  - `n_iter <= 2`, the property that makes L1 the diagnostic floor.

### Measured

- **`scripts/gam_gaussian_probe.R`** — `gam_multiterm_probe.R`'s own three-term
  design with `family = gaussian(link = "identity")` and nothing else changed,
  so the family is the only unverified thing in the comparison.
- **`src/polaris_re/analytics/gam_gaussian_conformance.py`** — a declared
  `VerificationClaim`, both quantities `INDEPENDENT`, tolerances **imported**
  from `gam_select_free_sp_conformance` and never redeclared.
- **A `mgcv-conformance.yml` probe step + compare step + path filters**, so the
  measurement re-runs on the pinned digest whenever either side changes.
- **Tier 3 result:** `eta` `2.442e-14`, `edf_total` diff `-7.105e-15`, inside
  ADR-221's `2e-2` / `1.0`. See ADR-229 and the ledger row.
- **10 tests over the conformance module**, including the two that make the
  independence claim checkable rather than asserted: stripping every
  `mgcv`-produced key leaves the fit bit-identical, and `edf_total` moves with
  the penalty.
- **`MGCV_FEATURE_COVERAGE.md` §2.2 Stage B** now reads ✅ tier 3, **fixed `sp`
  only** — the two claims in that row moved at different times on purpose:
  `expressible?` when the registration landed, Stage B when this measurement
  did. (PR #237 review [P1-2]: holding the whole row was under-claiming, the
  opposite drift from over-claiming Stage B. Both are drift.)

---

## Slice 2 — what landed

### Built

- **`gam_basis_re.re_basis(group, n_levels)`** — the entire construction is a
  0/1 level-indicator design plus `numpy.eye(n_levels)`. No knot recipe, no
  rescaling, no constraint step: every one of `gam_basis_cr`'s four
  construction stages collapses to nothing for this basis.
- **`TermSpec` gains `basis="re"`** — one factor variable, no `k`, `n_levels`
  **required** (the mgcv asymmetry the OTHER way from `sz`, where `n_levels`
  is optional).
- **`gam_model.assemble_model_design`'s dispatch extended** for `"re"`,
  alongside `cr`/`ti`/`sz`.
- **`gam_stage_a.build_python_re_term` + `RE_BASIS_CLAIM`** — the Stage-A
  independent producer, plus two new `gam_term_extract.R` cases
  (`re-4level`, `re-7level`).
- **`gam_re_conformance.py`** — Stage B, TWO claims: `RE_FIXED_SP_CLAIM`
  (`gaussian(identity)`, fixed `sp`, same reasoning as ladder slice 1) and
  `RE_FREE_SP_CLAIM` (`poisson(log)`, free `sp` — chosen specifically so this
  half does not wait on rung L5, per the plan's own instruction for this
  slice).
- **Verified first, before any code**: `smoothCon(s(fac, bs="re"),
  absorb.cons=TRUE)` and `absorb.cons=FALSE` return bit-identical `$X`, and
  `nrow($C) == 0` regardless — `mgcv` absorbs NO constraint on a `"re"` term
  at all. So the Stage-A claim names one `mgcv` producer, not two.
- Closed-form unit tests (`test_gam_basis_re.py`) against the algebra
  (indicator matrix structure, identity penalty, full rank, width = `n_levels`
  regardless of the observed level count).

### Measured

- **Stage A** (`re-4level`, `re-7level`): `max_abs_design_diff` /
  `max_abs_S_diff` / `rank_diff` all **exactly** `0.000e+00` / `0.000e+00` /
  `0`, tier 3. No continuous construction step exists for either side to
  differ about.
- **Stage B fixed `sp`** (`gaussian(identity)`, `n=900`, `n_levels=6`):
  `max_abs_eta_diff = 2.176e-14`, `edf_total_diff = 1.066e-14`, tier 3.
- **Stage B free `sp`** (`poisson(log)`, `n=900`, `n_levels=6`, `p=19`,
  single-start — no `multistart` needed): `max_abs_eta_diff = 3.226e-05`,
  `max_abs_log10_sp_diff = 0.0010`, `edf_total_diff = -0.0010`,
  `at_bound=False`, `converged=True` on both sides, tier 3.
- **Both regimes `agrees=True`** under ADR-221's imported `2e-2`/`1.0` gate.
  Run [35553707543](https://github.com/jonathancrawford05/polaris-re/actions/runs/35553707543),
  oracle `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`,
  R 4.6.1 / mgcv 1.9.4.
- **The same suspicion-not-just-a-check pair slice 1 used**, now run on both
  Stage-B regimes: every `mgcv`-produced key stripped from the payload leaves
  the Polaris fit bit-identical, and `edf_total` strictly falls when the
  `"re"` block's own fixed `sp` is raised.
- **`MGCV_FEATURE_COVERAGE.md` §2.1's `re` row** moves from **NO** to
  **yes**, Stage A ✅ tier 3 (exact), Stage B ✅ tier 3 **fixed AND free
  `sp`** — the first basis in this epic to land both regimes in the slice
  that introduced it.

**What was NOT deferred, contrary to the usual pattern.** `sz` (slice 6 of the
predecessor epic) shipped Stage A only, then fixed-`sp` Stage B, then never
reached free `sp` — three separate landings, and the last one never happened
(deprioritised to L11). `bs="re"`'s free-`sp` half was reachable in the SAME
session because `poisson(log)`'s free-`sp` search was already verified
elsewhere in this epic and does not share Gaussian's free-scale blocker, so
this slice measured all three (Stage A, Stage B fixed, Stage B free) rather
than registering a follow-up letter-suffix slice.

---

## Carried constraints — read before touching slice 3

These were written for slice 1 and **all five still hold**; 1 and 3 are what
slice 1's acceptance was actually held to.

1. **Fixed `sp` only, and say so.** `gam_reml.reml_score_general` raises when
   `family.dispersion_fixed` is `False` (`gam_reml.py:263`), and Gaussian has a
   free scale. Free `sp` is blocked until L5 (slice 3). Slice 1's acceptance
   criteria must state this rather than claim a rung it did not climb.
   `test_gaussian_estimates_its_scale` asserts the premise, so if it ever flips
   the plan's §2.2 argument is void and must be re-derived.
2. **No new tolerance.** ADR-221's `eta`/`edf_total` bounds are **imported**,
   never redeclared — Anchor W5 forbids re-gating. Follow
   `gam_production_mi_conformance.py`'s import of
   `_AGREEMENT_TOLERANCE_ETA`/`_EDF`.
3. **Tier 3 or it did not happen.** A local apt-R reading is a hypothesis
   (`ROUTINE_MGCV_PARITY.md`); only the pinned digest settles it.
4. **The `eta` offset trap.** Read `m$linear.predictors`, **never**
   `predict(type="link")` — the latter drops an argument-supplied offset and has
   already produced one `1.9751`-against-`2e-2` false reading in this epic. The
   existing probes carry a tripwire; copy it.
5. **`REFERENCE_INTERNAL` exists now** (ADR-228, PR #236). Slice 1's comparison
   is Polaris-vs-`mgcv`, so its quantities are `INDEPENDENT` — but if any
   `mgcv`-vs-`mgcv` column is added, it takes the new member, not `INDEPENDENT`.
6. **L5 now unblocks TWO families, not one** — and the reach split across the
   registry is **the free scale, not the count/binary divide**.
   `quasipoisson(log)` and `gaussian(identity)` both carry
   `dispersion_fixed=False`; the other three are `True`. Slice 1 made Gaussian
   the second such family and thereby falsified the plan's own *"the only
   registered family"* wording, now amended. Slice 3 should size L5 against both.
   Verify by execution rather than by reading — walking `_FAMILY_LINKS` and
   printing `dispersion_fixed` is two lines, and it is how PR #237 review
   [P1-C] was confirmed.

---

## Open questions for the maintainer

None blocking. The plan's L5-at-slice-3 ordering was confirmed 2026-09-18 and
its justification rewritten in `2dec2a4`.

---

## Where to pick up

`docs/PLAN_mgcv_capability_ladder.md` §3, **slice 3 — L5 scale-estimated
REML**. Slices 1 and 2 are closed (ADR-229, ADR-230).

Slice 3 is the epic's least-measured estimate (§2.1: sized on inspection, not
on measurement) and sits on the critical path to L9/L10. Its own deliverable
includes **removing the "fixed `sp` only" qualifier from ladder slice 1's own
coverage row IN SLICE 3'S PR** (`PLAN_mgcv_capability_ladder.md` §3, slice 3's
own acceptance) — that is not a follow-up, it is the point of pulling L5
forward. `quasipoisson(log)` and `gaussian(identity)` are the two
`dispersion_fixed=False` families it unblocks (constraint 6 above);
`gam_reml.reml_score_general`'s raise at `gam_reml.py:263` is where the
free-scale REML criterion needs to replace it.

Nearest template for the whole basis-plus-conformance shape — R probe,
conformance module with a declared claim, workflow probe step + compare step
+ path filters, tier-3 dispatch — remains **slices 1 and 2**:
`scripts/gam_gaussian_probe.R` / `gam_re_probe.R` / `gam_re_free_sp_probe.R` +
`src/polaris_re/analytics/gam_gaussian_conformance.py` /
`gam_re_conformance.py`. Slice 2's own module is the one to copy for a
FREE-`sp` measurement specifically (`RE_FREE_SP_CLAIM`'s shape), since slice
1's own template is fixed-`sp` only.

**A near-exact or exact agreement is a suspicion before it is a result** —
both slices 1 and 2 needed the same pair of independence tests (strip every
`mgcv`-produced key; check the compared quantity moves with the thing under
test) to make their agreements reportable rather than merely green. Any new
slice landing a near-exact reading should carry the same pair.
