"""Auckland Growth Scenario context for portfolio planning."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


REGIONAL_TOTAL = "Auckland Region forecast totals"
UNMAPPED_AREA = "Unmapped / not supplied"
COMBINED_ISLAND_AREA = "Waiheke-Great Barrier"


def planning_area_for_board(local_board: object) -> str:
    """Map asset-board labels to the published AGS23v1.1 geography."""
    if pd.isna(local_board):
        return UNMAPPED_AREA
    board = str(local_board).strip()
    if board in {"", "Unknown", "NOT SUPPLIED"}:
        return UNMAPPED_AREA
    if board in {"Waiheke", "Aotea/Great Barrier"}:
        return COMBINED_ISLAND_AREA
    return board


def assign_planning_area(assets: pd.DataFrame) -> pd.DataFrame:
    result = assets.copy()
    result["planning_area"] = result["local_board"].map(planning_area_for_board)
    return result


def load_growth_reference(path: Path, *, start_year: int, end_year: int) -> pd.DataFrame:
    """Load and validate the compact, versioned AGS23v1.1 extract."""
    frame = pd.read_csv(path)
    measures = ("households", "population", "employment")
    required = {"local_board_group"}
    for measure in measures:
        required.update({f"{measure}_{start_year}", f"{measure}_{end_year}"})
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Growth reference is missing columns: {missing}")
    if frame["local_board_group"].duplicated().any():
        raise ValueError("Growth reference contains duplicate local-board groups")
    if REGIONAL_TOTAL not in set(frame["local_board_group"]):
        raise ValueError("Growth reference is missing the Auckland regional total")

    years = end_year - start_year
    if years <= 0:
        raise ValueError("Growth comparison end year must be after the start year")
    for measure in measures:
        start = pd.to_numeric(frame[f"{measure}_{start_year}"], errors="coerce")
        end = pd.to_numeric(frame[f"{measure}_{end_year}"], errors="coerce")
        if start.isna().any() or end.isna().any() or (start <= 0).any() or (end <= 0).any():
            raise ValueError(f"{measure.title()} reference values must be positive")
        frame[f"{measure}_growth_rate"] = end / start - 1
        frame[f"{measure}_cagr"] = (end / start) ** (1 / years) - 1
    return frame


def build_growth_context(
    register: pd.DataFrame,
    growth_reference: pd.DataFrame,
) -> pd.DataFrame:
    """Join scenario-level portfolio evidence to Council planning projections."""
    required = {
        "record_id",
        "scenario",
        "planning_area",
        "replacement_value_nzd",
        "expected_annual_loss_nzd",
    }
    missing = sorted(required - set(register.columns))
    if missing:
        raise ValueError(f"Risk register is missing growth-context columns: {missing}")

    regional = growth_reference.loc[
        growth_reference["local_board_group"] == REGIONAL_TOTAL
    ].iloc[0]
    board_reference = growth_reference.loc[
        growth_reference["local_board_group"] != REGIONAL_TOTAL
    ].copy()
    grouped = (
        register.groupby(["scenario", "planning_area"], as_index=False, dropna=False)
        .agg(
            portfolio_assets=("record_id", "nunique"),
            assets_with_modelled_loss=(
                "expected_annual_loss_nzd",
                lambda values: int((values > 0).sum()),
            ),
            illustrative_portfolio_value_nzd=("replacement_value_nzd", "sum"),
            expected_annual_loss_nzd=("expected_annual_loss_nzd", "sum"),
        )
    )
    context = grouped.merge(
        board_reference,
        left_on="planning_area",
        right_on="local_board_group",
        how="left",
        validate="many_to_one",
    )
    context["growth_data_mapped"] = context["population_growth_rate"].notna()
    context["auckland_population_growth_rate"] = float(
        regional["population_growth_rate"]
    )
    context["above_auckland_population_growth"] = (
        context["growth_data_mapped"]
        & (
            context["population_growth_rate"]
            > context["auckland_population_growth_rate"]
        )
    )
    context["future_population_eal_per_1000_nzd"] = np.where(
        context["population_2052"].fillna(0) > 0,
        context["expected_annual_loss_nzd"] / context["population_2052"] * 1_000,
        np.nan,
    )
    return context.sort_values(
        ["scenario", "expected_annual_loss_nzd"], ascending=[True, False]
    ).reset_index(drop=True)
