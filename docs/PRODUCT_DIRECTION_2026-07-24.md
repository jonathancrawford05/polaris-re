# Product Direction — 2026-07-24

## Purpose

This is the regenerated **nightly reasonability / direction line**, superseding
`PRODUCT_DIRECTION_2026-06-18.md` (36 days old — past the routine's ~30-day
regeneration trigger, and overdue since ~2026-07-18). It is the **S0.1**
deliverable of the queued post-A4′ Sprint 0 (set up 2026-07-24, maintainer-
directed; see the prior file's "Next Sprint — QUEUED" block).

Regeneration scope, per routine step 17 and the S0.1 brief:
1. List what has **shipped since 2026-06-18** (the A1′/A2′/A3′/A4′ epics + the
   mid-June modeling epics), cross-checked against `git log` and the COMPLETE
   CONTINUATIONs.
2. **Carry forward** the unresolved "Promoted Follow-ups" from the prior file
   (102 items: 12 IMPORTANT + 90 NICE-TO-HAVE), with provenance preserved.
3. **Re-rank** the catalogue against the fresh
   `COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md` (9 days old — no re-review
   needed).
4. **Surface the Phase-7 frontier decision** to the maintainer (review §7).

The full prose of every carried-forward follow-up remains in
`PRODUCT_DIRECTION_2026-06-18.md` — that file is **not deleted** (audit trail);
this file is the live authority and the compact, re-ranked view.

**Bottom line up front.** Polaris RE has now shipped its **entire written
roadmap** — Phases 1–5 modeling, the 6.2 production-hardening milestone, and
the whole 2026-07-05 productization ladder (validation, hardening, ingestion),
capped by the A4′ experience-GAM epic (ROADMAP 6.1, the ML-native
differentiator). **No unstarted Tier-A "big rock" remains.** The routine has
crossed the inflection the 2026-07-15 review named: from *"build the roadmap"*
into *maintenance* (harvest Tier-B/C quick wins) **unless the maintainer charts
a Phase 7** (§ "Decision Surfaced"). Until a frontier is chosen, the routine is
in **maintenance mode, not growth mode**, and each session log should say so.

This session ships the S0.1 regeneration **and bundles S0.2** — the latent
`core` → `assumptions` circular-import fix (ADR-155) — since S0.1 has no epic
slice competing for wall-clock.

---

## What Has Shipped Since 2026-06-18

Every item below is on the working branch line (`claude/loving-gauss-*`,
routine-effective main) with a COMPLETE CONTINUATION and an ADR. (Note: local
`origin/main` lags at PR #139 because the routine never merges its own PRs; the
human merges lazily. "Shipped" here = merged into the routine's integration
branch, the ledger convention used by step 4b.)

| Epic | Status | PRs | ADRs | Evidence |
|------|--------|-----|------|----------|
| IFRS 17 period-to-period **movement table** (Epic 2) | ✅ COMPLETE | #87–#90, CLI #97 | 093–097 | `CONTINUATION_ifrs17_movement` |
| **Cross-jurisdiction capital** (US RBC + Solvency II; Epic 3) | ✅ COMPLETE | #91–#106, #109 | 098–107 | `CONTINUATION_cross_jurisdiction_capital` |
| **Asset / ALM** (duration gap, book yield, modco interest; Epic 4) | ✅ COMPLETE | #108–#117 | 108–117 | `CONTINUATION_asset_alm` |
| **Expense allowance + experience refund** | ✅ COMPLETE | #118–#124 | 118–124 | `CONTINUATION_expense_allowance` |
| **Reserve-basis exactness** (CRVM/VM-20/GAAP concrete bases) | ✅ COMPLETE | #125–#128 | 125–128 | `CONTINUATION_reserve_basis_exactness` |
| **A1′ Validation & benchmark pack** (`polaris benchmark`) | ✅ COMPLETE | #130–#132 | 130–132 | `CONTINUATION_validation_benchmark` |
| **A2′ Production hardening & observability** (ROADMAP 6.2) | ✅ COMPLETE | #133–#135 | 133–135 | `CONTINUATION_production_hardening` |
| **A3′ Cedant data-ingestion robustness** | ✅ COMPLETE | #136–#139 | 136–138 | `CONTINUATION_cedant_ingestion` |
| **A4′ Data-Driven Experience Analysis & Assumption-Setting (GAM)** (ROADMAP 6.1) | ✅ COMPLETE | #141–#156 | 139–154 | `CONTINUATION_experience_gam` |
| **S0.2** — latent `core`→`assumptions` circular-import fix | ✅ **this session** | *(this PR)* | 155 | `tests/test_core/test_import_layering.py` |

Also struck through in the prior file's "Promoted Follow-ups" as SHIPPED since
2026-06-18 (10 items): `GAMFitResult.feature_ranges`/`all_effects()` (#154),
the result-level solvency-ratio surface (#106), the WL prospective-to-omega
reserve + closed-form validation case (#128/#131), the canonical ALM liability
cash-flow stream (#112/#113), the IFRS 17 movement Excel + CLI surfaces, and
the coins/policy_cession pipeline goldens (#104).

**Ledger-healed this session (step 4b).** Circular-import follow-up (prior file
line ~1911) → **SHIPPED** as S0.2 / ADR-155 (this PR). The five "effectively
resolved but not struck-through" items flagged during the carry-forward survey
(GAAP concrete reserve basis / ADR-092; IFRS 17 movement umbrella / ADR-094;
COMMERCIAL_VIABILITY_REVIEW 30-day regen / resolved 2026-07-05; "constitute a
productization epic" / A1′+A2′ done; proxy-aware rate-limit keying / ADR-135)
are treated as **shipped** and are **not** carried forward below.

---

## Reasonability Status

Unchanged from the prior nightly — this regeneration surfaces **no new
reasonability flag**. The suite is clean at **2,455 unit tests passing** (3
skipped on absent CIA tables, 112 slow-deselected), the QA golden suite is
**76/76**, and all four golden configs (`yrt`, `coins`, `policy_cession`,
`flat`) reproduce their committed baselines within the standing ±$500 / ±0.5 pp
tolerance. Coinsurance additivity (`net + ceded == gross`) holds to
floating-point precision. The two long-standing structural notes remain
(documented, not defects): a **flat YRT rate vs the rising-with-age WL claim
curve** on the SOA-VBT golden (the per-duration solver ADR-063/067 is the fix;
the golden does not consume it), and the deliberately-stressed golden block
(mixed standard/smoker/SUBSTANDARD, no select credit, 6% discount, 10% hurdle)
producing negative-PV headline blocks by construction. The `flat` config
remains the deal-committee-presentable reasonable output. Full reasonability
narrative: `PRODUCT_DIRECTION_2026-06-18.md` §Reasonability Assessment.

## Commercial Readiness: **Production-ready across the modeled surface**

The three gaps the 2026-06-18 file named as "what gates production use at a
large reinsurer" have **all closed**: (1) reserve-basis matching — CRVM / VM-20
(simplified) / GAAP FAS 60 concrete bases shipped (Epic reserve-basis-exactness,
ADR-125–128); (2) IFRS 17 period-to-period **movement table** — shipped
(ADR-093–097); (3) cross-jurisdiction capital — **US RBC + Solvency II**
alongside LICAT, with a jurisdiction selector on every surface (ADR-098–107).
Layered on top since: Asset/ALM duration-gap + modco interest, expense-allowance
/ experience-refund treaty terms, a CI-executable **validation & benchmark
pack**, **production hardening** (auth, rate limiting, Prometheus/K8s), robust
**cedant ingestion**, and the **experience-GAM** assumption-setting loop. What
remains is **not** a modeling, validation, or deployment gap — it is the
Phase-7 go/no-go (below).

---

## Re-ranked Catalogue (from `COMMERCIAL_VIABILITY_REVIEW_2026-07-15`)

Value judged against a paying reinsurance client; effort in developer-days.
This mirrors the review's §4 re-rank (9 days old — authoritative).

### Tier A — High value, multi-session (the remaining big rocks)

**None unstarted.** A4′ (experience-GAM) was the last unstarted roadmap epic
and is now COMPLETE. The only Tier-A-scale items left are **blocked or
gated**, not startable:

| # | Item | Status | Why not startable |
|---|------|--------|-------------------|
| — | **AXIS/Prophet side-by-side reconciliation** (validation Slice 4) | REFERENCE-BLOCKED | Needs a maintainer-supplied AXIS/Prophet reference output; cannot be autonomously constituted. Highest *external* credibility win — revive on a supplied reference. |
| — | **A new Phase-7 frontier** | AWAITING MAINTAINER | See "Decision Surfaced" below — no frontier is chosen, so step 5b has nothing to constitute. |

Per the routine's ACTIVE-EPIC guardrail: with no startable Tier-A epic, the
session correctly falls to gated Tier-B/C fallback (Sprint 0), and **flags
maintenance mode**.

### Tier B — High value, single-to-short (between-epic quick wins — Sprint 0)

| # | Feature | Value | Effort | Notes |
|---|---------|-------|--------|-------|
| **B1** | **Switch capital surfaces to `for_product_interim`** — expose the built C-1/C-3 factors everywhere | ★★★★☆ | ~1–2 d | Behaviour change → golden rebaseline + ADR. Unshipped after **three** reviews. |
| **B2** | **Scale benchmark at 100K–500K policies** — publish a timing table; back the README perf claim | ★★★★☆ | ~1 d | Unshipped after **three** reviews. Pairs with NICE-TO-HAVE perf-harness work. |
| **B4** | **Premium-deficiency reserve / loss recognition** — turn the sufficiency analyzer into a reserve floor | ★★★☆☆ | ~1–2 d | Unshipped after **three** reviews. |

B1 and B2 are the cleanest between-epic fallback picks and the **S3** sequence
(value-per-day order: B1 → B2 → B4), now behind the maintainer-directed S1
(`pipeline.py` relocation) and S2 (MI dashboard page).

### Tier C — Medium value, enabling / operational

| # | Feature | Value | Effort |
|---|---------|-------|--------|
| C3 | Funds-withheld coinsurance (`FWCoinsuranceTreaty`) | ★★★☆☆ | ~2 d |
| C4 | Parallel portfolio execution + caching + `remove_deal` | ★★★☆☆ | ~2 d |
| C5 | Per-deal hurdle rates on `Portfolio` | ★★★☆☆ | ~5 d |
| C6 | Phase-6.3 load test (100 concurrent `/api/v1/price` < 2s) + QUICKSTART K8s guide | ★★★☆☆ | ~1–2 d |

### Tier D — Exactness polish / low value (deprioritise)

Interest-exactness helper (`CONTINUATION_reserve_basis_correctness` Slices 2–3,
parked NICE-TO-HAVE); the A1′/A2′/A3′ automation/scale polish now in
Carried-Forward NICE-TO-HAVE; GAAP PADs on the deal path (see IMPORTANT #5),
sex/smoker statutory-table composition, CSO-version selection, Excel/dashboard
micro-polish.

---

## Decision Surfaced for the Maintainer — the post-roadmap inflection

> **Q: With the entire written roadmap shipped (A4′ closed), what drives the
> routine next — quick-win harvest, or a new Phase 7?**
>
> There is **no further Tier-A "big rock"** in the current plans. The routine
> will, correctly, fall to the Tier-B/C quick-win queue (B1 → B2 → B4 →
> C3/C4/C5/C6) — legitimate **maintenance** work, but *not* a growth frontier,
> and it risks the "quick-win-becomes-the-default" pattern the epic track was
> built to avoid, one tier up.
>
> **Recommended:** choose the next frontier. Candidate **Phase 7** themes (any
> one re-establishes a Tier-A ladder):
> - **Real AXIS/Prophet reconciliation** — supply a reference output so the
>   parked validation Slice 4 can ship. The single highest *external*
>   credibility win and the only thing blocking a "matches the incumbent" claim.
> - **New product frontier** — indexed/variable annuities with living benefits
>   (GMxB), or group/worksite blocks — the largest *un-modelled* liability
>   classes a reinsurer would bring.
> - **Stochastic ALM / nested stochastic / ESG** — the economic-scenario
>   generator and nested-stochastic capability that VM-21 / PBR and real
>   economic-capital work require (extends the Phase-5.4 Asset/ALM base).
> - **Multi-user / persistence / audit** — a deal database, run history, and
>   user-level audit trail: the "team of actuaries, not one" operational layer a
>   purchased tool needs.
>
> **If no Phase-7 preference yet:** the autonomous default is to harvest B1 → B2
> → B4 as single-session quick wins while this stays open — but the routine is
> then in **maintenance mode, not growth mode**, and each session log must say
> so. *Source: COMMERCIAL_VIABILITY_REVIEW_2026-07-15 §7; DEV_SESSION_LOG_2026-07-24_experience_gam_slice4d3 Open Questions.*
>
> **Maintainer response (2026-07-24, live):** Phase-7 frontier **still open / not
> yet chosen.** In the interim the maintainer directed the next two *maintenance*
> items explicitly — **S1** (proper `pipeline.py` relocation) then **S2** (MI
> dashboard page) — ahead of the B1/B2/B4 default (see "Recommended Next Sprint").
> The routine remains in **maintenance mode** until a Phase-7 frontier is chosen.

---

## Recommended Next Sprint (post-A4′ Sprint 0)

Run in order; each is single-session. This supersedes the prior file's stale
"Recommended Next Sprint" (which led with long-shipped reserve-basis work).

> **⏭️ Maintainer directive (2026-07-24, live).** The next **two** routine
> items are fixed, in this order and **ahead of the Tier-B quick wins**: **S1 —
> the proper `core`→`assumptions` layering fix (relocate `pipeline.py`)**, then
> **S2 — an MI (mortality-improvement) page on the Streamlit dashboard.** Both
> are maintenance-mode refinements of shipped work, so the routine stays in
> maintenance mode; the Phase-7 frontier decision (above) remains open and is
> unblocked by neither. Step 5b/step 6 should select S1 next, then S2, then fall
> to S3.

- **S0.1 — PRODUCT_DIRECTION regeneration + Phase-7 surfacing.** ✅ **done this
  session** (this file).
- **S0.2 — Fix the latent `core`→`assumptions` circular import (symptom).** ✅
  **done this session** (ADR-155; cheap symptom fix — removed the eager
  `pipeline` re-export from `core/__init__.py`; zero callers; goldens
  byte-identical). The *proper* architectural fix is now **S1** below.
- **S1 — Proper `core`→`assumptions` layering fix (maintainer-directed).** ✅
  **done this session** (PR #158, ADR-156; `CONTINUATION_pipeline_relocation` →
  COMPLETE). `git mv`'d `core/pipeline.py` → `polaris_re/pipeline.py`, rewrote all
  28 in-repo importers (no backward-compat shim), rewrote the module +
  `core/__init__` docstrings, and extended
  `tests/test_core/test_import_layering.py` (4 fresh-interpreter guards, incl. the
  old path no longer resolving). The CLAUDE.md §6 layering exception is **retired
  entirely** — `core/` can no longer import `assumptions/` at all. The
  eager-cross-layer-`__init__`-re-export **sweep was folded in**: every
  `src/polaris_re/**/__init__.py` audited; **no other instances found** (each
  re-exports only its own sub-package). Behaviour-neutral → goldens
  byte-identical. Single session (mechanical import churn + ADR); Slice 2 folded
  into Slice 1 per the PLAN.
- **S2 — MI (mortality-improvement) page on the Streamlit dashboard
  (maintainer-directed, SECOND).** **PLAN LOCKED: `docs/PLAN_mi_dashboard.md`.**
  A dedicated dashboard page surfacing the experience-GAM / mortality-improvement
  capability to non-CLI users, folding two carried-forward items: (a) the
  **versioned improvement-scale selector** (IMPORTANT #12 / ADR-148 — so a
  dashboard user can drive a priced run from a versioned
  `ImprovementScale.CUSTOM` basis, the dashboard half of the selector; the
  REST-API half of #12 may follow separately as optional Slice 3), and (b) the
  **MI diagnostics view** (NICE-TO-HAVE experience-GAM #89 / ADR-153 — effects /
  MI-surface `MI_x(y)` slices / projection fan, reusing `viz/experience_plots.py`
  + `all_effects()`/`--grid-out` already shipped for the `[viz]` helpers). Add
  `AppTest` dashboard flow tests (`tests/qa/test_dashboard_flows.py` pattern) +
  `DealConfig.to_dict()` round-trip for the selector state; pin all dates
  (ADR-074); exclude the view from coverage (ADR-032). MEDIUM — 2 slices (+1
  optional API slice); the PLAN decomposes it and the next session opens
  `docs/CONTINUATION_mi_dashboard.md`. *Source: maintainer directive 2026-07-24;
  IMPORTANT #12 (ADR-148) + Carried-Forward experience-GAM #89 (ADR-153).*
- **S3 — Tier-B quick wins in value-per-day order: B1 → B2 → B4** (was S0.3; now
  follows S1+S2; see the re-ranked catalogue). Independently valuable
  maintenance-mode PRs while no Phase-7 frontier is chosen.
- **Then** Tier-C (C3/C4/C5/C6) or a chosen Phase-7 epic (which, once picked,
  is constituted via step 5b: PLAN + slice 1).

---

## Carried-Forward Promoted Follow-ups

Unresolved items harvested by the daily-dev routine (step 17) from the prior
file, provenance preserved. **These are first-class work items, not
commentary.** Full prose per item: `PRODUCT_DIRECTION_2026-06-18.md`
"Promoted Follow-ups". Count: **12 IMPORTANT + 90 NICE-TO-HAVE = 102.** No
BLOCKER remains.

### IMPORTANT (12)

1. **Statutory valuation mortality table (2001 CSO) for CRVM.** TermLife/WholeLife
   CRVM value on projection best-estimate mortality, not the prescribed 2001 CSO
   table; a distinct `valuation_mortality` slot is needed to reproduce a cedant's
   US statutory CRVM reserve exactly. *Source: ADR-089 Out of scope (1st-order).*
2. **Close the WL terminal-reserve artefact on the NET_PREMIUM basis.** The default
   NET_PREMIUM WL reserve still uses a one-period terminal estimate that collapses
   at the horizon; prospective-to-omega valuation moves goldens → needs its own ADR
   + rebaseline. *Source: ADR-089 Out of scope + DEV_SESSION_LOG_2026-06-19_reserve_basis_slice2b Open Questions (1st-order).*
3. **Engage block-aware first-year duration mapping when an `expense_allowance` is
   supplied via config.** With an allowance set but `use_policy_cession` unset, the
   allowance falls back to the new-business projection-month basis, wrongly charging
   the high first-year rate on renewal inforce; fix is to force the cohort inforce
   through `apply()` whenever an allowance is present. *Source: ADR-122 Out of scope + DEV_SESSION_LOG_2026-06-30_expense_allowance_slice3b2a Open Questions (1st-order).*
4. **Prescribed statutory valuation-interest helper.** Issue-year → prescribed
   valuation-interest-rate lookup so statutory CRVM reproduction is penny-exact on
   the interest side (currently directional via a single manual rate). *Source: ADR-125 Out of scope + CONTINUATION_reserve_basis_exactness Refinement Backlog (1st-order); reclassified per ADR-126 / PR #125 review.*
5. **Surface the GAAP (FAS 60) PADs on the deal path (`DealConfig` / CLI / API).**
   The two GAAP PADs live on `ProjectionConfig` but are not exposed via the CLI
   config parser, `--gaap-*` flags, or REST `PriceRequest`. *Source: ADR-127 / ADR-128 Out of scope (1st-order).*
6. **Shared rate-limit backend for multi-replica deployments.** The in-process
   limiter counts per replica, so behind N replicas the effective limit is ~N× the
   configured threshold — a silent correctness caveat on a shipped, deployed
   feature. *Source: ADR-134 Out of scope (1st-order).*
7. **Shared backend for multi-replica metrics aggregation.** The in-process
   `MetricsRegistry` exposes per-pod counters; exact global counts (without
   Prometheus sum-by) need a shared/remote-write backend. *Source: ADR-135 Out of scope (1st-order).*
8. **CI smoke-test job (real entry points).** A fast (<30s) deterministic job that
   boots uvicorn and curls `/health`, `/metrics`, a real `/api/v1/price`, runs
   `polaris price` + `polaris benchmark --pack closed-form`, gating merges — catches
   "won't boot / endpoint 500s" that unit tests miss. *Source: maintainer discussion 2026-07-12 (CI perf/smoke thread), 1st-order.*
9. **Performance harness with same-run head-vs-main baseline.** A `polaris perfbench`
   / `tests/perf/` harness timing engine hot paths on a fixed synthetic block +
   deterministic structural metrics, benchmarking head and main **in the same job**
   (noise-cancelling ratio → `perf.json`). Prerequisite for #10 and NICE-TO-HAVE
   #62/#63. *Source: maintainer discussion 2026-07-12, 1st-order.*
10. **Committed per-merge performance log (`perf/history.jsonl`) + creep detection.**
    One append-only deterministic-first row per merge to `main`, to catch slow
    multi-month creep a per-PR comment structurally cannot. Depends on #9. *Source: maintainer discussion 2026-07-12, 1st-order.*
11. **Confirm the ADR-141 backend deviation for the Bayesian MI surface.** Slice 2b
    shipped a pure-NumPy/SciPy reduced-rank GP instead of the PLAN-locked
    `bambi`/`pymc` HSGP (defective in installed versions); maintainer should confirm
    this direction — it now blocks only the optional `pymc`-NUTS audit path. *Source: ADR-141 human-review flag + DEV_SESSION_LOG_2026-07-22 DISCOVERY (1st-order).*
12. **Surface the experience-improvement selector on the dashboard + REST API.** The
    versioned `ImprovementScale.CUSTOM` basis is wired into `--config` and a
    `--improvement-version` CLI flag but not the dashboard Deal Pricing page or REST
    `/price` schema. *Source: ADR-148 Out of scope (1st-order).* **→ the dashboard
    half is Next Sprint S2 (maintainer-directed 2026-07-24), folded into the MI
    dashboard page; the REST-API half may follow.**

> **CI performance & smoke tracking (maintainer discussion 2026-07-12) — group
> context.** IMPORTANT #8/#9/#10 and NICE-TO-HAVE #62/#63/#64 form one coherent
> group with a dependency chain (#9 harness is prerequisite for #10 and the
> NICE-TO-HAVE bridge/backfill items — do not start a dependent before its
> prerequisite is on `main`). **Overriding design rule (non-negotiable):**
> *deterministic / noise-normalized metrics may gate or alert; raw wall-time
> only informs.* GitHub runners vary 2–3× run-to-run, so any gate on absolute
> latency is an alert-fatigue generator.

### NICE-TO-HAVE (90) — grouped by theme

Each: **title** — one-line. *Source.* (Full prose in the 2026-06-18 file.)

**Capital & solvency (4)**
- **Configurable held-capital basis (target multiple of ACL) for US RBC** — let the RoC denominator reflect a target multiple (300–400% ACL), not the regulatory floor. *ADR-098 + CONTINUATION_cross_jurisdiction_capital Open Questions.*
- **Additional Solvency II SCR sub-modules** — extend beyond mortality/lapse/cat + market/counterparty to longevity/expense/revision/disability/health for annuity & health books. *ADR-100.*
- **Per-side available-capital numerator for the solvency ratio** — let cedant and reinsurer ratios each use their own available-capital figure. *ADR-104/106 + DEV_SESSION_LOG_2026-06-26 (2nd-order).*
- **Mutually calibrate the three capital standards' factors** — required capital differs ~100× across LICAT/RBC/SII on identical NAR (shock vs small-factor); shock-based calibration is the C0 Asset/ALM epic. *ADR-107 + CONTINUATION_cross_jurisdiction_capital "Factor calibration sign-off".*

**Asset / ALM (9)**
- **Stochastic reinvestment yields (Hull-White / CIR)** — make reinvestment scenario-driven via `analytics/stochastic.py`. *ADR-108.*
- **Non-fixed-income asset classes** — extend `AssetPortfolio` beyond bonds (equities/mortgages). *ADR-108.*
- **Net-of-spread asset book yield** — gross-less-investment-expense/default option so modco interest reflects net return. *PLAN_asset_alm §5.*
- **Time-varying (amortising) asset earned rate** — an earned-rate vector recomputed along run-off, sharpening modco interest & duration gap. *PLAN_asset_alm §5.*
- **Asset-yield vs liability-discount-rate split in the duration gap** — discount each side at its own rate. *ADR-111 + DEV_SESSION_LOG_2026-06-27_asset_alm_slice4a (2nd-order).*
- **Distinct cedant-held vs reinsurer-held asset portfolios in the duration gap** — second portfolio reflecting each party's assets (esp. modco). *ADR-114.*
- **Conditional formatting on the Excel "ALM Duration Gap" sheet** — visual flag on large negative dollar-duration gaps. *ADR-115.*
- **Saved / file-upload asset portfolio on the dashboard ALM input** — `st.file_uploader` to remove the per-run JSON paste. *ADR-116 + DEV_SESSION_LOG_2026-06-29_asset_alm_slice4b3b.*
- **Generic "execute every notebook" CI guard** — parametrise the exec guard over all `notebooks/*.ipynb`. *ADR-117 + DEV_SESSION_LOG_2026-06-29_asset_alm_slice4b4.*

**Reserve basis / statutory (12)**
- **Statutory reserve bases for UL and DI** — extend CRVM/VM-20/GAAP beyond Term/WL. *ADR-087.*
- **20-pay expense-allowance cap for short-pay whole life** — unblock WholeLife CRVM on short-pay/high-premium WL. *ADR-089.*
- **Exact VM-20 NPR refinements (X factors / deficiency)** — term-specific mortality X factors, select-period grading, deficiency. *ADR-090.*
- **VM-20 stochastic reserve (SR)** — CTE-70 stochastic reserve over prescribed scenarios (epic ships deterministic `max(NPR,DR)` only). *ADR-090.*
- **Broader DR expense components (commissions, premium tax)** — fuller gross-premium DR. *ADR-090.*
- **Reserve-basis selector on `scenario` / `uq` surfaces** — currently `price` path only. *ADR-092.*
- **Dashboard reserve-basis control (CLI/Streamlit parity)** — one control + state default. *ADR-092.*
- **Sex/smoker-distinct statutory valuation-table composition helper** — load per-sex/smoker CSVs into one `valuation_mortality` table. *ADR-125 + CONTINUATION_reserve_basis_exactness Refinement Backlog.*
- **Issue-year → CSO-version selector** — 2001 vs 2017 CSO + straddle handling. *ADR-126 + CONTINUATION_reserve_basis_exactness Refinement Backlog.*
- **CSV-path escape hatch for an arbitrary cedant valuation table** — `valuation_mortality_path` for non-standard tables. *ADR-126.*
- **Echo the prescribed valuation table on API / Excel / dashboard** — currently CLI JSON summary only. *ADR-126.*
- **Prescribed statutory valuation-interest helper (interest-exactness, Reserve-Basis-Correctness Slices 2–3)** — issue-year → SVL max rate resolver; DEMOTED to NICE-TO-HAVE by the 2026-07-05 checkpoint (distinct from IMPORTANT #4). *COMMERCIAL_VIABILITY_REVIEW_2026-07-05 + CONTINUATION_reserve_basis_correctness Checkpoint (2nd-order).*

**IFRS 17 (11)**
- **Heterogeneous-term cohort calendar alignment** — common grid before aggregating different-term contracts issued the same year. *ADR-093 + CONTINUATION_ifrs17_movement Open Questions.*
- **Cohort measurement under PAA / VFA** — Slice 1 is BBA-only. *ADR-093.*
- **Onerous-contract sub-grouping within an annual cohort** — IFRS 17.16 onerous / no-significant-possibility / remaining split. *ADR-093.*
- **Per-issue-year locked-in-rate override on the CLI** — `--ifrs17-locked-in-rates` JSON file (REST already accepts a map). *ADR-097.*
- **Dedicated `polaris ifrs17` movement-only subcommand** — emit the disclosure without a full pricing run. *ADR-097.*
- **Dashboard IFRS 17 movement view** — movement reachable on REST/Excel/CLI but not Streamlit. *ADR-097.*
- **Block-wide (cross-product) movement on a common calendar grid** — depends on heterogeneous-term alignment. *ADR-097 (2nd-order).*
- **Mid-life in-force movement opening** — period-0 opening = current in-force, no new-business line. *ADR-094 + DEV_SESSION_LOG_2026-06-20_ifrs17_movement_slice2.*
- **Explicit RA finance/unwinding line in the movement table** — split RA interest accretion from risk release. *ADR-094.*
- **IFRS 17 analysis-of-change (movement) dashboard view** — reuse the `to_dict()` serialiser (near-dup of the movement view above). *ADR-095 (2nd-order).*
- **Drive cohort locked-in rates from issue-era rate curves** — remove the manual flat override. *ADR-095 (2nd-order).*

**Expense allowance / experience refund (9)**
- **Gross- vs ceded-basis loss ratio for the sliding scale** — basis selector for treaties quoting against the gross block loss ratio. *ADR-118 + DEV_SESSION_LOG_2026-06-29_expense_allowance_slice1.*
- **Dedicated expense-allowance line on `CashFlowResult`** — distinct array (core-contract change). *ADR-118 + DEV_SESSION_LOG_2026-06-29_expense_allowance_slice1.*
- **Survivorship-weight the first-year fraction** — weight `f[t]` by in-force lx for mixed-duration blocks. *ADR-119.*
- **Per-policy (seriatim) expense-allowance allocation** — each policy's duration drives its first-year split. *ADR-119.*
- **Annual / per-period experience-refund settlement timing** — per-period schedule vs single end-of-horizon scalar. *ADR-120 + DEV_SESSION_LOG_2026-06-30_experience_refund_slice3a.*
- **Experience-refund deficit carryforward** — carry deficit against future favourable experience. *ADR-120 + DEV_SESSION_LOG_2026-06-30_experience_refund_slice3a.*
- **Echo applied `expense_allowance` / `experience_refund` terms on deal-pricing responses** — close the auditability gap (unlike `reserve_basis`). *ADR-123 + DEV_SESSION_LOG_2026-06-30_expense_allowance_slice3b2b1.*
- **`use_policy_cession` block-aware-duration fallback on the API path** — same fix as IMPORTANT #3, extended to `/api/v1/price` + scenario/uq/portfolio. *ADR-123 (2nd-order).*
- **Surface both terms on the Streamlit dashboard + `DealConfig.to_dict()`** — dashboard parity + round-trip (currently silently dropped). *ADR-124 + DEV_SESSION_LOG_2026-07-03_expense_allowance_slice3b2b2.*

**GAAP (2)**
- **FAS 60 DAC amortisation + loss-recognition / premium-deficiency test** — beyond the benefit-reserve-only Slice 3. *ADR-127 (2nd-order).*
- **Duration-varying / select-period GAAP PAD structures** — grade PADs by duration vs a single flat multiplier. *ADR-127 (2nd-order).*

**Goldens / validation (6)**
- **Cash-flow-vector golden (finer than per-cohort summary)** — catch offsetting per-period errors that net to the same summary. *ADR-105 (2nd-order).*
- **Pipeline goldens for Modco / stop-loss configs** — one-file add once those configs exist. *ADR-105 (2nd-order).*
- **AXIS/Prophet side-by-side validation case** — licensed-tool reference; REFERENCE-BLOCKED. *ADR-130 (2nd-order).*
- **Published held-reserve deck (VM-20 / CRVM worked example)** — validate the reserve path directly. *ADR-131 (2nd-order).*
- **User-supplied reference decks for `polaris benchmark`** — accept `case_id, expected, tolerance` CSV → reusable acceptance harness. *ADR-132 (2nd-order).*
- **Reconcile stale `tests/qa/golden_outputs/*.json` byte-format with the CLI `-o` schema** — regenerate snapshots or point the check at the parsed QA guard. *qa-on-pr review of PR #130.*

**Ops / observability / architecture (8)**
- ~~**Relocate `pipeline.py` out of `core/` (proper fix for the S0.2 layer violation)** — move to `polaris_re/pipeline.py`, update 27 importers + ADR; retires the CLAUDE.md §6 exception, not just the symptom fixed in ADR-155. Also: sweep other `__init__.py` for the same eager cross-layer re-export anti-pattern. *ADR-155 Out of scope (1st-order).*~~ — **SHIPPED** (S1 / ADR-156, PR #158): `git mv`'d `core/pipeline.py` → `polaris_re/pipeline.py`, rewrote all 28 in-repo importers, no shim; §6 exception retired. Anti-pattern sweep folded in — **no other eager cross-layer `__init__.py` re-exports found**. Goldens byte-identical.
- **Decompose the `polaris_re.pipeline` composition root (~887 lines)** — config parsing, treaty construction, and cohort iteration are separable concerns that could split into focused modules under a `composition/` package now that the file sits at the top level. Pure maintainability; no behaviour change. *ADR-156 Out of scope (1st-order).*
- **OpenTelemetry trace spans for the API** — span-level tracing behind an optional extra. *ADR-133.*
- **OIDC/JWT authentication as an alternative to static API keys** — IdP tokens, scopes, expiry/refresh. *ADR-134.*
- **Per-route / per-key rate-limit tiers** — shape load beyond the single global threshold. *ADR-134.*
- **API-key hardening: hashing, rotation, secret-store** — salted-hash comparison, overlapping keys, secret sourcing. *ADR-134.*
- **Richer instrumentation via `prometheus-client` / OpenTelemetry extra** — per-handler histograms, exemplars, traces. *ADR-135.*
- **Prometheus `ServiceMonitor`/`PodMonitor` CRD + CI manifest gating** — Operator-native scrape + `helm lint`/`kubeconform`. *ADR-135.*
- **Engine-level, entry-point-agnostic metrics** — instrument the core so CLI/Streamlit runs emit metrics, not just HTTP. *PR #135 review (2026-07-10).*

**CI perf/smoke — NICE-TO-HAVE tail (3)** *(group context in the IMPORTANT blockquote)*
- **pr-review routine posts the perf judgment comment** — fold a head-vs-main perf verdict (advisory, noise-band-suppressed) into the review comment; depends on IMPORTANT #9. *maintainer discussion 2026-07-12 (2nd-order).*
- **Seed `perf/history.jsonl` by backfilling meaningful commits (one-off)** — backfill ~10–15 engine-touching merges on one machine so creep detection is useful day one; depends on #9/#10. *maintainer discussion 2026-07-12 (2nd-order).*
- **Durable epic-grained history ledger (`CHANGELOG.md` / `docs/EPICS.md`)** — append-only, one row per completed epic, written when a CONTINUATION flips COMPLETE. Guardrail: must not precede constituting a Tier-A epic. *maintainer discussion 2026-07-12 (1st-order).*

**Ingestion (6)**
- **Live / per-cohort currency conversion** — multi-currency book / period-end FX needs a rate source beyond the single static `CurrencyConfig`. *ADR-137.*
- **Per-row provenance of the inferred date format** — annotate which source format each cell was read under. *ADR-137.*
- **Value coercion beyond monetary/date families** — light normaliser for messy free-text columns. *ADR-137.*
- **Machine-readable ingestion report sidecar** — `<output>.report.json` a pipeline could gate on. *ADR-138.*
- **Rejects-file format option** — `--rejects-format` (Parquet/JSON) preserving dtypes. *ADR-138.*
- **Streaming ingestion for out-of-core files** — Polars `scan_csv` + chunked partition. *ADR-138.*

**Experience-GAM (20)**
- **Exposure-weighted modal reference level for `ExperienceGAM` factor effects** — deterministic reference on equal-count levels (cosmetic; contrasts already invariant). *ADR-146 + DEV_SESSION_LOG_2026-07-22_experience_gam_slice4b1 (2nd-order).*
- **Full negative-binomial (estimated α) likelihood on the by-amount basis** — likelihood-based fit vs quasi-Poisson φ-scaling. *ADR-139.*
- **Lapse experience through the same GAM machinery** — the A/E-over-static-base form generalizes to lapse. *ADR-139 / PLAN_experience_gam "Out of Scope".*
- **Data-driven smoothness selection for the frequentist tensor MI surface** — penalized-GAM/GCV vs fixed-df (largely subsumed by HSGP). *ADR-140 (2nd-order).*
- **RW2 (linear-trend) forward-projection prior** — fanning-band alternative to mean-reversion. *ADR-142 + PLAN_experience_gam Open Decisions.*
- **Per-age / per-segment long-term improvement rate in the MI projection** — accept `float | np.ndarray` for `long_term_rate`. *ADR-142.*
- **Empirical-Bayes length-scale / amplitude selection for the Bayesian MI surface** — evidence-maximising vs fixed GP hyperparameters. *ADR-141.*
- **Select-and-ultimate (per-duration) CUSTOM improvement grids** — third axis / select-ultimate pair. *ADR-143.*
- **Carry a credible/confidence band alongside a CUSTOM scale** — propagate MI uncertainty into scenario/UQ vs dropping it at the assumption boundary. *ADR-143.*
- **Age-varying group-specific MI smoother (full Pedersen GS/GI HGAM)** — per-segment shrunk `te(age,year)` surface. *ADR-144.*
- **Exposure-weighted sum-to-zero centring for segment deviations** — Bühlmann-collective baseline vs unweighted. *ADR-144.*
- **Per-segment forward MI projection + NB variance component** — per-segment `project_improvement` + full-NB between-segment variance. *ADR-144.*
- **Sibling assumption kinds in the version store (lapse, base mortality)** — exercise the parameterised `kind` field. *ADR-147.*
- **Retention / prune policy for the append-only version store** — `polaris experience prune --keep-latest`. *ADR-147.*
- **Config selector for a built-in improvement scale (Scale AA / MP-2020)** — `mortality.improvement_scale` enum without the version store. *ADR-148.*
- **CLI surface for the experience data loaders (`polaris experience load-hmd`/`load-ilec`)** — start the chain from a raw cached file without a Python script. *ADR-149 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c1.*
- **Built-in HMD authenticated-session flow in `fetch_hmd`** — self-contained login on a fresh machine. *ADR-149 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c1.*
- **Real-data experience-improvement diligence run (HMD/ILEC vs published targets)** — compare fitted `MI_x(y)` against MIM-2021/CIA (gated on licensed data, never CI). *ADR-150 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c2.*
- **Execute the `mgcv` oracle on an R-equipped dev box** — exercise the `rpy2`→`mgcv` glue (absent in CI by design). *ADR-151 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c3.*
- **Wire experience-GAM diagnostics into the Streamlit dashboard** — interactive effects / MI-surface slices / projection fan reusing `all_effects()`/`--grid-out`. *ADR-153 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4d2.* **→ folded into Next Sprint S2 (maintainer-directed 2026-07-24), the MI dashboard page.**

---

## Comparison with Previous Assessment

`PRODUCT_DIRECTION_2026-06-18` reported **no BLOCKERs**, three lead IMPORTANT
epics in flight (reserve-basis matching, IFRS 17 movement, cross-jurisdiction
capital), and a large NICE-TO-HAVE queue. The **material change** since: all
three lead epics **shipped**, and so did the entire 2026-07-05 productization
ladder (A1′ validation, A2′ hardening, A3′ ingestion) **and** the A4′
experience-GAM epic — the last unstarted roadmap milestone. The gap-tier
picture at the top has therefore **inverted**: where 2026-06-18 had three
IMPORTANT epics gating a large-reinsurer deal, **no Tier-A "big rock" remains**.

The IMPORTANT queue is now **12 harvested follow-ups** — refinements of shipped
epics (statutory-table exactness, multi-replica ops caveats, CI perf/smoke
infra, the Bayesian-backend confirmation, and dashboard/API surfacing of the
improvement selector), not new frontier gaps. The NICE-TO-HAVE queue (90) is
the accumulated out-of-scope harvest of ~70 shipped PRs; it grows in the polish
direction, which is exactly why the review's Phase-7 decision matters: **without
a chosen frontier the routine is in maintenance mode**, drawing this queue down
one quick win at a time (B1 → B2 → B4 → C…). The reasonability profile is
**unchanged** — no new flag emerged. The single strategic item for the
maintainer is the **Phase-7 go/no-go** surfaced above.
