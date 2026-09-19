#!/usr/bin/env Rscript
# Backs every measured number in docs/MGCV_NOTATION_PRIMER.md sections 1, 3 and 4.
#
# The primer states penalty-counting RULES ("te has one smoothing parameter per
# margin", "t2 has 2^d - 1", "fs has 1 + M and does not grow with factor
# levels").  A rule stated from memory is worth nothing here -- ADR-193's whole
# point -- so each rule is written below as a PREDICTION and then checked
# against what mgcv actually constructs.  The script exits non-zero on the first
# disagreement, so a future mgcv that changes a construction breaks this loudly
# instead of silently falsifying the primer.
#
# Scope note: this is a probe of *mgcv's own* term construction.  Polaris is not
# involved on either side, so nothing here is parity evidence under ADR-193 --
# it is a reference-behaviour measurement, and the primer cites it as such.
#
# Usage:  Rscript scripts/mgcv_penalty_count_probe.R
# Tier:   tier 1 when run locally; tier 3 when run by mgcv-conformance.yml
#         against the pinned image (docs/ROUTINE_MGCV_PARITY.md).

suppressPackageStartupMessages(library(mgcv))

cat("R          :", R.version.string, "\n")
cat("mgcv       :", as.character(packageVersion("mgcv")), "\n\n")

failures <- 0L

check <- function(label, actual, expected) {
  ok <- isTRUE(all.equal(actual, expected))
  if (!ok) failures <<- failures + 1L
  cat(sprintf(
    "  [%s] %-56s actual=%s expected=%s\n",
    if (ok) "ok" else "FAIL", label,
    paste(actual, collapse = ","), paste(expected, collapse = ",")
  ))
  invisible(ok)
}

# Deterministic synthetic data.  Nothing here depends on the response, only on
# how mgcv constructs the design and penalties, but a fit still has to run.
set.seed(20260916)
n <- 400
dat <- data.frame(
  x = runif(n), z = runif(n), w = runif(n),
  ang = runif(n, 0, 1) # for the cyclic margin
)
dat$y <- sin(2 * pi * dat$x) + dat$z + rnorm(n, sd = 0.3)
for (lv in c(2L, 4L, 6L)) {
  dat[[paste0("f", lv)]] <- factor(rep_len(seq_len(lv), n))
}
dat$f3 <- factor(rep_len(seq_len(3L), n))

# Number of penalty matrices and coefficients mgcv builds for each smooth in a
# formula.  gam(fit = FALSE) does the construction without the fit, which is
# exactly the layer these rules are about.
term_report <- function(formula, data = dat) {
  g <- gam(formula, data = data, fit = FALSE)
  lapply(g$smooth, function(sm) {
    list(
      label = sm$label,
      n_pen = length(sm$S),
      ncoef = sm$last.para - sm$first.para + 1L
    )
  })
}

one_term <- function(formula, data = dat) term_report(formula, data)[[1L]]

total_sp <- function(formula, data = dat) {
  sum(vapply(term_report(formula, data), function(s) s$n_pen, integer(1)))
}

# ---------------------------------------------------------------------------
cat("== SECTION 1: the default basis, and constructions consuming a margin ==\n")
# Primer S1: "a bare s(x) is a thin-plate regression spline".
bare <- gam(y ~ s(x), data = dat, fit = FALSE)$smooth[[1L]]
cat("  bare s(x) class :", paste(class(bare), collapse = ", "), "\n")
cat("  formals(mgcv::s)$bs :", formals(mgcv::s)$bs, "\n")
check("bare s(x) is a tprs.smooth", "tprs.smooth" %in% class(bare), TRUE)
check("s() default bs is 'tp'", as.character(formals(mgcv::s)$bs), "tp")

# Primer S1: "sz is built on top of cr (or tp, or ps; measured, all accepted)".
for (margin in c("cr", "tp", "ps")) {
  got <- tryCatch({
    one_term(as.formula(sprintf(
      'y ~ s(f3, x, bs = "sz", k = 8, xt = list(bs = "%s"))', margin
    )))
    TRUE
  }, error = function(e) FALSE)
  check(sprintf("sz accepts a '%s' margin via xt", margin), got, TRUE)
}
cat("\n")

# ---------------------------------------------------------------------------
cat("== SECTION 3: smoothing parameters per term ==\n")
cat("   rule: s -> 1 ; te/ti over d margins -> d ; t2 over d margins -> 2^d - 1\n\n")

sec3 <- list(
  list(f = y ~ s(x, k = 6),                       pen = 1L, coef = 5L),
  list(f = y ~ te(x, z, k = c(5, 5)),             pen = 2L, coef = 24L),
  list(f = y ~ ti(x, z, k = c(5, 5)),             pen = 2L, coef = 16L),
  list(f = y ~ t2(x, z, k = c(5, 5)),             pen = 3L, coef = 24L),
  list(f = y ~ te(x, z, w, k = c(4, 4, 4)),       pen = 3L, coef = 63L),
  list(f = y ~ t2(x, z, w, k = c(4, 4, 4)),       pen = 7L, coef = 63L)
)
for (case in sec3) {
  s <- one_term(case$f)
  check(sprintf("%-28s n_pen", s$label), s$n_pen, case$pen)
  check(sprintf("%-28s ncoef", s$label), s$ncoef, case$coef)
}
# The ANOVA-shaped form the epic actually measures: 1 + 1 + 2 = 4.
check("s(x) + s(z) + ti(x,z) total smoothing parameters",
      total_sp(y ~ s(x, k = 6) + s(z, k = 6) + ti(x, z, k = c(5, 5))), 4L)
cat("\n")

# ---------------------------------------------------------------------------
cat("== SECTION 4: the four ways to make something vary by a group ==\n")
cat("   rule: re -> 1 always ; fs -> 1 + M (level-independent) ;\n")
cat("         sz -> one per level ; by=factor -> one TERM per level\n\n")

for (lv in c(2L, 4L, 6L)) {
  fac <- paste0("f", lv)
  fs <- one_term(as.formula(sprintf(
    'y ~ s(x, %s, bs = "fs", k = 10, xt = list(bs = "cr"))', fac)))
  sz <- one_term(as.formula(sprintf(
    'y ~ s(%s, x, bs = "sz", k = 10, xt = list(bs = "cr"))', fac)))
  re <- one_term(as.formula(sprintf('y ~ s(%s, bs = "re")', fac)))
  cat(sprintf(
    "  levels=%d   fs: n_pen=%d ncoef=%-3d |  sz: n_pen=%d ncoef=%-3d |  re: n_pen=%d ncoef=%d\n",
    lv, fs$n_pen, fs$ncoef, sz$n_pen, sz$ncoef, re$n_pen, re$ncoef))
  # fs over a cr margin: null space {constant, linear} -> M = 2 -> 3 penalties,
  # and crucially the SAME 3 at every level count.
  check(sprintf("fs n_pen is level-independent (levels=%d)", lv), fs$n_pen, 3L)
  check(sprintf("sz n_pen grows one per level (levels=%d)", lv), sz$n_pen, lv)
  check(sprintf("re n_pen is 1 regardless of levels (levels=%d)", lv), re$n_pen, 1L)
  check(sprintf("re ncoef is one per level (levels=%d)", lv), re$ncoef, lv)
}
cat("\n")

# by= with a factor is a term MULTIPLIER, not a term parameter.
by_fac <- term_report(y ~ s(x, by = f3, k = 6))
by_num <- term_report(y ~ s(x, by = z, k = 6))
cat("  s(x, by=f), f 3-level   ->  smooths=", length(by_fac),
    "  [", paste(vapply(by_fac, function(s) s$label, ""), collapse = ", "), "]",
    "  total_sp=", total_sp(y ~ s(x, by = f3, k = 6)), "\n", sep = "")
cat("  s(x, by=z), z numeric   ->  smooths=", length(by_num),
    "  [", paste(vapply(by_num, function(s) s$label, ""), collapse = ", "), "]",
    "  total_sp=", total_sp(y ~ s(x, by = z, k = 6)), "\n\n", sep = "")
check("s(x, by=factor) yields one smooth per level", length(by_fac), 3L)
check("s(x, by=numeric) yields a single smooth", length(by_num), 1L)

# ---------------------------------------------------------------------------
cat("\n== SECTION 4b: the 1 + M rule, tested as a prediction ==\n")
cat("   A P-spline with difference-penalty order m has a null space of\n")
cat("   polynomials of degree m-1, so M = m and n_pen should be m + 1.\n")
cat("   Stepping m is what makes this a prediction rather than a restatement.\n\n")
for (m in 1:3) {
  sm <- one_term(as.formula(sprintf(
    'y ~ s(x, f3, bs = "fs", k = 10, m = %d, xt = list(bs = "ps"))', m)))
  cat(sprintf(
    "  fs over ps margin, m=%d  ->  predicted M=%d, predicted n_pen=%d, ACTUAL n_pen=%d\n",
    m, m, m + 1L, sm$n_pen))
  check(sprintf("fs over ps margin m=%d gives 1 + M penalties", m), sm$n_pen, m + 1L)
}
# Cross-check on a margin with a smaller null space: a cyclic spline's null
# space is constants only (M = 1), so the rule predicts 2, not 3.
cc <- one_term(y ~ s(ang, f3, bs = "fs", k = 10, xt = list(bs = "cc")))
cat(sprintf(
  "  fs over cc margin        ->  predicted M=1, predicted n_pen=2, ACTUAL n_pen=%d\n",
  cc$n_pen))
check("fs over a cyclic margin gives 2 penalties, not 3", cc$n_pen, 2L)

# ---------------------------------------------------------------------------
cat("\n")
if (failures > 0L) {
  cat(sprintf("RESULT: %d check(s) FAILED -- docs/MGCV_NOTATION_PRIMER.md is stale.\n", failures))
  quit(status = 1L)
}
cat("RESULT: all checks passed -- docs/MGCV_NOTATION_PRIMER.md sections 1, 3 and 4 reproduce.\n")
