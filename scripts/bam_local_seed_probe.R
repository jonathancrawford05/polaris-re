#!/usr/bin/env Rscript
#
# bam_local_seed_probe.R -- Slice R3 Stage B, MAINTAINER-RUN (real cells, tier L).
#
# Fits bam(method="fREML", discrete=TRUE) on ONE trial cell once per discrete.mf seed
# (mgcv's own 8547 first, then the others given on the command line). The seed is the
# constant in `temp.seed(8547)` inside mgcv:::discrete.mf (the sample() that pads each
# variable's unique values); it is patched in a namespace COPY and restored on exit.
# Per-row eta/se.fit go to a SCRATCH json that stays on the maintainer's machine; the
# orchestrator (bam_local_run.py) reduces them to scalars.
#
# USAGE: Rscript scripts/bam_local_seed_probe.R <cells.csv> <spec.json> <out.json> [seed ...]
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

orig <- get("discrete.mf", asNamespace("mgcv"))
replace_const <- function(e, from, to) {
  if (is.numeric(e) && length(e) == 1 && e == from) return(to)
  if (is.call(e)) {
    for (i in seq_along(e)) if (!is.null(e[[i]])) e[[i]] <- replace_const(e[[i]], from, to)
    return(e)
  }
  e
}
set_seed <- function(seed) {
  f <- orig; body(f) <- replace_const(body(orig), 8547, seed)
  assignInNamespace("discrete.mf", f, ns = "mgcv")
}

main <- function(argv) {
  stopifnot(length(argv) >= 3)
  seeds <- if (length(argv) > 3) as.numeric(argv[-(1:3)]) else c(1, 2, 3, 4, 5, 6)
  seeds <- c(8547, seeds)
  spec <- jsonlite::read_json(argv[[2]], simplifyVector = FALSE)
  d <- utils::read.csv(argv[[1]], stringsAsFactors = FALSE)
  for (nm in names(spec$factors)) d[[nm]] <- factor(d[[nm]], levels = unlist(spec$factors[[nm]]))
  fam <- eval(parse(text = paste0(spec$family, if (grepl("\\(", spec$family)) "" else "()")))
  w <- if (is.null(spec$weights)) NULL else d[[spec$weights]]
  f <- as.formula(spec$formula)
  on.exit(assignInNamespace("discrete.mf", orig, ns = "mgcv"))
  fits <- list()
  for (sd in seeds) {
    set_seed(sd)
    t0 <- proc.time()[["elapsed"]]
    m <- mgcv::bam(f, data = d, family = fam, weights = w, method = "fREML", discrete = TRUE,
                   select = isTRUE(spec$select))
    el <- proc.time()[["elapsed"]] - t0
    pr <- predict(m, se.fit = TRUE, type = "link")
    fits[[length(fits) + 1]] <- list(seed = sd, elapsed_s = el, iter = m$iter,
      converged = isTRUE(m$mgcv.conv), edf_total = sum(m$edf), n_coef = length(coef(m)),
      eta = as.numeric(m$linear.predictors), se_fit = as.numeric(pr$se.fit))
    cat(sprintf("seed %g: %.1f s, %d iterations, edf_total %.3f\n", sd, el, m$iter, sum(m$edf)))
  }
  jsonlite::write_json(list(mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string, n_rows = nrow(d), fits = fits),
    argv[[3]], digits = I(17), auto_unbox = TRUE, null = "null", na = "null")
}
if (sys.nframe() == 0L) main(commandArgs(trailingOnly = TRUE))
