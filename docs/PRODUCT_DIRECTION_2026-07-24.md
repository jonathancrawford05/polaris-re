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
5 explains the shortfall. On the identical truth and seeds, the **unpenalized**
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

- **Next: slice 2 — `bs = "cr"`, with supplied and default knots.** The natural
  continuation; `extract_raw_terms`/`TermExtract` are shaped to extend to an mgcv-native
  code path (`smoothCon(..., absorb.cons=TRUE)` per ADR-191) without touching the `raw`
  path already proven. *Source: `docs/PLAN_mgcv_parity_engine.md` §3 (1st-order — the
  epic's own NEXT slice).* **BLOCKER**, same standing blocker as the epic itself.

- **The pre-existing `data/mortality_tables` gap** (5 test failures — all one root
  cause, the gitignored generated CSVs absent in this fresh container — plus some golden
  QA-config skips) is unrelated to this epic and unaddressed here; it needs
  `scripts/convert_soa_tables.py` run against a network-reachable table source. *Source:
  this session's baseline check (2nd-order, NICE-TO-HAVE — orthogonal to the active
  epic, for whichever routine next needs those tables).*
