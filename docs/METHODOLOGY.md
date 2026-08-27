# Methodology and modelling choices

## 1. Scope

This is a portfolio-screening model for Auckland public park and community-facility assets exposed to coastal inundation. It demonstrates how hazard science, asset information, uncertainty and financial risk can be brought into one reproducible decision pipeline.

It is not a site-specific flood assessment, valuation, insurance model or investment case.

## 2. Why the project uses hazard extent rather than invented flood depth

The public Auckland Council layers used here provide mapped inundation **extent** at specified annual exceedance probabilities. They do not provide an event water-depth raster at every asset location.

A digital elevation model alone cannot supply flood depth. Depth requires both terrain elevation and a defensible event water-surface elevation:

\[
Depth(x,y) = WaterSurface_e(x,y) - Terrain(x,y)
\]

Subtracting a DEM from an assumed or synthetic water surface would create false precision. The project therefore uses an extent-based conditional damage model with explicit uncertainty. This is more defensible than presenting synthetic depth as observed Auckland hazard information.

| Approach | Used here? | Reason |
| --- | --- | --- |
| Real hazard extent + conditional damage distribution | Yes | Supported by the public source data and transparent for screening |
| DEM-only depth assignment | No | A DEM does not contain event water-surface elevation |
| Synthetic depth surface | No | Useful for teaching, but weaker for real-Auckland resume claims |
| Hydrodynamic depth raster + empirical depth-damage curves | Future upgrade | Preferred when authoritative depth outputs and calibrated vulnerability data are available |

## 3. Exposure model

Each asset point is tested for intersection with coastal-inundation polygons for four annual exceedance probabilities (AEPs): 18.1%, 4.9%, 2% and 1%. Present-day and +1 m sea-level-rise layers are modelled independently.

Public hazard polygons are generalised to 20 metres during download. This materially reduces processing cost while retaining a suitable resolution for regional portfolio screening. Boundary assets should be checked against the original geometry before any operational use.

## 4. Financial assumptions

Replacement values are illustrative type-based assumptions defined in `config/model.yml`. They are not Auckland Council financial records. Event loss for asset \(i\) in event \(e\) and scenario \(s\) is:

\[
L_{i,e,s} = I_{i,e,s} \times V_i \times DR_e \times M_s
\]

where:

- \(I\) is the binary exposure indicator;
- \(V\) is illustrative replacement value;
- \(DR\) is conditional damage ratio;
- \(M\) is the scenario treatment multiplier.

## 5. Uncertainty model

The model performs 10,000 deterministic-seed Monte Carlo iterations. It samples:

- asset replacement-value factors from a mean-corrected lognormal distribution;
- event damage ratios from beta distributions;
- a systematic damage factor shared across each simulated portfolio event.

Outputs include expected, P50 and P90 portfolio event loss.

## 6. Loss-exceedance curve and EAL

Expected annual loss is calculated as the area under the loss-exceedance curve. With only four public AEP points, the model makes its boundaries explicit:

- the 1% AEP loss is held constant from probability 0 to 0.01;
- the 18.1% AEP loss is linearly reduced to zero at probability 1;
- trapezoidal integration is applied between points.

This approximation is transparent and replaceable when more event frequencies are available.

## 7. Decision prioritisation

The asset priority score adjusts EAL for service criticality:

\[
Priority_i = EAL_i \times [1 + 0.15(C_i - 1)]
\]

It is a triage score, not a benefit-cost ratio. A production investment model should add intervention cost, remaining life, downtime, service dependency, equity and uncertainty in avoided loss.

## 8. Validation

The automated QA checks confirm:

- every asset has valid geometry and required standardised fields;
- duplicate business identifiers are flagged rather than silently removed;
- exposure counts and expected losses are monotonic across event severity;
- mitigation reduces loss under identical random draws;
- the dashboard loads without application exceptions;
- SQLite totals reconcile with the CSV scenario summary.

