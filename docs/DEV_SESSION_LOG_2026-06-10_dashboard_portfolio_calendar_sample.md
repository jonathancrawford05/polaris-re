# Dev Session Log — 2026-06-10 — Staggered-Date Sample Portfolio (Calendar-Mode UI Path)

**Feature:** Calendar-aligned portfolio UX polish — non-zero grid offsets in the sample
**Branch:** `claude/nifty-fermi-ben105`
**Slice:** single-session NICE-TO-HAVE (PRODUCT_DIRECTION_2026-05-23)
**Status at end of session:** DONE — ready for draft PR

---

## What was done

Added a second in-tree sample portfolio,
`data/inputs/portfolio_staggered_sample/`, whose per-deal valuation
dates are staggered two calendar months apart so the dashboard
portfolio page's `align="calendar"` path (ADR-061 / ADR-062) lights up
end to end: the grid-origin banner fires, the "Grid Offset (months)"
column appears, and the calendar-mode aggregate PV visibly differs
from a naive sum of per-deal PVs. No engine code changed — this is
sample data + tests + Docker plumbing only.

### Investigation finding (why a second sample, and why YAML dates)

The backlog entry assumed moving the CSVs' `valuation_date` column
would produce non-zero offsets. Verified that this is wrong on two
counts:

1. **The grid is driven by the YAML, not the CSVs.** The deal-level
   `ProjectionConfig.valuation_date` consumed by
   `Portfolio._grid_offsets` comes from the `deal:` block of the
   portfolio config (`DealConfig.valuation_date`, defaulting to
   `date.today()` — see `build_pipeline` resolution order in
   `core/pipeline.py`). The per-policy `valuation_date` column never
   reaches the grid logic. The original sample's YAML sets no
   deal-level dates, so all four deals share `date.today()` — which is
   why every Slice 2 / Slice 3 test passes under `align="strict"`
   despite the CSVs' mixed 2026-01-01 / 2026-01-15 dates, and why
   `align="calendar"` runs but yields all-zero offsets (banner
   suppressed, column hidden).
2. **Mutating the original sample would break the strict-mode tests.**
   Adding mixed deal-level dates to `portfolio_sample/portfolio.yaml`
   makes `align="strict"` raise `PolarisValidationError`, and every
   `TestPortfolioPage*` fixture builds its result with
   `align="strict"`. Hence the second-sample approach: the original
   stays the canonical strict-mode demo, byte-identical.

### Files added

**`data/inputs/portfolio_staggered_sample/`** (6 files)

- `portfolio.yaml` — same 4-deal composition as `portfolio_sample/`
  but with explicit `valuation_date:` in each `deal:` block:
  `2026-01-01` for DEAL_A / DEAL_B, `2026-03-01` for DEAL_C / DEAL_D.
  Same day-of-month (the calendar-mode constraint in
  `_grid_offsets`), two months apart, so `align="calendar"` accepts
  the portfolio and produces offsets `0 / 0 / 2 / 2`. `name:` and
  `inforce_csv:` paths updated; header comment documents the intent.
- `deal_a_*.csv` / `deal_b_*.csv` — byte-identical copies from
  `portfolio_sample/` (valuation 2026-01-01).
- `deal_c_*.csv` / `deal_d_*.csv` — copies with ALL dates shifted +2
  months (2026-01-15 → 2026-03-01; seasoned policies' issue dates
  2025-01-15 → 2025-03-01 and 2022-01-15 → 2022-03-01) so every
  `duration_inforce` is unchanged.
- `README.md` — distinguishes the two samples (original = strict-mode
  demo; staggered = calendar-mode `grid_offset` demo), documents the
  YAML-vs-CSV date distinction and the `v**2 x (standalone PV)`
  discount-factor effect (ADR-061).

### Files modified

**`tests/qa/test_dashboard_flows.py`** — new
`TestPortfolioPageCalendarAlignment` (3 tests), same session-state
injection pattern as `TestPortfolioPage`:

- `test_grid_origin_banner_renders` — the `st.info` grid-origin banner
  fires and names the earliest valuation date (2026-01-01).
- `test_per_deal_table_has_grid_offset_column` — the per-deal
  breakdown dataframe gains the "Grid Offset (months)" column.
- `test_deal_c_and_d_offset_by_two_months` — offsets are exactly
  `{DEAL_A: 0, DEAL_B: 0, DEAL_C: 2, DEAL_D: 2}`.

**`tests/test_dashboard/test_portfolio_loader.py`** — new
`TestLoadStaggeredSample` (3 tests) so the sample stays exercised even
without AppTest:

- `test_roundtrips_staggered_portfolio` — loads via
  `load_portfolio_from_config_path`, 4 deals, hurdle 0.10.
- `test_calendar_run_produces_two_month_offsets` — offsets `0/0/2/2`,
  grid origin 2026-01-01.
- `test_strict_run_rejects_mixed_valuation_dates` — `align="strict"`
  raises `PolarisValidationError` (by design).

**`Dockerfile`** — added
`COPY data/inputs/portfolio_staggered_sample/ ...` next to the
existing `portfolio_sample/` COPY (runtime stage runs the test suite,
which now needs the new fixture — same class of fix PR #61 made).

**`.dockerignore`** — allow-through negations
(`!data/inputs/portfolio_staggered_sample/` + `/**`) mirroring the
`portfolio_sample/` entries.

### Files NOT modified

- `src/polaris_re/analytics/portfolio.py` — guardrail; sample-data
  only.
- `data/inputs/portfolio_sample/` — guardrail; byte-identical
  (verified via `git status`). Note its README's "Calendar offsets"
  paragraph claims the 2026-01-15 CSV dates produce non-zero
  offsets — stale per the investigation finding above; left untouched
  per the guardrail and flagged as a follow-up below.
- `data/qa/golden_*.json` — guardrail; untouched.

## What the change achieves (demo path)

A demo viewer can now: (1) flip `align="calendar"` in the UI without
an error, (2) see "Grid origin: 2026-01-01" in the banner, (3) read
`grid_offset = 2` for DEAL_C / DEAL_D in the per-deal table, and
(4) observe calendar-mode `total_pv_profits` ($668,710) differ from
the naive sum of standalone per-deal PVs ($675,559) — DEAL_C / DEAL_D
each contribute `v**2 x (standalone PV)` to the aggregate (ADR-061).

## Quality gate

```bash
uv run ruff format src/ tests/        # 145 files left unchanged
uv run ruff check src/ tests/ --fix   # All checks passed
uv run pytest tests/qa/test_dashboard_flows.py -v
# 46 passed (43 existing + 3 new) in 14.48s
uv run pytest tests/ -m "not slow"
# 1241 passed, 4 skipped, 4 pre-existing failures (missing SOA table
# CSVs under data/mortality_tables/; same baseline as previous sessions)
uv run polaris portfolio run \
    --config data/inputs/portfolio_staggered_sample/portfolio.yaml \
    --align calendar
# Grid Origin 2026-01-01; per-deal breakdown reports Offset 0/0/2/2;
# Total PV Profits $668,710.
uv run polaris price --inforce data/qa/golden_inforce.csv \
    --config data/qa/golden_config_flat.json -o /tmp/dev_check.json
# Successful run; output shape unchanged.
```

## Key decisions

1. **Second sample, not a mutation.** Every Slice 2 / Slice 3 fixture
   pins the strict-mode aggregate of `portfolio_sample/`; a mutation
   would have broken them all (verified, not assumed — see
   investigation finding).
2. **Dates staggered via the YAML `deal:` blocks.** The CSV
   `valuation_date` column does not reach `_grid_offsets`; the CSVs
   are shifted anyway so the per-policy data is internally consistent
   with the deal-level dates.
3. **DEAL_C / DEAL_D moved to 2026-03-01, not 2026-02-15.** The
   PRODUCT_DIRECTION entry suggested 2026-02-15, but calendar mode
   requires a common day-of-month across ALL deals (days 1 and 15
   would be rejected). First-of-month two months out gives clean
   `grid_offset = 2` against DEAL_A / DEAL_B's 2026-01-01.
4. **Seasoned-policy issue dates shifted by the same +2 months** so
   `duration_inforce` (12 for C024/C025, 48 for D022–D025) stays
   exact.
5. **Docker plumbing fixed in this PR** rather than as a follow-up:
   the runtime image runs the test suite, and the new loader tests
   reference the new directory — without the COPY +
   `.dockerignore` negations, `make docker-test` would fail (the
   PR #61 lesson applied proactively).

## Follow-ups

- `data/inputs/portfolio_sample/README.md` "Calendar offsets" bullet
  is stale (claims the CSV dates drive non-zero offsets; they don't,
  and offsets are 0 on that sample). Untouched this session per the
  "never modify portfolio_sample/" guardrail — fold the correction
  into the next session that's allowed to touch that directory.
- After this PR merges, strike out "Calendar-aligned portfolio UX
  polish — non-zero grid offsets in the sample" in the NICE-TO-HAVE
  section of `docs/PRODUCT_DIRECTION_2026-05-23.md` (post-merge
  crossout session, same pattern as PR #64).

## Next session

Remaining candidates from `PRODUCT_DIRECTION_2026-05-23.md` matching
the daily-dev cadence:

- `polaris portfolio` Excel writer rows for the `capital` block
  (ADR-060 Out of scope: "CLI / API / Excel surfacing of the new
  `capital` block").
- Post-merge crossout for this session's entry (can ride along with
  the next feature PR).
