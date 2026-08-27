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

