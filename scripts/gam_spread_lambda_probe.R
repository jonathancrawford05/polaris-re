# Does the FITTER degrade at badly-scaled lambda, or only the determinant?
#
# The determinant-only scope for PLAN slice 5c rests on "the fitter is tier-3
# verified on eta (ADR-206, 1.242e-10) and is not implicated". But ADR-206 verified
# at ONE well-conditioned sp. Wood (2011) section 3.1 says the numerical zero
# leakage problem "leads to serious errors in evaluation of beta-hat, |S|+ AND
# |X'WX + S| and their derivatives" -- so the fitter may be implicated at spread
# lambda, where it has never been checked.
#
# Emits mgcv's eta at each of the same eight fixed-sp points.

suppressPackageStartupMessages({
  library(mgcv)
  library(jsonlite)
})

set.seed(20260825)
n <- 900
age_knots <- c(1, 2, 4, 7, 14, 18, 24, 35, 50, 70, 85, 90, 95)
year_knots <- c(1, 2, 3, 5, 10, 21)
AttdAge <- runif(n, 1, 95)
PolYear <- runif(n, 1, 21)
StudyYear_C <- runif(n, -5, 5)
ExposCnt <- round(runif(n, 50, 500))
eta_true <- -4.5 + 0.03 * AttdAge - 0.02 * PolYear +
  0.01 * StudyYear_C * (AttdAge - 50) / 50 +
  0.15 * sin(AttdAge / 10) * cos(PolYear / 3)
prob_true <- 1 - exp(-exp(eta_true))
DthCnt <- rbinom(n, ExposCnt, prob_true)
y <- DthCnt / ExposCnt
df <- data.frame(
  AttdAge = AttdAge, PolYear = PolYear,
  StudyYear_C = StudyYear_C, ExposCnt = ExposCnt, y = y
)
knots_arg <- list(AttdAge = age_knots, PolYear = year_knots)
form <- y ~ s(AttdAge, k = 13, bs = "cr") +
  s(AttdAge, by = StudyYear_C, k = 13, bs = "cr") +
  ti(AttdAge, PolYear, k = c(13, 6), bs = "cr")

m_free <- mgcv::gam(form,
  data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
  knots = knots_arg, method = "REML"
)
points <- list(
  mgcv_opt    = log10(as.numeric(m_free$sp)),
  python_opt  = c(6.753, 9.096, 3.099, 3.054),
  flat_2      = c(2, 2, 2, 2),
  flat_4      = c(4, 4, 4, 4),
  flat_6      = c(6, 6, 6, 6),
  mixed_lo_hi = c(3, 8, 2, 5),
  mixed_hi_lo = c(8, 3, 5, 2),
  mid         = c(5, 5, 3, 3),
  # Deliberately harsher than anything measured so far: 12 decades, which is
  # inside PRODUCTION_LOG10_BOUNDS = (-2, 12) and so genuinely reachable.
  extreme     = c(-1, 11, 0, 6)
)

rows <- lapply(names(points), function(nm) {
  lg <- as.numeric(points[[nm]])
  m <- mgcv::gam(form,
    data = df, family = binomial(link = "cloglog"), weights = ExposCnt,
    knots = knots_arg, sp = 10^lg, method = "REML"
  )
  list(name = nm, log10_sp = lg, eta = as.numeric(predict(m, type = "link")))
})

write_json(
  list(
    mgcv_version = as.character(packageVersion("mgcv")),
    age_knots = age_knots, year_knots = year_knots,
    AttdAge = AttdAge, PolYear = PolYear, StudyYear_C = StudyYear_C,
    ExposCnt = ExposCnt, y = y, points = rows
  ),
  commandArgs(trailingOnly = TRUE)[1], digits = 17, auto_unbox = TRUE
)
cat("done\n")
