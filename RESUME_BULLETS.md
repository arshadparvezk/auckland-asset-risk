# Resume-ready project entry

## Auckland Natural Hazard Asset Loss Engine

**Python, GeoPandas, NumPy, Monte Carlo Simulation, SQL/SQLite, R, Streamlit, Plotly, ArcGIS REST**

- Engineered a reproducible geospatial pipeline that cleaned and assessed **2,022 public asset records** against **8 Auckland coastal-inundation layers**, spanning four annual exceedance probabilities and current versus +1 m sea-level-rise conditions, with automated data-quality and geometry checks.
- Built a **10,000-iteration Monte Carlo financial-loss model** incorporating replacement-value and damage uncertainty to generate P50/P90 loss-exceedance curves and annualised loss estimates; modelled illustrative portfolio EAL of **NZ$0.79m under current climate and NZ$6.46m under +1 m SLR**.
- Automated current, climate-change and resilience-treatment scenarios and delivered a criticality-adjusted asset priority register, SQLite analytical database, interactive Streamlit dashboard and stakeholder-ready executive report; a stated 35% damage-reduction treatment assumption reduced modelled +1 m SLR EAL to **NZ$4.20m**.

## Short version when resume space is tight

- Developed a Python/GeoPandas and Monte Carlo asset-risk engine for 2,022 Auckland public assets, producing probabilistic loss-exceedance curves, annualised loss, automated +1 m SLR scenarios, SQL risk registers and an interactive Streamlit dashboard using transparent illustrative financial assumptions.

## 60-second interview explanation

I built this because the role sits at the intersection of hazard science, geospatial data and asset finance. The pipeline downloads public Auckland Council asset locations and coastal-inundation extents for four annual exceedance probabilities, cleans and validates the data, then identifies exposed assets under current conditions and a one-metre sea-level-rise scenario. Because the public hazard layer provides extent rather than depth and does not contain confidential asset values, I used clearly labelled, configurable replacement-value and vulnerability assumptions. I then propagated those uncertainties through 10,000 Monte Carlo iterations to produce P50 and P90 event losses, loss-exceedance curves and expected annual loss. Finally, I built a criticality-adjusted priority register, SQLite database, executed notebook, standalone dashboard and executive summary. The most important design choice was making every assumption explicit so a hazard scientist, asset manager or finance stakeholder could challenge and replace it.

## Integrity note

The financial results are method-demonstration outputs based on assumptions in `config/model.yml`; they are not Auckland Council valuations and should always be described as illustrative.
