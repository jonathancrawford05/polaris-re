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
- ~~**Sliding-scale expense allowances / experience refunds** — ~3 dev-days.~~
  — **SHIPPED** (PRs #117–#123, Tier-B B3 epic, ADR-118–124; ledger-healed
  2026-07-03; see `CONTINUATION_expense_allowance.md`, COMPLETE).
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

- **NICE-TO-HAVE — Exposure-weighted modal reference level for `ExperienceGAM`
  factor effects.** `ExperienceGAM.factor_effect` reports each categorical level's
  A/E multiplier relative to the **modal** reference level, chosen by row count
  (`group_by(f).len()`). When two levels have equal cell counts (e.g. a balanced
  synthetic or a perfectly split book) the reference is a nondeterministic
  tie-break, so which level renders at multiplier 1.0 can vary run-to-run. The
  reported *contrasts* are reference-invariant (correctness is unaffected), and
  real studies have unequal exposure so it is deterministic in practice — this is
  cosmetic. An exposure-weighted (or largest-exposure) modal reference would make
  the reference deterministic and actuarially the more natural baseline. Affects
  only the diagnostic display of `polaris experience fit` / Slice-1 effects, not
  any pricing path → NICE-TO-HAVE. Surfaced while wiring the 4b-1 diagnostics CLI.
  *Source: ADR-146 Out of scope + DEV_SESSION_LOG_2026-07-22_experience_gam_slice4b1 Open Questions (2nd-order — a follow-up on the Slice-1 `factor_effect` behaviour).*

- **NICE-TO-HAVE — Capture observed feature ranges on `GAMFitResult` so effect
  assembly drops the `cells` reach-back.** `_collect_experience_effects` in the CLI
  reads each smooth term's observed span from the `cells` frame because the
  `GAMFitResult` does not carry the range; `smooth_effect(feature)` therefore also
  cannot default its grid to the observed range. Storing
  `feature_ranges: dict[str, tuple[float, float]]` on the result at fit time would
  let `smooth_effect` default its grid and let effect-shape assembly move onto the
  model as a public `all_effects(...) -> pl.DataFrame` (option 2/3 from the PR #148
  review) — so the CLI *and* the incoming Slice-4d dashboard call one public method
  instead of each re-deriving ranges from `cells`. Best landed **as part of Slice 4d**
  (when the dashboard becomes a second consumer of the tidy long-format frame), per
  the reviewer's recommendation — touch this surface once. The public
  `GAMFitResult.smooth_features` accessor (the P2 one-liner) already shipped in PR
  #148; this is the remaining, larger half. Internal coupling cleanup, no correctness
  or commercial impact → NICE-TO-HAVE.
  *Source: PR #148 review [P2] (option 3) + ADR-146 + CONTINUATION_experience_gam Slice-4b-1 key decisions (1st-order — a review-driven refinement of the 4b-1 GAM-fit surface).*

_Slice 4b-1's remaining ADR-146 out-of-scope items (assumption versioning, `--config`/
`AssumptionSet` wiring, loaders + validation deck, diagnostic plots + docs) are already
first-class planned slices in `CONTINUATION_experience_gam` (4b-2/4b-3/4c/4d) and are picked
up by the routine via step 5, so they are not re-promoted here (would duplicate the ledger)._

- **NICE-TO-HAVE — Configurable held-capital basis (target multiple of ACL)
  for US RBC.** The US RBC module (Epic 3 Slice 1) fixes the held-capital basis
  fed to return-on-capital at the **Company Action Level** (= 2× Authorized
  Control Level = the covariance result). Reinsurers commonly hold a *target
  multiple* of ACL (typically 300–400%); a configurable multiple would let the
  RoC denominator reflect a cedant's actual capital target rather than the
  regulatory floor. Affects the magnitude of the RBC return-on-capital number,
  not first-deal correctness or the LICAT/common path → NICE-TO-HAVE. Resolve
  the design (where the multiple is set — on `RBCCapital` vs `run_with_capital`)
  in Epic 3 Slice 2/4. **Update (ADR-106, Slice 4c-2b):** the CLI/API/Excel/
  dashboard now accept an *absolute* available-capital numerator; the
  target-multiple form is the alternative numerator entry mode and would attach
  to the same dashboard `number_input` / CLI flag. Generalises beyond US RBC to
  all three standards (the numerator surface is jurisdiction-agnostic).
  *Source: ADR-098 Out of scope + CONTINUATION_cross_jurisdiction_capital Open Questions (1st-order); reinforced by ADR-106 / DEV_SESSION_LOG_2026-06-26 Open Questions.*

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

- ~~**NICE-TO-HAVE — Result-level solvency-ratio surface (own funds / SCR).** The
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
  presentation surfacing re-pointed to Slice 4c-2b, notebook to 4c-2c.*~~ —
  **SHIPPED** (PR #106, closing Epic 3): the full result-level solvency-ratio
  surface is now complete — core (4c-1/ADR-103), CLI+API machine surfaces
  (4c-2a/ADR-104, PR #103), Excel ratio row + dashboard input/tile (4c-2b/ADR-106,
  PR #105), and the three-standard validation notebook (4c-2c/ADR-107, this PR).
  LICAT/RBC/EU solvency ratios are surfaced on every consumer.

- **NICE-TO-HAVE — Stochastic reinvestment yields for the asset model
  (Hull-White / CIR).** The Asset/ALM epic (Epic 4) prices bond cash flows and,
  in later slices, investment income and Modco interest on a **flat / book
  yield**. ROADMAP 5.4 envisions integrating `analytics/stochastic.py`
  (Hull-White / CIR rate paths) so reinvestment yields are scenario-driven
  rather than flat. This is deliberately out of the epic's core scope (the flat
  book yield is enough to make Modco economically correct vs today's hand-set
  rate) and would otherwise be invisible once the epic closes. Affects asset
  reinvestment precision under rate scenarios, not the flat-rate first-deal
  Modco path → NICE-TO-HAVE.
  *Source: ADR-108 Out of scope (1st-order).*

- **NICE-TO-HAVE — Non-fixed-income asset classes for the asset model.** The
  Asset/ALM epic (Epic 4) models **bonds only** (coupon + principal
  fixed-income instruments). A reinsurer's asset portfolio backing ceded
  reserves can also hold equities, mortgages, and other classes with different
  cash-flow and duration behaviour. Extending `AssetPortfolio` beyond bonds
  would let the duration-gap and investment-income analytics reflect a real
  mixed portfolio. Affects books backed by non-bond assets, not the
  bond-backed common path → NICE-TO-HAVE.
  *Source: ADR-108 Out of scope (1st-order).*

- **NICE-TO-HAVE — Net-of-spread asset book yield.** Per the Epic 4 design
  resolution (maintainer, 2026-06-26), `AssetPortfolio.book_yield()` (Slice 2)
  is the **gross** IRR of carrying value vs cash flows. The modco rate a
  reinsurer actually credits is typically a *net* earned rate — gross book yield
  less an investment-expense / default-allowance spread. A net-of-spread option
  on the book yield would let the modco interest reflect the net portfolio
  return, kept deliberately distinct from the C-1 capital component so
  asset-default risk is not double-counted. Affects the magnitude of the
  asset-driven modco rate, not first-deal correctness or the flat-rate path →
  NICE-TO-HAVE.
  *Source: PLAN_asset_alm §5 / CONTINUATION_asset_alm design resolution (1st-order).*

- **NICE-TO-HAVE — Time-varying (amortising) asset earned rate.** The Epic 4
  book yield is a **scalar held flat** over the horizon (design resolution,
  2026-06-26). As the portfolio amortises and bonds mature, the true earned rate
  drifts; a time-varying earned-rate vector recomputed along the run-off would
  make the asset-driven modco interest and the ALM duration-gap analytics more
  accurate on long-dated or barbelled portfolios. Affects rate precision over
  the projection, not first-deal correctness or the flat-rate path →
  NICE-TO-HAVE.
  *Source: PLAN_asset_alm §5 / CONTINUATION_asset_alm design resolution (1st-order).*

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

- **IMPORTANT — GAAP (FAS 60) concrete reserve basis.** *(ADDRESSED in draft,
  pending merge — TermLife GAAP shipped 2026-07-04, ADR-127, Slice 3; WholeLife
  GAAP shipped 2026-07-04 in a draft PR, ADR-128, Slice 4. GAAP now computes for
  **both** Term and Whole Life; the Reserve-Basis Exactness epic is COMPLETE. The
  morning ledger-healing step should strike this through once the Slice-4 PR
  merges to main. Do not re-select.)* The reserve-basis epic shipped
  NET_PREMIUM / CRVM / VM-20 / GAAP (FAS 60) for Term and Whole Life and surfaced
  the selector. GAAP is the net-premium benefit reserve on locked-in
  best-estimate + PADs (net **level** premium, prospective to omega for WL). US
  GAAP is a basis a US cedant commonly reports on, so reproducing it is part of
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

- ~~**IMPORTANT — Pipeline golden baselines for the `coins` and `policy_cession`
  configs (config-driven, drift-guarded).** `data/qa/` ships four pricing configs
  (`flat`, `yrt`, `coins`, `policy_cession`) but `tests/qa/golden_outputs/` pins
  byte-level baselines for only two (`golden_flat`, `golden_yrt`). The coinsurance
  and policy-cession pipeline paths are exercised end-to-end only by CLI **smoke**
  tests (`test_cli_golden.py::TestCLIGoldenSmoke` — exit-0, no value assertion);
  their numbers are not pinned to a committed baseline, so a silent numeric
  regression in the coinsurance **reserve transfer** (proportional reserve cession,
  CLAUDE.md §9 — actuarially subtle) or in policy-level cession weighting would pass
  the QA suite. The underlying math is unit-tested in `test_reinsurance/`, so this
  is a defense-in-depth gap, not an unprotected path → IMPORTANT (correctness net on
  the common coinsurance path), not BLOCKER. **Root cause:** `generate_golden.py`
  hardcodes `PipelineInputs` for `flat`/`yrt` and never reads the JSON configs, so
  the generator and the committed config set drift. **Fix (Option A — recommended):**
  (1) make `generate_golden.py` and `test_pipeline_golden.py` both *enumerate*
  `data/qa/golden_config_*.json` and load each through the same config path the CLI
  uses (delete the hand-built `PipelineInputs`); (2) generate + commit
  `golden_coins.json` + `golden_policy_cession.json`; (3) parametrize the regression
  over the discovered config set, applying `@requires_soa_tables` per-config by its
  mortality source (flat → always-on, SOA → gated); (4) add a **drift-guard** test
  asserting every `golden_config_*.json` has a matching baseline (or is explicitly
  SOA-gated), so a future config fails loudly instead of silently becoming
  smoke-only. Pure test-infra (no product/analytics code, zero engine golden-output
  risk); SMALL (~1 session). Routine disposition: Tier-B between-epics quick win —
  fallback work under the active-epic guardrail, picked up when Epic 3's next slice
  is blocked.
  *Source: PR #103 automated review — P2 finding (1st-order; QA-harness follow-up
  surfaced during review, not introduced by #103).*~~ — **SHIPPED** (PR #104,
  ADR-105): config-driven golden harness — `generate_golden.py` /
  `test_pipeline_golden.py` enumerate `data/qa/golden_config_*.json` via the
  shared `golden_runner` (CLI parser), committed `golden_coins.json` +
  `golden_policy_cession.json` baselines, parametrized regression with per-config
  SOA gating, and a drift-guard test that fails loudly on any unbaselined config.
  `flat`/`yrt` byte-identical; QA suite 76 passed.

- **NICE-TO-HAVE — Cash-flow-vector golden (finer-grained than per-cohort
  summary).** The pipeline golden (ADR-105) pins per-cohort *summary* metrics (PV
  profits, margins, gross premiums/claims), not the full cash-flow vectors. A
  vector-level golden would catch offsetting per-period errors that net to the
  same summary. Defense-in-depth refinement of an already-shipped net, not a
  correctness gap on the common path → NICE-TO-HAVE.
  *Source: ADR-105 Out of scope (2nd-order — follow-up of the config-driven
  golden harness, itself a 1st-order PR #103-review follow-up).*

- **NICE-TO-HAVE — Pipeline goldens for Modco / stop-loss treaty configs.** The
  config-driven harness (ADR-105) auto-discovers any new
  `data/qa/golden_config_*.json` and the drift guard enforces a committed
  baseline, so adding a Modco or stop-loss golden is now a one-file change once
  those treaty configs exist. Tracks the remaining treaty types not yet
  represented by a golden config → NICE-TO-HAVE.
  *Source: ADR-105 Out of scope (2nd-order).*

- **NICE-TO-HAVE — Per-side available-capital numerator for the solvency ratio.**
  The solvency-ratio surfaces (CLI/API in 4c-2a, Excel/dashboard in 4c-2b) apply
  a single supplied available-capital figure to BOTH the cedant and reinsurer
  perspectives, each dividing by its own required capital. A reinsurer evaluating
  both sides of a deal may hold distinct available capital per entity; a per-side
  numerator input would let each ratio use its own numerator. Symmetric with how
  peak/RoC are surfaced today, so this is a refinement, not a correctness gap →
  NICE-TO-HAVE.
  *Source: ADR-104/ADR-106 Out of scope + DEV_SESSION_LOG_2026-06-26 Open Questions (2nd-order — follow-up of the available-capital numerator, itself a 1st-order Epic-3 surface).*

- **NICE-TO-HAVE — Mutually calibrate the three capital standards' factors
  (Asset/ALM epic).** Closing Epic 3, the three-standard validation notebook
  (`notebooks/03_capital_standards_comparison.ipynb`, ADR-107) made concrete that
  the standards are **not yet mutually calibrated**: on an identical $5M NAR the
  required-capital *levels* differ ~100x (LICAT peak $750K vs US RBC $7.5K vs EU
  Solvency II $13.9K), because LICAT's default C-2 is a **10% mortality shock** on
  NAR while RBC (0.15%) and Solvency II (0.20%) are small ongoing factors. Each
  standard is internally sound and the solvency ratio is meaningful *within* a
  standard (linear in available capital), but cross-standard *level* comparison is
  not yet valid. Shock-based calibration that puts the three on a comparable basis
  is the C0 Asset/ALM epic; until then the committee-stage placeholders are
  acceptable for single-jurisdiction screening (the disposition the LICAT module
  already uses). Affects cross-standard comparison only, not single-jurisdiction
  first-deal correctness → NICE-TO-HAVE.
  *Source: ADR-107 Out of scope + CONTINUATION_cross_jurisdiction_capital Open Questions "Factor calibration sign-off" (1st-order — follow-up of the originally-planned Epic 3 capital feature).*

- ~~**IMPORTANT — Canonical liability cash-flow stream for the ALM duration gap
  (Asset/ALM Slice 4b).** Slice 4a (ADR-111) shipped the `analytics/alm.py`
  duration-gap core. Its `liability_cash_flows(result)` provides a *documented
  default* — net benefit outgo (`death_claims + lapse_surrenders + expenses -
  gross_premiums`) — but when Slice 4b threads the gap into the CLI/API/dashboard
  and it drives a **surfaced** number, the convention must be confirmed: the
  **net** reinsurer position vs the **ceded** side, and whether the reserve basis
  affects which obligation stream the assets are matched against. This picks the
  number a committee reads off the ALM block, so it is correctness-relevant on the
  Modco/coinsurance path → IMPORTANT. Resolve with the maintainer when wiring the
  Slice 4b surface.~~ — **SHIPPED** (PRs #112 + #113, Slices 4b-2a + 4b-2b): the maintainer settled
  the convention (Option B reserve-backed liability, reinsurer-view headline) and
  it is fully implemented. 4b-2a (ADR-113) made the liability the reserve run-off
  stream (PV ties to the held reserve, basis-agnostic across NET_PREMIUM / CRVM /
  VM20 / GAAP); 4b-2b (ADR-114) computes the gap on **both** the ceded
  (reinsurer-view, headline) and cedant-retained sides on each side's reserve, on
  the CLI and the `/api/v1/price` surface.
  *Source: ADR-111 Out of scope + DEV_SESSION_LOG_2026-06-27_asset_alm_slice4a Open Questions (1st-order — follow-up of the originally-planned Epic 4 Slice 4 surfacing).*

- **NICE-TO-HAVE — Asset-yield vs liability-discount-rate split in the duration
  gap.** Slice 4a measures both sides of the duration gap at one common flat
  `valuation_yield` by design, isolating the timing mismatch from any yield
  difference. A refinement could discount the asset side at its book yield and the
  liability at a separate valuation/credit rate, reporting the gap net of the
  yield-basis difference (closer to an economic-capital duration gap). Affects the
  precision of an analytics output, not first-deal pricing correctness, and is a
  refinement of the deliberate flat-yield design choice → NICE-TO-HAVE.
  *Source: ADR-111 + DEV_SESSION_LOG_2026-06-27_asset_alm_slice4a Open Questions (2nd-order — follow-up of the single-valuation-yield design choice, itself the 1st-order Slice 4a decision).*

- **NICE-TO-HAVE — Distinct cedant-held vs reinsurer-held asset portfolios in the
  duration gap.** Slice 4b-2b (ADR-114) measures **one** supplied `AssetPortfolio`
  against both the ceded (reinsurer-view) and cedant-retained reserve liabilities —
  the asset side is identical across the two sides; only the liability differs. In
  reality the cedant and reinsurer hold different asset books (especially under
  modco, where the cedant retains the assets), so a true cedant-side gap would take
  a separate cedant portfolio. Supporting a second portfolio would let the dual gap
  reflect each party's actual assets rather than a shared book. Affects the
  precision of the secondary (cedant) ALM view, not the headline reinsurer gap or
  first-deal pricing correctness → NICE-TO-HAVE.
  *Source: ADR-114 Out of scope (1st-order — follow-up of the originally-planned Epic 4 Slice 4 surfacing).*

- **NICE-TO-HAVE — Conditional formatting on the Excel "ALM Duration Gap" sheet.**
  Slice 4b-3a (ADR-115) renders the duration-gap sheet with plain number formats,
  matching the CLI Rich block. A risk reviewer scanning a committee packet would
  benefit from a visual flag on a large negative dollar-duration gap (assets much
  shorter than the liability — the unhedged surplus exposure), e.g. a red fill /
  threshold rule, mirroring how the YRT rate-table sheet greys filled cells. Pure
  presentation polish on a new, non-golden sheet; no effect on the numbers or on
  first-deal pricing → NICE-TO-HAVE.
  *Source: ADR-115 Out of scope (1st-order — follow-up of the originally-planned Epic 4 Slice 4 surfacing).*

- **NICE-TO-HAVE — Saved / file-upload asset portfolio on the dashboard ALM
  input.** Slice 4b-3b (ADR-116) takes the dashboard asset side as a per-run JSON
  paste in the Deal Pricing expander. The YRT rate table, by contrast, has a
  persisted file-upload widget; an analyst iterating on a deal must re-paste the
  portfolio JSON on each session. A saved-portfolio / `st.file_uploader`
  affordance (parsed into the same `AssetPortfolio`) would remove the re-paste and
  match the rate-table UX. Pure dashboard convenience — the analytics and the CLI
  config surface are unchanged, and the per-run paste already prices correctly → so
  no effect on first-deal correctness → NICE-TO-HAVE.
  *Source: ADR-116 Out of scope + DEV_SESSION_LOG_2026-06-29_asset_alm_slice4b3b Open Questions (1st-order — follow-up of the originally-planned Epic 4 Slice 4b-3b dashboard surface).*

- **NICE-TO-HAVE — Generic "execute every notebook" CI guard.** Slice 4b-4
  (ADR-117) added `tests/test_notebooks/test_alm_duration_gap_notebook.py`, which
  reads `notebooks/04_alm_duration_gap.ipynb` with `nbformat` and `exec`s its code
  cells so the embedded closed-form reconciliations run in CI. That guard covers
  **only** notebook 04; notebooks 01–03 (`01_term_life_yrt_pricing`,
  `02_reserve_basis_comparison`, `03_capital_standards_comparison`) have no
  execution guard and can silently rot when an API they call changes. A
  parametrised guard that discovers and execs every `notebooks/*.ipynb` (skipping
  any that need a kernel/data the suite can't provide) would close that gap and
  make the per-epic notebooks self-verifying. Pure test-infra hardening — no effect
  on engine correctness or first-deal pricing → NICE-TO-HAVE.
  *Source: ADR-117 Out of scope + DEV_SESSION_LOG_2026-06-29_asset_alm_slice4b4 (1st-order — follow-up of the originally-planned Epic 4 Slice 4b-4 validation notebook).*

- **NICE-TO-HAVE — Gross- vs ceded-basis loss ratio for the expense-allowance
  sliding scale.** The new `ExpenseAllowance` (Expense-allowance epic, Slice 1,
  ADR-118) selects its sliding-scale renewal rate from the **ceded** loss ratio
  (`ceded_claims.sum()/ceded_premiums.sum()`) — the reinsurer's own experience
  drives its allowance, which Slice 2 will pass in. Some treaties quote the
  sliding scale against the **gross** block loss ratio instead. A basis selector
  on `ExpenseAllowance` (ceded vs gross) would let the engine reproduce those
  treaties. Affects only sliding-scale deals quoted on the gross basis, not the
  flat-allowance or ceded-basis common path → NICE-TO-HAVE.
  *Source: ADR-118 Out of scope + DEV_SESSION_LOG_2026-06-29_expense_allowance_slice1 Open Questions (1st-order).*

- **NICE-TO-HAVE — Dedicated expense-allowance line on `CashFlowResult`.** The
  Expense-allowance epic (Slice 2) folds the reinsurer→cedant allowance into the
  existing `expenses` line as a transfer (+A ceded / −A net) so the
  `net + ceded == gross` invariant holds with **no contract change**. A dedicated
  `expense_allowance` array on `CashFlowResult` would let reports show the
  allowance distinctly from operating expenses (cleaner committee presentation),
  but it is a core-contract change requiring an ADR + backward-compat default.
  Reporting/presentation polish, not first-deal correctness → NICE-TO-HAVE.
  *Source: ADR-118 Out of scope + DEV_SESSION_LOG_2026-06-29_expense_allowance_slice1 Open Questions (1st-order).*

- **NICE-TO-HAVE — Survivorship-weight the expense-allowance first-year fraction.**
  Slice 2 maps projection month → policy duration via a **face-weighted** first-year
  fraction `f[t]` (`ExpenseAllowance.first_year_fraction_for_block`), ignoring
  decrements between valuation and projection month `t`. It is **exact at the
  all-new and all-renewal boundaries** (the common inforce cases) and only blends
  approximately across the policy-year-one transition of a *mixed-duration* block.
  Weighting `f[t]` by in-force survivorship (lx) would sharpen the blend for a block
  with policies straddling the year-one boundary. Second-order accuracy on a
  non-common path → NICE-TO-HAVE. *Source: ADR-119 Out of scope (1st-order).*

- **NICE-TO-HAVE — Per-policy (seriatim) expense-allowance allocation.** Slice 2
  computes the allowance on the **aggregate** ceded premium stream with a
  face-weighted first-year fraction, rather than per-policy (the way `YRTTreaty`
  has a seriatim premium path when `seriatim_lx`/`seriatim_reserves` are present).
  A seriatim allowance would let each policy's own duration drive its first-year
  split exactly and support per-policy allowance reporting, at the cost of an
  (N,T) computation. The aggregate face-weighted fraction is correct on the common
  path (single-cohort or all-renewal blocks); seriatim matters only for large,
  duration-heterogeneous books → NICE-TO-HAVE. *Source: ADR-119 Out of scope (1st-order).*

- **NICE-TO-HAVE — Annual / per-period experience-refund settlement timing.** The
  new `ExperienceRefund` (Expense-allowance epic, Slice 3a, ADR-120) computes a
  single **end-of-horizon scalar** refund from the accumulated experience account.
  A real large YRT/coinsurance treaty frequently settles the experience refund
  **annually** (per experience period), refunding favourable experience each year
  rather than once at projection end. Adding a per-period / annual settlement schedule
  (and the matching terminal-transfer placement in Slice 3b) would let the engine
  reproduce those treaties' year-by-year refund cash flows. The end-of-horizon scalar
  is correct for a single-settlement treaty (the common first-deal case) → NICE-TO-HAVE.
  *Source: ADR-120 Out of scope + DEV_SESSION_LOG_2026-06-30_experience_refund_slice3a
  Open Questions (1st-order — follow-up of the originally-planned Slice 3).*

- **NICE-TO-HAVE — Experience-refund deficit carryforward.** `ExperienceRefund`
  (Slice 3a, ADR-120) refunds nothing on an unfavourable (negative) experience
  balance and does **not** carry the deficit forward against future favourable
  experience. Multi-period treaties often carry a loss forward so a good year only
  refunds after an earlier bad year is recovered. A deficit-carryforward mode would
  model that, but it is meaningful only once per-period settlement exists (it is a
  refinement of the timing follow-up above) and matters only for multi-period books →
  NICE-TO-HAVE. *Source: ADR-120 Out of scope + DEV_SESSION_LOG_2026-06-30_experience_refund_slice3a
  Open Questions (1st-order — follow-up of the originally-planned Slice 3).*

- **IMPORTANT — Engage the block-aware first-year duration mapping when an
  `expense_allowance` is supplied via config.** Slice 3b-2a (ADR-122) lets a
  `polaris price --config` deal carry an `expense_allowance`, but the allowance's
  block-aware first-year duration mapping (`first_year_fraction_for_block`, ADR-119)
  only engages when the cohort `InforceBlock` reaches `treaty.apply()` — which today
  happens only when `deal.use_policy_cession` is set. With an `expense_allowance` set
  but `use_policy_cession` unset, the allowance falls back to the **new-business
  projection-month basis** (first 12 periods = first year), so a mid-duration inforce
  block is wrongly charged the high first-year rate on renewal business — overstating
  the allowance on the primary (inforce) use case. The fix is to force the cohort
  inforce through `apply()` whenever an `expense_allowance` is present (as the tabular
  YRT path already forces it), independent of `use_policy_cession`. Affects the first
  user of the config-supplied allowance on an inforce block → IMPORTANT.
  *Source: ADR-122 Out of scope + DEV_SESSION_LOG_2026-06-30_expense_allowance_slice3b2a
  Open Questions (1st-order — follow-up of the originally-planned allowance feature).*

- **NICE-TO-HAVE — Echo the applied `expense_allowance` / `experience_refund` terms
  back on the deal-pricing responses.** Slice 3b-2b-1 (ADR-123) lets the API request
  models carry both terms, and they move the priced numbers, but no response field
  echoes *which* terms were applied — unlike `reserve_basis`, which `PriceResponse`
  echoes so a client can confirm the basis that drove the numbers. A caller (or an
  audit trail) cannot read back from a `/api/v1/price` response whether an allowance/
  refund was honoured or what its rates were; they must trust the request. Adding an
  optional echo block (the resolved terms) to `PriceResponse` / scenario / uq / the CLI
  JSON would close the auditability gap. Affects reporting/audit, not the common pricing
  path → NICE-TO-HAVE. *Source: ADR-123 Out of scope + DEV_SESSION_LOG_2026-06-30_expense_allowance_slice3b2b1
  (1st-order — follow-up of the originally-planned allowance-surfacing feature).*

- **NICE-TO-HAVE — The `use_policy_cession` block-aware-duration follow-up (above) now
  applies to the API path too.** The same new-business-projection-month fallback the
  IMPORTANT config item describes affects `/api/v1/price` (and scenario / uq /
  portfolio) once an `expense_allowance` is supplied through the request models added in
  Slice 3b-2b-1 — the fix (force the cohort inforce through `apply()` whenever an
  allowance is present) is the single shared one in `treaty.apply()`, so this is a scope
  note on the IMPORTANT item, not separate work. *Source: ADR-123 (2nd-order — follow-up
  of the use_policy_cession follow-up; scope note only, NICE-TO-HAVE per the polish cap).*

- **NICE-TO-HAVE — Surface the `expense_allowance` / `experience_refund` terms on the
  Streamlit dashboard + `DealConfig.to_dict()`.** The Expense-allowance epic (B3) surfaced
  both terms across the config, CLI, REST API, and deal-pricing Excel export (Slices 3b-2a
  through 3b-2b-2, ADR-122 → ADR-124), completing the epic — but the **dashboard** has no
  input for either term, and `DealConfig.to_dict()` deliberately omits both (the
  `yrt_rate_table_*` / reserve-basis dashboard-parity omission precedent), so a dashboard
  round-trip silently drops them. Adding a dashboard input surface (allowance FY/renewal % +
  optional sliding-scale bands; refund %, retention, margin, interest) and the matching
  `to_dict()` round-trip would give the dashboard parity with the CLI/API/Excel surfaces.
  Deferred until a dashboard surface actually consumes the terms; pure parity polish for the
  dashboard, not first-deal correctness → NICE-TO-HAVE. *Source: ADR-124 Out of scope +
  DEV_SESSION_LOG_2026-07-03_expense_allowance_slice3b2b2 (1st-order — follow-up of the
  originally-planned B3 allowance-surfacing feature, the one deal-pricing consumer the epic
  did not cover).*

- **NICE-TO-HAVE — Sex/smoker-distinct statutory valuation table composition
  helper.** The new `AssumptionSet.valuation_mortality` slot (Reserve-Basis
  Exactness epic, Slice 1, ADR-125) takes a single composed `MortalityTable`.
  The 2001 CSO conversion produces per-sex CSVs (and cedant filings may
  prescribe smoker-distinct variants); composing them into the multi-key
  `MortalityTable` the slot expects is manual today. A composition helper
  (load per-sex/smoker CSVs → one valuation `MortalityTable`) would make the
  Slice-2 config surface ergonomic for real filings. Affects convenience of
  the prescribed-table path, not correctness → NICE-TO-HAVE.
  *Source: ADR-125 Out of scope + CONTINUATION_reserve_basis_exactness
  Refinement Backlog (1st-order).*

- **IMPORTANT — Prescribed statutory valuation-interest helper** (~~NICE-TO-HAVE~~,
  reclassified 2026-07-04 per the PR #125 review). Statutory CRVM prescribes the
  maximum valuation interest rate by issue year / product; the engine takes a
  single manual `valuation_interest_rate` on `ProjectionConfig`. An issue-year →
  prescribed-rate lookup helper would complete "reproduce the cedant's basis" on
  the interest side the way ADR-125/126 does on the mortality side.
  **Reclassification rationale:** the Reserve-Basis Exactness epic's headline
  commercial claim is *penny-exact reproduction of the cedant's held statutory
  reserve* (to price coinsurance/modco, quantify reserve/capital relief, and
  defend the profit signature to auditors). `valuation_mortality` (Slices 1–2)
  fixes only the **mortality** half; without prescribed valuation interest the
  reproduction is directional, not exact — so this gates the epic's own value
  proposition on the common statutory path, i.e. IMPORTANT, not convenience.
  Sequence it before positioning "exact CRVM reproduction" as done.
  *Source: ADR-125 Out of scope + CONTINUATION_reserve_basis_exactness
  Refinement Backlog (1st-order); reclassified per ADR-126 design boundary /
  PR #125 review.*
- **NICE-TO-HAVE — Issue-year → CSO-version selector.** 2001 vs 2017 CSO
  applicability is issue-year-driven (2017 CSO mandatory for 2020+ issues,
  elective 2017–2019); `valuation_mortality` takes one named table per deal, so
  a block straddling the applicability boundary must be split or the correct
  table chosen manually. An issue-year → CSO-version selector (and straddle
  handling) would make the prescribed-table path correct-by-default for
  multi-vintage blocks. Convenience on multi-vintage books, not a common-path
  correctness bug → NICE-TO-HAVE.
  *Source: ADR-126 design boundary + CONTINUATION_reserve_basis_exactness
  Refinement Backlog (1st-order).*

- **NICE-TO-HAVE — CSV-path escape hatch for an arbitrary cedant valuation
  table.** Slice 2 (ADR-126) surfaces `valuation_mortality` as a **named source
  id** only (`CSO_2001` / `SOA_VBT_2015` / `CIA_2014` / `flat`). A cedant whose
  prescribed valuation table is not one of the shipped named sources cannot yet
  point the deal at an arbitrary CSV directory the way `yrt_rate_table_path`
  allows for YRT rates. Adding a `valuation_mortality_path` config/CLI/API
  surface (loading a directory of valuation-table CSVs) would complete the
  exact-reproduction story for non-standard cedant tables. Affects only cedants
  off the named-source path, not correctness on the common path → NICE-TO-HAVE.
  *Source: ADR-126 Out of scope (1st-order).*

- **NICE-TO-HAVE — Echo the prescribed valuation table on the API response /
  Excel / dashboard surfaces.** Slice 2 (ADR-126) echoes the selected
  `valuation_mortality` only in the CLI JSON `summary` (conditionally, to
  preserve byte-identity). The REST `PriceResponse`, the deal-pricing Excel
  workbook, and the dashboard pricing surface do not record which prescribed
  table drove the statutory reserve. Surfacing it (a nullable response field +
  an Assumptions-sheet / dashboard line) would give the same audit visibility
  the CLI has. Pure reporting polish, no priced-number change → NICE-TO-HAVE.
  *Source: ADR-126 Out of scope (1st-order).*

- **IMPORTANT — Surface the GAAP (FAS 60) PADs on the deal path
  (`DealConfig` / CLI / API).** Slices 3–4 (ADR-127 / ADR-128) implemented GAAP
  for **both** TermLife and WholeLife and put the two provisions for adverse
  deviation on `ProjectionConfig` (`gaap_mortality_pad`, `gaap_interest_margin`,
  both neutral-default). A `ProjectionConfig` built directly (notebooks /
  analytics) can set them, but the CLI config parser, `--gaap-*` flags, and the
  REST `PriceRequest` do not yet expose them — so a CLI/API user gets GAAP only at
  neutral PADs (= locked-in best-estimate NPR) on either product. FAS 60 PADs are
  company-specific and are exactly what reproduces the cedant's GAAP benefit
  reserve, so this is part of "match the cedant's basis," not polish. Mirror the
  dedicated surfacing slice `valuation_mortality` got (ADR-125 engine → ADR-126
  deal path) → IMPORTANT.
  *Source: ADR-127 / ADR-128 Out of scope (1st-order).*

- **NICE-TO-HAVE — FAS 60 DAC amortisation + loss-recognition / premium-deficiency
  test.** Slice 3 (ADR-127) models the GAAP **benefit reserve** only. A full FAS 60
  GAAP picture also amortises deferred acquisition costs (DAC) against a premium /
  gross-profit basis and runs a loss-recognition (premium-deficiency) test that can
  write DAC down and establish an additional liability. These change the GAAP
  earnings signature (not the benefit reserve) and are beyond the reserve-basis
  epic's "reproduce the cedant's reserve" scope → NICE-TO-HAVE.
  *Source: ADR-127 Out of scope (2nd-order — a follow-up of the GAAP follow-up).*

- **NICE-TO-HAVE — Duration-varying / select-period GAAP PAD structures.** Slice 3
  applies a single flat mortality multiplier and a flat interest haircut. A real
  FAS 60 valuation may grade PADs by policy duration or use a select-period margin.
  Design completeness for GAAP, not common-path correctness → NICE-TO-HAVE.
  *Source: ADR-127 Out of scope (2nd-order — a follow-up of the GAAP follow-up).*

- ~~**IMPORTANT — WholeLife does not model mortality improvement on any basis.**~~
  — **SHIPPED** (PR #128, ADR-129): `WholeLife._build_rate_arrays` now applies a
  configured `AssumptionSet.improvement` scale (mirroring TermLife) on every
  best-estimate basis (projection cash flows, NET_PREMIUM, GAAP, VM-20 DR); the
  prescribed statutory bases (CRVM, VM-20 NPR) stay static via an explicit
  `apply_improvement` caller flag on `_build_valuation_mortality`. Byte-identical
  on all goldens (no config sets WL improvement — verified). 11 closed-form /
  guardrail tests in `test_wl_improvement.py`. Slice 1 of the Reserve-Basis
  Correctness epic.
  *(NEXT UP — reprioritised to the front of the queue at the maintainer's
  direction 2026-07-05, ahead of the interest-exactness work, because this is a
  silent correctness bug, not exactness polish. Constituted as **Slice 1 (NEXT)**
  of the active epic "Reserve-Basis Correctness & Interest Exactness" —
  `docs/PLAN_reserve_basis_correctness.md` / `CONTINUATION_reserve_basis_correctness.md`,
  status IN PROGRESS. The next daily-dev run picks it up at step 5.)*
  Surfaced while implementing WL GAAP (Slice 4, ADR-128): `TermLife._build_rate_arrays`
  applies the configured `AssumptionSet.improvement` scale to the projection `q`,
  but `WholeLife._build_rate_arrays` (and hence every WL reserve basis —
  NET_PREMIUM / CRVM / VM-20 / GAAP — plus the WL projection cash flows) never
  reads `improvement`, so a WL block priced with an improvement scale configured
  **silently ignores it**. This is a pre-existing, WL-wide gap (not GAAP-specific);
  it is why the TermLife GAAP "reflects improvement" guardrail test has no WL
  analogue. It affects the common WL pricing path (best-estimate mortality is a
  touch conservative vs the intended improving basis) and the trust/auditability
  of the projected numbers → IMPORTANT. Fix: apply `improvement` in
  `WholeLife._build_rate_arrays` (and the to-omega `_build_valuation_mortality`
  where a best-estimate basis is valued — GAAP/VM-20 DR — but NOT the statutory
  `valuation_mortality` path, which is prescribed-static by design). Guard with a
  golden-byte-identity check (no golden configures WL improvement) and a
  closed-form improvement-isolation test mirroring TermLife.
  *Source: ADR-128 Out of scope + DEV_SESSION_LOG_2026-07-04_reserve_basis_exactness_slice4
  Open Questions (1st-order — surfaced by the originally-planned Slice-4 WL GAAP work).*

- **NICE-TO-HAVE — Regenerate COMMERCIAL_VIABILITY_REVIEW at the Slice-1
  checkpoint / 30-day mark.** *(PARTIALLY RESOLVED 2026-07-05: the next epic IS
  now constituted — "Reserve-Basis Correctness & Interest Exactness",
  `PLAN_reserve_basis_correctness.md`, IN PROGRESS, Slice 1 = the WL-improvement
  correctness fix above. What remains is the deliberate re-anchoring:)* the
  Reserve-Basis Exactness epic is COMPLETE and Phases 1–3 of the ROADMAP are done,
  so the modeling backlog is largely exhausted. Before the epic's interest-
  exactness slices (2–3) proceed, regenerate the viability review (re-review the
  last ~10 PRs + docs, re-rank the catalogue) to confirm interest-exactness is
  still the highest-value continuation vs a **productization** epic (data-ingestion
  robustness, an AXIS/Prophet benchmark validation, packaging/deployment,
  documentation). This is the guard against an epic-level polish spiral now that
  the modeling roadmap is done, and it also satisfies the ~2026-07-18 30-day
  staleness trigger. Scheduled as the CONTINUATION checkpoint after Slice 1.
  *Source: DEV_SESSION_LOG_2026-07-04_reserve_basis_exactness_slice4 Open Questions
  + PLAN_reserve_basis_correctness Checkpoint (1st-order).*
  **— RESOLVED 2026-07-05 (checkpoint regenerated): `COMMERCIAL_VIABILITY_REVIEW_2026-07-05.md`.**

- **NICE-TO-HAVE — Prescribed statutory valuation-interest helper (interest-
  exactness, Reserve-Basis Correctness Slices 2–3).** Issue-year → SVL max
  valuation rate / VM-20 NPR discount rate resolver, wired into CRVM / VM-20 NPR
  discounting for **penny-exact** statutory reserve reproduction (today a single
  manual `ProjectionConfig.valuation_interest_rate` makes it directional, not
  exact). *DEMOTED from Tier-A-epic to NICE-TO-HAVE by the 2026-07-05 checkpoint:*
  the modeling roadmap (Phases 1–5, all Tier-A epics, Asset/ALM, expense-allowance)
  is complete, so this exactness polish (★★★☆☆) no longer out-ranks the
  productization/credibility frontier (validation & benchmark pack, production
  hardening, ingestion robustness). Full PLAN/CONTINUATION preserved
  (`PLAN_reserve_basis_correctness.md` Slices 2–3) for revival on a real
  penny-exact cedant reproduction requirement — or immediate resumption if the
  maintainer declines the redirect (review §7). *Source:
  COMMERCIAL_VIABILITY_REVIEW_2026-07-05 §3–§5 + CONTINUATION_reserve_basis_correctness
  Checkpoint outcome (2nd-order — follow-up of the checkpoint follow-up above).*

- **IMPORTANT — Constitute a productization / credibility epic (next active epic).**
  With the modeling roadmap complete, the frontier is trust-and-deployment. Lead
  candidate **A1′ — validation & benchmark pack** (reproduce published statutory
  reserve decks / SOA illustrative values / closed-form textbook cases, and an
  AXIS/Prophet side-by-side where a reference output is obtainable, into a
  CI-executed validation suite + report notebook — backs the README's "credible
  alternative to AXIS/Prophet" thesis). Fallbacks if A1′ is reference-blocked:
  **A2′ production hardening & observability** (ROADMAP 6.2 — logging, auth, rate
  limiting, K8s/Helm) and **A3′ cedant-ingestion robustness** (harden the 4.2
  pipeline for messy real blocks). Next session should run a scoping pass and
  write `PLAN_<productization>.md` + slice 1. *Source:
  COMMERCIAL_VIABILITY_REVIEW_2026-07-05 §4–§5 (1st-order — direction item from the
  regenerated review).*
  - **ACTED ON (2026-07-05):** the **A1′ Validation & Benchmark pack** epic was
    constituted as the active epic and Slice 1 shipped — `PLAN_validation_benchmark.md`
    + `CONTINUATION_validation_benchmark.md` (IN PROGRESS), ADR-130, module
    `polaris_re.analytics.validation` (framework + closed-form seed set), 18 tests.
    Slice 2 shipped 2026-07-06 (ADR-131): the **SOA Illustrative Life Table** deck
    (`data/validation/illustrative_life_table.csv`, `STATUTORY_DECK` cases for
    whole-life `A_x`/`ä_x`/`P_x` reproduced by the WholeLife engine to machine
    precision) + `run_full_validation_pack()`, 26 tests. **Slice 3 shipped
    2026-07-06 (ADR-132) — the A1′ epic is now COMPLETE:** the pack is surfaced
    headless by `polaris benchmark` (`--pack {full,closed-form,deck}`, `-o`
    Markdown / `--json` export, **non-zero exit on any FAIL** so it can gate CI)
    and by `notebooks/05_validation_report.ipynb`; 11 tests. The planned
    `polaris validate` name was **already taken** by input-file schema validation,
    so the command was named `polaris benchmark` (the verify-premise correction —
    `validate` = check your files, `benchmark` = check the engine). The redirect
    go/no-go remains reserved for the maintainer: with A1′ done, the parked
    interest-exactness epic (`CONTINUATION_reserve_basis_correctness`, Slices 2–3)
    is the natural next active epic unless the maintainer redirects.
  - **ACTED ON (2026-07-07):** A1′ was not reference-blocked, so per the review's
    recommended sequence (§5: A1′ → **A2′ Production hardening** → A3′) the next
    Tier-A epic constituted is **A2′ Production Hardening & Observability**
    (ROADMAP 6.2) — `PLAN_production_hardening.md` + `CONTINUATION_production_hardening.md`
    (IN PROGRESS). **Slice 1 shipped 2026-07-07 (ADR-133):** `api/observability.py`
    — structured JSON access logging with a per-request **correlation id**
    (`X-Request-ID`/`X-Correlation-ID` echo or uuid4) and monotonic-clock duration,
    surfaced as `X-Correlation-ID`/`X-Response-Time-Ms` response headers via
    `RequestContextMiddleware`; 12 tests; goldens byte-identical. **PR #133 MERGED
    (ledger-healed 2026-07-09).** **Slice 2 shipped 2026-07-09 (ADR-134):**
    `api/observability.py`'s sibling `api/auth.py` — two **default-off** Starlette
    middlewares wired inside `RequestContextMiddleware`: `APIKeyAuthMiddleware`
    (env `POLARIS_API_KEYS`; `X-API-Key` / `Bearer`; 401 + correlation-stamped log;
    probes exempt) and `RateLimitMiddleware` (env `POLARIS_API_RATE_LIMIT`; 429 +
    `Retry-After`; hand-rolled dependency-free `SlidingWindowRateLimiter` with an
    injectable clock — a deliberate deviation from the plan's `slowapi` suggestion,
    keeping the zero-new-runtime-dep property and clock-safe tests). 34 tests;
    goldens byte-identical. **PR #134 MERGED (ledger-healed 2026-07-10).**
    **Slice 3 shipped 2026-07-10 (ADR-135), epic COMPLETE:** `api/metrics.py` — a
    dependency-free Prometheus `/metrics` endpoint (text exposition v0.0.4) fed by
    `MetricsMiddleware` (request counter + latency histogram; route-template `path`
    label bounded by `__unmatched__`; exempt from auth/rate-limiting), the
    PR #134 [P2] proxy-aware rate keying (`POLARIS_TRUSTED_PROXIES` → trusted
    `X-Forwarded-For`), deployment manifests under `deploy/` (raw K8s + Helm chart),
    a Prometheus scrape config, Grafana provisioning, and `docker-compose`
    `prometheus`+`grafana` services. 34 tests; goldens byte-identical. Draft PR
    open (to be ledger-healed on merge). **The A2′ epic is now COMPLETE** —
    `PLAN_production_hardening.md` / `CONTINUATION_production_hardening.md` are
    marked COMPLETE. The interest-exactness epic remains parked
    open-but-deprioritised (Tier-D per the review); the maintainer redirect
    go/no-go is still open.

- **NICE-TO-HAVE — AXIS/Prophet side-by-side validation case.** A licensed-tool
  reference output would let the validation pack (A1′) assert against the incumbent
  systems directly, not just closed-form/published references. Currently
  REFERENCE-BLOCKED (no licensed tool / reference output obtainable in CI); revive
  only if the maintainer supplies a reference output. *Source: ADR-130 Out of scope
  (2nd-order — follow-up of the A1′ validation-epic follow-up → NICE-TO-HAVE per the
  step-17 order cap).*

- ~~**NICE-TO-HAVE — WholeLife-to-omega closed-form validation case.** Slice 1 of the
  validation pack validates via TermLife (the simplest engine); a WholeLife
  net-single-premium / reserve closed-form case would extend coverage to the
  accumulation-product path. Candidate for Slice 2. *Source: ADR-130 Out of scope
  (2nd-order — follow-up of the A1′ validation-epic follow-up → NICE-TO-HAVE per the
  step-17 order cap).*~~ — **SHIPPED** (PR for Slice 2, ADR-131): the WholeLife engine
  is now validated to omega against the SOA Illustrative Life Table `A_x`/`ä_x`/`P_x`
  at machine precision (`STATUTORY_DECK` cases, issue ages 35/40/65).

- **NICE-TO-HAVE — published held-reserve deck (VM-20 / CRVM worked example).** The
  ILT deck (ADR-131) validates the whole-life APV / net-premium columns; a published
  *reserve* worked example (a held statutory reserve factor for a specified policy)
  would validate the reserve path directly — closer to the "reproduce the cedant's
  held reserve" reinsurance use case. Not required to close the A1′ epic. *Source:
  ADR-131 Out of scope (2nd-order — follow-up of the A1′ validation-epic deck slice
  → NICE-TO-HAVE per the step-17 order cap).*

- **NICE-TO-HAVE — user-supplied reference decks for `polaris benchmark`.** The
  `benchmark` command (ADR-132) runs the fixed built-in reference catalogue only.
  Accepting a user-provided deck (e.g. a cedant's own worked reserve example, or a
  CSV of `case_id, expected, tolerance` scored against a specified projection)
  would let a diligence team validate the engine against *their* numbers, not just
  the vendored references — turning the pack from a shipped-in demonstration into a
  reusable acceptance harness. *Source: ADR-132 Out of scope (2nd-order — follow-up
  of the A1′ validation-epic surfacing slice → NICE-TO-HAVE per the step-17 order
  cap).*

- **NICE-TO-HAVE — OpenTelemetry trace spans for the API.** Slice 1 of A2′
  (ADR-133) ships structured JSON access logging + correlation IDs + request
  duration using the standard library only. ROADMAP 6.2 also lists optional
  OpenTelemetry trace spans (projection / treaty-application / profit-test steps)
  behind an optional-dependency extra — deeper, span-level tracing beyond the
  per-request access log. Deferred from Slice 1 to keep the core `api` extra
  dependency-free; not required by any shipped feature. *Source: ADR-133 Out of
  scope (1st-order — a follow-up of the originally-planned A2′ production-hardening
  epic; NICE-TO-HAVE as it affects observability depth, not correctness).*

- **NICE-TO-HAVE — reconcile the stale `tests/qa/golden_outputs/*.json` byte-format
  with the current CLI `-o` schema.** Pre-existing on main (not introduced by any
  recent PR): the committed golden snapshots use an older flat per-product schema
  (`"TERM": {…}` / `"WHOLE_LIFE": {…}`) while `polaris price -o` now emits nested
  `"cohorts": […]` / `"summary"` / `"rated_block"`. The QA guard
  (`tests/qa/test_*_golden.py`) parses and compares per-cohort metrics, so it is
  green regardless — but the routine's step-13 *literal* byte-diff of `-o` against
  the snapshot always shows a spurious difference, which repeatedly costs a session
  the effort of confirming it is not a real pricing change (happened this session,
  PR #130). Regenerate the snapshots to the current CLI schema (a docs/tooling
  change; verify pricing is unchanged first) OR point step-13 at the parsed QA guard
  instead of the raw file. Repo hygiene — no production-correctness impact.
  *Source: qa-on-pr review of PR #130 (1st-order — fresh discovery during review;
  repo hygiene, so NICE-TO-HAVE).*

- **IMPORTANT — shared rate-limit backend for multi-replica deployments.** The
  API rate limiter shipped in A2′ Slice 2 (ADR-134) is **in-process** (a per-client
  deque per replica). It is correct for a single replica, but behind a load
  balancer with N replicas the effective limit becomes ~N× the configured
  threshold (each replica counts independently), so a `POLARIS_API_RATE_LIMIT` no
  longer means what it says. A shared backend (Redis, or a sticky-session
  guarantee) is required before rate limiting is trustworthy on a multi-replica
  deployment — which A2′ Slice 3 (K8s/Helm) explicitly targets. Ship alongside or
  right after the deployment slice. *Source: ADR-134 Out of scope (1st-order — a
  follow-up of the originally-planned A2′ production-hardening epic; IMPORTANT
  because it is a silent correctness caveat on a shipped, deployed feature).*

- **NICE-TO-HAVE — OIDC/JWT authentication as an alternative to static API keys.**
  A2′ Slice 2 (ADR-134) ships static, env-configured `X-API-Key` / `Bearer`
  authentication — sufficient for first-deal quoting behind an ops gateway. A
  heavier OIDC/JWT integration (identity-provider-issued tokens, scopes,
  expiry/refresh) is a separate, larger epic; revive only if a buyer's security
  review requires federated identity rather than shared keys. *Source: ADR-134
  Out of scope (1st-order — a follow-up of the originally-planned A2′ epic;
  NICE-TO-HAVE as static keys cover the MVP path).*

- **NICE-TO-HAVE — per-route / per-key rate-limit tiers.** The shipped limiter
  (ADR-134) applies one global threshold per client host. Distinct limits per
  endpoint (e.g. a low cap on the expensive `/api/v1/uq` Monte-Carlo path, a
  higher cap on `/api/v1/price`) or per API key (per-tenant quotas) would let an
  operator shape load more precisely. *Source: ADR-134 Out of scope (1st-order —
  a follow-up of the originally-planned A2′ epic; NICE-TO-HAVE, load-shaping
  polish over the single-threshold baseline).*

- **NICE-TO-HAVE — API-key hardening: hashing, rotation, and secret-store
  integration.** A2′ Slice 2 (ADR-134) reads plaintext keys from
  `POLARIS_API_KEYS` and compares them directly. Production-grade credential
  handling — comparing against salted hashes, supporting overlapping keys for
  zero-downtime rotation, and sourcing keys from a secret store (Vault / K8s
  Secret) rather than a raw env var — would harden the auth surface. Pairs
  naturally with the Slice 3 K8s/secret plumbing. *Source: ADR-134 Out of scope
  (1st-order — a follow-up of the originally-planned A2′ epic; NICE-TO-HAVE, the
  plaintext-env baseline is acceptable for the MVP).*

- **IMPORTANT — proxy-aware client identification for rate limiting
  (`X-Forwarded-For` trust decision).** The A2′ Slice 2 rate limiter (ADR-134)
  keys on `request.client.host`. Behind a reverse proxy / ingress / load
  balancer, every request presents the *proxy's* IP, so per-client rate limiting
  silently collapses to a single global bucket — a common single-replica case,
  distinct from the already-harvested multi-replica backend item. Fixing it means
  deriving the client IP from `X-Forwarded-For` **only when the immediate peer is
  a trusted proxy** (an explicit trusted-proxy / trusted-hops config), because
  `X-Forwarded-For` is client-spoofable otherwise. This is a security trust-
  boundary decision that belongs with the Slice 3 K8s/ingress deployment surface
  (where the proxy topology is defined). *Source: PR #134 automated review [P2]
  (1st-order — fresh discovery during review of the originally-planned A2′ Slice 2;
  IMPORTANT because it silently defeats rate limiting behind any ingress).*
  **Update (2026-07-10): SHIPPED in A2′ Slice 3 (ADR-135)** — `client_ip()` derives
  the client from `X-Forwarded-For` only when the immediate peer is in
  `POLARIS_TRUSTED_PROXIES`. Draft PR open; strike through on merge (ledger-heal).

- **IMPORTANT — shared backend for multi-replica metrics aggregation.** A2′
  Slice 3 (ADR-135) ships an **in-process** `MetricsRegistry` feeding `/metrics`,
  the exact analogue of the already-harvested in-process rate limiter. Behind N
  replicas each pod exposes its own counters/histograms; a scrape hits one pod at
  a time, so dashboards must aggregate `sum by (...)` across per-pod series and a
  single pod restart resets its counters. This is inherent to the annotation-based
  per-pod scrape (Prometheus handles the aggregation) and is not a bug — but a
  buyer wanting exact global counts without Prometheus aggregation, or push-based
  metrics, would need a shared/remote-write backend. Pairs with the shared
  rate-limit backend item above (same replica-scaling root cause). *Source: ADR-135
  Out of scope (1st-order — follow-up of the originally-planned A2′ epic; IMPORTANT
  as a documented caveat on a shipped multi-replica-facing feature).*

- **NICE-TO-HAVE — richer instrumentation via `prometheus-client` / OpenTelemetry
  extra.** The shipped `/metrics` (ADR-135) is a hand-rolled, dependency-free text
  exposition covering request count + latency histogram. An optional
  `prometheus-client` (or OpenTelemetry) extra would add per-handler histograms,
  exemplars, and distributed traces without changing the default zero-new-dep
  install. Revive if a buyer's observability stack expects OTLP/traces. *Source:
  ADR-135 Out of scope (1st-order — follow-up of the A2′ epic; NICE-TO-HAVE, the
  dependency-free baseline covers the common ops need).*

- **NICE-TO-HAVE — Prometheus `ServiceMonitor`/`PodMonitor` CRD + CI manifest
  gating.** The Slice 3 manifests (ADR-135) use the annotation-based scrape
  convention (`prometheus.io/scrape`), which the Prometheus Operator ignores in
  favour of `ServiceMonitor`/`PodMonitor` CRDs. Shipping those CRDs (guarded so
  the chart installs with or without the Operator) plus CI `helm lint` /
  `kubeconform` validation and a packaged/versioned chart repo would make the
  deployment surface Operator-native and continuously validated. *Source: ADR-135
  Out of scope (1st-order — follow-up of the A2′ epic; NICE-TO-HAVE, annotation
  scrape covers the common non-Operator case).*

- **NICE-TO-HAVE — engine-level, entry-point-agnostic metrics.** The A2′ metrics
  surface (ADR-135) is transport-level: `MetricsMiddleware` counts/times **HTTP
  requests to the FastAPI app** only, so a pricing run through the **CLI**
  (`polaris price`) or the **Streamlit dashboard** — both of which call the engine
  in-process (`BaseProduct.project`, `ProfitTester.run`) with no HTTP hop —
  produces **zero** metrics even with the full Prometheus/Grafana stack running.
  Genuine engine observability (projection duration, policies priced, treaty
  applications) that is identical regardless of entry point would instrument the
  **engine core** rather than the transport: a small counter/timer around the hot
  paths that every caller (API, CLI, Streamlit) feeds, exposed through the same
  dependency-free registry. Distinct from the shared-backend and richer-HTTP-
  instrumentation follow-ups above (those still only see the API). NICE-TO-HAVE:
  operational observability, not first-deal-quoting correctness; but unlike the
  ADR-135 *multi-tenant design note* (recorded in DECISIONS.md, not promoted), this
  is actionable work a session could pick up. *Source: PR #135 review discussion
  (2026-07-10) — fresh discovery while demonstrating the Grafana stack; 1st-order
  follow-up of the A2′ metrics feature.*

### CI performance & smoke tracking (maintainer discussion 2026-07-12)

A coherent group from a maintainer design discussion after A2′ shipped. Items
**#2/#4/#5 form one capability** (a perf-tracking harness + committed history +
seed) that could be run as a small decomposed epic; **#1 is an independent quick
win**; **#3 bridges the "comment gap"** by reusing the pr-review routine. Explicit
dependency ordering is stated per item — do not start a dependent before its
prerequisite is on `main`. The **overriding design rule for the whole group**:
*deterministic / noise-normalized metrics may gate or alert; raw wall-time only
informs.* GitHub-hosted runners vary 2–3× run-to-run, so any gate on absolute
latency is an alert-fatigue generator — this is the single most important
constraint and a future session must not rebuild these as a naive wall-time log.

- **IMPORTANT — CI smoke-test job (real entry points).** CI today runs lint, the
  pytest matrix, a Docker build, and a one-line *import* smoke check — but nothing
  boots the real surfaces. Add a fast (<30s) smoke job that: boots `uvicorn` and
  curls `/health`, `/metrics`, and one real `/api/v1/price` (asserting 200 +
  shape); runs `polaris price` on `data/qa/golden_inforce.csv` (exit 0); and runs
  `polaris benchmark --pack closed-form` (exit 0). Deterministic, low-flake —
  **gate merges on it.** Independent of the perf items below. *Source: maintainer
  discussion 2026-07-12 (CI perf/smoke thread) — 1st-order; IMPORTANT as it catches
  "won't boot / entrypoint broken / endpoint 500s" that unit tests miss.*

- **IMPORTANT — performance harness with same-run head-vs-main baseline.** A
  `polaris perfbench` / `tests/perf/` harness (built on `pytest-benchmark`) that
  times the engine hot paths (`BaseProduct.project`, `ProfitTester.run`) on a
  **fixed synthetic block**, plus deterministic structural metrics (array
  allocations, engine-iteration counts, peak RSS, policies×months processed) and a
  fixed calibration microbench (e.g. a fixed-size NumPy matmul) as a runner-speed
  **normalizer**. In CI, benchmark the **PR head *and* `main` in the same job**
  (`git checkout main`, re-run) so the reported delta is a same-runner ratio —
  noise largely cancels, and **no persistent storage / gh-pages / token is
  required**. Emit `perf.json` `{head, base, delta, deterministic_metrics,
  calibration}` as a CI artifact; optionally a *hard* fail only on egregious
  regression (>50%) as a deterministic backstop. Measure engine throughput, **not**
  API latency (deterministic workload, commercially meaningful — "can it price a
  large inforce block fast enough"). Keep distinct from `polaris benchmark`, which
  is *correctness* validation (closed-form APVs), not performance. *Source:
  maintainer discussion 2026-07-12 — 1st-order follow-up of the observability
  theme; IMPORTANT; prerequisite for #3, #4, #5 below.*

- **NICE-TO-HAVE — pr-review routine posts the perf judgment comment (the
  "comment gap" bridge).** Rather than stand up `github-action-benchmark` +
  `gh-pages` purely to emit a PR comment, extend the existing pr-review Claude
  routine to read the perf harness's `perf.json` artifact and fold a perf verdict
  into the review it already posts: the head-vs-main delta **plus judgment a
  mechanical threshold cannot supply** — is the regression *expected* given the
  diff (e.g. a legitimately heavier calc) or *unexplained*; a root-cause hint from
  the diff; and noise-band suppression ("±11% is within this runner's variance —
  not flagging"). Keep the agent **advisory, not the hard gate** (agent output is
  non-deterministic; the CI backstop in #2 is the deterministic gate). This covers
  the **per-PR** comment; it does **not** see long-term creep (that is #4).
  **Depends on:** #2 (perf harness emitting `perf.json`). *Source: maintainer
  discussion 2026-07-12 — 2nd-order (follow-up of the perf harness) → NICE-TO-HAVE
  per the step-17 order cap; the bridge that makes perf tracking change behaviour
  without new infra.*

- **IMPORTANT — committed per-merge performance log (`perf/history.jsonl`) + creep
  detection.** The one thing the per-PR comment (#3) structurally cannot catch:
  slow multi-month creep (each PR +3%, all green, 40% over a quarter). Persist one
  append-only row **per merge to `main`** (keyed by merge SHA) under
  `perf/history.jsonl`, plus a short `perf/README.md` (or ADR) stating the metrics
  and the **interpretation rules the agent follows** (which metrics are
  deterministic vs. informational; the noise band; "flag only unexplained
  regression >X% on a deterministic metric"; "≥3 consecutive down-merges = creep
  alert"). This fits the repo's existing committed-ledger pattern
  (DECISIONS/PRODUCT_DIRECTION) and needs **no gh-pages/token** — strictly better
  for an audit-first project. **Design rule (non-negotiable):** the log is
  **deterministic-first** — lead with structural/normalized metrics (op counts,
  allocations, peak RSS, `engine_time / calibration_time`); keep raw wall-time as a
  secondary *informational* column with runner metadata (CPU, Python version).
  Deterministic metrics may alert; raw wall-time never gates — else the committed
  log becomes a noise generator with a git history. Wire the routines: **daily-dev
  appends** the row on merge (it already maintains ledgers); **pr-review reads** the
  log and adds creep context to its comment ("4th down-merge in a row"). **Depends
  on:** #2. *Source: maintainer discussion 2026-07-12 — 1st-order (core
  creep-tracking capability from the original discussion, not a derivative of the
  harness — hence IMPORTANT despite depending on #2); the creep tracker; upgrades
  the earlier "gh-pages CSV" idea to a committed, normalized, agent-read JSONL.*

- **NICE-TO-HAVE — seed `perf/history.jsonl` by backfilling meaningful commits
  (one-off).** So creep detection is useful on day one instead of accumulating from
  zero, backfill the log over ~10–15 engine-touching merges (select via `git log`
  on `src/polaris_re/products/`, `reinsurance/`, `analytics/profit_test.py` —
  substandard-rating slices, the YRT per-duration solver, portfolio aggregation,
  IFRS-17, the capital modules; **cap the count**). Run them **back-to-back on one
  machine** so the seeded history is *mutually comparable by construction* (a
  cleaner gold reference than scattered-runner points; the #2 normalizer aligns
  future points to it). Bonus: the archaeology may itself **surface a past
  regression** worth a finding. A bounded, one-off task an agent can drive once the
  harness (#2) and log format (#4) exist. **Depends on:** #2, #4. *Source:
  maintainer discussion 2026-07-12 — 2nd-order (supports the creep store) →
  NICE-TO-HAVE per the step-17 order cap; separable one-off effort.*

- **NICE-TO-HAVE — durable epic-grained history ledger (`CHANGELOG.md` /
  `docs/EPICS.md`).** The project has no durable, growing, **epic-grained** record
  of what shipped: a `CONTINUATION_*` flips `COMPLETE` and drops out of the
  routine's read scope, `ROADMAP.md` is forward-looking checkboxes (not a shipped
  narrative), and `PRODUCT_DIRECTION`'s "Recently Completed" is slice-grained and
  rolls over — so completed **epics effectively vanish from view**. The unit of
  *meaning* is the epic (each introduced a user-visible capability); the PR/slice
  is only the unit of *work* (a delivery increment gated by merge cadence). Add a
  **two-layer** history: **Layer 1** — an append-only epic ledger (Keep-a-Changelog
  style but sectioned by capability/epic, not raw version bumps) with one row per
  completed epic — `Epic | Capability delivered | Slices/PRs | ADRs | Shipped` —
  and **Layer 2** = the existing PR/ADR/session-log audit trail it *links into*
  (preserve PR traceability for the "which commit moved this number" case; don't
  drop slice-grain, just index it). Wire it: when the daily-dev routine flips a
  `CONTINUATION` to `COMPLETE`, it appends the row (it already maintains
  append-only ledgers — one more step, and it directly fixes the vanishing-epic
  hole). Doubles as the README "what's new" / diligence capability list — a real
  credibility asset for an open-source AXIS/Prophet alternative. **Guardrail:** this
  is Tier-B meta/process work; per the 2026-07-12 [P1] direction flag it must NOT
  precede constituting the next Tier-A epic (A3′) — fold it in alongside an epic's
  final slice, don't let it jump the queue. *Source: maintainer discussion
  2026-07-12 — 1st-order (fresh discovery: history should be epic-grained, not
  PR-grained); NICE-TO-HAVE process improvement.*

- **NICE-TO-HAVE — live / per-cohort currency conversion for ingestion.** A3'
  Slice 2 (ADR-137) added a single **static** `CurrencyConfig(code, rate)` applied
  to the monetary columns (`reporting = source × rate`). A multi-currency cedant
  book, or a valuation that must strike money at a period-end FX rate, needs a
  rate *source* (a lookup by currency, or an as-of FX curve) rather than one hard
  number — and possibly a per-cohort/per-currency column. Additive on top of the
  existing hook. Affects only multi-currency books, so NICE-TO-HAVE, not a
  common-path gate. *Source: ADR-137 Out of scope (1st-order).*

- **NICE-TO-HAVE — per-row provenance of the inferred date format.** A3' Slice 2
  coerces mixed date formats to canonical ISO and warns (at column granularity)
  when a column is ambiguous or has unparseable cells, but it does not record
  *which* source format each individual cell was read under. For a data steward
  auditing a coerced extract, a per-row/per-column "read as %m/%d/%Y" annotation
  (e.g. an optional diagnostics frame) would make the coercion fully traceable.
  Diagnostic nicety, not correctness. *Source: ADR-137 Out of scope (1st-order).*

- **NICE-TO-HAVE — value coercion for columns beyond the monetary/date families.**
  A3' Slice 2 coerces the monetary columns and `issue_date`/`valuation_date`.
  Other messy free-text columns (e.g. non-standard `sex`/`smoker_status` spellings
  not covered by an explicit `code_translations` map, whitespace/case in
  `product_type`) are still left to the existing `code_translations` mechanism. A
  light normaliser (trim/upper + fuzzy code match) could reduce reject rates on
  the roughest extracts. Separable, low-frequency; NICE-TO-HAVE. *Source: ADR-137
  Out of scope (1st-order).*

- **NICE-TO-HAVE — machine-readable ingestion report sidecar.** A3' Slice 3
  (ADR-138) surfaces the quarantine report to the console (`polaris ingest`) and
  in the JSON response (`/api/v1/ingest`), and writes the rejected *rows* to a
  CSV. It does not write the *report itself* (counts + per-reason breakdown +
  coercion warnings) as a machine-readable sidecar (e.g. `<output>.report.json`)
  for a pipeline to gate on without parsing console text. Additive on top of the
  existing report object. Ops/automation nicety, not a common-path gate.
  *Source: ADR-138 Out of scope (1st-order — follow-up of the A3' epic).*

- **NICE-TO-HAVE — rejects-file format option.** A3' Slice 3 writes the rejects
  frame as CSV (matching the clean output). A cedant returning a mixed-type or
  nested extract might prefer Parquet/JSON for the rejects file (to preserve
  dtypes or round-trip back into a correction workflow). A `--rejects-format`
  option is a small additive surface. Low-frequency; NICE-TO-HAVE. *Source:
  ADR-138 Out of scope (1st-order — follow-up of the A3' epic).*

- **NICE-TO-HAVE — streaming ingestion for out-of-core files.** The pipeline
  (ingest → coerce → partition) is eager: it materialises the full frame in
  memory. A cedant extract too large to hold in memory (multi-GB, tens of
  millions of rows) would need a streaming/lazy path (Polars `scan_csv` +
  chunked partition). No current deal needs it; revive when a book exceeds
  single-node memory. NICE-TO-HAVE (scale, not correctness). *Source: ADR-138
  Out of scope (1st-order — follow-up of the A3' epic).*

- **NICE-TO-HAVE — full negative-binomial (estimated α) likelihood on the
  by-amount experience basis.** A4' Slice 1 (ADR-139) handles by-amount
  overdispersion with quasi-Poisson Pearson-φ scaling (widens SEs by √φ). A full
  NB with an estimated dispersion `α` is the textbook alternative and gives a
  likelihood-based fit rather than a moment-scaled one. Quasi-Poisson is the
  robust, dependency-light Slice-1 choice; promote NB only if a validation deck
  shows the quasi-Poisson bands materially misstate uncertainty. Separable,
  low-frequency; NICE-TO-HAVE. *Source: ADR-139 Out of scope (1st-order —
  follow-up of the A4' epic).*

- **NICE-TO-HAVE — lapse experience through the same GAM machinery.** The
  A4' Experience-GAM module (ADR-139) is built for mortality; the additive
  A/E-over-static-base form generalizes directly to lapse (swap the base
  offset for a lapse assumption and the death measure for lapse counts). The
  epic's Slices 1–4 are mortality (incl. the tensor MI surface); lapse is an
  explicit epic-level out-of-scope. Revive as a self-contained follow-up once
  the mortality slices land. NICE-TO-HAVE. *Source: ADR-139 / PLAN_experience_gam
  "Explicitly Out of Scope" (1st-order — follow-up of the A4' epic).*

- **NICE-TO-HAVE — data-driven smoothness selection for the frequentist tensor MI
  surface.** A4' Slice 2a (ADR-140) fits `te(attained_age, calendar_year)` with
  **fixed-df** tensor-product regression B-splines (the robust, deterministic
  de-risking choice), so the surface's wiggliness is a hyperparameter, not
  data-estimated. On real (noisy) experience this can under- or over-smooth the
  improvement gradient and mis-scale the delta-method band. Slice 2b's Bayesian
  anisotropic HSGP largely **subsumes** this (ARD length-scales are the estimated
  smoothing parameters), so promote a standalone frequentist penalized-GAM
  (`GLMGam` / mgcv-style GCV) variant only if a validation deck shows the fixed-df
  bands materially misstate uncertainty *and* 2b's HSGP is not the chosen path.
  2nd-order (a follow-up of the 2a implementation choice) → NICE-TO-HAVE. *Source:
  ADR-140 Out of scope (2nd-order — follow-up of the A4' Slice-2a de-risking choice).*

- **IMPORTANT — confirm the ADR-141 backend deviation for the Bayesian MI surface
  (reduced-rank GP vs `bambi`/`pymc` HSGP).** A4' Slice 2b-surface **deviated from a
  locked PLAN decision**: the PLAN's `bambi`/`pymc` `inference_method="laplace"`
  backend is **defective in the installed versions** (`pymc` 6.1.0 / `bambi` 0.19.0 →
  `NullTypeGradError` in `pymc.tuning.scaling.find_hessian` when an HSGP term is
  combined with an `offset()` term; reproduced), and full NUTS is non-deterministic +
  too slow for CI. The surface therefore ships as a **pure-NumPy/SciPy reduced-rank
  GP** — the identical HSGP math in closed form (deterministic, core-only, no heavy
  dependency). This is strictly better for CI but reverses the locked backend choice,
  so the maintainer should confirm the direction **before the 2b-projection slice**,
  which is where a `pymc`-NUTS audit path for the posterior-predictive forward
  projection (if still wanted) would land. 1st-order (a discovery on the planned
  Slice-2b feature) → IMPORTANT (architecture/direction decision gating the next
  slice). *Source: ADR-141 human-review flag + DEV_SESSION_LOG_2026-07-22 DISCOVERY
  (step 11b) (1st-order).* **Update (2026-07-22, projection session):** Slice
  2b-projection (ADR-142) shipped the deterministic reduced-rank-GP projection and
  **deferred** the optional `pymc`-NUTS audit path pending this confirmation — so the
  epic advanced without resolving the gate, but the gate now blocks only the (optional)
  audit backend, not the epic. Confirm the direction so the audit path can either land
  or be dropped.

- **NICE-TO-HAVE — RW2 (linear-trend) forward-projection prior as an alternative to
  mean-reversion.** A4' Slice 2b-projection (ADR-142) ships the locked default —
  CMI/MP-style mean-reversion of `MI_x(y)` to a settable long-term rate (band narrows to
  the deterministic rate). The PLAN also offered **RW2 linear extrapolation** (extrapolate
  the last *rate of change*; the credible band fans out) as an alternative projection
  model. It is a genuinely different prior, not shipped here. Promote if a validation deck
  (or a maintainer preference) wants the fanning-band behaviour for long-horizon
  projections. 1st-order (a follow-up of the planned Slice-2b projection). *Source:
  ADR-142 Out of scope + PLAN_experience_gam Open Decisions (1st-order).*

- **NICE-TO-HAVE — per-age (or per-segment) long-term improvement rate in the MI
  projection.** `project_improvement` takes a single scalar `long_term_rate` (the CMI
  convention). Real MI projections sometimes taper to an age-varying long-term rate (e.g.
  higher at younger ages). Accept `long_term_rate: float | np.ndarray` (broadcast over
  ages) once a use-case needs it. 1st-order (a follow-up of the planned Slice-2b
  projection) → NICE-TO-HAVE. *Source: ADR-142 Out of scope (1st-order).*

- **NICE-TO-HAVE — empirical-Bayes length-scale / amplitude selection for the
  Bayesian MI surface.** A4' Slice 2b-surface (ADR-141) fixes the GP length-scales
  (in standardised coordinates) and `prior_scale` amplitude as smoothness dials — the
  Bayesian analogue of the frequentist fixed spline df. Data-driven selection by
  maximising the Laplace marginal likelihood (evidence) was prototyped but **deferred**
  because the Matérn spectral density underflows at large length-scales, singularising
  the Laplace Hessian — it added numerical fragility for no gain on the closed-form
  recovery tests. Promote a hardened evidence-maximising (or cross-validated)
  length-scale/amplitude selector only if a validation deck shows the fixed defaults
  materially misstate the credible-band width on real experience. 1st-order (a
  follow-up of the planned Slice-2b surface) → NICE-TO-HAVE. *Source: ADR-141 Out of
  scope (1st-order — follow-up of the A4' Slice-2b surface).*

- **NICE-TO-HAVE — select-and-ultimate (per-duration) CUSTOM improvement grids.**
  A4' Slice 2c (ADR-143) emits `ImprovementScale.CUSTOM` from an **attained-age ×
  calendar-year** `MI_x(y)` grid (`from_grid` / `to_mortality_improvement`). Real
  improvement can also vary by select duration (early-duration wear-off differs from
  ultimate). A per-duration custom grid (a third grid axis, or a select/ultimate pair)
  would let a CUSTOM scale carry duration structure the way the base table does.
  Improvement is duration-invariant in the current epic form (PLAN Design-Anchor-4), so
  this is design polish, not common-path correctness → NICE-TO-HAVE. 1st-order (a
  follow-up of the planned Slice-2c emission). *Source: ADR-143 Out of scope (1st-order).*

- **NICE-TO-HAVE — carry a credible/confidence band alongside a CUSTOM improvement
  scale.** A4' Slice 2c (ADR-143) emits a **point** `MI_x(y)` basis — the `MISurface`/
  `MIProjection` credible band is dropped, because `MortalityImprovement.apply_improvement`
  returns a single improved-rate vector. Propagating the band (e.g. a low/mid/high CUSTOM
  triple, or an optional band payload consumed by a stochastic pricing run) would let the
  MI uncertainty flow into scenario/UQ pricing rather than being discarded at the
  assumption boundary. Point basis is correct for deterministic pricing → NICE-TO-HAVE.
  1st-order (a follow-up of the planned Slice-2c emission). *Source: ADR-143 Out of scope
  (1st-order).*

- **NICE-TO-HAVE — age-varying group-specific MI *smoother* (full Pedersen GS/GI HGAM).**
  A4' Slice 3 (ADR-144) pools a per-segment **level** deviation and a per-segment **linear
  calendar-trend** deviation toward the global surface. The PLAN's fuller framing is a
  group-specific *smoother* — each segment gets its own shrunk `te(age, year)` deviation
  surface (age-varying segment improvement), not just a level + linear trend. This is
  modelling richness for books with genuinely different age-shaped segment improvement, not
  common-path first-deal correctness → NICE-TO-HAVE. 1st-order (a follow-up of the planned
  Slice-3 hierarchy). *Source: ADR-144 Out of scope (1st-order).*

- **NICE-TO-HAVE — exposure-weighted sum-to-zero centring for segment deviations.** A4'
  Slice 3 centres the segment random effect on the *unweighted* average segment (the
  standard GAM sum-to-zero constraint), so "the global" is the mean segment, not the
  exposure-weighted book. A weighted (Bühlmann-collective) centring would report each
  segment's deviation relative to the exposure-weighted population baseline — closer to
  actuarial credibility convention. The current convention is defensible and the deviations
  are correct up to the choice of origin → NICE-TO-HAVE. 1st-order (a follow-up of the
  Slice-3 identifiability choice). *Source: ADR-144 Out of scope (1st-order).*

- **NICE-TO-HAVE — per-segment forward MI projection + NB variance component (Slice 3).**
  `HierarchicalMISurfaceResult` exposes the in-window segment surface but not a per-segment
  `project_improvement` (the CMI/MP-style mean-reverting projection is only on the global
  `BayesianMISurfaceResult`); and the between-segment variance component is Gaussian
  (quasi-Poisson dispersion on the likelihood), not a full negative-binomial. Both are
  refinements for by-amount / thin-segment projection work, not common-path correctness →
  NICE-TO-HAVE. 1st-order (a follow-up of the planned Slice-3 hierarchy). *Source: ADR-144
  Out of scope (1st-order).*

- **NICE-TO-HAVE — sibling assumption kinds in the version store (lapse, base mortality).**
  `AssumptionVersionStore` (Slice 4b-2, ADR-147) versions the `mortality_improvement` kind
  only. The `kind` field already parameterises the store contract, but no lapse-improvement or
  base-mortality version is emitted or consumed anywhere — a `polaris experience lapse` /
  base-table versioning surface would exercise it. Scale/breadth, not common-path correctness
  → NICE-TO-HAVE. 1st-order (a follow-up of the planned Slice-4b-2 versioning). *Source:
  ADR-147 Out of scope (1st-order).*

- **NICE-TO-HAVE — retention / prune policy for the append-only version store.**
  The store (Slice 4b-2, ADR-147) is append-only by design with no `remove`/`prune` or
  retention surface, so a long-lived study cadence accumulates one file per re-fit forever.
  A retention policy (or an explicit `polaris experience prune --keep-latest`) is a housekeeping
  refinement — deliberately a human decision today, not routine → NICE-TO-HAVE. 1st-order
  (a follow-up of the planned Slice-4b-2 versioning). *Source: ADR-147 Out of scope (1st-order).*

- **IMPORTANT — Surface the experience-improvement selector on the dashboard + REST API.**
  Slice 4b-3 (ADR-148) wired a versioned `ImprovementScale.CUSTOM` basis into the pricing
  `--config` schema + a `--improvement-version` CLI flag, so a frozen experience basis can drive
  a `polaris price` run. The **dashboard Deal Pricing page** and the **REST API** `/price`
  request schema do not yet expose the selector, so a non-CLI user cannot pick a versioned basis
  (they get the no-improvement default). Deferred by the `yrt_rate_table_*` / ALM precedent (a
  config field joins the dashboard/API parity surfaces only when a slice consumes it), but it is
  the natural completion of making the feature reachable across product surfaces → IMPORTANT.
  1st-order (a follow-up of the planned Slice-4b-3 config wiring). *Source: ADR-148 Out of scope
  (1st-order).*

- **NICE-TO-HAVE — Config selector for a built-in improvement scale (Scale AA / MP-2020).**
  Slice 4b-3 (ADR-148) wires only the experience-derived **CUSTOM** path (a versioned basis from
  the assumption store) into `--config`/`AssumptionSet`. A run cannot yet select a **built-in**
  improvement scale (Scale AA, MP-2020, CPM-B) from config — the only way to apply one is to
  build the `AssumptionSet` in Python. A `mortality.improvement_scale` config field (enum → the
  built-in `ImprovementScale` values, with the scale parameters) would let a config apply a
  standard improvement basis without the version store. Orthogonal to the CUSTOM path and design
  polish, not common-path correctness → NICE-TO-HAVE. 1st-order (a follow-up of the planned
  Slice-4b-3 config wiring). *Source: ADR-148 Out of scope (1st-order).*

- **NICE-TO-HAVE — CLI surface for the experience data loaders (`polaris experience
  load-hmd` / `load-ilec`).** Slice 4c-1 (ADR-149) added `load_hmd()` / `load_ilec()` as a
  **library** API (`analytics/experience_loaders.py`) that maps HMD / SOA-ILEC files into the
  canonical grouped-cell contract. There is no CLI command to run them from the shell — a user
  scripting the pipeline calls the Python API directly. A thin `polaris experience load-hmd
  --deaths ... --exposures -o cells.csv` / `load-ilec --basis ... -o cells.csv` convenience
  wrapper would let the fit/improvement/save chain start from a raw cached file without a Python
  script. The loaders are consumed by the Slice-4c-2 validation deck as a library, so a CLI is
  not required by the epic → NICE-TO-HAVE. 1st-order (a follow-up of the planned Slice-4c-1
  loaders). *Source: ADR-149 Out of scope + DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c1
  Open Questions (1st-order).*

- **NICE-TO-HAVE — Built-in HMD authenticated-session (login/token) flow in `fetch_hmd`.**
  Slice 4c-1's `fetch_hmd` (ADR-149) takes an injectable `downloader` transport and its default
  urllib transport does a plain authenticated-URL GET; a full HMD account login/token flow
  (mortality.org requires an account) is left to the caller's environment. A built-in session
  handler (accept credentials, obtain the session cookie/token, then fetch) would make
  `fetch_hmd` self-contained for a fresh machine. Network + credential handling, never exercised
  in CI, and the injectable transport already unblocks any real fetch → NICE-TO-HAVE. 1st-order
  (a follow-up of the planned Slice-4c-1 loaders). *Source: ADR-149 Out of scope +
  DEV_SESSION_LOG_2026-07-23_experience_gam_slice4c1 Open Questions (1st-order).*

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
