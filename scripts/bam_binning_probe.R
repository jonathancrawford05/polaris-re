#!/usr/bin/env Rscript
#
# bam_binning_probe.R -- Slice R3 Stage A (ADR-260 amendment 1).
#
# Two sections, written to ONE JSON file:
#
#  1. BINNING (INDEPENDENT comparison with polaris_re.gam.bam_binning_conformance): for each
#     cell, mgcv:::discrete.mf(full = TRUE) is run on the formula and the data, and the
#     per-variable nr, discretised value per row and cell index are written. The data columns
#     ARE the recipe; Polaris is handed the same raw columns, never this script's index.
#     `joint` cells call mgcv:::compress.df directly on a 2-column term (d = 2: m = 100).
#
#  2. ALGORITHM (REFERENCE_INTERNAL: mgcv against mgcv, Polaris absent): one cell with no
#     binned covariate fitted by gam(REML), bam(fREML, discrete=FALSE) and
#     bam(fREML, discrete=TRUE). Isolates whether bam's difference from gam is the BINNING
#     (it cannot be: nothing is binned) or the ALGORITHM.
#
# USAGE: Rscript scripts/bam_binning_probe.R <out.json>
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

set.seed(20261016)

cells <- list()
add_cell <- function(name, formula, d, m = NULL) {
  cells[[length(cells) + 1]] <<- list(name = name, formula = formula, d = d, m = m)
}

ag <- expand.grid(age = 30:90, dur = 1:20, smoker = c("NS", "S"), stringsAsFactors = FALSE)
ag$y <- 0
add_cell("integer_age_dur_ti",
         'y ~ s(age, bs="cr", k=13) + s(dur, bs="cr", k=6) + ti(age, dur, bs="cr", k=c(13,6)) + smoker', ag)

n <- 5000
add_cell("continuous_binned_two_smooths", 'y ~ s(x, bs="cr", k=10) + s(z, bs="cr", k=10)',
         data.frame(x = runif(n), z = rnorm(n), y = 0))
add_cell("continuous_below_threshold", 'y ~ s(x, bs="cr", k=10)',
         data.frame(x = runif(800), y = 0))
add_cell("exactly_1000_unique_not_binned", 'y ~ s(x, bs="cr", k=10)',
         data.frame(x = rep((1:1000) / 7, 3), y = 0))
add_cell("exactly_1001_unique_binned", 'y ~ s(x, bs="cr", k=10)',
         data.frame(x = rep((1:1001) / 7, 3), y = 0))
nn <- 4000
add_cell("factor_by_and_continuous_parametric",
         'y ~ g + w + s(x, bs="cr", k=8, by=g)',
         data.frame(g = sample(c("A", "B", "C"), nn, TRUE), w = runif(nn) * 50, x = runif(nn), y = 0))
add_cell("shared_variable_across_terms",
         'y ~ s(age, bs="cr", k=10) + ti(age, dur, bs="cr", k=c(6,5)) + s(dur, bs="cr", k=5, by=smoker) + smoker',
         transform(ag, age = age + runif(nrow(ag)) * 0.001))

run_cell <- function(cell) {
  d <- cell$d
  for (nm in names(d)) if (is.character(d[[nm]])) d[[nm]] <- factor(d[[nm]])
  gp <- interpret.gam(as.formula(cell$formula))
  mf <- model.frame(gp$fake.formula, d)
  names.pmf <- setdiff(names(mf), as.character(gp$response))
  dm <- mgcv:::discrete.mf(gp, mf, names.pmf, m = cell$m, full = TRUE)
  vars <- setdiff(rownames(dm$ks), "(Intercept)")
  nr <- list(); vals <- list(); idx <- list()
  for (v in vars) {
    r <- dm$nr[[v]]
    kcol <- dm$k[, dm$ks[v, 1]]
    u <- dm$mf[[v]][seq_len(r)]
    row_vals <- u[kcol]
    if (is.factor(row_vals)) {
      lev <- sort(unique(as.character(d[[v]])), method = "radix")
      row_vals <- match(as.character(row_vals), lev) - 1
    }
    nr[[v]] <- r; vals[[v]] <- as.numeric(row_vals); idx[[v]] <- as.integer(kcol)
  }
  data_out <- lapply(d[setdiff(names(d), "y")], function(col) if (is.factor(col)) as.character(col) else as.numeric(col))
  list(name = cell$name, formula = cell$formula, m = cell$m, data = data_out,
       mgcv = list(nr = nr, values = vals, index = idx))
}
cell_out <- lapply(cells, run_cell)

joint <- list()
add_joint <- function(name, df, m = NULL) {
  facs <- names(df)[vapply(df, is.factor, logical(1))]
  cd <- mgcv:::compress.df(df, m = m)
  k <- as.integer(attr(cd, "index"))
  cols <- lapply(names(df), function(v) {
    x <- cd[[v]][k]
    if (is.factor(x)) match(as.character(x), sort(unique(as.character(df[[v]])), method = "radix")) - 1 else as.numeric(x)
  })
  names(cols) <- names(df)
  data_out <- lapply(df, function(col) if (is.factor(col)) as.character(col) else as.numeric(col))
  joint[[length(joint) + 1]] <<- list(name = name, m = m, factors = as.list(facs), data = data_out,
    mgcv = list(nr = nrow(cd), values = cols, index = k))
}
add_joint("joint_two_numeric_binned", data.frame(x = runif(3000), z = runif(3000)))
add_joint("joint_two_numeric_small", data.frame(x = sample(1:30, 3000, TRUE), z = sample(1:40, 3000, TRUE)))
add_joint("joint_factor_numeric_binned", data.frame(x = runif(6000), f = factor(sample(c("A","B","C"), 6000, TRUE))))
add_joint("joint_two_numeric_m_given", data.frame(x = runif(3000), z = runif(3000)), m = 200)
add_joint("joint_three_numeric", data.frame(x = runif(4000), y = runif(4000), z = runif(4000)))

# ---- ALGORITHM section: REFERENCE_INTERNAL ---------------------------------------------
gal <- expand.grid(age = 30:90, dur = 1:20, smoker = factor(c("NS", "S")))
gal$expo <- runif(nrow(gal), 50, 500)
mu <- gal$expo * exp(-6 + 0.07 * (gal$age - 30) - 0.02 * gal$dur + 0.3 * (gal$smoker == "S"))
gal$y <- rpois(nrow(gal), mu)
form <- y ~ s(age, bs = "cr", k = 13) + s(dur, bs = "cr", k = 6) +
  ti(age, dur, bs = "cr", k = c(13, 6)) + smoker + offset(log(expo))
fits <- list(
  gam = gam(form, data = gal, family = poisson(), method = "REML"),
  bam_nodisc = bam(form, data = gal, family = poisson(), method = "fREML", discrete = FALSE),
  bam_disc = bam(form, data = gal, family = poisson(), method = "fREML", discrete = TRUE))
summ <- function(m) list(
  eta = as.numeric(m$linear.predictors), edf_total = sum(m$edf),
  smooth_edf = vapply(m$smooth, function(s) sum(m$edf[s$first.para:s$last.para]), numeric(1)),
  smooth_label = vapply(m$smooth, function(s) s$label, character(1)),
  log10_sp = log10(as.numeric(m$sp)), iter = if (is.null(m$iter)) NA else m$iter)
algorithm <- list(n_rows = nrow(gal), formula = deparse(form), fits = lapply(fits, summ))

out <- list(mgcv_version = as.character(packageVersion("mgcv")), r_version = R.version.string,
            cells = cell_out, joint = joint, algorithm = algorithm)
args <- commandArgs(trailingOnly = TRUE)
# digits = I(17): 17 SIGNIFICANT digits round-trips a double exactly. digits = NA is only 15, which
# changed the data Polaris saw by an ulp and flipped an engineered exact rounding tie.
jsonlite::write_json(out, args[[1]], digits = I(17), auto_unbox = TRUE, null = "null", na = "null")
cat("wrote", args[[1]], "\n")
