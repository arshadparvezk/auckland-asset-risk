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

