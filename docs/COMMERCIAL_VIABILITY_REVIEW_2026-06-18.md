# Commercial Viability Review — 2026-06-18

## Purpose

This document does three things the daily-dev routine has stopped doing on
its own:

1. **Reviews the last 10 merged PRs (#69–#78)** and the supporting
   documentation, and names the pattern they reveal.
2. **Catalogues the remaining features that move Polaris RE toward
   commercial viability**, ranked on two axes — *expected effort / time to
   complete* and *intrinsic value to a paying reinsurance client*.
3. **Proposes a workflow change** so the daily-dev routine stops producing
   sub-day polish and starts driving the larger, higher-value features
   across staggered phases. The routine mechanics live in the companion
   `docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-06-18.md`.

It is a strategic / direction document, not a reasonability assessment.
The canonical reasonability baseline remains
`docs/PRODUCT_DIRECTION_2026-04-19.md`.

---

## 1. Review of the Last 10 PRs (#69–#78)

| PR  | ADR | Theme | One-line scope | Est. size |
|-----|-----|-------|----------------|-----------|
| #69 | 077 | Perspective | `perspective` param on `ScenarioRunner` / `MonteCarloUQ` + CLI default `reinsurer` | <1 day |
| #70 | 078 | Perspective | Same `perspective` plumbed to the scenario/uq **API + dashboard** | <1 day |
| #71 | 079 | Perspective/YRT | `--yrt-rate-table` flag on `scenario` / `uq` (mirror of `price`) | ~½ day |
| #72 | 080 | Excel | Write "Gross" / "Ceded" cash-flow sheets in deal-pricing workbook | ~1 day |
| #73 | 081 | Excel | Add a combined Gross/Ceded/Net **comparison sheet** | ~½ day |
| #74 | 082 | Sufficiency | `PremiumSufficiencyTester` library primitive | ~1 day |
| #75 | 083 | Sufficiency | Surface sufficiency across CLI / API / dashboard / Excel | ~1 day |
| #76 | 084 | Sufficiency | Per-line-item sufficiency breakdown (Excel + dashboard) | ~½ day |
| #77 | 085 | Sufficiency | Per-line-item sufficiency breakdown on the CLI Rich table | ~½ day |
| #78 | 086 | Excel | Per-line-item Gross/Ceded/Net comparison sheet | ~½ day |

### What the table shows

Ten PRs collapse into **three conceptual themes**:

- **Perspective plumbing** (#69–#71): one decision — "report the reinsurer
  view by default" — spread across the runner, then the API/dashboard, then
  a flag mirror. Three PRs.
- **Deal-pricing Excel sheets** (#72, #73, #78): one sheet, then a
  comparison of that sheet, then a per-line-item version of the comparison.
  Three PRs of escalating granularity.
- **Premium sufficiency** (#74–#77): a library primitive, then surfacing it,
  then a line-item breakdown, then the same breakdown on one more surface.
  Four PRs.

Every PR is correct, tested, additive, and byte-identical on existing
goldens. **That is not the problem.** The problem is the *granularity*: the
median PR is roughly half a developer-day, and each one tends to **spawn its
own follow-up** (a comparison sheet invites a per-line-item comparison sheet
invites a merged-header comparison sheet). The work queue is growing faster
than it shrinks, and it is growing in the *polish* direction.

### Root cause — why the routine keeps picking small

This is structural, not accidental. Two mechanics in the current routine
combine into a "polish spiral":

1. **The harvest-follow-ups step** (`DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-05-23.md`,
   Change 1) promotes *every* ADR "Out of scope" note into the work queue
   when a CONTINUATION closes. This was the right fix for *losing* follow-ups
   — but it means each shipped feature deposits 2–3 fresh micro-items. The
   queue is now dominated by self-generated polish.

2. **The single-session selection bias.** `PRODUCT_DIRECTION_2026-05-23.md`
   states the rule explicitly: *"No IMPORTANT item remains that fits a single
   session. The two surviving IMPORTANT items … are 10 dev-days each … and
   should be scoped as a dedicated roadmap entry rather than picked up
   mid-sprint."* The routine then falls back to the "well-stocked … sub-day
   to 3-day" NICE-TO-HAVE queue every time. Large items are *never* started
   because no single session can finish one, and nothing decomposes them.

The net effect: the two genuinely important remaining features
(**reserve-basis matching** and the **IFRS 17 movement table**) have sat
untouched since at least 2026-04-19 while ten consecutive PRs refined Excel
sheets and premium-sufficiency surfacing. The routine is doing exactly what
it was told to do; it was told to prefer small.

---

## 2. Where the Product Actually Stands

Polaris RE is genuinely capable. Phases 1–4 are complete (726 tests, ~94%
coverage). The engine can, today:

- Project TERM / WL / UL / Disability-CI seriatim, vectorised `(N×T)`.
- Apply YRT (flat **and** tabular age×duration), Coinsurance, Modco, Stop-Loss.
- Profit-test (IRR / PV / margin / break-even) with reporting guardrails.
- Scenario + Monte Carlo UQ, with a reinsurer/cedant perspective switch.
- IFRS 17 BBA / PAA / VFA **point-in-time** measurement.
- LICAT capital + return-on-capital (Canada; with interim C-1/C-3 factors).
- Portfolio aggregation (calendar-aligned, concentration, capital, scenarios).
- Per-policy substandard rating; cedant data ingestion; ML mortality/lapse.
- Ship a committee-grade Excel workbook and run via CLI / FastAPI / Streamlit.

The 2026-04-19 verdict — **"Commercial Readiness: Partial"** — still holds,
but the boundary has moved. All four original BLOCKERs (WL expense bug,
substandard rating, LICAT capital, deal Excel) shipped. The remaining gap is
no longer "can it price a first deal" — it can — it is **"can it stand up to
a sophisticated buyer's diligence across jurisdictions and into production."**

---

## 3. Feature Catalogue — Ranked by Value × Effort

Each candidate is drawn from the ROADMAP (Phases 5–6), the two
PRODUCT_DIRECTION files, and the 2026-04-19 gap analysis. Value is judged
against a paying reinsurance client (pricing actuary, CRO/CFO, IT/ops).
Effort is in developer-days; "phases" is the recommended number of staggered
slices.

### Tier A — High value, multi-session (the missing "big rocks")

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| A1 | **Reserve-basis matching** (CRVM, VM-20 simplified, GAAP) — reproduce the *cedant's* reserves, not just net-premium; also closes the WL terminal-reserve artefact (see below) | ★★★★★ | ~10 d | 3–4 | PD-04-19 IMPORTANT |
| A2 | **IFRS 17 period-to-period movement table** — opening→experience→unwinding→closing by annual cohort, locked-in rates | ★★★★★ | ~10 d | 3 | ROADMAP 5.3 |
| A3 | **US RBC + Solvency II capital modules** — RoC for US/EU clients (LICAT is Canada-only today) | ★★★★★ | ~15 d (both) | 4 | PD-04-19 BLOCKER (RBC) |

**Why these three first.** A1 and A2 are the only two items both
PRODUCT_DIRECTION files have carried as IMPORTANT for two months without
progress. A reinsurer that cannot reproduce the cedant's statutory reserve
basis cannot trust the profit number — this is the single biggest *credibility*
gap. A3 is a hard *market-access* gate: the engine cannot quote a US or EU deal
on a return-on-capital basis at all today (confirmed worth retaining by the
maintainer, 2026-06-18; the 2026-04-19 baseline rated US RBC a BLOCKER). The
**Asset / ALM model** (formerly listed here as A4) is a genuine big rock but a
*lower-priority* one — Modco prices on a fixed credited rate today, so the
engine is usable without it — and has been moved to Tier C (C0) to be scheduled
after these three (maintainer direction, 2026-06-18).

> **Folded-in flag — WL prospective terminal reserve.** The nightly
> `PRODUCT_DIRECTION_2026-06-18` surfaced a concrete reasonability artefact:
> on the golden WL block the reserve declines from $7.18M (yr 10) to **$56k
> (yr 20)** on a $25M permanent block — an ARCHITECTURE §4 horizon-edge
> limitation a deal-committee actuary would query. This is **the same body of
> work as A1**: a true prospective / cedant-reproduced WL reserve basis should
> close the artefact. It is therefore a named **acceptance test inside Epic 1**,
> not a standalone item.

### Tier B — High value, single-to-short (quick credibility wins)

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| B1 | **Switch capital surfaces to `for_product_interim`** — expose the already-built C-1/C-3 factors everywhere | ★★★★☆ | ~1–2 d | 1 | ADR-072 |
| B2 | **Scale benchmark at 100K–500K policies** — publish a timing table; back the README's performance claim | ★★★★☆ | ~1 d (+perf if it fails) | 1 | PD-04-19 NICE |
| B3 | **Sliding-scale expense allowances / experience refunds** (`reinsurance/expense_allowance.py`) — standard in large YRT deals | ★★★★☆ | ~3 d | 1–2 | PD-04-19 NICE |
| B4 | **Premium-deficiency reserve / loss recognition** — turn the new sufficiency analyzer into a reserve floor | ★★★☆☆ | ~1–2 d | 1 | ADR-082 |

### Tier C — Medium value, enabling / operational

| # | Feature | Value | Effort | Phases | Source |
|---|---------|-------|--------|--------|--------|
| C0 | **Asset / ALM model** (`core/asset.py`) — bond cash flows, investment income, duration/convexity; completes Modco economics and embedded value. *Big rock, but lower priority than A1–A3 — Modco works on a fixed credited rate today (maintainer direction, 2026-06-18). Schedule after the three Tier-A epics.* | ★★★★☆ | ~20 d | 4 | ROADMAP 5.4 |
| C1 | **Production hardening & observability** — API auth, rate limiting, structured logging, K8s/Helm | ★★★☆☆ | ~8 d | 3 | ROADMAP 6.2 |
| C2 | **Experience-monitoring automation loop** — study→export→retrain; the ML self-improvement story | ★★★☆☆ | ~6 d | 2–3 | ROADMAP 6.1 |
| C3 | **Funds-withheld coinsurance** (`FWCoinsuranceTreaty`) | ★★★☆☆ | ~2 d | 1 | PD-04-19 NICE |
| C4 | **Parallel portfolio execution + caching + `remove_deal`** — 50+ deal books | ★★★☆☆ | ~2 d | 1 | CONT-portfolio #6 |
| C5 | **Per-deal hurdle rates on `Portfolio`** — aggregate PV at differing discount rates (design redesign) | ★★★☆☆ | ~5 d | 2 | CONT-portfolio #4 |

### Tier D — Low value / polish (the current default — deprioritise)

Everything the last 10 PRs were drawn from: merged-cell Excel headers,
per-sheet perspective captions, dimension-outer transposes, additional
sufficiency surfaces on scenario/uq, dashboard upload-flow keys, warm-start
`brentq`, per-duration cell interpolation, etc. These are real and harmless,
but they are **fallback work**, not direction. They should only be picked
when a session genuinely cannot advance a Tier A–C epic.

### The picture in one view

```
        HIGH VALUE
            │  A3 RBC/SolvII      A1 Reserve basis
            │  (C0 Asset/ALM*)    A2 IFRS17 movement
            │                     B1 capital surfaces
            │  C1 hardening       B2 scale benchmark
            │  C2 experience loop B3 expense allowances
   ─────────┼──────────────────────────────────────── 
            │  C5 per-deal hurdle B4 deficiency reserve
            │  C4 parallel        C3 funds-withheld
            │                     [Tier D polish]
        LOW │
            └──────────────────────────────────────────
              HIGH EFFORT                    LOW EFFORT

  * C0 Asset/ALM is high-value/high-effort but deliberately scheduled
    AFTER the three Tier-A epics (Modco is usable without it today).
```

Upper-right (high value, low effort) = **do now**: B1, B2.
Upper-left (high value, high effort) = **schedule as epics**: A1–A3 first,
then C0 (Asset/ALM).
Lower-right = opportunistic fill: B4, C3.
Lower-left = only with a deliberate decision: C5.

---

## 4. Recommended Sequence (Staggered Epics)

The intent is to interleave one **epic** (Tier A, multi-session, plan-driven)
with occasional **quick wins** (Tier B), and reserve Tier D only as filler.

**Sprint 0 — clear the quick credibility wins (≈ 1 week)**
- B1 — switch capital surfaces to `for_product_interim` (with golden
  rebaseline + an ADR; it is a behaviour change).
- B2 — publish the 100K/500K scale benchmark.

**Epic 1 — Reserve-basis matching (A1), ~3–4 sessions**
1. `ReserveBasis` enum + plumbing through `ProjectionConfig`; net-premium
   stays the default → byte-identical goldens.
2. CRVM concrete basis + closed-form test vs a worked example.
3. VM-20 (simplified PBR) basis + test.
4. Surface the basis selector on CLI / API / Excel; validation notebook.

**Epic 2 — IFRS 17 movement table (A2), ~3 sessions**
1. `IFRS17CohortManager` (annual cohorts, locked-in rate).
2. `IFRS17MovementTable` (opening→…→closing) with the additivity test.
3. `POST /api/v1/ifrs17/movement` + Excel/CLI surfacing.

**Epic 3 — Cross-jurisdiction capital (A3), ~4 sessions**
- US RBC (C-0…C-4) first (largest market), then Solvency II SCR, sharing the
  `CapitalModel` protocol LICAT already established.

**After the ladder — Asset / ALM (C0), ~4 sessions**
- Deliberately *not* one of the three lead epics (maintainer direction,
  2026-06-18): Modco works today on a fixed credited rate, so the engine is
  usable without it. Scheduled after Epics 1–3, where it upgrades Modco from
  "approximate" to "correct" and unlocks embedded value. Run it as a fourth
  epic once the three credibility/market-access gaps are closed.

Tier B3/B4 and Tier C items slot between epics as single-session picks when
an epic is blocked or a session is time-boxed.

---

## 5. The Workflow Change (summary)

The detailed routine edits are in
`docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-06-18.md`. In brief:

1. **Add an "Epic" track.** The routine must always have exactly one active
   epic (a Tier-A feature with a written multi-slice `PLAN_*.md`, in the same
   style as `docs/PLAN_dashboard_portfolio.md`). Each daily session advances
   the active epic's next slice *before* it is allowed to pick fallback work.

2. **Decompose, don't defer.** The "this is 10 dev-days, scope it as a
   dedicated roadmap entry" escape hatch is removed. When the top-ranked item
   is large, the session's job is to write/append its PLAN and ship slice 1 —
   not to skip it for a sub-day item.

3. **Cap the polish spiral.** A follow-up that is itself a follow-up of a
   follow-up (third-order polish) is not auto-promoted to the work queue; it
   is logged but parked. A session may pick Tier-D polish only when the active
   epic is genuinely blocked, and must say so in the session log.

4. **Re-rank monthly against this document.** This review (value × effort)
   becomes an input to selection alongside PRODUCT_DIRECTION, so "smallest
   available" stops being the default tiebreaker.

---

## 6. Bottom Line

Polaris RE crossed the "can it price a first deal" threshold a month ago. The
last ten PRs added genuine polish but did not move the commercial needle,
because the routine is optimised to finish *something* every session rather
than to advance the *highest-value* thing across sessions. The three Tier-A
epics — reserve-basis matching, IFRS 17 movement, and US/EU capital — are what
a sophisticated buyer will probe in diligence, followed by the Asset/ALM model
once those gaps close; none can be done in a single session. The recommended
fix is an epic-driven routine that decomposes large features into staggered
slices and treats the sub-day polish queue as fallback, not as the main road.

---

## 7. Reconciliation with the nightly `PRODUCT_DIRECTION_2026-06-18`

This review and the routine-authored nightly `PRODUCT_DIRECTION_2026-06-18.md`
(PR #79) were produced independently the same day. They **agree on the
destination** — both name Reserve-basis matching and the IFRS 17 movement
table as the enduring IMPORTANT gaps, both put Reserve-basis matching first,
and the nightly even concludes it is "the highest-impact direction shift
available." They **disagreed on the route**, and that disagreement is resolved
in this revision (maintainer direction, 2026-06-18):

| Point | Nightly (as merged) | This review / resolution |
|---|---|---|
| Next-step prescription | "pick the cleanest small win on the freshest thread" | **Epic-first**: advance one decomposed IMPORTANT epic per session before any fallback pick |
| Ranking method | single scalar `impact × (1/effort)` (rewards smallest) | 2-D value × effort (separates "do-now small" from "schedule-as-epic large") |
| Big items | "out of scope for single-session pickup → dedicated roadmap slot" | **Decompose, don't defer** — driven through daily-dev as `PLAN_*` + `CONTINUATION_*` slices |
| US RBC / Solvency II | dropped from gap analysis | **Restored to IMPORTANT** (A3); maintainer confirmed worth retaining |
| Asset / ALM | not surfaced as a gap | Big rock but **lower priority** (C0); scheduled after A1–A3 |
| WL terminal reserve | free-floating NICE-TO-HAVE sub-item | **Folded into Epic 1** as a named acceptance test |

The corrections above have been applied directly to
`PRODUCT_DIRECTION_2026-06-18.md` in this same change, so the nightly doc and
this review now agree on both destination and route.
