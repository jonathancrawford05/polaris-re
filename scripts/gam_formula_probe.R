#!/usr/bin/env Rscript
#
# gam_formula_probe.R -- preview epic Slice P3 (docs/PLAN_gam_parity_preview.md,
# ADR-251): the formula front end, mgcv's side.
#
# Each cell is a FORMULA STRING plus a data frame. This script fits it with
# mgcv::gam(as.formula(<string>), ...) and exports mgcv's own outputs; Polaris
# receives the SAME string and the SAME data (factor columns as their string labels,
# exactly as R would read them) and fits through polaris_re.gam.gam(...). Polaris
# reads nothing under "mgcv". See polaris_re.gam.formula_conformance for the claim.
#
# WHAT IS EXPORTED, per cell
#   mgcv$eta            m$linear.predictors            (training rows)
#   mgcv$edf_total      sum(m$edf)
#   mgcv$edf_by_smooth  sum of m$edf over each smooth's coefficient span
#   mgcv$labels         sapply(m$smooth, "[[", "label")
#   mgcv$bs_dim         smooth$bs.dim (product of the margins' bs.dim for a tensor smooth)
#   mgcv$ncoef          last.para - first.para + 1 per smooth
#   mgcv$nsdf           m$nsdf
#   mgcv$sp, mgcv$scale
#   mgcv$levels         levels() of every factor column in the model frame, as R
#                       sorted them -- the level-ordering measurement
# and, once per file, the session's collation and R's ordering of a probe string set.
#
# REQUIREMENTS: R with mgcv and jsonlite.   USAGE: Rscript scripts/gam_formula_probe.R [out.json]
# EXIT STATUS: 0 on a completed run, 1 on any R-side error.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

cell <- function(name, formula, family, d, select = FALSE, weights_col = NULL, newdata = NULL) {
  fam <- eval(parse(text = paste0(family, "()")))
  # character -> factor with R's DEFAULT factor() (levels sorted by the session's
  # collation): this is the level-ordering measurement. The strings are exported.
  dfit <- d
  dfit[] <- lapply(dfit, function(v) if (is.character(v)) factor(v) else v)
  args <- list(formula = as.formula(formula), data = dfit, family = fam,
               method = "REML", select = select)
  if (!is.null(weights_col)) args$weights <- dfit[[weights_col]]
  m <- do.call(mgcv::gam, args)
  sm <- m$smooth
  ssum <- summary(m)
  fac_names <- names(m$model)[vapply(m$model, is.factor, logical(1))]
  # Slice P5 (ADR-254): predict.gam at held-out rows, link and response scale, with se.fit
  # (Vp) and unconditional se.fit (Vc) -- the guide's worked example only.
  pred <- NULL
  if (!is.null(newdata)) {
    nd <- newdata
    for (nm in names(nd)) if (is.character(nd[[nm]])) {
      nd[[nm]] <- factor(nd[[nm]], levels = levels(dfit[[nm]]))
    }
    pl <- predict(m, nd, type = "link", se.fit = TRUE)
    plu <- predict(m, nd, type = "link", se.fit = TRUE, unconditional = TRUE)
    pr <- predict(m, nd, type = "response", se.fit = TRUE)
    pred <- list(
      newdata = as.list(newdata),
      link = as.numeric(pl$fit), link_se = as.numeric(pl$se.fit),
      link_se_unconditional = as.numeric(plu$se.fit),
      response = as.numeric(pr$fit), response_se = as.numeric(pr$se.fit)
    )
  }
  list(
    name = name, formula = formula, family = family, select = select,
    weights_column = weights_col,
    data = as.list(d),
    predict = pred,
    # Slice P4 (ADR-253): summary.gam's own report, for GamFit.summary() to be compared with
    summary = list(
      n = as.integer(ssum$n),
      scale = as.numeric(ssum$scale),
      dev_expl = as.numeric(ssum$dev.expl),
      reml = as.numeric(m$gcv.ubre),
      deviance = as.numeric(m$deviance),
      null_deviance = as.numeric(m$null.deviance),
      edf_s = if (is.null(ssum$s.table)) numeric(0) else as.numeric(ssum$s.table[, "edf"]),
      sp = as.numeric(m$sp)
    ),
    mgcv = list(
      eta = as.numeric(m$linear.predictors),
      edf_total = as.numeric(sum(m$edf)),
      edf_by_smooth = vapply(sm, function(s) sum(m$edf[s$first.para:s$last.para]), numeric(1)),
      labels = vapply(sm, function(s) s$label, character(1)),
      # a tensor smooth carries no bs.dim of its own: use the product of its margins'
      bs_dim = vapply(sm, function(s) as.integer(
        if (!is.null(s$bs.dim)) s$bs.dim else prod(vapply(s$margin, function(q) q$bs.dim, numeric(1)))),
        integer(1)),
      ncoef = vapply(sm, function(s) as.integer(s$last.para - s$first.para + 1L), integer(1)),
      nsdf = as.integer(m$nsdf),
      sp = as.numeric(m$sp),
      scale = as.numeric(m$scale),
      levels = setNames(lapply(fac_names, function(nm) levels(m$model[[nm]])), fac_names)
    )
  )
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_formula_probe.json"
  cells <- list()
  lv3 <- c("a", "b", "c"); lv2 <- c("p", "q")

  set.seed(20261006); n <- 400
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), w = runif(n, -2, 2))
  d$y <- sin(d$x) + 0.1 * d$z + 0.3 * d$w * (d$x - 5) / 5 +
    0.2 * sin(d$x / 2) * cos(d$z) + rnorm(n, sd = 0.3)
  cells[[length(cells) + 1]] <- cell("gaussian_cr_by_ti",
    'y ~ s(x, k = 9, bs = "cr") + s(x, by = w, k = 9, bs = "cr") + ti(x, z, k = c(7, 5), bs = "cr")',
    "gaussian", d)

  set.seed(20261007); n <- 450
  d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE), stringsAsFactors = FALSE)
  shift <- c(a = 0, b = 0.6, c = -0.5)[d$f]
  d$y <- sin(d$x + shift) + rnorm(n, sd = 0.3)
  # the rank-deficient form: Polaris REFUSES it (structural condition, ADR-250)
  cells[[length(cells) + 1]] <- cell("gaussian_factor_by_with_bare_smooth",
    'y ~ s(x, k = 8, bs = "cr") + s(x, by = f, k = 8, bs = "cr")', "gaussian", d)
  # the identified form of the same model: factor main effect + factor-by smooth
  cells[[length(cells) + 1]] <- cell("gaussian_factor_by",
    'y ~ f + s(x, by = f, k = 8, bs = "cr")', "gaussian", d)

  set.seed(20261008); n <- 360
  d <- data.frame(x = runif(n, 0, 10), A = sample(lv3, n, TRUE), B = sample(lv2, n, TRUE),
                  stringsAsFactors = FALSE)
  eff <- c(a = 0, b = 0.5, c = -0.3)[d$A] + c(p = 0, q = 0.4)[d$B] +
    0.3 * (d$A == "c") * (d$B == "q")
  d$y <- eff + cos(d$x / 2) + rnorm(n, sd = 0.3)
  cells[[length(cells) + 1]] <- cell("gaussian_parametric",
    'y ~ A + B + A:B + s(x, k = 8, bs = "cr")', "gaussian", d)
  # select=TRUE with an unpenalised parametric block (ADR-252)
  cells[[length(cells) + 1]] <- cell("gaussian_select_parametric",
    'y ~ A + B + A:B + s(x, k = 8, bs = "cr")', "gaussian", d, select = TRUE)

  set.seed(20261009); n <- 500
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), f = sample(lv3, n, TRUE),
                  stringsAsFactors = FALSE)
  lam <- exp(0.4 + 0.3 * sin(d$x / 2) + 0.1 * d$z + c(a = 0, b = 0.3, c = -0.2)[d$f])
  d$y <- rnbinom(n, mu = lam, size = 4)
  cells[[length(cells) + 1]] <- cell("quasipoisson_cr_re_ti",
    'y ~ s(x, k = 8, bs = "cr") + s(f, bs = "re") + ti(x, z, k = c(6, 5), bs = "cr")',
    "quasipoisson", d)
  # select=TRUE on cr + re + ti, quasi-Poisson (ADR-252): the target formula's structure
  cells[[length(cells) + 1]] <- cell("quasipoisson_select_cr_re_ti",
    'y ~ s(x, k = 8, bs = "cr") + s(f, bs = "re") + ti(x, z, k = c(6, 5), bs = "cr")',
    "quasipoisson", d, select = TRUE)

  set.seed(20261010); n <- 600
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5))
  d$y <- rbinom(n, 1, plogis(-0.3 + sin(d$x / 2) + 0.2 * (d$z - 2.5)))
  cells[[length(cells) + 1]] <- cell("binomial_cr",
    'y ~ s(x, k = 8, bs = "cr") + s(z, k = 6, bs = "cr")', "binomial", d)

  set.seed(20261011); n <- 450
  d <- data.frame(x = runif(n, 0, 10), expo = runif(n, 20, 200))
  d$y <- rpois(n, d$expo * exp(-3 + 0.4 * sin(d$x / 2)))
  d$off <- log(d$expo)
  cells[[length(cells) + 1]] <- cell("poisson_offset",
    'y ~ s(x, k = 8, bs = "cr") + offset(off)', "poisson", d)

  set.seed(20261013); n <- 700
  d <- data.frame(age = runif(n, 45, 85), year = runif(n, 2010, 2021),
                  dur = runif(n, 2, 22), expo = runif(n, 200, 4000))
  lrr <- -0.014 * (d$year - 2015) * (1 + 0.012 * (d$age - 65)) +
    0.05 * sin(d$age / 11) - 0.18 * exp(-d$dur / 9)
  q <- 0.0004 + 0.00003 * exp(0.085 * (d$age - 45))
  d$y <- rpois(n, d$expo * q * exp(lrr))
  d$off <- log(d$expo * q)
  cells[[length(cells) + 1]] <- cell("poisson_hgam",
    paste0('y ~ offset(off) + s(age, k = 7, bs = "cr") + s(year, k = 5, bs = "cr") + ',
           'ti(age, year, k = c(7, 5), bs = "cr") + s(dur, k = 5, bs = "cr")'),
    "poisson", d)

  set.seed(20261014); n <- 400
  d <- data.frame(x = runif(n, 0, 10), z = runif(n, 0, 5), w = runif(n, 0, 1))
  d$y <- sin(d$x) + 0.3 * d$z + rnorm(n, sd = 0.3)
  cells[[length(cells) + 1]] <- cell("gaussian_select",
    'y ~ s(x, k = 8, bs = "cr") + s(z, k = 6, bs = "cr") + s(w, k = 6, bs = "cr")',
    "gaussian", d, select = TRUE)

  # weights column
  set.seed(20261015); n <- 400
  d <- data.frame(x = runif(n, 0, 10), wt = runif(n, 0.5, 3))
  d$y <- sin(d$x) + rnorm(n, sd = 0.3 / sqrt(d$wt))
  cells[[length(cells) + 1]] <- cell("gaussian_weights",
    'y ~ s(x, k = 8, bs = "cr")', "gaussian", d, weights_col = "wt")

  # level ordering: mixed case and numeric-looking strings, sorted by R's own factor()
  set.seed(20261016); n <- 480
  lv <- c("b", "B", "a", "A", "10", "9", "_z", "Z")
  d <- data.frame(x = runif(n, 0, 10), g = sample(lv, n, TRUE), stringsAsFactors = FALSE)
  d$y <- sin(d$x) + as.integer(factor(d$g)) * 0.1 + rnorm(n, sd = 0.3)
  cells[[length(cells) + 1]] <- cell("gaussian_level_order",
    'y ~ g + s(x, k = 8, bs = "cr")', "gaussian", d)

  # HELD-OUT level ordering (review P1-1): strings chosen BEFORE the run, disjoint from the
  # calibration sample above -- multi-character case ties, an embedded underscore and
  # digit/letter mixes -- so the en_US rule is tested rather than re-confirmed.
  set.seed(20261017); n <- 600
  lvh <- c("aB", "Ab", "ab", "AB", "a_b", "ab2", "a1", "1a", "B2", "b10", "b9", "Zed", "zed")
  d <- data.frame(x = runif(n, 0, 10), g = sample(lvh, n, TRUE), stringsAsFactors = FALSE)
  d$y <- sin(d$x) + as.integer(factor(d$g)) * 0.05 + rnorm(n, sd = 0.3)
  cells[[length(cells) + 1]] <- cell("gaussian_level_order_heldout",
    'y ~ g + s(x, k = 8, bs = "cr")', "gaussian", d)

  # Slice P5 (ADR-254): the user guide's worked example. The data are the committed
  # synthetic CSVs that docs/GAM_USER_GUIDE.md and the notebook read; the formula string is
  # polaris_re.gam.example.GUIDE_FORMULA, copied here as text (a test pins the two equal).
  gd <- read.csv("data/gam_preview/guide_example_train.csv", stringsAsFactors = FALSE)
  gn <- read.csv("data/gam_preview/guide_example_new.csv", stringsAsFactors = FALSE)
  cells[[length(cells) + 1]] <- cell("guide_example",
    paste0("deaths ~ offset(log_exposure) + sex + s(age, k = 8, bs = 'cr') + ",
           "s(duration, k = 6, bs = 'cr') + ti(age, duration, k = c(6, 4), bs = 'cr')"),
    "quasipoisson", gd, newdata = gn)

  out <- list(
    schema_version = 1L,
    mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string,
    collate = Sys.getlocale("LC_COLLATE"),
    sort_probe_input = c("b", "B", "a", "A", "10", "9", "_z", "Z"),
    sort_probe = sort(c("b", "B", "a", "A", "10", "9", "_z", "Z")),
    sort_heldout_input = c("aB", "Ab", "ab", "AB", "a_b", "ab2", "a1", "1a", "B2", "b10", "b9", "Zed", "zed"),
    sort_heldout = sort(c("aB", "Ab", "ab", "AB", "a_b", "ab2", "a1", "1a", "B2", "b10", "b9", "Zed", "zed")),
    cells = cells
  )
  jsonlite::write_json(out, out_path, digits = NA, auto_unbox = TRUE, null = "null")
  cat(sprintf("Wrote %s -- %d cells, mgcv %s, LC_COLLATE %s\n", out_path, length(cells),
              as.character(packageVersion("mgcv")), Sys.getlocale("LC_COLLATE")))
  invisible(NULL)
}

status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
  error = function(e) { message("gam_formula_probe.R FAILED: ", conditionMessage(e)); 1L })
quit(status = status)
