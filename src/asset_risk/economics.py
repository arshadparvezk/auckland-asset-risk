"""Illustrative lifecycle economics for the modelled resilience treatment."""

from __future__ import annotations

import numpy as np
import pandas as pd


def annuity_factor(real_discount_rate: float, analysis_years: int) -> float:
    """Return the present-value factor for equal end-of-year real cash flows."""
    rate = float(real_discount_rate)
    years = int(analysis_years)
    if years <= 0:
        raise ValueError("Analysis years must be positive")
    if rate < 0:
        raise ValueError("Real discount rate cannot be negative")
    if rate == 0:
        return float(years)
    return float((1 - (1 + rate) ** -years) / rate)


def discounted_payback_year(
    *,
    capital_cost_nzd: float,
    annual_benefit_nzd: float,
    annual_om_cost_nzd: float,
    real_discount_rate: float,
    analysis_years: int,
) -> int | None:
    """Return the first whole year with non-negative discounted cash flow."""
    capital = float(capital_cost_nzd)
    annual_net = float(annual_benefit_nzd) - float(annual_om_cost_nzd)
    rate = float(real_discount_rate)
    years = int(analysis_years)
    if capital < 0:
        raise ValueError("Capital cost cannot be negative")
    if annual_net <= 0:
        return None
    cumulative = -capital
    for year in range(1, years + 1):
        cumulative += annual_net / (1 + rate) ** year
        if cumulative >= -1e-9:
            return year
    return None


def _paired_scenarios(register: pd.DataFrame, economics_cfg: dict) -> pd.DataFrame:
    untreated_name = str(economics_cfg["untreated_scenario"])
    treated_name = str(economics_cfg["treated_scenario"])
    required = {
        "record_id",
        "asset_id",
        "asset_type",
        "local_board",
        "replacement_value_nzd",
        "expected_annual_loss_nzd",
        "scenario",
    }
    missing = sorted(required - set(register.columns))
    if missing:
        raise ValueError(f"Risk register is missing required columns: {missing}")

    untreated = register.loc[register["scenario"] == untreated_name].copy()
    treated = register.loc[register["scenario"] == treated_name].copy()
    if untreated.empty or treated.empty:
        raise ValueError("Both untreated and treated scenarios are required")
    for label, frame in ((untreated_name, untreated), (treated_name, treated)):
        if frame["record_id"].duplicated().any():
            raise ValueError(f"Scenario {label} contains duplicate record_id values")

    untreated_ids = set(untreated["record_id"].astype(str))
    treated_ids = set(treated["record_id"].astype(str))
    if untreated_ids != treated_ids:
        raise ValueError("Untreated and treated scenarios must contain identical record sets")

    optional = [
        "description",
        "site_description",
        "asset_group",
        "planning_area",
        "criticality_score",
    ]
    attributes = [column for column in optional if column in untreated.columns]
    paired = untreated[
        [
            "record_id",
            "asset_id",
            "asset_type",
            "local_board",
            "replacement_value_nzd",
            *attributes,
            "expected_annual_loss_nzd",
        ]
    ].copy()
    paired["record_id"] = paired["record_id"].astype(str)
    paired = paired.rename(
        columns={"expected_annual_loss_nzd": "untreated_eal_nzd"}
    )

    treated_lookup = treated.assign(record_id=treated["record_id"].astype(str)).set_index(
        "record_id"
    )
    paired["treated_eal_nzd"] = paired["record_id"].map(
        treated_lookup["expected_annual_loss_nzd"]
    )
    treated_values = paired["record_id"].map(treated_lookup["replacement_value_nzd"])
    replacement_values = pd.to_numeric(paired["replacement_value_nzd"], errors="coerce")
    if replacement_values.isna().any() or (replacement_values <= 0).any():
        raise ValueError("Replacement values must be present and positive")
    if not np.allclose(replacement_values, treated_values.astype(float)):
        raise ValueError("Replacement values differ between treatment scenarios")

    tolerance = 1e-6
    if (
        paired["treated_eal_nzd"].astype(float)
        > paired["untreated_eal_nzd"].astype(float) + tolerance
    ).any():
        raise ValueError("Treated EAL cannot exceed untreated EAL")
    paired["avoided_annual_loss_nzd"] = (
        paired["untreated_eal_nzd"].astype(float)
        - paired["treated_eal_nzd"].astype(float)
    ).clip(lower=0.0)
    return paired.loc[paired["avoided_annual_loss_nzd"] > tolerance].copy()


def build_intervention_economics(
    register: pd.DataFrame,
    economics_cfg: dict,
    *,
    cost_multiplier: float = 1.0,
    real_discount_rate: float | None = None,
) -> pd.DataFrame:
    """Evaluate candidate assets under explicit, replaceable demonstration assumptions."""
    appraisal = economics_cfg["appraisal"]
    capital_cfg = economics_cfg["capital_cost"]
    operations_cfg = economics_cfg["operations"]
    years = int(appraisal["analysis_years"])
    rate = (
        float(appraisal["real_discount_rate"])
        if real_discount_rate is None
        else float(real_discount_rate)
    )
    fraction = float(capital_cfg["fraction_of_replacement_value"])
    minimum = float(capital_cfg["minimum_nzd"])
    om_rate = float(operations_cfg["annual_om_fraction_of_capex"])
    multiplier = float(cost_multiplier)
    if fraction < 0 or minimum < 0 or om_rate < 0:
        raise ValueError("Cost fraction, cost floor, and O&M rate cannot be negative")
    if multiplier <= 0:
        raise ValueError("Cost multiplier must be positive")

    factor = annuity_factor(rate, years)
    result = _paired_scenarios(register, economics_cfg)
    if result.empty:
        return result.assign(
            capital_cost_nzd=pd.Series(dtype=float),
            annual_om_cost_nzd=pd.Series(dtype=float),
            illustrative_bcr=pd.Series(dtype=float),
        )

    result["modelled_loss_reduction_pct"] = (
        result["avoided_annual_loss_nzd"] / result["untreated_eal_nzd"]
    )
    result["base_capital_cost_nzd"] = np.maximum(
        result["replacement_value_nzd"].astype(float) * fraction,
        minimum,
    )
    result["cost_multiplier"] = multiplier
    result["capital_cost_nzd"] = result["base_capital_cost_nzd"] * multiplier
    result["annual_om_cost_nzd"] = result["capital_cost_nzd"] * om_rate
    result["analysis_years"] = years
    result["real_discount_rate"] = rate
    result["pv_avoided_loss_nzd"] = result["avoided_annual_loss_nzd"] * factor
    result["pv_om_cost_nzd"] = result["annual_om_cost_nzd"] * factor
    result["pv_lifecycle_cost_nzd"] = (
        result["capital_cost_nzd"] + result["pv_om_cost_nzd"]
    )
    if (result["pv_lifecycle_cost_nzd"] <= 0).any():
        raise ValueError("Present-value lifecycle cost must be positive")
    result["illustrative_npv_nzd"] = (
        result["pv_avoided_loss_nzd"] - result["pv_lifecycle_cost_nzd"]
    )
    result["illustrative_bcr"] = (
        result["pv_avoided_loss_nzd"] / result["pv_lifecycle_cost_nzd"]
    )
    result["break_even_capex_nzd"] = result["pv_avoided_loss_nzd"] / (
        1 + om_rate * factor
    )
    payback = [
        discounted_payback_year(
            capital_cost_nzd=row.capital_cost_nzd,
            annual_benefit_nzd=row.avoided_annual_loss_nzd,
            annual_om_cost_nzd=row.annual_om_cost_nzd,
            real_discount_rate=rate,
            analysis_years=years,
        )
        for row in result.itertuples()
    ]
    result["discounted_payback_year"] = pd.array(payback, dtype="Int64")
    result["payback_status"] = np.where(
        result["discounted_payback_year"].notna(),
        "achieved within horizon",
        "not achieved within horizon",
    )
    result["assumption_set"] = economics_cfg["assumption_set"]
    result["analysis_status"] = economics_cfg["status"]
    return result.sort_values(
        ["illustrative_npv_nzd", "record_id"], ascending=[False, True]
    ).reset_index(drop=True)


def summarize_intervention_portfolio(
    economics: pd.DataFrame,
    *,
    cost_case: str,
    cost_multiplier: float,
    real_discount_rate: float,
    analysis_years: int,
) -> dict:
    """Aggregate benefits and costs before calculating portfolio economics."""
    benefit = float(economics.get("pv_avoided_loss_nzd", pd.Series(dtype=float)).sum())
    lifecycle_cost = float(
        economics.get("pv_lifecycle_cost_nzd", pd.Series(dtype=float)).sum()
    )
    capital = float(economics.get("capital_cost_nzd", pd.Series(dtype=float)).sum())
    annual_benefit = float(
        economics.get("avoided_annual_loss_nzd", pd.Series(dtype=float)).sum()
    )
    annual_om = float(economics.get("annual_om_cost_nzd", pd.Series(dtype=float)).sum())
    payback = discounted_payback_year(
        capital_cost_nzd=capital,
        annual_benefit_nzd=annual_benefit,
        annual_om_cost_nzd=annual_om,
        real_discount_rate=real_discount_rate,
        analysis_years=analysis_years,
    )
    return {
        "cost_case": str(cost_case),
        "cost_multiplier": float(cost_multiplier),
        "real_discount_rate": float(real_discount_rate),
        "analysis_years": int(analysis_years),
        "candidate_assets": int(len(economics)),
        "positive_npv_assets": int(
            (economics.get("illustrative_npv_nzd", pd.Series(dtype=float)) > 0).sum()
        ),
        "avoided_annual_loss_nzd": annual_benefit,
        "capital_cost_nzd": capital,
        "annual_om_cost_nzd": annual_om,
        "pv_avoided_loss_nzd": benefit,
        "pv_lifecycle_cost_nzd": lifecycle_cost,
        "illustrative_npv_nzd": benefit - lifecycle_cost,
        "illustrative_bcr": benefit / lifecycle_cost if lifecycle_cost else np.nan,
        "discounted_payback_year": payback,
        "payback_status": (
            "achieved within horizon" if payback is not None else "not achieved within horizon"
        ),
    }


def build_intervention_sensitivity(
    register: pd.DataFrame, economics_cfg: dict
) -> pd.DataFrame:
    """Build a transparent cost-by-discount-rate sensitivity matrix."""
    years = int(economics_cfg["appraisal"]["analysis_years"])
    rows: list[dict] = []
    for cost_case, multiplier in economics_cfg["sensitivity"][
        "cost_multipliers"
    ].items():
        for rate in economics_cfg["sensitivity"]["real_discount_rates"]:
            economics = build_intervention_economics(
                register,
                economics_cfg,
                cost_multiplier=float(multiplier),
                real_discount_rate=float(rate),
            )
            rows.append(
                summarize_intervention_portfolio(
                    economics,
                    cost_case=cost_case,
                    cost_multiplier=float(multiplier),
                    real_discount_rate=float(rate),
                    analysis_years=years,
                )
            )
    return pd.DataFrame(rows).sort_values(
        ["cost_multiplier", "real_discount_rate"]
    ).reset_index(drop=True)
