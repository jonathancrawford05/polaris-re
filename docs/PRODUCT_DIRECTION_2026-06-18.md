# Product Direction — 2026-06-18

## Reasonability Assessment

The nightly regression suite is **clean**: 1,476 unit tests + 72 QA tests + all
four golden configs (`yrt`, `coins`, `policy_cession`, `flat`) reproduce their
committed baselines within the standing ±$500 / ±0.5 pp tolerance. Coinsurance
additivity (`net + ceded == gross` per line item, per year) holds for both
treaty types to floating-point precision (`max drift < 1e-3` across premiums,
claims, surrenders, expenses, reserve increase, and NCF).

The golden block headlines pass the actuarial smell test for a deliberately
stressed test population (mixed standard / smoker / SUBSTANDARD, $3.3M TERM
face + $25.5M WL face, no select credit, 6% discount, 10% hurdle):

- **YRT 90% cession on TERM ($3.3M face):** cedant PV profits **-$83,902**,
  IRR **-2.6%**, profit margin **-3,741%** (the very small PV-premiums base of
  ~$2.2k makes the margin ratio uninformative — IRR is the right read). The
  cedant retains 10% of an underwater claim curve plus full acquisition
  ($500/policy) and maintenance ($75/policy/yr) expenses, so a small negative
  PV is the expected sign.
- **YRT 90% cession on WL ($25.5M face):** cedant PV profits **-$1.34M**,
  IRR **5.3%** (below the 10% hurdle), profit margin **-46%**. Reinsurer PV
  profits **-$4.32M**, profit margin **-594%**. The reinsurer loss is
  structural, not a bug: `derive_yrt_rate` produces a single **flat** rate per
  $1000 from gross cash flows, and a flat rate cannot match the
  steeply-rising-with-age claim profile of a 20-year WL projection (claims rise
  from $143k in yr 1 to $1.51M in yr 15 — a ~10× rise). The per-duration YRT
  rate solver (ADR-063 / ADR-067) is the structural fix; the golden YRT config
  does not consume it.
- **Coinsurance 50% on TERM / WL:** net + ceded = gross by construction so the
  cedant and reinsurer PV profits are identical
  (TERM **-$90,140**, WL **-$2.83M**). The two sides taking the same loss on an
  underwater block is the expected algebraic outcome on a proportional treaty.
- **Flat 0.3% mortality YRT 90% cession (CI-safe, no SOA):** the reinsurer PV
  is a near-zero **+$596** on TERM and a healthy **+$44,791** on WL (margin
  7.8%) — within the typical YRT 5-15% margin band when actuals match pricing.
  Cedant TERM PV is **-$35,292** but cedant WL is **+$3.55M** (the cedant
  retains 10% of a profitable block), break-even year 1, margin 98% — the
  textbook "cession on a profitable block leaves cedant healthy and reinsurer
  with a thin loaded margin" pattern.

The two negative PV blocks (the SOA-VBT-based YRT and coins configs) are
working as designed for a stress-test golden; the flat config is the one a
pricing actuary would point to as the "deal-committee-presentable" reasonable
output, and it lands inside industry norms.

## Cash Flow Shape Review

**TERM cohort (gross, YRT config):**

- ✓ **Reserves hump-shaped:** build from $18.5k (yr 1) to peak $147k (yr 11),
  release to **$0 at yr 20** — textbook term life reserve trajectory.
- ✓ **Claims rise then drop:** $5.6k (yr 1) → $51.6k (yr 15), then a sharp
  drop to $24.5k (yr 16) — the 10-yr and 15-yr term policies expire at yr 5
  and yr 10 respectively, the SUBSTANDARD F smoker (10-yr) and remaining
  short-term policies expire by yr 15.
- ✓ **Premiums decline:** $5.6k (yr 1) → $1.2k (yr 20) — tracks the
  select-and-ultimate lapse table (high early lapses, 1.5% ultimate) plus
  expiry.
- ✗ **NCF stays negative through all 20 years** for the cedant: -$17.8k (yr 1)
  through -$6.6k (yr 20). The acquisition + maintenance expenses ($500 + $75)
  plus claims dominate the small net premium stream. Combined with 90%
  cession, the cedant's retained 10% of claims still outruns the retained 10%
  of premiums. Not a bug — the block was constructed to stress-test, not to
  be a profitable book. Worth noting because the routine asks us to flag NCF
  that "should turn positive for profitable deals" — these are not profitable
  deals.

**WL cohort (gross, YRT config):**

- ✓ **Claims increase with attained age:** $143k (yr 1) → peak $1.51M (yr 15)
  — a ~10× rise consistent with mortality acceleration as the block ages from
  attained 35-60 (per `golden_inforce.csv` issue ages) into the 55-80 band.
- ✓ **Reserves build through yr 10:** $1.78M (yr 1) → peak **$7.18M (yr 10)**
  — monotone build during the active period.
- ⚠ **Reserves decline after yr 10:** the reserve balance falls from $7.18M
  (yr 10) to **$56k (yr 20)**. ARCHITECTURE.md §4 documents this as a known
  modelling limitation: the WL reserve uses the prospective terminal estimate
  `V_T = face × q_T × v` at the projection horizon, so backward recursion from
  a small terminal value gives reserves that decline as the horizon edge
  dominates. A true permanent-pay block at the same horizon would carry a
  much higher closing reserve (the in-force WL block at yr 20 still owes
  benefits to surviving policyholders). This is **not a deal-breaking
  finding** — Phase 3 was scheduled to extend to true prospective reserves and
  it is the same limitation that's been visible on every prior nightly. Flag
  here only because the routine asks us to surface anything a deal-committee
  actuary would question, and "reserves at end of horizon = $56k on a $25M
  permanent block" is one of them. Workaround for nightly reasonability:
  extend the projection horizon well past the youngest insured's age-120.
- ✓ **Premiums decline:** $537k (yr 1) → $80k (yr 20) — tracks
  lapse + mortality decrement.
- **NCF strongly negative throughout** the projection. At cession 90% YRT on
  a block where claims are 2-10× premiums, the cedant retains 10% of an
  underwater P&L plus full expenses. As above, this is a block-construction
  outcome, not a code defect.

**Lapse-driven inforce runoff (both cohorts):**
The lapse table in all four configs is select-and-ultimate (6% / 5% / 4% / 3.5%
/ 3% / 2.5% / 2% × 4 / 1.5% ultimate). Premium decay between yr 5 (TERM:
$5.0k → $3.7k, a -27% step) and yr 10 (TERM: $3.3k → $3.1k, a -7% step)
reflects the select-period drop at yr 6 (3.0% → 2.5%) and yr 10 (2.0% → 1.5%
ultimate) — consistent with the configured curve.

**YRT premium pattern vs expected mortality progression:**
The reinsurer ceded YRT premium on WL declines monotonically ($133k yr 1 →
$18.7k yr 20) — tracking NAR × flat rate × in-force. But the ceded death claims
rise from $128k (yr 1) to $1.36M (yr 15) before declining. The mismatch between
falling premiums and rising claims is the structural flag noted above (flat
YRT rate vs rising mortality). On TERM the same pattern is muted because the
underlying gross claim curve does rise then fall (terms expire).

## Commercial Readiness: **Partial → Production-ready for Single-deal Pricing**

For **single-deal reinsurance pricing on TERM + WL with YRT / Coinsurance /
Modco / Stop-Loss treaties**, including ML-enhanced assumptions, calendar-
aligned portfolio aggregation, LICAT capital tiers C-1 / C-2 / C-3 with lapse
and morbidity risk, IFRS 17 BBA / PAA / VFA point-in-time measurement,
stochastic interest-rate scenarios, Monte Carlo UQ, and per-duration tabular
YRT rate solving, the engine is **ready for use** in a deal-committee
workflow. The CLI, REST API, Streamlit dashboard, and deal-pricing Excel
export each carry a reinsurer-perspective default plus a cedant-view selector,
making the primary use case (reinsurer pricing) the path of least resistance
across every surface. Premium sufficiency now reports on the deal-pricing path
end-to-end (CLI / API / dashboard / Excel) with per-line-item PV breakdown.

What still **gates production use at a large reinsurer** is the same two
items the 2026-05-23 file flagged, plus a third gap restored at maintainer
direction this run: (1) the engine carries a single net-premium reserve basis
with a horizon-edge approximation; reproducing the cedant's stated reserves
(GAAP, STAT VM-20, CRVM, deficiency reserves) is not yet possible, (2) IFRS 17
only produces point-in-time recognition figures, not the period-to-period
movement table required for a real filing, and (3) regulatory capital is
LICAT-only (Canada), so US and EU deals cannot be evaluated on a
return-on-capital basis at all. These are scoped as **staggered epics**
(see `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`), decomposed into
session-sized slices and driven by daily-dev — not deferred to an
unscheduled roadmap slot.

## Feature Gap Analysis

### BLOCKERs

None remain. Every BLOCKER identified in 2026-04-19 has shipped, and the
2026-05-23 review confirmed no new BLOCKER had been promoted from the harvested
follow-up queue.

### IMPORTANT

Two IMPORTANT items are unchanged from 2026-05-23 — neither was selected by
daily-dev in the intervening 26 days, per their (now-removed) "out of scope
for single-session pickup" caveat. A third (cross-jurisdiction capital) is
restored this run at maintainer direction. All three are now treated as
**epics to decompose and drive**, not items to defer (see
`docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-06-18.md`):

- ~~**Reserve basis matching (cedant reproduction).** `core/projection.py`
  supports one reserve basis. Reinsurers must reproduce the cedant's reserves
  (GAAP, STAT VM-20, CRVM, CIA net premium, or deficiency reserves) to give a
  consistent profit-test. **Scope:** ~10 dev-days for a `ReserveBasis` enum +
  two concrete alternatives (CRVM, VM-20 PBR simplified). **Affected:**
  `core/projection.py`, all four products, new test suite vs published cedant
  filings. *Carried from PRODUCT_DIRECTION_2026-05-23 → 2026-04-19.*~~ —
  **SHIPPED** (PRs #81–#86): `ReserveBasis` enum + plumbing (#81), CRVM for
  Term (#82) and WL to-omega FPT (#83), VM-20 simplified for Term (#84) and WL
  (#85), and the CLI/API/Excel/notebook selector (#86). Epic 1 COMPLETE; see
  `CONTINUATION_reserve_basis.md`. Residual refinements (GAAP basis, 2001 CSO
  valuation table, 20-pay cap, exact VM-20 NPR, stochastic VM-20,
  scenario/uq/dashboard surfacing) live in Promoted Follow-ups below.

- ~~**IFRS 17 period-to-period movement table.** Current implementation gives
  BEL / RA / CSM at initial recognition only (`analytics/ifrs17.py`).
  Production filers need the opening → experience adjustments → unwinding →
  closing movement table by annual cohort with locked-in discount rates
  (Roadmap Phase 5.3). **Scope:** ~10 dev-days. **Affected:**
  `analytics/ifrs17.py`. *Carried from PRODUCT_DIRECTION_2026-05-23 →
  2026-04-19.*~~ — **SHIPPED** (PRs #87–#91): `IFRS17CohortManager` +
  annual-cohort locked-in rates (#87), `IFRS17MovementTable`
  opening→experience→unwinding→closing with the additivity/footing test (#88),
  and the REST (#89), Excel (#90), and CLI (#91, `polaris price
  --ifrs17-movement`) surfaces. Epic 2 COMPLETE; see
  `CONTINUATION_ifrs17_movement.md` (Status COMPLETE). Residual refinements
  (per-issue-year locked-in-rate override on the CLI, dedicated `polaris
  ifrs17` subcommand, dashboard movement view, block-wide cross-product
  movement) live in Promoted Follow-ups below.

- **Cross-jurisdiction regulatory capital (US RBC + Solvency II).** LICAT
  capital (C-1 / C-2 / C-3, with lapse and morbidity risk) ships today, but
  it is the **Canadian** standard only. A reinsurer cannot evaluate a US or
  EU deal on a return-on-capital basis — the primary decision metric for a
  reinsurer — without the equivalent RBC (US) and Solvency II SCR (EU)
  modules. **This is a market-access gate, not polish:** the 2026-04-19
  baseline listed US RBC as a BLOCKER; it was dropped from the gap analysis
  in the intervening nightlies and is restored here at maintainer direction
  (2026-06-18). Both reuse the `CapitalModel` protocol LICAT already
  established. **Scope:** ~15 dev-days for both (US RBC first, ~8 d;
  Solvency II SCR, ~7 d). **Affected:** new `analytics/capital.py` siblings
  to `LICATCapital`, `ProfitTester` surfacing, CLI `--capital {rbc,solvency2}`,
  API `capital_model` field, new ADRs. *Restored from
  PRODUCT_DIRECTION_2026-04-19 (was BLOCKER); see
  `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` Tier A (A3).*

A further item surfaced this run **would warrant IMPORTANT status if it
begins to show up in cedant submissions**, currently filed NICE-TO-HAVE in
the queue but worth re-reading. Unlike 2026-05-23, it is now explicitly
**folded into the Reserve-basis-matching epic as a motivating acceptance
test**, not left as a free-floating sub-item:

- **WL prospective terminal reserve.** The horizon-edge artefact (WL reserve
  declining from $7.18M at yr 10 to $56k at yr 20) is an ARCHITECTURE-
  documented limitation rather than a regression, but a deal-committee actuary
  would query why a $25M WL block carries near-zero reserves at projection
  end. ARCHITECTURE.md §4 already foreshadows "Phase 3 will extend to true
  prospective reserves" — this remains open. **Disposition:** carried on the
  NICE-TO-HAVE queue, but named as an acceptance test inside Epic 1
  (Reserve-basis matching) — a true prospective / cedant-reproduced WL basis
  should close the $56k-at-horizon artefact, so the two are the same body of
  work. *Cross-referenced in `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`
  Epic 1.* — **SHIPPED (CRVM/VM-20 bases only)** (PR #83): the to-omega WL CRVM
  reserve (ADR-089) closes the artefact under CRVM/VM-20 — golden-WL yr20
  aggregate `reserve_balance` rises to ~$2.35M (>40×). The NET_PREMIUM-basis
  artefact closure remains open (rebaseline-bearing) and is tracked in Promoted
  Follow-ups.

### NICE-TO-HAVE

The NICE-TO-HAVE queue published in PRODUCT_DIRECTION_2026-05-23 remains the
working backlog. All items survived intact except those crossed out below in
"Recently Completed". The full list (with provenance, scope, and "Affected"
notes) is the previous file — this nightly does not re-state it. Briefly, the
queue covers:

- **Premium sufficiency on `scenario` / `uq` / portfolio surfaces** — ~1
  dev-day per surface (single-deal price-path surfaces all shipped 2026-06-16 →
  2026-06-17, ADR-083 / ADR-084 / ADR-085).
- **Premium-deficiency reserve / loss-recognition extension** — design ADR +
  ~1-2 dev-days, touches reserve mechanics.
- **Per-sheet perspective caption on the Ceded Excel sheet** — ~0.5 dev-day.
- **Grouped two-level header on the Line Item Comparison sheet** (new
  harvest from ADR-086) — ~0.5 dev-day, presentation-only.
- **Switch standard capital surfaces from `for_product` to
  `for_product_interim`** — behaviour change with golden regen, ~1-2 dev-days.
- **Capital-weighted concentration basis on `PortfolioResultWithCapital`** —
  ~1-2 dev-days; PR #56 merged so dependency is clear.
- **Annuity-product LICAT factor** — depends on Phase 5.4 asset/ALM engine.
- **Sliding-scale expense allowances / experience refunds** — ~3 dev-days.
- **Funds-withheld coinsurance variant** — ~2 dev-days.
- **Duration-specific select-period customisation** — ~2 dev-days.
- **Experience monitoring automation loop** (Phase 6.1) — ~6 dev-days.
- **Scale benchmarks at 100K policies** — ~1 dev-day.
- **Parallel portfolio execution + `remove_deal` + per-deal result caching**
  — ~2 dev-days.
- **Per-duration cell-failure interpolation** / **Warm-start `brentq` across
  adjacent per-duration cells** — ~1 dev-day each, both presentation /
  performance only.
- **Reinsurer-vs-cedant perspective on `Portfolio.run_scenarios`** — premise
  was corrected to "already-satisfied or add cedant view"; confirm before
  acting.
- **Sub-month / non-common day-of-month inception dates in calendar mode** —
  design ADR + ~2 dev-days.
- **Per-deal scenario overrides (heterogeneous stresses across cedants)** —
  design ADR + ~3 dev-days.
- **Streamlit dashboard page for portfolio scenario results** — ~3 dev-days.
- **Relative-to-config path resolution for `yrt_rate_table_path`** — ~0.5-1
  dev-day.
- **Dashboard upload-flow key for a tabular YRT table** — ~1 dev-day.
- **ANB vs ALB attained-age convention** — ~0.5-1 dev-day.
- **As-of re-valuation workflow** — design sketch + ~1-2 dev-days.
- **Deal-specific hurdle rates on `Portfolio`** — ~2 dev-days design +
  ~3 dev-days implementation.
- **CI / DI substandard rating** — defer until cedant ingestion confirms.
- **Flat-extra as a separate cash-flow line** — touches `CashFlowResult`
  contract; needs a contract review.
- **`polaris price --with-sensitivity` inline scenarios** — ~1 dev-day.
- **Treaty-level rated-YRT override (`yrt_rate × multiplier`)** — ~1 dev-day.

## Recommended Next Sprint

**Direction change (2026-06-18, maintainer-approved).** The prior nightlies
ranked work by `(commercial impact) × (1 / effort)` and recommended "pick the
cleanest small win on the freshest thread". That single scalar structurally
rewards the *smallest* available item, which is why ten consecutive PRs
(#69–#78) were sub-day polish while the IMPORTANT items sat untouched for
~56 days (see `docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`). Selection is
now **epic-first**: advance one decomposed IMPORTANT epic every session before
any fallback pick, and order fallback work by a 2-D value × effort read rather
than by `1 / effort` alone.

**Lead item — Epic 1: Reserve-basis matching.** Highest-impact direction shift
available; gates cedant reproduction in the deal-committee workflow and closes
the WL terminal-reserve flag above. Decompose per
`docs/COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md` §4 into 3–4 session-sized
slices (slice 1: `ReserveBasis` enum + plumbing, goldens byte-identical) and
ship slice 1 next session. Write `docs/PLAN_reserve_basis.md` and open
`docs/CONTINUATION_reserve_basis.md` (IN PROGRESS) before any fallback pick.
Epics 2 (IFRS 17 movement) and 3 (US RBC + Solvency II) follow.

**Fallback queue (between-epic / blocked-epic picks only).** When the active
epic's next slice is blocked or complete and the session has capacity, these
are the cleanest small wins, ordered by value-per-day:

1. **Premium sufficiency on `scenario` / `uq` / portfolio surfaces.**
   Single-deal price has surfaced sufficiency end-to-end since ADR-085
   (yesterday); the natural follow-on is to surface it on the
   sensitivity-analysis paths so a committee sees "is this deal still
   sufficient under +10% mortality?" alongside the existing PV / IRR table.
   ~1 dev-day per surface (CLI / API / dashboard / portfolio).
   *Acceptance:* same `PremiumSufficiencyResult` block in every scenario /
   UQ / portfolio output, identical reading order to the price-path panels.
   *Modules:* `cli.py` (`scenario_cmd`, `uq_cmd`), `analytics/portfolio.py`,
   `api/main.py`, `dashboard/views/`, tests.
   *Dependencies:* none — analyzer is already in place (ADR-082).

2. **Grouped two-level header on the Line Item Comparison sheet.**
   Newest harvest (ADR-086); ~0.5 dev-day; presentation-only; no contract
   change.
   *Acceptance:* `{item}` merged across its three basis columns on row 1,
   `Gross | Ceded | Net` on row 2; existing flat-header tests continue to
   pass (or one is updated with rationale).
   *Modules:* `src/polaris_re/utils/excel_output.py`
   (`_write_line_item_comparison_sheet`), tests.
   *Dependencies:* none.

3. **Per-sheet perspective caption on the Ceded Excel sheet.** ~0.5 dev-day;
   purely additive; closes a known clarity gap on the Ceded sheet whose
   `Net Cash Flow` column carries the reinsurer view.
   *Acceptance:* a caption / title cell on the "Ceded Cash Flows" sheet
   makes the reinsurer-vs-cedant reading unambiguous; consistent with the
   dashboard perspective captions (ADR-078).
   *Modules:* `src/polaris_re/utils/excel_output.py`, tests.
   *Dependencies:* none.

4. **Premium-deficiency reserve / loss-recognition extension.** Higher
   commercial impact (closes a true actuarial loop) but touches reserve
   mechanics — design ADR first, ~1-2 dev-days implementation. Best treated
   as a two-session item: ADR + slice 1 (compute the deficiency reserve and
   expose on the price surfaces), slice 2 (optional projection-time floor).
   *Acceptance:* when `is_sufficient = False`, the price output surfaces a
   computed deficiency reserve; opt-in flag threads it into reserve floor.
   *Modules:* `analytics/premium_sufficiency.py`, possibly
   `core/projection.py`, tests.
   *Dependencies:* none.

5. **Switch standard capital surfaces from `for_product` to
   `for_product_interim`.** Higher visibility (every capital tile and every
   golden capital number moves), but explicitly a behaviour-change item
   that needs its own ADR + coordinated golden baseline regeneration.
   Reserve for a session with the explicit goal of regenerating goldens, not
   a quick small pick. ~1-2 dev-days.

The three IMPORTANT items (Reserve-basis matching, IFRS 17 movement table,
US RBC + Solvency II capital) are **no longer** treated as out of scope for
daily-dev. Each is an epic: scoped, decomposed into session-sized slices, and
driven to completion one slice per session via a `PLAN_*.md` + `CONTINUATION_*.md`
pair, exactly as the dashboard-portfolio work was (PR #61 / #62 / #63). The
Asset / ALM model (Roadmap 5.4) remains a lower-priority big rock than these
three — Modco prices on a fixed credited rate today — and is scheduled after
the three epics above (see review §3, Tier C).

## Recently Completed (by daily dev routine)

Items addressed by `DEV_SESSION_LOG_*.md` files since PRODUCT_DIRECTION_2026-05-23.
All entries below were previously open in the queue and are now SHIPPED.

| Item | Sessions | ADR | PR | Merge status |
|---|---|---|---|---|
| Portfolio aggregate CashFlowResult (claims / expenses / reserves) | 2026-05-27 | ADR-059 | PR #46 | MERGED |
| Aggregate return-on-capital on `Portfolio` | 2026-05-28 | ADR-060 | PR #47 | MERGED |
| Calendar-aligned portfolio aggregation (Slice 1 / 2) | 2026-05-29 / 2026-05-31 | ADR-061 / ADR-062 | PR #48 / PR #49 | MERGED |
| Per-duration solver in `YRTRateSchedule.generate_table()` | 2026-06-01 | ADR-063 | PR #50 | MERGED |
| Portfolio-level scenario analysis (`run_scenarios`) | 2026-06-01 | ADR-064 | PR #51 | MERGED |
| LICAT lapse-risk and morbidity-risk capital components | 2026-06-02 | ADR-065 | PR #52 | MERGED |
| `polaris portfolio scenarios` CLI + API endpoint | 2026-06-03 | ADR-066 | (committed direct) | MERGED |
| `--solve-mode` Typer flag on `polaris rate-schedule` | 2026-06-04 | ADR-067 | (committed direct) | MERGED |
| Excel rated-block panel (`RatedBlockExport`) | 2026-06-05 | ADR-068 | (committed direct) | MERGED |
| Weighted concentration variants (`concentration_by_basis`, `hhi_by_basis`) | 2026-06-05 | ADR-069 | PR #56 | MERGED |
| CLI surfacing of `--concentration-basis` | 2026-06-05 | ADR-070 | (committed direct) | MERGED |
| Ingestion strict-mode for unknown rating codes | 2026-06-06 | ADR-071 | PR #58 | MERGED |
| LICAT C-1 / C-3 interim factor classmethod | 2026-06-07 | ADR-072 | PR #59 | MERGED |
| Dimension-outer transposed view on `concentration_by_basis` | 2026-06-07 | ADR-073 | PR #60 | MERGED |
| Streamlit dashboard portfolio page (Slice 1 / 2 / 3) | 2026-06-07 → 2026-06-09 | (rolls under PLAN_dashboard_portfolio) | PR #61 / PR #62 / PR #63 | MERGED |
| Dashboard error handling — widen catches to `PolarisComputationError` | 2026-06-10 | — | PR #65 | MERGED |
| Calendar-aligned portfolio UX polish (staggered sample) | 2026-06-10 | ADR-074 | PR #66 | MERGED |
| Valuation-date resolution (fix-along) | 2026-06-11 | ADR-074 (post-mortem) | — | MERGED |
| `yrt_rate_table_path` field on `DealConfig` for YAML configs | 2026-06-13 | ADR-075 | PR #67 | MERGED |
| `deal.yrt_rate_table_path` on `scenario` / `uq` CLI commands | 2026-06-14 | ADR-076 | (committed direct) | MERGED |
| Reinsurer-vs-cedant profit-test perspective in scenario / UQ (CLI) | 2026-06-14 | ADR-077 | PR #69 | MERGED |
| Reinsurer-vs-cedant perspective on scenario / UQ API + dashboard | 2026-06-15 | ADR-078 | PR #70 | MERGED |
| `--yrt-rate-table` CLI flag on `scenario` / `uq` | 2026-06-15 | ADR-079 | PR #71 | MERGED |
| Gross / Ceded cash-flow sheets in deal-pricing Excel | 2026-06-15 | ADR-080 | PR #72 | MERGED |
| Combined Gross / Ceded / Net cash-flow comparison sheet | 2026-06-16 | ADR-081 | PR #73 | MERGED |
| `PremiumSufficiencyTester` library primitive | 2026-06-16 | ADR-082 | PR #74 | MERGED |
| Surface premium sufficiency across CLI / API / dashboard / Excel | 2026-06-16 | ADR-083 | PR #75 | MERGED |
| Per-line-item premium-sufficiency breakdown (Excel + dashboard) | 2026-06-17 | ADR-084 | PR #76 | MERGED |
| Per-line-item premium-sufficiency breakdown (CLI Rich table) | 2026-06-17 | ADR-085 | PR #77 | MERGED |
| Per-line-item Gross / Ceded / Net comparison sheet | 2026-06-17 | ADR-086 | PR #78 | MERGED |

Throughput: ~30 shipped items across 26 calendar days, all crossed out in the
2026-05-23 file's queue with full provenance and SHIPPED footers. Reading the
crossouts in 2026-05-23 in isolation gives the same accounting as the table
above — this file does not duplicate the SHIPPED-footer detail.

## Promoted Follow-ups

Items harvested from completed/in-flight work by the daily-dev routine
(step 17), with provenance. These are first-class work items, not commentary.

- **NICE-TO-HAVE — Configurable held-capital basis (target multiple of ACL)
  for US RBC.** The US RBC module (Epic 3 Slice 1) fixes the held-capital basis
  fed to return-on-capital at the **Company Action Level** (= 2× Authorized
  Control Level = the covariance result). Reinsurers commonly hold a *target
  multiple* of ACL (typically 300–400%); a configurable multiple would let the
  RoC denominator reflect a cedant's actual capital target rather than the
  regulatory floor. Affects the magnitude of the RBC return-on-capital number,
  not first-deal correctness or the LICAT/common path → NICE-TO-HAVE. Resolve
  the design (where the multiple is set — on `RBCCapital` vs `run_with_capital`)
  in Epic 3 Slice 2/4.
  *Source: ADR-098 Out of scope + CONTINUATION_cross_jurisdiction_capital Open Questions (1st-order).*

- **NICE-TO-HAVE — Additional Solvency II SCR sub-modules.** The EU Solvency II
  module (Epic 3 Slice 3) models only the life-underwriting sub-modules that
  drive a typical individual-life reinsurance quote — **mortality, lapse,
  catastrophe** — plus top-level **market** and **counterparty default** risk.
  The standard formula also defines **longevity, expense, revision, and
  disability/morbidity** life sub-modules and **health / non-life / intangible**
  top-level modules. Extending the correlation matrices and factor set to cover
  these would let the engine quote annuity (longevity) and health books on a true
  standard-formula SCR rather than the mortality-proxy approximation used today.
  Affects only longevity/health/non-life blocks, not the common life first-deal
  path → NICE-TO-HAVE. The aggregation machinery (`_correlation_aggregate`) and
  the documented-matrix pattern already generalise to larger matrices, so this is
  factor + matrix extension, not new structure.
  *Source: ADR-100 Out of scope (1st-order).*

- **NICE-TO-HAVE — Result-level solvency-ratio surface (own funds / SCR).** The
  Solvency II `SolvencyIIResult` exposes the SCR schedule and the cost-of-capital
  risk margin, but not a solvency ratio (own funds / SCR), the EU analogue of the
  RBC ratio. Like the deferred RBC ratio it needs an external own-funds input the
  RoC entry points do not hold. **Slice 4c-1 (ADR-103) shipped the result-level
  ratio CORE**: a `CapitalSchedule.capital_ratio(available_capital)` protocol
  method (LICAT total ratio / RBC ratio / EU solvency ratio, denominator
  encapsulated per jurisdiction) surfaced on `ProfitResultWithCapital` via an
  optional `run_with_capital(..., available_capital=...)` keyword. **Slice 4c-2a
  (ADR-104) shipped the machine surfacing**: the CLI `--available-capital` flag
  and the API `available_capital` field, both emitting `capital_ratio` on the
  cedant + reinsurer views. What REMAINS is the *presentation* surfacing —
  rendering `capital_ratio` on the Excel capital block (a ratio row) and the
  dashboard (a number-input + ratio tile) — which lands in **Epic 3 Slice 4c-2b**,
  with the three-standard validation notebook in **4c-2c**. Affects the
  capital-ratio surface for US/EU deals, not first-deal RoC correctness →
  NICE-TO-HAVE.
  *Source: ADR-100 Out of scope (1st-order); re-pointed to Slice 4c by ADR-102;
  core shipped in 4c-1 (ADR-103); machine surfaces shipped in 4c-2a (ADR-104);
  presentation surfacing re-pointed to Slice 4c-2b, notebook to 4c-2c.*

- **NICE-TO-HAVE — Statutory reserve bases for UL and DI.** The reserve-basis
  epic (A1) implements CRVM / VM-20 / GAAP for Term and Whole Life only. UL
  keeps reserve = account value and DI keeps reserve = 0; both raise
  `PolarisComputationError` on any non-NET_PREMIUM basis. Extending statutory
  bases to UL (CRVM-for-UL) and DI (GAAP DI reserves) is deliberately out of
  the epic's scope and would otherwise be invisible once the epic closes.
  Affects only UL/DI blocks valued on a statutory basis, not the common
  Term/WL first-deal path → NICE-TO-HAVE.
  *Source: ADR-087 Out of scope (1st-order).*

- ~~**IMPORTANT — Whole-life CRVM + prospective terminal reserve (Slice 2b).**
  Reserve-basis Slice 2 was decomposed into 2a (TermLife CRVM, shipped) and 2b.
  Slice 2b owns: WholeLife CRVM (Full Preliminary Term), the **WL prospective
  terminal reserve to omega** that closes the $7.18M→$56k horizon-edge artefact,
  the distinct **statutory valuation mortality table** (2001 CSO — TermLife CRVM
  currently values on the projection table), and the **20-pay expense-allowance
  cap** (binds for short-pay/high-premium WL, never for level term).~~ —
  **SHIPPED** (PR #83): WholeLife CRVM via prospective-to-omega FPT;
  the $7.18M→$56k artefact is closed under the CRVM basis (golden-WL yr20
  reserve_balance ~$2.35M, >40×). The 2001 CSO table and 20-pay cap were
  **deferred** and are re-promoted as their own items below.
  *Source: ADR-088 Out of scope + DEV_SESSION_LOG_2026-06-19_reserve_basis_slice2a Open Questions (1st-order).*

- **IMPORTANT — Statutory valuation mortality table (2001 CSO) for CRVM.**
  Both TermLife (2a) and WholeLife (2b) CRVM value on the **projection
  best-estimate mortality**, not the prescribed statutory valuation table
  (2001 CSO). Exact reproduction of a cedant's US statutory CRVM reserve — the
  whole point of the epic — requires wiring a distinct `valuation_mortality`
  slot (a controlled core-contract change → ADR + backward-compat default). This
  is a real gap to "match the cedant's basis exactly," not polish → IMPORTANT.
  *Source: ADR-089 Out of scope (1st-order).*

- **NICE-TO-HAVE — 20-pay expense-allowance cap for short-pay whole life.**
  WholeLife CRVM (FPT) is exact for whole-life pay and limited-pay ≥ 20 years;
  for premium-paying periods < 20 years the 20-payment-whole-life cap binds and
  `_compute_reserves_crvm()` currently **raises** `PolarisComputationError`
  (never a silently-wrong reserve). Implementing the cap unblocks CRVM on
  short-pay/high-premium WL. Narrow product subset, and the safe-raise means no
  correctness risk on the common path → NICE-TO-HAVE.
  *Source: ADR-089 Out of scope (1st-order).*

- **IMPORTANT — Close the WL terminal-reserve artefact on the NET_PREMIUM
  basis.** Slice 2b closes the $7.18M→$56k horizon-edge collapse only under the
  **CRVM** basis; the **default NET_PREMIUM** WL reserve still uses the
  one-period terminal estimate `V_T = face·q_T·v` and still collapses (left
  byte-identical to honour the epic's golden constraint). Replacing the
  NET_PREMIUM terminal estimate with the same prospective-to-omega valuation
  would close the artefact on the default path, but **moves the goldens** and so
  needs its own ADR + coordinated baseline regeneration + human review. Affects
  the default reserve number on every WL block → IMPORTANT (gated on
  rebaseline authorization).
  *Source: ADR-089 Out of scope + DEV_SESSION_LOG_2026-06-19_reserve_basis_slice2b Open Questions (1st-order).*

- ~~**IMPORTANT — VM-20 simplified for Whole Life (Slice 3b).** Reserve-basis
  Slice 3 was decomposed into 3a (TermLife VM-20, shipped) and 3b. Slice 3b owns
  WholeLife VM-20 `max(NPR, DR)`: the WL NPR reuses the WL CRVM reserve (ADR-089),
  but the **deterministic reserve must be valued prospectively to omega** (reusing
  `_build_valuation_mortality` / `_valuation_months_to_omega` from 2b) so it does
  not collapse at the horizon — the WL analogue of the 3a finite-horizon DR.
  Tracked as the NEXT slice in `CONTINUATION_reserve_basis.md`. Completes VM-20
  across both Phase-1 life products → IMPORTANT.~~ — **SHIPPED** (PR #85):
  WholeLife VM-20 `max(NPR, DR)` with both NPR (to-omega CRVM) and DR
  (new `_compute_deterministic_reserve` + `_build_valuation_lapse`) valued to
  omega; VM20 (≥ the to-omega NPR) does not collapse at the horizon. ADR-091.
  *Source: ADR-090 Out of scope (1st-order).*

- **NICE-TO-HAVE — Exact VM-20 NPR refinements (X factors / deficiency).**
  TermLife VM-20 (3a) maps the NPR to the CRVM reserve (the "simplified" in
  "VM-20 simplified"). The exact VM-20 NPR adds the term-specific mortality
  `X` factors / select-period grading and a deficiency adjustment where the gross
  premium falls below the net premium. The prescribed valuation table piece is
  already covered by the "2001 CSO valuation table" IMPORTANT item above; the
  `X`-factor / deficiency refinement affects NPR precision on term blocks, not
  the common first-deal correctness path → NICE-TO-HAVE.
  *Source: ADR-090 Out of scope (1st-order).*

- **NICE-TO-HAVE — VM-20 stochastic reserve (SR).** The reserve-basis epic
  implements the **deterministic** VM-20 path only (`max(NPR, DR)`), per PLAN §2.
  Full VM-20 takes `max(NPR, DR, SR)` where SR is the CTE-70 stochastic reserve
  over prescribed economic scenarios — a scenario-generation + tail-measure build
  that is its own multi-session epic, deliberately excluded here. Relevant mainly
  for interest-sensitive / long-duration business → NICE-TO-HAVE.
  *Source: ADR-090 Out of scope (1st-order).*

- **NICE-TO-HAVE — Broader DR expense components (commissions, premium tax).**
  The VM-20 deterministic reserve (3a) models the expenses the engine carries —
  maintenance per in-force policy plus the one-time acquisition cost. A fuller
  gross-premium DR would also project renewal commissions, premium tax, and
  overhead. These flow from expense assumptions the engine does not yet model, so
  adding them is a config/assumption extension, not a reserve-math change → 
  NICE-TO-HAVE.
  *Source: ADR-090 Out of scope (1st-order).*

- **IMPORTANT — GAAP (FAS 60) concrete reserve basis.** The reserve-basis epic
  shipped NET_PREMIUM / CRVM / VM-20 for Term and Whole Life and surfaced the
  selector (Slice 4), but **GAAP** has only the `ReserveBasis.GAAP` enum value
  and the dispatch guard — selecting it raises `PolarisComputationError`. US
  GAAP (net-premium benefit reserve with locked-in best-estimate assumptions +
  PAD) is a basis a US cedant commonly reports on, so reproducing it is part of
  "match the cedant's basis," not polish → IMPORTANT.
  *Source: ADR-092 Out of scope + PLAN_reserve_basis §1 (1st-order).*

- **NICE-TO-HAVE — Reserve-basis selector on `scenario` / `uq` surfaces.**
  Slice 4 surfaced `--reserve-basis` (CLI) and `reserve_basis` (API) on the
  **`price`** path only, mirroring the CLI `polaris price` surface. The
  `scenario` and `uq` CLI commands and API endpoints still always value on
  NET_PREMIUM. A deal committee that wants stress / UQ runs on the cedant's
  basis needs the same selector wired there (`_resolve_*` plumbing already
  exists for the other deal params). The basis-correct base case is available
  via `price`, so this is design-completeness, not common-path correctness →
  NICE-TO-HAVE.
  *Source: ADR-092 Out of scope (1st-order).*

- **NICE-TO-HAVE — Dashboard reserve-basis control (CLI/Streamlit parity).**
  The Streamlit dashboard has no reserve-basis selector; `DealConfig.to_dict()`
  now carries `reserve_basis` so the wiring is one control + a state default.
  Parity polish for the dashboard surface, not first-deal correctness →
  NICE-TO-HAVE.
  *Source: ADR-092 Out of scope (1st-order).*

- **NICE-TO-HAVE — Heterogeneous-term IFRS 17 cohort calendar alignment.** The
  new `IFRS17CohortManager` (Epic 2, Slice 1) requires all contracts to share a
  projection grid (`projection_months` / `valuation_date` / `time_index`) so the
  cohort aggregate is well defined. Different policy terms issued the same year
  need a common calendar grid before they can be aggregated into one cohort.
  Affects multi-term books; the first filing-grade movement table works on a
  shared grid → NICE-TO-HAVE.
  *Source: ADR-093 Out of scope + CONTINUATION_ifrs17_movement Open Questions
  (1st-order).*

- **NICE-TO-HAVE — IFRS 17 cohort measurement under PAA / VFA.** Slice 1 cohorts
  measure **BBA only**; the PAA (short-duration) and VFA (direct-participating)
  measurement models are not yet available at the cohort level. The movement
  table targets BBA (the general model); PAA/VFA cohort movement is a later
  refinement → NICE-TO-HAVE.
  *Source: ADR-093 Out of scope (1st-order).*

- **NICE-TO-HAVE — Onerous-contract sub-grouping within an annual IFRS 17
  cohort.** IFRS 17.16 requires an annual cohort to be split into onerous /
  no-significant-possibility-of-becoming-onerous / remaining sub-groups. Slice 1
  groups by issue year only. The movement table proceeds on issue-year cohorts;
  onerous sub-grouping is a disclosure refinement, not a blocker for the first
  movement table → NICE-TO-HAVE.
  *Source: ADR-093 Out of scope (1st-order).*

- **IMPORTANT — Surface the IFRS 17 movement table (Epic 2, Slice 3).** Slice 2
  built `IFRS17MovementTable` + `IFRS17CohortManager.cohort_movement_tables()` /
  `.aggregate_movement_table()`, but nothing is wired to a user surface yet.
  Slice 3 owns `POST /api/v1/ifrs17/movement`, an "IFRS 17 Movement" Excel sheet,
  and a CLI surface (a `polaris price` opt-in flag or a `polaris ifrs17`
  subcommand), plus a `to_dict`/serialiser on the movement types. This is the
  filing artefact a user actually consumes, and the only slice that may move
  goldens (and only for runs that request the table) → IMPORTANT.
  *Source: ADR-094 Out of scope + CONTINUATION_ifrs17_movement Slice 3 (1st-order).*
  **SHIPPED (all sub-slices)**: Slice 3a — `to_dict()` serialiser + `POST
  /api/v1/ifrs17/movement` — merged (PR #89, ADR-095). Slice 3b — the
  "IFRS 17 Movement" Excel sheet — merged (PR #90, ADR-096). Slice 3c — the
  `polaris price --ifrs17-movement` CLI surface — shipped this draft (ADR-097).
  **Epic 2 (IFRS 17 movement table) is complete.**

- ~~**IMPORTANT — IFRS 17 movement Excel sheet (Epic 2, Slice 3b).** Add an
  "IFRS 17 Movement" sheet to the deal-pricing workbook (`utils/excel_output.py`),
  consuming the `IFRS17MovementTable.to_dict()` serialiser shipped in Slice 3a.
  The Excel workbook is the deliverable a pricing actuary hands to a filer, so the
  movement table belongs in it → IMPORTANT. May move goldens only for runs that
  request the sheet.
  *Source: ADR-095 Out of scope + CONTINUATION_ifrs17_movement Slice 3b (1st-order).*~~
  — **SHIPPED** (this draft, Slice 3b): `IFRS17MovementExport` DTO +
  `DealPricingExport.ifrs17_movement` field; `write_deal_pricing_excel` appends an
  "IFRS 17 Movement" sheet (aggregate + per-cohort blocks, each BEL/RA/CSM/total
  as a Year x movement-line sub-table that foots) when populated; suppressed by
  default → goldens byte-identical (ADR-096). The CLI does not yet populate the
  field — that is Slice 3c (below).

- ~~**IMPORTANT — IFRS 17 movement CLI surface (Epic 2, Slice 3c).** A
  `polaris price` opt-in flag or a dedicated `polaris ifrs17` subcommand emitting
  the movement table (JSON / Rich), reusing the Slice-3a serialiser. Completes the
  surfacing epic so the disclosure is reachable from every entry point → IMPORTANT.
  When wiring `polaris price`, also populate `DealPricingExport.ifrs17_movement`
  (the Slice-3b field) so the Excel "IFRS 17 Movement" sheet appears on the same
  run — building the `IFRS17CohortManager` from the priced block (issue-year
  grouping + per-year locked-in rates) is the shared input for both surfaces.
  *Source: ADR-095/096 Out of scope + CONTINUATION_ifrs17_movement Slice 3c (1st-order).*~~
  — **SHIPPED** (this draft, Slice 3c): `polaris price --ifrs17-movement` (with
  `--ifrs17-ra-factor` / `--ifrs17-months-per-period`) builds the movement table
  **per product cohort** (issue-year grouping, locked-in = config discount rate),
  adds it to the JSON output (REST-mirroring shape), renders two Rich tables, and
  with `--excel-out` populates `DealPricingExport.ifrs17_movement` so the
  Slice-3b sheet appears on the same run. Off by default → goldens byte-identical
  (ADR-097). **This completes Epic 2 (IFRS 17 movement table).**

- **NICE-TO-HAVE — Per-issue-year locked-in-rate override on the CLI.** Epic 2
  Slice 3c (`polaris price --ifrs17-movement`, ADR-097) applies a single
  locked-in rate (`config.discount_rate`) to every issue-year cohort. The REST
  API already accepts a `locked_in_rates` (issue-year → rate) map; the CLI should
  offer the same, e.g. a `--ifrs17-locked-in-rates` JSON-file flag, so a filer can
  reproduce each cohort's issue-era rate. Affects multi-vintage books wanting
  rate-accurate CSM accretion; the common single-rate path already works →
  NICE-TO-HAVE.
  *Source: ADR-097 Out of scope (1st-order).*

- **NICE-TO-HAVE — Dedicated `polaris ifrs17` movement-only subcommand.** Slice 3c
  surfaced the movement table as an opt-in flag on `polaris price` (ADR-097); a
  standalone `polaris ifrs17` subcommand that emits only the movement table
  (no pricing) would let a filer produce the disclosure without running a full
  deal-pricing pipeline. The flag route already makes the disclosure reachable →
  NICE-TO-HAVE.
  *Source: ADR-097 Out of scope (1st-order).*

- **NICE-TO-HAVE — Dashboard IFRS 17 movement view.** The movement table is now
  reachable on the REST API (3a), Excel (3b) and CLI (3c). The Streamlit
  dashboard has no movement view yet. Additive surface — the filing artefacts
  (Excel / JSON) already exist → NICE-TO-HAVE.
  *Source: ADR-097 Out of scope (1st-order).*

- **NICE-TO-HAVE — Block-wide (cross-product) IFRS 17 movement on a common
  calendar grid.** Slice 3c builds the movement table **per product cohort**
  because TERM and WHOLE_LIFE project on different grids, so a block-wide
  aggregate fails the cohort manager's alignment check. A cross-product aggregate
  needs a common calendar grid (the same heterogeneous-term alignment the existing
  "Heterogeneous-term IFRS 17 cohort calendar alignment" follow-up describes) →
  NICE-TO-HAVE.
  *Source: ADR-097 Out of scope (2nd-order — depends on heterogeneous-term alignment).*

- **NICE-TO-HAVE — Mid-life in-force IFRS 17 movement opening.** The shipped
  movement table is a from-recognition roll-forward: the cohort's first reporting
  period opens at 0 and recognises the initial balance as `new_business`. A
  mid-life filing on an in-force block may instead want period-0 opening = the
  current in-force balance with no new-business line. The from-recognition view
  is correct for a cohort projected from inception; the alternate opening is a
  presentation variant → NICE-TO-HAVE.
  *Source: ADR-094 Out of scope + DEV_SESSION_LOG_2026-06-20_ifrs17_movement_slice2 Open Questions (1st-order).*

- **NICE-TO-HAVE — Explicit RA finance/unwinding line in the movement table.**
  Under the simplified cost-of-capital RA (`ra_factor·|BEL|`) the movement table
  carries no RA interest-accretion line; the whole period RA change is booked as
  risk release. A more complete RA model would split out an RA finance line.
  Affects disclosure granularity only, not the BEL/CSM mechanics → NICE-TO-HAVE.
  *Source: ADR-094 Out of scope (1st-order).*

- **NICE-TO-HAVE — IFRS 17 movement table on the dashboard.** The dashboard's
  IFRS 17 view currently shows only the point-in-time BEL/RA/CSM schedules. Once
  the movement table is surfaced on API/Excel/CLI (Slices 3a–3c), a dashboard
  analysis-of-change view would consume the same `to_dict()` serialiser. The
  original Slice-3 plan named only API/Excel/CLI, so this is an additional surface
  → NICE-TO-HAVE.
  *Source: ADR-095 Out of scope (2nd-order).*

- **NICE-TO-HAVE — Drive IFRS 17 cohort locked-in rates from issue-era rate
  curves.** The movement API takes a flat per-issue-year `locked_in_rates`
  override (defaulting to one `discount_rate`). A production filer locks each
  cohort's rate to the risk-free + illiquidity curve prevailing at that cohort's
  recognition; wiring a real issue-era curve lookup would remove the manual
  override. Refinement of the surfacing follow-up → NICE-TO-HAVE.
  *Source: ADR-095 Out of scope (2nd-order).*

## Carried Forward

No item was partially completed in this period — every dev-session log
records a self-contained `Slice: complete (single PR)` or a numbered Slice
within an explicit multi-slice plan whose later slices have since shipped
(notably `PLAN_dashboard_portfolio.md`, all three slices merged via PR #61
/ #62 / #63). The follow-up entries harvested into the NICE-TO-HAVE queue
(grouped two-level header on Line Item Comparison, premium-sufficiency on
scenario / UQ / portfolio surfaces, per-sheet perspective caption on the
Ceded sheet, premium-deficiency reserve, etc.) are fresh out-of-scope items
from completed work, not in-flight slices.

## Comparison with Previous Assessment

PRODUCT_DIRECTION_2026-05-23 reported BLOCKERs cleared, two IMPORTANT items
deferred, and a richly-stocked NICE-TO-HAVE queue. The 2026-06-18 picture is
**materially the same** at the gap-tier level — no new BLOCKER has surfaced,
the two IMPORTANT items are unchanged in scope and rationale, and the
NICE-TO-HAVE queue has been drawn down by the items listed under "Recently
Completed" while four new sub-day-scope items were harvested from completed
work (grouped Line Item Comparison header, per-sheet perspective caption,
sufficiency-on-scenario/UQ/portfolio surfaces, premium-deficiency reserve).
Net queue movement is consistent with the daily-dev routine's design — finish
small follow-ups, harvest the next batch of follow-ups from the ADRs of the
work just shipped. **That design is exactly what `COMMERCIAL_VIABILITY_REVIEW_2026-06-18.md`
identifies as the "polish spiral": the queue grows in the polish direction
faster than it shrinks, and the highest-value work never starts.** Two
corrections are applied this run: (a) **US RBC + Solvency II capital** is
restored to IMPORTANT (the 2026-04-19 baseline had US RBC as a BLOCKER; it
had silently dropped out of the gap analysis), and (b) the **WL terminal
reserve** flag is folded into the Reserve-basis epic as an acceptance test
rather than left as a free-floating NICE-TO-HAVE.

The three IMPORTANT items (Reserve-basis matching, IFRS 17 period-to-period
movement table, US RBC + Solvency II) are the gap-to-real-deal at a large
reinsurer. Reserve-basis matching is the highest-impact and is the lead epic;
IFRS 17 movement and cross-jurisdiction capital follow. Rather than a
"dedicated 2-week roadmap slot" carved out of daily-dev, the maintainer
direction (2026-06-18) is to **drive these through daily-dev as decomposed
epics** — one session-sized slice at a time, byte-identical goldens until the
final surfacing slice — per `docs/DAILY_DEV_ROUTINE_PROPOSED_CHANGES_2026-06-18.md`.

The actuarial reasonability profile is unchanged from prior nightlies — flat
YRT rate vs rising mortality on the WL block, WL prospective terminal
reserve at horizon edge — both pre-existing structural notes covered in
ARCHITECTURE.md and the per-duration solver / IFRS 17 movement table queue.
No new reasonability flag emerged from today's run.
