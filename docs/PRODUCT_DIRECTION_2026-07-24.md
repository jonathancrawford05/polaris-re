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
9. **Performance harness with same-run head-vs-main baseline.** A `polaris perfbench`
   / `tests/perf/` harness timing engine hot paths on a fixed synthetic block +
   deterministic structural metrics, benchmarking head and main **in the same job**
   (noise-cancelling ratio → `perf.json`). Prerequisite for #10 and NICE-TO-HAVE
   #62/#63. *Source: maintainer discussion 2026-07-12, 1st-order.*
   — **IN PROGRESS** (this session): constituted as a MEDIUM epic and decomposed —
   `docs/PLAN_perf_harness.md` + `docs/CONTINUATION_perf_harness.md` (IN PROGRESS).
   **Slice 1 shipped** (ADR-169, this PR): the deterministic perf-probe core
   (`analytics/perf_harness.py` — `PerfProbe`/`PerfReport`/`run_perf_probe`,
   `to_perf_dict()`/`to_json()` `perf.json` shape, deterministic counts + output
   fingerprint + MiB-peak + best-of-k timing), reusing B2's `build_homogeneous_block`;
   fast unit + `perf`+`slow` reproducibility tests; `perf` marker; `make perf`.
   Goldens byte-identical. **Remaining #9 work is tracked as the epic's own Slice 2
   (head-vs-main same-job driver + `perf.json` diff) and Slice 3 (CI perf job — gates
   structural deltas, alerts on wall-time ratio), in the CONTINUATION.** Strike through
   once Slice 3 closes #9.
10. **Committed per-merge performance log (`perf/history.jsonl`) + creep detection.**
    One append-only deterministic-first row per merge to `main`, to catch slow
    multi-month creep a per-PR comment structurally cannot. Depends on #9. *Source: maintainer discussion 2026-07-12, 1st-order.*
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
