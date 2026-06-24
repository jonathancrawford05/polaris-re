# Dev Session Log — 2026-06-24 (Config-driven golden-regression harness)

## Item Selected
- **Source:** `PRODUCT_DIRECTION_2026-06-18.md` — Promoted Follow-ups —
  *"Pipeline golden baselines for the `coins` and `policy_cession` configs
  (config-driven, drift-guarded)"* (IMPORTANT). Surfaced by the PR #103 automated
  review as a P2 finding and promoted at the maintainer's request.
- **Priority:** IMPORTANT
- **Title:** Config-driven golden-regression harness + baselines for `coins` and
  `policy_cession`.
- **Slice:** complete (SMALL, single session).
- **Branch:** `claude/awesome-bardeen-yqv16z` (environment-designated; reset to
  `origin/main` after PR #103 merged, per step 8 ENVIRONMENT OVERRIDE).

## Selection Rationale

Explicit maintainer request: after PR #103 merged, implement the "Option A" fix
for the golden-output gap surfaced in its review. This is gated fallback work
(Tier-B test-infra), selected by direct instruction rather than the autonomous
epic track. It is pure test infrastructure — no `src/polaris_re/` code — so it
carries zero engine golden-output risk.

## Verify Premise (step 7b)

Reproduced before writing code: `data/qa/` holds four configs
(`flat`, `yrt`, `coins`, `policy_cession`) but `tests/qa/golden_outputs/` held
only two byte-level baselines (`golden_flat.json`, `golden_yrt.json`). The
`coins`/`policy_cession` paths were covered only by `test_cli_golden.py`
smoke tests (exit-0, no value assertion). Confirmed the root cause: both
`generate_golden.py` and `test_pipeline_golden.py` hand-built `PipelineInputs`
for only `flat`/`yrt` and never read the JSON configs. The premise holds.

Also confirmed a latent inconsistency: the hand-built inputs used `LapseConfig()`
(default `DEFAULT_LAPSE_CURVE`) while the JSON configs carry an explicit
`duration_table`. They are identical today (`DEFAULT_LAPSE_CURVE` == the config
table), so the config-driven generator reproduces the existing baselines
byte-for-byte — but nothing had enforced that equivalence.

## What Was Done

Made the four `data/qa/golden_config_*.json` files the single source of truth for
both the baseline generator and the regression test (the "Option A" plan from the
PR #103 review):

- **`tests/qa/golden_runner.py` (new, pytest-free).** Enumerates the configs into
  `GoldenCase` records, loads each through the CLI's own parser
  (`_parse_config_to_pipeline_inputs`), and prices the shared golden inforce block
  via one `run_pricing` shared by the generator and the test — so a baseline can
  never disagree with what the test recomputes. Holds the baseline I/O + tolerance
  comparison previously duplicated across the two files.
- **`generate_golden.py`** rewritten to iterate discovered cases (skipping
  SOA-dependent configs under `--flat-only` or when the tables are absent).
- **`test_pipeline_golden.py`** rewritten: one regression parametrized over the
  discovered configs (per-config SOA gating by mortality source), a **drift guard**
  (`test_every_config_has_committed_baseline`) that fails loudly when a config has
  no committed baseline, a discovery sanity check, and the retained
  `TestGoldenSanity`.
- **`conftest.py`** slimmed to source shared constants/`has_soa_tables` from
  `golden_runner`, keep `requires_soa_tables` + the `golden_inforce` fixture, and
  drop the now-unused `golden_flat_inputs` / `golden_yrt_inputs` fixtures.
- **New baselines** committed: `golden_coins.json`, `golden_policy_cession.json`.

Recorded as ADR-105.

## Files Changed

- `tests/qa/golden_runner.py` — new shared, config-driven machinery.
- `tests/qa/generate_golden.py` — rewritten config-driven generator.
- `tests/qa/test_pipeline_golden.py` — parametrized regression + drift guard.
- `tests/qa/conftest.py` — slimmed; sources constants from `golden_runner`.
- `tests/qa/golden_outputs/golden_coins.json` — new baseline.
- `tests/qa/golden_outputs/golden_policy_cession.json` — new baseline.
- `docs/DECISIONS.md` — ADR-105.
- `docs/DEV_SESSION_LOG_2026-06-24_golden_config_driven.md` — this log.

## Tests Added

- `TestGoldenRegression::test_golden_regression[case]` — parametrized over the
  four discovered configs (`flat` runs always; `yrt`/`coins`/`policy_cession`
  gated on SOA tables). Replaces the hand-built `TestGoldenYRT` / `TestGoldenFlat`.
- `TestGoldenBaselineCoverage::test_every_config_has_committed_baseline` — the
  drift guard (runs without SOA tables).
- `TestGoldenBaselineCoverage::test_discovers_all_known_configs` — discovery
  sanity.

## Acceptance Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Generator + test enumerate `data/qa/golden_config_*.json` | ✅ | `discover_golden_cases()` |
| Configs loaded via the CLI's own parser | ✅ | `_parse_config_to_pipeline_inputs` |
| `golden_coins.json` + `golden_policy_cession.json` committed | ✅ | actuarially coherent |
| Regression parametrized over discovered set, per-config SOA gating | ✅ | flat always-on |
| Drift guard fails loudly on an unbaselined config | ✅ | verified with a temp config |
| `flat`/`yrt` baselines byte-identical | ✅ | git shows them unmodified |
| No `src/polaris_re/` change | ✅ | pure test infra |
| Own ADR | ✅ | ADR-105 |

## Open Questions / Follow-ups

- **Finer-grained cash-flow-vector golden.** The pipeline golden still pins
  per-cohort summary metrics (PV profits, margins, gross premiums/claims), not the
  full cash-flow vectors. A vector-level golden would catch offsetting errors that
  net to the same summary. NICE-TO-HAVE.
- **Goldens for unrepresented treaty types** (Modco, stop-loss) once configs
  exist — now a one-file change (add `golden_config_<name>.json`, generate, commit;
  the drift guard enforces the baseline). NICE-TO-HAVE.

## Parked Polish

None.

## Impact on Golden Baselines

`golden_flat.json` and `golden_yrt.json` are **byte-identical** to the committed
versions (the config-driven generator reproduces them exactly — git shows them
unmodified). Two **new** baselines added (`golden_coins.json`,
`golden_policy_cession.json`) for paths that previously had none. No existing
baseline regenerated/changed.

## Baseline Note

Branch reset to `origin/main` HEAD `bbf111a` (PR #103 merge). Full QA suite
(`pytest tests/qa/`): **76 passed** (was 72 — +2 regression cases, +2
coverage/discovery guards). Ruff format + check clean. The drift guard was
confirmed to fail on a temporary unbaselined config (then removed), and
`generate_golden.py --flat-only` confirmed to skip the three SOA configs while
leaving `golden_flat.json` byte-identical.

## Post-Review Addendum (PR #104 automated review)

The PR #104 review approved (zero P0, all 5 CI checks green) with three findings;
addressed in-PR:

- **[P1] Harvest** — promoted the two ADR-105 out-of-scope items to
  `PRODUCT_DIRECTION_2026-06-18` Promoted Follow-ups as **NICE-TO-HAVE**, tagged
  *2nd-order* (`Source: ADR-105 Out of scope`): the cash-flow-vector golden and
  Modco/stop-loss treaty goldens. (The original harvest only struck the source
  item; this closes that gap.)
- **[P2] mypy** — the 9 newly-introduced errors in `golden_runner.py` (from typing
  the metric dicts as `dict[str, object]`) cleared by a `MetricValue = float | int
  | None` / `GoldenResult` alias and a `# type: ignore[attr-defined]` on
  `treaty.apply` mirroring the CLI (`build_treaty` is annotated `object | None`).
  `mypy tests/qa/golden_runner.py` now clean. The `no-untyped-def` notes on
  `test_pipeline_golden.py` test methods are the universal pytest-method
  convention across the suite and outside CI's `mypy src/` scope — left as-is.
- **[P2] private CLI-helper import** — left as-is: binding the goldens to the
  exact parser the CLI uses is the point of the PR and is documented; a public
  accessor would touch `src/` and expand scope beyond test-infra.
