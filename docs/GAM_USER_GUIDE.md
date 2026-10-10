# Polaris GAM — user guide (PREVIEW)

> **Preview.** `polaris_re.gam` fits a **verified subset** of `mgcv`'s `gam()` formula
> language by REML and predicts, with standard errors, from the fit. It is **not**
> "`mgcv`-compatible" in general: it reproduces `mgcv` on the constructs in §5, on the
> synthetic cells in the [generated parity report](GAM_PARITY_REPORT.md), against **one
> pinned oracle** — R 4.6.1 / `mgcv` 1.9.4, image digest
> `sha256:0d54c192e23c62bdc614eb5b534e04482f6cf92290e76cacb7956022cd806fd8` — under
> these gates: `eta` within `2e-2` and `edf_total` within `1` (ADR-221), relative `se.fit`
> within `2e-2` (ADR-250). Everything outside §5 is refused **by name** (§6), never
> silently approximated. The word to take from this paragraph is *evidence about these
> cells*, not *a guarantee about your model*.

## 1. Install

```bash
git clone https://github.com/jonathancrawford05/polaris-re.git
cd polaris-re
uv sync --all-extras
```

There is no R dependency. R and `mgcv` appear only in the repository's conformance CI,
which is where the parity report comes from.

## 2. A worked example, end to end

The data are synthetic mortality-style counts (`scripts/gam_guide_example_data.py`; not
experience data): 800 training cells with `deaths`, `age`, `duration`, `sex` and
`log_exposure`, plus 60 held-out rows. The same formula string and the same CSVs are fitted
by `mgcv` in CI, so **this example is itself a row of the parity report** (its §4).

```python
from polaris_re.gam import GUIDE_FAMILY, GUIDE_FORMULA, gam, load_guide_example

train, new = load_guide_example()
print(GUIDE_FORMULA)
fit = gam(GUIDE_FORMULA, train, GUIDE_FAMILY)
```

`gam(formula, data, family)` takes an `mgcv` formula string and a Polars DataFrame. There
are no solver options: the smoothing parameters come from one deterministic Newton REML
search (`fit.converged` says whether it met its criterion; a warning is raised if not).
String, categorical and enum columns are factors; the first level is the reference.

### Summary

```python
print(fit.summary())
```

reports per-smooth `edf` and `log10(sp)`, the scale, the REML score, deviance explained,
`n`, and the Newton search's convergence (iterations, final relative projected gradient
against `epsilon_rel = 1e-6`). **There are no p-values**: the smooth-term tests of
`summary.gam` (Wood 2013) are not in the verified subset, and the printed footer says so.

### Predict, with standard errors

```python
link, link_se = fit.predict(new, "link", se_fit=True)
rate, rate_se = fit.predict(new, "response", se_fit=True)
_, link_se_c = fit.predict(new, "link", se_fit=True, unconditional=True)
print(rate[:3], rate_se[:3])
```

`predict` takes a DataFrame with the training covariates (and the offset column, if the
formula has one). `se_fit=True` is `predict.gam(..., se.fit=TRUE)` — the Bayesian posterior
covariance `Vp`, scaled by the fitted dispersion. `unconditional=True` adds the
Wood-Pya-Säfken smoothing-parameter-uncertainty correction (`Vc`). Rows outside the
training range are extrapolated linearly beyond the end knots, as `mgcv` does; that
agreement is measured but **reported, not gated**, in the parity report, because linear
extrapolation amplifies any gap in the fit itself. A factor level not seen in training is
refused.

### Read what you got

```python
print(fit.edf_per_term, fit.dispersion, fit.converged)
```

## 3. Choosing the family

`"gaussian"`, `"poisson"`, `"quasipoisson"`, `"binomial"` — optionally with a link
(`'binomial(link="cloglog")'`). `weights="col"` names a prior-weights column;
`offset(col)` in the formula (or `offset="col"`) names an offset. For counts with an
exposure, put `offset(log_exposure)` in the formula, as the example does. Gaussian,
Poisson, quasi-Poisson (estimated scale) and binomial (logit, cloglog) are each compared
with `mgcv` in the report.

## 4. Things that are different from R

- **REML scores are not comparable across packages** for non-Gaussian or weighted fits
  (an additive convention constant differs, ADR-231); do not compare `fit.summary()`'s REML
  score with R's. Gaussian unweighted scores agree.
- **`log10(sp)` is reported, never gated.** On `select=TRUE` and on terms the data barely
  need, the REML surface is flat in `sp` while `eta` and `edf` agree; the report shows
  `log10(sp)` differences of up to a couple of decades on such rows. If you compare
  smoothing parameters with R's, compare the fitted curves, not `sp`.
- **Factor levels follow R's `factor()` order under the oracle's `en_US.UTF-8` collation**
  for `[A-Za-z0-9_]` strings (verified on two string sets). For anything else, pass a
  Polars `Enum` and the declared order is used.
- **Coefficients are not compared and not comparable**: `mgcv` reparameterises. Compare
  `eta`, `edf`, `se.fit`.

## 5. The verified subset

| construct | status | evidence (tier 3 unless noted) |
|---|---|---|
| `s(x, bs="cr", k=)` — cubic regression spline | supported | parity report §2 (every cell) |
| `s(x, by=z, bs="cr")` — numeric `by` (varying coefficient) | supported | report §2, §1 |
| `s(x, by=f, bs="cr")` — factor `by`, written `f + s(x, by=f, ...)` | supported | report §2 (`gaussian_factor_by`) |
| `s(x) + s(x, by=f)` (with or without `f`) — a smooth beside a factor-`by` smooth of the same covariate | supported **with a pivot** (Slice 9, ADR-255): the one coefficient the data cannot identify is eliminated, as `mgcv` does. `eta`, `edf_total` and the standard errors (`unconditional=False`) are compared with `mgcv`; **`unconditional=True` is refused** for such a fit (§7); per-term `edf` depends on which coefficient is eliminated, and `mgcv` itself does not reproduce it between runs (ADR-256), so it is reported but not gated. Such a model emits a `PolarisRankDeficiencyWarning` when fitted | ADR-255, report §1-§3 |
| `ti(x, z, bs="cr", k=c(.,.))` — tensor interaction | supported | report §2, §4 |
| `s(f, bs="re")` — random-effect / level indicator | supported | report §2 |
| factors `a`, `a:b` (with both main effects), `offset(col)` | supported | report §2 |
| `select=TRUE` | supported with `cr`, numeric `by`, `ti`, `re`, parametric | report §2, §3 |
| `select=TRUE` with a factor-`by` smooth: `f + s(x, by=f, bs="cr")` and `s(x, by=f, bs="cr")` | supported (Slice R1, ADR-258). Each by-level smooth gets its own null-space penalty, as in `mgcv`. The fit is **not** pivoted (no redundancy warning) and both `unconditional=False` and `unconditional=True` standard errors are available | ADR-258, report §1-§3, §6 |
| 15-penalty quasi-Poisson `select=TRUE` fit, 5,000 rows | one cell, one draw | report §3 (target-size row) |
| families gaussian / poisson / quasipoisson / binomial | supported | report §2 |

A bare `s(x)` is **not** in the table: `mgcv`'s default basis is `tp`, which is not
verified yet. Write `s(x, bs="cr")` — the same model with an explicit basis is accepted
for every form above.

## 6. Refused by name

Each of these raises `PolarisValidationError` naming the construct and the
[coverage row](MGCV_FEATURE_COVERAGE.md) that explains why. One test per construct.

| refused | why |
|---|---|
| a bare `s(x)` (mgcv default `tp`) | `tp` is ladder rung L7, not yet verified; write `bs="cr"` |
| `bs="tp"`, `"ps"`, `"fs"`, `"sz"`, and any other basis | not verified (§2.1 of the coverage file) |
| `te()`, `t2()`, `ti()` of three variables, multi-variable `s()` | not verified |
| `select=TRUE` with a bare smooth beside a factor-`by` smooth of the same covariate (`s(x) + s(x, by=f)`, with or without `f`) | on that shape the Newton search stops, converged by its own criterion, at a point `mgcv`'s REML scores lower in 8 of 60 draws (up to 0.12 on `eta`); the forms without the bare smooth agreed in 60 of 60 (ADR-258, report §6). Drop the bare smooth, or fit without `select=TRUE` |
| `scale=` (a fixed dispersion) | verified only inside the conformance module, not through the production fitter |
| `s(..., sp=, fx=, m=)`, `ti(..., by=)` | not verified |
| `a*b`, `a^2`, `a:b:c`, `-1`, `0 +`, transformed variables or responses (`log(x)`, `poly(x,2)`, `factor(g)`) | transform the column in Polars first |
| a missing value, a non-numeric smooth covariate, an unseen factor level at predict time | refused with the column named |

If your model is not in §5 and not in §6, it is refused too (by the parser, with the
construct named). Nothing in the preview falls back to a guess.

## 7. Limitations that were measured

- **The factor-`by` beside a bare smooth** (§5) was first met as a miss against `mgcv` on one
  synthetic draw (`gaussian_factor_by`, ADR-249); the mechanism is a rank defect, not an
  outer-search problem (ADR-250), and since Slice 9 (ADR-255) it is fitted with the
  unidentified coefficient pivoted out. **The unconditional covariance (`Vc`,
  `unconditional=True`) is refused for such a fit:** its second-order term depends on which
  coefficient is eliminated, and `mgcv`'s own choice is rounding noise on exactly tied
  candidates (its per-term edf moves by 1.0 and `Vc` `se` by up to 4% between two thread
  counts of the same image), so there is no rule to reproduce (ADR-256). `Vp`-based standard errors, `eta` and `edf_total`
  do not depend on that choice; per-term edf does (§5).
- **`select=TRUE` with a bare smooth beside a factor-`by` smooth** of the same covariate is refused (§6): over 15 draws per cell the Newton search stopped, converged by its own test, at a point `mgcv` scores lower in 8 of 60 fits (ADR-258). The forms without the bare smooth agreed in 60 of 60.
- **Size.** The largest verified fit is the 5,000-row, 15-penalty cell in the report. A
  30,000-row fit was run for Polaris alone (it converges in about 40 s on the development
  box) but has no `mgcv` side — plain `gam()` does not finish at that size and `bam` is out
  of scope — so it is a measurement of this engine against its own criterion, **not**
  parity.
- **One draw per cell.** Every cell in the report is one synthetic sample. Agreement there
  is evidence, not a coverage guarantee.
- **Not in the preview:** p-values / `anova.gam`, `bam`, `fREML`, `discrete=TRUE`, `tp`,
  `te`, `t2`, `fs`, free-`sp` `sz`, and any CLI, API, dashboard or MCP exposure.

## 8. How it is verified, and what that does and does not show

The [parity report](GAM_PARITY_REPORT.md) is **generated** by
`scripts/gam_parity_report.py` in the conformance workflow, pinned to its CI run id, commit
and oracle digest. Every headline in it is produced by `evidence_markdown()` from a declared
`VerificationClaim` (ADR-193): for each compared column it names what computed each side,
and a column only counts as parity evidence when Polaris and `mgcv` each computed it from
the same recipe — the formula string and the data — without either reading the other's
output. Columns that are merely echoed or parsed are labelled as such and are not counted.
Golden regression files in `tests/qa/golden_outputs/` are this engine's own prior output:
they detect change, not correctness, and are not cited anywhere in the report.

To reproduce a row yourself you need R with `mgcv` (any recent release is fine for a
sanity check; the report's numbers are the pinned image's), the CSVs in
`data/gam_preview/`, and the formula string printed above.
