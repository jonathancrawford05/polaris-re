#!/usr/bin/env Rscript
#
# gam_target_size_probe.R -- preview epic Slice P4 (docs/PLAN_gam_parity_preview.md,
# ADR-253): ONE fit at the near-term target's size, mgcv's side.
#
# The cell is the target formula's term archetypes expressed in the VERIFIED subset
# (cr, ti, numeric-by cr, re, a factor parametric block with its interaction), a
# quasi-Poisson response with a log offset, select = TRUE, and >= 13 penalty blocks, on
# 5,000 synthetic rows (plain gam(), not bam(discrete): the 30,000-row fit exceeded 15 min of local mgcv time, ADR-253). `sz` terms
# are NOT in the verified subset (MGCV_FEATURE_COVERAGE.md §2.1), so this is the target's
# SIZE and block count, not its exact `sz` structure -- the cell says so, it does not
# pretend otherwise.
#
# The export has the same shape as gam_formula_probe.R's cells (recipe + "mgcv" +
# "summary"), plus mgcv's wall-clock fit time. Polaris reads nothing under "mgcv" or
# "summary". Synthetic data only (DATA_LICENSING.md §1).
#
# USAGE: Rscript scripts/gam_target_size_probe.R [out.json]      EXIT: 0 ok, 1 R-side error

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_target_size_probe.json"
  set.seed(20261009); n <- 5000
  d <- data.frame(
    age = runif(n, 25, 95), dur = runif(n, 1, 25), z = runif(n, 0, 10),
    mi = runif(n, -5, 6), expo = runif(n, 0.5, 4),
    FS = sample(c("small", "large"), n, TRUE), SM = sample(c("ns", "sm"), n, TRUE),
    grp = sample(paste0("g", 1:6), n, TRUE), stringsAsFactors = FALSE)
  lrr <- -0.012 * d$mi * (1 + 0.01 * (d$age - 60)) + 0.05 * sin(d$age / 11) -
    0.20 * exp(-d$dur / 8) + 0.04 * sin(d$z / 2) +
    0.10 * (d$FS == "large") + 0.15 * (d$SM == "sm") +
    c(g1 = 0, g2 = 0.05, g3 = -0.04, g4 = 0.08, g5 = -0.06, g6 = 0.02)[d$grp] +
    0.05 * sin(d$age / 14) * cos(d$z / 3)
  q <- 0.002 + 0.00004 * exp(0.075 * (d$age - 25))
  mu <- d$expo * q * exp(lrr)
  d$y <- rnbinom(n, mu = mu, size = 30)       # overdispersed: quasi-Poisson is the right family
  d$off <- log(d$expo * q)

  formula <- paste0(
    'y ~ offset(off) + FS + SM + FS:SM + s(age, k = 13, bs = "cr") + ',
    's(dur, k = 6, bs = "cr") + s(z, k = 8, bs = "cr") + ',
    'ti(age, dur, k = c(13, 6), bs = "cr") + ti(age, z, k = c(8, 5), bs = "cr") + ',
    's(age, by = mi, k = 13, bs = "cr") + s(grp, bs = "re")')
  dfit <- d
  dfit[] <- lapply(dfit, function(v) if (is.character(v)) factor(v) else v)
  elapsed <- system.time(
    m <- mgcv::gam(as.formula(formula), data = dfit, family = quasipoisson(),
                   method = "REML", select = TRUE)
  )[["elapsed"]]
  sm <- m$smooth
  ssum <- summary(m)
  fac_names <- names(m$model)[vapply(m$model, is.factor, logical(1))]
  cell <- list(
    name = "quasipoisson_target_size", formula = formula, family = "quasipoisson",
    select = TRUE, weights_column = NULL, data = as.list(d),
    mgcv_fit_seconds = as.numeric(elapsed),
    summary = list(
      n = as.integer(ssum$n), scale = as.numeric(ssum$scale),
      dev_expl = as.numeric(ssum$dev.expl), reml = as.numeric(m$gcv.ubre),
      deviance = as.numeric(m$deviance), null_deviance = as.numeric(m$null.deviance),
      edf_s = as.numeric(ssum$s.table[, "edf"]), sp = as.numeric(m$sp)),
    mgcv = list(
      eta = as.numeric(m$linear.predictors), edf_total = as.numeric(sum(m$edf)),
      edf_by_smooth = vapply(sm, function(s) sum(m$edf[s$first.para:s$last.para]), numeric(1)),
      labels = vapply(sm, function(s) s$label, character(1)),
      bs_dim = vapply(sm, function(s) as.integer(
        if (!is.null(s$bs.dim)) s$bs.dim else prod(vapply(s$margin, function(q) q$bs.dim, numeric(1)))),
        integer(1)),
      ncoef = vapply(sm, function(s) as.integer(s$last.para - s$first.para + 1L), integer(1)),
      nsdf = as.integer(m$nsdf), sp = as.numeric(m$sp), scale = as.numeric(m$scale),
      levels = setNames(lapply(fac_names, function(nm) levels(m$model[[nm]])), fac_names)))
  out <- list(schema_version = 1L, mgcv_version = as.character(packageVersion("mgcv")),
              r_version = R.version.string, n_sp = length(m$sp), cells = list(cell))
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE, null = "null")
  cat(sprintf("Wrote %s -- n=%d, %d smoothing parameters, mgcv fit %.2f s, mgcv %s\n",
              out_path, n, length(m$sp), elapsed, as.character(packageVersion("mgcv"))))
  invisible(NULL)
}

status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
  error = function(e) { message("gam_target_size_probe.R FAILED: ", conditionMessage(e)); 1L })
quit(status = status)
