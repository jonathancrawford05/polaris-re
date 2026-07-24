# Continuation: Mortality-Improvement (MI) Dashboard Page

**Source:** PRODUCT_DIRECTION_2026-07-24.md — Recommended Next Sprint **S2**
(maintainer-directed 2026-07-24). Backing spec: `docs/PLAN_mi_dashboard.md`.
**Status:** IN PROGRESS
**Total slices:** 2 (+1 optional API slice)
**Estimated total scope:** ~2 dev-days (MEDIUM)

## Overall Goal

Add a **Mortality Improvement** page to the Streamlit dashboard that makes the
shipped experience-GAM / mortality-improvement capability (A4' epic,
ADR-139..154) usable by a non-CLI pricing actuary. Two capabilities, both from
carried-forward follow-ups: (a) the **MI diagnostics view** (NICE-TO-HAVE
experience-GAM #89 / ADR-153) and (b) the **versioned improvement-scale
selector wired into Deal Pricing** (IMPORTANT #12 / ADR-148, the dashboard
half). It is a presentation layer only — no pricing/engine behaviour changes,
goldens byte-identical.

## Decomposition

### Slice 1: MI diagnostics page (the #89 half)
- **Status:** DONE
- **Branch:** `claude/loving-gauss-q4swra` (environment-designated)
- **PR:** #159 (draft)
- **What was done:** New `views/experience_improvement.py` with
  `page_experience_improvement()`, registered in `app.py` (sidebar radio +
  dispatch). The user loads a built-in sample grouped-cell experience (default,
  so the flow is exercisable without a file upload) or uploads a
  canonical-contract CSV, then sees four diagnostics rendered via the shipped
  `[viz]` helpers: fitted effects (`plot_effects` from
  `ExperienceGAM.all_effects()`), the `MI_x(y)` surface slices (`plot_mi_surface`
  from `TensorMIModel.improvement_surface()`), a band-width identification
  heatmap (`plot_mi_surface_bandwidth`), and — behind a "run Bayesian (slow)"
  toggle — the forward projection fan (`plot_mi_projection` from
  `BayesianTensorMIModel.project_improvement()`). A "download MI surface grid"
  button mirrors the CLI `--grid-out`. ADR-157.
- **Key decisions:**
  - Frequentist `TensorMIModel` is the interactive default (sub-second on the
    sample); the Bayesian reduced-rank-GP is gated behind an explicit toggle
    (0.43s on the sample, but kept opt-in per PLAN §5).
  - Slice 1 requires a pre-built `q_base` column on the CSV; the standard-table
    attach path (`--table` in the CLI) is deferred (harvested follow-up).
  - The GLM fits are cached in `st.session_state` keyed on a content+config
    signature that excludes `confidence_level` (folded in post-review at
    maintainer request), so a confidence-slider move re-derives bands without
    refitting. The saved-version load path remains Slice 2.
  - Built-in sample pins all ages/years as literals (ADR-074).
  - View excluded from coverage (ADR-032 `dashboard/*` omit) but covered by
    `AppTest` flows + pure-function helper unit tests in
    `tests/qa/test_dashboard_flows.py`.

### Slice 2: Versioned improvement-scale selector wired into pricing (the #12 dashboard half)
- **Status:** DONE
- **Branch:** `claude/loving-gauss-ovcw39` (environment-designated)
- **PR:** #160 (draft)
- **What was done:** The Deal Pricing page (`views/pricing.py`) now renders a
  `_improvement_version_selector` that lists the CUSTOM bases in the
  assumption-version store
  (`AssumptionVersionStore(default_store_root()).list_versions(kind="mortality_improvement")`)
  and lets the actuary pick one. The chosen `version_id` is mirrored onto the
  session `deal_config`; the frozen scale is loaded via the same
  `load_improvement_version` path the CLI `--improvement-version` flag uses and
  applied to the run as `assumption_set.model_copy(update={"improvement": <loaded>})`
  (frozen Pydantic model). `DealConfig` gains an
  `improvement_version_id: str | None = None` field round-tripped in `to_dict()`.
  An empty/absent store degrades to a "none available" caption. ADR-158.
- **Key decisions:**
  - The selector lives on the **Deal Pricing** page (not the Assumptions page) —
    #12 is specifically the Deal Pricing selector, and co-locating the override
    with the Run button keeps the "this run uses a frozen basis" decision next to
    pricing and echoed on `deal_config`.
  - The override reuses the CLI loader + the same `AssumptionSet.improvement`
    field the engine consumes, so a dashboard-selected basis prices
    **byte-identically** to the CLI path (regression-guarded at `atol=0`).
  - `DealConfig.improvement_version_id` is the **dashboard parity surface only**;
    the CLI/config path keeps `improvement_version_id` on `MortalityConfig`
    (`inputs.mortality`), where `build_assumption_set` reads it. Default `None`
    keeps every existing config byte-identical.
  - Tests seed a CUSTOM version into a `tmp_path` store and redirect
    `POLARIS_DATA_DIR`; the `AppTest` fixture uses flat mortality so no SOA
    table files are needed under the redirected root.
- **Acceptance criteria:**
  - A dashboard-selected versioned basis drives the priced run identically to the
    CLI `--improvement-version` / `mortality.improvement_version_id` path. ✅
    (byte-identical gross death claims + `pv_profits` at `atol=0`)
  - `DealConfig.to_dict()` round-trips the field; goldens untouched. ✅

### Slice 3 (optional / may split to its own PR): REST-API improvement selector (the #12 API half)
- **Status:** NEXT
- **Depends on:** Slice 2 merged
- **Scope:** Add `improvement_version` to the `/api/v1/price` `PriceRequest`
  schema, thread through the same pipeline path, echo on the response. If not
  co-shipped, IMPORTANT #12 stays open in PRODUCT_DIRECTION noting only the
  dashboard half shipped.

## Context for Next Session

- The pricing state precedent is `components/state.py` + `views/pricing.py`; the
  CLI threads the version via `load_improvement_version` (`cli.py`, `pipeline.py`)
  and the `--improvement-version` flag / `mortality.improvement_version_id`
  config key. Mirror that exactly in Slice 2.
- `AssumptionVersionStore.list_versions(kind=...)` lives in
  `assumptions/version_store.py`. On a fresh checkout the store may be empty —
  guard the selector so an empty store degrades to "no versioned basis available"
  rather than erroring.
- `AppTest` cannot drive `st.file_uploader`; keep any new testable path reachable
  via the sample/session-state route (Slice 1's sample-data default is the
  precedent).
- The `DealConfig.to_dict()` change in Slice 2 is a controlled contract touch —
  default `None`, backward-compatible, flag it in the PR description per the
  routine guardrails.

## Open Questions (for human)

- **Page vs tab placement** (PLAN §5 default: a dedicated sidebar page — shipped
  in Slice 1). Reconsider only if the maintainer prefers a tab on the existing
  Assumptions or Experience Study page.
- **Always-Bayesian default** (PLAN §5 default: frequentist, Bayesian behind a
  toggle). The Bayesian fit is only ~0.4s on the sample; the maintainer may want
  it as the default on small blocks. Left as the locked frequentist default for
  Slice 1.

When all slices are DONE, update Status to COMPLETE — and run HARVEST
FOLLOW-UPS first (routine step 17) so the deferred table-attach path and any
surviving refinement items reach the latest PRODUCT_DIRECTION.
