#!/usr/bin/env Rscript
# =============================================================================
# Level 4: mgcv's vcov(unconditional = TRUE) — the R side.
# =============================================================================
# Wood, Pya & Saefken (2016) eq. (7). ADR-190 measured that Vc != Vb + J Vrho J'
# and re-scoped the level-4 blocker to "implement the fuller correction". This
# probe produces the reference operand for that: mgcv's OWN Vb and Vc at its OWN
# free-sp selection.
#
# WHY FREE sp, AND WHY THAT IS NOT A PROBLEM HERE. mgcv forms Vc only when the
# smoothing parameters were estimated — there is no Vc at fixed sp (RUNBOOK level
# 4's own stated limitation). So the fit must be free-sp. To stop that turning
# into a lambda disagreement rather than a correction comparison, this script
# also exports the sp mgcv SELECTED, and the Python side refits at that same
# lambda. Both sides then compute their own Vb, Vrho, J and correction over a
# shared (X, S, y, weights, lambda) — which is shared RECIPE, not an answer.
#
# WHAT IS AND IS NOT SHARED. Exported as recipe: X, S_j, y, prior weights, and
# mgcv's selected sp. Exported as the REFERENCE operand, never read by the Python
# producer: vcov(m) and vcov(m, unconditional = TRUE). The Python side computes
# its own Vb rather than reading mgcv's, so the inflation ratio each side reports
# is its own throughout.
#
# DIAGNOSTIC, continue-on-error, same contract as the epic's other probes.
# =============================================================================
suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_vc_probe.json"

  set.seed(20260822) # ADR-074: pinned, never the wall clock.
  n <- 300
  p <- 8

  x1 <- sort(runif(n, -2, 2))
  X <- cbind(1, x1, x1^2, x1^3, sin(x1), cos(x1), sin(2 * x1), cos(2 * x1))
  colnames(X) <- paste0("X", 1:p)

  D <- diff(diag(p), differences = 2)
  S1 <- crossprod(D)
  S2 <- matrix(0, p, p); S2[2, 2] <- 1

  make_case <- function(label, family, y, wts) {
    m <- gam(y ~ 0 + X,
             family = family, weights = wts,
             paraPen = list(X = list(S1, S2)),
             method = "REML",
             control = gam.control(scalePenalty = FALSE))
    vb <- vcov(m)
    vc <- vcov(m, unconditional = TRUE)
    list(
      label = label,
      family = family$family, link = family$link,
      y = as.numeric(y),
      prior_weights = as.numeric(wts),
      # mgcv's OWN selection — shared recipe, so both sides work at one lambda.
      selected_sp = as.numeric(m$sp),
      # mgcv's OWN outer Hessian (of its REML criterion w.r.t. rho) and the Vrho
      # it implies. Exported to LOCALIZE a disagreement, exactly as ADR-190's
      # ks_formula_probe.R does: substituting it for ours separates "our Vrho is
      # wrong" from "our V'' is wrong", which no end-to-end number can.
      outer_hessian = if (is.null(m$outer.info$hess)) NULL else as.numeric(m$outer.info$hess),
      # REFERENCE operand. Never read by the Python producer.
      vcov_diag = as.numeric(diag(vb)),
      vcov_unconditional_diag = as.numeric(diag(vc)),
      # FULL matrices: the scalar inflation ratio averages diagonals and hid a
      # 26.7% element-wise residual behind a 0.39% headline during this slice.
      vcov_full = as.numeric(vb),
      vcov_unconditional_full = as.numeric(vc),
      mgcv_inflation = as.numeric(mean(diag(vc)) / mean(diag(vb))),
      edf_total = sum(m$edf),
      scale = as.numeric(m$sig2)
    )
  }

  eta_true <- 0.8 * sin(1.5 * x1) - 0.3 * x1
  cases <- list(
    make_case("poisson-log", poisson(link = "log"),
              rpois(n, exp(eta_true)), rep(1, n)),
    make_case("binomial-logit", binomial(link = "logit"),
              rbinom(n, 30, 1 / (1 + exp(-eta_true))) / 30, rep(30, n)),
    # Non-canonical link: alpha != 1, so the observed/expected Hessian
    # distinction (ADR-201) is live here as it is not on the two above.
    make_case("binomial-cloglog", binomial(link = "cloglog"),
              rbinom(n, 20, 1 - exp(-exp(eta_true))) / 20, rep(20, n))
  )
  names(cases) <- vapply(cases, function(c) c$label, character(1))

  out <- list(
    schema_version = 1L,
    r_version = R.version.string,
    mgcv_version = as.character(packageVersion("mgcv")),
    n = n, p = p,
    design = X,
    penalties = list(S1, S2),
    cases = cases
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE,
                       null = "null", matrix = "rowmajor")
  cat(sprintf("Wrote %s — %d case(s), mgcv %s\n",
              out_path, length(cases), as.character(packageVersion("mgcv"))))
  for (c in cases) {
    cat(sprintf("  %-16s sp=(%.4g, %.4g)  mgcv inflation=%.4fx  edf=%.3f\n",
                c$label, c$selected_sp[1], c$selected_sp[2],
                c$mgcv_inflation, c$edf_total))
  }
}

tryCatch(main(commandArgs(trailingOnly = TRUE)),
  error = function(e) {
    message("gam_vc_probe.R failed: ", conditionMessage(e))
    quit(status = 1)
  }
)
