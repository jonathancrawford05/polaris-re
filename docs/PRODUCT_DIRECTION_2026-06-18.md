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
items the 2026-05-23 file flagged: (1) the engine carries a single net-
premium reserve basis with a horizon-edge approximation; reproducing the
cedant's stated reserves (GAAP, STAT VM-20, CRVM, deficiency reserves) is not
yet possible, and (2) IFRS 17 only produces point-in-time recognition figures,
not the period-to-period movement table required for a real filing. Both are
documented in the queue with ~10 dev-day scope estimates and explicitly scoped
to a dedicated Phase 5.3+ roadmap entry rather than mid-sprint pickup.

## Feature Gap Analysis

### BLOCKERs

None remain. Every BLOCKER identified in 2026-04-19 has shipped, and the
2026-05-23 review confirmed no new BLOCKER had been promoted from the harvested
follow-up queue.

### IMPORTANT

Both surviving IMPORTANT items are unchanged from 2026-05-23 — neither was
selected by daily-dev in the intervening 26 days, per their explicit scope
caveat:

- **Reserve basis matching (cedant reproduction).** `core/projection.py`
  supports one reserve basis. Reinsurers must reproduce the cedant's reserves
  (GAAP, STAT VM-20, CRVM, CIA net premium, or deficiency reserves) to give a
  consistent profit-test. **Scope:** ~10 dev-days for a `ReserveBasis` enum +
  two concrete alternatives (CRVM, VM-20 PBR simplified). **Affected:**
  `core/projection.py`, all four products, new test suite vs published cedant
  filings. *Carried from PRODUCT_DIRECTION_2026-05-23 → 2026-04-19.*

- **IFRS 17 period-to-period movement table.** Current implementation gives
  BEL / RA / CSM at initial recognition only (`analytics/ifrs17.py`).
  Production filers need the opening → experience adjustments → unwinding →
  closing movement table by annual cohort with locked-in discount rates
  (Roadmap Phase 5.3). **Scope:** ~10 dev-days. **Affected:**
  `analytics/ifrs17.py`. *Carried from PRODUCT_DIRECTION_2026-05-23 →
  2026-04-19.*

Today's run surfaces a **third item that would warrant IMPORTANT status if
it begins to show up in cedant submissions**, currently filed
NICE-TO-HAVE in the queue but worth re-reading:

- **WL prospective terminal reserve.** The horizon-edge artefact (WL reserve
  declining from $7.18M at yr 10 to $56k at yr 20) is an ARCHITECTURE-
  documented limitation rather than a regression, but a deal-committee actuary
  would query why a $25M WL block carries near-zero reserves at projection
  end. ARCHITECTURE.md §4 already foreshadows "Phase 3 will extend to true
  prospective reserves" — this remains open. Flagged for visibility this
  nightly. *No promotion proposed — keep on the carried-forward NICE-TO-HAVE
  queue (Reserve-basis matching covers the user need; this is a sub-item).*

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

With no BLOCKERs, no IMPORTANT item that fits a single session, and a
well-stocked NICE-TO-HAVE queue, the recommendation for the next several
daily-dev sessions remains "pick the cleanest small win on the freshest
thread". Concretely, ranked by `(commercial impact) × (1 / effort)`:

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

The two IMPORTANT items (Reserve-basis matching, IFRS 17 movement table)
remain out of scope for single-session pickup; they should be slated as a
dedicated Phase 5.3+ roadmap entry with explicit scope, golden plan, and
review milestones.

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
work just shipped.

The two enduring IMPORTANT items (Reserve-basis matching and IFRS 17
period-to-period movement table) have not been touched in 56 days and remain
correctly out of scope for single-session pickup. They are the canonical
candidates for a dedicated Phase 5.3+ roadmap entry. If the maintainer wants
to compress the gap-to-real-deal timeline, scoping a focused 2-week roadmap
slot for one of these — most likely Reserve-basis matching, since it
gates cedant reproduction in the deal-committee workflow — is the highest-
impact direction shift available from here.

The actuarial reasonability profile is unchanged from prior nightlies — flat
YRT rate vs rising mortality on the WL block, WL prospective terminal
reserve at horizon edge — both pre-existing structural notes covered in
ARCHITECTURE.md and the per-duration solver / IFRS 17 movement table queue.
No new reasonability flag emerged from today's run.
