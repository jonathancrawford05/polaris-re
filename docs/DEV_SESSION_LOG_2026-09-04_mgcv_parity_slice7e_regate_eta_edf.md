# Dev session log — 2026-09-04 — mgcv parity, slice 7e: re-gate `eta`/`edf`

**Routine:** `docs/ROUTINE_MGCV_PARITY.md` (scheduled, daily)
**Epic:** `docs/CONTINUATION_mgcv_parity_engine.md` / `docs/PLAN_mgcv_parity_engine.md`
**Slice:** 7e — re-gate `SELECT_FREE_SP_MODEL_CLAIM` on `eta`/`edf`, H-weighted
distance as a companion (ADR-219 amendment 1 decision 4)
**ADR:** ADR-221, amendments 1-3

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

**Corrected by the post-review addendum below (ADR-221 amendment 3) — this
paragraph originally mislabelled the H-weighted companion and is kept,
struck through in substance, for the record of what was claimed and how it
was found wrong.** The H-weighted-at-own-point companion measurement
(section (5) of `scripts/gam_select_free_sp_identifiability_diagnostic.py`)
is a norm on a displacement between two INDEPENDENTLY-produced points
(Python's own selected `log10(sp)`, `mgcv`'s own selected `log10(sp)`),
weighted by our own criterion's curvature. Applying
`VERIFICATION_STANDARD.md` §2.1's own mechanical test ("remove the
reference entirely, is there still a number?") — remove `mgcv`'s selection
and there is no displacement, hence no number, so `mgcv`'s payload is an
OPERAND here, not merely the point of evaluation. Its provenance is
**INDEPENDENT**, matching what `docs/PLAN_mgcv_parity_engine.md`'s own
"Preconditions inherited from ADR-219" block and ADR-219's own body text
already stated in prose. This session's original edit to the diagnostic
script's print statement (`INDEPENDENT` → `MEASUREMENT (own criterion)`)
was itself the mislabelling, not a correction of one — found by an
automated PR review (P1-1) and fixed properly: the quantity is now formally
declared on `SELECT_FREE_SP_MODEL_CLAIM.quantities`, weighted at OUR OWN
point (never `mgcv`'s, per ADR-219's own "second channel" precondition).
See the "Post-review addendum" section below for the full fix.

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
- `[machine]` Tier 1 AND tier 3, both recorded, both agreeing — **MET, as
  of the post-review addendum below**: two independent tier-3 dispatches
  (runs 33870429467 and 33871712927), bit-identical between them and
  identical in verdict to tier 1, confirm the primary deliverable (the
  `SELECT_FREE_SP_MODEL_CLAIM` re-gate table). Originally recorded PARTIAL
  when this PR was still draft; the PR is no longer draft — see the "Post-review
  addendum" section below, which is where this bullet was updated (found
  stale by an automated PR review, P1-3).
- `[machine]` `tests/qa/golden_outputs/` byte-identical — **MET**: verified
  above, `git status` confirms no changes under `tests/qa/`.

## Perf history (ADR-177)

`perf/history.jsonl` gained one row, commit-pinned to `82dd4f8` (the first
commit of this session, before the docs-only and fix commits that
followed — the row is appended once, on the initial PR open, per step 9b).
Creep verdict (`scripts/perf_history.py`, run at commit time):
`insufficient_data: false`, `n_rows: 41`, `peak_mib` baseline 33.0 → recent
33.0 (`delta 0.0`), **no structural creep**; wall-time ratio 1.06
(advisory, informs but does not gate); no config drift.

## Branch

`claude/intelligent-hamilton-a2qxnn` — the environment-designated branch
for this session, PR #226.

## Post-review addendum — automated PR review, findings addressed (ADR-221 amendment 3)

An automated review of PR #226 (APPROVE verdict, zero P0s) found three P1s
and three P2s. Per the babysit posture for a PR this session owns, all six
are addressed here rather than deferred.

**[P1-1] The H-weighted distance's provenance re-label was wrong.** This
session's own ADR-221 had "corrected" the diagnostic script's
`H-weighted : INDEPENDENT` label to `MEASUREMENT (own criterion)`, framing
it as catching staleness. The review applied `VERIFICATION_STANDARD.md`
§2.1's own mechanical test ("remove the reference entirely, is there still
a number?") and found the opposite: `mgcv`'s selected `rho` is one OPERAND
of the displacement `hessian_weighted_distance` weights, not merely a point
of evaluation — remove it and there is no displacement, hence no number.
**Confirmed against the actual prior source**, not just the review's
paraphrase: `docs/PLAN_mgcv_parity_engine.md`'s own "Preconditions inherited
from ADR-219" block (missed on the first read of that file — it sits just
above the slice 7e section this session read from) and ADR-219's own body
text both state, unambiguously, that the H-weighted column IS labelled
INDEPENDENT and name TWO preconditions before it can gate anything: (1)
formally declare it as a `ComparedQuantity` on `SELECT_FREE_SP_MODEL_CLAIM`,
and (2) weight it at OUR OWN selected point, never `mgcv`'s, to close a
"second channel" `mgcv`'s payload would otherwise re-enter through. This
session's original "correction" satisfied neither precondition and actively
mislabelled the category.

**Fixed properly, not just re-labelled:**
- `gam_sp_identifiability.py`'s own module docstring corrected — it had
  ALSO conflated the two functions' provenance (a pre-existing inconsistency
  predating this session, not introduced by it): `identified_direction_count`
  genuinely is `MEASUREMENT (own criterion)`; `hessian_weighted_distance`
  is a comparison on two independent operands, INDEPENDENT.
- New `derive_floor_from_step_stability` (promoted from the diagnostic
  script's own local `_step_stability`/`_derived_floor`, generalised and
  unit-documented) added to `gam_sp_identifiability.py`, with two new
  closed-form tests (`test_gam_sp_identifiability.py`).
- `gam_select_free_sp_conformance.py`: a new `ComparedQuantity`
  ("H-weighted rho distance (own-point weighting)", INDEPENDENT) added to
  `SELECT_FREE_SP_MODEL_CLAIM.quantities` — satisfying precondition 1.
  `SelectFreeSpCaseComparison` gained `h_weighted_rho_distance` and
  `h_weighted_rho_distance_computable`, computed by a new
  `_h_weighted_rho_distance_at_own_point` helper that builds the weighting
  Hessian at OUR OWN selected point (never `mgcv`'s) — satisfying
  precondition 2. Verified the computed value matches the diagnostic
  script's own section (5) reading exactly (`0.312096` for the multistart
  configuration on this session's tier-1 payload, both routes). Gracefully
  returns `(nan, False)` on the same non-convergent-neighbour condition
  ADR-221 amendment 2 found, rather than raising out of the primary
  comparison.
- The diagnostic script's own section (4) print text corrected back to
  `INDEPENDENT`, with the real, narrower finding stated precisely: what
  was genuinely missing was the own-point weighting, not the category.

**[P1-2] "Bit-identical … to tier 1" overstated the cross-tier agreement.**
This session's own tier-1 table (2 rows, FD gradient only) is NOT
bit-identical to the tier-3 table (4 rows, FD + analytic gradient) — the
multistart FD `eta` figure alone differs by ~2x (`0.00268` tier 1 vs
`5.388e-03` tier 3), real search-path variability, not a formula gap. What
holds across tiers is **identical in verdict** — every `agrees`/
`agrees_log10_sp` cell matches, and the tier-3 FD figures match ADR-220's
own already-committed tier-3 reading to the printed digit. Fixed in
ADR-221 amendment 2's own prose, `docs/CONFORMANCE_LEDGER.md`'s
corresponding row, and this PR's own body (which already used the correct
"identical in verdict" language for the two-run tier-3 comparison, but the
ADR needed a matching correction).

**[P1-3] Stale post-amendment bookkeeping in four places** — ADR-221's own
`Status:` line, this session log's final DoD bullet (both said "tier 3
pending" after amendments 1-2 (same ADR) had already landed it),
`CONTINUATION`'s open-question answer block, and the `PRODUCT_DIRECTION`
entry. All four fixed to state tier 1 AND tier 3 confirmed. The PLAN and
`CONTINUATION` status BLOCK (the top-of-file summary) were already correct
— this was an incomplete propagation of the addendum into secondary
locations, not a claim conflict.

**[P2-1] Bare float `==` in the new tolerance-reporting test** — changed to
`pytest.approx`, matching the convention the review itself confirmed the
other new assertions in the same test already use.

**[P2-2] No perf-history verdict recorded** — added above ("Perf history
(ADR-177)" section), reproducing the review's own computed verdict (no
structural creep, `peak_mib` 33.0 → 33.0).

**[P2-3] No branch record** — added above ("Branch" section).

**What was NOT changed:** the maintainer-facing questions the review
flagged for human attention (whether `2e-2` on the cloglog linear predictor
is the right pricing-relevant bar, whether promoting `_AGREEMENT_TOLERANCE_EDF`
to a gate half is intended given `eta` is doing all the discriminating work)
are exactly the kind of judgement call this routine may not make on its own
(`docs/ROUTINE_MGCV_PARITY.md`, "May not decide" — "whether to relax an
acceptance criterion"). Recorded here, not silently dropped, for the
maintainer's own review.
