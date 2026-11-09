# Commercial Viability Review — 2026-11-09

## Purpose

The daily-dev routine (step 6) regenerates this review when the latest one is
older than ~30 days. The previous one, `COMMERCIAL_VIABILITY_REVIEW_2026-07-15.md`,
is **117 days old**. This regeneration had a second trigger as well: daily-dev's
**Epic slot is empty**. Step 5b excludes epics owned by another routine. Every
IN PROGRESS continuation on `main` today belongs to the mgcv Parity routine
(`docs/ROUTINE_MGCV_PARITY.md`) or is parked:

| CONTINUATION (IN PROGRESS by grep) | Owner / state |
|---|---|
| `gam_dashboard` (active: `PLAN_gam_dashboard_stabilise_retire.md`, S1 open as PR #283) | mgcv Parity routine (pointer in `ROUTINE_MGCV_PARITY.md`) |
| `mgcv_parity_engine`, `mgcv_capability_ladder`, `gam_real_data_readiness` | mgcv Parity routine |
| `penalized_mi_surface` | superseded from slice 6, routed to the mgcv routine |
| `reserve_basis_correctness` | PARKED (resume on maintainer decision only) |

The routine (2026-08-16 amendment, Change 4) treats this as an **empty Epic
slot**: follow the maintenance-mode path, or regenerate this review. The review
is stale, so this session regenerates it. It **re-ranks the pricing-engine
catalogue** and **names the next daily-dev Tier-A epic**. Per step 5b, the next
session writes that epic's PLAN and ships slice 1.

This is a strategic document. It contains no comparison against a reference and
no number that Polaris computes and then reports as agreement. ADR-193 does not
bind any figure here.

---

## 1. Review of the Last 10 PRs (#273–#282), plus #283 open

| PR | Title (abridged) | Track | Product-engine change? |
|----|------------------|-------|------------------------|
| #273 | R3 Stage B — Polaris `bam` meets cloud acceptance on 9/10 ILEC cells | mgcv | No (`gam/`) |
| #274 | docs: record R3 DONE; S1_mid miss kept as known limitation | mgcv | No |
| #275 | R4 — thin-plate (`tp`) basis | mgcv | No (`gam/`) |
| #276 | docs: next epic — HGAM fitter in the dashboard | mgcv | No |
| #277 | D1 — HGAM fitter in the experience-improvement page + cost model | mgcv | Dashboard (GAM page) |
| #278 | measure(D1): headless local check of the cost model | mgcv (maintainer) | No |
| #279 | D2 — HGAM partial effects and `MI_x(y)` surface | mgcv | Dashboard (GAM page) |
| #280 | ux(dashboard) batch 1 (closed, superseded by #281) | maintainer UX | — |
| #281 | ux(dashboard) batch 1 — R-01/04/05/07/09/16 | maintainer UX | Dashboard shell + portfolio page (small) |
| #282 | docs: ADR-264 — stabilise the HGAM, then retire the older experience-GAM | mgcv | No |
| #283 *(open)* | S1 — saturation flag, surface mask, exposure message | mgcv | Dashboard (GAM page) |

### What the table shows: one track has held 100% of throughput for three months

The last ten PRs all come from the mgcv/GAM track, apart from one maintainer UX
batch. The pattern holds over a much longer window than ten PRs:

- **PR #183 (2026-08-04)** was the last merged **pricing-engine** feature. It closed
  the C4 portfolio-execution epic.
- **PRs #184 → #282 (2026-08-04 → 2026-11-09, ~97 days, ~95 merged PRs)** are the
  GAM diligence harness, the penalized MI surface, mgcv parity (slices 1–10), the
  capability ladder, the Wood outer solver, the parity preview, real-data
  readiness and the GAM dashboard. The only exceptions are the cross-cutting
  verification-provenance work (#200, #208, #236), which this track also
  motivated, and #281.
- In that window, **no** treaty, product, reserve, capital, IFRS 17, API or portfolio
  capability was added or fixed.

This is not a quality complaint. The GAM track has been rigorous: two independent
producers throughout, measured rather than asserted, and limitations recorded
instead of relaxed. It also followed the maintainer's direction (ADR-207 made the
parity stack the production route). The problem is structural: **the two routines
share one implicit slot.** `ROUTINE_MGCV_PARITY.md` §Budget says it "replaces
daily-dev's slot on days when the parity epic is the active work … only one of
them has work to do". The daily-dev routine's 2026-08-16 amendment says the
opposite. It says to **exclude** the externally-owned epic and treat daily-dev's
own slot as empty. In practice the first reading won by default. Because the GAM
track always has a next slice, daily-dev never constituted an epic of its own.

That is the 2026-06-18 "polish spiral" in a new form. Back then the problem was
sub-day polish crowding out epics. Now one epic family crowds out the whole
pricing-engine catalogue. The IMPORTANT items in `PRODUCT_DIRECTION_2026-07-24`
(#2, #4, #6, #7, #11) have waited **108 days** without being touched.

---

## 2. Where the Product Stands

**Pricing engine: production-ready across the modelled surface, and frozen since
2026-08-04.** Shipped and complete (see `PRODUCT_DIRECTION_2026-07-24`, "What Has
Shipped"):

- Term, whole life, UL, DI/CI and annuity products
- YRT, coinsurance, modco, stop-loss and funds-withheld coinsurance treaties
- Reserve bases: CRVM, VM-20 simplified, GAAP
- IFRS 17 movement table
- LICAT, RBC and Solvency II capital
- Asset/ALM base
- Expense allowance and experience refund
- Portfolio aggregation, lifecycle, cache and parallel execution
- Validation pack
- Production hardening: auth, rate limit, metrics, K8s/Helm
- Cedant ingestion
- MCP server (the first Phase-7 epic, closed 2026-07-31)
- CI smoke job and per-merge perf history

**Experience/assumption layer: well ahead of the market, and still moving.** The
mgcv-parity GAM stack gives:

- `gam`/`bam` with `cr`/`tp`/`re`/`ti`, factor-by and `select=TRUE`
- quasi-Poisson
- Wood-2011 REML with a Newton outer solver

It has INDEPENDENT tier-3 parity evidence. It is now wired into the dashboard
(D1/D2), with S1 in review. That work is owned and sequenced by its own routine,
and **this review does not re-rank it**.

**What a paying reinsurer would still miss, in order of how often it would come up:**

1. **No run history or audit trail.** A priced deal cannot be found again,
   compared with an earlier run, or tied to the assumption and code versions that
   produced it. Each run is a JSON file on someone's disk. CLAUDE.md §1 lists
   "Transparent — every cash flow output carries full metadata" as a design
   principle. That principle holds within one run but stops at the run boundary.
   This is the "team of actuaries, not one" layer raised in both earlier reviews
   (2026-07-15 §7, 2026-07-24 Decision Surfaced). It has never been started.
2. **A known artefact on the default whole-life reserve basis.** On
   `NET_PREMIUM`, whole life still values from a one-period terminal estimate, and
   that estimate collapses at the horizon. This review checked the code today:
   `products/whole_life.py:270-290` documents that the CRVM, VM-20 and GAAP paths
   value to omega and "close" the artefact, while NET_PREMIUM "is left
   byte-identical". It is IMPORTANT #2 in the ledger. It has been open since
   ADR-089 (June) and is a correctness issue on the **default** path.
3. **Multi-replica correctness of shipped ops features.** The rate limiter and the
   metrics registry are per-process (IMPORTANT #6 and #7). Behind N replicas the
   effective limit is about N times the configured threshold.
4. **No stochastic economic layer.** There is no ESG and no nested stochastic, so
   there is no VM-21/PBR stochastic reserve and no economic capital beyond factor
   and shock methods.
5. **No GMxB or group business.** These are the largest un-modelled liability
   classes.
6. **AXIS/Prophet reconciliation** is still REFERENCE-BLOCKED.

---

## 3. Is there a genuine next Tier-A epic for daily-dev? Yes: Deal and Run Persistence with an Audit Trail

The 2026-07-15 and 2026-07-24 documents both listed four Phase-7 candidates. The
maintainer picked the MCP server from outside that list (2026-07-27), and it
shipped. The other four are still open. Re-ranked today against what a client
would hit first and against what an **autonomous** routine can deliver safely:

| Candidate | Client value | Autonomy-safe? | Contention with the mgcv routine | Verdict |
|---|---|---|---|---|
| **Deal and run persistence / audit trail** | ★★★★☆: daily friction for every user; needed before a team can adopt the tool | **Yes**: data engineering, no actuarial judgement; goldens byte-identical (additive) | **None**: touches `core/`/CLI/API/a new dashboard page, not `gam/` or the experience-improvement page | **A5′, next epic** |
| Stochastic ESG + nested stochastic (VM-21 / economic capital) | ★★★★☆ | **Partly**: calibration choices (real-world vs risk-neutral, Hull–White/CIR parameters, scenario count, CTE level) are modelling judgements the maintainer should own | Low | A6′: constitute **after** the maintainer specifies the calibration basis |
| GMxB annuities / group business | ★★★★☆ | Partly; GMxB depends on A6′ (stochastic equity paths) | Low | A7′: after A6′ |
| AXIS/Prophet side-by-side | ★★★★★ external credibility | No: needs a licensed reference output | None | REFERENCE-BLOCKED |

**Why A5′ leads.**

- **It is the most-requested missing layer.** It comes up on every use, not only
  on particular deals.
- **It has no open actuarial questions.** The routine does not need to guess.
- **It does not collide with the mgcv routine.** Both routines can advance one
  slice a day without editing the same files.
- **It builds on patterns the repo already has:**
  - the versioned improvement-basis store (ADR-148, `load_improvement_version`)
  - measurement provenance stamps (ADR-204)
  - `VerificationClaim`-style typed metadata (ADR-193)
  - the CLI JSON `-o` schema

  A run record is these pieces put together: config hash, inforce hash,
  assumption and improvement version ids, package version and git SHA, timestamp,
  user (API key id), and the outputs.
- **It makes the next epics cheaper.** A6′ scenario runs and AXIS reconciliation
  both need a place to keep and diff runs.

---

## 4. Feature Catalogue: re-ranked for 2026-11-09

Value is judged against a paying reinsurance client. Effort is in developer-days.
**GAM/mgcv items are excluded** because the mgcv routine owns and ranks them (see
`ROUTINE_MGCV_PARITY.md` and the GAM plans).

### Tier A: high value, multi-session

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| **A5′** | **Deal and run persistence with an audit trail.** A run-record contract and a local store (SQLite by default, path configurable); `polaris price --record` / `polaris runs list/show/diff`; REST `GET /api/v1/runs[/{id}]`; a dashboard "Run history" page; diff of two runs by metric and by assumption version. | ★★★★☆ | ~5–6 d | 4 | 2026-07-15 §7 / 2026-07-24 Phase-7 list ("multi-user / persistence / audit"); CLAUDE.md §1 "Transparent" |
| A6′ | Stochastic ESG and nested-stochastic reserve/capital (VM-21 SR, CTE). Extends `analytics/stochastic.py` and the asset/ALM base. | ★★★★☆ | ~8–10 d | 4–5 | Phase-7 list; ADR-090 (VM-20 SR out of scope); ADR-108 |
| A7′ | GMxB variable/indexed annuity riders | ★★★★☆ | ~10+ d | 5 | Phase-7 list; depends on A6′ |
| — | AXIS/Prophet reconciliation (validation Slice 4) | ★★★★★ | — | — | REFERENCE-BLOCKED |

### Tier B: high value, single-to-short (Sprint-0 / between-slice quick wins)

| # | Feature | Value | Effort | Source |
|---|---------|-------|--------|--------|
| **B5** | **Close the WL terminal-reserve artefact on the default NET_PREMIUM basis**: prospective-to-omega valuation, the same as the CRVM path. Moves goldens, so it needs an ADR and an explained rebaseline. | ★★★★☆ | ~1–2 d | IMPORTANT #2 (ADR-089); premise re-checked 2026-11-09 |
| B6 | **Shared rate-limit backend** (optional Redis behind the existing `SlidingWindowRateLimiter` interface; in-process stays the default) | ★★★☆☆ | ~1–2 d | IMPORTANT #6 (ADR-134) |
| B7 | **Milestone 6.3 quality gate**: load test (100 concurrent `/api/v1/price` < 2 s) and a QUICKSTART K8s/observability guide. This is the last unchecked box in the written roadmap's Phase 6. | ★★★☆☆ | ~1–2 d | ROADMAP 6.3 (was C6) |

### Tier C: medium value, enabling or operational

| # | Feature | Value | Effort | Source |
|---|---------|-------|--------|--------|
| C5 | Per-deal hurdle rates on `Portfolio` | ★★★☆☆ | ~5 d | CONT-portfolio #4 |
| C7 | Shared metrics backend (remote-write / multiprocess) | ★★☆☆☆ | ~1–2 d | IMPORTANT #7 (ADR-135) |
| C8 | PDR per-period roll-forward of the reserve floor | ★★★☆☆ | ~2 d | ADR-162 harvest (IMPORTANT) |
| C9 | Decompose the `polaris_re.pipeline` composition root | ★★☆☆☆ | ~1 d | ADR-156 Out of scope |

### Tier D: exactness polish / low value (deprioritise)

- The interest-exactness helper (`reserve_basis_correctness`, PARKED).
- The ~90 NICE-TO-HAVE items carried in `PRODUCT_DIRECTION_2026-07-24`, which are
  grouped by theme there.
- Item IMPORTANT #11 (confirm the ADR-141 backend deviation) is a maintainer
  confirmation, not dev work. It is listed in §7.

### The picture in one view

```
        HIGH VALUE
            │  A5' run persistence/audit  ◄ next epic      B5 WL NET_PREMIUM artefact
            │  A6' stochastic ESG (needs calibration spec)  B6 shared rate limit
            │  A7' GMxB (after A6')                         B7 6.3 load-test gate
   ─────────┼──────────────────────────────────────────────────────────────
            │  C5 per-deal hurdle            C8 PDR roll-forward
            │                                C7 metrics backend, C9 pipeline split
        LOW │                                [Tier D: interest exactness, polish]
            └──────────────────────────────────────────────────────────────
              HIGH EFFORT                                     LOW EFFORT
       (AXIS/Prophet: reference-blocked — off-grid;  GAM/mgcv: owned by its own routine)
```

---

## 5. Verdict and Recommended Sequence

**Verdict:** the daily-dev routine should stop yielding its slot. **Constitute A5′
(deal and run persistence with an audit trail) as daily-dev's active epic**, in
parallel with, and without touching, the mgcv routine's GAM epic.

1. **Next daily-dev session:** write `docs/PLAN_run_persistence.md` using the slice
   outline in §6. Open `docs/CONTINUATION_run_persistence.md` (IN PROGRESS) and
   ship **slice 1**. That is the session's whole deliverable (step 5b(b)).
2. **Between A5′ slices**, while a slice PR waits for merge: B5 first. It has the
   highest value per day, and it is a correctness fix on the default path.
   Then B7, then B6.
3. **Before A5′ closes:** the maintainer specifies A6′'s calibration basis (§7 Q2).
   That way the next epic can be constituted without the routine guessing at
   actuarial choices.

**This session's deliverable is this review.** Re-ranking after a 117-day gap is
the substantial analytical task that step 6 allows to stand alone. A5′ slice 1
ships next run.

---

## 6. A5′ suggested decomposition (for next session's PLAN; Pattern A then B)

Each slice is additive. Every slice must leave `polaris price` output and all QA
goldens **byte-identical**, because recording is opt-in.

- **Slice 1: run-record contract and store (library only).**
  - `core/run_record.py`: a `RunRecord` (`PolarisBaseModel`) with these fields:
    - `run_id`
    - `created_at` (injected, never `datetime.now()` in tests: ADR-074)
    - `polaris_version`, `git_sha`
    - `config_sha256`, `inforce_sha256`
    - `assumption_ids`, `improvement_version`
    - `treaty_type`, `reserve_basis`
    - `summary_metrics`
    - `output_path`
  - An `analytics/` or `utils/` `RunStore` with an SQLite backend: `save`, `get`,
    `list(filter)`.
  - Round-trip and immutability tests, and a hash-stability test.
  - Not yet called from the CLI.
- **Slice 2: CLI surface.**
  - `polaris price --record [--store PATH]`.
  - `polaris runs list | show ID`.
  - Off by default, so goldens stay byte-identical.
  - A test asserts that a recorded run's `summary_metrics` equal the CLI `-o`
    JSON. This is a **TRANSPORT** check, labelled as one. It is a round-trip
    test, not evidence that any figure is correct.
- **Slice 3: diff and API.**
  - `polaris runs diff A B`: per-metric deltas, plus which inputs changed (config
    hash, inforce hash, assumption and version ids, code version).
  - REST `GET /api/v1/runs`, `GET /api/v1/runs/{id}`, scoped by API key id.
  - An optional `record: bool` on `PriceRequest`, defaulting to false.
- **Slice 4: dashboard "Run history" page and docs (closes the epic).**
  - The page: list, inspect, compare.
  - `DealConfig.to_dict()` round-trip.
  - ADR, ARCHITECTURE and QUICKSTART updates.
  - If any test reads a store fixture under `data/`, update the Dockerfile COPY
    and the `.dockerignore` allowlist in the same PR (the #61/#66 trap).

**Open design questions** for the PLAN to settle or put to the maintainer:

- SQLite or Parquet-plus-index. SQLite is recommended: it is stdlib and
  transactional.
- Whether to store full cash-flow vectors or a summary plus an output-file
  pointer. Summary plus pointer is recommended for slice 1.
- How "user" is identified without an auth backend: the API key id, or
  `$USER`/`--user` on the CLI.

---

## 7. Decisions Surfaced for the Maintainer

> **Q1: Do the two routines run in parallel, each with its own active epic?**
> `ROUTINE_MGCV_PARITY.md` §Budget ("replaces daily-dev's slot … only one of them
> has work to do") and daily-dev step 5b (exclude the external epic and treat the
> slot as empty) disagree. In practice this has meant daily-dev added no
> pricing-engine features for ~97 days.
> **Recommended:** run them in parallel and amend the mgcv routine's §Budget line
> to match. The two epics share no files. If you would rather daily-dev keep
> yielding, say so, and the next session will log "maintenance mode, yielded to
> mgcv" and do only Tier-B work.

> **Q2: A6′ calibration basis.** Before a stochastic ESG epic can be constituted
> autonomously, someone has to fix the modelling choices the routine must not
> guess:
> - real-world or risk-neutral (or both, for nested)
> - the rate model (Hull–White 1F or CIR)
> - the equity model, if GMxB follows
> - the scenario count and seed policy
> - the CTE level (VM-21: CTE 70)
>
> **Recommended:** a one-paragraph spec on the A5′ PRs. The routine will write
> `PLAN_stochastic_esg.md` from it when A5′ closes.

> **Q3 (carried, IMPORTANT #11): confirm the ADR-141 backend deviation.** This is
> the pure-NumPy reduced-rank GP in place of `bambi`/`pymc`. The older
> experience-GAM is now scheduled for deprecation under ADR-264 (R1–R3), so the
> likely answer is "moot, close it". It is listed here so the ledger can be
> closed.

---

## 8. Reconciliation with `PRODUCT_DIRECTION_2026-07-24`

The latest ledger is 108 days old. This review does **not** regenerate it. The
ledger is the nightly routine's reasonability authority, and this session
promotes no new work items. A5′/A6′/A7′ are the 2026-07-24 file's own Phase-7
candidates being ranked, not new items. B5, B6, B7, C5, C7, C8 and C9 are
existing ledger entries (IMPORTANT #2, #6, #7, the ADR-162 harvest, ROADMAP 6.3,
C5, ADR-156), now ordered by value per day.

Ledger healing (step 4b): the PRs merged since the last session log are #279,
#281 and #282, and none of them corresponds to a `PRODUCT_DIRECTION` entry. #279
and #282 are GAM-track work tracked in that routine's plans. #281's R-items live
in ROADMAP "Dashboard UX Backlog", not in the ledger. So there is nothing to
strike through.

**Note for the next regeneration of `PRODUCT_DIRECTION`.** When the next session
harvests a follow-up (step 17 requires a new file once the latest is more than
30 days old), it should:

- list the C4 portfolio-execution and MCP server epics, and the GAM track's
  merged epics, as shipped since the prior file;
- carry forward the 12 IMPORTANT + 90 NICE-TO-HAVE items;
- adopt this review's ordering.
