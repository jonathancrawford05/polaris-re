# CONTINUATION: mgcv capability ladder (L1–L5)

**Plan:** `docs/PLAN_mgcv_capability_ladder.md`
**Created:** 2026-09-19, by the session that started slice 1 — as the plan's §3
requires, and not before (the one-active-epic rule).
**Status:** **ACTIVE.** Slice 1 complete; slice 2 (`bs="re"`) not started.

---

## Slice status

| slice | rung | status |
|---|---|---|
| **1** | **L1** `gaussian(identity)` | **DONE** (2026-09-19, ADR-229) — family built, closed-form verified, and measured against `mgcv` at **tier 3**. **Fixed `sp` only** |
| 2 | L2 `bs="re"` | not started |
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

## Carried constraints — read before touching slice 2

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

---

## Open questions for the maintainer

None blocking. The plan's L5-at-slice-3 ordering was confirmed 2026-09-18 and
its justification rewritten in `2dec2a4`.

---

## Where to pick up

`docs/PLAN_mgcv_capability_ladder.md` §3, **slice 2 — L2 `bs="re"`**. Slice 1 is
closed (ADR-229).

Nearest template for the whole shape — R probe, conformance module with a
declared claim, workflow probe step + compare step + path filters, tier-3
dispatch — is now **slice 1 itself**: `scripts/gam_gaussian_probe.R` +
`src/polaris_re/analytics/gam_gaussian_conformance.py` +
`tests/test_analytics/test_gam_gaussian_conformance.py`. It fits at **fixed
`sp`**, which is the right shape to copy rather than any of the free-`sp` ones.

One thing slice 1 did that is worth repeating at L2: `bs="re"`'s penalty is the
identity and its `edf` has a closed form, so the comparison will likely also
land near machine precision. **A near-exact agreement is a suspicion before it
is a result** — slice 1's two independence tests (strip every `mgcv`-produced
key; check the quantity moves with `sp`) are what make it reportable, and L2
should carry the same pair.
