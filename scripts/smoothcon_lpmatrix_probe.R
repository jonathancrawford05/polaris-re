#!/usr/bin/env Rscript
# =============================================================================
# Slice 1's one named risk, on the authoritative oracle.
# =============================================================================
# docs/PLAN_mgcv_parity_engine.md Anchor 1 / slice 1: `predict(type="lpmatrix")` returns
# a design AFTER mgcv absorbs identifiability constraints and reparameterises;
# `smoothCon()` returns the smooth BEFORE, unless called with `absorb.cons = TRUE`. Which
# of the two Stage A should compare against changes what "our X equals mgcv's X" means,
# and PLAN section 5 risk 1 records a fallback (compare column space and fitted values)
# for the case where neither works as a referent.
#
# The tier-1 finding this probe exists to promote: on a `bs="cr"` term, fit through
# `gam()`, then `smoothCon(..., absorb.cons = TRUE)$X` is BIT-EXACT (max abs diff 0) with
# the corresponding block of `predict(m, type="lpmatrix")`. That is not "neither
# referent works" — it is "the two referents are the same object", because
# `predict.gam` dispatches to `PredictMat` on the smooth object `gam.setup` built with
# `absorb.cons = TRUE`. If true on the pinned oracle, slice 1's risk resolves to a
# decision (`smoothCon(absorb.cons = TRUE)` is Stage A's referent) rather than a
# fallback, and per-term extraction can use `smoothCon()` directly without fitting a
# full model — which is what makes an isolated-term harness possible at all.
#
# WHY THIS IS A COMMITTED SCRIPT AND A CI STEP rather than an argument from tier 1.
# `ROUTINE_MGCV_PARITY.md` SETUP step 2 permits committing only TIER 3 numbers, and this
# finding is specifically the kind tier 1 cannot rule out on its own: whether
# `predict(type="lpmatrix")` is DEFINED to agree with `smoothCon(absorb.cons=TRUE)` is a
# fact about mgcv's own code, and "a version change is not noise, it is different code"
# is the routine's own reason a structural finding needs tier 3 too, not only a numeric
# one. ADR-190's ks_formula_probe.R is the template this follows.
#
# DIAGNOSTIC, NOT A GATE. It has explicit `stop()` paths and can exit non-zero; what
# keeps it from blocking a merge is `continue-on-error: true` on its workflow step, same
# as ks_formula_probe.R. The conformance comparison job is untouched by this file.
# =============================================================================
suppressPackageStartupMessages(library(mgcv))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
out_path <- if (length(args) >= 1) args[1] else "smoothcon_lpmatrix_probe.json"

set.seed(20120101) # ADR-074: pinned, never the wall clock.

probe_one <- function(label, n, k, knots_x = NULL) {
  x <- sort(runif(n, 0, 10))
  y <- sin(x) + rnorm(n, sd = 0.1)
  df <- data.frame(x = x, y = y)

  knots_arg <- if (is.null(knots_x)) NULL else list(x = knots_x)
  sm <- smoothCon(s(x, k = k, bs = "cr"), data = df, knots = knots_arg,
                   absorb.cons = TRUE)[[1]]

  m <- gam(y ~ s(x, k = k, bs = "cr"), data = df, knots = knots_arg)
  Xp <- predict(m, type = "lpmatrix")
  smooth_cols <- grep("^s\\(x\\)", colnames(Xp))
  Xp_smooth <- Xp[, smooth_cols, drop = FALSE]

  if (!identical(dim(Xp_smooth), dim(sm$X))) {
    stop(sprintf(
      "%s: lpmatrix smooth block is %dx%d but smoothCon(absorb.cons=TRUE)$X is %dx%d.",
      label, nrow(Xp_smooth), ncol(Xp_smooth), nrow(sm$X), ncol(sm$X)
    ))
  }
  max_abs_diff_x <- max(abs(Xp_smooth - sm$X))

  # The penalty is our other Stage-A quantity (Anchor 1), so the probe checks it too:
  # gam's fitted smooth object carries S at the same (post-constraint) dimension.
  s_fit <- m$smooth[[1]]$S[[1]]
  max_abs_diff_s <- max(abs(s_fit - sm$S[[1]]))

  eta_gam <- as.vector(Xp %*% coef(m))
  max_abs_diff_eta <- max(abs(eta_gam - m$linear.predictors))

  list(
    label = label, n = n, k = k,
    knots_supplied = !is.null(knots_x),
    dim_x = dim(sm$X), rank = sm$rank,
    max_abs_diff_lpmatrix_vs_smoothcon_x = max_abs_diff_x,
    max_abs_diff_gam_smooth_S_vs_smoothcon_S = max_abs_diff_s,
    max_abs_diff_eta_identity_check = max_abs_diff_eta
  )
}

cases <- list(
  probe_one("default-knots-k8", n = 200, k = 8),
  probe_one("default-knots-k13", n = 400, k = 13),
  probe_one("supplied-knots-k8", n = 200, k = 8,
            knots_x = c(0, 1, 2, 3, 5, 8, 9, 10))
)
names(cases) <- vapply(cases, function(c) c$label, character(1))

for (c in cases) {
  cat(sprintf(
    "%-20s dim %dx%d rank %d | max|lpmatrix - smoothCon(absorb.cons=TRUE)X| = %.3e | max|S diff| = %.3e\n",
    c$label, c$dim_x[1], c$dim_x[2], c$rank,
    c$max_abs_diff_lpmatrix_vs_smoothcon_x, c$max_abs_diff_gam_smooth_S_vs_smoothcon_S
  ))
}

jsonlite::write_json(
  list(
    schema_version = 1L,
    r_version = R.version.string,
    mgcv_version = as.character(packageVersion("mgcv")),
    cases = cases
  ),
  out_path,
  auto_unbox = TRUE, digits = NA, pretty = TRUE
)
cat(sprintf("Wrote %s — %d cases, mgcv %s\n", out_path, length(cases),
            as.character(packageVersion("mgcv"))))
