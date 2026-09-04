-- Highest-priority assets for an investment-planning workshop.
SELECT
  asset_id,
  description,
  asset_type,
  local_board,
  expected_annual_loss_nzd,
  criticality_score,
  priority_score,
  risk_band
FROM asset_risk_register
WHERE scenario = 'slr_1m'
ORDER BY priority_score DESC
LIMIT 25;

-- Scenario comparison by local board.
SELECT
  local_board,
  scenario,
  COUNT(*) AS asset_count,
  SUM(CASE WHEN expected_annual_loss_nzd > 0 THEN 1 ELSE 0 END) AS exposed_asset_count,
  SUM(expected_annual_loss_nzd) AS expected_annual_loss_nzd
FROM asset_risk_register
GROUP BY local_board, scenario
ORDER BY expected_annual_loss_nzd DESC;

-- Data-quality check: duplicate business identifiers.
SELECT asset_id, COUNT(*) AS record_count
FROM assets
GROUP BY asset_id
HAVING COUNT(*) > 1
ORDER BY record_count DESC;

-- Multi-hazard review queue: coastal financial exposure plus liquefaction screening.
SELECT
  asset_id,
  description,
  local_board,
  coastal_slr_1m_exposed,
  liquefaction_vulnerability,
  liquefaction_review_flag,
  screening_flag_count,
  screening_attention
FROM asset_hazard_screening
WHERE screening_flag_count > 0
ORDER BY coastal_slr_1m_exposed DESC, local_board, asset_id;

-- Growth context remains a planning lens and is not multiplied into EAL.
SELECT
  planning_area,
  population_2022,
  population_2052,
  population_growth_rate,
  portfolio_assets,
  assets_with_modelled_loss,
  expected_annual_loss_nzd
FROM local_board_growth_context
WHERE scenario = 'slr_1m'
ORDER BY population_growth_rate DESC;

-- Intervention sensitivity: compare lifecycle value under every assumption set.
SELECT
  cost_case,
  cost_multiplier,
  real_discount_rate,
  candidate_assets,
  pv_avoided_loss_nzd,
  pv_lifecycle_cost_nzd,
  illustrative_npv_nzd,
  illustrative_bcr,
  discounted_payback_year
FROM intervention_portfolio_summary
ORDER BY cost_multiplier, real_discount_rate;
