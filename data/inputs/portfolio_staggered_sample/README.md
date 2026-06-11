# Staggered-date portfolio sample inputs

A clone of [`data/inputs/portfolio_sample/`](../portfolio_sample/README.md)
with per-deal valuation dates staggered two calendar months apart, built
to exercise the calendar-aligned aggregator (ADR-061 / ADR-062) and the
dashboard portfolio page's `align="calendar"` UI path end to end.

## How it differs from `portfolio_sample/`

| Sample | Deal valuation dates | `align="strict"` | `align="calendar"` |
|--------|----------------------|------------------|--------------------|
| `portfolio_sample/` (canonical strict-mode demo) | Not set in the YAML — every deal resolves to its CSVs' shared `2026-01-01` block date (ADR-074) | Works — aggregate PV equals the sum of per-deal PVs | Works, but every `grid_offset` is 0, so the calendar path is indistinguishable from strict |
| `portfolio_staggered_sample/` (this directory) | Explicit in each `deal:` block — DEAL_A / DEAL_B at `2026-01-01`, DEAL_C / DEAL_D at `2026-03-01` | Errors by design (mixed valuation dates) | Works — DEAL_C / DEAL_D land at `grid_offset = 2` |

The grid placement is driven by each deal's resolved
`ProjectionConfig.valuation_date` — an explicit YAML `deal.valuation_date`
when set, else the block's own validated date (ADR-074). This sample sets
explicit YAML dates and shifts the per-policy CSV dates to match, so both
sources agree. All dates fall on the same day-of-month (the 1st) because
calendar-mode aggregation requires monthly grids that line up exactly.

What the staggered dates surface:

- The dashboard's grid-origin banner ("Grid origin: 2026-01-01") and the
  "Grid Offset (months)" column in the per-deal breakdown table, which
  are suppressed whenever every offset is 0.
- The discount-factor effect that makes calendar mode actuarially
  distinct from a naive sum of PVs: DEAL_C and DEAL_D each contribute
  `v**2 x (standalone PV)` to the aggregate because their cash flows
  start two months after the grid origin (ADR-061).

## Files

```
portfolio.yaml                                   <- top-level config (explicit valuation_date per deal)
deal_a_cedant_north_term_yrt.csv                 <- 25 policies, valuation 2026-01-01 (byte-identical to portfolio_sample)
deal_b_cedant_north_wl_coinsurance.csv           <- 25 policies, valuation 2026-01-01 (byte-identical to portfolio_sample)
deal_c_cedant_south_term_coinsurance.csv         <- 25 policies, all dates shifted +2 months to 2026-03-01
deal_d_cedant_south_ul_modco.csv                 <- 25 policies (UL), all dates shifted +2 months to 2026-03-01
```

100 policies total. DEAL_C / DEAL_D seasoned policies' issue dates are
shifted by the same two months so every `duration_inforce` is unchanged.
Composition (cedants, products, treaties, cessions, rated lives) is
identical to `portfolio_sample/` — see its README for the rationale.

## Running

From the repo root:

```bash
# Calendar-aligned (ADR-061) — DEAL_C / DEAL_D report grid_offset = 2
uv run polaris portfolio run \
    --config data/inputs/portfolio_staggered_sample/portfolio.yaml \
    --align calendar \
    -o /tmp/portfolio_staggered_calendar.json

# Strict mode errors by design (mixed valuation dates):
# use data/inputs/portfolio_sample/ for the strict-mode demo.
```

Or upload `portfolio.yaml` + the four CSVs to the dashboard's Portfolio
page and pick **calendar** in the Alignment mode selectbox.
