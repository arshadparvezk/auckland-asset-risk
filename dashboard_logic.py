"""Pure calculation helpers for the Streamlit decision dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd


def scoped_intervention_summary(
    economics: pd.DataFrame,
    record_ids: list[str],
    *,
    cost_multiplier: float = 1.0,
    real_discount_rate: float = 0.05,
) -> tuple[pd.DataFrame, dict]:
    """Return asset economics and a correctly aggregated portfolio summary."""
    scoped = economics.loc[economics["record_id"].astype(str).isin(record_ids)].copy()
    multiplier = float(cost_multiplier)
    rate = float(real_discount_rate)
    if multiplier <= 0 or rate < 0:
        raise ValueError("Cost multiplier must be positive and discount rate non-negative")
    if not scoped.empty:
        years = int(scoped["analysis_years"].iloc[0])
        om_rate = float(
            (
                scoped["annual_om_cost_nzd"]
                / scoped["capital_cost_nzd"].replace(0, np.nan)
            )
            .dropna()
            .iloc[0]
        )
        factor = years if rate == 0 else (1 - (1 + rate) ** -years) / rate
        scoped["cost_multiplier"] = multiplier
        scoped["real_discount_rate"] = rate
        scoped["capital_cost_nzd"] = scoped["base_capital_cost_nzd"] * multiplier
        scoped["annual_om_cost_nzd"] = scoped["capital_cost_nzd"] * om_rate
        scoped["pv_avoided_loss_nzd"] = scoped["avoided_annual_loss_nzd"] * factor
        scoped["pv_om_cost_nzd"] = scoped["annual_om_cost_nzd"] * factor
        scoped["pv_lifecycle_cost_nzd"] = (
            scoped["capital_cost_nzd"] + scoped["pv_om_cost_nzd"]
        )
        scoped["illustrative_npv_nzd"] = (
            scoped["pv_avoided_loss_nzd"] - scoped["pv_lifecycle_cost_nzd"]
        )
        scoped["illustrative_bcr"] = (
            scoped["pv_avoided_loss_nzd"] / scoped["pv_lifecycle_cost_nzd"]
        )
    else:
        years = 0
    annual_benefit = float(scoped["avoided_annual_loss_nzd"].sum())
    capital = float(scoped["capital_cost_nzd"].sum())
    annual_om = float(scoped["annual_om_cost_nzd"].sum())
    pv_benefit = float(scoped["pv_avoided_loss_nzd"].sum())
    pv_cost = float(scoped["pv_lifecycle_cost_nzd"].sum())
    payback = None
    cumulative = -capital
    annual_net = annual_benefit - annual_om
    if scoped.empty:
        payback_status = "No candidates in view"
    elif annual_net <= 0:
        payback_status = "Not achieved within horizon"
    else:
        for year in range(1, years + 1):
            cumulative += annual_net / (1 + rate) ** year
            if cumulative >= -1e-9:
                payback = year
                break
        payback_status = (
            f"Year {payback}" if payback is not None else "Not achieved within horizon"
        )
    return scoped, {
        "candidate_assets": int(len(scoped)),
        "positive_npv_assets": int((scoped["illustrative_npv_nzd"] > 0).sum()),
        "avoided_annual_loss_nzd": annual_benefit,
        "capital_cost_nzd": capital,
        "annual_om_cost_nzd": annual_om,
        "pv_avoided_loss_nzd": pv_benefit,
        "pv_lifecycle_cost_nzd": pv_cost,
        "illustrative_npv_nzd": pv_benefit - pv_cost,
        "illustrative_bcr": pv_benefit / pv_cost if pv_cost else np.nan,
        "discounted_payback_year": payback,
        "payback_status": payback_status,
        "analysis_years": years,
        "real_discount_rate": rate,
    }


def scoped_growth_context(
    view: pd.DataFrame,
    growth_context: pd.DataFrame,
    scenario: str,
) -> pd.DataFrame:
    """Recalculate portfolio metrics for the selected cohort, retaining source projections."""
    source_columns = [
        "planning_area",
        "growth_data_mapped",
        "households_2022",
        "households_2052",
        "population_2022",
        "population_2052",
        "employment_2022",
        "employment_2052",
        "households_growth_rate",
        "population_growth_rate",
        "employment_growth_rate",
        "auckland_population_growth_rate",
        "above_auckland_population_growth",
    ]
    reference = growth_context.loc[growth_context["scenario"] == scenario, source_columns]
    reference = reference.drop_duplicates("planning_area")
    if view.empty:
        columns = [
            "planning_area",
            "assets_in_view",
            "assets_with_modelled_loss",
            "illustrative_portfolio_value_nzd",
            "expected_annual_loss_nzd",
            *source_columns[1:],
        ]
        return pd.DataFrame(columns=columns)
    grouped = (
        view.groupby("planning_area", as_index=False, dropna=False)
        .agg(
            assets_in_view=("record_id", "nunique"),
            assets_with_modelled_loss=(
                "expected_annual_loss_nzd",
                lambda values: int((values > 0).sum()),
            ),
            illustrative_portfolio_value_nzd=("replacement_value_nzd", "sum"),
            expected_annual_loss_nzd=("expected_annual_loss_nzd", "sum"),
        )
    )
    result = grouped.merge(reference, on="planning_area", how="left", validate="one_to_one")
    result["growth_data_mapped"] = result["growth_data_mapped"].fillna(False).astype(bool)
    result["growth_and_loss_focus"] = (
        result["expected_annual_loss_nzd"].gt(0)
        & result["above_auckland_population_growth"].fillna(False).astype(bool)
    )
    return result.sort_values(
        ["growth_and_loss_focus", "expected_annual_loss_nzd"],
        ascending=[False, False],
    ).reset_index(drop=True)
