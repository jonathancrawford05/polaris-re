#!/usr/bin/env Rscript
#
# gam_real_data_trial.R -- Slice R2 (docs/PLAN_gam_real_data_readiness.md, ADR-259): the mgcv side
# of the ILEC trial. Runs INSIDE the pinned oracle image on the maintainer's machine (tier L).
#
# Reads ONE cell file written by scripts/gam_real_data_trial.py and fits the SAME formula string
# with mgcv::gam(method = "REML"). It reads nothing Polaris produced except the cells, the formula
# string, the family, the weights column name, the select flag and the factor level ORDER (the
# shared recipe; level order does not change eta or edf, it only removes locale collation from
# the comparison). Polaris reads nothing mgcv produced until the comparison.
#
# The output is a SCRATCH file: it carries per-row eta and se.fit, so it is data-derived and must
# stay on the maintainer's machine (never committed). The Python side reduces it to scalars.
#
# USAGE: Rscript scripts/gam_real_data_trial.R <cells.csv> <spec.json> <out.json>
#   spec.json: {formula, family, weights, select, factors: {name: [levels in order]},
#               repeats, budget_s}
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

`%||%` <- function(a, b) if (is.null(a)) b else a

# Everything compared, from a fitted gam object. Sourced by the CI rehearsal probe too, so the
# extraction that produced the real-data numbers is the one the tier-3 rehearsal exercised.
extract_mgcv <- function(m, times) {
  pr <- predict(m, se.fit = TRUE, type = "link")
  sm <- lapply(m$smooth, function(s) {
    idx <- s$first.para:s$last.para
    sp_idx <- if (length(s$sp) && !is.null(s$first.sp)) s$first.sp:s$last.sp else integer(0)
    list(label = s$label, edf = sum(m$edf[idx]), df = length(idx),
         log10_sp = as.numeric(log10(m$sp[sp_idx])))
  })
  # R heap high-water mark (gc 'max used', Mb) -- NOT process RSS; labelled as such in the runbook
  mem_mb <- tryCatch(as.numeric(sum(gc()[, 6])), error = function(e) NA_real_)
  list(
    r_version = R.version.string, mgcv_version = as.character(packageVersion("mgcv")),
    eta = as.numeric(m$linear.predictors), se_fit = as.numeric(pr$se.fit),
    edf_total = sum(m$edf), smooths = sm, reml = as.numeric(m$gcv.ubre),
    scale = as.numeric(m$scale),
    converged = isTRUE(m$converged) && isTRUE(m$mgcv.conv$fully.converged %||% TRUE),
    outer_iter = if (!is.null(m$outer.info$iter)) m$outer.info$iter else NA_integer_,
    n_coef = length(coef(m)), n_penalties = length(m$sp),
    fit_seconds = times, peak_mb_gc = mem_mb)
}

main <- function(argv) {
  stopifnot(length(argv) == 3)
  spec <- jsonlite::read_json(argv[[2]], simplifyVector = FALSE)
  d <- utils::read.csv(argv[[1]], stringsAsFactors = FALSE)
  for (nm in names(spec$factors))
    d[[nm]] <- factor(d[[nm]], levels = unlist(spec$factors[[nm]]))
  fam <- eval(parse(text = paste0(spec$family, if (grepl("\\(", spec$family)) "" else "()")))
  w <- if (is.null(spec$weights)) NULL else d[[spec$weights]]
  fit_once <- function()
    mgcv::gam(as.formula(spec$formula), data = d, family = fam, weights = w,
              method = "REML", select = isTRUE(spec$select))

  times <- numeric(0); m <- NULL
  while (length(times) < spec$repeats && (length(times) == 0 || sum(times) < spec$budget_s)) {
    t <- system.time(m <- fit_once())[["elapsed"]]
    times <- c(times, t)
  }
  out <- extract_mgcv(m, times)
  jsonlite::write_json(out, argv[[3]], digits = NA, auto_unbox = TRUE, null = "null", na = "null")
  cat(sprintf("Wrote %s (%d fits, best %.2f s, mgcv %s)\n", argv[[3]], length(times),
              min(times), as.character(packageVersion("mgcv"))))
}
if (sys.nframe() == 0L) {   # run as a script; sourced by the rehearsal probe it only defines
  status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
    error = function(e) { message("gam_real_data_trial.R FAILED: ", conditionMessage(e)); 1L })
  quit(status = status)
}
