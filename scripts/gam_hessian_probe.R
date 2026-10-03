#!/usr/bin/env Rscript
# =============================================================================
# Outer-solver epic Slice 2 — mgcv's OWN outer Hessian of the REML criterion.
# =============================================================================
# Produces the REFERENCE operand for the exact-Hessian comparison
# (polaris_re.analytics.gam_hessian_conformance). Five cases on one design,
# covering every family/link this engine defines: poisson-log,
# binomial-logit and binomial-cloglog (NON-canonical: alpha != 1, so the
# observed/expected Hessian distinction is live) at KNOWN scale, and
# quasipoisson-log and gaussian-identity at FREE scale.
#
# WHAT IS SHARED RECIPE AND WHAT IS REFERENCE (ADR-193).
#   Recipe, exported for the Python producer: the design X, the penalty blocks
#   S_j, y, prior weights, and mgcv's SELECTED sp — the latter only as the POINT
#   AT WHICH BOTH SIDES EVALUATE the Hessian (VERIFICATION_STANDARD.md 2.1: a
#   Hessian is a function of rho, so "compared at which rho" must be fixed).
#   Reference, never read by the Python producer: m$outer.info$hess and
#   m$scale. The Python side computes its own penalized fit at that sp and its
#   own second derivative of its own criterion.
#
# FREE-SCALE LAYOUT. For an estimated scale mgcv appends log(phi) to the search
# vector, so outer.info$hess is (M+1) x (M+1) over (log sp_1..M, log phi).
# `hess_dim` is exported so the Python side reads the layout from the payload
# rather than assuming it.
#
# DIAGNOSTIC, continue-on-error, same contract as the epic's other probes.
# REQUIREMENTS: R with mgcv and jsonlite.
# =============================================================================
suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_hessian_probe.json"

  set.seed(20261004) # ADR-074: pinned, never the wall clock.
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
    hess <- m$outer.info$hess
    if (is.null(hess)) stop(sprintf("Case '%s' exposed no outer.info$hess.", label))
    list(
      label = label,
      family = family$family, link = family$link,
      scale_estimated = !(family$family %in% c("poisson", "binomial")),
      y = as.numeric(y),
      prior_weights = as.numeric(wts),
      # RECIPE: the point of evaluation, mgcv's own selection.
      selected_sp = as.numeric(m$sp),
      # REFERENCE: never read by the Python producer.
      outer_hessian = as.numeric(hess),
      hess_dim = nrow(hess),
      outer_gradient = as.numeric(m$outer.info$grad),
      scale = as.numeric(m$sig2),
      outer_converged = as.character(m$outer.info$conv),
      outer_iter = as.integer(m$outer.info$iter)
    )
  }

  eta_true <- 0.8 * sin(1.5 * x1) - 0.3 * x1
  cases <- list(
    make_case("poisson-log", poisson(link = "log"),
              rpois(n, exp(eta_true)), rep(1, n)),
    make_case("binomial-logit", binomial(link = "logit"),
              rbinom(n, 30, 1 / (1 + exp(-eta_true))) / 30, rep(30, n)),
    make_case("binomial-cloglog", binomial(link = "cloglog"),
              rbinom(n, 20, 1 - exp(-exp(eta_true))) / 20, rep(20, n)),
    make_case("quasipoisson-log", quasipoisson(link = "log"),
              rpois(n, exp(eta_true)), rep(1, n)),
    make_case("gaussian-identity", gaussian(link = "identity"),
              eta_true + rnorm(n, sd = 0.4), rep(1, n))
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
  write_json(out, out_path, digits = NA, auto_unbox = TRUE, matrix = "rowmajor")
  cat(sprintf("Wrote %s (mgcv %s, %s)\n", out_path, out$mgcv_version, out$r_version))
  for (c in cases) {
    cat(sprintf("  %-18s sp=(%.4g, %.4g)  hess %dx%d  conv=%s\n", c$label,
                c$selected_sp[1], c$selected_sp[2], c$hess_dim, c$hess_dim, c$outer_converged))
  }
}

main(commandArgs(trailingOnly = TRUE))
