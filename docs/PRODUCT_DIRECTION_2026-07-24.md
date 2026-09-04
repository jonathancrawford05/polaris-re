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
| ~~**B1**~~ | ~~**Switch capital surfaces to `for_product_interim`** — expose the built C-1/C-3 factors everywhere~~ — **SHIPPED** (PR #162 / ADR-160): the `licat` branch of `capital_model_for` now resolves to `for_product_interim`, surfacing interim C-1/C-3 + extended C-2 on the CLI/API/dashboard priced path, aligned with the portfolio roll-up and RBC/SII. **No golden rebaseline** — no QA golden config enables a capital model, so `polaris price` is byte-identical (guards 23/23). Behaviour change flagged for human review on the draft PR. | ★★★★☆ | ~1–2 d | Was unshipped after three reviews; shipped 2026-07-25. |
| ~~**B2**~~ | ~~**Scale benchmark at 100K–500K policies** — publish a timing table; back the README perf claim~~ — **SHIPPED** (PR #163 / ADR-161): `analytics/scale_benchmark.py` harness times the production `project()` path across sizes; committed table (1K→500K, ~linear time growth, ~7.5K–17K policies/sec) published in the README *Performance & scale* section + `docs/PERFORMANCE.md`; regenerator `scripts/scale_benchmark.py`. Additive-only — goldens byte-identical. | ★★★★☆ | ~1 d | Shipped 2026-07-25; was unshipped after three reviews. |
| ~~**B4**~~ | ~~**Premium-deficiency reserve / loss recognition** — turn the sufficiency analyzer into a reserve floor~~ — **SHIPPED** (PR #164 / ADR-162): `analytics/premium_deficiency.py` `PremiumDeficiencyTester` computes the FAS 60 / ASC 944 loss-recognition test at the valuation date — `GPV = PV(benefits + expenses) − PV(premiums)` (exactly `−sufficiency_margin`, reusing `PremiumSufficiencyTester` verbatim), `PDR = max(0, GPV − existing_reserve)`, `reserve_floor = max(existing_reserve, GPV)`. Additive-only — goldens byte-identical. | ★★★☆☆ | ~1 d | Shipped 2026-07-26; was unshipped after three reviews. |

B1 and B2 are the cleanest between-epic fallback picks and the **S3** sequence
(value-per-day order: B1 → B2 → B4), now behind the maintainer-directed S1
(`pipeline.py` relocation) and S2 (MI dashboard page).

### Tier C — Medium value, enabling / operational

| # | Feature | Value | Effort |
|---|---------|-------|--------|
| ~~C3~~ | ~~Funds-withheld coinsurance (`FWCoinsuranceTreaty`)~~ — **SHIPPED** (PR #166): Slice 1 (PR #165, ADR-163: treaty module + funds-withheld interest) + Slice 2 (PR #166, ADR-164: surfaced on CLI/API/dashboard + `golden_fw_coins`); both merged to main 2026-07-27. `docs/CONTINUATION_fw_coinsurance.md` [COMPLETE]. (Ledger-healed this session, step 4b.) | ★★★☆☆ | ~2 d |
| C4 | Parallel portfolio execution + caching + `remove_deal` — **IN PROGRESS** (constituted 2026-08-02 as a 3-slice MEDIUM epic: `docs/PLAN_portfolio_execution.md` + `docs/CONTINUATION_portfolio_execution.md`). **Slice 1 SHIPPED** (PR #181 / ADR-178, **MERGED** to main `a160246` — ledger-healed 2026-08-02 step 4b): the deal-lifecycle API (`remove_deal` / `replace_deal` / `clear_deals` / `without_deal` / `deal_ids` / `get_deal` / `len` / `in`). **Slice 2 SHIPPED** (PR #182 / ADR-179, **MERGED** to main `39729fb` — ledger-healed 2026-08-02 step 4b): opt-in per-deal result cache `Portfolio(cache=True)` keyed `(deal_id, hurdle_rate)`, per-deal invalidation on all four mutation verbs, `without_deal` copies inherit surviving entries (leave-one-out sweep drops from `N x (N-1)` projections to `N`), `_with_scenario` starts empty, plus `clear_cache()` / `cache_stats()`. ~~Slice 3 = parallel execution (behind a measurement gate).~~ — **SHIPPED** (PR #183 / ADR-180): `run(max_workers=N)` + `run_with_capital` / `run_scenarios` forwarding, one task per deal collected by index, bit-identical at every worker count, plus the committed measurement `scripts/bench_portfolio_parallel.py`. The measurement gate came back **below the bar** (peak 1.29x; 0.48-0.59x — slower than serial — at 4/8 workers on small deals, 4-core runner), so the speed-up is **published, not claimed**, and the knob's disposition is flagged for the maintainer in ADR-180. **This closes epic C4** (all 3 slices shipped). | ★★★☆☆ | ~2 d |
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
- **S3 — Tier-B quick wins in value-per-day order: ~~B1~~ → ~~B2~~ → ~~B4~~** (was S0.3; now
  follows S1+S2; see the re-ranked catalogue). Independently valuable
  maintenance-mode PRs while no Phase-7 frontier is chosen. **ALL THREE SHIPPED:**
  **B1** 2026-07-25 (PR #162 / ADR-160 — LICAT resolver → `for_product_interim`);
  **B2** 2026-07-25 (PR #163 / ADR-161 — scale benchmark at 100K–500K policies);
  **B4** 2026-07-26 (PR #164 / ADR-162 — premium-deficiency reserve / loss
  recognition). **S3 is now complete** — the Tier-B Sprint-0 queue is drawn down.
- **Then** Tier-C (C3/C4/C5/C6) or a chosen Phase-7 epic (which, once picked,
  is constituted via step 5b: PLAN + slice 1). With S3 exhausted, the next
  maintenance-mode fallback is the Tier-C queue (in value-per-day order) unless
  the maintainer charts a Phase-7 frontier.

---

## Carried-Forward Promoted Follow-ups

Unresolved items harvested by the daily-dev routine (step 17) from the prior
file, provenance preserved. **These are first-class work items, not
commentary.** Full prose per item: `PRODUCT_DIRECTION_2026-06-18.md`
"Promoted Follow-ups". Count: **12 IMPORTANT + 90 NICE-TO-HAVE = 102.** No
BLOCKER remains.

### IMPORTANT (12)

1. ~~**Statutory valuation mortality table (2001 CSO) for CRVM.** TermLife/WholeLife
   CRVM value on projection best-estimate mortality, not the prescribed 2001 CSO
   table; a distinct `valuation_mortality` slot is needed to reproduce a cedant's
   US statutory CRVM reserve exactly. *Source: ADR-089 Out of scope (1st-order).*~~
   — **SHIPPED** (PR #125 / ADR-125, Reserve-Basis Exactness Slice 1): the distinct
   `assumptions.valuation_mortality` slot exists and CRVM / VM-20 NPR value on it
   (`TermLife._valuation_q` / `_build_rate_arrays`; `--valuation-mortality` CLI flag,
   `deal.valuation_mortality` config key, `load_valuation_mortality`; no improvement
   applied on the valuation grid). **Closed by inspection this session (step 6 PRUNE):**
   the carried-forward item predates ADR-125 (Source was ADR-089). The residual
   sex/smoker composition + CSO-version selection are already tracked as the separate
   NICE-TO-HAVE items "Sex/smoker-distinct statutory valuation-table composition
   helper" (ADR-125) and "Issue-year → CSO-version selector" (ADR-126) — not
   reopened here.
2. **Close the WL terminal-reserve artefact on the NET_PREMIUM basis.** The default
   NET_PREMIUM WL reserve still uses a one-period terminal estimate that collapses
   at the horizon; prospective-to-omega valuation moves goldens → needs its own ADR
   + rebaseline. *Source: ADR-089 Out of scope + DEV_SESSION_LOG_2026-06-19_reserve_basis_slice2b Open Questions (1st-order).*
3. ~~**Engage block-aware first-year duration mapping when an `expense_allowance` is
   supplied via config.** With an allowance set but `use_policy_cession` unset, the
   allowance falls back to the new-business projection-month basis, wrongly charging
   the high first-year rate on renewal inforce; fix is to force the cohort inforce
   through `apply()` whenever an allowance is present. *Source: ADR-122 Out of scope + DEV_SESSION_LOG_2026-06-30_expense_allowance_slice3b2a Open Questions (1st-order).*~~
   — **SHIPPED** (PR #168 / ADR-166 engine + PR #169 / ADR-167 caller wiring):
   `BaseTreaty.apply` decouples per-policy cession (keyword `use_policy_cession`)
   from block-aware allowance mapping (keyed on `inforce` presence), and every
   deal-path caller (CLI `_price_single_cohort`, `/api/v1/price`, dashboard) now
   passes `inforce` unconditionally with the deal's flag. **MERGED** to main
   2026-07-27 (ledger-healed this session, step 4b). The optional Slice 3
   (scenario/uq/portfolio runner-internal parity) is 2nd-order and tracked as a
   NICE-TO-HAVE.
4. **Prescribed statutory valuation-interest helper.** Issue-year → prescribed
   valuation-interest-rate lookup so statutory CRVM reproduction is penny-exact on
   the interest side (currently directional via a single manual rate). *Source: ADR-125 Out of scope + CONTINUATION_reserve_basis_exactness Refinement Backlog (1st-order); reclassified per ADR-126 / PR #125 review.*
5. ~~**Surface the GAAP (FAS 60) PADs on the deal path (`DealConfig` / CLI / API).**
   The two GAAP PADs live on `ProjectionConfig` but are not exposed via the CLI
   config parser, `--gaap-*` flags, or REST `PriceRequest`. *Source: ADR-127 / ADR-128 Out of scope (1st-order).*~~ — **SHIPPED** (PR #167, ADR-165) — **MERGED** to main 2026-07-27 (ledger-healed this session, step 4b).
   `DealConfig.gaap_mortality_pad` / `gaap_interest_margin` (both neutral by
   default) parse from both config schemas and thread through
   `build_projection_config`; `--gaap-mortality-pad` / `--gaap-interest-margin`
   CLI flags override the config (echoed in the JSON summary only when non-neutral);
   `PriceRequest` carries both (out-of-range → 422) and `PriceResponse` echoes them.
   Neutral defaults keep every existing config / run / response byte-identical; the
   PADs are consumed only on the GAAP reserve basis. Strike through once merged.
6. **Shared rate-limit backend for multi-replica deployments.** The in-process
   limiter counts per replica, so behind N replicas the effective limit is ~N× the
   configured threshold — a silent correctness caveat on a shipped, deployed
   feature. *Source: ADR-134 Out of scope (1st-order).*
7. **Shared backend for multi-replica metrics aggregation.** The in-process
   `MetricsRegistry` exposes per-pod counters; exact global counts (without
   Prometheus sum-by) need a shared/remote-write backend. *Source: ADR-135 Out of scope (1st-order).*
8. ~~**CI smoke-test job (real entry points).** A fast (<30s) deterministic job that
   boots uvicorn and curls `/health`, `/metrics`, a real `/api/v1/price`, runs
   `polaris price` + `polaris benchmark --pack closed-form`, gating merges — catches
   "won't boot / endpoint 500s" that unit tests miss. *Source: maintainer discussion 2026-07-12 (CI perf/smoke thread), 1st-order.*~~
   — **SHIPPED** (PR #170 / ADR-168): a CI `smoke` job boots a live `uvicorn` server
   (`/health`, `/metrics`, real `POST /api/v1/price`) and the `polaris` console script
   (`price` on the golden deal + `benchmark --pack closed-form`), gating merges alongside
   lint/test/docker; whole pack ~4.6 s, all `-m smoke`/`slow`-tagged. **MERGED** to main
   2026-07-27 (ledger-healed this session, step 4b).
9. ~~**Performance harness with same-run head-vs-main baseline.** A `polaris perfbench`
   / `tests/perf/` harness timing engine hot paths on a fixed synthetic block +
   deterministic structural metrics, benchmarking head and main **in the same job**
   (noise-cancelling ratio → `perf.json`). Prerequisite for #10 and NICE-TO-HAVE
   #62/#63. *Source: maintainer discussion 2026-07-12, 1st-order.*~~
   — **SHIPPED** (perf-harness epic, Slices 1–3; ADR-169 / ADR-175 / ADR-176):
   Slice 1 (PR #171, MERGED) the deterministic perf-probe core
   (`analytics/perf_harness.py`); Slice 2 (PR #178, MERGED `750a6a7`) the
   head-vs-main `diff_reports` verdict + `scripts/perfbench.py` git-worktree
   runner; **Slice 3 (ADR-176, PR #179)** the CI `perf` job that runs
   `scripts/perfbench.py --ref origin/main --no-fetch` on one PR-only runner,
   **gates the merge on a structural hard delta** (never on the advisory
   wall-time / peak-MiB alerts), and uploads `perf.json`. `CONTINUATION_perf_harness`
   → COMPLETE (mandatory scope). The optional Slice 4 (`perf/history.jsonl` creep
   log) is the standing IMPORTANT #10 below.
10. ~~**Committed per-merge performance log (`perf/history.jsonl`) + creep detection.**
    One append-only deterministic-first row per merge to `main`, to catch slow
    multi-month creep a per-PR comment structurally cannot. Depends on #9.~~ *Source: maintainer discussion 2026-07-12, 1st-order.*
    — **SHIPPED** (PR #180 / ADR-177, 2026-08-02; **MERGED** to main `51701b1` —
    ledger-healed 2026-08-02 step 4b): `analytics/perf_history.py`
    (`PerfHistoryRow` + `append_history_row`/`load_history` + `detect_creep` →
    `CreepVerdict`) and the runner `scripts/perf_history.py` record one
    deterministic-first row per commit into the committed append-only
    `perf/history.jsonl` and check the whole series for creep — earliest-window vs
    recent-window **median**, gating only on the machine-portable MiB-peak
    (wall-time / config drift advisory only, per the 2026-07-12 rule). Commit dates
    come from `git show -s --format=%cI` (ADR-074, never the clock); the runner is
    idempotent per commit. Additive-only — goldens byte-identical. The **automatic
    per-merge CI append + commit-back-to-`main`** is deliberately deferred (needs
    `contents: write` / maintainer authorization for a bot commit to `main`) and is
    harvested below; the one-off backfill (NICE-TO-HAVE #63) is now unblocked.
11. **Confirm the ADR-141 backend deviation for the Bayesian MI surface.** Slice 2b
    shipped a pure-NumPy/SciPy reduced-rank GP instead of the PLAN-locked
    `bambi`/`pymc` HSGP (defective in installed versions); maintainer should confirm
    this direction — it now blocks only the optional `pymc`-NUTS audit path. *Source: ADR-141 human-review flag + DEV_SESSION_LOG_2026-07-22 DISCOVERY (1st-order).*
12. ~~**Surface the experience-improvement selector on the dashboard + REST API.** The
    versioned `ImprovementScale.CUSTOM` basis is wired into `--config` and a
    `--improvement-version` CLI flag but not the dashboard Deal Pricing page or REST
    `/price` schema. *Source: ADR-148 Out of scope (1st-order).*~~ — **SHIPPED** (fully
    closed across MI dashboard Slices 2–3). Dashboard half: PR #160 / ADR-158 (Slice 2) —
    the Deal Pricing page's versioned-improvement selector lists the store's CUSTOM bases
    and drives the run byte-identically to the CLI `--improvement-version` path. REST-API
    half: PR #161 / ADR-159 (Slice 3) — `PriceRequest` gains an optional
    `improvement_version` (a store `version_id`) loaded server-side via
    `load_improvement_version` and threaded onto `AssumptionSet.improvement`, echoed on
    the response; unknown id → 422; default `None` byte-identical. **All three surfaces
    (CLI, dashboard, API) now drive a priced run from a versioned experience basis —
    IMPORTANT #12 CLOSED.**

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
- ~~**Wire experience-GAM diagnostics into the Streamlit dashboard** — interactive effects / MI-surface slices / projection fan reusing `all_effects()`/`--grid-out`. *ADR-153 + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4d2.* **→ folded into Next Sprint S2 (maintainer-directed 2026-07-24), the MI dashboard page.**~~ — **SHIPPED** (S2 Slice 1 / ADR-157, PR #159): new "Mortality Improvement" dashboard page (`views/experience_improvement.py`) rendering fitted effects (`plot_effects`), the `MI_x(y)` surface slices (`plot_mi_surface`), a band-width heatmap (`plot_mi_surface_bandwidth`), and — behind a slow toggle — the Bayesian projection fan (`plot_mi_projection`), plus an MI-grid CSV download. `AppTest` flows + helper unit tests; goldens byte-identical.

### Harvested 2026-07-24 (MI dashboard Slice 1 — ADR-157)

New follow-ups surfaced by ADR-157's "Out of scope" (all 1st-order — follow-ups
of the originally-planned S2 MI dashboard page; both NICE-TO-HAVE — convenience
polish on a shipped surface, not a production-correctness gap):

- **Standard-table `q_base` attach path on the MI dashboard page** — build the
  static base offset from a standard mortality table (as the CLI's
  `polaris experience improvement --table` does) so a dashboard user can fit
  from an experience CSV that lacks a pre-built `q_base` column. Slice 1
  requires the column. *Source: ADR-157 Out of scope (1st-order).*
- ~~**Cache the interactive MI fit across reruns**~~ — **SHIPPED** (PR #159,
  ADR-157 follow-up, maintainer-directed): the frequentist GLM fits are now
  cached in `st.session_state` by a content+config signature that excludes the
  confidence level, so a slider move re-derives bands without refitting.
- **Add a saved-version load path on the MI *diagnostics* page** — load a fitted MI
  surface from the version store alongside upload/sample on the diagnostics page
  (the caching half of this item shipped above). This is distinct from Slice 2's
  *pricing* selector (PR #160), which reads the store to drive a priced run but
  does not render a stored surface's diagnostics. *Source: ADR-157 Out of scope
  (1st-order).*
- ~~**REST-API half of the experience-improvement selector (IMPORTANT #12, API
  half)** — add `improvement_version` to the `/api/v1/price` `PriceRequest`
  schema and thread it through the same pipeline path, echoed on the response.
  The dashboard half shipped in Slice 2 (PR #160); this is the optional Slice 3.
  *Source: ADR-158 Out of scope (1st-order); carried forward from IMPORTANT #12.*~~
  — **SHIPPED** (MI dashboard Slice 3 / ADR-159): `PriceRequest.improvement_version`
  (a store `version_id`) loaded server-side via `load_improvement_version` and threaded
  onto `AssumptionSet.improvement`; echoed on `PriceResponse`; unknown id → 422; default
  `None` byte-identical. Closes IMPORTANT #12.
- **Thread `improvement_version` through `/api/v1/scenario` and `/api/v1/uq`** — Slice 3
  surfaced the versioned basis on `/api/v1/price` only; a stressed / Monte-Carlo run on a
  frozen experience basis is not yet reachable over the API (the scenario/uq DTOs already
  omit `reserve_basis` / `valuation_mortality` for the same "pricing surface first" reason).
  NICE-TO-HAVE. *Source: ADR-159 Out of scope (2nd-order).*
- **Store-authoring REST API over the assumption-version store** — versions are authored
  only via `polaris experience save`; both the dashboard and the REST API are read-only
  over the store. A create/freeze-over-HTTP flow would let an integration client persist a
  fitted MI surface without the CLI. NICE-TO-HAVE. *Source: ADR-159 Out of scope
  (2nd-order).*
- **Fuller provenance panel in the Deal-Pricing version selector** — the Slice-2
  selectbox shows a compact label (id + study date + optional label + credibility)
  and an override info line; surface the version's `notes` / source-study
  provenance in a panel so the actuary sees the full audit trail before pricing on
  it. NICE-TO-HAVE. *Source: ADR-158 Out of scope (2nd-order).*
- **Store-management UI over the assumption-version store** — versions are authored
  only via `polaris experience save`; the dashboard is read-only over the store.
  A create/save-from-dashboard flow would let a fitted MI surface be frozen without
  dropping to the CLI. NICE-TO-HAVE. *Source: ADR-158 Out of scope (2nd-order).*

> The experience-improvement selector (IMPORTANT #12) is now **fully SHIPPED** across
> all three surfaces: CLI (`--improvement-version` / `mortality.improvement_version_id`),
> dashboard Deal Pricing (**Slice 2** — PR #160, ADR-158), and the REST API
> (**Slice 3** — ADR-159, `/api/v1/price` `improvement_version`). **IMPORTANT #12 CLOSED**;
> the MI dashboard epic (`CONTINUATION_mi_dashboard.md`) is COMPLETE.

### Harvested 2026-07-25 (B1 LICAT interim resolver — ADR-160)

New follow-ups from ADR-160's "Out of scope". B1 is a catalogue (planned) Tier-B item, so its
out-of-scope items are **1st-order** and promoted normally.

- **ALM-derived shock-based C-1 / C-3 calibration for LICAT (supersede the interim placeholders).**
  B1 made the interim ADR-072 committee-stage placeholders (C-1 = 0.5% of reserves; C-3
  duration-scaled) the **default** LICAT priced basis. They are conservative screening placeholders,
  not calibrated capital. The proper successor derives C-1 (asset default) and C-3 (interest-rate)
  from a shock-based asset / ALM model — the Phase-5.4 work the ADR-072 comment anticipated and the
  Asset/ALM epic (ADR-108..117) did **not** deliver for the LICAT factors. Now that these factors
  drive every priced LICAT deal (not just the portfolio surface), calibrating them is a
  production-correctness concern. Overlaps the existing NICE-TO-HAVE "Mutually calibrate the three
  capital standards' factors" (Capital & solvency group) — this promotes the LICAT half to
  **IMPORTANT** given the default flip. *Source: ADR-160 Out of scope (1st-order).* **IMPORTANT.**
- **Configurable capital-basis selector (interim vs mortality-only) on the CLI / API.** A user who
  wants the pre-B1 mortality-only `for_product` basis (or the extended-C-2-without-C-1/C-3 basis)
  has no flag to select it; B1 hard-switches the resolver. A `--capital-basis` option (or a
  per-run factor override surfaced on the config) would restore that choice. *Source: ADR-160 Out
  of scope (1st-order).* **NICE-TO-HAVE.**
- **Interim asset/interest loadings for RBC / Solvency II beyond their `for_product` defaults.**
  Their `for_product` constructors already load asset/interest components, but there is no
  `for_product_interim`-equivalent screening overlay for parity with the LICAT interim basis if one
  is ever wanted. *Source: ADR-160 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Rebaseline any documentation / notebook that quotes pre-B1 LICAT capital numbers.** Worked
  examples or notebook cells that printed LICAT `peak_capital` / `pv_capital` / RoC on the priced
  path now understate the interim-basis figures; a sweep would keep the docs consistent with the
  shipped default. *Source: ADR-160 Out of scope (1st-order).* **NICE-TO-HAVE.**

### Harvested 2026-07-25 (B2 scale benchmark — ADR-161)

New follow-ups from ADR-161's "Out of scope". B2 is a catalogue (planned) Tier-B item, so its
out-of-scope items are **1st-order** and promoted normally.

- **Surface the scale benchmark as a `polaris` CLI subcommand.** B2 ships the harness as
  `analytics/scale_benchmark.py` + `scripts/scale_benchmark.py`; it is deliberately **not** a
  `polaris` subcommand so the correctness-only `polaris benchmark` stays unambiguous. A distinct
  `polaris scale-benchmark` (or `polaris benchmark --timing`) would give ops a one-command timing
  check without the `scripts/` invocation. *Source: ADR-161 Out of scope (1st-order).*
  **NICE-TO-HAVE.**
- **Benchmark product engines beyond TermLife (WholeLife / UL / DI-CI).** The published table times
  only the TERM engine. The other product engines share the vectorized `(N × T)` design, so a
  per-engine timing table would extend the perf evidence across the modeled surface (and catch a
  per-engine `O(N²)` regression the TERM-only slow test would miss). Pairs with the existing
  NICE-TO-HAVE "parallel portfolio execution" (Tier-C C4) but is independent of it. *Source:
  ADR-161 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **CI performance-regression gate.** ADR-161 adds a `@pytest.mark.slow` scaling-shape test (4× the
  block must take < 6× the time) that catches a reintroduced per-policy Python loop, but there is no
  CI job that runs it or trends wall-clock over time. Folding a timing job into CI **overlaps the
  existing IMPORTANT "CI perf/smoke infra" follow-up** — recorded here as the B2-specific slice of
  that item, not as a new duplicate. *Source: ADR-161 Out of scope (1st-order; overlaps existing
  IMPORTANT CI-perf item).* **NICE-TO-HAVE.**

### Harvested 2026-07-26 (B4 premium-deficiency reserve — ADR-162)

New follow-ups from ADR-162's "Out of scope". B4 is a catalogue (planned) Tier-B item, so its
out-of-scope items are **1st-order** and promoted normally.

- **Per-period roll-forward of the reserve floor across the projection.** ADR-162 ships the
  point-in-time loss-recognition test at the valuation date only. A roll-forward would compare the
  prospective gross premium reserve to the held reserve at every future duration and report the
  reserve-floor *path* (catching a deficiency that emerges mid-projection even when the inception
  test passes). The blocker is a design question: the aggregate `CashFlowResult` flows embed
  survivorship from inception, so a per-duration prospective reserve needs a per-survivor
  normalization decision. *Source: ADR-162 Out of scope (1st-order).* **IMPORTANT** — a
  deficiency the inception test misses is a production-correctness gap on the loss-recognition
  common path, not polish.
- **Surface the premium-deficiency reserve on the CLI / dashboard / REST API.** The tester is
  module-only (mirroring how `PremiumSufficiencyTester` itself was module-first, then surfaced over
  later slices — ADR-083). A deficiency panel alongside the existing sufficiency tables (CLI Rich
  table + JSON dict; dashboard; `/api/v1/price` echo) would make the reserve floor reachable to
  non-Python users. **The dashboard surface is spec'd in `docs/PLAN_pdr_dashboard.md`** (key
  constraint: net against the block's valuation-date held reserve `reserve_balance[0]`, not the
  0.0 default — otherwise the tile is redundant with the sufficiency margin). *Source: ADR-162 Out
  of scope (1st-order).* **NICE-TO-HAVE.**
- **Wire the reserve floor back into the projected `reserve_balance`.** ADR-162 reports the PDR as
  a standalone diagnostic; it does not strengthen the projected reserve so downstream profit / IRR
  reflect the established deficiency reserve. Doing so touches the `CashFlowResult` reserve path and
  the profit tester — a controlled contract change, not additive. *Source: ADR-162 Out of scope
  (1st-order).* **NICE-TO-HAVE.**
- **DAC / unearned-premium components of the full FAS 60 test.** The benefit-reserve-only model
  carries no DAC balance, so the test nets only against `existing_reserve`. A model with deferred
  acquisition costs would add the unamortized DAC to the deficiency comparison (cf. ADR-127's
  loss-recognition follow-up). *Source: ADR-162 Out of scope (1st-order; overlaps ADR-127 DAC
  follow-up).* **NICE-TO-HAVE.**

### Harvested 2026-07-26 (FW coinsurance Slice 1 — ADR-163)

New follow-ups from ADR-163's "Out of scope (Slice 1)". C3 is a catalogue
(planned) Tier-C item, so its out-of-scope items are **1st-order** and promoted
normally. (The Slice-2 **surfacing** work — wiring `FWCoinsurance` into
`build_treaty` / CLI / REST / dashboard + a pipeline golden — is NOT harvested
here: it is the next slice of the IN PROGRESS `CONTINUATION_fw_coinsurance` and
is tracked there.)

- **Sliding-scale `ExpenseAllowance` / `ExperienceRefund` layers on FW coinsurance.**
  `CoinsuranceTreaty` / `YRTTreaty` carry the optional sliding-scale expense
  allowance and terminal experience-refund transfers; `FWCoinsuranceTreaty`
  Slice 1 models only the proportional `include_expense_allowance` split. Adding
  the two optional layers (reusing `BaseTreaty._expense_allowance_transfer` /
  `_experience_refund_transfer`) would bring FW coinsurance to parity with the
  other proportional treaties for treaties quoting an allowance / profit share.
  *Source: ADR-163 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Stochastic / amortising funds-withheld balance distinct from the ceded reserve.**
  Slice 1 takes the funds-withheld balance equal to the ceded reserve balance.
  A real funds-withheld account can diverge (deposits, withdrawals, its own
  crediting mechanics); a distinct balance track would let the interest accrue on
  an actual FW-account roll-forward rather than the notional ceded reserve.
  *Source: ADR-163 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **"Funds-withheld modco" variant.** FW mechanics (withheld assets + interest
  credit) applied to a modco-style *non-transferred* reserve — a further treaty
  variant distinct from `FWCoinsuranceTreaty` (which transfers the reserve like
  coinsurance). *Source: ADR-163 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Remove the dead `validate_fw_rate_positive` / `validate_modco_rate_positive`
  `@model_validator`s.** Both `FWCoinsuranceTreaty` and `ModcoTreaty` declare the
  rate field with `Field(ge=0.0, le=1.0)`, so Pydantic rejects negatives at field
  validation before the after-validator body runs — the `< 0.0` branch is
  unreachable dead code. A one-line cleanup in **both** `fw_coinsurance.py` and
  `modco.py` (kept consistent across the two sibling proportional-interest
  treaties; not expanded into this Slice-1 PR to avoid touching the unrelated
  `modco.py`). *Source: PR #165 automated review [P2] (2nd-order).* **NICE-TO-HAVE.**

### Harvested 2026-07-27 (FW coinsurance Slice 2 — ADR-164; CONTINUATION closed)

Slice 2 surfaced `FWCoinsurance` on the CLI / REST API / dashboard (ADR-164) and
**closes `CONTINUATION_fw_coinsurance`**. Surviving refinement items promoted per
the HARVEST step. All are 1st-order follow-ups of a planned Tier-C feature but
touch only advanced / comparison use — none affect production correctness on the
common path — so all are NICE-TO-HAVE.

- **Dedicated `funds_withheld_rate` config/request field distinct from `modco_rate`.**
  Slice 2 reuses `modco_rate` / `modco_interest_rate` as the funds-withheld rate
  (ADR-164). A separate field is only needed if a single config must express
  *distinct* modco and FW rates simultaneously (e.g. a treaty-comparison surface
  pricing both side by side). Additive follow-up.
  *Source: CONTINUATION_fw_coinsurance Refinement Backlog #1 / ADR-164 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Add `FWCoinsurance` to the dashboard Treaty Comparison page.** Slice 2
  surfaced it on the Deal Pricing (Assumptions) treaty selector; the
  Treaty Comparison page's multiselect (`Gross / YRT / Coinsurance / Modco`)
  does not yet offer it. A one-line options addition plus the comparison
  page's projection wiring.
  *Source: CONTINUATION_fw_coinsurance Refinement Backlog #2 / ADR-164 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Thread `ExpenseAllowance` / `ExperienceRefund` and the `AssetPortfolio`
  book-yield path through the surfaces for FW coinsurance.** The
  `FWCoinsuranceTreaty` engine supports the asset-driven funds-withheld rate
  (Option A) and could carry the allowance/refund layers, but no pricing surface
  threads an asset portfolio into a *proportional* treaty today — a shared gap
  with Modco, not FW-specific. Surfacing it is a cross-treaty enhancement.
  *Source: CONTINUATION_fw_coinsurance Refinement Backlog #3 / ADR-164 Out of scope (1st-order).* **NICE-TO-HAVE.**

### Harvested 2026-07-28 (GAAP PADs on the deal path — ADR-165; IMPORTANT #5 shipped)

IMPORTANT #5 shipped (ADR-165): the two GAAP (FAS 60) PADs are now surfaced on the
CLI (`--gaap-mortality-pad` / `--gaap-interest-margin` + config keys) and the REST
`PriceRequest` / `PriceResponse`. Surviving out-of-scope item promoted per the
HARVEST step. 1st-order (follow-up of the originally-planned IMPORTANT #5); it is
convenience polish on a shipped surface, not a production-correctness gap → NICE-TO-HAVE.

- **Surface the two GAAP PADs on the Streamlit dashboard Deal Pricing page +
  `DealConfig.to_dict()` round-trip.** ADR-165 surfaced the PADs CLI/API-first
  (the `valuation_mortality` / `expense_allowance` precedent: no dashboard surface
  consumes them yet, so they are omitted from `to_dict()`). A dashboard slice
  would add two inputs (a mortality-PAD number and an interest-margin number,
  shown/enabled only when the reserve basis is GAAP) and round-trip them through
  the session-state `deal_config` dict, giving non-CLI users the same
  adverse-deviation control. *Source: ADR-165 Out of scope (1st-order).* **NICE-TO-HAVE.**

> The other two ADR-165 out-of-scope items — **duration-varying / select-period
> GAAP PAD structures** and **FAS 60 DAC amortisation / full loss-recognition on
> the deal path** — are already carried in the NICE-TO-HAVE **GAAP (2)** group
> above (from ADR-127); ADR-165 does not create new duplicates, it reinforces them.

### Appended 2026-07-27 (expense-allowance duration Slice 2, ADR-167)

- **Block-aware allowance mapping on the scenario / uq / portfolio paths.**
  ADR-167 (Slice 2) wired the block-aware sliding-scale allowance duration
  mapping into the common quoting path — CLI `polaris price`, REST
  `/api/v1/price`, and the dashboard projection — closing the IMPORTANT #3
  correctness gap there. The `/api/v1/scenario`, `/api/v1/uq`, and portfolio
  treaty-apply paths still run the allowance on the treaty's own internal path
  (the CLI scenario/uq *parity dumps* are rewired, but the `ScenarioRunner` /
  `MonteCarloUQ` / portfolio engines are not). Those DTOs also omit
  `reserve_basis` / `valuation_mortality` for the same "pricing-surface-first"
  reason, so this is design-parity polish on the non-headline surfaces, not a
  correctness gap on the common quoting path. Also tracked as the optional
  Slice 3 in `docs/CONTINUATION_expense_allowance_duration.md` (IN PROGRESS).
  *Source: ADR-167 Out of scope (2nd-order — companion to IMPORTANT #3).* **NICE-TO-HAVE.**

> **On IMPORTANT #3 (this section, above).** Its common-path fix ships in Slice 2
> (ADR-167) but the PR is an unmerged draft, so the entry is left un-struck; the
> morning ledger-healing step (4b) should strike it once the Slice 2 PR merges.
> **UPDATE 2026-07-27:** PR #169 (Slice 2) is now **MERGED** to main; IMPORTANT #3
> struck through above (step 4b, this session).

### Harvested 2026-07-27 (CI smoke-test job — ADR-168; IMPORTANT #8 shipped)

IMPORTANT #8 shipped (ADR-168): a CI `smoke` job now boots the real deployed
entry points — a live `uvicorn` server (`/health`, `/metrics`, real
`POST /api/v1/price`) and the `polaris` console script (`price` on the golden
deal + `benchmark --pack closed-form`) — gating merges alongside lint/test/docker.
Surviving out-of-scope items promoted per the HARVEST step. All 1st-order
(follow-ups of the originally-planned smoke job); all test-/CI-infra convenience,
not production-correctness gaps → NICE-TO-HAVE.

- **Extend the smoke pack to the remaining real entry points (`scenario` / `uq` /
  `ingest`).** The gate boots `/api/v1/price` + `polaris price` + `polaris benchmark`;
  the `scenario` / `uq` / `ingest` CLI subcommands and their `/api/v1/*` routes are
  not yet smoke-covered, so a boot-only regression on one of those entry points
  would still ship green. Additive to `tests/smoke/`. *Source: ADR-168 Out of scope
  (1st-order).* **NICE-TO-HAVE.**
- **Smoke the auth-enabled and multi-worker server modes.** The job boots the
  single-process, auth-disabled default (what CI can afford). A real
  `POST /api/v1/price` behind API-key auth, and a `--workers > 1` / gunicorn boot,
  exercise deployment configurations the current gate does not. *Source: ADR-168
  Out of scope (1st-order).* **NICE-TO-HAVE.**

> The remaining ADR-168 out-of-scope note — folding a head-vs-main **performance**
> verdict into CI — is *not* a new item: it is the existing IMPORTANT #9/#10
> (noise-normalized perf harness + per-merge log), deliberately kept out of this
> pass/fail smoke gate per the group's "deterministic may gate; wall-time only
> informs" rule. No duplicate created.

### Harvested 2026-07-28 (perf harness Slice 1 — ADR-169; IMPORTANT #9 IN PROGRESS)

IMPORTANT #9 was constituted as a MEDIUM epic and decomposed this session
(`docs/PLAN_perf_harness.md` + `docs/CONTINUATION_perf_harness.md`, IN PROGRESS);
**Slice 1** (the deterministic perf-probe core) shipped as ADR-169. The bulk of
ADR-169's "Out of scope" is the epic's **own tracked later slices** — the
head-vs-main same-job driver (Slice 2), the CI perf job that gates on structural
deltas and alerts on the wall-time ratio (Slice 3, which closes #9), and the
per-merge `perf/history.jsonl` creep log (Slice 4 = the existing IMPORTANT #10).
These live in the CONTINUATION (visible to the next routine run via step 5/5b),
so they are **not** re-promoted here as loose items. The genuinely-new loose
out-of-scope follow-up is promoted below; it is 1st-order (a follow-up of the
originally-planned perf epic) but touches only harness depth, not production
correctness → NICE-TO-HAVE.

- **Finer engine sub-path probes (rate-array build, treaty apply) in the perf
  harness.** Slice 1 times the full `project()` hot path only. `run_perf_probe`
  already accepts a caller-supplied `hot_paths` map, so adding named sub-path
  probes (e.g. `_build_rate_arrays`, `BaseTreaty.apply`) needs no contract change
  — it would localise a regression to the sub-step that slowed, not just the whole
  projection. *Source: ADR-169 Out of scope (1st-order).* **NICE-TO-HAVE.**

> The other ADR-169 out-of-scope note — **benchmark product engines beyond
> TermLife** in the default probe — is *not* a new item: it is the existing
> ADR-161 NICE-TO-HAVE "Benchmark product engines beyond TermLife
> (WholeLife / UL / DI-CI)" (B2 scale-benchmark group). The perf harness already
> accepts a caller-supplied engine, so it is not blocked. No duplicate created.

### Harvested 2026-07-28 — MCP Server epic, Slice 2 (ADR-171)

The scenario/UQ tools + HTTP transport (Slice 3) and the eval set + hardening
(Slice 4) are future slices of the **active** MCP epic, tracked in
`CONTINUATION_mcp_server.md` (visible to the next routine run via step 5/5b), so
they are **not** re-promoted here as loose items. *(Update 2026-07-29: Slice 3
shipped the scenario/UQ tools — ADR-172 — and split the streamable-HTTP transport
out to a new epic-internal **Slice 3b**, still tracked in the CONTINUATION, not a
loose item.)* The genuinely-new loose out-of-scope follow-ups are promoted below.
All are 1st-order (follow-ups of the originally-planned MCP epic) and extend the
agent-access surface or polish it, not production correctness → NICE-TO-HAVE.

- **MCP tools for the remaining `run_*` endpoints (ifrs17 / ingest / rate-schedule
  / portfolio).** Slices 1–4 cover the price/scenario/uq core. Each remaining
  endpoint is another `run_*` service extraction + a thin tool once the pattern is
  proven. *Source: ADR-171 Out of scope + PLAN_mcp_server Out of Scope (1st-order).*
  **NICE-TO-HAVE.**
- **MCP prompt templates and MCPB / desktop-extension packaging.** MCP prompt
  templates for common deal-pricing flows, plus a packaged desktop extension and a
  published-registry entry, so the server installs without a manual `claude mcp
  add`. *Source: ADR-171 Out of scope + PLAN_mcp_server Out of Scope (1st-order).*
  **NICE-TO-HAVE.**
- **Genuinely-distinct compact text content block for MCP tool results.** FastMCP's
  high-level decorator emits one serialised value as both structured content and
  JSON text; the compact-output intent is currently carried by the
  `PriceBlockResult.summary` field + `detail` array-gating. A dedicated short text
  block (dropping to the lower-level `CallToolResult`) would shrink the text
  content further for context-tight hosts. *Source: DEV_SESSION_LOG_2026-07-28
  mcp_server_slice2 Open Questions (1st-order).* **NICE-TO-HAVE.**
- **Confirm `.mcp.json` relative-path resolution on a real host.** The committed
  config uses `--directory .` / `./data`; whether these resolve from an arbitrary
  Claude Code launch CWD is untested end-to-end (QUICKSTART documents the
  absolute-path `claude mcp add` fallback). Verify during Slice 4 hardening.
  *Source: DEV_SESSION_LOG_2026-07-28 mcp_server_slice2 Open Questions (1st-order).*
  **NICE-TO-HAVE.**
- **Per-product / named-block headline for a mixed sample block.**
  `polaris_price_block` prices only the policies matching `product_type`
  (transparent via `n_policies`); a future named-block registry (a locked v1
  deferral) or a per-product aggregated headline could price all cohorts of a mixed
  block in one call. *Source: DEV_SESSION_LOG_2026-07-28 mcp_server_slice2 Open
  Questions (1st-order).* **NICE-TO-HAVE.**
- **Service-layer DTO base-class convention (§5 vs the merged `BaseModel`
  precedent).** CLAUDE.md §5 says every model inherits `PolarisBaseModel`, but the
  transport/boundary DTOs deliberately deviated: `PolicyInput` / `PriceRequest` /
  `PriceResponse` (`services/pricing.py`, Slice 1) and the MCP `PriceBlockResult`
  (Slice 2) all use plain `BaseModel`. The PR #174 review raised this as a [P2] and
  correctly recommended *no per-model flip* — a wrapper on `PolarisBaseModel` around
  a family of plain-`BaseModel` DTOs is *more* internally inconsistent, not less.
  Decide it family-wide in one ADR, not ad hoc. Evidence gathered this session:
  switching is a **wash for the payload** — a parent model's `ConfigDict` does *not*
  propagate to nested model instances, so `model_dump()` and the nested
  `PriceResponse` serialise byte-identically either way (parity tests unaffected).
  The *only* observable delta is that `extra="forbid"` adds
  `"additionalProperties": false` to the **client-facing output/OpenAPI schema** of
  each DTO — a boundary-contract tightening that a strict MCP/HTTP client validates
  against, which is exactly why it should be a deliberate, family-wide decision with
  the schema impact re-checked, not an incidental change inside a feature slice.
  *Source: PR #174 review [P2] + follow-up analysis (1st-order — convention/design,
  not correctness).* **NICE-TO-HAVE.**

### Harvested 2026-07-29 — MCP Server epic, Slice 3 (ADR-172)

Slice 3 extracted `run_scenario` / `run_uq` into `services/pricing.py` and added
the `polaris_run_scenario` / `polaris_run_uq` MCP tools (byte-identical goldens).
Per ADR-172's "Out of scope", the streamable-HTTP transport was split out to an
epic-internal **Slice 3b**, and the Slice-4 eval set + hardening remain epic
slices — **both tracked in `CONTINUATION_mcp_server.md`, not re-promoted here as
loose items** (same convention as the Slice-2 harvest above). No genuinely-new
loose out-of-scope follow-up surfaced this slice: the scenario/UQ tools reused the
proven Slice-1/Slice-2 pattern, and the one design item they touch (the
service-layer DTO base-class convention) is already promoted above from the PR #174
review — the new `Scenario*` / `UQ*` contracts and the `ScenarioBlockResult` /
`UQBlockResult` wrappers are the same plain-`BaseModel` family that item already
covers, so that family-wide decision now spans price + scenario + uq DTOs.

### Harvested 2026-07-30 — MCP Server epic, Slice 3b (ADR-173)

Slice 3b added the optional streamable-HTTP (stateless JSON) transport of the same
in-process MCP server, reusing `APIKeyAuthMiddleware` (byte-identical goldens). The
Slice-4 eval set + hardening + docs remains an epic slice tracked in
`CONTINUATION_mcp_server.md` (the only slice left; it CLOSES the epic) — **not
re-promoted here as a loose item.** The genuinely-new loose follow-ups below are
1st-order refinements of the (originally-planned) HTTP transport surface; all affect
only the remote/shared-deployment path, never the default local-stdio quoting path,
so all are NICE-TO-HAVE:

- **HTTP transport requires the `[api]` extra (auth-stack coupling).** `build_http_app()`
  reuses `api.auth.APIKeyAuthMiddleware`, whose import pulls in FastAPI via
  `api/__init__` → `api.main`. A `[mcp]`-only install can serve stdio but not HTTP.
  Extracting `APIKeyAuthMiddleware` (and its `observability` correlation dep) into a
  web-framework-light module — or making `api/__init__` lazy — would let HTTP mode run
  under `[mcp]` alone. Documented as a QUICKSTART §10 prerequisite for now.
  *Source: ADR-173 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Per-scope / per-tool MCP auth.** HTTP auth today is all-or-nothing (a valid
  `POLARIS_API_KEYS` key grants every read-only tool). Since the engine is read-only
  there is no privilege to separate yet, but a future write/store surface (ADR-171
  "store-authoring tools", explicitly out of scope) would want scoped keys.
  *Source: ADR-173 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Non-stateless (session) HTTP transport mode.** v1 HTTP is stateless JSON (no
  session affinity — the shape API-key auth expects). A stateful/SSE session mode
  (resumable streams via an `event_store`) is a possible later transport option for
  hosts that prefer it. *Source: ADR-173 Out of scope (1st-order).* **NICE-TO-HAVE.**

### Harvested 2026-07-31 — MCP Server epic, Slice 4 (ADR-174; CONTINUATION CLOSED — epic complete)

Slice 4 shipped the committed 10-question eval set (`polaris_re.mcp.evals`), the
actionable out-of-range-parameter errors, the ARCHITECTURE MCP section, and the
finalized README/QUICKSTART — and **closes the MCP-server epic**
(`CONTINUATION_mcp_server.md` → COMPLETE; byte-identical goldens). Per the
close-out rule, every surviving refinement item is promoted so the next routine
run sees it. The CONTINUATION carried **no Refinement Backlog** and its Open
Questions were resolved (the Slice-3-vs-3b ordering question was settled when 3b
merged as PR #176). The other ADR-174 out-of-scope items — folding the HTTP auth
stack into the `[mcp]` extra, the post-epic tool surface (ifrs17 / ingest /
rate-schedule / portfolio tools), store-authoring/write tools, MCP prompt
templates, and MCPB packaging — are **already promoted** in the Slice-2 / Slice-3b
harvests above and are **not** duplicated here. The genuinely-new loose follow-up:

- **MCP eval CLI + CI gate + rendered eval report.** `EVAL_SET` is importable and
  green in CI via `tests/test_mcp/test_evals.py`, but there is no first-class
  headless runner. A `polaris mcp-eval` command (or a CI job) that runs the set,
  emits a Markdown pass/fail report, and exits non-zero on any failure — mirroring
  the `polaris benchmark` validation-pack pattern (ADR-132) — would let the eval
  set gate CI and produce a diligence-grade artifact, not only a pytest run.
  *Source: ADR-174 Out of scope (1st-order — a follow-up of the planned eval-set
  feature).* **NICE-TO-HAVE.**

**Carried, still open (already promoted — status note only, no re-promotion):**
the Slice-2 item *"Confirm `.mcp.json` relative-path resolution on a real host"*
(above) asked for end-to-end verification during Slice-4 hardening. This session
could not spawn a real Claude Code host in the CI sandbox, so relative-path
resolution remains **unverified end-to-end**; the absolute-path `claude mcp add`
fallback is documented in QUICKSTART §10 and is the robust path. The item stays
open for a human with a real host.

### Harvested 2026-07-31 (perf harness Slice 2 — ADR-175; IMPORTANT #9 IN PROGRESS)

**Slice 2** of the perf epic shipped as ADR-175: the head-vs-main diff layer
(`diff_reports` → `PerfDiff`/`ProbeDiff`) + `scripts/perfbench.py`, the
git-worktree runner that produces the `perf.json` comparison and exits non-zero
on a hard delta. As with Slice 1, the bulk of ADR-175's "Out of scope" is the
epic's **own tracked later work** — the CI perf job (Slice 3, closes #9) and the
per-merge `perf/history.jsonl` creep log (IMPORTANT #10) — which live in the
CONTINUATION and PD #9/#10, so they are **not** re-promoted as loose items. The
one genuinely-new loose follow-up is promoted below; it is 1st-order (a follow-up
of the originally-planned perf epic), design polish only → NICE-TO-HAVE.

- **Optional `polaris perfbench` CLI subcommand.** Slice 2 shipped the runner as
  `scripts/perfbench.py` (script-first, mirroring B2's `scripts/scale_benchmark.py`
  precedent). Surfacing it as a `polaris perfbench` Typer subcommand is a
  convenience only — the CI job (Slice 3) and local use both call the script
  directly. Defer to the maintainer's script-first precedent unless a CLI surface
  is requested. *Source: ADR-175 Out of scope + CONTINUATION_perf_harness Open
  Questions (1st-order).* **NICE-TO-HAVE.**

> Two Slice-2 policy choices — the wall-time alert **band** (1.5×) and the
> **`peak_mib` alert delta** (4 MiB) `diff_reports` defaults — were surfaced for
> the maintainer and **CONFIRMED on PR #178 (2026-07-31)**. Slice 3 wires them
> into CI as-is (both alert only, never hard gates). Recorded in
> `CONTINUATION_perf_harness` Open Questions; not a promoted work item.

### Harvested 2026-08-01 (perf harness Slice 3 — ADR-176; IMPORTANT #9 CLOSED — epic complete)

**Slice 3** of the perf epic shipped as ADR-176, **closing IMPORTANT #9**: the CI
`perf` job in `.github/workflows/ci.yml` runs `scripts/perfbench.py --ref
origin/main --no-fetch` on one PR-only runner, gates the merge on a structural
hard delta (never on the advisory wall-time / peak-MiB alerts), and uploads
`perf.json`. IMPORTANT #9 is struck through above; `CONTINUATION_perf_harness` is
COMPLETE (mandatory scope, Slices 1–3).

Every item in ADR-176's "Out of scope" is **already tracked** — no new loose
items are promoted (avoiding the duplication the routine's "already addressed"
check guards against):
- **Per-merge `perf/history.jsonl` creep log** = the standing **IMPORTANT #10**
  (annotated **UNBLOCKED** above — now the top candidate for a follow-on epic;
  the perf epic's optional Slice 4).
- **Fold a head-vs-main perf verdict into the pr-review comment** = the existing
  NICE-TO-HAVE "pr-review routine posts the perf judgment comment" (depends on #9,
  now satisfied). No duplicate created.
- **Optional `polaris perfbench` CLI subcommand** = the NICE-TO-HAVE already
  promoted in the Slice-2 harvest above. No duplicate created.

> With IMPORTANT #9 closed and `CONTINUATION_perf_harness` COMPLETE, no Tier-A
> epic and no in-progress CONTINUATION remain active. The next routine run
> selects a new Epic per step 5b (re-rank against the latest
> COMMERCIAL_VIABILITY_REVIEW; regenerate it if older than ~30 days —
> `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is >30 days old as of 2026-08-01, so a
> regen is due before the next Epic is chosen). IMPORTANT #10 (perf history log)
> is the natural continuation of this epic's thread.

### Harvested 2026-08-02 (perf history log — ADR-177; IMPORTANT #10 SHIPPED)

**IMPORTANT #10** shipped as ADR-177 (struck through above): `analytics/perf_history.py`
+ `scripts/perf_history.py` + the committed `perf/history.jsonl` record one
deterministic-first row per commit and run earliest-vs-recent-window median creep
detection, gating only on the machine-portable MiB-peak. Additive-only, goldens
byte-identical.

> **Correction (routine-hygiene).** The 2026-08-01 note above (and that session
> log) states `COMMERCIAL_VIABILITY_REVIEW_2026-07-15` is ">30 days old as of
> 2026-08-01". That is an arithmetic error — 2026-07-15 → 2026-08-02 is **18
> days**, inside the ~30-day trigger. **No viability-review regeneration is due.**
> This session therefore did not regenerate the review; the 18-day-old review
> remains authoritative and already prescribes the post-A4′ maintenance-mode
> fallback (§7), under which #10 was selected. The routine stays in **maintenance
> mode** (no Phase-7 frontier chosen; AXIS/Prophet reconciliation
> reference-blocked) — no startable Tier-A epic remains.

New follow-up from ADR-177's "Out of scope" (1st-order — a follow-up of the
originally-planned #10 capability; promoted normally):

- **Automatic per-merge CI append of `perf/history.jsonl` + commit-back-to-`main`.**
  ADR-177 ships the record + creep-detection *capability* and its runner, but
  nothing yet *runs* it on each merge and commits the appended row back to `main`
  (the perf CI job is PR-only and cannot write to `main`). A CI job on push-to-`main`
  that runs `scripts/perf_history.py`, commits the new row, and fails on structural
  creep would make the log self-maintaining. **Blocked on maintainer authorization:**
  it needs `contents: write` and a bot commit to `main` — an infra/permissions
  decision the autonomous routine will not take unprompted. *Source: ADR-177 Out of
  scope (1st-order).* **IMPORTANT.**
  > **Status update (maintainer decision 2026-08-02, daily-dev routine revision).**
  > The maintainer chose the **unprivileged** answer instead: the routine now
  > appends exactly one row per routine PR (new step 14b), so the row reaches
  > `main` through the normal review/merge path — no `contents: write`, no bot
  > commit to `main`, no branch-protection bypass. This item therefore stays
  > **open but narrowed**: what remains uncovered is a **human hotfix merged
  > outside the routine**, which gets no row. Two operational notes recorded with
  > the decision: every routine PR now touches the same append-only file, so two
  > concurrently-open PRs will conflict on it (fine at the serial 1-run/day
  > cadence); and the append is initial-open-only, so a PR reworked across
  > sessions does not get a duplicate row.

Two ADR-177 out-of-scope items are **already tracked** — no duplicates created:
- **One-off backfill of ~10–15 historical merges** = the existing NICE-TO-HAVE
  "Seed `perf/history.jsonl` by backfilling meaningful commits" (#63), now
  **unblocked** (its target format + mechanism exist; creep detection is a no-op
  until the log holds `2*window` rows).
- **Fold the creep verdict into the pr-review comment** = the existing NICE-TO-HAVE
  "pr-review routine posts the perf judgment comment" (#62), now extendable to the
  long-baseline verdict as well.

> With IMPORTANT #10 shipped, the perf CI-perf/smoke group (#8/#9/#10) is complete
> bar the deferred auto-append CI job (above) and its two tracked NICE-TO-HAVE
> tails (#62/#63). No Tier-A epic and no in-progress CONTINUATION remain; the
> routine is in **maintenance mode** pending a maintainer Phase-7 frontier
> decision. Next fallback picks (value-per-day): the deferred auto-append job (if
> authorized), then Tier-C (C4 parallel portfolio / C6 load test) per the
> re-ranked catalogue.

### Harvested 2026-08-02 (portfolio deal-lifecycle API — ADR-178; C4 Slice 1)

Tier-C item **C4** was constituted this session as a 3-slice MEDIUM epic
(`docs/PLAN_portfolio_execution.md` + `docs/CONTINUATION_portfolio_execution.md`,
IN PROGRESS) and **Slice 1** shipped as ADR-178 — the `Portfolio` deal-lifecycle
API. The other two thirds of C4 — **per-deal result caching** (Slice 2) and
**parallel execution** (Slice 3) — are the epic's own tracked slices, visible to
the next routine run via step 5/5b, so they are **not** re-promoted here as loose
items (same convention as the perf/MCP epic harvests above). C4 is a catalogue
(planned) Tier-C item, so ADR-178's out-of-scope items are **1st-order** and
promoted normally; none is a production-correctness gap on the common quoting
path, so all three are NICE-TO-HAVE.

- **Per-deal marginal-contribution / risk-attribution analytic.** `without_deal`
  makes the leave-one-out loop a two-liner (a shipped test asserts the exact
  identity: full-book PV minus ex-deal PV equals that deal's PV contribution
  under strict alignment), but a real attribution surface — per-deal **marginal
  PV, marginal required capital, and marginal concentration/HHI**, reported as a
  first-class result object — is its own feature with its own ADR. Marginal
  *capital* in particular is the interesting one and is genuinely non-additive
  (the capital call is made once on the aggregate, so a deal's marginal capital
  is not its standalone capital). **The highest-value of the three items here.**
  *Source: ADR-178 Out of scope (1st-order).* **NICE-TO-HAVE.**
- **Surface the lifecycle API on the CLI / REST / dashboard.** All three portfolio
  surfaces (`polaris portfolio run`, `POST /api/v1/portfolio`, the Streamlit
  portfolio page) construct a fresh `Portfolio` per request, so incremental
  what-if *across a session* needs a state design first — a stateful portfolio
  session on the dashboard, or a diff-style REST payload. Deliberately not
  attempted inside the epic. *Source: ADR-178 Out of scope (1st-order).*
  **NICE-TO-HAVE.**
- **`Deal`-level partial edits.** `replace_deal` replaces the whole deal, so
  re-quoting a single term (a new `cession_pct`, say) means restating the other
  five arguments. A `Portfolio.amend_deal(deal_id, *, treaty=...)` keeping every
  unspecified field would make the commonest what-if a one-liner. *Source:
  ADR-178 Out of scope (1st-order).* **NICE-TO-HAVE.**

> The two Slice-2 / Slice-3 design questions raised this session (the cache
> opt-in shape — constructor-level vs per-call; and what measured speed-up would
> justify keeping a `max_workers` knob) live in
> `CONTINUATION_portfolio_execution.md` "Open Questions (for human)" while the
> epic is IN PROGRESS, per the harvest convention — they are decisions, not work
> items, and will be promoted only if they survive the epic's close-out.

### Harvested 2026-08-02 (portfolio per-deal result cache — ADR-179; C4 Slice 2)

**Slice 2** of the C4 epic shipped as ADR-179 — the opt-in per-deal result cache
`Portfolio(cache=True)`. Slice 3 (parallel execution) remains the epic's own
tracked slice and is **not** re-promoted here, per the same convention. One of
the two Slice-2/3 design questions above is now closed: the **cache opt-in shape**
is resolved as constructor-level (`Portfolio(..., cache=True)`) in ADR-179
decision point 1, struck through in the CONTINUATION's Open Questions; the Slice-3
measurement-threshold question stands. ADR-179's out-of-scope items are
**1st-order** (C4 is a planned catalogue item and Slice 2 was planned scope) and
promoted normally; neither is a production-correctness gap on the common quoting
path, so both are NICE-TO-HAVE.

- **Bound the cache (LRU / max entries).** The cache is an unbounded dict keyed
  `(deal_id, hurdle_rate)`. That is right for a book held for the duration of one
  pricing exercise — the intended use — but a long-lived service sweeping many
  hurdle rates over a large book would grow it without limit, since nothing
  evicts on size and every entry holds a `DealResult` + `CashFlowResult` with
  their per-month arrays. An LRU bound (or a `max_entries` constructor arg) would
  cap it. Not needed while the CLI / REST / dashboard build a fresh `Portfolio`
  per request and never enable the cache at all. *Source: ADR-179 Out of scope
  (1st-order).* **NICE-TO-HAVE.**
- **Detect in-place mutation of a deal's projection inputs.** The cache can only
  see changes made through the portfolio's own four mutation verbs; a caller who
  mutates an `InforceBlock` / `AssumptionSet` / `ProjectionConfig` / treaty in
  place gets a stale result, and `clear_cache()` is the manual answer. A content
  hash or a monotonic version stamp on `InforceBlock` / `AssumptionSet` would make
  it automatic — and would also be the prerequisite for ever turning the cache on
  by default. ADR-179 deliberately kept the id-plus-explicit-invalidation contract
  because it is honest about what it can and cannot detect. *Source: ADR-179 Out
  of scope (1st-order).* **NICE-TO-HAVE.**
- **Mark cached arrays read-only (`arr.flags.writeable = False`).** The symmetric
  hazard to the item above, from the *output* side: cached results are handed out
  live, so a caller who writes into an array returned by a previous `run()`
  corrupts every later run of that portfolio. Measured on PR #182: the aggregate
  PV moved **27,089.56 → 37,248.14** silently. Latent, not live — nothing in-tree
  does it (the dashboard reads scalars only), `clear_cache()` recovers, and the
  direct `result.deal_results[0].net_cash_flow *= 2` form is already blocked by
  `DealResult` being a frozen dataclass (it takes a local binding first). Setting
  the writeable flag on cached entries costs **no copy** and converts silent
  corruption into a loud `ValueError` at the point of the mistake; verified that
  `run` / `run_with_capital` / `run_scenarios` all still pass with every cached
  array read-only, PV identical. The cost, and why it is a decision rather than a
  flag flip: cached and uncached results would then differ in **writeability** —
  not in value, but an observable divergence from the "bit-identical either way"
  property ADR-179 leans on. Handing out copies instead was already rejected on
  cost grounds (ADR-179 alternative (f)). Wants an explicit ADR line either way.
  *Source: PR #182 review round, follow-up notes thread 1 (1st-order).*
  **NICE-TO-HAVE.**

> Deliberately **not** promoted as a new item: *surfacing `cache=True` on the CLI
> / REST / dashboard*. Each of those surfaces builds a fresh `Portfolio` per
> request, so a cache would never be hit — this is the same session-state design
> question already carried above as "Surface the lifecycle API on the CLI / REST /
> dashboard", not a second item. Also not promoted: the **cache's lack of
> locking**, which is a constraint on Slice 3 (two threads can both miss on one
> key and duplicate a projection — wasteful, not incorrect) and is recorded in
> `CONTINUATION_portfolio_execution.md` under Slice 2's key decisions, where the
> slice that must act on it will read it.

#### DISCOVERY (routine step 11b) — `test_scaling_is_near_linear` is a wall-clock ratio gate with ~37% headroom

Surfaced while re-running the suite for the PR #182 review round, **not** caused
by this PR and **not** fixed in it (step 11b: quantify, file, ship only the
selected scope).

`tests/test_analytics/test_scale_benchmark.py::TestRunScaleBenchmark::test_scaling_is_near_linear`
failed once in a combined `tests/test_analytics/ tests/qa/` run, then passed 6/6
in isolation and in a full 1039-test `tests/test_analytics/` run.

**Trigger identified 2026-08-08 — CPU contention, not randomness.** It fired
**three times** in one session, and every firing was a `tests/test_analytics/` run
launched while another full suite or a perf probe was executing in the same
container; it passed in isolation immediately afterwards each time (0.7-1.0 s).
That reclassifies it from "intermittent" to **deterministic given a loaded host**,
which matters two ways: a reader hitting it should check what else is running
before investigating, and the fix is a real one — assert on the *work* ratio
(cells, allocations) rather than on wall clock — rather than widening the
tolerance until it stops. Still filed, still not fixed here. It is not a
real regression — it is a **wall-clock ratio assertion** (`t_large < 6.0 *
t_small`, projecting a 2,000- vs an 8,000-policy block) whose margin is far
thinner than the comment claims. Measured over six consecutive runs on an idle
machine:

| run | `t_small` | `t_large` | ratio | bound |
|---|---|---|---|---|
| 0 | 0.0302 s | 0.1158 s | 3.83× | 6.00× |
| 1 | 0.0278 s | 0.1134 s | 4.07× | 6.00× |
| 2 | 0.0251 s | 0.1101 s | **4.39×** | 6.00× |
| 3 | 0.0250 s | 0.1093 s | 4.37× | 6.00× |
| 4 | 0.0258 s | 0.1101 s | 4.27× | 6.00× |
| 5 | 0.0265 s | 0.1092 s | 4.12× | 6.00× |

Two things make it fragile. The observed ratio already sits at 3.8–4.4× against
a 6× bound — only **~37% headroom**, not the "generous" margin the docstring
describes. And the denominator `t_small` is **~25–30 ms**, small enough that one
GC pause or scheduler preemption during the small run dominates it: `t_small`
dipping to 0.018 s with `t_large` unchanged is already a failure at 6.1×.

This is the exact shape the group's standing rule warns against — *"deterministic
metrics may gate; raw wall-time only informs"* (maintainer 2026-07-12) — and the
same reasoning that led the 2026-08-02 session to reject Tier-C **C6** (the "100
concurrent requests < 2 s" load test) as a fallback pick. A flaky gate that reds
the pipeline at random trains reviewers to ignore red, which costs more than the
O(N²) regression it is guarding against.

The suggested fix is a shape change, not a looser bound: `ScaleBenchmarkRow`
already carries `peak_rss_mb`, and **MiB is precisely the deterministic-first
metric ADR-177's perf-history design settled on**. Assert linear *memory*
scaling (or an allocation/op count) as the gate and demote the timing ratio to
reported-but-not-asserted. Failing that, the cheap mitigations are to raise the
block sizes so the denominator is ~100 ms rather than ~25 ms, and/or mark the
timing assertion `@pytest.mark.slow` so it informs without gating `make test`.

Classified **IMPORTANT** on operational grounds: it touches **no quoted number
and no actuarial surface** — under a strict commercial-impact reading it would be
NICE-TO-HAVE — but it can spuriously red the merge gate, which blocks delivery
and undermines the CI perf gate (ADR-176) landed only days ago. A maintainer may
reasonably downgrade it. *Source: DISCOVERY during PR #182 review round
(1st-order).* **IMPORTANT.**

### Harvested 2026-08-30 (mgcv-parity slice 5e, ADR-213) — NICE-TO-HAVE, not numbered into the catalogue above

The epic's own PLAN registers the substantive follow-on as slice 5f
(covariate-sharing N>4 multi-start robustness, not blocking) — that is the
primary registration mechanism per `docs/CONTINUATION_mgcv_parity_engine.md`'s
own note that this file is the cross-epic view, and left un-renumbered here to
avoid disturbing the catalogue's existing count. Two smaller items named but
not actioned this session, cross-epic-visible in case a later, unrelated
session touches these files:

- **Stale `python_opt_log10` in `scripts/gam_fixed_sp_score_probe.R` /
  `gam_multiterm_sp_delta_probe.R`.** Both still carry the free-`sp` point
  from an earlier session (ADR-208's pre-Appendix-B reading, per ADR-211's own
  note); refreshing under the now-pinned `OPENBLAS_NUM_THREADS=1` regime is
  bookkeeping for a different (mgcv-comparison) measurement than slice 5e's
  own, so it was named but not done here. *Source: ADR-213, PLAN slice 5e
  (2nd-order).*
- **`fit_polaris_gam` could expose multi-start as an opt-in parameter.**
  `select_lambdas_continuous_multistart` exists and is measured to help on a
  real (if narrow) N=4 case; wiring it through `PolarisGAM`'s own production
  entry point as a caller-chosen option (never a changed default — that is a
  separate, maintainer-gated decision per ADR-186's own precedent) is a small
  follow-up. *Source: ADR-213 Consequences (2nd-order).*

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

### Harvested 2026-08-02 (portfolio parallel execution — ADR-180; C4 Slice 3 — CLOSES C4)

**Slice 3** of the C4 epic shipped as ADR-180 and **closes the epic**
(`CONTINUATION_portfolio_execution.md` → COMPLETE), so this harvest promotes the
epic's surviving refinement items as well as ADR-180's own out-of-scope
paragraph, per the step-17 close-out rule.

The slice's headline outcome is a **negative measurement, honestly published**:
threaded per-deal fan-out peaked at **1.29x** (4 deals x 20k policies, 4 workers)
and was **slower than serial** — 0.59x at 4 workers, 0.48x at 8 — on 8 deals x 5k
policies, on a 4-core runner. The knob ships off by default with those numbers in
its docstring and no speed-up claim anywhere in the docs. Two consequences below
are first-class work items rather than commentary.

- ~~**Vectorise the engines' month-by-month recursions (the real throughput
  bottleneck).**~~ — **PARKED 2026-08-03, downgraded to NICE-TO-HAVE.** Constituted
  as an epic and parked the same day: pre-work measurement
  (`docs/MEASUREMENT_engine_recursion_prework.md`) showed the `lx` loop vectorises
  **bit-identically for zero speed-up** (165.2 → 167.1 ms at N=20,000; it is
  array-work-bound, not interpreter-bound), and the unexamined premise underneath
  — that projection speed is a problem — does not hold: a 320k-policy book prices
  in **5.2 s**. One of four loops was measured, so the falsification is partial;
  revival needs a profile *and* a workload where latency blocks someone (UQ over
  thousands of scenarios). The measurement's incidental finding is the durable
  part and is promoted separately below. Original framing:
  **→ was CONSTITUTED 2026-08-03 as the active Epic** on maintainer
  direction: `docs/PLAN_engine_recursion_vectorisation.md` +
  `docs/CONTINUATION_engine_recursion_vectorisation.md` (IN PROGRESS, 4 slices,
  slice 1 = NEXT). Slice 1 is a **measurement** slice — the claim below is an
  inference from ADR-180's parallel curve, not a profile, and slice 1 is allowed
  to falsify the epic. Slices 2–3 are bit-identical rewrites; slice 4 (the
  reserve recurrences) is **gated** on a maintainer goldens decision because it
  cannot be made bit-identical. Note this fills a genuine gap rather than
  jumping a queue: A4′ shipped, so the `COMMERCIAL_VIABILITY_REVIEW_2026-07-15`
  Tier-A ladder is **exhausted** and step 5b had no unstarted Tier-A item left.
  Original framing: ADR-180's measurement diagnosed *why* the fan-out barely helps:
  a per-deal projection is not one big GIL-releasing ufunc. `products/term_life.py`
  runs several `for month in range(t)` recursions (in-force factor `lx`,
  net-premium reserve, CRVM reserve) — Python loops around comparatively small
  per-step NumPy calls on `(N,)` arrays — so threads overlap the array work but
  contend on everything between the steps. That is directly visible in the
  measurement: 20k-policy deals scale (1.29x) where 5k-policy deals regress
  (0.59x), because larger `N` lengthens each C section relative to the Python
  overhead around it. Shortening or vectorising those loops would raise the
  **serial** number too, which is a strictly larger win than any fan-out, and it
  is a change to `products/`, not `analytics/`. Genuinely reserve-recursive steps
  may resist full vectorisation; the honest first step is a profile attributing
  projection time across the recursions before committing to a rewrite.
  *Source: ADR-180 Out of scope + DISCOVERY protocol finding, routine step 11b
  (1st-order).* **IMPORTANT.**
- ~~**Decide the `max_workers` knob's fate.**~~ — **RESOLVED 2026-08-03: KEEP**
  (ADR-180 amendment 2). The maintainer's Apple Silicon measurement peaked at
  **1.77x** (16 deals x 20k policies, 4 workers), clearing the 1.5x bar though not
  2x, with every row bit-identical — see
  `docs/MEASUREMENT_portfolio_parallel_macbook_air.md`. Kept in a *narrower* form
  than "parallel works": still off by default, now documented with two measured
  rules (match performance cores, not total cores; large per-deal blocks only),
  because the small-deal regression reproduced on independent hardware. Original
  context retained below for the audit trail. ADR-180 deliberately did not decide
  it: the `CONTINUATION`'s open question asked what speed-up justifies the API
  surface (1.5x? 2x?), the measured peak is below both, and on the plan's own
  terms this is the "ship the measurement, not the claim" branch. The knob was
  kept rather than deleted only because a **4-core** measurement is a thin basis
  for removing a feature that may pay on a 32-core workstation, and
  `scripts/bench_portfolio_parallel.py` is the instrument for re-measuring there.
  If the maintainer prefers the stricter reading, removing the parameter is a
  small self-contained revert; the benchmark and the ADR are worth keeping either
  way. *Source: CONTINUATION_portfolio_execution "Open Questions (for human)" —
  the one that survived the epic's close (1st-order).* **IMPORTANT** (an API
  surface decision, not a correctness gap).
- **Re-measure the parallel curve on many-core hardware.** The whole ADR-180
  table is one 4-core box. The oversubscription cliff at 4 and 8 workers is partly
  an artifact of that box, and nothing in the repo records what the curve looks
  like with real headroom. One run of `scripts/bench_portfolio_parallel.py` on a
  16- or 32-core machine, committed alongside the ADR table, would either justify
  the knob or settle its removal on evidence rather than inference. *Source:
  ADR-180 "Recommendation" (2nd-order — a follow-up of the knob-disposition
  item).* **NICE-TO-HAVE.**
- ~~**Surface `max_workers` on the CLI / REST / dashboard.**~~ — **PARTIALLY
  SHIPPED** (PR #183 / ADR-180 amendment): the **CLI half is done** —
  `polaris portfolio run --max-workers N` and `polaris portfolio scenarios
  --max-workers N`, serial by default, with `--help` text that leads with the
  measured *slower-than-serial* caveat (a test pins that wording). Shipped on
  maintainer direction the same session, ahead of the disposition decision rather
  than behind it. **REST and the Streamlit page remain out of scope and open**:
  a concurrency knob on a shared service multiplies per-request pools against the
  server's own concurrency, which is a capacity-planning decision, not an API one
  — unlike a CLI invocation, where one user owns the machine. Revisit only after
  the many-core measurement settles whether the knob survives at all. *Source:
  ADR-180 Out of scope + ADR-180 amendment (1st-order).* **NICE-TO-HAVE.**
- ~~**Run the many-core measurement and settle ADR-180's disposition question.**~~
  — **SHIPPED 2026-08-03**: run on an Apple Silicon MacBook Air, all three shapes,
  committed as `docs/MEASUREMENT_portfolio_parallel_macbook_air.md` and folded into
  ADR-180 as amendment 2. Verdict KEEP; the `run` docstring and CLI `--help` were
  rewritten around the real curve. Machine spec since captured — **10 cores, 4
  performance + 6 efficiency** — which confirms the peak sits exactly at the
  P-core count while 6 cores sit idle. No residual (RAM was not recorded; nothing
  in the runs suggests it mattered). Original framing retained for the audit trail:
  Now the gating item for the two above: `docs/RUNBOOK_portfolio_parallel_measurement.md`
  is the procedure (three book shapes, a results template, and the caveat that a
  CLI-level speed-up will be smaller than the benchmark's because the command also
  pays parsing / ingest / table-load / rendering — unmeasured). Output lands as
  `docs/MEASUREMENT_portfolio_parallel_<hardware>.md` and either closes the
  question as *keep* — with the ADR's 4-core table gaining a many-core sibling and
  the docstring / `--help` rewritten around the real curve — or as *remove*, on
  evidence. Maintainer has indicated a lean toward adoption; the measurement is
  what makes that a decision rather than a preference. *Source: ADR-180
  amendment + maintainer direction 2026-08-02 (1st-order).* **IMPORTANT.**
- **Incremental portfolio what-if over a session.** The C4 epic built the whole
  machinery — `without_deal` (ADR-178), the per-deal cache (ADR-179), the fan-out
  (ADR-180) — and none of it is reachable from any user-facing surface, because
  all three construct a fresh `Portfolio` per request. Making "drop DEAL_C and
  re-price" a one-click dashboard action needs a session/state design first (where
  the portfolio lives between requests, how it is invalidated, what happens on
  concurrent edits). This is the item that would convert the epic's ergonomics
  work into user-visible value. *Source: CONTINUATION_portfolio_execution
  "Context for Next Session" + PLAN §4 (1st-order).* **IMPORTANT.**
- **Portfolio-level marginal contribution analytic.** Considered and rejected in
  Slice 1 as out-of-character for an ergonomics epic: `without_deal` makes the
  leave-one-out loop a two-liner (and ADR-179's cache carry-over drops it from
  `N x (N-1)` projections to `N`), but a real attribution surface — marginal PV,
  marginal capital, marginal concentration, presented per deal — is its own
  feature with its own ADR. The cheap half of it now exists. *Source:
  CONTINUATION_portfolio_execution "Context for Next Session" — considered and
  rejected for Slice 1 (1st-order).* **NICE-TO-HAVE.**
- **Make the CLI-output test assertions colour-proof.** Three pre-existing tests
  assert on rendered Rich output without stripping ANSI escape codes
  (`TestPortfolioRunConcentrationBasisFlag::test_nar_peak_basis_renders_nar_section_only`,
  `::test_all_basis_renders_three_sections`,
  `TestPortfolioReportConcentrationBasisFlag::test_report_supports_all_basis` —
  all matching `'weighted by Peak Ceded NAR'`). They are **green on CI today**
  only because the module-level Rich `Console` disables colour off a TTY; reproduce
  the latent failure with
  `FORCE_COLOR=1 uv run pytest tests/test_analytics/test_cli_portfolio.py`. PR #183
  hit the same hazard on the *help*-rendering path — where Typer's formatter
  colours regardless of TTY — and added a `_plain()` helper in that file that these
  three could reuse. Low severity (a latent CI fragility, not a production defect),
  but it is a trap that has now cost one red CI round. *Source: PR #183 CI round 1,
  DISCOVERY protocol step 11b (1st-order).* **NICE-TO-HAVE.**
- **Numerical-rewrite PRs must assert array-level equality, not just goldens.**
  Discovered while measuring the recursion rewrites: patching a genuinely
  perturbing change into the engine (naive `lx` cumprod, verified to execute and
  to move the array by 1.9e-15) left **all five committed golden digests
  bit-identical**. The golden block is **6 policies per cohort** — too small to
  detect a last-ulp engine perturbation, and the digest is full-precision, so this
  is not a rounding artefact. "Goldens byte-identical" is therefore a *necessary
  but insufficient* acceptance criterion for any numerical change, and a future
  rewrite of this class would pass CI while altering the engine. Fix is cheap: add
  an array-level `assert_array_equal` on a ≥5,000-policy block to the QA suite, or
  enlarge a golden cohort. *Source: MEASUREMENT_engine_recursion_prework §4,
  DISCOVERY protocol step 11b (1st-order).* **IMPORTANT.**
- **Real-data diligence run for the experience GAM (HMD + SOA-ILEC).** The A4′
  epic shipped 15 slices, and every GAM fit in it is against **synthetic data with
  an injected known surface** — which proves the implementation recovers a surface
  it was handed, not that it recovers real mortality improvement from real
  experience. The loaders already exist (`experience_loaders.py`: HMD + ILEC
  parsers, canonical cell contract, injectable fetch, unit-tested on synthetic
  fixtures); what has never been done is run them. Given CLAUDE.md §1 names "no
  native ML integration" as the incumbents' defining weakness, a GAM validated
  only on synthetic data does not discharge the product thesis. Data acquisition
  is `docs/RUNBOOK_experience_data_acquisition.md` (maintainer-run: HMD needs an
  account, ILEC needs SOA terms acceptance, and neither may be committed).
  Previously filed as NICE-TO-HAVE (ADR-150) — **reclassified IMPORTANT on
  2026-08-03 maintainer direction**, and the strongest candidate for the next
  epic. *Source: ADR-150 + maintainer direction 2026-08-03 (1st-order).*
  **IMPORTANT.**

### Harvested 2026-08-04 (experience-GAM diligence harness — ADR-182; real-data epic Slice 1)

- **`uw_class` dtype is inconsistent across the composed and uncomposed loader
  paths.** `load_ilec` returns `uw_class` as `Int64` on the uncomposed path (the
  reader infers it from an all-numeric class column) but always `Utf8` on the
  composed one (`"1of2"`). Cosmetic today — nothing keys on it across vintages —
  but a join-key hazard the moment something does, and the kind of defect that
  surfaces as a silent empty join rather than an error. Fix is a cast at the
  loader boundary. **Promoted here rather than re-listed again:** it was filed in
  ADR-181's *Out of scope* and then carried as an open follow-up in two
  consecutive session logs without ever entering the catalogue, which is how an
  item accumulates instead of getting decided. It is 2nd-order (a follow-up of
  ADR-181, itself a slice of the real-data epic), so the order cap makes it
  NICE-TO-HAVE. *Source: ADR-181 out-of-scope → PR #185 review [P2], DISCOVERY
  protocol step 11b (2nd-order).* **NICE-TO-HAVE.**
- **Report artefacts need a rounding step, not just a missing clock, to be
  diffable.** Removing the wall clock from a generated artefact is necessary for
  byte-stability but not sufficient: the diligence report's delta-method band runs
  through `cov_params` and an `einsum`, both on multithreaded BLAS, which
  reassociates its sums depending on how threads carve up the work. Two runs of
  the same script over the same cache differed by up to **1.2e-14 relative** in
  the band endpoints — invisible actuarially, and enough to make every re-run of a
  committed finding show a spurious diff. Pinning `OMP_NUM_THREADS=1` removes it,
  confirming the cause. `experience_diligence` now rounds emitted floats to 12
  significant digits (`REPORT_SIGNIFICANT_DIGITS`) and verifies byte-equality
  across *separate processes*, not two renderings of one in-process object. **Any
  future generated artefact intended to be committed and diffed inherits this
  problem** — the perf history log and the QA golden digests are the two existing
  candidates worth auditing against it. *Source: PR #185 review (determinism
  over-claim) → measurement, DISCOVERY protocol step 11b (1st-order).*
  **NICE-TO-HAVE.**

### Harvested 2026-08-05 (real-data GAM epic slices 2-3 — ADR-182 amendments 2-5)

Four items the slice 2 and 3 measurement documents named and that were not
promoted when the epic closed. Each is a 1st-order follow-up of planned slice
scope, so the order cap does not bar them. With the epic marked COMPLETE and its
CONTINUATION stating that follow-ups live here, the omission was load-bearing
rather than cosmetic (PR #185 round-2 review [P1]).

- ~~**Re-run ILEC with `--duration-bands` to populate `standardised_ae`.**~~
  **DONE 2026-08-06** — measured, and it partially falsified the inference:
  direction confirmed, magnitude cut ~5x (ADR-182 amendment 6). Original text: The
  estimator shipped in ADR-182 amendment 5; both committed ILEC reports predate
  it, so `MEASUREMENT_experience_gam_ilec.md` §4 — the "a flat A/E is not evidence
  assumptions are sound" reading, which the CONTINUATION elevates to slice 3's
  headline — is still an **inference from the pooled-versus-banded contrast**, not
  a measurement. One maintainer run converts it. Until then the estimator is
  verified only against synthetic strata, which is precisely the kind of evidence
  this epic exists to say is not a finding about real experience. *Source: ADR-182
  amendment 5 + PR #185 round-2 review (1st-order).* **IMPORTANT.**
- **Age 45 is not usable on the ILEC fit — but its stated rationale is RETRACTED
  (2026-08-08).** ~~Fitted MI ramps 0.05% (2013) to 3.59% (2019) at `year_df=3`,
  which is the cubic floor — so this cannot be tuned away.
  `MEASUREMENT_experience_gam_ilec.md` §7: "needs a longer vintage, not a different
  setting." Resolution is a longer ILEC release, i.e. maintainer-gated.~~ **Both
  claims are false and this entry sourced them.** `year_df=3` was never a floor on
  flexibility — it was a floor on `df` with `degree` hardcoded at 3, and
  `df=1, degree=1` is legal and strictly less flexible (ADR-184, which is why
  `_MIN_SPLINE_DF` was removed). And a different setting does *not* remove the
  climb: refitting at `--year-df 2 --year-degree 2` leaves it at 3.54 → 3.58 points
  and moves the early-vs-late contrast by 0.01 (ADR-184 amendment 2). **The entry
  stays open** — age 45 is still not usable and still blocks any age-45 claim — but
  for reasons now listed separately below, none of which is spline flexibility.
  *Source: MEASUREMENT_experience_gam_ilec §3/§7 (1st-order).* **NICE-TO-HAVE.**
- **The ILEC A/E *level* of 1.079 is not interpreted.** Actual deaths run ~8% above
  VBT 2015 expected on this book. Only the *drift* is claimed anywhere; decomposing
  the level into basis, mix and selection effects was never in slice 3's scope and
  is a genuine open question for anyone pricing off this basis. *Source:
  MEASUREMENT_experience_gam_ilec §7 (1st-order).* **NICE-TO-HAVE.**
- **No quantitative comparison against MIM-2021's own scale.** HMD §3 claims
  *qualitative* structural agreement with the published record and explicitly
  scopes out matching rates, which would need MIM-2021 loaded as a comparison
  basis. That comparison is what would turn "the shape agrees" into "the rates
  agree to X", and it is the natural companion to the `mgcv` oracle (ADR-151).
  *Source: MEASUREMENT_experience_gam_hmd §3/§6 (1st-order).* **NICE-TO-HAVE.**

### Appended 2026-08-07 (data attribution + licensing audit)

Attribution for the HMD and SOA-ILEC sources was added to the three committed
findings documents and pinned by `tests/test_docs/test_data_attribution.py`
(`docs/DATA_LICENSING.md`). The audit that produced it surfaced one item that is
**not** closed.

- **Nobody has read the HMD or SOA terms of use.** Every licensing statement this
  repository has ever made is second-hand paraphrase — `RUNBOOK...` §0 "keeps you
  inside both licences", §6 "forbidden by the licences", and a
  `docs/measurements/README.md` heading that asserted the flat legal conclusion
  "Why committing these is not a licence problem". A grep confirms **no section
  number, quotation or URL to a terms document appears anywhere in the tree.** The
  attempt to read the primaries in-session was denied at the network gateway (403
  on `www.mortality.org` and `www.soa.org`; egress is a GitHub/PyPI allowlist), and
  search-engine summaries were deliberately **not** substituted — swapping one
  layer of paraphrase for another reproduces the defect rather than fixing it.
  `DATA_LICENSING.md` §4 poses the three questions that need answering: whether
  the terms reach *derived aggregates* or only the dataset; whether a prescribed
  attribution wording exists that §2 does not meet; and whether a non-commercial
  condition applies to a public repository whose stated purpose (CLAUDE.md §1) is
  a commercial alternative to AXIS/Prophet. §1 shows the committed artefacts are
  conservative by any reading, and §4c names the narrow remedy if an answer comes
  back unfavourable — the ILEC `ae_by_year` absolute counts and
  `soa_surface_comparison` rows are the only exposure, and both reduce to ratios
  without losing a single finding. **Maintainer-gated: it needs a browser this
  container does not have.** *Source: 2026-08-07 attribution pass (1st-order).*
  **IMPORTANT.**

### Appended 2026-08-07b (SOA terms read — the licensing item narrowed and re-aimed)

The item appended earlier the same day is **half-closed**: the maintainer read the
SOA Website Terms of Use, and ADR-183 amendment 1 plus `DATA_LICENSING.md` §3
record the clause text. What replaces it:

- **SOA permission request outstanding.** No dataset-specific licence exists; the
  site-wide Terms permit only non-commercial educational use, prohibit public
  **or** commercial distribution, bar derivative works, and offer prior written
  permission as the only route. The request is drafted at `DATA_LICENSING.md` §6
  and is the maintainer's to send. Revisit on any of the four triggers in §5b — a
  second contributor, any commercial engagement, a reply either way, or 90 days of
  silence. **Maintainer-gated.** *Source: SOA Terms of Use, read 2026-08-07
  (1st-order).* **IMPORTANT.**
- **Strip the absolute death counts from the two ILEC reports.** One re-run of
  `scripts/experience_diligence.py`; every finding in the measurement document
  survives because they are all ratios. Per ADR-183 amendment 1 this reduces
  exposure rather than eliminating it — the derivative-work clause is not about
  substitutability — but it removes the only committed content that could be
  characterised as republishing SOA figures rather than describing them.
  Maintainer-gated (needs the 12.5 GB cache). *Source: DATA_LICENSING §5c
  (1st-order).* **IMPORTANT.**
- **HMD User Agreement still unread.** The SOA answer does not transfer — different
  body, different kind of publisher. Likely cheap to close: if the widely-reported
  CC BY 4.0 licensing is accurate, derivative works and commercial use are both
  permitted and only attribution is owed, which §2a already provides. Needs a
  browser this container does not have. *Source: DATA_LICENSING §4 (1st-order).*
  **NICE-TO-HAVE.**

### Appended 2026-08-08 (HMD terms read — the licensing item narrows to one line)

- ~~**Supply the HMD version DOI.**~~ — **SHIPPED** (PR #188, ADR-183 amendment 3):
  access date **3 August 2026** (`kMDItemDateAdded`), DOI
  **`10.4054/HMD.Countries.20260615`** — the 06/15/2026 release of the *By country*
  product, which was current on the access date, so no *Previous Versions* row
  applies. **The HMD licensing position is closed entirely**: permissive terms,
  estimates tier confirmed, attribution complete in the prescribed form and pinned
  by a guard test. SOA is the only open licensing item.

  **Two things about how this closed, both flagged by the PR #188 review.** The DOI
  and the versions-table reading were **supplied by the maintainer in-session on
  2026-08-08**, which is what discharges the `Maintainer-gated` flag below — the
  container has no browser and performed no lookup. And the instruction below to use
  the **Statistics** column is **WITHDRAWN**: the series on disk are per-country
  `STATS` files, so the *By country* product is the right family. That reversal is
  ours, is the part still open to challenge, and is argued in `DATA_LICENSING.md`
  §2a rather than left implicit here.

  ~~Original text follows, unedited — including the withdrawn instruction and the
  gate it carried, because deleting them would erase what was reversed.~~ The HMD
  User Agreement was read 2026-08-08 and is
  **permissive** — CC BY 4.0 on its own estimates, derivatives and commercial use
  both permitted, and the `STATS` bundle this project used is confirmed to be that
  tier (ADR-183 amendment 2). The single remaining gap is that CC BY 4.0's condition
  *is* attribution and HMD prescribes a **version DOI** as part of it, which
  `DATA_LICENSING.md` §2a does not yet carry. Only the maintainer knows which
  release was downloaded. Four checks on 2026-08-08 settled what the files can and
  cannot tell us:
  the USA and GBRTENW headers differ by sixteen months (09 Jun 2026 vs 31 Jan 2025),
  proving `Last modified` is a per-country series stamp and not a release version;
  and `stat` returns birth time equal to mtime **to the second**, so the filesystem
  is echoing the archive's stored date rather than recording an extraction. Neither
  identifies the bundle. `kMDItemDateAdded` did resolve the access date —
  **2026-08-03 22:31 UTC** — which turns the version into one lookup: read the
  *current* release date off mortality.org, and if it postdates 2026-08-03 the
  version held is 06/15/2026, otherwise it is the current one. Take the DOI from
  that row's **Statistics** column (not Countries — the one visible in the
  screenshot is a different artifact), paste it into §2a and both measurement docs,
  then update `test_the_hmd_attribution_gap_is_not_rounded_to_compliant`.
  **Maintainer-gated.**
  *Source: HMD User Agreement + provenance checks 2026-08-08 (1st-order).*
  **IMPORTANT.**
- **If HMD Input Database series are ever used, this analysis does not carry over.**
  Only the `STATS` output tier is CC BY 4.0; input data carries a no-commercial-gain
  and no-republication restriction. Anything drawn from the Input Database needs its
  own provenance determination first. Nothing does today; this is a tripwire for
  future work rather than an open item. *Source: DATA_LICENSING §4b (1st-order).*
  **NICE-TO-HAVE.**

### Appended 2026-08-08c (next epic scoped — the penalized MI surface)

- **P-splines with REML-selected λ for the tensor MI surface.**
  `docs/PLAN_penalized_mi_surface.md`, 5 slices, ~4–6 dev-days autonomous plus one
  maintainer run. Promoted from the spline-diagnostics epic, which established both
  the case for it and the limits of that case.

  **What it fixes:** `df` currently sets basis dimension *and* wiggliness with one
  integer, which makes complexity a researcher degree of freedom — `year_df` 4→3
  and then `df==degree` 3→2 each moved a published ILEC finding, by hand, with
  nothing in the fit selecting them. A penalty makes effective complexity
  data-driven and lets it fall where information is thin, which is the mechanism
  ADR-184 measured (3.13-point swing at age 45 against 0.46 at 85, on a flat truth).

  **What it explicitly does not fix: age 45.** ADR-184 amendment 2 showed that
  climb survives removing a whole polynomial order. Framing this epic as fixing it
  would be a promise the previous epic already falsified, and the plan says so in
  §1 so nobody makes it later.

  **Why it should work:** the quadratic already beat the shipped cubic on the one
  independent check (SOA's own expected deaths — 10% and 35% closer) at equal
  dispersion and one fewer parameter. Something near "less than cubic" was right,
  and it took two epics and a maintainer run to find by hand. REML should find it
  in one fit. §6 registers that as a falsifiable prediction along with three others,
  each with its failure branch written out before slice 1 exists.

  **Known hard parts:** statsmodels penalizes but its smooths are additive-only, so
  the Kronecker design and penalty are hand-built; λ selection introduces an
  optimizer that threatens determinism harder than the BLAS jitter which already
  falsified the byte-for-byte claim; and eight distinct ILEC calendar years may
  simply not identify λ — which would be a finding rather than a failure.
  *Source: PLAN_penalized_mi_surface (1st-order).* **IMPORTANT.**

  **Progress — slices 1–3 done, ADR-185, ADR-186 + amendments 1–2, ADR-187 +
  amendments 1–2** (slice 3 merged as **PR #189**, 2026-08-09; ledger-healed
  2026-08-09 per routine step 4b). Slice 3 also **revised the plan**: 5 slices became
  7, and `mgcv` moved from an optional oracle for one quantity to a load-bearing
  conformance slice for three (PLAN Revision 1). Slice 3's own registered hypothesis
  came back **false** — the committed delta-method bands are calibrated (95.7%/95.9%),
  so ADR-184's age-45 artifact is a statement about the point estimate's spread and
  not about the interval.
  Two of the three "known hard parts" have resolved, in opposite directions.
  *statsmodels:* confirmed additive-only on 0.14.6, so the Kronecker design and
  penalty are hand-built as anticipated — and worse than anticipated, **patsy cannot
  build a P-spline basis at all** (it always clamps boundary knots, which destroys
  the difference penalty's null space), so the basis comes from
  `scipy.interpolate.BSpline.design_matrix` on an extended uniform sequence.
  *Determinism:* the threat **did not materialise**, because there is no optimizer —
  selection is a deterministic grid, so λ is a grid point and reproducible by
  construction. The hard part named here was real; the answer was to remove it
  rather than manage it. *Identifiability on eight ILEC years remains open and is
  slice 5's question.*

### Appended 2026-08-08d (harvest gap — the surviving age-45 explanations)

ADR-184 amendment 2 and `MEASUREMENT_experience_gam_ilec.md` §7 both name three
explanations that survive the diagnostic, and neither promoted them. They are the
direct 1st-order follow-ups of that PR's own headline finding, and without them the
retracted ledger entry above has no successor — "age 45 is not usable, for reasons
we did not write down" is exactly the state this ledger exists to prevent.

Slice 4 ruled out spline flexibility. **It ruled out nothing else.** Each of the
following is untested, live, and could individually account for the climb:

- **Duration mix *within* a band.** The banded fit conditions on nine duration
  bands with a fixed representative, but selection moves fastest in the first few
  policy years and band 1 still pools whatever sits inside it. A mix drifting with
  calendar year inside a band leaks into the trend exactly as the pooled-versus-
  banded contrast showed at the coarser level (ADR-182 amendment 4) — the same
  mechanism one level down. Testable by re-banding more finely at young ages and
  seeing whether age 45's climb moves. *Source: ADR-184 amendment 2 (1st-order).*
  **IMPORTANT.**
- **`uw_class` composition drift at young ages.** Preferred-class structures are
  not stable across an eight-year issue window, and the young end of an insured
  book is where new business concentrates — so the *mix* of classes at age 45 in
  2019 need not resemble 2012. `uw_class` enters as an additive factor, which
  handles a level difference but not a drifting composition. Testable by fitting
  age 45 within a single `uw_class` stratum. *Source: ADR-184 amendment 2
  (1st-order).* **IMPORTANT.**
- **The empirical `q_base` at sparse ages.** The offset is the pooled crude rate
  from the data itself, so at young ages it is estimated from few deaths and
  carries its own noise. It is calendar-invariant by construction and therefore
  *cannot* create a trend — but a badly-estimated base changes which cells the
  tensor must explain, which is how duration banding moved the surface without the
  duration term itself contributing. Testable by substituting a published table
  (VBT 2015) as the base and refitting. *Source: ADR-184 amendment 2 (1st-order).*
  **NICE-TO-HAVE** — the weakest of the three mechanistically, and the one with a
  ready-made alternative already loaded on the ILEC path.

All three are cheap on the maintainer's cache and none needs new data. Any one of
them landing would replace the retracted rationale with a real one; all three
coming back null would make "genuine underwriting-era effect" the leading
explanation, which is a publishable finding in its own right.

### Appended 2026-08-09 (slice-3 harvest — two items the coverage study surfaced)

- ~~**`select_lambdas_reml` aborts when a grid corner fails to converge.**~~
  — **SHIPPED** (PR #190 / ADR-188 decision 1, slice 4): the point is scored `+inf` and the
  search continues, with `n_rejected` / `n_evaluated` carried onto the fit so a
  truncated grid cannot hide; rejecting *every* point raises rather than returning the
  grid centre as a fabricated selection. Reproduced at seed 1098 before the fix (routine
  step 7b) and measured at **2 replicates in 400** during the coverage study — either
  one would previously have aborted it. **Caveat found in CI (ADR-188 amendment 1):**
  the corner's non-convergence is **platform-dependent** — it converges on CI's Python
  3.13 runner — so the "one replicate in a hundred" rate below is a property of a
  machine, not of the estimator. The fix is unaffected; three tests that pinned the
  accident were rewritten to force it. Original entry preserved below.

  **`select_lambdas_reml` aborts when a grid corner fails to converge.**
  **BLOCKER for slice 4** and already recorded as such in
  `CONTINUATION_penalized_mi_surface.md`; promoted here because it outlives the epic
  if the epic stalls. The coarse sweep visits `log10 λ = (-1, 8)` — essentially
  unpenalized in age, saturated in year — on every call, and on roughly **one
  replicate in a hundred** that point fails penalized IRLS in 100 iterations. The
  exception propagates and the entire selection dies, rather than the point being
  scored as unusable and skipped. Reproduced on the quadratic fixture at seed 1098.
  Slice 4 runs this selector on the 125,676-cell ILEC book, where a one-in-a-hundred
  abort is a failed production run rather than a flaky test. The fix is a **design
  choice**, which is why it was not patched inside a review round: score a
  non-converging point `+inf` and continue (cheap, and arguably correct — a λ whose
  fit does not converge is not a λ to select), damp the IRLS step, or raise the
  iteration cap. *Source: ADR-187 finding 5 (1st-order).* **IMPORTANT.**

- **REML λ selection is unstable across replicates, and nothing currently says so to
  a user.** On realisations of the *same* truth, log10 λ_age ranges over roughly five
  decades (2.50 to 8.00 across eight consecutive seeds on an eight-year window). The
  selected λ is one draw from a wide distribution, not a property of the data. Three
  consequences that are not yet anywhere a reader would see them: a reported λ is not
  reproducible-in-meaning across resamples even though it is reproducible-in-value by
  construction (Anchor 3 is about the *algorithm*, and this is about the
  *estimator*); a band displayed beside a selected λ is **not jointly calibrated**
  with it, because `Vb` carries no smoothing-parameter uncertainty; and any single
  penalized coverage figure is provisional — slice 3 saw its own headline move 5.5
  points on a selection-seed change. The candidate remedies are a proper marginal
  treatment of λ, averaging the selection over resamples, or simply reporting the
  instability. **The unconditional (select-per-replicate) coverage study that would
  quantify what a user actually gets is not delivered** — it is blocked by the item
  above. *Source: ADR-187 finding 2 (1st-order).* **IMPORTANT.**

  **PARTLY ADDRESSED (slice 4 / ADR-188).** The study is **delivered** —
  `docs/MEASUREMENT_unconditional_coverage.md` — and it quantifies the cost: selecting
  λ per replicate takes the *same* band from ADR-187's conditional 0.8710 down to
  **0.8201**. The "not jointly calibrated" consequence has a remedy shipped behind
  `fit_reml(unconditional=True)`, which recovers +3.2/+3.8 points of a ~13-point
  shortfall. **The item does not close**: nothing yet reports the instability to a
  *user* (that is slice 6), and the remaining shortfall is unexplained pending slice 5.

### Harvested 2026-08-09b (penalized MI slice 4 — ADR-188; the Anchor-7 gate FAILED)

**Headline for the maintainer:** the select-per-replicate coverage study is delivered
and **the gate does not pass**. Unconditional coverage is **0.8516 / 0.8581** against a
floor of 0.9192, so **nothing in this project may be labelled a 95% band** until slice
5 explains the shortfall.

> **Superseded twice, 2026-08-23 (ADR-203).** These figures went stale when `ce0b9f1`
> corrected the REML criterion on 2026-08-19: re-measured, the shipped band is
> **0.7815 / 0.8090**. Implementing Wood, Pya & Saefken (2016) eq. (7) then moved it to
> **0.8167 / 0.8354** — still failing. The bolded conclusion is unchanged and now rests
> on two independent measurements rather than one. On the identical truth and seeds, the **unpenalized**
delta-method band covers **0.9586** at 4.4x the width — the estimator this epic set out
to improve on currently has the better interval. That is a statement about the
*interval* and does not retract ADR-186's RMSE result for the point estimate.

- ~~**Run `mgcv` conformance levels 1 and 4 before anything else in slice 5.**~~
  — **SHIPPED** (PR #192 built it, **PR #193** ran it, ADR-189 + amendment 1): every level
  ran against the committed synthetic exchange in a digest-pinned container (R 4.6.1 /
  mgcv 1.9.4). **Levels 1-3 AGREE, levels 4 and 5 DISAGREE.** `tr(F)` **verified** to
  7.2e-13; the Kass-Steffey covariance **refuted — it systematically under-inflates**
  (ours 1.11-1.21x, mgcv 1.49-1.87x, every cell the same direction); `gamma` unsettled.
  The level ordering this entry asked for became moot — every level batches into one CI run.
  **It closes as asked and opens something better**: the successor work item is the
  under-inflation itself, below, because it converts "the Anchor-7 shortfall is unexplained"
  into "our Kass-Steffey arithmetic under-inflates". Original entry preserved below.

  **Run `mgcv` conformance levels 1 and 4 before anything else in slice 5.**
  The failing gate has two candidate causes with different remedies — our Kass–Steffey
  arithmetic is wrong, or the residual is shrinkage bias that no covariance correction
  can reach — and `vcov(m)` vs `vcov(m, unconditional = TRUE)` is what separates them.
  Slice 5 was already planned; what changed is that it is now **decisive rather than a
  completeness item**, and its level ordering matters if the maintainer's R time is
  limited. *Source: ADR-188 finding 1 (1st-order).* **BLOCKER** for any slice that puts
  a penalized band in front of a reader.

  **PARTLY ADDRESSED (slice 5 / ADR-189, PR #192), and the level-ordering half is moot.** The
  suite is **built and committed** — exporter, R script, comparator, runbook, the
  seed-pinned synthetic exchange and our own reference for it, 45 tests, none needing R.
  Every level is batched into **one** `Rscript` invocation, so "run 1 and 4 first if R
  time is short" no longer needs answering. **The item does not close: the R run has not
  happened.** It is now purely waiting on a human — one command,
  `docs/RUNBOOK_mgcv_conformance.md`.
  One thing the build sharpened and one it weakened, both worth knowing before the run:
  the exported coefficients are verified (without R) to sit at the unique penalized
  maximiser — worst cell `||Xᵀ(y-μ) - Sβ||∞` = **2.19e-10** — so a level-1 disagreement
  can only be R's solver or a convention, never our fit. But **level 4 is weaker than
  ADR-188 assumed**: `mgcv` forms `Vc` only when `sp` was *estimated*, so the
  Kass-Steffey correction cannot be compared at a matched λ at all, only as an inflation
  ratio at independently-selected λ. It still separates the two candidate causes, but
  less sharply than "`vcov(m)` vs `vcov(m, unconditional = TRUE)`" reads.

- **Decide whether the penalized band may be shown to a user at all.**
  Slice 6 is where these numbers reach a human. On current evidence the penalized
  interval covers 10 points worse than the one it would sit beside. Anchor 6 keeps the
  unpenalized path alive so the option exists in both directions, but "show it with a
  caveat" and "do not show it yet" are different products and the plan does not decide
  between them. *Source: ADR-188 finding 3 + DEV_SESSION_LOG_2026-08-09 Open Questions
  (1st-order).* **IMPORTANT — needs a maintainer decision, not a routine one.**

- **Replace the finite-difference Jacobian/Hessian with analytic derivatives.**
  `smoothing_uncertainty` costs **nine penalized fits per surface**. That is negligible
  against the selector's ~200 on a fixture and is not obviously negligible on the
  125,676-cell ILEC book, where each fit is the expensive object. Wood gives the
  analytic forms. *Source: ADR-188 Out of scope (1st-order).* **NICE-TO-HAVE** — a cost
  item, not a correctness one, and it should wait until slice 5 has confirmed the
  quantity is right before it is made faster.

- **Measure coverage on real experience, not only on injected truths.**
  Every coverage figure this project has — ADR-187's and ADR-188's alike — comes from a
  simulation whose truth is known because we wrote it. Whether these rates survive real
  ILEC overdispersion, sparsity and misspecification is unmeasured, and ADR-187 finding
  4 already showed both estimators collapse to ~67-76% at old ages once the basis cannot
  represent the truth. *Source: ADR-188 Out of scope (1st-order).* **IMPORTANT.**

- **A fixture must be checked against the penalty null space, not eyeballed for
  variation.** Slice 4's first age-varying truth used a *linear* age gradient, which
  sits **inside** the second-difference penalty's null space, so it reproduced the
  age-flat degeneracy under a different name — λ_age spread 5.50 decades against 1.25
  for the corrected quadratic and 5.00 for age-flat. This is the third epic in a row to
  hit the same shape (ADR-186: a truth the basis could not resolve; ADR-187: designed
  around it explicitly; ADR-188: built one wrong anyway). It is now a test on the
  *second* difference rather than a habit, and the generalisation is worth applying to
  any future estimator study: **assert the fixture exercises the mechanism, because
  "the values differ" passes on a fixture that does not.** *Source: ADR-188 finding 4
  (1st-order).* **NICE-TO-HAVE** — a practice note; no code is owed.

**Also corroborated rather than newly found:** ADR-187 amendment 1's mechanism holds at
**200 replicates rather than 8**. λ_age's spread still falls four-fold once the truth
carries age structure the penalty can see, and a max-minus-min range over 200 draws is a
much harder statistic than over 8. No action; recorded because the amendment's headline
number was previously supported by eight seeds.

### Harvested 2026-08-10 (penalized MI slice 5 — ADR-189; the suite is BUILT, the R run is NOT)

**Headline for the maintainer:** the `mgcv` conformance suite is committed and needs
**one command** from you — `Rscript scripts/mgcv_conformance.R`, no data, no arguments,
see `docs/RUNBOOK_mgcv_conformance.md`. It is now the epic's only external dependency,
and it gates both the Anchor-8 conversion of three adopted quantities (`tr(F)`, the
Kass-Steffey covariance, `gamma`) and the diagnosis of ADR-188's failing coverage gate.

One result arrived without R and it narrows what the run can find: the exported
coefficients are verified to sit at the **unique penalized maximiser** of the exported
problem (worst cell `||Xᵀ(y-μ) - Sβ||∞` = 2.19e-10 on O(1e2-1e3) counts), so any level-1
disagreement is R's solver or a *convention* — never our fit.

- **Run the `mgcv` conformance suite.** Covered by the standing BLOCKER above, annotated
  rather than duplicated. Listed here only so this section's reader is not left thinking
  slice 5 finished the job: **built is not run.**

- ~~**`mgcv`'s `scalePenalty` semantics for `paraPen` penalties are adopted from the
  documentation and unverified.**~~ — **CLOSED BY MEASUREMENT** (PR #193, ADR-189
  amendment 1): the setting is a **no-op on the `paraPen` path** and therefore not
  load-bearing at all. Structurally `gam.setup` passes `scale.penalty` only into
  `smoothCon()`; empirically, with penalties mismatched by `1e6` and λ fixed,
  `max|coef(TRUE) − coef(FALSE)|` is **exactly 0**. `sp` already multiplies the supplied `S`
  directly and the guarantee is *structural*. It stays `FALSE` as a version tripwire, which
  is a much smaller claim than the one this entry was written about.
  **And the fourth "defence" was worse than absent:** `penalty_scaling()` could only ever
  return `full.sp` — the smoothing-parameter vector, not a rescaling factor — so it fired the
  "sp did not multiply the supplied S" note on **all ten cells** of a run where level 1 agreed
  to 1e-13. Probe removed in #193. This one setting attracted **two defects of opposite
  polarity in two rounds** (a guard that could fail silently, then one that fired always),
  which is the reusable lesson: it was over-engineered because it was believed load-bearing.
  Original entry preserved below.

  **`mgcv`'s `scalePenalty` semantics for `paraPen` penalties are adopted from the
  documentation and unverified.** The whole suite rests on `sp` multiplying the supplied
  `S` **directly**, and `mgcv` rescales caller-supplied penalties by default. Whether and
  how that applies to `paraPen` specifically was not checkable in the routine's container
  — there is no R there — so it carries the same *adopted, not verified* mark as the three
  quantities the run is meant to settle. Four defences are in place (the script sets it
  FALSE, fails loudly if the argument is rejected, reads the manifest field directly and
  refuses a missing one rather than coercing it into the unsafe direction through
  `isFALSE()` — PR #192 review [P2] — and records every scaling artefact the fit exposes;
  the comparator additionally refuses a reference reporting rescaling left on), but a
  defence is not a verification. **If `penalty_scaling` comes back non-trivial on the
  first run, that is the run's first finding**, and the fix is one line of R rather than a
  re-derivation of our arithmetic. *Source: ADR-189 decision 8 (1st-order).* **IMPORTANT.**

- **Two free-`sp` tolerances now have their first measurement — both pass narrowly.**
  **PARTLY ADDRESSED** (PR #193): `max_abs_log10_sp_diff` 4.3221e-01 against 0.5 and
  `abs_edf_total_diff_free_sp` 8.7334e-01 against 1.0 — ~13% of headroom each, close enough
  that a different seed could cross either. Under `gamma = 1.4` the same two **miss**
  (6.7244e-01 and 1.1270), which is exactly why `gamma` is recorded as unsettled. **It does
  not close**: a marginal pass is not a calibration, and the remaining work is a *stated rule
  about selection noise* derived from the grid resolution and the profile's curvature — not a
  larger number. The maintainer restated the no-widening rule on #192; it stands.
  Original entry preserved below.

  **Two free-`sp` tolerances are PROVISIONAL and nobody has calibrated them.**
  `max_abs_log10_sp_diff` at 0.5 decades and `abs_edf_total_diff_free_sp` at 1.0 are
  *reasoned* — from the selector's 0.25-decade grid and ADR-187 amendment 2's shallow REML
  profile — not measured against R. A tolerance chosen without a measurement can pass a
  real disagreement as easily as it can fail a spurious one. The first run is what firms
  them, and **the answer is not to widen them to pass** (ADR-188's own refusal, restated).
  *Source: ADR-189 decision 6 + PLAN slice-5 discharge (1st-order).* **IMPORTANT.**

- ~~**Level 4 cannot compare the Kass-Steffey correction at a matched λ, and there is no
  third option.**~~ — **CLOSED: weak, and it was still enough** (PR #193). The limitation is
  real and unchanged — `mgcv` forms `Vc` only for estimated `sp`, so the comparison is an
  inflation ratio at independently-selected λ. But it produced a clear verdict: a three-cell,
  **same-direction**, ~1.5x-sized miss is not what λ disagreement produces, and level 2
  passing is what licenses saying so. Neither of the two sharpenings this entry proposed (an
  analytic derivation, or a second round trip at R's own `sp`) is needed to read the result.
  **Worth remembering the next time a comparison looks too blunt to be worth building.**
  Original entry preserved below.

  **Level 4 cannot compare the Kass-Steffey correction at a matched λ, and there is no
  third option.** `mgcv` forms `Vc` only when the smoothing parameters were *estimated*, so
  no fixed-`sp` fit can produce one; and at free `sp` the two sides select different λ. The
  exact half of level 4 is therefore the conditional `Vb` at fixed λ, and the correction
  itself is only checkable as an **inflation ratio** at independently-selected λ — which
  cannot separate a wrong Jacobian from a λ disagreement on its own and must be read after
  level 2 passes. ADR-188's failing gate needs level 4 to choose between "our arithmetic"
  and "shrinkage bias no covariance can reach", so this limitation is load-bearing. Two
  possible sharpenings, neither cheap: derive the correction analytically and compare
  term-by-term, or spend a second round trip feeding R's own selected `sp` back as a fixed
  pair. *Source: ADR-189 decision 6 (1st-order).* **IMPORTANT.**

- **Decide whether slice 6 waits for the R run.** The plan sequenced harness integration
  *behind* conformance for a stated reason: slice 6 is where these numbers first reach a
  human, and shipping an unverified `edf` beside an unverified band is the "less auditable,
  not more" failure Anchor 4 exists to prevent. Slice 5 is built but unrun, so that intent
  is half met. Proceeding is defensible if every `edf`/λ/band carries the *adopted, not
  verified* mark on top of the Anchor-7 amendment's three duties; waiting is also
  defensible. *Source: CONTINUATION_penalized_mi_surface Open Questions +
  DEV_SESSION_LOG_2026-08-10 (1st-order).* **IMPORTANT — a maintainer decision, not the
  routine's.**

- **The conformance exporter maintains a second ingest path for real data.** It reads a
  grouped-cells file rather than calling the diligence harness's ingest, because that ingest
  reaches private helpers (`_regroup`, `_filter_window`) and duplicating ~60 lines would be
  a second path to keep in step — untestable in this container, for a case whose exchange
  can never be committed. The clean fix is to promote those two helpers to public API and
  have the exporter call the real thing. *Source: ADR-189 decision 9 Out of scope
  (1st-order).* **NICE-TO-HAVE** — the current path is tested end to end on a synthetic
  frame put through `attach_empirical_base`, so this is duplication risk, not a defect.

- **The comparator captures `mgcv`'s REML score but does not compare it.** The R side dumps
  `m$gcv.ubre` as an intermediate, and our `reml_score` is in the Python reference, but the
  two carry different additive constants so no tolerance was defensible without a
  measurement. Once one run exists the offset is knowable and the criterion itself — not
  only the λ it selects — becomes comparable, which is a strictly stronger check on level 2.
  *Source: ADR-189 (1st-order).* **NICE-TO-HAVE** — and it needs the first run to exist
  before it can be specified, so it cannot be done ahead of it.

### Harvested 2026-08-10b (the conformance run — ADR-189 amendment 1, PR #193)

**Headline for the maintainer: the run happened, and ADR-188's failing gate now has a
located cause.** Levels 1-3 agree; `tr(F)` is **verified** to 7.2e-13, which discharges the
Anchor-4 obligation that has been open since slice 2. Levels 4 and 5 disagree, and level 4's
disagreement is the most valuable single result this epic has produced.

Three entries above close on this run (the level-1-and-4 BLOCKER, the `scalePenalty`
question, the level-4-is-weak worry). What replaces them is one BLOCKER and two smaller items.

- **The Kass-Steffey unconditional covariance systematically under-inflates.**
  Measured against `mgcv` on the committed exchange:

  | cell | ours | mgcv | rel. diff | tol |
  |---|---:|---:|---:|---:|
  | `l2-free-sp` | 1.1109x | 1.7392x | −0.3613 **FAIL** | 0.25 |
  | `l2-free-sp-kb` | 1.2139x | 1.8670x | −0.3498 **FAIL** | 0.25 |
  | `l2-free-sp-factors` | 1.1591x | 1.4863x | −0.2201 pass | 0.25 |

  **This is the answer to a question the project has carried since slice 4.** ADR-188
  measured unconditional coverage at 0.8516 / 0.8581 against a 0.9192 floor and named two
  candidate causes with different remedies: our arithmetic, or shrinkage bias no covariance
  can reach. An under-inflated covariance under-covers, in the observed direction, on the same
  cells — so it is **the arithmetic**, and the remedy is a fix rather than a redesign. The
  reading is legitimate because slice 5's own precondition holds: the inflation ratio is
  legible only once level 2 passes, and level 2 passes.
  Places to look, in order: the central-difference Jacobian `∂β̂/∂ρ` and `KS_LOG_STEP`; the
  **eigenvalue floor** in `smoothing_uncertainty`, which caps the variance a flat direction
  contributes and would produce exactly this if it binds too often (ADR-188 measured
  `n_floored` at 0.46 / 0.15 directions per fit); and the natural-log-vs-decade conversion,
  the one place a factor of `ln(10)²` ≈ 5.3 could hide. **Do not tune the floor until it
  matches `mgcv` — derive it.** *Source: ADR-189 amendment 1, level 4 (1st-order).*
  **BLOCKER** — it is the standing bar on labelling anything a 95% band, and it now has a
  location.

  > **RE-SCOPED 2026-08-15 — ADR-190. The measurement stands; the diagnosis above was
  > wrong.** All three "places to look" are refuted by measurement: the step is converged
  > (~1.7% across an 8x sweep), the eigenvalue floor **never binds** (`n_floored` 0 on every
  > free-sp cell), and the `ln(10)` conversion was already correct. Built from `mgcv`'s own
  > coefficients, own `V_rho` and own λ, `J V_rho Jᵀ` reproduces **our** inflation
  > (1.18 / 1.15 / 1.24), not `mgcv`'s — so `vcov(unconditional = TRUE)` is **not**
  > `Vb + J V_rho Jᵀ` but a larger quantity, by a non-constant 3.2-4.1x.
  >
  > **It is not our arithmetic — it is our formula.** `mgcv:::Vb.corr` uses `dw/drho`, the
  > derivative of the IRLS weights, which our fitter never forms; plain Kass-Steffey is the
  > first-order part of Wood, Pya & Säfken (2016).
  >
  > **Still a BLOCKER, now a slice rather than a fix.** Implementing Wood (2016) needs
  > `dw/drho`, and **it must be re-derived from the paper: `mgcv` is GPL (>= 2) and this
  > project is MIT, so its implementation cannot be transcribed.**
  >
  > **Registered prediction:** a correction 3.2-4.1x larger should move ADR-188's coverage
  > from 0.8516 / 0.8581 toward the 0.9192 floor. If it does not, there is a second cause.
  >
  > **RESOLVED 2026-08-23 (ADR-203): confirmed in direction, refuted in sufficiency.**
  > Against the re-measured baseline (0.7815 / 0.8090 — the quoted one was stale), eq. (7)
  > moves coverage to 0.8167 / 0.8354. It moves, so the prediction's literal trigger did
  > not fire; it falls up to 0.1025 short, so **there is a second cause anyway.** The
  > prediction was written against a *number* rather than a *re-measurement*, which is
  > how its baseline was able to drift underneath it — see ADR-203 finding 0.
  >
  > One process finding worth keeping: `test_the_hessian_standard_error_is_wide_but_finite`
  > has asserted `n_floored == 0` since slice 3 — the repository already held the evidence
  > against the floor hypothesis, in a green test, while three documents carried the
  > hypothesis for five days. A claim in prose and an assertion in a test are the same
  > claim; only one of them is checked.
  >
  > *Provenance of the items above: ADR-190 / the 2026-08-15 session (1st-order) — the
  > re-scoped BLOCKER, the GPL/MIT constraint and the registered prediction all descend
  > directly from starting this item, so none of them is a widening of it.*

- **Supply the Wood, Pya & Säfken (2016) derivation — a HUMAN prerequisite, and the only
  thing standing between the covariance BLOCKER and a well-posed slice.** ADR-190 decision 3
  established that `mgcv`'s implementation cannot be read: it is **GPL (>= 2)** and this
  project is **MIT**. So the correction has to come from the mathematics, and an autonomous
  session cannot obtain it — outbound access is policy-restricted, and the one copy on the
  machine is the source it is forbidden to use. **A routine run pointed at this item would be
  stuck between a source it must not read and a paper it cannot fetch, and the likely failure
  mode is that it derives something plausible from first principles and labels it Wood's
  correction.** That is worse than not starting.

  What is needed, in order of preference:
  1. **`docs/DERIVATION_unconditional_covariance.md`** — the correction written out as
     mathematics, with `dw/drho` defined explicitly and the paper cited. Once this exists the
     work becomes an ordinary implementation slice a routine can take.
  2. Failing that, the equations transcribed from Wood, Pya & Säfken (2016, JASA 111:1548),
     or **Wood, *GAM: An Introduction with R*, 2nd ed. §6.10**, which covers the same
     material and may be the easier source to hand.

  **Do NOT commit the paper itself.** This repository is public and the JASA article is not
  ours to redistribute; the derivation is a rewriting, the PDF is a copy.
  *Source: ADR-190 decision 3 (1st-order).* **BLOCKER on the BLOCKER** — the covariance item
  above cannot start until this lands, and it is the cheapest item on this list for a human
  and impossible for anyone else.

- **Audit prose claims in ADRs and CONTINUATIONs against the test suite.** ADR-190 found
  the eigenvalue-floor hypothesis had been carried for five days across an ADR, a docstring
  and this ledger while `test_the_hessian_standard_error_is_wide_but_finite` asserted its
  negation and passed on every run. **That is a search anyone can run and nobody did**,
  because the test was framed as being about a standard error and the hypothesis as being
  about coverage — the two never collided in a grep. The concrete item: before naming a
  suspect in an ADR, grep the suite for a test that already speaks to it; and sweep the
  standing hypotheses in `DECISIONS.md` for ones a green test already answers.
  *Source: ADR-190 / the 2026-08-15 session log follow-up 4 (2nd-order — it is a
  consequence of the finding rather than of the BLOCKER itself).* **NICE-TO-HAVE** — the
  cost of the miss here was five days of a wrong suspect list, not a wrong result.

- **`gamma` is unsettled: level 5 misses both tolerances narrowly, the sign check passes.**
  `max_abs_log10_sp_diff_gamma` 6.7244e-01 against 0.5, `abs_edf_total_diff_gamma` 1.1270
  against 1.0, while `gamma_edf_delta_agrees_in_sign` **passes** — `gamma` moves EDF the same
  way on both sides. Unsettled, **not refuted**. Note the cost/benefit: `gamma` defaults to
  1.0, is exactly inert there by construction, and nothing in the project uses it, so this
  may be worth less than the level-4 fix. *Source: ADR-189 amendment 1, level 5
  (1st-order).* **NICE-TO-HAVE.**

- **The R script's header still frames `scalePenalty` as load-bearing.**
  `scripts/mgcv_conformance.R` is owned by PR #193 in the current stack, so #192 deliberately
  did not edit it — the prose sweep covered the *documents* only. The file's own header
  comment ("THE ONE SETTING THAT IS LOAD-BEARING") is now refuted prose. *Source: ADR-189
  amendment 1, "Not done here" (1st-order).* **NICE-TO-HAVE** — a comment, not behaviour, and
  whoever lands #193 is best placed to do it.

- **The REML convention offset is recorded and gates nothing.** `reml_score` is not a compared
  metric, so the `≈ −l_sat/gamma` offset (`mgcv` scores on deviance; we use the full
  log-likelihood) changes no verdict. A residual of 0.93-3.17 survives after removing it and
  is unexplained. It only becomes a question if REML is ever compared — at which point it is a
  0.1% question rather than a 100% one. *Source: PR #193 (1st-order).* **NICE-TO-HAVE.**

**One process lesson, no code owed.** The build shipped a grep test over the R script and
called the R side covered. **A grep test pins strings in a file it cannot execute**, and the
script crashed on its first cell for every one of the six fixed-λ cells — λ went through
`gam()`'s top-level `sp`, which a `paraPen`-only fit cannot accept. The R-gated end-to-end
test *would* have caught it and skipped in every environment that existed. The gap was never a
missing assertion; it was that nothing anywhere ran the file. **CI closed it, not a test** —
which generalises: for any artefact in a language the test suite cannot execute, the only real
coverage is an environment that runs it.

### Registered 2026-08-11 — the ACTIVE epic, so it is visible to a selecting routine

The `mgcv`-parity engine (`docs/PLAN_mgcv_parity_engine.md`,
`docs/CONTINUATION_mgcv_parity_engine.md`) is the project's largest numerical undertaking
and it entered through **maintainer direction (2026-08-10)** rather than through the
Tier-A table of a `COMMERCIAL_VIABILITY_REVIEW`. That is a legitimate override, but it left
the epic **invisible in this ledger** — flagged by the PR #194 review, and fixed here.

- **Build a Python GAM engine at parity with `mgcv` for the mortality-improvement
  workflow.** The maintainer's selected model form is 110 coefficients over 8 smooth terms,
  binomial/`cloglog` on a proportion response with prior weights, hand-chosen non-uniform
  knots, and **13 smoothing parameters — 21 with `select = TRUE`**. It needs three basis
  classes the current engine does not have (`cr`, `ti`, `sz`) plus a numeric-`by` varying
  coefficient term, and an N-dimensional (f)REML optimiser in place of the current
  two-dimensional grid. The existing penalized IRLS core carries over, verified to 5e-13.
  7 slices; `bam`/`discrete` deferred to a later epic. *Source: maintainer direction
  2026-08-10; PLAN §1 carries the target verbatim and the measurements that size it
  (1st-order).* **BLOCKER** — it is the path to measuring mortality improvement on the real
  experience data, which is the commercial objective the whole experience track serves.

- ~~**Schedule `ROUTINE_MGCV_PARITY.md`.**~~ — **CLOSED 2026-08-15.** This session ran as
  the routine's own scheduled firing, which is the evidence the registration exists (the
  cron config itself lives outside the repo, so the run is the only proof visible here).
  *Source: PR #194 review, human-review item (1st-order).*

- ~~**Retire or re-cut the `r4.6.1-2026-08-01` image tag.**~~ It was moved onto the
  `mboost`-carrying rebuild, so a tag that looks like it encodes R version and CRAN
  snapshot date no longer identifies a unique build. Nothing broke — the conformance
  workflow pins by digest — but anyone else pinning that tag silently picked up a package
  that was not there before. *Source: maintainer observation 2026-08-10, carried into the
  workflow comment; PR #194 review (1st-order).* **NICE-TO-HAVE** — a hygiene decision in
  another repo, and the digest pin already protects this one.
  > **CLOSED 2026-08-11 — R-Gam-base PR #3.** Immutable never-reused tags
  > `r<R>-cran<snapshot>-b<NN>`, a digest-keyed `BUILDS.md` catalog, a CI refusal to push an
  > existing tag, and an in-image manifest from build 3 forward. The tag is **deprecated
  > rather than deleted**, correctly: GHCR deletes package *versions*, and that tag sits on
  > the digest this repo pins, so deletion would have destroyed our oracle.
  > **The close paid for itself in a way the item did not anticipate.** Reconciling the
  > catalog against our own git history showed that ADR-189 amendment 1's numbers — `tr(F)`
  > at 7.2e-13, the level-4 refutation — were produced on build 1 (`a77a61cf…`), while the
  > current pin is build 2 (`8853bf2b…`). Our record said "a digest-pinned container" and
  > named no digest, so those numbers were attributable to the wrong image. Fixed in
  > ADR-189 amendment 1. **The hygiene item in the other repo found a provenance defect in
  > this one** — which is the argument for treating "nothing broke" as a weaker signal than
  > it feels like.

- ~~**The old epic's slices 6-7 disposition.**~~ — **DECIDED** (maintainer direction
  2026-08-10, PR #194): **PARKED as superseded**, with banners on both
  `PLAN_penalized_mi_surface.md` and `CONTINUATION_penalized_mi_surface.md` and every slice
  status changed from NEXT to PARKED so a selecting routine cannot resolve a superseded
  slice as the next work. **Still owed before that CONTINUATION's status may change from
  IN PROGRESS:** the refinement-backlog harvest into this file, and maintainer confirmation
  of the parking. *Source: PR #194 review [P1-1] (1st-order).*

### Harvested 2026-08-15 — first `ROUTINE_MGCV_PARITY.md` run, slice 1 partially built

- ~~**Finish slice 1: the R-side per-term extractor and its Python comparator.**~~
  **SHIPPED 2026-08-15b.** `scripts/gam_term_extract.R` + `gam_stage_a.py`, proven on the
  existing verified `raw`/`paraPen` basis (Anchor 1's "known-good basis first") — see the
  harvest entry below. mgcv-native extraction (`cr`/`ti`/`sz` via `smoothCon()`) is
  explicitly deferred to slice 2, where it belongs alongside the first Python basis that
  needs it.

- **The R-side per-term extractor should reuse `smoothCon()`, not fit a full `gam()`
  model per term.** This session's finding is what unblocks that choice: fitting a model
  just to read `predict(type="lpmatrix")` would force every isolated-term Stage-A case to
  be a well-posed regression (a response, real data), where `smoothCon()` needs only the
  covariate values and returns the same design. *Source: this session
  (1st-order — a design decision the extractor is built from, not carried in code that
  reviews it independently).*

### Harvested 2026-08-15b — second `ROUTINE_MGCV_PARITY.md` run, slice 1 finished

- **Slice 1 is DONE.** All of PLAN §3 slice 1's acceptance criteria are now met:
  term-spec dataclasses (prior session), the `smoothCon`/`lpmatrix` referent decided in
  writing (ADR-191, prior session), and — this session — the R-side per-term extractor
  (`scripts/gam_term_extract.R`) and Python comparator
  (`src/polaris_re/analytics/gam_stage_a.py`), proven exactly on the existing verified
  `raw`/`paraPen` basis at both tier 1 and tier 3 (CI run 31915145674). Caught and fixed
  one real bug in the R script's own harness proof (a JSON key not matching its label)
  before any tier-3 dispatch — exactly what proving the harness on a known-good basis
  first is for. `docs/CONTINUATION_mgcv_parity_engine.md` slice 1 marked DONE, slice 2
  marked NEXT. *Source: this session.*

- ~~**Next: slice 2 — `bs = "cr"`, with supplied and default knots.**~~ **CORRECTED
  2026-08-16 (see the harvest entry below).** The PR #197 review found the premise for
  deferring mgcv-native extraction to slice 2 doesn't hold — a slice 1b now sits between
  slice 1 and slice 2 and is the actual next work.

- **The pre-existing `data/mortality_tables` gap** (5 test failures — all one root
  cause, the gitignored generated CSVs absent in this fresh container — plus some golden
  QA-config skips) is unrelated to this epic and unaddressed here; it needs
  `scripts/convert_soa_tables.py` run against a network-reachable table source. *Source:
  this session's baseline check (2nd-order, NICE-TO-HAVE — orthogonal to the active
  epic, for whichever routine next needs those tables).* Confirmed by the PR #197 review
  in a container with the tables converted: all 5 failures and 22 skips disappear (3344
  passed / 0 failed, `tests/qa/` 94/94) — the diagnosis was right, still unaddressed.

### Harvested 2026-08-16 — PR #197 review, work order for slice 1b

**Headline for the maintainer:** slice 1 shipped only the `raw`-basis half of its own
scope; a review of PR #197 found the mgcv-native half was deferred to slice 2 on a premise
that doesn't hold, and raised a work order splitting it out as **slice 1b**, gating slice
2. Full spec: `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`.

- **Slice 1b — mgcv-native per-term extraction. NEXT, BLOCKER** (same standing blocker as
  the epic itself). The referent slice 1b needs already exists and is already tier-3-green
  from a *prior* slice — `scripts/smoothcon_lpmatrix_probe.R`, ADR-191, run 31907362222 —
  so this is packaging the existing per-term JSON schema through that referent
  (`smoothCon(..., absorb.cons=TRUE)`), not new verification work, and Anchor 8 does not
  block it. Scope: a `smoothCon` branch in `scripts/gam_term_extract.R` promoting the
  probe's own cross-check into the extractor's standing internal guard;
  `extract_smooth_terms()` on the Python side; `compare_term_extract` extended to compare
  `knots` (currently accepted, never compared — the tell that slice 1 was half a harness).
  One design question to settle in writing before slice 2: whether a term's coefficient
  index range is read from a fit or assigned when the harness assembles terms into a
  model (`first.para`/`last.para` are empty on a bare `smoothCon()` object). Full
  field-mapping table already measured (R 4.3.3 / mgcv 1.9.1) in the work order §3.
  *Source: PR #197 review, `docs/WORK_ORDER_slice_1b_mgcv_native_extraction.md`
  (1st-order — the epic's actual NEXT slice, ahead of the renumbered slice 2).*

- **Slice 1's own acceptance criterion was the root cause, not implementer judgement.**
  "Stage A runs green on the existing basis" is satisfiable by the `raw`-only path alone,
  since the existing basis is precisely the one with no `smoothCon` path. Corrected in
  `docs/PLAN_mgcv_parity_engine.md` to: *the extractor handles both a supplied basis and
  an mgcv-native basis, each cross-checked against the fitted model.* Worth carrying as a
  writing lesson for future slice criteria in this epic: "runs green on X" can be true
  while X was chosen to be the easy half. *Source: PR #197 review (1st-order — a process
  fix, not a code fix, but it changes what "done" means for every remaining slice here).*

- **All of #197's own P1/P2 findings were fixed in the same PR, not deferred to 1b**
  (`Any` → `RTermPayload` TypedDict; two mypy errors on new lines; `gam_term_extract.R`'s
  fixed λ now read from the manifest's `l1-interior` cell instead of a hardcoded value
  that could silently drift; `d3` added to both comparison sites; dtype added to 8 test
  fixtures; a job-summary table header's literal pipes fixed). Nothing outstanding from
  that review beyond the work order's own §§1-5 and 8-9. *Source: this session, commit
  `9154023`.*

### Harvested 2026-08-16 — third `ROUTINE_MGCV_PARITY.md` run, slice 1b shipped

- ~~**Slice 1b — mgcv-native per-term extraction.**~~ **SHIPPED 2026-08-16.** A
  `smoothCon` branch (`extract_smooth_one`) in `scripts/gam_term_extract.R`, emitting
  the existing per-term schema for three isolated `bs="cr"` cases with its own
  internal consistency guard (promoted from `smoothcon_lpmatrix_probe.R`'s diagnostic
  into a standing check); `extract_smooth_terms()` and a `knots` comparison in
  `gam_stage_a.py`. Tier 1 confirmed (`docs/CONFORMANCE_LEDGER.md`); tier-3 dispatched
  with this PR. Unblocks slice 2. *Source: this session.*

- **The index-range design question is settled as ADR-192.** A term's coefficient
  index range is assigned by whichever side assembles the term into a model, never
  read off a fit — the `raw` path already did this (`DesignExport.n_tensor`/`n_coef`,
  not `m$first.para`/`last.para`), and slice 1b makes it explicit for the isolated
  mgcv-native case: the model a one-term Stage-A case assembles *is* that term, so its
  range is `[0, width)`. Recorded now, before a multi-term model exists to get it
  wrong for later. *Source: this session, ADR-192 (1st-order — a data-contract
  decision every later slice built on `TermExtract` inherits).*

- **The harness caught a real bug on its first run, not a rediscovered one** — jsonlite's
  `auto_unbox` silently collapsed a single-element `rank` vector to a bare JSON scalar
  wherever a term carries exactly one penalty, which the `raw` path's two-penalty tensor
  term never exercised. `TypeError: 'int' object is not iterable` on the Python side, not
  a silent wrong answer — but worth flagging for slice 2 and later: **any R-side field that
  can be length-1 needs `I()` to survive `auto_unbox`**, and `S`/`X` are already
  list-wrapped so only scalar-shaped fields (`rank`, and potentially per-term scalars in
  later slices) are at risk. *Source: this session (2nd-order, NICE-TO-HAVE — a
  documented gotcha for whoever writes the next R-side branch, not a design question).*

- **Next: slice 2 — `bs = "cr"`, with supplied and default knots.** Now genuinely
  unblocked — the mgcv-native Stage-A extractor slice 2 needs to check its basis
  against is built and tier-1-confirmed. *Source: this session,
  `docs/PLAN_mgcv_parity_engine.md` / `docs/CONTINUATION_mgcv_parity_engine.md`
  (1st-order — the epic's own NEXT slice).*

### Harvested 2026-08-16b — verification provenance (PR #199 review follow-up)

- **The verification-provenance standard, shipped.** ADR-193 +
  `docs/VERIFICATION_STANDARD.md` + `polaris_re.core.verification`: a comparison is
  parity evidence only when two independent producers computed the compared quantity.
  Provenance is declared in the type by the producer (no default), report headlines are
  derived from the declaration rather than hand-written, and `require_parity_evidence`
  gates any asserted parity claim. Both Stage-A paths now declare honestly — slice 1's
  `X`/`S` as ECHO, slice 1b's columns as TRANSPORT — and the CI job summary says so
  above the zeros. *Source: PR #199 review, maintainer direction (1st-order — a
  project-wide verification contract every future comparison inherits).*

- ~~**Slice 2 must be the epic's first Stage-A parity slice.**~~ **RESCOPED
  2026-08-16.** Its acceptance criteria in `docs/PLAN_mgcv_parity_engine.md` now name
  the provenance they require (INDEPENDENT on `design_X`/`penalty_S`), so a harness
  result cannot tick them, and the mechanical test is written into the criteria: the
  Python producer takes no R payload as an input. *Source: this session, ADR-193
  (1st-order — the epic's own NEXT slice).*

- **The routine prompts need their remaining edits.**
  `docs/ROUTINE_CHANGES_2026-08-16_verification_provenance.md` carries all seven
  verbatim with a status table. Applied 2026-08-16: the PR-review provenance audit,
  PR-review goldens-are-not-correctness, and the mgcv-parity provenance gate.
  Outstanding, all daily dev: the comparisons-against-a-reference step,
  provenance-named acceptance criteria, producers named on recorded comparisons, and
  the epic-ownership exclusion. The prompts live in the trigger configuration outside
  this repo, so the human who owns those triggers must apply them — the repo half is
  done. *Source: this session (1st-order — without the routine edits the standard
  binds code but not the sessions that write it).*

- **Retro-classifying the historical conformance-ledger rows.** ADR-193 declared it out
  of scope, and the PR #200 review asked where it went. The preamble of
  `docs/CONFORMANCE_LEDGER.md` now names the existing rows and their kind (the four
  slice-1 rows ECHO with `rank` independent; the two slice-1b rows TRANSPORT), which
  makes the caveat attach to identified artefacts rather than to "earlier rows". A
  per-row `CONFIRMED (harness)` marker is still unwritten and would need an
  append-only-safe convention first. *Source: PR #200 review [P1]/[P2] (2nd-order,
  NICE-TO-HAVE — a follow-up of ADR-193, which was itself the #199 review's follow-up).*

- **The `mgcv` epic's bases have no independent evidence yet; its fitter does.**
  Conformance levels 1-5 compare two independently implemented fitters over a shared
  `(X, S)`, which is why level 4 can genuinely disagree (ADR-190). §5 of the standard
  carries the full audit. Worth re-reading before any claim about what the epic has
  proven. *Source: this session (2nd-order, NICE-TO-HAVE — a documented statement of
  current evidence, not a work item).*

### Harvested 2026-08-17 — slice 2, the epic's first Stage-A basis parity (ADR-194)

- ~~**The `mgcv` epic's bases have no independent evidence yet.**~~ **PARTIALLY
  RESOLVED 2026-08-17.** The `cr` basis now does: `gam_basis_cr.py` reproduces
  `mgcv::smoothCon(bs="cr", absorb.cons=TRUE)` to float round-trip precision on 5
  cases, including the target formula's own `AttdAge`(k=13)/`PolYear`(k=6) knot
  vectors, confirmed at both tier 1 and tier 3 (CI run 32033738454). `design_X`,
  `penalty_S` and `rank` are `INDEPENDENT` (`CR_BASIS_CLAIM`) — the first table in
  `docs/CONFORMANCE_LEDGER.md` entitled to `CONFIRMED (parity)`. (`knots` agreement
  is also checked and also agrees on all 5 cases, but — PR #201 review [P1],
  corrected same-day — is reported separately rather than folded into the claim,
  since it is ECHO, not INDEPENDENT, in the 3 supplied-knot cases.) `ti` and `sz`
  (slices 5-6) remain unbuilt. *Source: this session, ADR-194 (1st-order — the
  epic's own next-slice progress).*

- **Extrapolation beyond the knot range is unverified in the Python `cr` basis.**
  All 5 of slice 2's cases draw `x` from inside `[knots[0], knots[-1]]` by
  construction; what `mgcv` does outside that range was never measured, and the
  natural boundary condition does not by itself imply the per-interval Hermite
  formula reduces to linear extrapolation there. This foreseeably blocks a specific
  future use: the target formula's own `AttdAge`/`PolYear` knots fit against real
  experience data, where the data range need not equal the hand-chosen knot range.
  *Source: this session, `gam_basis_cr.py` module docstring (1st-order — blocks a
  named future use, not a hypothetical).*

- **Slice 3 — families, links and weights.** Now genuinely unblocked (depended on
  slice 1, independent of slice 2). Binomial `cloglog`/`logit`, quasi-Poisson with
  `φ` estimated, Poisson with a log offset. *Source: `docs/PLAN_mgcv_parity_engine.md`
  (1st-order — the epic's own NEXT slice).*

- **The `continue-on-error` job-summary-artifact limitation likely affects the
  ADR-190 and ADR-191 diagnostic probes too**, not only the per-term comparison step
  fixed this session. Those steps' tier-3 confirmations rest on the same "the step
  didn't except" reading slice 1b's row did, for the same reason (job-summary
  artifact behind a blocked blob-storage host). The fix — `print()` the report to
  stdout alongside the file write — is a few lines per step if a future session
  needs to re-read one of those probes' actual numbers rather than their pass/fail.
  *Source: this session (2nd-order, NICE-TO-HAVE — a known gap with a known cheap
  fix, not urgent since neither probe is currently blocking anything).*

### Harvested 2026-08-17 — slice 3, the epic's first Stage-B parity outside Poisson (ADR-195)

- ~~**Slice 3 — families, links and weights.** Now genuinely unblocked.~~
  **DONE 2026-08-17.** `gam_family.py` (`Family`/`Link` abstraction, standard GLM
  IRLS theory — no R-source archaeology needed, unlike the `cr` basis) and
  `gam_fit.py` (`penalized_irls_general`, proven to reduce to the already-verified
  Poisson recursion bit-for-bit before any R round trip was spent) reproduce `mgcv`
  across binomial logit/cloglog with prior weights, quasi-Poisson with an
  estimated dispersion, and Poisson with a log offset — all four confirmed at tier
  3 (CI run 32057694949) to float round-trip precision on the **first**
  measurement, no iteration needed. `FAMILY_CLAIM` declares `eta`/`dispersion`
  `INDEPENDENT`; coefficients are never compared (Anchor 2). *Source: this
  session, ADR-195 (1st-order — the epic's own next-slice progress).*

- **`binomial`/`cloglog`'s non-canonical-link concavity gap is recorded, not
  resolved.** ADR-189 decision 1's "shared `(X,S)` ⇒ strictly concave ⇒ every
  disagreement is arithmetic" argument holds unconditionally only for a canonical
  link; `cloglog` is not canonical for the binomial family, so a future
  harder-conditioned `cloglog` case could genuinely disagree where `logit` would
  not, and that would be a real result rather than a bug in slice 3. Nothing to
  fix today — the module docstring already marks it — but worth remembering
  before treating a future `cloglog` disagreement as a regression. *Source: this
  session, ADR-195 decision 3 (2nd-order, NICE-TO-HAVE — a documented caveat, not
  a work item, unless a future slice's measurement actually hits it).*

- **Anchor 5's absolute-vs-relative idiom is not yet demonstrated end to end on
  the target's own term structure.** Slice 3 built and verified the general IRLS
  core on a dedicated small shared design (one design, four family/link/weight
  combinations) — it did not run the "weights AND an offset simultaneously"
  relative idiom against real term structure, only each control in isolation at
  the R-probe level (both together are unit-tested in
  `test_gam_family.py::TestWeightsAreNotAnOffset`, which is Python
  self-consistency, not an mgcv comparison). Demonstrating the distinction
  end-to-end on the target formula needs a multi-term model, which needs slice 4's
  optimiser first. *Source: `docs/PLAN_mgcv_parity_engine.md` slice 3's own
  acceptance criteria (1st-order — a named, not-yet-met piece of the slice's own
  scope, correctly deferred rather than silently dropped).*

- ~~**Slice 4 — the outer optimisation (N-dimensional (f)REML).** Now the epic's
  NEXT slice — the prerequisite for everything multi-term, and the largest single
  piece of work in the epic (PLAN §3: 4.8 million grid fits would be needed at the
  target's 13-21 smoothing parameters if the existing 2-D grid approach were
  naively extended, which is why it is a Newton/quasi-Newton slice instead).~~
  **PARTIALLY SHIPPED, 2026-08-18** — see the harvest immediately below for what
  moved and what is still open. *Source: `docs/PLAN_mgcv_parity_engine.md`,
  updated by this session's harvest (1st-order — the epic's own in-progress
  slice).*

### Harvested 2026-08-18 — slice 4 part A, the REML score generalized and measured (ADR-196)

- **PART A DONE, PART B NOT STARTED.** The generalized score
  (`gam_reml.reml_score_general`) is built and measured against `mgcv` before any
  search code exists — the right order, since a search over a criterion not shown
  to match would not be a meaningful measurement. It DISAGREES: an INDEPENDENT
  comparison (score computed two ways from a shared recipe, never reading the
  other side's fit or score) where **all three** pairwise score-difference
  residuals miss the declared 1e-6 tolerance (two by ~0.74, one by ~9.3e-4 —
  ~935x the tolerance, smaller than the other two but not agreement), identical
  at tier 1 and tier 3 — five orders of magnitude above BLAS/version noise, so
  this is a real formula gap, not an artifact. A second INDEPENDENT quantity,
  `deviance`, agrees at every point (~1e-11), which is what rules out the fit
  itself (or a rescaled-penalty artifact) as the cause. *Source: this session,
  ADR-196 (1st-order — the epic's own in-progress slice; the outer search cannot
  proceed meaningfully until this is closed).*

- ~~**Named next hypothesis for slice 4 part B's formula gap, corrected same-day
  (PR #203 review [P1-3]).**~~ **SUPERSEDED SAME DAY — see the harvest entry
  immediately below.** The corrected next step named here (build a fixture with
  overlapping penalty blocks, read Wood 2011's multi-penalty treatment) turned
  out not to be needed: the maintainer supplied the paper directly, and the
  actual missing term was in §2's criterion definition, not §3.1's
  multi-penalty machinery this entry pointed at. Kept, struck, for the audit
  trail — the reasoning that let the gap go unclosed for one more round (the
  session was looking at the right paper's wrong section) is itself informative.

### Harvested 2026-08-18b — slice 4 part A RESOLVED: the missing penalized-deviance term (ADR-196 resolution)

- **RESOLVED, same day as the characterization above.** The maintainer downloaded
  Wood (2011) directly (after some difficulty locating a free copy — resolved via
  the University of Bath research portal, not the paywalled DOI) and asked where
  in it the multi-penalty formula lived. §2 (p.4), equation (4), names the
  criterion's first term as the PENALIZED deviance,
  `Dp = D(beta_hat) + beta_hat^T S beta_hat` — a term
  `gam_reml.reml_score_general`'s first generalization omitted entirely, having
  copied the plain-deviance formula verbatim from
  `experience_gam_penalized.reml_score`. Adding the missing term closed the
  pairwise-score-difference gap to float round-trip precision (~1e-12) on all
  three tested points, tier 1 and tier 3 identical (CI run 32142352655).
  `REML_SCORE_CLAIM`'s two INDEPENDENT quantities both now agree — the epic's
  first Stage-C parity result. §3.1's multi-penalty numerical-stability machinery
  (the previous entry's "next hypothesis") turned out to be inapplicable to this
  fixture for a well-grounded reason (disjoint-support penalty blocks cannot
  suffer the cross-block "zero leakage" §3.1 addresses), not merely coincidental
  — closing that question too. *Source: this session, ADR-196 resolution
  (1st-order — closes the epic's own critical-path item).*

- **The identical omission is suspected, not yet confirmed, in the ALREADY-SHIPPED
  `experience_gam_penalized.reml_score`** — the formula the tensor MI surface's
  production 2-D grid selector (`select_lambdas_reml`) actually uses. Same formula
  shape, same omission by inspection. ADR-189 amendment 1's own "unexplained
  residual of 0.93-3.17" against `mgcv`'s raw score (recorded, explicitly marked
  "not a compared metric" at the time) is consistent in order of magnitude with
  this same missing term, but that is motivation for measurement, not a
  substitute for it. PLAN Anchor 7 protects that module from being touched by
  this epic without explicit, separate maintainer sign-off — the goldens were
  fitted with its current formula. Scoped as
  `docs/WORK_ORDER_reml_penalized_deviance_production_check.md`. *Source: this
  session, maintainer direction 2026-08-18 (1st-order — assigned as the epic's
  own next `ROUTINE_MGCV_PARITY.md` session, ahead of slice 4 part B).*

- **Slice 4 part B (the N-dimensional outer search) remains NOT STARTED,
  deliberately** — now unblocked in principle by the Python-side fix, but
  sequenced behind the work order above per maintainer direction, since building
  the search on a criterion whose production analogue's status is still a
  hypothesis would be premature. *Source: this session (1st-order — the epic's
  own next-but-one step).*

### Harvested 2026-08-18c — the production REML-score work order run (measured, tier 1 AND tier 3)

- **The suspected omission is CONFIRMED, and its actuarial impact is now
  measured, not just suspected.** `docs/WORK_ORDER_reml_penalized_deviance_production_check.md`
  ran end to end: §3.1 evaluated the SAME already-fitted `(design, coef,
  penalty)` each free-sp cell of the ten-cell conformance fixture already
  carries, scored two ways, against `mgcv`'s own `m$gcv.ubre` — offset-adjusted
  per ADR-189 amendment 1's own convention, the residual does NOT collapse (it
  roughly doubles, since the two sides select DIFFERENT lambda at a free-sp
  cell — a mismatched-point limitation named in the work order itself, not a
  refutation of the bug). §3.2, the harder and more consequential question, is
  where the registered prediction actually gets tested: re-scoring the SAME
  2-D grid search with the corrected criterion selects a point measurably
  CLOSER to `mgcv`'s own free-sp selection on **all three** free-sp cells
  (log10 distance to `mgcv`'s selection: 0.3149→0.0663, 0.1870→0.1097,
  0.4559→0.1248) — the prediction HELD, not assumed. On `l2-free-sp` the
  corrected grid search independently reproduces the exact grid-step move
  (3162.28→5623.41, `λ_year` unchanged) the maintainer's own earlier local
  patch-and-refit experiment found (§2 of the work order) — a second,
  independent confirmation of that number. §3.3: the correction shifts
  `smoothing_uncertainty`'s finite-difference Hessian eigenvalues materially
  (~25-40%), and the resulting Kass-Steffey inflation ratio moves in the
  right direction but only slightly (e.g. `l2-free-sp` 1.1109x → 1.1538x
  against `mgcv`'s 1.7392x) — nowhere near closing ADR-190's already-
  characterized, separately-derived 3-4x under-inflation gap. Tier 1 (R 4.3.3
  / mgcv 1.9.1, local apt) and tier 3 (R 4.6.1 / mgcv 1.9.4, oracle
  `sha256:0d54c192…`, CI run 32181109927) agree to every printed digit.
  ADR-197 and `docs/CONFORMANCE_LEDGER.md` carry the full measurement.
  *Source: this session (1st-order — closes the gating item ahead of slice 4
  part B).*

- **RESOLVED, 2026-08-19.** The maintainer explicitly authorized the
  recommendation above: "Proceed to fix `experience_gam_penalized.reml_score`
  the same way ADR-196 fixed `gam_reml.reml_score_general` (add the missing
  term)." Applied verbatim (same Wood (2011) §2 eq. (4) pattern, same
  citation style). `data/mgcv_exchange/synthetic/python_reference.json`
  re-baselined via its own regeneration path (`export_mgcv_case.py`, not
  hand-edited) — the delta matches §3.2's registered prediction to the
  printed digit on all three named free-sp cells, plus `l5-gamma` (same
  mechanism, not one of the three originally named). The full ten-cell `mgcv`
  conformance suite re-run against the fixed module: required levels 1-3
  still AGREE (no regression), and level 5 (Wood's `gamma`) moves from
  DISAGREES to AGREES — an improvement beyond what §3.2 alone measured. Level
  4 (Kass-Steffey covariance) is unchanged in kind — ADR-190's separate,
  already-tracked `dw/drho` gap, confirmed not a material contributor to it
  by §3.3, unaffected here. `tests/qa/golden_outputs/` reconfirmed
  byte-identical after the actual fix. Full measurement, both tiers, in
  ADR-197's 2026-08-19 resolution amendment (`docs/DECISIONS.md`) and
  `docs/CONFORMANCE_LEDGER.md`. *Source: this session (1st-order — closes the
  maintainer-gated follow-up from 2026-08-18c).*

- **Slice 4 part B (the N-dimensional outer search) remains unblocked to
  proceed** — the work order's gate was already satisfied before this
  session; now the production 2-D grid selector agrees with the search's own
  criterion (`gam_reml.reml_score_general`) too, rather than being two steps
  removed from it. *Source: this session (1st-order — the epic's own next
  slice).*

### Harvested 2026-08-19b — PR #204 round-2 review (age-axis `V_rho` follow-up)

- **Restore an age-axis `V_rho` sanity check on a fixture where the age
  margin actually carries signal.** ADR-197's production fix moved
  `test_the_smoothing_variance_matches_the_measured_lambda_spread`'s own
  selection to the search bound on the age axis (`lambda_age = 10**8`,
  `_quadratic_mi`'s truth is quadratic in year and CONSTANT in age — the age
  margin is genuinely null there), so the test's age-axis comparison against
  ADR-187's empirical λ-spread was retired as not meaningful on THIS fixture
  (a boundary optimum has zero-or-negative curvature by construction — not a
  bug, and not something `LAMBDA_LOG10_BOUNDS` should be touched to avoid).
  That is a small, well-documented, legitimate reduction in coverage — but
  it was never harvested as a follow-up, so the gap has lived only in the
  test's own docstring. Restore an equivalent age-axis `V_rho` check on a
  fixture whose age margin is NOT null (an age-varying truth, so an interior
  age-axis optimum exists to compare against a measured empirical spread),
  so the coverage this test used to carry on the age axis is not simply
  gone. *Source: PR #204 round-2 review [P2] (1st-order).*

### Harvested 2026-08-22 — slice 4 part B's first slice: the continuous search confirms ADR-198 (ADR-199)

- **PART B'S FIRST SLICE DONE — ADR-198's registered decisive test ran and HOLDS, tier 1
  AND tier 3 both confirmed.** `gam_reml_optimize.select_lambdas_continuous` — a
  Newton/quasi-Newton search (SciPy L-BFGS-B) over `log10(lambda)` for any number of
  independently-scaled penalty blocks and any known-scale family, built entirely on the
  already-verified `gam_fit.penalized_irls_general`/`gam_reml.reml_score_general` (no
  new fitting or scoring formula). On the same four free-sp cells ADR-198 measured
  post-fix, `max_abs_log10_sp_diff` against `mgcv`'s own free-sp selection collapses
  from the production grid's 0.0645/0.0791/0.1048/0.0776 to (tier 3, CI run
  32544930172, oracle `sha256:0d54c192…` build 8) 6.9e-04/5.1e-05/1.7e-04/9.8e-04 — 2-3
  orders of magnitude, landing at the search's own convergence tolerance rather than
  anywhere near 0.1, identical in verdict to the tier-1 reading. This settles ADR-198's
  open question decisively: the residual ADR-197's fix left behind was grid
  quantisation, not a remaining criterion difference. `CONTINUOUS_LAMBDA_CLAIM` declares
  both compared quantities INDEPENDENT (ADR-193). `experience_gam_penalized.
  select_lambdas_reml` and every other production entry point are untouched (PLAN
  Anchor 7) — this is a second, separate search, not a replacement (ADR-198 "Two
  searches, not one"). Required levels 1-3 of the ten-cell suite also still agree on
  the confirming CI run — no regression. *Source: this session, ADR-199 (1st-order —
  the epic's own active slice).*

- **Not yet exercised above N=2.** `select_lambdas_continuous` accepts any number of
  penalty blocks by construction, but the only fixture available to test against is the
  ten-cell suite's existing 2-block designs (`d1`/`d2`/`d3`). Extending to the target
  formula's 13-21 blocks needs a multi-term mgcv-native model, which is slice 5 onward's
  own scope — nothing in this session's module needs revisiting once that model exists.
  *Source: this session (2nd-order — a named, not-yet-met piece of the search's eventual
  target, correctly deferred rather than silently dropped).*

### Harvested 2026-08-22b — slice 5's MI term: the numeric-`by` `cr` basis (ADR-200)

- **THE MI TERM'S OWN BASIS IS DONE (Stage A), tier 1 AND tier 3 both confirmed and
  identical to the printed digit.** `s(AttdAge, by = StudyYear_C)` is the actual point of
  the target formula (PLAN §3: "the cheap one and the important one" — 13 coefficients
  saying log-hazard is linear in calendar year with an age-varying slope), and slice 5's
  own instruction was to ship it before `ti()` if they split. It agrees with
  `mgcv::smoothCon(s(x, by=z, bs="cr", k), absorb.cons=TRUE)` at `max_X_diff=2.176e-14`,
  `max_S_diff=3.775e-15`, `rank_diff=(0,)` — same order as slice 2's other five `cr`
  cases, on the first measurement, no iteration needed. Carries its own
  `CR_BY_BASIS_CLAIM` (ADR-193; split out from `CR_BASIS_CLAIM` after PR #206 review
  [P1] — same quantities, different producer strings):
  `design_X`/`penalty_S`/`rank` are INDEPENDENT, so this is genuine Stage-A
  basis parity, not a harness check. Tier 3: CI run 32571764900, oracle
  `sha256:0d54c192…` build 8; required levels 1-3 of the ten-cell suite also still agree
  — no regression. *Source: this session, ADR-200 (1st-order — the epic's own active
  slice).*

- **The construction fact worth carrying forward: `mgcv` absorbs NO identifiability
  constraint on a numeric-`by` smooth.** Measured by direct R probe before any code was
  written (Anchor 8, CLAUDE.md's "do not guess at a derivation"): the by-case's
  `smoothCon(..., absorb.cons=TRUE)$C` has **zero rows**, unlike a plain smooth's
  `colMeans(X)` row. So the by-term's design is the *unconstrained* `k`-column basis with
  each row scaled by the by-variable — `k` columns, not `k-1` — and its penalty is that
  same unconstrained `S`, untouched by the scaling. Anyone extending to `ti()` or `sz`
  should expect their own constraint treatment to be a separate measured question, not
  inherited from either the plain or the `by` case. *Source: this session, ADR-200
  decision 1 (1st-order — a construction fact later slices build on).*

- **Nothing gates on the Stage-A `cr` comparison, and that is pre-existing — slice 2's
  design, not slice 5's.** Surfaced by PR #206's review in its own second pass, after it
  corrected an earlier mis-statement of the same area. The facts, verified directly:
  `mgcv-conformance.yml` DOES run automatically on any PR touching `gam_basis_cr.py`,
  `gam_stage_a.py` or `gam_term_extract.R` (a path-filtered `pull_request:` trigger), so
  the comparison is not merely a manual dispatch — but the step is
  `continue-on-error: true` and its `any_cr_disagree` flag only inserts an annotation
  into the report, never exits non-zero. The workflow's actual merge gate is levels 1-3
  of the ten-cell suite, which never calls `build_python_cr_term`. **So a genuine
  Stage-A basis disagreement would leave every check on a PR green**, visible only as
  text inside a job summary — the same masked-`continue-on-error` failure mode the
  workflow's own comments warn about twice, and which ADR-194's print-to-stdout fix
  addressed for *reading* numbers without addressing *gating* on them. Not actioned in
  PR #206: the review explicitly framed the ask as the cheap half (R-free unit tests in
  the gating pytest job, now added) rather than a workflow change, and re-pointing the
  gate is a decision about the epic's verification posture that deserves its own
  session. *Source: PR #206 review second pass, verified independently (2nd-order,
  NICE-TO-HAVE — a real hole in the safety net, but one that has been open since slice 2
  and blocks nothing today).*

- **Slice 5 is IN PROGRESS, not DONE, and the remaining half has a named shared
  prerequisite.** `ti(AttdAge, PolYear)` — tensor interaction with marginal main effects
  excluded — is unstarted and is a materially different construction. Separately, this
  session's result is **Stage A only**: no multi-term mgcv-native model exists, so nothing
  has run Anchor 2's own acceptance criteria (the MI contrast, `η`) on this term. That
  same missing model is the prerequisite for three currently-open items — slice 5's
  Stage-B half, slice 4 part B's extension above N=2 (ADR-199's own named limitation), and
  Anchor 5's absolute/relative end-to-end demonstration — which makes building it the
  epic's highest-leverage next piece of work rather than one slice's internal detail.
  *Source: this session (1st-order — names the epic's actual next bottleneck).*

### Harvested 2026-08-22c — level 4's prerequisite is built from Wood (2011) (ADR-201)

- **`dw/drho` EXISTS AND IS TIER-3 VERIFIED — the ingredient ADR-190 named as
  missing.** ADR-190 decision 2 stated the level-4 blocker as *"it needs `dw/drho`,
  which nothing in the fitter currently computes."* `gam_derivatives` now computes
  it, from Wood (2011) §3.4 (`dbeta/drho`, `d(eta)/drho`) and Appendix D (`dw/deta`
  and the chain rule). Against `mgcv`'s own refits central-differenced at perturbed
  `sp`: `d(eta)/drho` agrees to 5.3–5.8e-11 on all three cells with a Richardson
  ratio of **4.00**, which is what establishes it as the `h -> 0` limit of `mgcv`'s
  behaviour rather than merely close at one step. `DERIVATIVE_CLAIM` declares both
  compared quantities INDEPENDENT. Tier 3, CI run 32586279901, oracle
  `sha256:0d54c192…` build 8. *Source: this session, ADR-201 (1st-order — the
  epic's oldest open blocker's critical path).*

- **LEVEL 4 IS NOT CLOSED, AND THE PAPER SUPPLIED WAS NOT THE ONE IT NEEDS.** The
  maintainer supplied Wood (2011) *JRSS-B* 73(1) — the same paper that resolved
  ADR-196 — rather than Wood, Pya & Säfken (2016) *JASA*, which is what ADR-190
  decision 1 names for `vcov(unconditional=TRUE)`. Wood (2011) contains `dw/drho`
  in full but **no unconditional-covariance formula at all** (searched: zero
  occurrences of "unconditional"); it derives those derivatives because the REML
  Newton iteration needs them. **What is still outstanding is only the assembly** —
  how `dw/drho` enters `Vc` — and per ADR-190 decision 3 it must be re-derived from
  the 2016 paper, never read off `mgcv`'s GPL source. *Source: this session
  (1st-order — names precisely what is still needed, so the next request is for the
  right artefact).*

- **The derivative needs the OBSERVED (Newton) Hessian, not the fitter's Fisher
  weights — worth ~5 orders of magnitude, and any `Vc` work inherits it.** Fisher
  scoring and Newton reach the same `beta-hat` but not the same derivative, because
  `dbeta/drho` depends on the Hessian *at* the stationary point. Registered as a
  prediction before measuring and it held: with Fisher weights the non-canonical
  cell (`binomial-cloglog`) is wrong by 6.9e-06 against ~1e-11 on the canonical
  ones; supplying the observed-Hessian weights closes it to 1.1e-11. `max|alpha-1|`
  is 6.7e-16 / 0.0 / 4.3e-03 across the three cells, independently confirming
  Wood §3.2's algebra since nothing in the implementation forces `alpha = 1` on a
  canonical link. **The fitter is untouched** (Anchor 7). *Source: this session,
  ADR-201 decision 1 (1st-order — a correctness fact the level-4 slice depends on).*

- **A convergence diagnostic that did not say what it claimed, caught and fixed.**
  The probe first reported one `h` regime with a Richardson ratio of ~0.6 while the
  column header said "want ~4". At `h <= 1e-4` the residual is round-off limited —
  differencing two separately-converged `mgcv` fits has its own floor — so halving
  `h` makes the *reference* worse and the ratio says nothing about convergence.
  Publishing it would have been a convergence claim the number did not support. The
  probe now brackets both regimes and labels which is which. *Source: this session
  (2nd-order — a methodology fix for any future finite-difference comparison in
  this epic, of which there will be more).*

### Harvested 2026-08-22d — LEVEL 4 CLOSED (ADR-202)

- **THE EPIC'S OLDEST BLOCKER IS CLOSED, tier 1 and tier 3 identical.** Standing since
  ADR-188 and re-scoped by ADR-190, level 4 was: ours inflates 1.11-1.21x where `mgcv`
  inflates 1.49-1.87x. With Wood, Pya & Säfken (2016) eq. (7), `gam_uncertainty` now
  reproduces `mgcv`'s `vcov(unconditional=TRUE)` to **<1% element-wise** (0.023%,
  0.150%, 0.904%) and **<0.1% on the inflation ratio**, on three committed cases plus
  five held-out ones including a non-canonical `cloglog`. CI run 32589501512, oracle
  `sha256:0d54c192…` build 8. *Source: this session, ADR-202 (1st-order — closes the
  standing BLOCKER).*

- **Three unknowns had to be identified, and all three were measured rather than
  chosen.** (a) `Vrho`'s regularisation is a ridge of exactly **0.1**, identified
  against `mgcv`'s own `m$V.sp` to 1.78e-15 — the paper names the mechanism ("a
  Gaussian prior on rho") but not the value. (b) **`V''` is not invariant to the choice
  of square root**; the factor is Wood (2011) §3.3's lower-triangular `L^-1`, not a
  Cholesky of `V_beta`. (c) The two terms use **different inverses** of the rho
  Hessian — `V'` the unregularised, `V''` the ridged. (c) was found by localisation:
  the leftover residual was rank-1, aligned `|cos|=0.9994` with `J[1]`, and its
  best-fitting coefficient (3210) matched the unregularised `H^-1[1,1]` (3184) to ~1%.
  *Source: this session, ADR-202 decision 1 (1st-order — facts any future covariance
  work depends on).*

- **ELEMENT-WISE IS THE GATE, NOT THE INFLATION RATIO — a lesson for the whole epic.**
  Mid-slice the scalar inflation ratio read 0.39% while the element-wise residual was
  26.7%: averaging diagonals hid a real structural disagreement behind a green
  headline. The probe now exports full `Vc`/`Vp` matrices and the comparator gates on
  the element-wise number. Any remaining conformance comparison that reports only a
  scalar summary is exposed to the same failure. *Source: this session (1st-order — a
  methodology fix with scope beyond this slice).*

- **WHAT IS STILL OPEN, AND IT IS NOT THE FORMULA.** The ten-cell suite's level 4
  still reads DISAGREES on the very run that confirms the fix — correctly, because it
  exercises the SHIPPED `experience_gam_penalized.smoothing_uncertainty`, untouched
  (Anchor 7). Three follow-ons: **(1)** re-pointing production at `gam_uncertainty`,
  needing Anchor 7 sign-off and its own determinism answer (ADR-186 chose the grid for
  reproducibility by construction); **(2)** re-running ADR-188's coverage gate, which
  ADR-190 decision 4 predicted in advance would move toward the 0.9192 floor — a
  registered prediction now testable and **still unrun**; **(3)** labelling any
  interval a 95% band, which stays maintainer-reserved either way. *Source: this
  session (1st-order — the decision the maintainer now actually has in front of them).*

- **A residual of 0.07-0.73% element-wise remains and is not float noise.** Eq. (7) is
  a first-order Taylor expansion whose remainder the paper drops, so exact agreement
  is not available in principle. Recorded rather than explained away; the 2% tolerance
  is set from the observed spread with under 3x headroom. *Source: this session
  (2nd-order — a documented limit of the formula, not a defect).*

### Harvested 2026-08-24 — slice 5's `ti()` tensor interaction (ADR-205)

- **`ti(AttdAge, PolYear)` IS DONE (Stage A), tier 1 AND tier 3 both confirmed.**
  Tensor interaction with the marginal main effects excluded — slice 5's other named
  piece, alongside the MI term's numeric-`by` basis (ADR-200, done 2026-08-22). Agrees
  with `mgcv::smoothCon(ti(x1, x2, bs="cr", k=(k1,k2)), absorb.cons=TRUE)` at
  `max_X_diff≈1.5e-14`, `max_S_diff≈3-5e-14` on both penalty blocks, `rank_diff=(0,0)`,
  on a synthetic case and the target formula's own `ti(AttdAge, PolYear, k=c(13,6))`
  knots — the harder case agreeing to the printed digit at both tiers. `TI_BASIS_CLAIM`
  declares `design_X`/`penalty_S`/`rank` (both blocks) INDEPENDENT: genuine Stage-A
  basis parity, the epic's second (after ADR-194's `cr` basis) and its first for a
  two-margin term. Tier 3: CI run 32677470292, oracle `sha256:0d54c192…` build 8;
  required levels 1-3 of the ten-cell suite also still agree — no regression. *Source:
  this session, ADR-205 (1st-order — the epic's own active slice).*

- **The construction needed instrumenting `mgcv`'s running C-backed constructor, not
  just reading its R source.** `mgcv::ti`'s own `np=TRUE` default names an SVD-based
  per-margin reparameterization in its formal argument list, and a literal reading of
  `smooth.construct.tensor.smooth.spec` suggests it always runs. A first hand-replica
  that applied it disagreed with `smoothCon()` by up to 182 in absolute value on `X`.
  `assignInNamespace`-installing a modified copy of the constructor that `assign()`s its
  own internal locals to the global environment mid-execution found the actual gate:
  `smooth.construct.cr.smooth.spec` sets `object$noterp <- TRUE` on every `cr` margin,
  and the tensor constructor's reparam loop is `if (is.null(margin$noterp)) {reparam}
  else XP[[i]] <- NULL` — false for `cr`, so the step is a no-op for an all-`cr` tensor.
  A second instrumented pass found a further gap after `X` agreed exactly but `S`
  disagreed by a constant ratio per block (8.06x on one case): `smoothCon()`'s own
  `scale.penalty` rescaling — already known from the plain `cr` basis (ADR-194) — fires
  **twice** for a tensor smooth, once per margin (inside each margin's own `smoothCon`
  call) and once more over the assembled tensor `X`/`S` (the tensor product is itself a
  `smoothCon()` return value). Anchor 8's "derive, don't guess" held even after a first
  derivation attempt failed — the fix was to measure harder, not to fall back to fitting
  a constant. *Source: this session, ADR-205 decision 1 (1st-order — a construction
  fact and a methodology note later `te()`/`sz` work should expect to need the same
  instrumentation discipline for).*

- **Slice 5 is IN PROGRESS, not DONE — both Stage-A pieces are now shipped, and the
  remaining half is the same named shared prerequisite ADR-200's harvest already
  flagged: a multi-term mgcv-native model.** Nothing has yet run Anchor 2's own
  acceptance criteria (the MI contrast, `η`) on either the `by` term or `ti()`, because
  no fitted model exercises them together. That same missing model still gates slice 5's
  Stage-B half, slice 4 part B's extension above N=2, and Anchor 5's absolute/relative
  end-to-end demonstration — unchanged from ADR-200's assessment, now with both of
  slice 5's Stage-A halves actually in hand to build it against. *Source: this session
  (1st-order — confirms the epic's next bottleneck is unchanged and is now the only
  thing between here and Stage B on two already-verified bases).*

### Harvested 2026-08-24b — slice 5's remaining scope closed: the first multi-term mgcv-native model (ADR-206)

- **Slice 5 IS NOW DONE.** The multi-term mgcv-native model both Stage-A halves
  (ADR-200, ADR-205) were waiting on now exists:
  `s(AttdAge,k=13,bs="cr") + s(AttdAge,by=StudyYear_C,k=13,bs="cr") +
  ti(AttdAge,PolYear,k=c(13,6),bs="cr")`, binomial/cloglog with `ExposCnt` weights
  (Anchor 5's absolute idiom), fit at a fixed `sp` per block. `polaris_re` assembles
  the design from the three already-independently-verified basis producers and fits
  with `gam_fit.penalized_irls_general`; `mgcv` fits the identical formula natively.
  Agreed on the FIRST measurement — `max_abs_eta_diff=1.242e-10` (`n=900`, `p=86`),
  identical to the printed digit at tier 1 and tier 3 (CI run 32722872476, oracle
  `sha256:0d54c192…` build 8). `MULTITERM_CLAIM` declares `eta` INDEPENDENT. Required
  levels 1-3 of the ten-cell suite also still agree — no regression. *Source: this
  session, ADR-206 (1st-order — closes the epic's active slice).*

- **The eta diff is real but four orders of magnitude looser than single-term
  Stage-A/B cases (~1e-14 → ~1e-10), diagnosed rather than left unexplained.**
  `cond(XᵀWX+S)≈5000` (well-conditioned), 9 IRLS iterations to convergence, and the
  diff is concentrated in a handful of rows (median 4.3e-13, mean 1.6e-12, max
  1.242e-10) — consistent with `gam_fit`'s shared `1e-10` relative-deviance IRLS
  convergence floor (`_IRLS_TOL`) compounding slightly more on an 86-column,
  four-penalty-block design than on the 7-13-column single-term cases every prior
  slice measured. Still ~8x inside the existing (not newly widened, Anchor 8) `1e-9`
  tolerance. *Source: this session (2nd-order — worth a closer look only if a future,
  larger multi-term model's diff grows past this order of magnitude; not evidence of
  a defect today).*

- **Three things this closure explicitly does NOT reach, named rather than left
  implicit.** (1) Anchor 2's *primary* MI-contrast-on-a-grid metric — needs basis
  evaluation at covariate values away from the training rows, a distinct question
  from the training-design `eta` check this session ran. (2) Extending slice 4 part
  B's continuous search (`select_lambdas_continuous`) to this design's N=4 penalty
  blocks — the assembled `(x, penalty_blocks)` is already the right shape, but
  nothing calls the search on it yet. (3) `sz` (slice 6) is not part of this model.
  *Source: this session, ADR-206 (1st-order — each is a concrete, small next slice
  now that the multi-term harness exists, not a re-opening of slice 5).*

### Harvested 2026-08-25 — slice 5b: `PolarisGAM` built, and its own registered prediction refuted (ADR-208)

- **Slice 5b IS NOW DONE — item (2) above is answered, not merely attempted.**
  `analytics/gam_model.py` generalises ADR-206's `assemble_multiterm_design`
  into `assemble_model_design(model: ModelSpec, data)` (any `"cr"`/`"ti"` term
  mix, not just the fixed three) and adds `fit_polaris_gam`, which selects its
  own `log10(lambda)` via `select_lambdas_continuous` (ADR-199) and fits with
  `penalized_irls_general` (ADR-195) — nothing re-derived. ADR-206's own tests
  pass unchanged against the refactor, proving it behaviour-preserving.
  *Source: this session, ADR-208 (1st-order — closes the epic's designated
  slice).*

- **The work order's own §4 registered prediction is REFUTED, and characterised
  rather than left an open gap.** ADR-199 measured `select_lambdas_continuous`
  against `mgcv` at 6.9e-04-to-9.8e-04 on 2-block designs; N=4 free-`sp`
  selection disagrees by `max_abs_log10_sp_diff=0.7766` instead — three orders
  of magnitude larger, concentrated in one block. Two diagnostic-only checks
  (not part of the committed, INDEPENDENT comparator) localise this to a FLAT
  REML SURFACE along that block's direction, not a criterion or search defect:
  the shared, already-verified criterion scores Python's own
  mgcv-independent optimum *lower* (better) than `mgcv`'s own exact selection,
  and starting the search from `mgcv`'s own point converges to yet a third,
  still-lower-scoring point. PLAN §5 risk 3 ("the optimiser may be badly
  conditioned where the 2-D grid was merely shallow"), now measured at N=4
  rather than merely anticipated. *Source: this session, ADR-208 (1st-order —
  a genuine INDEPENDENT disagreement is parity-epic progress per the routine's
  own framing, not a defect to fix reflexively).*

- **PLAN §6's separate registered prediction — "`edf` agrees far better than
  `sp` does" — holds again at N=4.** `edf_total_diff` is ≈4% (0.726 out of
  ~16-17) against `sp`'s near-full-decade disagreement. Confirms `edf` as the
  more stable basis-invariant quantity to report from a multi-term free-`sp`
  fit, the same lesson the ten-cell suite's level 2 and ADR-199 already
  established at lower dimension. *Source: this session, ADR-208 (2nd-order —
  a confirmed pattern, not a new finding requiring action).*

- **Correction, same day (PR #212 review [P1]): the "flat surface, not a
  criterion defect" diagnosis above was incomplete and is superseded.** Both
  checks it rested on read only OUR OWN criterion at both points, which
  cannot distinguish "mgcv's own optimiser stopped short" from "the two
  criteria disagree about which point is better." The discriminating
  measurement (`scripts/gam_multiterm_sp_delta_probe.R`, new) reads `mgcv`'s
  own score at both points too: `mgcv`'s own criterion and ours rank
  `mgcv`'s point and Python's point in OPPOSITE order
  (`delta_mgcv=-0.1214` vs `delta_ours=+0.7252`) — real evidence of an
  `sp`-dependent criterion discrepancy at this N=4-block, `ti()`
  -sharing-a-span structure, not (only) optimiser path-sensitivity.
  **CONFIRMED at tier 3, same day** (CI run 32874213883, `delta_mgcv=-0.121389`
  identical to tier 1 at every printed digit) — the sign flip is a real,
  reproducible finding on the pinned production oracle. **Slice 6 should
  still not be designated** — confirming the discrepancy is real is not the
  same as localising or closing it; a fourth basis's own `sp` selection on
  top of a CONFIRMED, still-unlocalised criterion discrepancy would compound
  rather than isolate the next disagreement. *Source: this session, ADR-208's
  amendment (1st-order — on the epic's critical path, blocks slice 6
  designation until localised or closed).*

- **Whether a more robust search strategy narrows the N=4 gap is open, and
  deliberately not attempted here.** `select_lambdas_continuous` was reused
  unchanged per the work order's own scope ("if this work starts producing new
  numerics, stop") — multi-start or informed initialisation (from
  mgcv-independent points only, so as not to break the INDEPENDENT
  classification) would be new numerics belonging to a future slice, not this
  one. *Source: this session (2nd-order, NICE-TO-HAVE — revisit only if a
  future slice needs tighter free-`sp` agreement at N>2, e.g. before adding
  `sz`/`select=TRUE` terms whose own smoothing parameters would compound the
  same flatness).*

### Harvested 2026-08-29 — slice 5c CLOSES the criterion defect (ADR-210); the N=4 gap re-lands as an optimiser question, escalated

- **Slice 5c IS NOW DONE.** Both defects PLAN slice 5c registered — Wood
  (2011) §3.1's `log|S|+` null-space cut (Appendix B, built whole:
  similarity transform, pivoted-QR determinant, the stable square root `E`)
  and eq. (4)'s observed-Hessian weight (`Family.observed_information_weight`,
  analytically exact `alpha_i=1` for both canonical links this module
  defines) — are fixed in the PRODUCTION `reml_score_general`. The eight-point
  fixed-`sp` spread against `mgcv` collapses from 3.910776 (raw, shipped) to
  4.271e-07 (tier 1) / 0.000000 at tier 3's print precision — ~9.2 million
  times smaller, identical at both tiers. *Source: this session, ADR-210
  (1st-order — closes the epic's designated slice).*

- **The registered prediction (PLAN slice 5c §4) lands on its THIRD branch —
  the most valuable and most consequential result this session produced.**
  Fixed-`sp` closes exactly as predicted. Free-`sp` selection on ADR-208's
  own N=4 structure does NOT follow it there: `max_abs_log10_sp_diff` reads
  0.7560 (tier 1) / **1.0996 (tier 3 — WORSE than the 0.6398 pre-fix
  reading)**. The discriminating measurement (score both sides' points under
  our OWN now-correct criterion) shows `mgcv`'s own selected point scoring
  measurably BETTER than our optimiser's own converged point
  (612.611 vs 612.663, tier 1) — **this re-diagnoses ADR-208's own finding**:
  the N=4 free-`sp` disagreement is no longer a criterion problem (the
  criterion is now settled, float precision, both tiers) but an OPTIMISER
  CONVERGENCE problem on this specific `by`-term-dominated landscape.
  *Source: this session, ADR-210 (1st-order — reopens the epic's cost
  estimate for the free-`sp`/slice-6 path; explicitly flagged for maintainer
  attention per slice 5c's own DoD, not absorbed as a routine finding).*

- **Registered as PLAN slice 5d, with two named hypotheses and a cheap
  tier-3 discriminator named before either needs new code.** (1) The
  finite-difference gradient L-BFGS-B uses may be too imprecise on a
  weakly-identified `lambda` — an analytic gradient exists to test this,
  built in this session but unused (Appendix B's own derivative
  expressions). (2) The surface may be genuinely multi-modal, distinguished
  from (1) by multi-start restarts on the same fixture. *Source: this
  session, ADR-210/PLAN slice 5d (1st-order — unblocks slice 6, which stays
  BLOCKED with its reason restated rather than lifted).*

- **Mutation-tested per the slice's own protocol, and reported honestly
  rather than papered over.** 6 mutations applied; 2 caught by dedicated
  tests (skip the pre-step; transpose the accumulated similarity transform),
  4 NOT caught by any fixture attempted — including the target model's own
  real four-block penalty structure at its own measured `sp`. The four
  constants those mutations touch only matter in a regime (a dominant
  block's own near-zero eigenvalues corrupted by genuine floating-point
  roundoff from an ill-conditioned matrix product) no fixture built by hand
  or drawn from this repository's own models currently exercises. *Source:
  this session, ADR-210 (2nd-order, NICE-TO-HAVE — closing it needs a
  harder-to-construct fixture than the two that succeeded; not blocking any
  acceptance criterion, since the two mutations that WERE caught are the
  ones the PLAN itself flagged as most load-bearing, mutation 6 especially).*

- **`experience_gam_penalized.reml_score` checked for the same two defects
  and found unaffected, at both tiers** — ADR-197's own precedent for
  running that check rather than assuming its answer, now run twice more.
  No material difference on that module's own well-conditioned two-block
  fixture, consistent with Wood's "the problem vanishes for a full rank S1"
  and that module's own `lambda`s never spanning the decades the target
  structure does. *Source: this session, ADR-210 (2nd-order — confirms no
  action needed on the production tensor-MI selector, PLAN Anchor 7).*

- **A job-summary-artifact limitation this session's own new workflow step
  reintroduced, caught and fixed same session.** The new fixed-`sp` compare
  step initially wrote its output ONLY into `$GITHUB_STEP_SUMMARY`, invisible
  to `get_job_logs` — the exact limitation `CONTINUATION_mgcv_parity_engine.md`'s
  backlog already names for two other steps, self-inflicted this time.
  `tee`'d to a file and re-dispatched before treating the run as sufficient
  confirmation. *Source: this session (3rd-order, PARKED — a one-line
  pattern fix, not a recurring risk once named; the two PRE-EXISTING
  instances of this same limitation remain the 2nd-order backlog item they
  already were).*

### Harvested 2026-08-29 (session 2, slice 5d)

- **Slice 5c's third-branch escalation, resolved the SAME DAY.** The optimiser-
  convergence question ADR-210 registered as PLAN slice 5d (above) was
  distinguished with evidence without needing the analytic-gradient hypothesis
  built in that session. Root cause: SciPy's L-BFGS-B default finite-difference
  step (`1.49e-8`, absolute) sits inside the noise floor `select_lambdas_continuous`'s
  own nested penalized-IRLS solve creates — a forward-difference scan at the
  optimiser's own "converged" point showed the derivative estimate stable from
  `h=1e-1` to `1e-6`, then wrong-signed at `h=1e-9`, with SciPy's default squarely
  inside the broken region. Fixed by deriving a step from this module's OWN
  measured noise floor (never from a comparison against `mgcv`) — confirmed at
  both tiers: `mgcv`'s own criterion now ranks Python's default-start point
  within `0.0007` of its own optimum (was `0.0523`, ~78x tighter), `eta`
  agreement improves to `~8e-4` (from `3.7e-2`). *Source: this session,
  ADR-212 (1st-order — unblocks slice 6, the epic's next basis).*

- **A genuinely new finding this fix surfaced: one smoothing parameter can be
  weakly identified by REML on real data, and the standard `log10(sp)`
  agreement metric is the wrong yardstick when that happens.** The by-term's
  own `lambda` swings across a decade and a half (and even flips which tier's
  `mgcv` build "wins" the comparison) while changing the REML score by only
  a few thousandths and barely moving the fitted surface — `max_abs_log10_sp_diff`
  swings 3.4x between tiers (`0.8777` tier 1, `0.2606` tier 3) while `eta`
  agreement stays fixed at `~8e-4` on both. *Source: this session, ADR-212
  (1st-order for the METHODOLOGY point — a future basis with a weakly-identified
  parameter should expect this signature and check `eta`/`edf` stability across
  tiers before trusting a raw `log10(sp)` disagreement as a defect; 2nd-order
  for the specific metric-revision question below, since it is maintainer-reserved).*

- **Open question carried to the maintainer, narrower than 5c's original
  escalation:** whether `FREE_SP_MODEL_CLAIM`'s own primary metric should be
  revisited to weight `eta`/`edf` over raw `log10(sp)` on structures with a
  weakly-identified block, now that the raw metric is demonstrated unstable
  across R builds in a way that does not track model agreement. *Source: this
  session, ADR-212 Consequences (2nd-order — a comparator-design decision,
  not blocking any slice; slice 6 proceeds under the current metric either way).*
### Harvested 2026-08-29 — slice 5d resolves both hypotheses (ADR-211); slice 6 unblocked; a new production-robustness gap registered as slice 5e

- **Slice 5d IS NOW DONE, same day as 5c.** The N=4 free-`sp` residual
  slice 5c's session reopened is resolved: it is `select_lambdas_continuous`'s
  own convergence precision on a weakly-identified `lambda` (hypothesis 1,
  CONFIRMED), not `mgcv` reaching a point ours cannot (hypothesis 2,
  REFUTED). Warm-starting the search at `mgcv`'s own selection converges
  back to it (within 1e-6) at a score 0.052286 BETTER than the blind
  default start's own result — the identical starting point reaches the
  identical, better point, which is the direct refutation of hypothesis 2.
  *Source: this session, ADR-211 (1st-order — closes the epic's designated
  slice and unblocks slice 6).*

- **The mechanism is precise, not inferred, and explains a standing
  inconsistency in the epic's own numbers.** On identical code and data,
  the blind search's own converged point on the by-term's block moves by
  nearly a full log10 decade (9.116 / 8.519 / 8.773) depending SOLELY on
  `OPENBLAS_NUM_THREADS`, while a fixed-`sp` evaluation of the identical
  criterion moves by ~4e-10 across the same thread counts. This is what
  made ADR-210's own tier-1 (0.7560) and tier-3 (1.0996) readings of "the
  same" measurement disagree — a confound in the epic's own tooling, not a
  BLAS/mgcv-version artifact of the kind the routine already knows to
  watch for on the R side. *Source: this session, ADR-211 (1st-order —
  affects how every future free-`sp` reading in this epic should be taken
  and compared).*

- **Fixed: `OPENBLAS_NUM_THREADS=1` now pinned for the CI "compare" job**
  (`.github/workflows/mgcv-conformance.yml`), mirroring the R oracle's own
  existing pin. Not a tolerance change (Anchor 8) — it removes a measurement
  confound, the identical argument that justified pinning it for R.
  *Source: this session, ADR-211 (1st-order — every future free-`sp`
  measurement in this workflow is now reproducible run to run).*

- **Registered as PLAN slice 5e, READY but not designated: the production
  search's own convergence robustness at N > 4 blocks is unfixed.** A
  blind, non-cheating 9-start check improved on the single default start
  (612.6149 vs 612.6630 best-of-9) but did not reach `mgcv`'s reachable
  612.6108, and 2 of 9 far-corner starts failed to converge outright. The
  target formula has 13-21 blocks — more room for this pathology, not
  less. Candidate fixes named but not chosen (multi-start with best-of-N,
  an analytic gradient on Appendix B's own derivative expressions, a
  different search algorithm). *Source: this session, ADR-211/PLAN slice 5e
  (1st-order — on the epic's critical path before slice 7's 21-block
  `select = TRUE`, and arguably before slice 6 if `sz`'s blocks interact
  with the by-term's; sizing and sequencing against slices 6/7 is a
  maintainer call, not this routine's).*

### Harvested 2026-08-30 — reconciling the two concurrent slice-5d ADRs (merge of PR #216 into PR #217)

- **Two daily-dev sessions resolved slice 5d concurrently, and the merge is
  where the reconciliation had to happen.** ADR-212 (PR #216, merged first)
  localised the MECHANISM — SciPy's L-BFGS-B default finite-difference step
  sits inside the nested IRLS solve's noise floor — and fixed it. ADR-211
  (PR #217, this branch) localised the environment CONFOUND — the blind
  search's landing point moves with `OPENBLAS_NUM_THREADS` alone — and pinned
  it in CI. Neither subsumes the other: a gradient step inside the noise floor
  is exactly what lets BLAS summation order move the result, so one fixes
  convergence quality and the other fixes measurement reproducibility.
  ADR-211 carries an amendment recording this; `DECISIONS.md` keeps both in
  numeric order, so the 211 slot the renumber would otherwise have left empty
  is filled. *Source: this merge, ADR-211 amendment 1 (1st-order — the epic's
  own critical path).*

- **PLAN slice 5e's premise was restated against the merged fix rather than
  carried forward unchanged.** Every number slice 5e was registered against
  (`612.6630` single-start, `612.6149` best-of-9, both versus `mgcv`'s
  `612.6108`) was measured PRE-fix and no longer describes the shipped
  default; PR #216's own post-fix sweep has it landing in a `612.6101`–
  `612.6116` band. What survives the fix intact is the question nothing has
  measured yet: whether a single start still suffices at the target's 13–21
  blocks. *Source: this merge, PLAN slice 5e (1st-order — a follow-up of an
  originally-planned feature, and the acceptance bar for slices 6/7).*

- **A merge artifact neither session could see, registered as slice 5e's
  first task:** ADR-212's refreshed hardcoded `python_opt_log10` was measured
  before ADR-211's thread pin existed, and the pin is scoped to the `compare`
  job while that constant is consumed by the R job. The discriminator
  therefore scores `mgcv` against a Python point the pinned pipeline would not
  necessarily reproduce. Harmless today (the point is hand-supplied by
  construction, and ADR-212 recorded its `nproc`/thread provenance for exactly
  this check), but it should be refreshed once under the pinned regime before
  being used as a baseline. *Source: this merge, PLAN slice 5e (2nd-order — a
  follow-up of a follow-up, promoted as NICE-TO-HAVE only, per the order cap).*

### Harvested 2026-08-31 — slice 5f: covariate-sharing N=8 robustness answered, and it is MORE stable than either of slice 5e's own readings (ADR-214)

- **Slice 5f IS NOW DONE.** ADR-213 (slice 5e) left open whether a
  covariate-SHARING N>4 structure — closer to the target formula's own
  13-21 blocks, most of which share `AttdAge`/`PolYear`/factor levels —
  behaves differently from its own covariate-DECOUPLED N=8 stress case.
  This session built one (the N=4 fixture's own three terms plus four
  `s(x, by=Group)` terms standing in for the target's own four
  `sz(factor, AttdAge/PolYear)` terms) and measured it the identical way
  ADR-213 measured its two structures. **Single-start converged and
  matched best-of-9 EXACTLY at all three thread counts** — the cleanest
  reading of any structure tested across either slice, and the
  thread-to-thread spread (`0.000656`) is smaller than BOTH of ADR-213's
  own readings (N=4: `0.001483`; decoupled N=8: `0.001180`), not between
  them. *Source: this session, ADR-214 (1st-order — closes the epic's
  designated slice and answers the open question slice 5e itself could
  not, without unblocking or blocking anything else: slice 6 was already
  unblocked by slice 5d).*

- **A real defect was found and fixed during construction, not just in
  the final measurement — worth keeping for the next session that builds
  a covariate-sharing fixture.** A first draft (two indicators, each
  reused across an `AttdAge` term and a `PolYear` term, mirroring
  `sz(FaceSize, AttdAge)`/`sz(FaceSize, PolYear)` literally) was exactly
  rank-deficient by 2, SVD-confirmed: an unconstrained `by`-scaled `cr`
  basis always contains the constant function in its span (ADR-200), so
  two terms sharing one indicator each contain that indicator's own
  direction — one exact dependency per repeated indicator. `mgcv`'s own
  `sz` avoids this via its own centering constraint, which this simpler
  stand-in deliberately does not build. *Source: this session, ADR-214
  (2nd-order, NICE-TO-HAVE — a documented dead end for whoever builds
  `sz`'s own Stage-A fixtures in slice 6, not itself a code gap).*

- **What remains open, explicitly not filed as new slices:** (1) this is
  one covariate-sharing construction (independent binary indicators), not
  `sz`'s own constrained parameterisation — evidence about the outer
  search's robustness, not a preview of `sz`'s own basis behaviour (slice
  6's own work); (2) the MI by-term's own at-bound, weakly-identified
  behaviour (first found in ADR-211/212's N=4 fixture) persists
  structurally across every N tested so far without destabilising the
  rest of the search — not a new finding, but not resolved either; (3)
  whether single-start continues to suffice past N=8, toward the target's
  13-21 blocks, remains untested in any shape. *Source: this session,
  ADR-214 (2nd-order, NICE-TO-HAVE — named for slice 6/7's own future
  sessions, not urgent on its own).*

### Harvested 2026-08-31 — slice 6: the `sz` basis Stage A, an INDEPENDENT closed-form re-derivation (ADR-215)

- **Slice 6's Stage A IS NOW DONE.** The target formula's four
  `sz(<factor>, <smoothed margin>, ...)` terms all name a single two-level
  factor and no `id`; this session built and verified exactly that scope.
  `mgcv`'s own constraint machinery for `sz` (`object$C <- c(0, nf)`, routed
  through `smoothCon`'s `mgcv:::XZKr` branch) has no closed-form statement
  anywhere `mgcv` documents, so this session instrumented the constructor
  directly, derived the linear-algebraic effect as a contrast-against-the-
  last-level matrix (`M = D kron I_k`), and verified that closed form against
  `smoothCon()`'s actual output on three cases — agreeing to float
  round-trip precision (~1e-14) on the first attempt. PLAN §6's own
  registered prediction ("`sz` is the hardest basis") did not bite Stage A:
  the cost was entirely in understanding the constraint machinery, not in
  getting the numbers to agree once that understanding existed. *Source:
  this session, ADR-215 (1st-order — closes the epic's next unchecked
  slice and is the third of the three basis classes PLAN §1 named as
  required).*

- **What remains open, registered rather than left implicit (PLAN slice
  6b):** nothing has yet fit a multi-term model containing an `sz` term and
  compared it against `mgcv`'s own native fit on `eta`, the way ADR-206 did
  for the `ti`/numeric-`by` terms. Slice 4 part B's outer search
  (`select_lambdas_continuous`) has also not been exercised on an
  `sz`-shaped penalty-block structure (one smoothing parameter per factor
  level rather than per margin). Neither blocks slice 7. *Source: this
  session, ADR-215 (1st-order — a follow-up of the slice this session
  closed, needed before the target's full eight-term structure can be
  assembled and fit).*

### Harvested 2026-08-31 — slice 6b: the first `sz`-carrying multi-term Stage-B fit, agrees on the first measurement at both tiers (ADR-216)

- **Slice 6b IS NOW DONE, the same day slice 6 closed Stage A.**
  `gam_model.assemble_model_design` dispatches `basis="sz"` (via a new,
  explicit `TermSpec.n_levels` input) alongside the `cr`/`ti` dispatch slice
  5b already built — every basis PLAN §1 named as required now has both an
  INDEPENDENT Stage-A and an INDEPENDENT Stage-B result. A two-term model
  (`s(AttdAge,k=13,bs="cr")` + the target formula's own first `sz` term,
  `s(FaceSize,AttdAge,k=13,bs="sz",xt=list(bs="cr"))`, fixed sp) agrees with
  `mgcv`'s native fit on `eta` at `3.921e-12` (tier 1) / `3.912e-12` (tier
  3) — the first measurement, no iteration needed, the same shape ADR-206's
  own first multi-term result had (`1.242e-10`). *Source: this session,
  ADR-216 (1st-order — closes the epic's next unchecked slice and is the
  last basis-class gap named in PLAN §1).*

- **What remains open, named but not yet registered as a slice:**
  extending `select_lambdas_continuous` to an `sz`-shaped block structure
  (one smoothing parameter per factor level); a multi-term model combining
  `sz` with `ti`/numeric-`by` (the target formula's own actual shape, all
  eight terms together); a model with more than one `sz` term (the target
  has four). This session deliberately proved the minimal new `cr`+`sz`
  pairing first, the same discipline ADR-206 used before combining `ti`
  and `by`. ~~Slice 7 (`select = TRUE`) remains the epic's next PLANNED,
  un-blocked slice.~~ — **SHIPPED** (PR #222, 2026-09-01): see the
  2026-09-01 harvest entry below. *Source: this session, ADR-216
  (1st-order — a follow-up needed before the target's full eight-term
  structure can be assembled, fit and have its own smoothing parameters
  selected).*

### Harvested 2026-09-01 — slice 7: `select = TRUE`'s double penalty is one basis-agnostic rule; Stage A and a fixed-`sp` Stage B both agree with mgcv, tier 1 AND tier 3 (ADR-217)

- **Slice 7 IS NOW DONE for Stage A and a fixed-`sp` Stage B — the last
  unchecked slice in the epic's written PLAN.**
  `gam_select_penalty.null_space_penalty` found and confirmed ONE
  basis-agnostic rule for `mgcv`'s `select=TRUE` double penalty
  (eigendecompose the sum of a term's own existing penalty block(s) at
  their natural, unscaled magnitude; the extra penalty is `U0 @ U0.T` for
  the resulting null-space eigenvectors), agreeing with `mgcv`'s own
  `gam(..., select=TRUE, fit=FALSE)$smooth[[i]]$S` to float round-trip
  precision across all four term archetypes the target formula uses
  (`cr`, numeric-`by` `cr`, `ti`, `sz`; six cases total, at the target's
  own knots), with no per-basis branch in the implementation. Wired into
  the production `assemble_model_design` path via a new `ModelSpec.select`
  field — the same three-term model ADR-206 verified now fits under
  `select=TRUE` (7 blocks) and agrees with `mgcv`'s native fit on `eta` to
  `6.164e-11` (tier 1) / `5.691e-11` (tier 3). Both stages confirmed
  tier 1 AND tier 3 identical, same session, CI run 33417357327 (also
  reproduced on the PR's docs-only head commit, run 33417953915). Also
  fixed the at-bound-guard collision PR #212's review named: only the
  lower search bound raises by default now; the upper bound (exactly what
  `select=TRUE` produces for a no-signal term) is reported on the fit
  rather than raised, with a new `strict=True` for the harness mode that
  still wants a hard raise. *Source: this session, ADR-217 (1st-order —
  closes the epic's last unchecked PLAN slice).*

- **What remains open, named but not yet registered as a slice:**
  extending `select_lambdas_continuous`/`fit_polaris_gam`'s own free-`sp`
  search to the doubled/increased block count `select=True` produces —
  every case measured this session uses a FIXED, externally-supplied `sp`,
  so nothing yet reproduces PLAN §1's own headline figures (13 → 21
  smoothing parameters, edf 47.36 → 16.96); combining `select=True` with
  the target's full eight-term structure, including more than one `sz`
  term. **The epic's written PLAN is now otherwise exhausted** — this is
  the largest remaining piece of work, and whether it becomes a registered
  slice 7b is a maintainer decision worth making before the next routine
  run picks work (PR #222 review, "Human review recommended for"). *Source:
  this session, ADR-217 (1st-order — the step that would let a caller
  actually reach the target formula's own headline `select=TRUE` figures).*

### Harvested 2026-09-01b — slice 7b: the free-`sp` search on `select=TRUE`'s 7-block structure, characterised (ADR-218)

- **Slice 7b IS NOW DONE, tier 1 measured this session, tier 3 dispatched —
  registered and closed the same session, maintainer-authorized.** The item
  the entry above named ("whether it becomes a registered slice 7b is a
  maintainer decision") was authorized in-session; `fit_polaris_gam`'s own
  free-`sp` search is now measured on `select=True`'s 7-block structure.
  Single-start disagrees badly (`max_abs_log10_sp_diff=5.13`, worse than
  any N=4 reading this epic has taken). A new opt-in
  `fit_polaris_gam(multistart=True)` parameter (best-of-9,
  `select_lambdas_continuous_multistart`, ADR-213 — every other caller's
  default behaviour unchanged) closes `eta` agreement 166x (to `0.0027`)
  and `edf_total` 22x (to `0.11`); raw `log10(sp)` only tightens to `1.48`.
  A warm-start diagnostic (TRANSPORT, never a parity claim) shows the
  survivor is optimiser convergence on a weakly-identified surface —
  `mgcv`'s own point scores measurably better under our own criterion than
  best-of-9 blind multistart reaches, the exact mechanism ADR-211/212 fixed
  at N=4, now recurring at a larger scale. **Refutes** slice 7b's own
  "null-space blocks are the likely culprit" registered-prediction clause:
  multistart resolves the three null-space blocks to `<0.01` agreement; the
  residual relocates to two of the three terms' own EXISTING blocks
  instead. PLAN §1's own headline `select=TRUE` figures (13→21 smoothing
  parameters, edf 47.36→16.96) are now reachable through the production
  path with a working, measured mitigation. *Source: this session, ADR-218
  (1st-order — the step that lets a caller actually reach the target
  formula's own headline `select=TRUE` figures through `fit_polaris_gam`).*

- **The `eta`/`edf`-vs-`log10(sp)` acceptance-metric question (first raised
  ADR-212 Consequences) now has a second, larger data point.** At N=7,
  after `multistart=True`, `max_abs_log10_sp_diff` stays at `1.48` (misses
  `SELECT_FREE_SP_MODEL_CLAIM`'s own `1e-2` gate by two orders of magnitude)
  while `eta` agrees to `0.0027` and `edf_total` to `0.11` — sharper than
  ADR-212's own N=4 reading. **Still maintainer-reserved, restated rather
  than re-opened as a new question** (`docs/CONTINUATION_mgcv_parity_engine.md`
  "Open questions"). *Source: this session, ADR-218 (2nd-order — a
  comparator-design decision, not blocking; the epic's remaining scope
  proceeds under the current metric either way).*

- **What remains open, named but not yet registered as a slice:**
  combining `select=True` with the target's full eight-term structure, or
  with an `sz` term (Stage A's `sz-facesize-*` cases are single-term only).
  Not attempted this session; out of slice 7b's own stated scope. *Source:
  this session, ADR-218 (2nd-order — the epic's written PLAN is otherwise
  exhausted at the three-term subset every Stage-B slice since ADR-206 has
  used).*

### Harvested 2026-09-01c — slice 7c: ADR-218's residual was the metric, not the optimiser (ADR-219)

- **The `1e-2` gate on raw `log10(sp)` is ILL-POSED on two of the seven
  `select=TRUE` blocks — measured, not argued.** At `mgcv`'s own point our
  REML criterion fails to resolve 2 of the 7 `rho` directions (step-stability,
  confirmed at both tiers; an eigenvalue-sign count read "5 of 7" at tier 1 and
  "7 of 7" at tier 3 and must not be quoted — ADR-219 amendment 2); the two are
  exactly the two ADR-218 found its residual had relocated to. Their apparent
  curvature grows like `1/h^2` as the step shrinks (a noise floor on a flat
  direction, not the saddle their raw negative eigenvalues suggest), and
  moving one of them TWO decades changes the score by `-0.0002` against
  `~+1.0` for HALF a decade on an identified block. **No optimiser, however
  exact, can pin a parameter the objective does not resolve** — which is why
  slice 7c's own Part 1 (the analytic gradient) was deliberately not built.
  *Source: this session, ADR-219 (1st-order — it corrects the target of
  ADR-218's own named next hypothesis).*

- **Slice 7d registered: the analytic REML gradient, re-aimed.** Still worth
  building, but for the `0.0141` score gap on the 5 identified directions, the
  `converged=False`-at-near-zero-gradient defect, and the ~8x cost saving that
  would make `multistart=True` cheap enough to default — **not** for the
  `log10(sp)` gate it cannot close. *Source: this session, ADR-219 (1st-order
  — the direct continuation of ADR-218's next hypothesis).*

- **A defect-in-waiting found in committed code, filed before it bites.**
  `gam_derivatives.dw_deta`/`dw_drho` implement Wood Appendix D **at
  `alpha ≡ 1`** (the FISHER working weight), while `reml_score_general`'s
  `log|XᵀWX + S|` uses the **OBSERVED** weight (`newton_working_weights`,
  slice 5c Defect B). Any future REML gradient that wires `dw_drho` straight
  into its `dW/drho` term is correct for a canonical link and **silently wrong
  for `cloglog`** — the case this epic fits. Recorded on slice 7d. *Source:
  this session, ADR-219 (1st-order — a latent defect in an
  originally-planned component, found while reading it for slice 7c).*

- **Recommended and NOT taken: re-gate on the Hessian-weighted distance.** It
  preserves INDEPENDENT provenance (the same two operands, re-normed by our
  own criterion's curvature) where the sharper-looking score gap is
  DIAGNOSTIC and must never be a gate. Stays maintainer-reserved. *Source:
  this session, ADR-219 (2nd-order — a comparator-design decision, unchanged
  in status from ADR-212/218).*

- **Tier-3 confirmation owed on ADR-219's three ledger rows.** Not dispatched
  this session (no production path changed for a tier-3 run to exercise);
  required before these numbers are cited outside the session log. *Source:
  this session, ADR-219 (2nd-order — a confirmation obligation on this
  session's own rows, not new scope).*

- **`test_the_r_probe_runs_end_to_end` passes only when
  `OPENBLAS_NUM_THREADS` is pinned — green in CI, red for a contributor
  running the suite locally.** Found while taking slice 7c's own baseline and
  verified on unmodified `main` (`0fd6ddc`): at this container's default of 4
  threads the test fails at `assert comparison.converged`
  (`max_abs_eta_diff=0.000759342158123566`,
  `max_abs_log10_sp_diff=0.2606175963459325`, identical to the last digit on
  `main` and on the branch); at `OPENBLAS_NUM_THREADS=1` — what the CI compare
  job pins job-level, PR #217 review [P1-1] — it passes. This is ADR-211/213's
  own measured thread sensitivity (its ledger row already records single-start
  failing to converge at 4 threads) surfacing as a test that is green only in
  the one environment that pins threads. **Not fixed in slice 7c's PR:
  out of scope, and the candidate fixes are not equivalent** — pinning threads
  inside the test, dropping the `converged` assertion, or switching that
  harness to `multistart=True` each say something different about what the
  test is for. Needs its own slice. *Source: this session, slice 7c baseline
  (1st-order — a defect in an originally-planned component, in committed
  code).*

- **`select_lambdas_continuous`/`_multistart` is not reproducible across CI
  runner instances, even with `OPENBLAS_NUM_THREADS` pinned to 1.** Three
  readings of one fixture (ADR-219 amendments 2-3): two tier-3 runs on the SAME
  oracle image with the SAME pins disagree by **four decades** on the selected
  `sp` for a weakly-identified block (`multistart` `max abs log10(sp) diff`
  `5.9517` vs `1.4754`), while one of them reproduces the tier-1 reading exactly.
  ADR-211/213 measured sensitivity to thread COUNT; this is the same class one
  level deeper — identical pinned configuration, different physical runner.
  **Consequence: any acceptance gate must be shown reproducible across repeated
  runs in one environment before it is a gate**, which is a harder bar than
  cross-tier agreement and the right one given the marketing intent recorded in
  amendment 1. Not fixed in slice 7c (out of scope). *Source: this session,
  ADR-219 amendment 3 (1st-order — a reproducibility defect in an
  originally-planned component, in committed code).*

### Harvested 2026-09-03 — slice 7d: the analytic REML gradient closes the score gap, and a NEW SciPy stopping-rule defect explains the `converged` contradiction (ADR-220)

- **The `dW/drho` defect-in-waiting ADR-219 flagged is now CLOSED, not
  merely avoided.** `gam_derivatives.third_deriv_mu_eta`/
  `variance_second_deriv`/`dalpha_deta`/`dw_deta_observed`/
  `dw_drho_observed` supply the exact, alpha-aware Appendix D chain, each
  verified against a central difference of the function one order below it
  on all three link/family combinations this codebase defines, before
  composition. The cheap check ADR-219/220 required before deriving
  anything FAILED first (omitting the term left a residual an order of
  magnitude above an established noise floor), which is why the derivation
  was warranted rather than skipped. *Source: this session, ADR-220
  (1st-order — closes a defect-in-waiting an earlier session filed).*

- **The score-gap half of ADR-218's residual is closed, decisively, at a
  measured 8.4x-9.5x lower search cost — CONFIRMED at both tier 1 and tier
  3.** On the `select=TRUE` N=7 structure, tier 1 (R 4.3.3/mgcv 1.9-1) and
  tier 3 (R 4.6.1/mgcv 1.9.4, pinned oracle digest
  `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`,
  CI run [33766634959](https://github.com/jonathancrawford05/polaris-re/actions/runs/33766634959))
  agree identically in verdict: a warm-started analytic-gradient search
  reaches REML score `523.645314` (tier 1) / `523.645315` (tier 3) against
  `mgcv`'s own `523.645336` (tier 1) / `523.645331092` (tier 3) — tier 3's
  gap of `-0.000016` is the tightest reading this epic has produced on this
  structure — and `multistart(9)` with the analytic gradient reaches
  essentially the same score gap as the finite-difference default using 549
  (tier 1) / 462 (tier 3) function evaluations against 4600 / 4384 — the
  "~8x cost saving" ADR-219 predicted in advance, now measured and
  confirmed at both tiers rather than assumed. *Source: this session,
  ADR-220 and its amendment 1 (1st-order — closes the direct continuation
  of ADR-218's own named next hypothesis).*

- **NEW: SciPy L-BFGS-B can report `converged=True` via its own `ftol`-style
  stopping rule while the TRUE gradient (now exact, not finite-differenced)
  is large on directions not pinned at a search bound.** Refutes the second
  clause of slice 7d's own registered prediction ("`converged` stops
  disagreeing with a near-zero gradient") — but by a DIFFERENT mechanism
  than the one that clause assumed (ADR-212's finite-difference-noise
  defect, which this slice's exact gradient does not have). Localised to
  one reproducible case (blind single-start, `select=TRUE` N=7, two of
  seven blocks pinned at the search's upper bound) but not chased to a fix
  this session — three candidate directions named, none evaluated.
  Registered as PLAN slice 7f with a release condition (ADR-209 decision 1).
  *Source: this session, ADR-220 (1st-order — a defect in the search this
  slice's own scope touches directly).*

- **Tier-3 confirmation on ADR-220's `SELECT_FREE_SP_MODEL_CLAIM` table
  (analytic-gradient rows) is now OBTAINED, same session, by TWO
  separately-dispatched runs (ADR-220 amendments 1-2).** A fourth dispatch
  (`33766634959`) succeeded after cancelling two colliding
  `workflow_dispatch` runs freed the runner — all 27 steps succeeded, but
  an automated PR review caught that the run's own run-level `conclusion`
  reads `cancelled` (a stray cancel call landed right as it finished), so
  a second run (`33768187631`, clean `conclusion: success`, same PR head)
  was cited alongside it — bit-identical on the parity table, one small
  (`~1e-5`-`1e-3`) run-to-run wobble on the warm-start diagnostic row only,
  attributed to cross-run floating-point non-associativity, not a defect.
  Every finding matches tier 1 in verdict, several tighter. Both tables are
  citable outside the session log as of this confirmation. *Source: this
  session, ADR-220 amendments 1-2 (2nd-order — discharges the
  confirmation obligation this session's own rows carried, not new
  scope).*

- **`docs/MEASUREMENT_unconditional_coverage.md`'s stamp drifted from an
  INERT edit, the same schema gap `CONTINUATION_mgcv_parity_engine.md`'s own
  open question already names.** Adding functions to
  `gam_derivatives.py`/`gam_reml_appendix_b.py` (both sit in
  `scripts/unconditional_coverage_study.py`'s transitive import closure via
  `gam_uncertainty_mi` → `gam_uncertainty`) tripped the drift detector even
  though nothing on the measured path changed. Re-ran the study for real
  rather than asserting inertness — the honest fix available today — and
  the coverage figures are unchanged to the printed digit (0.7435/0.7815
  age-flat, 0.7781/0.8090 age-varying), confirming the edit really was
  inert. The schema question itself (should an additive, unrelated edit to
  a file in the closure even count as drift) remains open and
  maintainer-reserved, unchanged in status. *Source: this session
  (2nd-order — a second instance of an already-filed schema gap, not new
  scope).*

- **PLAN slice 7e (re-gating `SELECT_FREE_SP_MODEL_CLAIM` on `eta`/`edf`)
  is DONE, tier 1 AND tier 3 both confirmed (ADR-221 + amendments 1-3).**
  Carries out the maintainer's own already-authorized decision (ADR-219
  amendment 1 decision 4). Both new tolerances derived, not tuned
  (`edf_tolerance` reuses an existing project constant verbatim;
  `eta_tolerance` derived with the same headroom-over-a-measured-floor
  method `compare_vc_case` already uses); the change discriminates a real
  production choice (the module's own single-start default still fails the
  new gate) rather than loosening the measurement. *Source: this session
  (1st-order — the epic's own next unchecked slice).*
- **The H-weighted companion distance (slice 7c) is sensitive to WHICH
  endpoint's Hessian weights it — not previously measured.** Evaluated at
  each search's own converged point for the first time (ADR-221 §5):
  single-start's reading is 4.8x smaller at its own point than at `mgcv`'s;
  multistart's is 5.1x larger. No safe default endpoint exists. A stated
  convention (or reporting both, as this session does) is needed before
  this metric could ever gate anything. *Source: this session, ADR-221
  (2nd-order — a measurement precondition for a future re-gating decision,
  not itself blocking anything today).*
- **A stale provenance label, found and fixed while re-checking
  `docs/VERIFICATION_STANDARD.md` §2.1 compliance for this slice.**
  `scripts/gam_select_free_sp_identifiability_diagnostic.py`'s own section
  (4) header had printed `H-weighted : INDEPENDENT` since slice 7c
  (2026-09-01) — a label ADR-219 amendment 1 decision 2 superseded the next
  day when it ratified `MEASUREMENT (own criterion)` as the correct
  category. Nothing downstream had cited the stale label as evidence
  (`gam_sp_identifiability.py`'s own docstring was already correct), so no
  retraction is needed — but it is exactly the kind of drift §1's own
  warning describes ("a caveat in a paragraph does not travel"), caught
  only because this slice's own claim sentence depended on getting it
  right. *Source: this session (2nd-order — a documentation correction with
  no downstream consequence found).*
