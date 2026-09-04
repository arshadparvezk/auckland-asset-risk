"""Non-financial multi-hazard screening for public asset locations."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


LIQUEFACTION_ORDER = {
    "Very Low": 1,
    "Damage Unlikely": 2,
    "Damage Possible": 3,
}
LIQUEFACTION_ALIASES = {
    "Possible": "Damage Possible",
    "Liquefaction Damage is Possible": "Damage Possible",
    "Damage Possible": "Damage Possible",
    "Unlikely": "Damage Unlikely",
    "Liquefaction Damage is Unlikely": "Damage Unlikely",
    "Damage Unlikely": "Damage Unlikely",
    "Very Low": "Very Low",
    "Very Low Liquefaction Vulnerability": "Very Low",
}


def classify_liquefaction(
    assets: gpd.GeoDataFrame,
    zones: gpd.GeoDataFrame,
    *,
    category_field: str = "Vulnerability",
) -> pd.DataFrame:
    """Assign one deterministic Council liquefaction category to every asset."""
    if "record_id" not in assets or assets["record_id"].duplicated().any():
        raise ValueError("Assets require unique record_id values")
    if category_field not in zones:
        raise ValueError(f"Liquefaction layer is missing {category_field}")
    if assets.crs is None or zones.crs is None:
        raise ValueError("Assets and liquefaction zones require coordinate systems")

    projected_zones = zones.to_crs(assets.crs)
    valid_zones = projected_zones.loc[
        projected_zones.geometry.notna() & ~projected_zones.geometry.is_empty,
        [category_field, "geometry"],
    ].copy()
    joined = gpd.sjoin(
        assets[["record_id", "geometry"]],
        valid_zones,
        how="left",
        predicate="intersects",
    )
    joined["_mapped_match"] = joined["index_right"].notna()
    raw_category = joined[category_field].fillna("Unclassified mapped area")
    joined["_category"] = raw_category.map(LIQUEFACTION_ALIASES).fillna(raw_category)
    joined.loc[~joined["_mapped_match"], "_category"] = "Not mapped"
    joined["_rank"] = joined["_category"].map(LIQUEFACTION_ORDER).fillna(0)
    joined = joined.sort_values(
        ["record_id", "_rank", "index_right"],
        ascending=[True, False, True],
        na_position="last",
    )
    best = joined.drop_duplicates("record_id", keep="first")[
        ["record_id", "_category", "_mapped_match"]
    ]
    match_counts = (
        joined.loc[joined["_mapped_match"]]
        .groupby("record_id")
        .size()
        .rename("liquefaction_overlap_matches")
    )
    result = pd.DataFrame({"record_id": assets["record_id"].astype(str)}).merge(
        best.assign(record_id=best["record_id"].astype(str)),
        on="record_id",
        how="left",
        validate="one_to_one",
    )
    result = result.merge(match_counts, on="record_id", how="left")
    result["liquefaction_vulnerability"] = result["_category"].fillna("Not mapped")
    result["liquefaction_mapped"] = result["_mapped_match"].fillna(False).astype(bool)
    result["liquefaction_review_flag"] = (
        result["liquefaction_vulnerability"] == "Damage Possible"
    )
    result["liquefaction_overlap_matches"] = (
        result["liquefaction_overlap_matches"].fillna(0).astype(int)
    )
    result["liquefaction_unrecognised_category"] = (
        result["liquefaction_mapped"]
        & ~result["liquefaction_vulnerability"].isin(LIQUEFACTION_ORDER)
    )
    return result.drop(columns=["_category", "_mapped_match"])


def build_asset_hazard_screening(
    assets: gpd.GeoDataFrame,
    liquefaction_zones: gpd.GeoDataFrame,
    register: pd.DataFrame,
    *,
    category_field: str = "Vulnerability",
) -> pd.DataFrame:
    """Combine coastal financial exposure and seismic vulnerability without blending scores."""
    needed_scenarios = {"baseline", "slr_1m"}
    available = set(register["scenario"].astype(str))
    if not needed_scenarios.issubset(available):
        raise ValueError("Baseline and +1 m SLR register rows are required")
    subset = register.loc[register["scenario"].isin(needed_scenarios)].copy()
    if subset.duplicated(["record_id", "scenario"]).any():
        raise ValueError("Risk register contains duplicate asset-scenario rows")
    eal = subset.pivot(
        index="record_id", columns="scenario", values="expected_annual_loss_nzd"
    ).rename(
        columns={
            "baseline": "coastal_current_eal_nzd",
            "slr_1m": "coastal_slr_1m_eal_nzd",
        }
    )
    eal = eal.reset_index()

    asset_columns = [
        "record_id",
        "asset_id",
        "description",
        "site_description",
        "asset_type",
        "asset_group",
        "local_board",
        "planning_area",
        "replacement_value_nzd",
        "criticality_score",
    ]
    asset_columns = [column for column in asset_columns if column in assets.columns]
    result = pd.DataFrame(assets.drop(columns="geometry"))[asset_columns].copy()
    result["record_id"] = result["record_id"].astype(str)
    result = result.merge(
        eal.assign(record_id=eal["record_id"].astype(str)),
        on="record_id",
        how="left",
        validate="one_to_one",
    )
    result = result.merge(
        classify_liquefaction(
            assets, liquefaction_zones, category_field=category_field
        ),
        on="record_id",
        how="left",
        validate="one_to_one",
    )
    result["coastal_current_exposed"] = result["coastal_current_eal_nzd"] > 0
    result["coastal_slr_1m_exposed"] = result["coastal_slr_1m_eal_nzd"] > 0
    result["screening_flag_count"] = (
        result["coastal_slr_1m_exposed"].astype(int)
        + result["liquefaction_review_flag"].astype(int)
    )
    result["screening_attention"] = "No elevated flag"
    result.loc[result["coastal_slr_1m_exposed"], "screening_attention"] = (
        "Coastal inundation only"
    )
    result.loc[result["liquefaction_review_flag"], "screening_attention"] = (
        "Liquefaction review only"
    )
    result.loc[result["screening_flag_count"] == 2, "screening_attention"] = (
        "Dual-hazard review"
    )
    return result.sort_values(
        ["screening_flag_count", "coastal_slr_1m_eal_nzd", "record_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
