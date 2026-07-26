# Plan — Premium-Deficiency Reserve (PDR) on the Streamlit dashboard

> **Audience.** A future Claude Code session (or human) that will surface the
> shipped `PremiumDeficiencyTester` (ADR-162, PR #164) on the Deal Pricing page.
> Read this document fully before writing code, then read the CLAUDE.md
> dashboard/coverage conventions, ADR-162 (`docs/DECISIONS.md`), and ADR-083
> (the `PremiumSufficiencyTester` this composes on). This plan is the read-only
> spec, not the running log.
>
> **Status.** 🔲 PLANNED — not started. The analytical engine is shipped and
> tested (`analytics/premium_deficiency.py`, 18 tests); this is a
> presentation-layer follow-up only.
>
> **Provenance.** NICE-TO-HAVE follow-up harvested from ADR-162 "Out of scope"
> into `docs/PRODUCT_DIRECTION_2026-07-24.md` ("Surface the premium-deficiency
> reserve on the CLI / dashboard / REST API"). 1st-order. Module-first, then
> surfaced — mirrors how `PremiumSufficiencyTester` itself was built (ADR-083).

---

## 1. Goal

Surface the premium-deficiency reserve (PDR) beside the existing premium-
sufficiency tiles on the Deal Pricing page, so a non-CLI actuary can read the
loss-recognition **reserve floor** — not just the signed sufficiency margin —
for both the cedant (NET) and reinsurer (ceded) views. It is a pure presentation
layer over the shipped `PremiumDeficiencyTester`: no pricing/engine behaviour
changes, goldens byte-identical.

## 2. The one decision that makes this worth doing — net against the held reserve

`PremiumDeficiencyTester` defaults `existing_reserve=0.0` (the "bare test"). At
that default,

    PDR = max(0, GPV) = max(0, -sufficiency_margin)

which is just a **sign-flipped, floored copy of the "Sufficiency Margin" tile
already displayed** (`_render_sufficiency_tiles`, `pricing.py:562`). Rendering it
that way adds no information.

The surfacing is only worth doing if PDR is computed against the block's
**valuation-date held reserve**, turning it into a genuinely distinct answer —
*"the reserve you hold is short by $X"* rather than *"the premium margin is
−$X"*. The held reserve is already in hand at the sufficiency call site:

- Cedant (NET) view → `net.reserve_balance[0]`
- Reinsurer (ceded) view → `ceded.reserve_balance[0]`

`reserve_balance` is the per-basis aggregate reserve at the first projection
point; `[0]` is the scalar valuation-date held reserve. This is a legitimate
point-in-time input requiring **no** per-survivor normalization — that
complication only arises for the per-period roll-forward (see §5).

**Acceptance-defining requirement:** the dashboard PDR MUST be computed with
`existing_reserve = <basis>.reserve_balance[0]`, not the 0.0 default. A PDR tile
at `existing_reserve=0` is redundant with the sufficiency margin and should not
ship.

## 3. Where it plugs in (exact call sites, `dashboard/views/pricing.py`)

1. **`CohortPricingData` dataclass (`pricing.py:67-68`)** — add two optional
   fields alongside the sufficiency ones:
   `premium_deficiency: PremiumDeficiencyResult | None = None` and
   `reinsurer_premium_deficiency: PremiumDeficiencyResult | None = None`.
2. **Compute (next to `pricing.py:490-498`)** — where `PremiumSufficiencyTester`
   is already run on `net` (and `ceded`) at `config.discount_rate`, add:
   `PremiumDeficiencyTester(net, config.discount_rate, existing_reserve=float(net.reserve_balance[0]))`
   for the cedant, and the analogous `ceded` call for the reinsurer view (guard
   the reinsurer branch exactly as the sufficiency block already does). Store on
   the returned `CohortPricingData` (next to `pricing.py:530-531`).
3. **Render** — add `_render_deficiency_tiles(result, view)` next to
   `_render_sufficiency_tiles` (`pricing.py:537`), and call it immediately after
   the sufficiency tiles: cedant after `pricing.py:785`, reinsurer after
   `pricing.py:881`.

Tiles to show: **Reserve Floor** (`reserve_floor`), **Premium-Deficiency
Reserve** (`premium_deficiency_reserve`), **Held Reserve** (`existing_reserve`,
for context), and a verdict (`✅ No deficiency` / `❌ Deficiency` from
`is_deficient`). Format with `f"${...:,.0f}"` like the sufficiency tiles.

## 4. Framing / labelling (reviewer-flagged)

The automated review of PR #164 flagged the FAS 60 / ASC 944 loss-recognition
framing for human attention. On a **pricing** screen a prominent reserve figure
must not be mistaken for a booked statutory/GAAP reserve. Label the block
explicitly as a **loss-recognition screening floor at the valuation date** (a
short `st.caption` under the tiles), and keep it visually subordinate to the
pricing headline. It is a screening diagnostic, not a booked reserve.

## 5. Out of scope for this surfacing

- **Per-period roll-forward** of the reserve floor across the projection — that
  is the separate **IMPORTANT** harvested follow-up (ADR-162), and it carries the
  aggregate-vs-per-survivor normalization design question. This surfacing is
  point-in-time (valuation date) only.
- **CLI and REST-API** surfaces of PDR — sibling NICE-TO-HAVE follow-ups; do
  them as their own slices if desired (the CLI already has the sufficiency
  plumbing — `cli.py` `_render_sufficiency_table` / `_sufficiency_to_dict` — to
  mirror).
- **Wiring the floor back into the projected `reserve_balance`** so downstream
  profit/IRR reflect the strengthened reserve — a controlled contract change, not
  additive; tracked separately (ADR-162 Out of scope).

## 6. Tests / conventions

- Dashboard views are **excluded from coverage** (ADR-032) — verify via an
  `AppTest` flow in `tests/qa/test_dashboard_flows.py` (a deficient sample block
  shows the deficiency verdict + a non-zero PDR; a sufficient block shows
  `No deficiency` / PDR 0).
- Pin all dates explicitly (ADR-074) — no `date.today()`.
- Goldens byte-identical: this touches only the dashboard presentation layer;
  `polaris price` on the golden configs must be unchanged, QA golden guards green.
- Ship as its own PR on a fresh branch from `main` (do not expand an approved PR).
