# CONTINUATION: mgcv capability ladder (L1–L5)

**Plan:** `docs/PLAN_mgcv_capability_ladder.md`
**Created:** 2026-09-19, by the session that started slice 1 — as the plan's §3
requires, and not before (the one-active-epic rule).
**Status:** **ACTIVE.** Slice 1 in progress.

---

## Slice status

| slice | rung | status |
|---|---|---|
| **1** | **L1** `gaussian(identity)` | **IN PROGRESS** — family built and closed-form verified; `mgcv` measurement NOT yet taken |
| 2 | L2 `bs="re"` | not started |
| 3 | L5 scale-estimated REML | not started |
| 4 | L3 factor-`by` | not started |
| 5 | L4 unpenalized parametric block | not started |

---

## Slice 1 — what has landed, and what has not

### Landed

- **`gam_family.gaussian_identity()`** — identity link, `V(mu) = 1`,
  `V'(mu) = 0`, `dispersion_fixed=False`.
- **Registered** in `gam_model._FAMILY_LINKS` as `("gaussian", "identity")`, so
  `ModelSpec(family="gaussian", link="identity")` now resolves where it
  previously raised.
- **12 closed-form tests** in `tests/test_analytics/test_gam_family.py`. These
  compare against **the algebra, not against a reference**:
  - unpenalized IRLS ≡ OLS (`lstsq`), to `1e-12`;
  - penalized IRLS ≡ the closed-form ridge `(X'X + S)^-1 X'y`, to `1e-12`, and
    again across `log10(lambda) ∈ {-4, 0, 4, 8}` so a penalty-scaling error
    cannot hide at `lambda = 1`;
  - observed ≡ expected Hessian weight (canonical link ⇒ Wood's `alpha_i ≡ 1`);
  - `d2mu_deta2` exactly zero, `V(mu)` exactly one;
  - the deviance's factor-of-2 convention, pinned so nobody "fixes" it;
  - `n_iter <= 2`, the property that makes L1 the diagnostic floor.

### NOT landed — and slice 1 is not done without it

- **No `mgcv` measurement has been taken.** The plan's acceptance for this slice
  is Stage B `eta` + `edf_total` against `mgcv::gam(..., method="REML")` at
  **fixed `sp`**, on ADR-221's committed criterion, **tier 3**. That needs an R
  probe, a conformance module with a declared `VerificationClaim`, and a
  `mgcv-conformance.yml` step.
- **`MGCV_FEATURE_COVERAGE.md` §2.2's `gaussian(identity)` row has NOT moved.**
  Per the plan's §4 and the coverage file's §6, *a rung that lands without its
  row moving has not landed.* The row moves in the same PR as the measurement,
  and it must read **"fixed `sp` only"** until slice 3.

---

## Carried constraints — read before touching slice 1

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

---

## Open questions for the maintainer

None blocking. The plan's L5-at-slice-3 ordering was confirmed 2026-09-18 and
its justification rewritten in `2dec2a4`.

---

## Where to pick up

`docs/PLAN_mgcv_capability_ladder.md` §3, slice 1, **"Measure"**. The build half
is done; the measurement half is untouched. Nearest template for the whole
shape — R probe, conformance module, claim, workflow step — is
`gam_multiterm_conformance.py` + `scripts/gam_multiterm_probe.R`, which fits at
**fixed `sp`** and is therefore the right one to copy rather than any of the
free-`sp` ones.
