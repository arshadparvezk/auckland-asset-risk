# Independent R check of expected annual loss from the Python output.
# Run from the project root: Rscript r/validate_loss_curve.R

curve <- read.csv("outputs/loss_exceedance_curve.csv")

integrate_curve <- function(aep, loss) {
  ord <- order(aep)
  x <- c(0, aep[ord], 1)
  y <- c(loss[ord][1], loss[ord], 0)
  sum(diff(x) * (head(y, -1) + tail(y, -1)) / 2)
}

scenarios <- unique(curve$scenario)
checks <- do.call(rbind, lapply(scenarios, function(s) {
  rows <- curve[curve$scenario == s, ]
  data.frame(
    scenario = s,
    expected_curve_eal_nzd = integrate_curve(rows$aep, rows$expected_loss_nzd),
    p90_curve_eal_nzd = integrate_curve(rows$aep, rows$p90_loss_nzd)
  )
}))

write.csv(checks, "outputs/r_eal_validation.csv", row.names = FALSE)
print(checks)

