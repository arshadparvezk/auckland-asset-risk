# Methodology and modelling choices

## 1. Scope

This is a portfolio-screening model for Auckland public park and community-facility assets. Coastal inundation is the only hazard monetised as expected annual loss (EAL). Auckland Council liquefaction vulnerability is added as a separate seismic screening category, and Auckland Growth Scenario 2023 version 1.1 (AGS23v1.1) is added as planning context. The evidence types are deliberately not blended into one opaque score.

It is not a site-specific hazard assessment, valuation, insurance model or investment case.

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
| Synthetic depth surface | No | Useful for teaching, but weaker for evidence-based portfolio claims |
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

It is a coastal-financial triage score. Liquefaction category and growth context do not alter EAL or this priority score.

## 8. Liquefaction vulnerability screening

The pipeline downloads Auckland Council's public **Liquefaction Vulnerability – Basic Assessment** polygon layer in EPSG:2193 and intersects it with the asset points using unsimplified source geometry. Source category values are normalised for presentation:

| Source value | Output label | Use in this project |
| --- | --- | --- |
| `Possible` | `Damage Possible` | Flag for further geotechnical review |
| `Unlikely` | `Damage Unlikely` | Retain as mapped context |
| `Very Low` | `Very Low` | Retain as mapped context |
| no polygon match | `Not mapped` | Record coverage gap |

If polygons overlap, the pipeline deterministically retains the highest-attention category and records the number of matches. The verified source produced no overlaps for this portfolio.

This is regional desktop vulnerability mapping conditional on earthquake shaking. It is not an occurrence-frequency model, site-specific ground assessment or financial-loss model. It has substantial residual uncertainty and does not account for recent earthworks, ground improvement or foundation design. A monetised earthquake EAL would require an earthquake event set and asset fragility functions, so none is invented here.

## 9. Growth and service-demand context

The committed reference extract comes from Auckland Council's current AGS23v1.1 local-board worksheet and compares 2022 with 2052 household, population and employment projections. Council states that this scenario informs the Long-term Plan, asset-management plans and investment coordination.

- `Waiheke` and `Aotea/Great Barrier` asset results are aggregated to the source geography `Waiheke-Great Barrier` before joining.
- `Unknown` and `NOT SUPPLIED` local-board records remain explicitly unmapped.
- `Tuakau-Pokeno` and workbook total/note rows are excluded from the Auckland local-board extract.
- Auckland's published regional population-growth benchmark is 35.2497% from 2022 to 2052.

Growth is shown beside loss and exposure as a planning lens. It is not used as a damage, probability, criticality or EAL multiplier because population growth alone does not establish asset demand or vulnerability.

## 10. Illustrative intervention economics

Only the existing +1 m SLR scenarios are paired. The annual direct-damage benefit for asset (i) is:

\[
B_i = EAL_{i,\,slr\_1m} - EAL_{i,\,treated}
\]

The central demonstration assumes a 30-year horizon, 5% real discount rate, capital cost equal to the greater of 20% of illustrative replacement value or NZ$50,000, and annual operations and maintenance (O&M) equal to 1% of capital cost. Benefits and O&M start at the end of year 1. There is no residual value, renewal, degradation, inflation, tax or financing model.

For discount rate (r) and horizon (N):

\[
AF(r,N)=\frac{1-(1+r)^{-N}}{r}, \quad
PV(B_i)=B_i\times AF(r,N)
\]

\[
PV(C_i)=Capex_i + O\&M_i\times AF(r,N)
\]

\[
NPV_i=PV(B_i)-PV(C_i), \qquad BCR_i=\frac{PV(B_i)}{PV(C_i)}
\]

Portfolio BCR is the ratio of total PV benefits to total PV costs; asset BCRs are never averaged. Discounted payback is the first whole year cumulative discounted net benefit becomes non-negative. The pipeline evaluates a 0.5×/1×/2× cost matrix and 3%/5%/7% real discount rates.

These are replaceable demonstration assumptions, not Council settings, contractor estimates or a dated forecast of when +1 m SLR occurs. Benefits include modelled direct physical damage only. Excluded benefits and costs include public safety, service continuity, equity, environmental outcomes, downtime, insurance, dependencies, programme economies and shared infrastructure. The results must not be described as an investment recommendation.

## 11. Validation

The automated QA checks confirm:

- every asset has valid geometry and required standardised fields;
- duplicate business identifiers are flagged rather than silently removed;
- exposure counts and expected losses are monotonic across event severity;
- mitigation reduces loss under identical random draws;
- treatment scenarios pair on unique `record_id`, preserve values and never increase treated EAL;
- portfolio BCR is calculated from aggregate benefits and costs, with cost sensitivity monotonic;
- liquefaction screening produces exactly one auditable row per asset and preserves unmapped records;
- AGS23v1.1 regional totals and the combined island geography reconcile;
- the dashboard loads without application exceptions;
- the offline dashboard embeds all charts and data without external resources;
- SQLite tables and CSV outputs reconcile.

## 12. Primary sources and responsible use

- Auckland Council public coastal-inundation and asset-location ArcGIS services, configured in `config/model.yml`.
- Auckland Council [Liquefaction Vulnerability – Basic Assessment](https://services1.arcgis.com/n4yPwebTjJCmXB6W/ArcGIS/rest/services/Liquefaction_Vulnerability_Basic_Assessment/FeatureServer/0).
- Auckland Council [Auckland Growth Scenario 2023 v1.1](https://www.knowledgeauckland.org.nz/publications/auckland-growth-scenario-2023-version-11-ags23v11-data/).
- Auckland Council [geospatial terms and conditions](https://www.aucklandcouncil.govt.nz/geospatial/Pages/geospatial-terms-conditions.aspx).

The source layers are indicative and must be independently verified before operational use. The repository republishes derived asset classifications and aggregate outputs for a portfolio demonstration; it does not claim property-level certainty.
