#!/usr/bin/env Rscript
#
# bam_discrete_probe.R -- Slice R3, first step (docs/CONTINUATION_gam_real_data_readiness.md).
# A MEASUREMENT, not a claim: it fits ONE cell with either
#   gam(method = "REML")                      -- the current oracle, or
#   bam(method = "fREML", discrete = TRUE)    -- the R3-bam candidate,
# with the same formula, family, weights and select flag, and writes eta, se.fit, edf and
# timing. Run each method in its OWN process (scripts/bam_discrete_probe_run.sh) so the
# wrapper can read a clean process peak RSS. Output is scratch: per-row eta lives in it, so it
# stays on the maintainer's machine and is never committed.
#
# USAGE: Rscript scripts/bam_discrete_probe.R <cells.csv> <spec.json> <gam|bam> <out.json>
#   cells.csv and spec.json are written by scripts/gam_real_data_trial.py run-cell, one
#   directory per cell under the work directory (e.g. $WORK/T1_mid/).
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

`%||%` <- function(a, b) if (is.null(a)) b else a

main <- function(argv) {
  stopifnot(length(argv) == 4)
  cells_path <- argv[[1]]; spec_path <- argv[[2]]; method <- argv[[3]]; out_path <- argv[[4]]
  if (!method %in% c("gam", "bam")) stop("method must be 'gam' or 'bam'")

  spec <- jsonlite::read_json(spec_path, simplifyVector = FALSE)
  d <- utils::read.csv(cells_path, stringsAsFactors = FALSE)
  for (nm in names(spec$factors))
    d[[nm]] <- factor(d[[nm]], levels = unlist(spec$factors[[nm]]))
  fam <- eval(parse(text = paste0(spec$family, if (grepl("\\(", spec$family)) "" else "()")))
  w <- if (is.null(spec$weights)) NULL else d[[spec$weights]]
  f <- as.formula(spec$formula)
  sel <- isTRUE(spec$select)

  t0 <- proc.time()[["elapsed"]]
  m <- if (method == "gam") {
    mgcv::gam(f, data = d, family = fam, weights = w, method = "REML", select = sel)
  } else {
    mgcv::bam(f, data = d, family = fam, weights = w, method = "fREML",
              discrete = TRUE, select = sel)
  }
  elapsed <- proc.time()[["elapsed"]] - t0

  pr <- predict(m, se.fit = TRUE, type = "link")
  smooths <- lapply(m$smooth, function(s) {
    idx <- s$first.para:s$last.para
    list(label = s$label, edf = sum(m$edf[idx]))
  })
  out <- list(
    method = method, mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string, elapsed_s = elapsed,
    n_rows = nrow(d), n_coef = length(coef(m)),
    eta = as.numeric(m$linear.predictors), se_fit = as.numeric(pr$se.fit),
    edf_total = sum(m$edf), smooths = smooths,
    converged = if (is.null(m$converged)) NA else isTRUE(m$converged)
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE,
                       null = "null", na = "null")
  cat(sprintf("%s: %.1f s, edf_total %.3f, wrote %s\n", method, elapsed, out$edf_total, out_path))
}

if (sys.nframe() == 0L) main(commandArgs(trailingOnly = TRUE))
