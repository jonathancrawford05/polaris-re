#!/usr/bin/env Rscript
# =============================================================================
# Slice: dEta/dRho and dw/dRho from Wood (2011) — the R side.
# =============================================================================
# docs/WORK_ORDER_dw_drho_wood2011.md. This probe produces the INDEPENDENT
# right-hand operand for the parity claim: mgcv's OWN eta and working weights,
# refitted at smoothing parameters perturbed one block at a time, so the Python
# side can central-difference them and compare against its analytic Wood (2011)
# derivative.
#
# WHAT MAKES THIS INDEPENDENT (ADR-193). This script never reads any Python
# output. It builds its own deterministic design (set.seed, ADR-074), fits mgcv
# through paraPen at a fully-supplied sp so no optimisation runs, and exports
# eta and m$weights at the base point and at rho +/- h per block. The Python
# producer reads only the shared recipe (X, S, y, weights, the rho grid) and
# computes its derivative analytically. Neither side sees the other's
# derivative, so the comparison can genuinely disagree.
#
# WHY eta AND NOT coef. PLAN Anchor 2: mgcv reparameterises internally, so beta
# is basis-dependent and eta is not. d(eta)/d(rho) is the basis-invariant image
# of d(beta)/d(rho) and is what any downstream use actually needs. Coefficients
# are deliberately NOT exported as a compared quantity.
#
# THE STEP SIZE IS DERIVED, NOT TUNED (Anchor 8). Central differences balance
# O(h^2) truncation against O(eps/h) round-off at h ~ eps^(1/3) ~ 6e-6 in rho.
# h = 1e-4 sits comfortably above the round-off floor with truncation ~1e-8.
# The script emits BOTH h and h/2 so the Python side can verify the residual
# falls ~4x — the evidence that any disagreement is truncation-limited rather
# than real.
#
# DIAGNOSTIC, wired continue-on-error, same contract as the epic's other probes.
# =============================================================================
suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_deriv_probe.json"

  set.seed(20260822) # ADR-074: pinned, never the wall clock.
  n <- 200
  p <- 6

  # A shared, deterministic design this script builds itself — never read from
  # a Python payload.
  x1 <- sort(runif(n, -2, 2))
  X <- cbind(1, x1, x1^2, sin(x1), cos(x1), x1^3)
  colnames(X) <- paste0("X", 1:p)

  # Two independently-scaled penalty blocks with DISJOINT column supports, the
  # same structure ADR-196's fixture uses (and the reason its section 3.1
  # stability machinery was inapplicable there).
  D <- diff(diag(p), differences = 2)
  S1 <- crossprod(D)
  S2 <- matrix(0, p, p); S2[2, 2] <- 1

  base_rho <- c(1.0, 0.5) # natural log of lambda, matching Wood's rho
  # Two REGIMES, deliberately, because one h cannot demonstrate both things.
  #   1e-2 and 5e-3 — TRUNCATION-dominated. Here the O(h^2) law is visible and
  #     halving h must cut the residual ~4x. That is what shows the analytic
  #     derivative is the h -> 0 limit of mgcv's own behaviour rather than merely
  #     close to it at one step size.
  #   1e-4 — ROUND-OFF-dominated, and the tightest agreement available. At this h
  #     the truncation error is already below the noise floor of differencing two
  #     separately-converged mgcv fits, so shrinking h further makes the REFERENCE
  #     worse, not better. Measured: at 5e-5 the residual grows, ratio ~0.6.
  # Reporting only the small h would overstate what the Richardson check proves;
  # reporting only the large h would understate the agreement.
  h_values <- c(1e-2, 5e-3, 1e-4)

  fit_at <- function(rho, family, y, wts) {
    sp <- exp(rho)
    m <- gam(y ~ 0 + X,
             family = family,
             weights = wts,
             paraPen = list(X = list(S1, S2, sp = sp)),
             method = "REML",
             control = gam.control(scalePenalty = FALSE))
    list(eta = as.numeric(predict(m, type = "link")),
         w   = as.numeric(m$weights))
  }

  make_case <- function(label, family, y, wts) {
    base <- fit_at(base_rho, family, y, wts)
    perturbed <- list()
    for (hi in seq_along(h_values)) {
      h <- h_values[hi]
      for (j in seq_along(base_rho)) {
        rp <- base_rho; rp[j] <- rp[j] + h
        rm <- base_rho; rm[j] <- rm[j] - h
        up <- fit_at(rp, family, y, wts)
        dn <- fit_at(rm, family, y, wts)
        key <- sprintf("h%d_block%d", hi, j)
        perturbed[[key]] <- list(
          h = h, block = j,
          eta_plus = up$eta, eta_minus = dn$eta,
          w_plus = up$w, w_minus = dn$w
        )
      }
    }
    list(
      label = label,
      family = family$family, link = family$link,
      eta = base$eta, w = base$w,
      y = as.numeric(y),
      prior_weights = as.numeric(wts),
      perturbed = perturbed
    )
  }

  # Poisson-log: canonical, alpha == 1, Fisher and Newton coincide.
  eta_true <- 0.4 * x1 - 0.2 * x1^2
  y_pois <- rpois(n, exp(eta_true))
  case_pois <- make_case("poisson-log", poisson(link = "log"), y_pois, rep(1, n))

  # Binomial-logit: canonical. Proportion response with prior weights, the
  # target formula's own idiom (PLAN Anchor 5).
  wts_bin <- rep(25, n)
  mu_true <- 1 / (1 + exp(-eta_true))
  y_logit <- rbinom(n, size = 25, prob = mu_true) / 25
  case_logit <- make_case("binomial-logit", binomial(link = "logit"), y_logit, wts_bin)

  # Binomial-cloglog: NON-canonical — the cell where alpha != 1 and the
  # observed/expected Hessian distinction is measurable. The registered
  # prediction (work order section 3) is about this cell specifically.
  mu_cll <- 1 - exp(-exp(eta_true))
  y_cll <- rbinom(n, size = 25, prob = mu_cll) / 25
  case_cll <- make_case("binomial-cloglog", binomial(link = "cloglog"), y_cll, wts_bin)

  cases <- list(case_pois, case_logit, case_cll)
  names(cases) <- vapply(cases, function(c) c$label, character(1))

  out <- list(
    schema_version = 1L,
    r_version = R.version.string,
    mgcv_version = as.character(packageVersion("mgcv")),
    n = n, p = p,
    design = X,
    penalties = list(S1, S2),
    base_rho = base_rho,
    h_values = h_values,
    cases = cases
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE,
                       null = "null", matrix = "rowmajor")
  cat(sprintf("Wrote %s — %d case(s), mgcv %s\n",
              out_path, length(cases), as.character(packageVersion("mgcv"))))
}

tryCatch(main(commandArgs(trailingOnly = TRUE)),
  error = function(e) {
    message("gam_deriv_probe.R failed: ", conditionMessage(e))
    quit(status = 1)
  }
)
