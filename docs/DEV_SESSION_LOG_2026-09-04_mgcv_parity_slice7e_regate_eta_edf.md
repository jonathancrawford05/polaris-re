# Dev session log — 2026-09-04 — mgcv parity, slice 7e: re-gate `eta`/`edf`

**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (scheduled, daily)
**Epic:** `docs/CONTINUATION_mgcv_parity_engine.md` / `docs/PLAN_mgcv_parity_engine.md`
**Slice:** 7e — re-gate `SELECT_FREE_SP_MODEL_CLAIM` on `eta`/`edf`, H-weighted
distance as a companion (ADR-219 amendment 1 decision 4)
**ADR:** ADR-221, amendments 1-2

## Addendum — tier-3 dispatch, a real bug found and fixed, then confirmed

The first tier-3 dispatch (CI run 33870429467) confirmed this slice's
primary deliverable — the `SELECT_FREE_SP_MODEL_CLAIM` re-gate — identical
in verdict to tier 1 (both multistart rows `agrees=True`, both single-start
rows `agrees=False`, at both tiers). It also found a genuine bug: section
(5)'s own-point Hessian loop (new this session) crashed on
`PolarisComputationError` when a finite-difference-perturbed point near
multistart's own converged rho failed to converge — masked at the job
level by a pre-existing `continue-on-error: true`, so only reading the
actual log content (not the API's `conclusion` field) surfaced it. Fixed
with the same `try/except` guard section (3)'s profile scan already
carries; confirmed locally as a no-op on this session's own tier-1 reading;
pushed, and a second tier-3 dispatch (run 33871712927) confirmed both that
the fix works (graceful report, no crash) and that the underlying
non-convergence is a real, reproducible property of where multistart's
search lands on this fixture and oracle build — bit-identical failure
(`deviance 987.13`) across both post-fix tier-3 runs. Single-start's
own-point reading is now confirmed at both tiers; multistart's stays
genuinely unavailable at tier 3, characterised rather than chased further.
Full detail in ADR-221 amendments 1-2 and the corresponding
`docs/CONFORMANCE_LEDGER.md` rows.

**This is exactly the kind of finding the routine's own "what a good
session looks like" section names as a success**: a real, INDEPENDENT
result (the re-gate) confirmed at both tiers, plus an honestly
characterised measurement gap (the multistart own-point reading) rather
than a number quietly promoted past what the evidence supports.

## Setup

- `uv sync --all-extras` — clean.
- Installed the local scratch oracle:
  `apt-get install -y r-base-core r-cran-mgcv r-cran-jsonlite`.
  Recorded versions: **R 4.3.3 / mgcv 1.9.1** — matches the routine's expected
  tier-1 versions exactly.
- Read, in full, before writing code: `docs/ROUTINE_MGCV_PARITY.md`,
  `docs/PLAN_mgcv_parity_engine.md` (Anchors 1/2/8/9, slices 7c-7f),
  `docs/CONTINUATION_mgcv_parity_engine.md` (status block through ADR-220,
  "Open questions"), `docs/CONFORMANCE_LEDGER.md` (slice 7b/7d rows),
  `docs/VERIFICATION_STANDARD.md`, `CLAUDE.md`, `docs/DECISIONS.md`
  (ADR-189+amendments, 190, 191, 192, 193, 219 + amendments 1-4, 220 +
  amendments).

## Work selection

The PLAN's next unchecked slice: **slice 7e**, "re-gate on `eta`/`edf`, with
the H-weighted distance as companion" — REGISTERED, not started, per the
CONTINUATION's own status block ("NEXT: slice 7e ... or slice 7d"; 7d was
completed same-session by ADR-220, leaving 7e as the next unchecked item;
slice 7f is also REGISTERED but explicitly depends on 7d's own finding and
is a smaller, separable optimiser-defect item — left for a future session,
named in "What remains" below rather than attempted here per the routine's
"one slice per session").

The maintainer had already authorized the SUBSTANCE of this slice (ADR-219
amendment 1 decision 4, 2026-09-02: "`eta`/`edf` primary, H-weighted distance
a companion") — this session is the one that carries it into code, per the
PLAN's own DoD for slice 7e.

## Gap Before

The gap this session measures and closes is not an `mgcv`-vs-Polaris
numerical gap (that is what levels 1-5 of the conformance suite measure, and
none of them move this session) — it is a **criterion gap**:
`SELECT_FREE_SP_MODEL_CLAIM.agrees` gated on `max_abs_log10_sp_diff < 1e-2`,
a criterion ADR-219 Part 0 proved unreachable in principle on this fixture
(two of seven blocks carry curvature indistinguishable from zero at `mgcv`'s
own point). Restated from the ledger before any code change: **every
committed reading this epic has ever produced on this fixture read
`agrees=False`** under that gate — 8 rows, both tiers, every search
configuration (single/multistart × finite-difference/analytic gradient).
The gate had never once been satisfiable on this structure, by construction.

## Gap After

`compare_select_free_sp_case.agrees` now gates on `eta`/`edf`
(`max_abs_eta_diff < 2e-2`, `abs(edf_total_diff) < 1.0`, both derived, see
below). Re-stating every one of the 8 prior committed readings under the new
gate (pure arithmetic on already-published numbers, no new fitting): the 4
rows using `multistart=True` (both gradient variants, both tiers) now read
`agrees=True`; the 4 single-start rows still read `agrees=False`, at the
same order of magnitude they failed the old gate by. The old gate
(`agrees_log10_sp`) is preserved unchanged and still reads `False` on all 8.

**New measurement this session** (fresh tier-1 R dispatch, `select_free_sp`
recipe, same shared covariates/knots as every slice 7b/7d run):

| search | `max_abs_eta_diff` | `edf_total_diff` | `agrees` (new) | `agrees_log10_sp` (old) |
|---|---:|---:|---|---|
| single-start (module default) | 0.4457 | +2.4216 | False | False |
| `multistart=True, n_starts=9` | 0.00268 | -0.1106 | **True** | False |

The module's own single-start DEFAULT still fails the new gate by the same
order it failed the old one — the change discriminates a real production
choice rather than passing everything.

## Provenance

Every quantity the new gate reads (`eta`, `edf_total`) was **already
declared INDEPENDENT** on `SELECT_FREE_SP_MODEL_CLAIM` (ADR-218) — this
slice changes which tolerance is applied to already-correctly-declared
quantities, not their provenance. No `ComparedQuantity` was added or
reclassified.

The new H-weighted-at-own-point companion measurement (section (5) of
`scripts/gam_select_free_sp_identifiability_diagnostic.py`, new this
session) is **`MEASUREMENT (own criterion)`**
(`docs/VERIFICATION_STANDARD.md` §2.1) — a norm on a displacement between
two INDEPENDENTLY-produced points, weighted by our own criterion's own
curvature evaluated at either endpoint. Not a comparison; carries no
`VerificationClaim`; gates nothing. `mgcv`'s point enters only as the other
end of the displacement, never as an operand under comparison. This matches
the classification already established for the same quantity evaluated at
`mgcv`'s point in slice 7c (ADR-219), which this session's own read of
`scripts/gam_select_free_sp_identifiability_diagnostic.py` found mislabelled
`INDEPENDENT` in a stale print statement (pre-dating ADR-219 amendment 1
decision 2's ratification of the `MEASUREMENT (own criterion)` category by
one session) — corrected in the same pass, see ADR-221.

**Claim sentence, written before the code**
(`docs/VERIFICATION_STANDARD.md` §3.2), carried in code as
`gam_select_free_sp_conformance.SELECT_FREE_SP_REGATE_CLAIM_SENTENCE`:

> `polaris_re`'s `PolarisGAM` (`gam_model.fit_polaris_gam`, `multistart=True`)
> and `mgcv`'s `gam(select=TRUE, method="REML")` independently select all 7
> `log10(lambda)` for the identical three-term `select=TRUE` formula from the
> same shared recipe; agreement is declared on whether the two selections
> produce the SAME FITTED SURFACE — `max_abs_eta_diff < 2e-2` and
> `abs(edf_total_diff) < 1.0` — not on whether they land at the same
> `log10(lambda)`, which is reported as a diagnostic alongside a companion
> H-weighted `rho`-distance (`MEASUREMENT (own criterion)`, never a gate)
> rather than compared directly.

Narrower than the sentence it replaces in the three ways ADR-219 amendment
1's marketing-benchmark constraint requires: one structure named, one search
configuration named (`multistart=True`), both tolerances stated explicitly.
No unqualified "mgcv parity" claim is made anywhere in this PR — conformance
level 4 (ADR-190) is untouched and still genuinely disagrees.

## Hypotheses tried

1. **Can the two tolerances be derived rather than chosen to make today's
   reading pass?** Yes. `edf_tolerance=1.0` reuses an existing, precedented
   project constant (`gam_model_conformance._AGREEMENT_TOLERANCE_EDF`)
   verbatim — no new number invented. `eta_tolerance=0.02` is derived the
   same way `gam_uncertainty_conformance.compare_vc_case` derives its own 2%
   bound: ~3.7x headroom over the best CONFIRMED-at-both-tiers reading this
   epic has produced on this fixture (`multistart=True,
   analytic_gradient=True`, ADR-220: `5.46e-03` at both tiers), the same
   order of headroom that precedent uses ("under a factor of three").
   **CONFIRMED as derivable, not tuned** — verified by checking the gate
   against the module's own DEFAULT (single-start) configuration, which
   still fails it (see table above): a tolerance tuned to pass everything
   would not fail the default call.
2. **Does the H-weighted companion's weighting Hessian matter — is
   evaluating it only at `mgcv`'s point (as slice 7c did) an adequate
   proxy for evaluating it at our own point?** NO — refuted. Section (5)
   (new) repeats the eigenspectrum/step-stability derivation at each
   search's own converged point: single-start's H-weighted distance is
   **4.8x smaller** at its own point (1.6499) than at `mgcv`'s (7.9265);
   multistart's is **5.1x larger** at its own point (0.3121) than at
   `mgcv`'s (0.0617). Real, non-negligible, in BOTH directions — there is
   no safe default endpoint. Reported as both readings rather than assumed
   negligible, per the DoD's own precondition.

Neither hypothesis needed a second pass; both resolved on the first
measurement, so this is not a case of the routine's "three passes, no
movement" stop condition — it is the ordinary shape of a slice whose
substance (the maintainer's own decision) was already settled and whose
remaining work was carrying it into code plus checking the one thing the
DoD flagged as unmeasured.

## Oracle version

Tier 1: R 4.3.3 / mgcv 1.9.1 (local apt, this session's own install).
Tier 3: pending this session's own CI dispatch (wired into
`mgcv-conformance.yml`'s existing `select_free_sp` steps — confirms on the
next scheduled run per ADR-219 amendment 1 decision 1's own "for free"
precedent; the new gate logic is pure arithmetic on already-committed
`eta`/`edf` numbers and needs no new R payload of its own, but the fresh
single-vs-multistart comparison table and the section-(5) own-point
H-weighted reading are this session's tier-1 measurements and are not
committed as tier-3 numbers until confirmed, per `ROUTINE_MGCV_PARITY.md`
step 2).

## What changed, in code

- `src/polaris_re/analytics/gam_select_free_sp_conformance.py` —
  `compare_select_free_sp_case`'s `agrees` redefined to `eta`/`edf`;
  `agrees_log10_sp` added (the preserved old gate); `eta_tolerance`,
  `edf_tolerance`, `log10_sp_tolerance` carried on
  `SelectFreeSpCaseComparison` for auditability; `_AGREEMENT_TOLERANCE_ETA`
  (new) and `_AGREEMENT_TOLERANCE_EDF` (reused) module constants, both with
  derivations documented in their own docstrings;
  `SELECT_FREE_SP_REGATE_CLAIM_SENTENCE` (new).
- `scripts/gam_select_free_sp_identifiability_diagnostic.py` — refactored
  the step-stability scan into `_step_stability`/`_derived_floor` (reused,
  not duplicated); added section (5), H-weighted companion re-evaluated at
  each search's own point; corrected the stale `H-weighted : INDEPENDENT`
  provenance label to `MEASUREMENT (own criterion)`.
- `.github/workflows/mgcv-conformance.yml` — the slice 7b/7d job-summary
  step now prints both gates side by side (`agrees` / `agrees_log10_sp`)
  with the applied tolerances, and its "Disagreement" callout is keyed off
  the new primary gate.
- `tests/test_analytics/test_gam_select_free_sp_conformance.py` — two new
  R-free tests exercising the gate arithmetic directly (a close-eta/far-sp
  payload passes the new gate and fails the old one; a far-eta/exact-sp
  payload does the reverse) plus a tolerance-reporting test; the existing
  R-gated end-to-end test extended to assert both `agrees` fields are
  present and boolean.
- `docs/DECISIONS.md` — ADR-221.
- `docs/CONFORMANCE_LEDGER.md` — four new rows (the fresh single-vs-
  multistart reading; the 8-row re-statement of every prior committed
  reading under both gates; the H-weighted-at-own-point measurement; the
  provenance-label correction).
- `docs/PLAN_mgcv_parity_engine.md`, `docs/CONTINUATION_mgcv_parity_engine.md`
  — slice 7e status updated to DONE (tier 1; tier 3 pending), the relevant
  "Open questions" entry marked answered-and-implemented.

## Quality gate

- `uv run ruff format src/ tests/ scripts/` — clean, no changes needed
  beyond this session's own edits (already formatted while writing).
- `uv run ruff check src/ tests/ scripts/ --fix` — 12 pre-existing errors
  in `scripts/convert_soa_tables.py`, `scripts/train_ml_assumptions.py`,
  `scripts/convert_lapse_tables.py`, `scripts/ingest_inforce.py`,
  `scripts/validate_tables.py` — **none in any file this session touched**
  (confirmed: `ruff check` on this session's own 3 changed Python files
  reports "All checks passed!"). Pre-existing, not this session's to fix.
- `uv run mypy src/polaris_re/analytics/gam_select_free_sp_conformance.py`
  — clean.
- `uv run pytest tests/ -q --tb=short -m "not slow"` — **5 failed, 3591
  passed, 22 skipped, 126 deselected.** The 5 failures are the STANDING
  mortality-table-CSV-missing baseline (`docs/DEV_SESSION_LOG_2026-09-03_
  mgcv_parity_slice7d_analytic_gradient.md`'s own baseline: "5 failed, 3589
  passed, 22 skipped, 126 deselected" — identical failure set, identical
  skip/deselect counts). The delta is exactly this session's own 2 new
  tests (3589→3591). **Matches baseline — proceed, no regression.**
- `uv run pytest tests/qa/ -q --tb=short` — **85 passed, 9 skipped** —
  identical to the prior parity session's own reading.
  `tests/qa/golden_outputs/` byte-identical (`git status` shows no changes
  under `tests/qa/` or `data/`).

## Follow-ups harvested

Registered in `docs/PLAN_mgcv_parity_engine.md` (already-existing slice 7f
entry, untouched by this session) and named, not attempted, here:

- **Tier-3 confirmation** of this session's own fresh readings (the
  single-vs-multistart table and the H-weighted-at-own-point measurement).
  Not filed as a new backlog item — it is this slice's own DoD requirement
  and will land on the next CI dispatch of this PR.
- **Extending the same re-gate to `gam_model_conformance.FREE_SP_MODEL_CLAIM`**
  (the N=4, non-`select` structure) — PLAN slice 7e's own text names this
  optional; 2nd-order, not promoted.
- **A stated convention for which endpoint's Hessian the H-weighted
  companion should use**, now that it is shown non-negligible in both
  directions — 2nd-order, named in ADR-221's "What remains" rather than
  resolved.
- Slice 7f (the SciPy `ftol`-based early exit near a bound-active corner,
  ADR-220) remains REGISTERED, not started — the PLAN's next unchecked
  slice after this one, left for a future session per "one slice per
  session".

## Definition of Done (PLAN slice 7e, verbatim, ADR-209 decision 3)

- `[machine]` New gate's quantities declared as `ComparedQuantity` before
  gating — **MET**: `eta`/`edf` were already declared INDEPENDENT on
  `SELECT_FREE_SP_MODEL_CLAIM` prior to this slice; unchanged here.
- `[machine]` H-weighted companion evaluated at OUR OWN point, shift
  measured and reported — **MET**: section (5), see "Gap After" table
  above (4.8x / 5.1x shifts, both directions).
- `[machine]` Every prior committed reading re-stated under both gates —
  **MET**: ADR-221's 8-row table, `docs/CONFORMANCE_LEDGER.md`.
- `[judgement]` Claim sentence narrower than the one it replaces — **MET**:
  see "Provenance" above; names one structure, one search configuration,
  both tolerances explicitly.
- `[judgement]` No unqualified "mgcv parity" claim anywhere — **MET**:
  checked across this PR's diff; level 4's standing DISAGREE is untouched
  and mentioned explicitly in ADR-221.
- `[machine]` Tier 1 AND tier 3, both recorded, both agreeing — **PARTIAL,
  NOT MET YET**: tier 1 recorded this session; tier 3 pending the next CI
  dispatch on this PR (wired in, confirms "for free"). This PR is DRAFT
  for exactly this reason — see the PR body's own DoD checklist.
- `[machine]` `tests/qa/golden_outputs/` byte-identical — **MET**: verified
  above, `git status` confirms no changes under `tests/qa/`.
