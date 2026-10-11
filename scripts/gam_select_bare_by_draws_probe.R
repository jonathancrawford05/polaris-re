#!/usr/bin/env Rscript
#
# gam_select_bare_by_draws_probe.R -- Slice R1 (docs/PLAN_gam_real_data_readiness.md, ADR-258):
# select=TRUE with a factor-by smooth, over REPEATED DRAWS, for all four forms.
#
# Why draws: one synthetic sample per cell cannot separate a form that is wrong from a draw that
# is unlucky. Draws 1-15 are the first set, 16-30 an independent second set (added with the
# two-by forms, ADR-258 review P1): 30 draws x 2 families x 8 forms = 480 mgcv fits.
# mgcv fits gam(<formula>, method = "REML", select = TRUE) on each draw and exports eta,
# edf_total, sp and the REML score; scripts/gam_select_bare_by_draws_compare.py fits the same
# strings and data in Polaris through its own front end. Polaris reads nothing under "mgcv".
#
# FORMS (f = a 3-level factor)
#   by_only       y ~ s(x, by = f)
#   main_by       y ~ f + s(x, by = f)
#   bare_by       y ~ s(x) + s(x, by = f)          (gam() REFUSES this with select=TRUE: ADR-258)
#   main_bare_by  y ~ f + s(x) + s(x, by = f)      (likewise refused)
#   two_by        y ~ s(x, by = f) + s(x, by = g)   (g a 2-level factor; refused as UNMEASURED
#   main_two_by   y ~ f + g + s(x, by = f) + s(x, by = g)   until this probe, ADR-258 review P1)
#   main_by_ti    y ~ f + s(x, by = f) + ti(x, z)   (ti beside the by smooth; ADR-258 re-review P2)
#   main_by_numby y ~ f + s(x, by = f) + s(x, by = w)   (w numeric; was unmeasured and refused)
#
# USAGE: Rscript scripts/gam_select_bare_by_draws_probe.R [out.json]
suppressPackageStartupMessages({ library(mgcv); library(jsonlite) })

forms <- list(
  by_only = 'y ~ s(x, by = f, k = 8, bs = "cr")',
  main_by = 'y ~ f + s(x, by = f, k = 8, bs = "cr")',
  bare_by = 'y ~ s(x, k = 8, bs = "cr") + s(x, by = f, k = 8, bs = "cr")',
  main_bare_by = 'y ~ f + s(x, k = 8, bs = "cr") + s(x, by = f, k = 8, bs = "cr")',
  two_by = 'y ~ s(x, by = f, k = 8, bs = "cr") + s(x, by = g, k = 8, bs = "cr")',
  main_two_by = 'y ~ f + g + s(x, by = f, k = 8, bs = "cr") + s(x, by = g, k = 8, bs = "cr")',
  main_by_ti = 'y ~ f + s(x, by = f, k = 8, bs = "cr") + ti(x, z, k = c(5, 5), bs = "cr")',
  main_by_numby = 'y ~ f + s(x, by = f, k = 8, bs = "cr") + s(x, by = w, k = 8, bs = "cr")')

one <- function(name, fam, form, d) {
  dfit <- d; dfit$f <- factor(dfit$f); dfit$g <- factor(dfit$g)
  m <- mgcv::gam(as.formula(forms[[form]]), data = dfit,
                 family = eval(parse(text = paste0(fam, "()"))), method = "REML", select = TRUE)
  list(name = name, family = fam, form = form, formula = forms[[form]], select = TRUE,
       data = as.list(d),
       mgcv = list(eta = as.numeric(m$linear.predictors), edf_total = sum(m$edf),
                   sp = as.numeric(m$sp), reml = as.numeric(m$gcv.ubre),
                   scale = as.numeric(m$scale)))
}

main <- function(argv) {
  out_path <- if (length(argv) >= 1) argv[[1]] else "gam_select_bare_by_draws_probe.json"
  cells <- list(); lv3 <- c("a", "b", "c")
  for (fam in c("gaussian", "poisson")) for (seed in 1:30) {
    set.seed(5000 + seed); n <- if (fam == "gaussian") 450 else 600
    d <- data.frame(x = runif(n, 0, 10), f = sample(lv3, n, TRUE), stringsAsFactors = FALSE)
    shift <- c(a = 0, b = 0.6, c = -0.5)[d$f]
    d$y <- if (fam == "gaussian") sin(d$x + shift) + rnorm(n, sd = 0.3)
           else rpois(n, exp(0.8 + 0.4 * sin(d$x / 2 + shift)))
    set.seed(9000 + seed)  # g comes from its own stream so the draws above are unchanged
    d$g <- sample(c("p", "q"), n, TRUE)
    d$z <- runif(n, 0, 5)
    d$w <- runif(n, -1, 1)
    for (form in names(forms))
      cells[[length(cells) + 1]] <- one(sprintf("%s_draw%02d_%s", fam, seed, form), fam, form, d)
  }
  jsonlite::write_json(list(schema_version = 1L, mgcv_version = as.character(packageVersion("mgcv")),
    r_version = R.version.string, cells = cells), out_path, digits = NA, auto_unbox = TRUE,
    null = "null")
  cat(sprintf("Wrote %s -- %d cells, mgcv %s\n", out_path, length(cells),
              as.character(packageVersion("mgcv"))))
}
status <- tryCatch({ main(commandArgs(trailingOnly = TRUE)); 0L },
  error = function(e) { message("gam_select_bare_by_draws_probe.R FAILED: ", conditionMessage(e)); 1L })
quit(status = status)
