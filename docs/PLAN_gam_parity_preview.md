# Plan: the GAM parity preview — make the verified engine usable by someone outside this repo

> **STATUS: APPROVED — ACTIVE EPIC from 2026-10-06 (maintainer; ADR-248).** Its
> precondition, `PLAN_wood_outer_solver.md` Slice 4, is DONE (ADR-248):
> `fit_polaris_gam` defaults to the deterministic Newton search. Epic started and **P1 DONE** 2026-10-06 (ADR-249;
> `CONTINUATION_gam_parity_preview.md`). **NEXT: Slice P2.**
>
> **Maintainer decisions already taken (2026-10-06, recorded in ADR-248):**
> (1) the public entry point is **`polaris_re.gam`** (P3); (2) a bare `s(x)` is
> **refused until rung L7 (`bs="tp"`) is verified**, then accepted as `tp`,
> because `mgcv`'s own default is what the oracle defines (P3). Neither is
> re-opened by a session.

**Source:** maintainer question, 2026-10-04: *"I am hoping that we will soon have
a suitable parity engine to expose to potential users — what is outstanding?"*
The answer recorded here was given in the review of PR #254/#256.
**Predecessors:** `PLAN_wood_outer_solver.md` (one deterministic solver, Slice 4);
`PLAN_mgcv_capability_ladder.md` (the verified bases); ADR-202 (Wood-Pya-Säfken
unconditional covariance, tier 3); ADR-193 / `docs/VERIFICATION_STANDARD.md`.
**Routine:** `docs/ROUTINE_MGCV_PARITY.md` — same tiers, same provenance gate,
same nevers.
**Total slices:** 5. **No slice may be split without maintainer approval** (§4).
The house guideline is 3-4 slices per epic (PR #257 review P2): the epic-start
session confirms in its ADR that P5 (release) carries a user-facing deliverable
and an INDEPENDENT comparison of its own (the generated parity report) — or folds
P5 into P4 — so it is never a polish tail.

---

## 1. The gap, measured on `main` (2026-10-05)

The engine fits. It cannot be *used*. Every statement below was checked against
the code, not against prose:

| a user needs | today | evidence |
|---|---|---|
| to call it | **nothing outside the harness calls it.** `fit_polaris_gam` is imported only by `*_conformance.py` modules and `scripts/gam_*` diagnostics; no CLI, API, dashboard or MCP path reaches it | `grep -rl "gam_model" src/ scripts/` |
| to write a model | **no formula front end.** A model is a hand-built `ModelSpec(terms=(TermSpec(...), ...))`; factor columns must arrive as integer codes the caller has ordered to match R's | `gam_term_spec.py` |
| to predict | **no `predict`.** `PolarisGAMFit` carries `eta` at the training rows only. The per-term knots and identifiability constraints are rebuilt from the *training* design inside the builders and not kept, so new rows cannot be evaluated on the same basis | `gam_model.py:400`, `gam_stage_a.build_python_*_term` |
| uncertainty | **no covariance on the fit.** `gam_model.py`'s module docstring says so. `gam_uncertainty.unconditional_covariance` (ADR-202, tier 3) exists but is wired to the older `experience_gam_penalized` surface, not to `PolarisGAMFit` | `gam_model.py:52-55`, `gam_uncertainty.py:311` |
| a summary | **none.** `edf_per_term`, `log_lambda`, `dispersion` exist as fields; nothing assembles them | `gam_model.py:400-437` |
| to know what is safe | **no refusal.** An unverified combination is either rejected deep in a builder or silently attempted | `MGCV_FEATURE_COVERAGE.md` §2 |
| scale | **largest verified fit is 7 penalty blocks** (`select=TRUE` N=7); the near-term target formula under `select=TRUE` is ~13+ | `MGCV_FEATURE_COVERAGE.md` §3 |

What *is* ready, and is the preview's scope: `cr` (incl. numeric and factor
`by`), `ti`, `re`, the parametric block, `select=TRUE`; `gaussian(identity)`,
`poisson(log)`, `quasipoisson(log)` (estimated **and** fixed scale),
`binomial(logit|cloglog)`; weights and offset; one deterministic Newton REML
search — `fit_polaris_gam`'s default since ADR-248. All tier 3, INDEPENDENT.

## 2. The preview's definition of done (the epic's acceptance test)

A user with a Polars DataFrame and an `mgcv` formula string **from the verified
subset** can, through one public Python entry point:

1. fit it — one call, no solver flags, deterministic;
2. predict at new rows, on the link and response scales, with standard errors;
3. print a summary (per-term edf, smoothing parameters, scale, REML score,
   deviance explained, n);
4. be **refused by name** — with the `MGCV_FEATURE_COVERAGE.md` row that says
   why — for anything outside the subset;

and every one of 1-3 has an INDEPENDENT tier-3 comparison against `mgcv` on
the same formula string, published in a parity report that is **generated**
from the declared `VerificationClaim`s (`evidence_markdown()`), never
hand-written.

**Explicitly not in the preview:** p-values / `anova.gam` / Wood (2013) smooth
tests; `bam`, `fREML`, `discrete=TRUE`; `tp`, `te`, `t2`, `fs`; free-`sp` `sz`;
the dashboard, CLI, MCP and pricing pipeline (Anchor 7 — a separate maintainer
decision once the preview exists).

## 3. The slices

Every slice lands **(i) one user-callable capability and (ii) at least one
INDEPENDENT tier-3 comparison of it.** A slice that can land only harness
work is not done; it is reported as blocked (§4), not re-scoped.

### Slice P1 — predict at new data

Keep, per term, what `mgcv` keeps in `m$smooth[[i]]`: knots, the absorbed
identifiability constraint (the null-space basis computed from the *training*
design), `by`/factor-`by` metadata, factor levels, and the parametric block's
contrast coding. `PolarisGAMFit.predict(newdata, type="link"|"response")`
evaluates each term on those stored objects (`mgcv`'s `PredictMat`).

- **Refactor guard `[machine]`:** the training design assembled through the
  stored objects is bit-identical to today's `assemble_model_design` output on
  every conformance recipe; every existing conformance test and the goldens
  unchanged.
- **Own-criterion check `[machine]`:** `predict(training rows)` equals
  `fit.eta` to `1e-12`.
- **INDEPENDENT `[machine]`:** on held-out rows the R probe never saw at fit
  time, Polaris `predict` vs `predict.gam(m, newdata)` for the six free-scale
  cells and the 4-term HGAM, under ADR-221's `eta` gate. Producer: Polaris
  takes the recipe plus `newdata`; `mgcv` predicts from its own fit.
- Out-of-range covariates: match `mgcv`'s own behaviour beyond the end knots,
  measured on the probe (not assumed); a test pins it.

### Slice P2 — standard errors

`PolarisGAMFit.vcov(unconditional: bool = False)` — `Vp` (Bayesian posterior
covariance, scaled by the fitted dispersion) and the Wood-Pya-Säfken
unconditional correction via the existing `gam_uncertainty.unconditional_covariance`,
fed by the exact REML Hessian the Newton search already computes
(`gam_reml_hessian`, ADR-243). `predict(..., se_fit=True)`.

- **INDEPENDENT `[machine]`:** `vcov(m)`, `vcov(m, unconditional=TRUE)` and
  `predict(m, newdata, se.fit=TRUE)$se.fit` vs Polaris on the six cells + HGAM.
  The tolerance is **derived and written down in the slice's ADR before the
  first tier-3 run** (relative, on `se.fit`), not chosen after reading it.
- **Known risk, measured not assumed:** on `select=TRUE` plateau blocks
  `V_rho` is near-singular; `MGCV_RHO_RIDGE` is `mgcv`'s own regulariser.
  Report the `select=TRUE` row separately.
- quasi families: confirm the dispersion scaling convention against `mgcv`
  (`Vp` carries `m$scale`); `gam_uncertainty`'s docstring says the inputs are
  unit-dispersion — the slice states where the scale is applied.

### Slice P3 — the public entry point and the formula front end

Package location decided (maintainer, 2026-10-06): **`polaris_re.gam`**, a new
subpackage with its own `__init__.py`/`__all__`, depending on `analytics/`, never
the reverse.

`polaris_re.gam.gam(formula: str, data: pl.DataFrame, family: str, *, weights=None,
offset=None, select=False, scale=None) -> PolarisGAMFit` — a thin, typed facade
(`__all__`, docstrings, no solver knobs; diagnostics stay on `fit_polaris_gam`).

- Parses the verified subset of `mgcv` syntax: `s(x, k=, bs="cr")`,
  `s(x, by=z)` / `s(x, by=f)`, `ti(x, z, k=c(.,.), bs="cr")`, `s(f, bs="re")`,
  `a + b + a:b` parametric factors, `offset(.)`. Anything else raises
  `PolarisValidationError` naming the construct and the coverage row
  (e.g. *"`bs='tp'` (mgcv's default for a bare `s(x)`) is not supported —
  MGCV_FEATURE_COVERAGE.md §2.1 L7; write `bs='cr'`"*). **A bare `s(x)` is
  refused, never silently mapped to `cr`** (maintainer, 2026-10-06). When L7
  (`tp`) is verified against `mgcv`, a bare `s(x)` becomes `tp` — the default is
  whatever `mgcv`'s own is, because the oracle defines it — and its refusal test
  is replaced by a parity test in that rung's slice.
- Factor coding reproduces R's: levels sorted as R's `factor()` sorts them
  (collation is locale-dependent — pin the oracle image's locale and state it),
  first level as reference (`contr.treatment`). A test pins
  mixed-case and numeric-string level ordering against an R probe.
- **INDEPENDENT `[machine]`:** the R probe receives the **same formula string**
  and data; `mgcv::gam` fits it; Polaris fits it through `gam(...)`; compared
  on `eta`/`edf_total` (ADR-221) for every gauntlet formula, now expressed as
  strings. The parse itself is checked against `mgcv`'s own `m$smooth`
  labels/`bs.dim`/`m$nsdf` (term structure), as a second, cheaper column.
- Refusal list `[machine]`: one test per refused construct.

### Slice P4 — summary, and one fit at the target's size

`PolarisGAMFit.summary()` — per-term edf, `log10(sp)`, scale, REML score,
deviance explained, n, convergence (Newton iterations, the final relative
projected gradient against `ε_rel = 1e-6`, ADR-248). **No
p-values** (they are a separate method, Wood 2013, out of scope — the summary
says so in its footer).

- **INDEPENDENT `[machine]`:** per-term edf, `sp`, `scale`, `dev.expl` vs
  `summary.gam(m)` on the gauntlet formulas.
- **Scale `[machine]`:** the near-term target formula (`cr` + `re` + `ti` +
  parametric block + the MI `by` term, quasi-Poisson, `select=TRUE`, ≥ 13
  penalty blocks) on a synthetic data set of production-like size, one Newton
  start, tier 3, ADR-221 gate; wall time and fit count recorded. If it fails on
  gradient precision within 2x of tolerance, that **is** Wood slice 3b's
  release condition — run 3b, nothing else.

### Slice P5 — release the preview

- `docs/GAM_USER_GUIDE.md`: install, one worked example end to end (fit,
  predict with SEs, summary), the supported subset, the refusal list.
- `notebooks/gam_parity_preview.ipynb` running the same example.
- `scripts/gam_parity_report.py` → `docs/GAM_PARITY_REPORT.md`, generated from
  the declared claims of P1-P4 plus the Wood gauntlet, headline by
  `evidence_markdown()`, pinned to its tier-3 run id and oracle digest.
- `[judgement]` the README / guide wording says **"preview"** and names the
  verified subset, oracle version and tolerance — never an unqualified
  "mgcv-compatible".
- What gets exposed beyond Python (CLI / MCP / dashboard) is put to the
  maintainer here, as a question, with a recommendation — not decided by the
  routine.

## 4. Rules that keep this epic from spiralling

1. **Every slice ships a capability.** "One user-callable capability + one
   INDEPENDENT tier-3 comparison" is the floor. Harness-only work is a
   sub-step of a slice, never a slice.
2. **No splitting.** P1-P5 are not split into letter-suffix parts without a
   maintainer comment approving it. A session that cannot finish its slice
   opens the PR as WIP and the next session finishes the same scope.
3. **A disagreement is a limitation first, a slice never.** If a comparison
   disagrees on something outside the target formula, it is recorded in the
   user guide's limitations and the refusal list (the construct is refused),
   and the epic moves on. Only a disagreement *on the target formula* blocks,
   and its mechanism goes to the owning plan (outer search → Wood plan's
   acceptance cases, per ROUTINE "MECHANISM BEFORE SLICE").
4. **No new solver work.** Start strategies, multistart and solver tuning are
   out of scope. Slice 3b is the only solver change that may run, and only on
   its registered release condition.
5. **Questions go to the maintainer the session they arise**, in the PR body
   and the CONTINUATION's "Maintainer questions" section, with a recommended
   answer. Work that does not depend on the answer continues.

## 5. Out of scope (and where each item lives)

| item | where it resumes |
|---|---|
| L6 `fs`, L7 `tp`, L8 `te`/`t2` | `PLAN_mgcv_capability_ladder.md`, **after** this epic, ordered by what preview users ask for |
| L9/L10 `fREML`, `bam`, `discrete=TRUE` | same; its own epic |
| L11 / slice 6b `sz` free-`sp`, `select=TRUE` on `cr+re+ti` | ladder, after this epic |
| p-values, `anova.gam`, `gam.check` | a post-preview item, if users ask |
| dashboard / CLI / MCP / pricing pipeline | maintainer decision at P5 (Anchor 7) |
| convergence certificate object (verdict, second-order report) | `PROPOSAL_convergence_certificate.md`; its two numbers are CLOSED (ADR-248: `ε_rel = 1e-6`, identified = step-stability scan); building it waits on demand |

## 6. Risks

1. **Stored-constraint refactor touches verified builders.** Mitigation: P1's
   bit-identical refactor guard runs before any new behaviour lands.
2. **Factor level ordering.** R sorts levels locale-dependently; the oracle
   runs in a fixed image. Pin that image's rule and test it against the probe.
3. **Covariance on plateaus.** `select=TRUE` blocks at large `sp` make `V_rho`
   near-singular; report that row separately rather than loosening the gate.
4. **Size.** The 13+-block fit is the first at target size. Its failure mode is
   pre-registered (Wood 3b); any other failure is a limitation, recorded, and
   the preview ships on the sizes that pass, saying so.
