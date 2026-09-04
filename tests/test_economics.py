from pathlib import Path

import pandas as pd
import pytest
import yaml

from asset_risk.economics import (
    annuity_factor,
    build_intervention_economics,
    build_intervention_sensitivity,
    discounted_payback_year,
    summarize_intervention_portfolio,
)


ROOT = Path(__file__).resolve().parents[1]


def economics_config() -> dict:
    with (ROOT / "config" / "model.yml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["intervention_economics"]


def paired_register() -> pd.DataFrame:
    rows = []
    for record_id, value, untreated, treated in (
        ("record-1", 100_000, 4_000, 2_600),
        ("record-2", 1_000_000, 20_000, 13_000),
    ):
        for scenario, eal in (("slr_1m", untreated), ("slr_1m_mitigated", treated)):
            rows.append(
                {
                    "record_id": record_id,
                    "asset_id": "duplicate-business-id",
                    "asset_type": "Test asset",
                    "local_board": "Test board",
                    "replacement_value_nzd": value,
                    "expected_annual_loss_nzd": eal,
                    "scenario": scenario,
                }
            )
    return pd.DataFrame(rows)


def test_annuity_factor_handles_zero_and_positive_discount_rates():
    assert annuity_factor(0, 5) == 5
    assert annuity_factor(0.05, 30) == pytest.approx(15.372451, rel=1e-6)
    with pytest.raises(ValueError):
        annuity_factor(-0.01, 30)


def test_intervention_economics_pairs_on_record_id_and_applies_cost_floor():
    result = build_intervention_economics(paired_register(), economics_config())

    assert set(result["record_id"]) == {"record-1", "record-2"}
    first = result.set_index("record_id").loc["record-1"]
    assert first["capital_cost_nzd"] == pytest.approx(50_000)
    assert first["avoided_annual_loss_nzd"] == pytest.approx(1_400)
    assert first["modelled_loss_reduction_pct"] == pytest.approx(0.35)
    assert result["asset_id"].nunique() == 1


def test_portfolio_bcr_is_ratio_of_totals_and_cost_sensitivity_is_monotonic():
    cfg = economics_config()
    central = build_intervention_economics(paired_register(), cfg)
    summary = summarize_intervention_portfolio(
        central,
        cost_case="central",
        cost_multiplier=1.0,
        real_discount_rate=0.05,
        analysis_years=30,
    )
    assert summary["illustrative_bcr"] == pytest.approx(
        central["pv_avoided_loss_nzd"].sum()
        / central["pv_lifecycle_cost_nzd"].sum()
    )

    sensitivity = build_intervention_sensitivity(paired_register(), cfg)
    at_five_percent = sensitivity.loc[
        sensitivity["real_discount_rate"].round(4) == 0.05
    ].sort_values("cost_multiplier")
    assert at_five_percent["illustrative_bcr"].is_monotonic_decreasing
    assert at_five_percent["illustrative_npv_nzd"].is_monotonic_decreasing


def test_discounted_payback_reports_achieved_and_not_achieved_cases():
    assert discounted_payback_year(
        capital_cost_nzd=100,
        annual_benefit_nzd=60,
        annual_om_cost_nzd=10,
        real_discount_rate=0,
        analysis_years=5,
    ) == 2
    assert (
        discounted_payback_year(
            capital_cost_nzd=100,
            annual_benefit_nzd=10,
            annual_om_cost_nzd=10,
            real_discount_rate=0.05,
            analysis_years=30,
        )
        is None
    )


def test_invalid_scenario_pairing_fails_loudly():
    register = paired_register()
    duplicate = pd.concat([register, register.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate record_id"):
        build_intervention_economics(duplicate, economics_config())

    higher_treated = register.copy()
    higher_treated.loc[
        (higher_treated["record_id"] == "record-1")
        & (higher_treated["scenario"] == "slr_1m_mitigated"),
        "expected_annual_loss_nzd",
    ] = 5_000
    with pytest.raises(ValueError, match="Treated EAL"):
        build_intervention_economics(higher_treated, economics_config())


def test_committed_economics_reconciles_with_scenario_totals():
    economics = pd.read_csv(ROOT / "outputs" / "intervention_economics.csv")
    summary = pd.read_csv(ROOT / "outputs" / "scenario_summary.csv").set_index(
        "scenario"
    )
    expected_avoided = (
        summary.loc["slr_1m", "expected_annual_loss_nzd"]
        - summary.loc["slr_1m_mitigated", "expected_annual_loss_nzd"]
    )
    assert economics["avoided_annual_loss_nzd"].sum() == pytest.approx(
        expected_avoided
    )
