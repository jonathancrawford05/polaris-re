# Portfolio sample inputs

A four-deal, three-cedant, three-product, three-treaty sample portfolio
used by the Streamlit dashboard portfolio page and by anyone exercising
`polaris portfolio run` end to end. The composition is deliberately
heterogeneous so the multi-basis concentration helpers (ADR-069 /
ADR-073), the calendar-aligned aggregator (ADR-061), and the rated-block
panel (ADR-068) all have something to surface.

## Files

```
portfolio.yaml                                   ← top-level config
deal_a_cedant_north_term_yrt.csv                 ← 25 policies
deal_b_cedant_north_wl_coinsurance.csv           ← 25 policies
deal_c_cedant_south_term_coinsurance.csv         ← 25 policies
deal_d_cedant_south_ul_modco.csv                 ← 25 policies (UL — adds account_value / credited_rate)
```

100 policies total.

## Composition

| Deal    | Cedant       | Product        | Treaty        | Cession | YRT loading | Notes |
|---------|--------------|----------------|---------------|---------|-------------|-------|
| DEAL_A  | CedantNorth  | TERM           | YRT           | 80%     | 10%         | 20-yr + 30-yr terms, ages 30–55, 3 rated lives, 3 seasoned policies |
| DEAL_B  | CedantNorth  | WHOLE_LIFE     | Coinsurance   | 50%     | n/a         | Ages 40–65, 2 rated lives, 5 seasoned policies |
| DEAL_C  | CedantSouth  | TERM           | Coinsurance   | 60%     | n/a         | 10-yr + 20-yr terms, mostly new-issue, all standard |
| DEAL_D  | CedantWest   | UNIVERSAL_LIFE | Modco         | 70%     | n/a         | Ages 35–60, 2 rated lives, 4 seasoned policies, includes `account_value` + `credited_rate` |

## Why this composition

- **3 cedants** (North, South, West) — cedant-dimension concentration
  HHI is non-degenerate.
- **3 product types** — product-dimension has three labels.
- **3 treaty types** (YRT + Coinsurance + Modco) — treaty-dimension has
  three labels.
- **YRT only on DEAL_A** — the `ceded_nar_peak` basis differs from
  `ceded_face`; the multi-basis concentration view is visibly different
  across the three bases.
- **Rated lives** — 7 rated policies across the book (3 in A, 2 in B,
  2 in D) so the rated-block panel (ADR-068) renders non-empty when any
  of these CSVs is run through `polaris price`.
- **Calendar offsets** — DEAL_A / DEAL_B have `valuation_date =
  2026-01-01`; DEAL_C / DEAL_D have `2026-01-15`. Running with
  `--align calendar` (ADR-061) produces a non-zero `grid_offset` for
  the two later deals.

## Running

From the repo root:

```bash
# Strict (same-month) alignment, default
uv run polaris portfolio run \
    --config data/inputs/portfolio_sample/portfolio.yaml \
    -o /tmp/portfolio_sample.json

# Calendar-aligned (ADR-061)
uv run polaris portfolio run \
    --config data/inputs/portfolio_sample/portfolio.yaml \
    --align calendar \
    -o /tmp/portfolio_sample_calendar.json

# All three concentration bases (ADR-070)
uv run polaris portfolio run \
    --config data/inputs/portfolio_sample/portfolio.yaml \
    --concentration-basis all
```

Or upload `portfolio.yaml` + the four CSVs to the dashboard's Portfolio
page (Slice 2+).
