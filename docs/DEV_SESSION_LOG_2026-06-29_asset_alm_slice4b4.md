# Dev Session Log — 2026-06-29

## Item Selected
- **Source:** CONTINUATION_asset_alm.md (active Epic — Asset/ALM model, Tier-C C0
  from COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md) — Slice 4b-4, the ALM validation
  notebook. This is the **final** slice of the epic.
- **Priority:** Tier-C / C0 (active Epic; the routine advances its next unchecked
  slice before any fallback pick).
- **Title:** ALM validation notebook
- **Slice:** 4b-4 of the Asset/ALM epic — **epic close**
- **Branch:** claude/awesome-bardeen-gdhqzd (environment-designated)

## Selection Rationale
Step 5 found the Asset/ALM CONTINUATION **IN PROGRESS** with Slice 4b-4 marked
NEXT. Step 5b confirms Asset/ALM is the single active Epic; its next slice must be
advanced before any fallback. Slice 4b-4's dependency (4b-3b) is merged — PR #115
is on `main` (the branch tip `0876a98` and `origin/main` are identical, 0 ahead /
0 behind), and `list_pull_requests state=open` context shows no draft-blocked
slice and no review feedback to address. Shipping the notebook is the session's
deliverable; per the guardrail, no fallback item was also picked.

Ledger healing (step 4b): the only PR merged since the prior session log is #115
(Slice 4b-3b), already recorded as DONE in the CONTINUATION — the Asset/ALM slices
are tracked in the CONTINUATION, not as PRODUCT_DIRECTION ledger entries, so there
is no crossout to heal.

## Baseline (step 4)
Fast suite baseline before any change: **1799 passed, 110 deselected, 0 failures**
(`make test`, 226s). This matches the prior session log's post-change count (1799).
Standing caveat: the routine's known failure baseline is the **4 pre-existing SOA /
CIA-2014 conversion failures** that surface only when step 2's pymort conversion
cannot reach its source (`scripts/convert_soa_tables.py` reported the **CIA-2014**
tables MISSING this run; CSO 2001 and SOA VBT 2015 converted OK). They did **not**
manifest in the fast suite (0 failures observed), so the baseline matched and the
run proceeded. STOP would apply only on a NEW or CHANGED failure beyond those 4
known-standing conversion failures.

## Premise Verification (step 7b)
The "premise" of a notebook slice is that a credible end-to-end ALM example can be
built and that its numbers reconcile to closed forms. Reproduced before writing the
notebook:
- **Flat mortality builds no whole-life reserve.** A hand-built WL block on flat
  `q=0.4%` produced an opening reserve of ~$202 for $5M face (and the *golden* WL
  cohort under the flat config carries only ~$551, the golden TERM cohort ~$51) —
  a level net premium funds a constant hazard each period, so nothing accumulates.
  An asset/ALM example on such a block is degenerate (the liability PV is
  near-zero). **Corrected approach:** a synthetic Gompertz-style *increasing* curve
  `q_x = 0.0004·1.09^(x-18)`, which is still self-contained (no data files) and
  produces a realistic seasoned-WL reserve (~$995k gross, ~$498k ceded on a $10M
  block). This is the corrected diagnosis carried into ADR-117.
- **The dual gap and the telescoping identity hold** on the corrected block: a 50%
  coinsurance cession defines both reinsurer and cedant sides; the reserve run-off
  PV reconciles to the opening ceded reserve to ~4e-9; the reinsurer-side gap is
  −8.93 yr (short assets vs an ~18.6-yr WL liability). Premise holds.

## Decomposition Plan (Asset/ALM epic — surfacing tail)
| Slice | Scope | Status | PR |
|-------|-------|--------|----|
| 4b-1 | CLI asset-portfolio input + duration-gap output | ✅ Done | merged |
| 4b-2a | Reserve-backed Option-B liability stream + CLI rewire | ✅ Done | merged |
| 4b-2b | Reinsurer/cedant dual gap + REST API surface | ✅ Done | #113 |
| 4b-3a | ALM duration-gap sheet on the Excel workbook | ✅ Done | #114 |
| 4b-3b | Dashboard asset-portfolio input + duration-gap display | ✅ Done | #115 |
| 4b-4 | **ALM validation notebook** | ✅ Done | this PR |

**Epic COMPLETE** — CONTINUATION_asset_alm.md status IN PROGRESS → COMPLETE.

## What Was Done
Added `notebooks/04_alm_duration_gap.ipynb` — the Asset/ALM epic's end-to-end
validation notebook, matching the per-epic notebook precedent (01 YRT pricing, 02
reserve basis, 03 capital standards). It builds a seasoned whole-life block on a
self-contained synthetic Gompertz mortality curve, cedes 50% on **coinsurance** so
the reinsurer inherits a real ceded reserve and **both** `DualDurationGap` sides
are defined (the golden config is YRT, whose reinsurer side is `None` — coinsurance
gives a fuller validation), sizes a backing bond portfolio to the ceded reserve,
and reports the dual duration gap via the **same** `dual_duration_gap` path the
CLI / REST API / Excel / dashboard surfaces use. It then reconciles the engine
against four closed forms: (1) the reserve-backed run-off telescopes to the opening
reserve at the reserve valuation rate (ADR-113); (2) a zero-coupon bond's Macaulay
duration is its term in years, modified is `N/(1+y)`, convexity is `N(N+1)/(1+y)²`;
(3) `duration_measures` on the portfolio's own cash flows reproduces the portfolio
duration API exactly (the gap wires one primitive, not two); (4) a block whose
liability equals the assets' own cash flows has an exactly-zero gap. A closing
section demonstrates immunisation — lengthening the assets shrinks the
reinsurer-side gap from −8.93 to −0.87 yr.

Because `nbclient`/`nbconvert` are not project dependencies, the notebook is made
**self-verifying in CI** by a pytest guard
(`tests/test_notebooks/test_alm_duration_gap_notebook.py`) that reads the `.ipynb`
with `nbformat` and `exec`s its (deliberately magic-free) code cells in one shared
namespace — reproducing a top-to-bottom kernel run. The closed-form reconciliations
are embedded in the cells as `np.testing.assert_allclose` / `assert`, so executing
the notebook IS the verification: any drift in the duration/run-off math fails CI.
Recorded as ADR-117. The change is purely additive (no `src/` change), so goldens
are byte-identical.

## Files Changed
- `notebooks/04_alm_duration_gap.ipynb` — new validation notebook (22 cells).
- `tests/test_notebooks/__init__.py` — new test package.
- `tests/test_notebooks/test_alm_duration_gap_notebook.py` — notebook execution guard.
- `docs/DECISIONS.md` — ADR-117.
- `docs/CONTINUATION_asset_alm.md` — 4b-4 DONE; status IN PROGRESS → COMPLETE.
- `docs/PLAN_asset_alm.md` — 4b-4 SHIPPED; status COMPLETE.
- `docs/ROADMAP.md` — Milestone 5.4 marked COMPLETE; 4b-4 + Tests boxes checked.
- `README.md` — notebook 04 added to the notebooks index.
- `docs/PRODUCT_DIRECTION_2026-06-18.md` — harvested the generic notebook-CI guard follow-up.

## Tests Added
- `tests/test_notebooks/test_alm_duration_gap_notebook.py` (3 tests): the notebook
  file exists; it has the expected code cells; and it **executes top to bottom with
  every embedded reconciliation passing**, with a defensive spot-check that the
  coinsurance run binds a `DualDurationGap` carrying both reinsurer and cedant sides.

## Acceptance Criteria
| Criterion | Status | Notes |
|-----------|--------|-------|
| End-to-end ALM example (duration gap on a real block) | ✅ | seasoned WL block, 50% coinsurance, dual gap |
| Worked closed-form reconciliation(s) | ✅ | four: run-off telescoping, ZCB duration/convexity, primitive consistency, zero-gap match |
| Reuses the shipped `dual_duration_gap` path (no recompute) | ✅ | notebook calls the same analytics fn the surfaces use |
| Self-contained (runs without external data files) | ✅ | synthetic Gompertz mortality, no SOA/CIA dependency |
| Verifiable by pytest | ✅ | notebook execution guard; embedded asserts run in CI |
| Additive — goldens byte-identical | ✅ | no `src/` change; `polaris price` golden = $45,386 reinsurer unchanged |
| Full fast suite green | ✅ | 1799 → 1802 passed (+3 new) |
| QA + golden suites green | ✅ | 79 passed (qa + notebook); golden price output unchanged |
| ADR recorded | ✅ | ADR-117 |
| Epic closed | ✅ | CONTINUATION + PLAN + ROADMAP marked COMPLETE |

## Open Questions / Follow-ups
None requiring human decision. The Asset/ALM epic is complete. One new follow-up
was harvested (a generic "execute every notebook" CI guard — the current guard
covers only notebook 04; notebooks 01–03 have no execution guard). All other
asset-side ambitions (net-of-spread / time-varying book yield, stochastic
reinvestment, distinct cedant/reinsurer portfolios, per-side valuation yield) were
already harvested by earlier slices and remain NICE-TO-HAVE.

**Next session:** no Epic is active after this close. Per step 5b, the next run
should START a new Epic from the latest COMMERCIAL_VIABILITY_REVIEW Tier-A/B
ranking (writing its PLAN + shipping slice 1 as that session's deliverable). The
review (2026-06-18) is within the ~30-day freshness window, so it need not be
regenerated yet — but it will cross 30 days on ~2026-07-18, so the Epic-selection
run nearest that date should regenerate it first.

## Parked Polish
None. (The one harvested item — the generic notebook-CI guard — is a 1st-order
follow-up of this session's originally-planned notebook, so it was promoted
normally as NICE-TO-HAVE, not parked.)

## Impact on Golden Baselines
None. The notebook is a new file with no `src/` change; `polaris price` on the
golden inforce/config produced the unchanged headline (Total PV Profits Reinsurer
$45,386, Cedant $3,513,563), and the QA golden suite confirms byte-identical output.
