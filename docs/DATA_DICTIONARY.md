# Data dictionary

## Asset risk register

| Field | Description |
| --- | --- |
| `record_id` | Unique source-record key created from the ArcGIS object identifier |
| `asset_id` | Business asset identifier; duplicates are retained and flagged |
| `scenario` | `baseline`, `slr_1m`, or `slr_1m_mitigated` |
| `asset_type` | Standardised public asset type |
| `asset_group` | Source asset grouping |
| `local_board` | Auckland local board name |
| `planning_area` | AGS23v1.1 join geography; combines Waiheke and Aotea/Great Barrier |
| `replacement_value_nzd` | Illustrative type-based replacement value assumption |
| `criticality_score` | Configured service criticality score from 1 to 5 |
| `expected_annual_loss_nzd` | Area under the asset loss-exceedance curve |
| `priority_score` | EAL adjusted for service criticality |
| `risk_band` | Relative portfolio-screening band |

## Loss-exceedance output

| Field | Description |
| --- | --- |
| `scenario` | Modelled climate/treatment scenario |
| `aep` | Annual exceedance probability as a decimal |
| `expected_loss_nzd` | Expected portfolio loss conditional on the event |
| `p50_loss_nzd` | Median Monte Carlo portfolio event loss |
| `p90_loss_nzd` | 90th-percentile Monte Carlo portfolio event loss |
| `exposed_assets` | Asset records intersecting the hazard extent |
| `exposed_value_nzd` | Sum of illustrative replacement values for exposed records |

## Multi-hazard screening output

File: `outputs/asset_hazard_screening.csv`. SQLite table: `asset_hazard_screening`.

| Field | Description |
| --- | --- |
| `record_id` | Unique asset source-record key |
| `coastal_current_eal_nzd` | Modelled current-climate coastal EAL |
| `coastal_slr_1m_eal_nzd` | Modelled untreated +1 m SLR coastal EAL |
| `coastal_current_exposed` | Whether current coastal EAL is positive |
| `coastal_slr_1m_exposed` | Whether +1 m SLR coastal EAL is positive |
| `liquefaction_vulnerability` | Normalised Council category: `Damage Possible`, `Damage Unlikely`, `Very Low`, or `Not mapped` |
| `liquefaction_mapped` | Whether the asset intersects a mapped source polygon |
| `liquefaction_review_flag` | True only for `Damage Possible`; investigation flag, not predicted loss |
| `liquefaction_overlap_matches` | Number of intersecting source polygons before deterministic resolution |
| `liquefaction_unrecognised_category` | Flags a mapped source value not covered by the documented normalisation |
| `screening_flag_count` | Transparent count of +1 m coastal exposure and liquefaction review flag; range 0–2 |
| `screening_attention` | Text description of which screening flags apply |

## Local-board growth context

Reference file: `data/reference/ags23v1_1_local_board_2022_2052.csv`. Output: `outputs/local_board_growth_context.csv`. SQLite table: `local_board_growth_context`.

| Field | Description |
| --- | --- |
| `scenario` | Coastal scenario used for the adjacent portfolio metrics |
| `planning_area` | AGS23v1.1 local-board grouping |
| `portfolio_assets` | Unique assets in that planning area |
| `assets_with_modelled_loss` | Assets with positive coastal EAL in the scenario |
| `illustrative_portfolio_value_nzd` | Sum of illustrative replacement values |
| `expected_annual_loss_nzd` | Coastal EAL summed for the planning area |
| `households_2022`, `households_2052` | Published AGS23v1.1 household projections |
| `population_2022`, `population_2052` | Published AGS23v1.1 population projections |
| `employment_2022`, `employment_2052` | Published AGS23v1.1 employment projections |
| `*_growth_rate` | End/start minus one for the relevant measure |
| `*_cagr` | Compound annual growth rate over 30 years |
| `growth_data_mapped` | Whether a published planning-area row was matched |
| `auckland_population_growth_rate` | Published regional benchmark repeated for comparison |
| `above_auckland_population_growth` | Whether planning-area population growth exceeds the regional benchmark |
| `future_population_eal_per_1000_nzd` | Context ratio of scenario EAL per 1,000 projected 2052 residents; not a loss forecast |

## Intervention economics

Asset file: `outputs/intervention_economics.csv`. Sensitivity file: `outputs/intervention_portfolio_summary.csv`. SQLite tables use the same base names.

| Field | Description |
| --- | --- |
| `untreated_eal_nzd`, `treated_eal_nzd` | Paired +1 m SLR asset EAL before and after illustrative treatment |
| `avoided_annual_loss_nzd` | Untreated minus treated EAL; sole monetised benefit |
| `modelled_loss_reduction_pct` | Avoided annual loss divided by untreated EAL |
| `base_capital_cost_nzd` | Greater of 20% of illustrative value or NZ$50,000 |
| `cost_multiplier` | Sensitivity multiplier applied to base capital cost |
| `capital_cost_nzd` | Multiplied demonstration capital cost |
| `annual_om_cost_nzd` | Annual O&M assumption, 1% of capital cost |
| `analysis_years` | Appraisal horizon |
| `real_discount_rate` | Real discount rate used for present values |
| `pv_avoided_loss_nzd` | Present value of steady annual avoided modelled loss |
| `pv_om_cost_nzd` | Present value of annual O&M |
| `pv_lifecycle_cost_nzd` | Capital cost plus PV O&M |
| `illustrative_npv_nzd` | PV avoided loss minus PV lifecycle cost |
| `illustrative_bcr` | PV avoided loss divided by PV lifecycle cost |
| `break_even_capex_nzd` | Maximum upfront capital cost consistent with BCR 1 under the stated O&M assumption |
| `discounted_payback_year` | First whole year cumulative discounted net benefit is non-negative; blank if not reached |
| `payback_status` | Whether discounted payback occurs within the horizon |
| `assumption_set` | Versioned demonstration assumption identifier |
| `analysis_status` | Explicitly `demonstration_only` |

The portfolio summary repeats the principal economic totals for every configured cost case and discount rate. Portfolio BCR is calculated from aggregate PV benefit and cost, not from the mean of asset BCRs.
