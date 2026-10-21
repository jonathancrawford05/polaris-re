#!/usr/bin/env Rscript
#
# gam_tp_probe.R -- Slice R4 (docs/PLAN_gam_real_data_readiness.md, ADR-261), Stage A:
# mgcv's side of the thin-plate (bs = "tp") basis comparison.
#
# Each case is a covariate vector x and a basis dimension k -- the shared RECIPE. This
# script builds smoothCon(s(x, bs = "tp", k = k), absorb.cons = TRUE) and exports mgcv's own
# X, S and rank. Polaris receives only x and k (polaris_re.analytics.gam_basis_tp.tp_basis,
# whose signature takes no mgcv output) and builds its own. Nothing here is read by Polaris
# except what it is compared against (scripts/gam_tp_compare.py).
#
# WHY A "vs_exact" COLUMN. mgcv truncates the eigendecomposition of its kernel matrix E with
# a Lanczos routine, which is not exact to machine precision on every case. To make the
# acceptance tolerance DERIVED rather than chosen, this script also measures how far mgcv's
# own range space is from the exact top-k-by-|lambda| eigenspace of E, computed here with
# R's eigen() on the SAME unique shifted covariate values mgcv used (smooth$Xu). That is a
# measurement of the REFERENCE against an exact solver (REFERENCE_INTERNAL), not a Polaris
# quantity: it only sets how much slack an honest comparison is allowed
# (gam_basis_tp.derived_tolerance).
#
# REQUIREMENTS: R with mgcv and jsonlite.   USAGE: Rscript scripts/gam_tp_probe.R [out.json]

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

M <- 2L  # null-space dimension of the m = 2, d = 1 penalty

probe <- function(name, x, k) {
  dat <- data.frame(x = x)
  sm_unc <- smoothCon(s(x, bs = "tp", k = k), dat, absorb.cons = FALSE)[[1]]
  sm_con <- smoothCon(s(x, bs = "tp", k = k), dat, absorb.cons = TRUE)[[1]]
  xu <- as.numeric(sm_unc$Xu[, 1])
  nu <- length(xu)
  xs <- x - as.numeric(sm_unc$shift)
  kern <- function(a, b) (gamma(-1.5) / (2^4 * sqrt(pi))) * abs(outer(a, b, "-"))^3
  # the EXACT recipe, built here with R's eigen() on mgcv's own Xu: top-k eigenpairs of E by
  # |lambda|, then the constraint T'delta = 0, then the data-row design and the sum-to-zero
  # constraint -- the same space gam_basis_tp compares, so the distance is read where it matters
  ev <- eigen(kern(xu, xu), symmetric = TRUE)
  Uk <- ev$vectors[, order(-abs(ev$values))[seq_len(k)], drop = FALSE]
  Tm <- cbind(1, xu)
  Zr <- qr.Q(qr(t(Uk) %*% Tm), complete = TRUE)[, 3:k, drop = FALSE]
  Xex <- cbind(kern(xs, xu) %*% (Uk %*% Zr), 1, xs)
  Cm <- matrix(colMeans(Xex), ncol = 1)
  Xexc <- Xex %*% qr.Q(qr(Cm), complete = TRUE)[, -1, drop = FALSE]
  qa <- qr.Q(qr(Xexc)); qb <- qr.Q(qr(sm_con$X))
  vs_exact <- max(svd(qb - qa %*% (t(qa) %*% qb), nu = 0, nv = 0)$d)
  list(
    name = name, k = as.integer(k), x = as.numeric(x),
    mgcv = list(
      X = unname(sm_con$X), S = unname(sm_con$S[[1]]), rank = as.integer(sm_con$rank),
      n_unique = as.integer(nu), vs_exact = as.numeric(vs_exact),
      unconstrained_ncol = ncol(sm_unc$X)
    )
  )
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_tp_probe.json"
  cases <- list()
  add <- function(name, x, k) cases[[length(cases) + 1]] <<- probe(name, x, k)

  set.seed(20261021)
  add("random_n80_k5", round(runif(80, 20, 90)), 5)
  add("random_n80_k10", round(runif(80, 20, 90)), 10)
  add("random_n300_k10_continuous", runif(300, 0, 10), 10)
  add("random_n1000_k20_continuous", rnorm(1000), 20)
  add("minimum_k3", runif(60, 0, 1), 3)
  add("k_equals_nu", c(0.3, 1.1, 2.0, 2.2, 4.1, 5.0, 5.9, 7.3), 8)
  # the ILEC covariates are integer grids with heavy ties
  add("age_0_120_k13", rep(0:120, each = 3), 13)
  add("age_18_100_k10", rep(18:100, 3), 10)
  add("duration_1_26_k6", rep(1:26, 40), 6)
  add("duration_1_26_k10", rep(1:26, 40), 10)
  add("year_2012_2019_k5", rep(2012:2019, 50), 5)
  add("year_2012_2019_k7", rep(2012:2019, 50), 7)
  add("grid_30_k10", seq(0, 1, length.out = 30), 10)
  add("grid_61_k20", seq(0, 3, length.out = 61), 20)
  # many rows, few distinct values (n > 2000 but nu <= 2000: mgcv does NOT subsample)
  add("n5000_ties_nu100_k12", sample(seq(0, 99), 5000, TRUE), 12)
  # large nu, both below max.knots = 2000
  add("nu1500_k12", sort(runif(1500, 0, 100)), 12)
  add("nu2000_k15", sort(runif(2000, 0, 100)), 15)
  write(toJSON(list(cases = cases, r_version = R.version.string,
                    mgcv_version = as.character(packageVersion("mgcv"))),
               digits = NA, auto_unbox = TRUE), out_path)
  cat("wrote", out_path, "with", length(cases), "cases\n")
}

main(commandArgs(trailingOnly = TRUE))
