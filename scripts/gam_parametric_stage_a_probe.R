#!/usr/bin/env Rscript
#
# gam_parametric_stage_a_probe.R -- capability ladder rung L4 (unpenalized
# parametric block), Stage A. (docs/PLAN_mgcv_capability_ladder.md slice 5.)
#
# WHAT THIS PROBES
# ------------------
# mgcv's own unpenalized parametric block for `FaceSize + Smoke +
# FaceSize:Smoke` -- the target formula's own opening terms
# (docs/MGCV_FEATURE_COVERAGE.md §1) -- via R's ordinary formula/contrast
# machinery, `model.matrix()`, which is exactly what `gam()` itself calls
# internally to build the parametric block of its own design (mgcv has no
# separate "parametric smooth" construction the way s()/ti() do -- the
# parametric part of a gam formula is built by the SAME model.matrix() call
# an lm()/glm() would use). No fit is needed for this comparison: the
# parametric block's columns do not depend on sp, y, or the smooth part of
# the formula at all.
#
# THE CONVENTION (measured, not guessed -- Anchor 8)
# -----------------------------------------------------
# `model.matrix(~A + B + A:B)` under R's default contr.treatment, measured
# directly on a synthetic 3-level/2-level factor pair before this script (or
# gam_basis_parametric.py) was written:
#
#   > A <- factor(c("a0","a1","a2","a0","a1","a2"), levels=c("a0","a1","a2"))
#   > B <- factor(c("b0","b0","b0","b1","b1","b1"), levels=c("b0","b1"))
#   > colnames(model.matrix(~A + B + A:B, data.frame(A=A,B=B)))
#   [1] "(Intercept)" "Aa1" "Aa2" "Bb1" "Aa1:Bb1" "Aa2:Bb1"
#
# i.e. a factor's own main-effect block drops its first (reference) level and
# keeps one indicator column per remaining level, in level order; an
# interaction block's columns are the outer product of the two factors' own
# main-effect columns, with the FIRST-NAMED factor varying FASTEST.
# `assign` (an attribute of the returned matrix) names which formula term
# each column belongs to (0 = intercept, 1/2/3 = the three terms in formula
# order here), which is what this script uses to split the block by term
# without any column-name parsing.
#
# INDEPENDENCE (ADR-193)
# -------------------------
# The Python side (polaris_re.analytics.gam_basis_parametric.parametric_design)
# builds the SAME columns from the 0-indexed factor-level codes and the level
# counts alone -- never from this script's own X -- matching mgcv's
# convention by construction (the einsum/reshape derivation in the module
# docstring), not by reading it back.
#
# REQUIREMENTS: R with mgcv and jsonlite (mgcv is not actually called for
# fitting here -- only R's own formula/contrast machinery is -- but every
# other probe in this project declares it, so this one does too rather than
# leaving a caller to remember which probes need which package).
# USAGE:  Rscript scripts/gam_parametric_stage_a_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_parametric_stage_a_probe.json"
  set.seed(20260927) # ADR-074: pinned, never the wall clock.

  n <- 40L
  face_levels <- c("Band1", "Band2", "Band3")
  smoke_levels <- c("N", "Y")
  FaceSize <- factor(sample(face_levels, n, replace = TRUE), levels = face_levels)
  Smoke <- factor(sample(smoke_levels, n, replace = TRUE), levels = smoke_levels)
  df <- data.frame(FaceSize = FaceSize, Smoke = Smoke)

  form <- ~ FaceSize + Smoke + FaceSize:Smoke
  mm <- model.matrix(form, data = df)
  a <- attr(mm, "assign")
  term_labels <- attr(terms(form), "term.labels")

  param_terms <- list()
  for (term_index in seq_along(term_labels)) {
    cols <- which(a == term_index)
    block <- mm[, cols, drop = FALSE]
    param_terms[[term_labels[term_index]]] <- list(
      index_start = 0L,
      index_end = ncol(block),
      X = block,
      S = list(),
      rank = list(),
      knots = NULL
    )
  }

  out <- list(
    schema_version = 1L,
    n = n,
    face_levels = face_levels,
    smoke_levels = smoke_levels,
    face_group = as.integer(FaceSize) - 1L,
    smoke_group = as.integer(Smoke) - 1L,
    term_labels = term_labels,
    param_terms = param_terms,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf(
    "Wrote %s -- n=%d, terms=%s\n", out_path, n, paste(term_labels, collapse = ", ")
  ))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_parametric_stage_a_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
