#!/usr/bin/env Rscript
#
# gam_predict_probe.R -- preview epic Slice P1 (docs/PLAN_gam_parity_preview.md,
# ADR-249): predict at NEW rows, mgcv's side.
#
# WHAT THIS PROBES
# ------------------
# For each of seven cells (one per verified basis family, below) it
#   (1) generates a training sample and fits it with mgcv::gam(method="REML");
#   (2) draws HELD-OUT rows the fit never saw -- one block inside the training
#       range of every numeric covariate, one block BEYOND it;
#   (3) exports mgcv's own predict.gam(m, newdata, ...) on each block:
#         type="lpmatrix"  -- the design mgcv's PredictMat builds at those rows
#         type="link"      -- eta
#         type="response"  -- mu
#       plus the training-row m$linear.predictors, sp and sum(edf).
#
# P2 (ADR-250) adds, per block: predict(se.fit=TRUE) with and without
# unconditional=TRUE, the response-scale se, Xp Vp Xp' and Xp Vc Xp', and m$scale.
#
# Polaris never reads any of those outputs when it fits and predicts (the
# recipe it takes -- train data, y, newdata COVARIATES -- is the first block of
# keys below; everything under "mgcv" is the comparand). See
# polaris_re.analytics.gam_predict_conformance for the declared claim.
#
# THE CELLS (factor columns are exported as 0-indexed integer codes,
# as.integer(f) - 1L, the convention every other probe here uses)
#   gaussian_cr_by_ti      s(x) + s(x,by=w) + ti(x,z), default knots
#   gaussian_factor_by     s(x) + s(x,by=f)            (factor by)
#   gaussian_parametric    A + B + A:B + s(x)
#   quasipoisson_cr_re_ti  s(x) + s(f,bs="re") + ti(x,z)       (free scale, log)
#   binomial_cr            s(x) + s(z)                         (logit)
#   poisson_offset         offset(log(expo)) + s(x)            (log, with offset)
#   poisson_hgam           offset(off) + s(age) + s(year) + ti(age,year) + s(dur)
#                          (the four-term ANOVA-shaped HGAM, log link; carried
#                          from P1 and added in the P2 session)
#   gaussian_select        s(x)+s(z)+s(w), select=TRUE, w is pure noise (plateau row)
#   gaussian_select_factor_by_main / poisson_select_factor_by_only   select=TRUE + factor by (R1)
#   gaussian_sz            s(f,x,bs="sz",xt=list(bs="cr"))  -- lpmatrix ONLY
#                          (free-sp sz is not verified; no Polaris fit is made)
#
# REQUIREMENTS: R with mgcv and jsonlite.
# USAGE:  Rscript scripts/gam_predict_probe.R [output.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

codes <- function(f) as.integer(f) - 1L

draw_new <- function(train, n_in, n_out, num_cols, fac_levels, rng_seed) {
  set.seed(rng_seed)
  mk <- function(n, outside) {
    out <- list()
    for (nm in names(num_cols)) {
      r <- range(train[[nm]]); w <- diff(r)
      out[[nm]] <- if (outside) {
        # alternate below / above the training range
        sgn <- rep(c(-1, 1), length.out = n)
        r[(sgn > 0) + 1L] + sgn * runif(n, 0.02, 0.15) * w
      } else {
        runif(n, r[1] + 0.01 * w, r[2] - 0.01 * w)
      }
    }
    for (nm in names(fac_levels)) {
      out[[nm]] <- sample(fac_levels[[nm]], n, replace = TRUE)
    }
    as.data.frame(out, stringsAsFactors = FALSE)
  }
  list(inrange = mk(n_in, FALSE), outrange = mk(n_out, TRUE))
}

as_factors <- function(df, fac_levels) {
  for (nm in names(fac_levels)) df[[nm]] <- factor(df[[nm]], levels = fac_levels[[nm]])
  df
}

cell <- function(name, formula, family, train, y_col, num_cols, fac_levels, seed_new,
                 offset_col = NULL, fit = TRUE, offset_range = c(log(20), log(200)),
                 select = FALSE) {
  train <- as_factors(train, fac_levels)
  m <- mgcv::gam(formula, data = train, family = family, method = "REML", select = select)
  nd <- draw_new(train, 60L, 12L, num_cols, fac_levels, seed_new)
  if (!is.null(offset_col)) {
    nd$inrange[[offset_col]] <- runif(60L, offset_range[1], offset_range[2])
    nd$outrange[[offset_col]] <- runif(12L, offset_range[1], offset_range[2])
  }
  block <- function(df) {
    dff <- as_factors(df, fac_levels)
    xp <- predict(m, dff, type = "lpmatrix")
    pl <- predict(m, dff, type = "link", se.fit = TRUE)
    plu <- predict(m, dff, type = "link", se.fit = TRUE, unconditional = TRUE)
    pr <- predict(m, dff, type = "response", se.fit = TRUE)
    out <- list(
      lpmatrix = xp,
      link = as.numeric(predict(m, dff, type = "link")),
      response = as.numeric(predict(m, dff, type = "response")),
      # preview Slice P2 (ADR-250): mgcv's own standard errors and covariance
      # projected onto these rows (Xp Vp Xp'), a basis-independent image of Vp/Vc
      se_link = as.numeric(pl$se.fit),
      se_link_unconditional = as.numeric(plu$se.fit),
      se_response = as.numeric(pr$se.fit),
      cov_proj = xp %*% m$Vp %*% t(xp),
      cov_proj_unconditional = xp %*% m$Vc %*% t(xp)
    )
    out
  }
  enc <- function(df) {
    o <- as.list(df)
    for (nm in names(fac_levels)) o[[nm]] <- codes(factor(df[[nm]], levels = fac_levels[[nm]]))
    o
  }
  encode_train <- function(df) {
    o <- as.list(df)
    for (nm in names(fac_levels)) o[[nm]] <- codes(df[[nm]])
    o
  }
  list(
    name = name,
    family = family$family, link = family$link,
    fit_polaris = fit,
    offset_column = offset_col,
    n_levels = lapply(fac_levels, length),
    train = encode_train(train[, setdiff(names(train), y_col), drop = FALSE]),
    y = as.numeric(train[[y_col]]),
    new_inrange = enc(nd$inrange),
    new_outrange = enc(nd$outrange),
    mgcv = list(
      inrange = block(nd$inrange),
      outrange = block(nd$outrange),
      eta_train = as.numeric(m$linear.predictors),
      scale = as.numeric(m$scale),
      sp = as.numeric(m$sp),
      edf_total = as.numeric(sum(m$edf))
    )
  )
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_predict_probe.json"
  cells <- list()
  lv3 <- c("a", "b", "c"); lv2 <- c("p", "q")

  # 1. gaussian cr + numeric by + ti, default knots (the data's own quantiles)
  set.seed(20261006)
  n <- 400
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), w = runif(n, -2, 2))
  d$y <- sin(d$x) + 0.1 * d$z + 0.3 * d$w * (d$x - 5) / 5 +
    0.2 * sin(d$x / 2) * cos(d$z) + rnorm(n, sd = 0.3)
  cells[[1]] <- cell("gaussian_cr_by_ti",
    y ~ s(x, k = 9, bs = "cr") + s(x, by = w, k = 9, bs = "cr") +
      ti(x, z, k = c(7, 5), bs = "cr"),
    gaussian(), d, "y", list(x = 1, z = 1, w = 1), list(), 101)

  # 2. gaussian factor-by
  set.seed(20261007)
  n <- 450
  d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE))
  shift <- c(a = 0, b = 0.6, c = -0.5)[d$f]
  d$y <- sin(d$x + shift) + rnorm(n, sd = 0.3)
  cells[[2]] <- cell("gaussian_factor_by",
    y ~ s(x, k = 8, bs = "cr") + s(x, by = f, k = 8, bs = "cr"),
    gaussian(), d, "y", list(x = 1), list(f = lv3), 102)

  # 3. gaussian parametric block + cr
  set.seed(20261008)
  n <- 360
  d <- data.frame(x = runif(n, 0, 10), A = sample(lv3, n, TRUE), B = sample(lv2, n, TRUE))
  eff <- c(a = 0, b = 0.5, c = -0.3)[d$A] + c(p = 0, q = 0.4)[d$B] +
    0.3 * (d$A == "c") * (d$B == "q")
  d$y <- eff + cos(d$x / 2) + rnorm(n, sd = 0.3)
  cells[[3]] <- cell("gaussian_parametric",
    y ~ A + B + A:B + s(x, k = 8, bs = "cr"),
    gaussian(), d, "y", list(x = 1), list(A = lv3, B = lv2), 103)

  # 4. quasipoisson cr + re + ti (free scale, log link)
  set.seed(20261009)
  n <- 500
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), f = sample(lv3, n, TRUE))
  lam <- exp(0.4 + 0.3 * sin(d$x / 2) + 0.1 * d$z + c(a = 0, b = 0.3, c = -0.2)[d$f])
  d$y <- rnbinom(n, mu = lam, size = 4)
  cells[[4]] <- cell("quasipoisson_cr_re_ti",
    y ~ s(x, k = 8, bs = "cr") + s(f, bs = "re") + ti(x, z, k = c(6, 5), bs = "cr"),
    quasipoisson(), d, "y", list(x = 1, z = 1), list(f = lv3), 104)

  # 5. binomial logit, two cr smooths
  set.seed(20261010)
  n <- 600
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5))
  p <- plogis(-0.3 + sin(d$x / 2) + 0.2 * (d$z - 2.5))
  d$y <- rbinom(n, 1, p)
  cells[[5]] <- cell("binomial_cr",
    y ~ s(x, k = 8, bs = "cr") + s(z, k = 6, bs = "cr"),
    binomial(), d, "y", list(x = 1, z = 1), list(), 105)

  # 6. poisson with an offset
  set.seed(20261011)
  n <- 450
  d <- data.frame(x = runif(n, 0, 10), expo = runif(n, 20, 200))
  d$y <- rpois(n, d$expo * exp(-3 + 0.4 * sin(d$x / 2)))
  d$off <- log(d$expo)
  cells[[6]] <- cell("poisson_offset",
    y ~ s(x, k = 8, bs = "cr") + offset(off),
    poisson(), d, "y", list(x = 1), list(), 106, offset_col = "off")

  # 7. sz -- lpmatrix only (no Polaris fit)
  set.seed(20261012)
  n <- 400
  d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE))
  d$y <- sin(d$x + c(a = 0, b = 0.5, c = -0.4)[d$f]) + rnorm(n, sd = 0.3)
  cells[[7]] <- cell("gaussian_sz",
    y ~ s(f, x, bs = "sz", k = 8, xt = list(bs = "cr")),
    gaussian(), d, "y", list(x = 1), list(f = lv3), 107, fit = FALSE)

  # 8. the four-term HGAM (poisson/log + offset): s(age)+s(year)+ti(age,year)+s(dur)
  set.seed(20261013)
  n <- 700
  d <- data.frame(age = runif(n, 45, 85), year = runif(n, 2010, 2021),
                  dur = runif(n, 2, 22), expo = runif(n, 200, 4000))
  lrr <- -0.014 * (d$year - 2015) * (1 + 0.012 * (d$age - 65)) +
    0.05 * sin(d$age / 11) - 0.18 * exp(-d$dur / 9)
  q <- 0.0004 + 0.00003 * exp(0.085 * (d$age - 45))
  d$y <- rpois(n, d$expo * q * exp(lrr))
  d$off <- log(d$expo * q)
  cells[[8]] <- cell("poisson_hgam",
    y ~ offset(off) + s(age, k = 7, bs = "cr") + s(year, k = 5, bs = "cr") +
      ti(age, year, k = c(7, 5), bs = "cr") + s(dur, k = 5, bs = "cr"),
    poisson(), d, "y", list(age = 1, year = 1, dur = 1), list(), 108,
    offset_col = "off", offset_range = range(d$off))

  # 9. select=TRUE with a pure-noise smooth: the plateau-block row (PLAN P2 risk)
  set.seed(20261014)
  n <- 400
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), w = runif(n, 0, 1))
  d$y <- sin(d$x) + 0.3 * d$z + rnorm(n, sd = 0.3)
  cells[[9]] <- cell("gaussian_select",
    y ~ s(x, k = 8, bs = "cr") + s(z, k = 6, bs = "cr") + s(w, k = 6, bs = "cr"),
    gaussian(), d, "y", list(x = 1, z = 1, w = 1), list(), 109, select = TRUE)

  # 10-11. Slice R1 (ADR-258): select=TRUE with a factor-by smooth. Vp and Vc se are gated here
  # (no bare smooth beside the by smooth, so the fit is not pivoted; the bare-smooth forms are
  # refused, ADR-258).
  set.seed(20261101)
  n <- 450
  d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE))
  shift <- c(a = 0, b = 0.6, c = -0.5)[d$f]
  d$y <- sin(d$x + shift) + rnorm(n, sd = 0.3)
  cells[[10]] <- cell("gaussian_select_factor_by_main",
    y ~ f + s(x, by = f, k = 8, bs = "cr"),
    gaussian(), d, "y", list(x = 1), list(f = lv3), 110, select = TRUE)

  set.seed(20261102)
  n <- 600
  d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE))
  shift <- c(a = 0, b = 0.6, c = -0.5)[d$f]
  d$y <- rpois(n, exp(0.8 + 0.4 * sin(d$x / 2 + shift)))
  cells[[11]] <- cell("poisson_select_factor_by_only",
    y ~ s(x, by = f, k = 8, bs = "cr"),
    poisson(), d, "y", list(x = 1), list(f = lv3), 111, select = TRUE)

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    cells = cells
  )
  jsonlite::write_json(
    out, out_path,
    digits = NA, auto_unbox = TRUE, null = "null", matrix = "rowmajor"
  )
  cat(sprintf("Wrote %s -- %d cells, mgcv %s\n", out_path, length(cells),
              as.character(packageVersion("mgcv"))))
  invisible(NULL)
}

status <- tryCatch(
  {
    main(commandArgs(trailingOnly = TRUE))
    0L
  },
  error = function(e) {
    message("gam_predict_probe.R FAILED: ", conditionMessage(e))
    1L
  }
)
quit(status = status)
