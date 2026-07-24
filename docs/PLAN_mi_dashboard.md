# Plan — Mortality-Improvement (MI) page on the Streamlit dashboard

> **Audience.** A new Claude Code session that will build this feature end to
> end. Read this document fully before writing code, then read the linked
> CLAUDE.md (dashboard/coverage conventions) / ARCHITECTURE.md §7 (experience-GAM)
> / `docs/DECISIONS.md` ADR-148 (versioned improvement selector) + ADR-153
> (`[viz]` diagnostic plots) sections it points at. Update the CONTINUATION +
> DECISIONS + DEV_SESSION_LOG at the end of every slice — this plan is the
> read-only spec, not the running log.
>
> **Status.** ⏳ IN PROGRESS — **Slice 1 shipped** (diagnostics page, ADR-157);
> Slice 2 (versioned selector into pricing) is NEXT. Queued as **Next Sprint S2**
> (maintainer-directed 2026-07-24) in `PRODUCT_DIRECTION_2026-07-24.md` — the
> second item, after S1 (`pipeline.py` relocation) and ahead of the Tier-B quick
> wins. Running log: `docs/CONTINUATION_mi_dashboard.md`.
>
> **Provenance.** Folds two carried-forward follow-ups: IMPORTANT #12 (ADR-148 —
> surface the versioned improvement selector on the dashboard) and NICE-TO-HAVE
> experience-GAM #89 (ADR-153 — wire the experience-GAM diagnostics into the
> dashboard). Maintainer directive 2026-07-24.

---

## 1. Goal

Add a **Mortality Improvement** page to the Streamlit dashboard
(`src/polaris_re/dashboard/views/`) that makes the shipped experience-GAM /
mortality-improvement capability usable by a non-CLI pricing actuary. The
analytical engine is already shipped (A4′ epic, ADR-139…154); this is the
presentation layer. Two capabilities, both from carried-forward follow-ups:

**(a) Versioned improvement-scale selector (IMPORTANT #12 / ADR-148 — dashboard
half).** The CLI already drives a priced run from a versioned
`ImprovementScale.CUSTOM` basis via `mortality.improvement_version_id` (config)
or the `--improvement-version` flag; the pipeline reads it through
`load_improvement_version` (`cli.py:353`, `pipeline.py`). A dashboard user
currently **cannot** pick a versioned basis — the Deal Pricing page has no
control. Surface it: list versions from `AssumptionVersionStore.list_versions()`
(`assumptions/version_store.py`), let the user select one, thread the chosen
`improvement_version_id` into the pricing `DealConfig`, and round-trip it
through `DealConfig.to_dict()`.

**(b) MI diagnostics view (experience-GAM #89 / ADR-153).** Render the
experience-GAM diagnostics interactively by reusing the shipped `[viz]`
helpers in `src/polaris_re/viz/experience_plots.py` — `plot_effects`,
`plot_mi_surface`, `plot_mi_surface_bandwidth`, `plot_mi_projection` — and the
public `all_effects()` / `MISurfaceResult` grid (`--grid-out`) surfaces from
`analytics/experience_gam.py`. The user fits (or loads a cached fit of) an MI
surface from an experience CSV and sees: per-feature effect shapes, the
`MI_x(y)` surface slices, and the posterior-predictive projection fan.

The page should:
1. Sit behind a new sidebar entry ("Mortality Improvement") in
   `dashboard/app.py`, delegating to `page_experience_improvement()` in a new
   `views/experience_improvement.py` (mirrors the `page_experience_study` /
   `views/experience_study.py` precedent).
2. Let the user **either** upload a grouped-cell experience CSV and fit an MI
   surface, **or** load a saved version from the store — cache the result in
   `st.session_state` (the `experience_study` / `portfolio` pages set the
   precedent).
3. Render the **diagnostics** section (effects / MI-surface / projection) via
   the `[viz]` helpers.
4. Render the **versioned-basis** section: list store versions, select one,
   and expose a "use this basis in Deal Pricing" handoff (write the selected
   `improvement_version_id` into the shared pricing state consumed by
   `views/pricing.py`).
5. Be **excluded from coverage** (matching the `dashboard/app.py` precedent,
   ADR-032) but tested via `streamlit.testing.v1.AppTest` in
   `tests/qa/test_dashboard_flows.py` so widget-wiring regressions are caught.

## 2. Why this work, and what it does NOT do

**Why.** A4′ built the ML-native differentiator end to end, but its only
interactive surface today is the CLI. A dashboard user (the deal-committee
persona the dashboard targets) can neither drive a priced run from a versioned
experience basis nor inspect the fitted MI surface. This page closes the last
surfacing gap for the epic's headline capability.

**What it does NOT do.**
- Does **not** change any pricing/engine behaviour — it is a presentation layer
  over shipped analytics + the shipped pipeline improvement-version path.
  Goldens are byte-identical.
- Does **not** ship the **REST-API half** of IMPORTANT #12 (the `/price` schema
  `improvement_version` field). That stays a carried-forward IMPORTANT item; it
  may follow as a separate small PR (note it in the CONTINUATION). Keep this
  epic dashboard-only unless the API half is trivial to co-ship.
- Does **not** add a new fitting mode or model — it reuses `ExperienceGAM` /
  `TensorMIModel` / `BayesianTensorMIModel` and the existing `[viz]` helpers as
  is. If the Bayesian fit is too slow for an interactive page, default the page
  to the frequentist `TensorMIModel` and gate the Bayesian path behind an
  explicit "run Bayesian (slow)" button.
- Does **not** touch core data contracts.

## 3. Decomposition (MEDIUM — 2 slices, +1 optional)

### Slice 1 — MI diagnostics page (the #89 half)
- New `views/experience_improvement.py` with `page_experience_improvement()`;
  register it in `app.py` (sidebar radio + dispatch).
- Upload a grouped-cell experience CSV → fit `TensorMIModel` (frequentist
  default) → cache in `st.session_state`.
- Render effects / MI-surface / projection via `viz/experience_plots.py`
  (`plot_effects`, `plot_mi_surface`, `plot_mi_projection`). Use `st.pyplot` on
  the returned figures; gate a "run Bayesian (slow)" toggle.
- Tests: `tests/qa/test_dashboard_flows.py` `AppTest` flow (upload fixture →
  assert the diagnostics render without exception, key widgets present). Reuse
  or add a small pinned-date grouped-cell CSV fixture (ADR-074 — no wall clock).
  Exclude the view from coverage per ADR-032.
- **Acceptance:** page renders the three diagnostics from a fixture CSV; AppTest
  green; goldens untouched; ruff clean.

### Slice 2 — Versioned improvement-scale selector wired into pricing (the #12 dashboard half)
- On the MI page (or a shared component), list `AssumptionVersionStore.list_versions(kind="mortality_improvement")`;
  `st.selectbox` the version id; store the choice in the shared pricing state.
- In `views/pricing.py` (+ `components/state.py`), consume the selected
  `improvement_version_id` into the `DealConfig` the pricing run builds, exactly
  as the CLI threads `--improvement-version` / `mortality.improvement_version_id`.
- Ensure `DealConfig.to_dict()` round-trips the field (add if missing — a
  controlled, backward-compatible addition; default `None` preserves behaviour).
- Tests: AppTest flow selecting a version and asserting the priced run consumes
  it (e.g. the echoed config carries the version id); a `to_dict()` round-trip
  unit test.
- **Acceptance:** a dashboard-selected versioned basis drives the priced run
  identically to the CLI path; round-trip test green; goldens untouched.

### Slice 3 (optional / may split to its own PR) — REST-API improvement selector (the #12 API half)
- Add `improvement_version` to the `/api/v1/price` `PriceRequest` schema and
  thread it through the same pipeline path; echo it on the response.
- Tests: API test asserting the field is accepted and consumed.
- If not co-shipped, leave IMPORTANT #12 open in `PRODUCT_DIRECTION` with a note
  that only the dashboard half shipped.

## 4. Guardrails (from the routine + CLAUDE.md)

- Dashboard views are **excluded from coverage** (ADR-032) but MUST be tested
  via `streamlit.testing.v1.AppTest` in `tests/qa/test_dashboard_flows.py`.
- All fixtures pin dates (ADR-074) — no `date.today()` / wall-clock dependence.
- If any test-referenced CSV is added under `data/`, update the Dockerfile COPY
  and `.dockerignore` allowlist **in the same PR** (the #61/#66 trap).
- `DealConfig.to_dict()` change (Slice 2) is a controlled contract touch —
  default `None`, backward-compatible, flagged in the PR description.
- Byte-identical goldens (presentation layer only); no baseline regeneration.
- Draft PR only; never self-merge.

## 5. Open Decisions (locked defaults; revivable by maintainer)

- **Frequentist default for the interactive fit** (default, locked): the page
  fits `TensorMIModel` by default; the Bayesian surface is behind an explicit
  slow-path button. Revive an always-Bayesian default only if fit latency is
  acceptable on the target block sizes.
- **Dashboard-only scope** (default): the API half of #12 (Slice 3) is optional
  and may split to its own PR — do not let it block the dashboard surfacing.
- **Page vs. tab placement** (default: a dedicated "Mortality Improvement"
  sidebar page): reconsider only if the maintainer prefers it as a tab on the
  existing Assumptions or Experience Study page.
