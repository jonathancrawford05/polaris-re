# Dev Session Log — 2026-06-11 — Canonical Valuation-Date Resolution (ADR-074)

**Feature:** Valuation-date handling — block-owned dates, no silent wall-clock fallback
**Branch:** `claude/nifty-fermi-ben105` (rides on PR #66)
**Slice:** single-session structural fix, explicitly authorized scope expansion
**Status at end of session:** DONE

---

## Why

Investigation of day-to-day price drift on the dashboard traced to the
effective `ProjectionConfig.valuation_date` being `date.today()` in
every path that didn't pin a date explicitly. Root cause: one line —
`DealConfig.valuation_date` declared with `default_factory=date.today`
— made every documented fallback to the inforce block's own date
unreachable dead code (in `build_pipeline`, in the dashboard's
`components/projection.build_projection_config`, and in the CLI
parser). Measured impact on the unmodified in-tree sample: +0.73%
total PV drift between a pinned 2026-01-01 valuation and a 2026-06-10
run date — a clock artifact, not an assumption change, and invisible
to the golden harness (which pins explicit dates).

A second structural defect compounded it: one projection consumed two
notions of policy seasoning — rate lookups used the date-derived
`*_vec_at(config.valuation_date)` arrays while the acquisition-cost
gate used the stored CSV scalar `duration_inforce_vec` — and nothing
validated the stored `attained_age` / `duration_inforce` columns
against the dates they summarise.

Full decision record: **ADR-074** in `docs/DECISIONS.md`.

## What was done

### Engine / pipeline

- **`core/pipeline.py`** — `DealConfig.valuation_date: date | None =
  None` (None = defer to the block). `build_projection_config` gains a
  terminal `date.today()` fallback documented as the generated-data
  path (no block access at that level). `build_pipeline`'s documented
  chain — explicit arg → deal config → block date → today — is now
  live. `load_inforce` runs the new consistency guard on both the CSV
  and list-of-dicts branches.
- **`core/inforce.py`** — new `InforceBlock.validate_date_consistency()`:
  per policy, stored `duration_inforce` must be within ±1 month of
  `months_between(issue_date, valuation_date)` and stored
  `attained_age` within ±1 year of `issue_age + derived_months // 12`;
  raises `PolarisValidationError` listing offenders. Hooked into
  `from_csv` (covers the dashboard upload path too).
- **`cli.py`** — both config-schema branches now pass `None` through
  when `valuation_date` is omitted instead of stamping `date.today()`.
- **`products/term_life.py` / `products/whole_life.py`** — the
  acquisition-cost new-business mask now uses
  `duration_inforce_vec_at(config.valuation_date) == 0`, the same
  seasoning notion as the rate lookups. Behaviour-identical for
  date-consistent data.
- **Dashboard** — zero code changes: the existing
  `deal_config → block → today` resolution branches (previously
  unreachable) simply became live. The Assumptions-page date widget now
  genuinely defaults to the block's date, as its help text always
  claimed. The API was already aligned (it builds `ProjectionConfig`
  from `policies[0].valuation_date`).

### Sample data

- **`data/inputs/portfolio_sample/`** — DEAL_C / DEAL_D dates unified
  from day-15 to day-01 (2026-01-15 → 2026-01-01; seasoned issue dates
  shifted identically so durations stay exact). Under block-date
  resolution the previous mixed dates would have made `align="strict"`
  raise; with uniform dates the sample is an honest, reproducible
  strict-mode demo (total PV 675,558.62 on any run day). YAML header
  comment + README updated.
- **`data/inputs/demo.csv`** — one row had stored `duration_inforce=0`
  against dates implying 3 months; corrected to 3.
- **`data/inputs/portfolio_staggered_sample/`** — data unchanged
  (explicit YAML dates win at resolution step 2); README's description
  of the original sample's resolution updated.

### Tests

- `tests/test_core/test_valuation_date.py` — `test_default_is_today` →
  `test_default_is_none`; new `TestBuildPipelineResolution` (block date
  wins when deal unset — the QA-gap regression; deal beats block;
  explicit arg beats both) and `TestValidateDateConsistency` (pass /
  duration mismatch / age mismatch / ±1-month tolerance / dicts-path
  guard). 29 tests.
- `tests/qa/test_dashboard_flows.py` — new
  `test_pricing_resolves_block_valuation_date`: deal_config starts with
  `valuation_date=None`; clicking Run Pricing produces a
  `gross_result` whose `valuation_date` equals the injected block's
  2026-04-01, never the run date.
- `tests/test_dashboard/test_portfolio_loader.py` — new
  `test_sample_resolves_block_valuation_date` pinning the original
  sample's resolved dates to {2026-01-01}.
- **Fixture repairs** (the guard found genuinely inconsistent and
  clock-dependent fixtures): `test_analytics/test_cli_portfolio.py`
  and `test_cli_config.py` and `test_cli_streamlit_parity.py` paired
  `issue_date=2020/2025-01-01` with `valuation_date=date.today()` and
  `duration_inforce=0` — all moved to fixed, internally consistent
  dates (also de-flaking them); `test_utils/test_ingestion.py` R003
  had `attained_age=55` where the dates imply 53 — corrected.

## Quality gate

```bash
uv run ruff format src/ tests/    # clean
uv run ruff check src/ tests/ --fix
uv run pytest tests/ -m "not slow"
# 1250 passed, 4 skipped, 4 pre-existing failures (missing SOA tables)
uv run polaris portfolio run --config data/inputs/portfolio_sample/portfolio.yaml
# strict mode, total PV $675,559 — reproducible across run days
uv run polaris portfolio run \
    --config data/inputs/portfolio_staggered_sample/portfolio.yaml --align calendar
# offsets 0/0/2/2, origin 2026-01-01 — unchanged
uv run polaris price --inforce data/qa/golden_inforce.csv \
    --config data/qa/golden_config_flat.json -o /tmp/dev_check.json
# golden config pins 2026-04-01; output unchanged
```

## Key decisions (see ADR-074 for full rationale)

1. **One resolution order everywhere**, aligned on the strictest
   already-shipped semantics (the API's): explicit → deal config →
   block date → today, with today reachable only for generated data
   with no block — per the product decision that the wall clock is the
   one honest date when there is no uploaded data.
2. **Guard at ingestion, not on the `Policy` model** — direct
   construction stays permissive for programmatic use; CSV/dict/upload
   ingestion is where inconsistent user data enters.
3. **Tolerances ±1 month / ±1 year** absorb partial-month counting and
   ANB/ALB rounding without letting real drift through (the synthetic
   generator's 30.44-day back-calculation stays within them).
4. **Unify the original sample rather than pin YAML dates** — keeps the
   CSVs the single source of truth for the strict-mode demo and avoids
   a config-vs-CSV disagreement in the bundled data.

## Out of scope / follow-ups (tracked in ADR-074)

- API-path consistency guard (needs an HTTP error-mapping decision).
- ANB vs ALB attained-age convention cleanup.
- Dedicated as-of re-valuation workflow.
