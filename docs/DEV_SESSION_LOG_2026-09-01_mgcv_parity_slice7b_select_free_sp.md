# Session log — 2026-09-01 — Slice 7b: extending the free-`sp` search to `select=TRUE`'s 7-block structure

**Routine:** `docs/ROUTINE_MGCV_PARITY.md`
**Slice:** 7b — `docs/PLAN_mgcv_parity_engine.md`. Not selectable by the routine's
own "next unchecked slice" rule at session start: slice 7 (ADR-217) closed
with its own closing line explicitly naming this gap and naming its
registration as "a maintainer decision, not a routine's". The maintainer
authorized proceeding in this session's own conversation; this session
registered the slice (ADR-209 decision 1) and then worked it, both in the
same session per the maintainer's direction.
**PR:** `claude/intelligent-hamilton-oq6sgh` (this session's designated
branch).
**ADR:** ADR-218.

## Setup

- `uv sync --all-extras` — clean (4 new packages: `statsmodels`, `patsy`,
  `openpyxl`, `et-xmlfile`).
- Installed the local scratch oracle (tier 1): `apt-get install -y -qq
  r-base-core r-cran-mgcv r-cran-jsonlite`. Versions recorded:
  **R 4.3.3 (2024-02-29) / mgcv 1.9-1** — matches the routine's expected apt
  versions, no drift to flag.
- Read `docs/ROUTINE_MGCV_PARITY.md` in full, `docs/VERIFICATION_STANDARD.md`,
  `docs/PLAN_mgcv_parity_engine.md` (slice 7's own "what remains" note),
  `docs/CONTINUATION_mgcv_parity_engine.md`'s status block through
  ADR-217/PR #222, `docs/CONFORMANCE_LEDGER.md`, CLAUDE.md, and DECISIONS.md
  ADR-193, ADR-209, ADR-211/212/213 (the N=4 multistart/finite-diff-step
  history this slice's registered prediction is built on), ADR-217.

## `make test` baseline

`uv run pytest tests/ -m "not slow" -q` (R installed) — **3532 passed, 6
failed, 22 skipped, 126 deselected.** Five failures are the same
pre-existing environment gap every recent parity session records
(`FileNotFoundError: Mortality table CSV not found` — mortality tables are
generated, not committed, CLAUDE.md §11), unrelated to this epic. The sixth
(`test_gam_model_conformance.py::test_the_r_probe_runs_end_to_end`) failed
only inside the full-suite run and passed cleanly in isolation
(`pytest tests/test_analytics/test_gam_model_conformance.py::test_the_r_probe_runs_end_to_end`
→ 1 passed) — a one-off flake consistent with contention between concurrent
R subprocess invocations under the full suite's own parallelism, not a
regression; not re-run a second time per the routine's own "at most once"
flake-confirmation rule since the isolated pass already confirms it. Proceed,
per the routine's own baseline rule.

## Gap Before

`fit_polaris_gam`'s free-`sp` search had never been exercised on the 7-block
structure `ModelSpec(select=True)` produces — ADR-217 verified the null-space
penalty (Stage A) and a fixed-`sp` Stage-B fit only. No comparison against
`mgcv`'s own free-`sp` `select=TRUE` selection existed; the claim sentence
could not be filled in (no probe, no Python comparator).

**Tier and digest:** N/A — no prior measurement exists to state a "before"
number for.

## Registered prediction (written before any measurement, PLAN slice 7b)

Slices 5c/5d/5e found the N=4 (non-`select`) structure's free-`sp` search
needed a finite-difference-step fix (ADR-212) and best-of-9 multi-start
(ADR-213) before it reliably reached `mgcv`'s own selected point. Prediction:
single-start underperforms multistart at least as much here, and the
null-space blocks (never exercised under free selection before) are the more
likely place for a genuinely new disagreement — not the three
already-verified existing blocks.

## Hypotheses tried

### Pass 1 — single-start (the module's own default, no code change)

**Hypothesis:** `fit_polaris_gam`'s default single bounds-centre start
disagrees with `mgcv`'s own free-`sp` `select=TRUE` selection.

**Built:** `scripts/gam_select_multiterm_free_sp_probe.R` (same shared recipe
as `gam_select_multiterm_probe.R`/`gam_multiterm_free_sp_probe.R`,
`select=TRUE`, `method="REML"`, seed 20260902) and
`gam_select_free_sp_conformance.py` (`SELECT_FREE_SP_MODEL_CLAIM`,
`fit_select_free_sp_case`, `compare_select_free_sp_case`).

**Measured (tier 1):** `max_abs_log10_sp_diff=5.132`,
`max_abs_eta_diff=0.4456`, `edf_total_diff=+2.4216` (Python `edf_total=16.98`
vs `mgcv=14.56`), `agrees=False`, `converged=True`. Worst block: `ti(...)`'s
own null-space block (Python `5.02` vs `mgcv` `-0.11`).

**Verdict:** Prediction's first half CONFIRMED — worse in absolute terms
than any N=4 reading this epic has taken. Second half (null-space blocks are
the culprit) provisionally supported by this pass alone.

### Pass 2 — `multistart=True` (one change: best-of-9)

**Hypothesis:** best-of-9 multistart (ADR-213's already-verified building
block) closes most of the gap, the way it did at N=4.

**Built:** `fit_polaris_gam` gained an opt-in `multistart: bool = False,
n_starts: int = 9` parameter, threading to
`select_lambdas_continuous_multistart` when `True` (every other caller's
default behaviour unchanged) — chosen over reimplementing the
assembly/scoring a second time inside the conformance module, which the
first draft did and was refactored out once this measurement showed the
parameter was worth having centrally.

**Measured (tier 1):** `max_abs_log10_sp_diff=1.475` (3.5x tighter),
`max_abs_eta_diff=0.00268` (166x tighter), `edf_total_diff=-0.111` (22x
tighter), `max_abs_term_edf_diff=0.103`, `agrees=False` (still misses the
`1e-2` `log10(sp)` gate). Per block: the three null-space blocks now agree to
`<0.01`; the residual moved to two of the three terms' own EXISTING blocks
(the reference age smooth's and the by-term's), both driven toward large
`lambda`.

**Verdict:** Large, real movement on `eta`/`edf`. **Refutes** the
prediction's second half — the null-space blocks were not the genuinely new
disagreement once the optimiser is fixed; the residual is on already-verified
existing blocks instead, the same class ADR-212 characterised at N=4.

### Pass 3 — warm-start diagnostic (TRANSPORT, never a parity claim)

**Hypothesis:** is the surviving residual optimiser convergence (hypothesis
1, ADR-211/212's own N=4 finding) or genuine multi-modality (hypothesis 2)?
Same discriminator ADR-211/212 used: start the search AT `mgcv`'s own
selection and see whether it stays there and scores better than the blind
multistart result.

**Built:** `scripts/gam_select_free_sp_warmstart_diagnostic.py`, no
production code change.

**Measured (tier 1):** warm-started fit stays at `mgcv`'s point (`max abs
diff=0.00148`) at score `523.6453` — `0.0141` BETTER than multistart's own
best (`523.6594`), `converged=False` (near-zero gradient, consistent with a
weakly-identified surface at that point).

**Verdict:** DECISIVE for hypothesis 1. `mgcv`'s own point is a reachable,
better-scoring optimum of our own criterion than nine blind starts reach —
the same mechanism ADR-211/212 found and fixed at N=4, recurring at a larger,
harder scale rather than a new defect. Three passes, three informative
results — stopped here per the routine's own "three passes" guardrail, with
a characterised finding rather than a fourth guess.

## Gap After

| metric | single-start | multistart(9) |
|---|---:|---:|
| `max_abs_log10_sp_diff` | 5.132 | 1.475 |
| `max_abs_eta_diff` | 0.4456 | 0.00268 |
| `edf_total_diff` | +2.4216 | -0.111 |
| `max_abs_term_edf_diff` | 2.4853 | 0.1027 |
| `agrees` (1e-2 gate on `log10(sp)`) | False | False |

**Not closed on the primary registered metric** (`log10(sp)`, `1e-2` gate) —
reported honestly, per Anchor 8 (never widen a tolerance to call a gap
closed). **Closed to the same order every other Stage-B measurement in this
epic reaches** on `eta` (166x tighter) and `edf_total` (22x tighter), with
the residual explained rather than merely observed (warm-start diagnostic).

## Provenance (ADR-193)

| quantity | left producer | right producer | provenance |
|---|---|---|---|
| `eta` | `gam_model.fit_polaris_gam` (single-start or `multistart=True`) at its own selected `log_lambda` | `mgcv gam(select=TRUE, method='REML')` free-`sp` fit, `predict(m, type='link')` | INDEPENDENT |
| `log10(sp)` per block | `gam_reml_optimize.select_lambdas_continuous`(`_multistart`)'s own `log_lambda` (7 blocks) | `mgcv`'s own `log10(m$sp)` at its free-`sp` `select=TRUE` selection | INDEPENDENT |
| `edf_total` | `PolarisGAMFit.edf_total` at the selected `log_lambda` | `mgcv`'s own `sum(m$edf)` | INDEPENDENT |
| per-term `edf` | `PolarisGAMFit.edf_per_term` | `mgcv`'s own `summary(m)$s.table[, 'edf']`, read positionally | INDEPENDENT |
| `warm_log10_sp` / `warm_reml_score` (pass 3, diagnostic) | `select_lambdas_continuous(x0=mgcv's own log10(sp))` | `mgcv`'s own selection (the SAME values supplied as `x0`) | TRANSPORT — never gates a parity claim |

`SELECT_FREE_SP_MODEL_CLAIM`'s four declared quantities are all INDEPENDENT,
gated by `require_parity_evidence`
(`test_select_free_sp_model_claim_is_independent_on_every_declared_quantity`).
The warm-start diagnostic's own claim (`WARM_START_CLAIM` in
`gam_select_free_sp_warmstart_diagnostic.py`) is TRANSPORT and is never
folded into it — the same discipline `scripts/gam_free_sp_warmstart_diagnostic.py`
established at N=4.

## Oracle version

Tier 1: R 4.3.3 (2024-02-29) / mgcv 1.9-1 (local apt), matching the routine's
expected versions — no drift.

Tier 3: dispatched this session via `workflow_dispatch` on this branch (oracle
`sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8`,
build 8, R 4.6.1 / mgcv 1.9.4, the digest this epic has used throughout) —
CI run [33458654272](https://github.com/jonathancrawford05/polaris-re/actions/runs/33458654272),
completed in ~3 minutes end to end (both jobs). **CONFIRMED, identical in
verdict and to 3-4 significant figures to the tier-1 readings above:**
single-start `max_abs_log10_sp_diff=5.1320` / `max_abs_eta_diff=4.456e-01` /
`edf_total_diff=+2.4216`; multistart `max_abs_log10_sp_diff=1.4754` /
`max_abs_eta_diff=2.681e-03` / `edf_total_diff=-0.1106`; warm-start score gap
(multistart - warm) `+0.014092`, max abs (warm - mgcv) `0.001314`, identical
READING (hypothesis 1 confirmed). Required conformance levels 1-3 also
re-confirmed AGREE on this run (no regression from `fit_polaris_gam`'s new
opt-in parameter), level 4 still DISAGREES (ADR-190, unaffected), level 5
AGREES. `docs/DECISIONS.md` (ADR-218) and
`docs/CONTINUATION_mgcv_parity_engine.md` are updated with these tier-3
figures per the routine's own rule (tier 3 only in those two files).

## Quality gate

- `uv run ruff format src/ tests/ scripts/` — 363 files unchanged (no
  reformatting needed beyond what was already written in the correct style).
- `uv run ruff check src/ tests/ scripts/ --fix` — 12 pre-existing errors
  remain, none in a file this session touched (verified explicitly: `grep`
  over the error list against the diff's own file set).
- `uv run pytest tests/test_analytics/test_gam_model.py
  tests/test_analytics/test_gam_model_conformance.py
  tests/test_analytics/test_gam_select_free_sp_conformance.py
  tests/test_analytics/test_gam_select_multiterm_conformance.py
  tests/test_analytics/test_gam_reml_optimize.py -q` — **57 passed.**
- Full suite (`pytest tests/ -m "not slow"`) re-run after all changes:
  **3541 passed, 5 failed, 22 skipped, 126 deselected** (559.6s). The 5
  failures are the identical pre-existing mortality-table gap; 3541 = the
  3532-passed baseline + 8 new tests this session added + 1 previously-flaky
  test (`test_the_r_probe_runs_end_to_end`) passing cleanly this run — no
  regression. `tests/qa/` byte-identical (`git diff` on
  `tests/qa/golden_outputs/` empty — this session touches no path any golden
  depends on, and every `tests/qa/` case passed as part of this run).
- Conformance re-run at tier 3 (this session's own CI dispatch): required
  levels 1-3 unaffected by this session's changes (no `src/` path this
  session touched is on the required-levels' own dependency list beyond
  `gam_model.py`'s new opt-in parameter, which is additive and does not
  change any existing caller's behaviour) — confirmed by the run cited above.

## Perf history

`uv run python scripts/perf_history.py -o ...` — appended one row for this
branch's HEAD commit (ADR-177 step 14b, initial PR open). Verdict:
`has_structural_creep=False`; `has_wall_time_creep=True` (recent/baseline
wall-time ratio 1.338x, ordinary run-to-run variance on the `TermLife.project`
probe this script measures — unrelated to this session's GAM-only change,
same class of noise prior sessions' own perf rows record).

## Definition of done (PLAN slice 7b's own acceptance, per ADR-209 decision 3)

- `[machine]` R probe runs end to end — `Rscript scripts/gam_select_multiterm_free_sp_probe.R`
  exits 0. **MET** — tier 1 confirmed this session; tier 3 confirmed by the
  CI run cited above.
- `[machine]` Python comparator reads only the shared recipe, proven by
  `test_fit_select_free_sp_case_signature_takes_no_r_fit_output`. **MET.**
- `[machine]` `SELECT_FREE_SP_MODEL_CLAIM` declares all four quantities
  INDEPENDENT, gated by `require_parity_evidence`. **MET**, proven by
  `test_select_free_sp_model_claim_is_independent_on_every_declared_quantity`.
- `[machine]` Tier-1 AND tier-3 measurement recorded in
  `docs/CONFORMANCE_LEDGER.md`. **MET** — six rows this session (three tier-1,
  three tier-3, all agreeing in verdict and order of magnitude).
- `[judgement]` The registered prediction resolved, in those words. **MET** —
  first half CONFIRMED (single-start underperforms multistart, worse in
  absolute terms than any N=4 reading), second half REFUTED (the null-space
  blocks are not the culprit once multistart is applied; two EXISTING blocks
  are).
- `[judgement]` If the gap does not close, it is characterised with evidence
  and a named next hypothesis, never left as an unregistered "Open question".
  **MET** — `log10(sp)` does not close to the `1e-2` gate; the warm-start
  diagnostic characterises exactly why (optimiser convergence on a
  weakly-identified surface), and the acceptance-metric question is restated
  in "Open questions" (`docs/CONTINUATION_mgcv_parity_engine.md`) as a
  maintainer decision, not filed as a new open-ended slice.
- `[machine]` `.github/workflows/mgcv-conformance.yml` gains the new probe
  step, artifact entry and comparator step, `continue-on-error: true`.
  **MET.**
- `[machine]` Required conformance levels 1-3 still AGREE, no regression.
  **MET**, confirmed by this session's own tier-3 CI run.
- `[machine]` `tests/qa/golden_outputs/` byte-identical. **MET** —
  `git diff` on that path is empty.

## Follow-ups filed

- The `eta`/`edf`-vs-`log10(sp)` acceptance-metric question — restated in
  `docs/CONTINUATION_mgcv_parity_engine.md`'s "Open questions" section with
  this slice's own N=7 data point, maintainer-reserved (unchanged from
  ADR-212, not a new item).
- Combining `select=True` with the target's full eight-term structure, or
  with an `sz` term — named in ADR-217/ADR-218, not attempted, no new slice
  registered for it this session (out of this slice's own stated scope).
