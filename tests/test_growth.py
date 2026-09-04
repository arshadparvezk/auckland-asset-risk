from pathlib import Path

import pandas as pd
import pytest

from asset_risk.growth import (
    COMBINED_ISLAND_AREA,
    REGIONAL_TOTAL,
    assign_planning_area,
    build_growth_context,
    load_growth_reference,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference" / "ags23v1_1_local_board_2022_2052.csv"


def test_growth_reference_matches_published_regional_benchmark():
    growth = load_growth_reference(REFERENCE, start_year=2022, end_year=2052)
    regional = growth.set_index("local_board_group").loc[REGIONAL_TOTAL]
    assert regional["population_2022"] == 1_695_741
    assert regional["population_2052"] == 2_293_485
    assert regional["population_growth_rate"] == pytest.approx(0.352497, rel=1e-5)


def test_island_boards_share_one_growth_geography_without_duplicating_population():
    assets = pd.DataFrame(
        {
            "local_board": ["Waiheke", "Aotea/Great Barrier", "Unknown"],
            "record_id": ["a", "b", "c"],
        }
    )
    assigned = assign_planning_area(assets)
    assert assigned.loc[:1, "planning_area"].tolist() == [
        COMBINED_ISLAND_AREA,
        COMBINED_ISLAND_AREA,
    ]

    register = assigned.assign(
        scenario="slr_1m",
        replacement_value_nzd=[100, 200, 300],
        expected_annual_loss_nzd=[10, 20, 0],
    )
    growth = load_growth_reference(REFERENCE, start_year=2022, end_year=2052)
    context = build_growth_context(register, growth)
    island = context.loc[context["planning_area"] == COMBINED_ISLAND_AREA].iloc[0]
    assert island["portfolio_assets"] == 2
    assert island["population_2022"] == 10_500
    assert island["population_2052"] == 11_698
