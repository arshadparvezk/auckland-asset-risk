import geopandas as gpd
from shapely.geometry import Point, box

from asset_risk.screening import classify_liquefaction


def test_liquefaction_classification_is_one_row_per_asset_and_uses_highest_overlap():
    assets = gpd.GeoDataFrame(
        {"record_id": ["a", "b", "c"]},
        geometry=[Point(0, 0), Point(10, 10), Point(30, 30)],
        crs="EPSG:2193",
    )
    zones = gpd.GeoDataFrame(
        {"Vulnerability": ["Very Low", "Damage Possible", "Damage Unlikely"]},
        geometry=[box(-2, -2, 2, 2), box(-1, -1, 1, 1), box(8, 8, 12, 12)],
        crs="EPSG:2193",
    )

    result = classify_liquefaction(assets, zones).set_index("record_id")

    assert len(result) == 3
    assert result.loc["a", "liquefaction_vulnerability"] == "Damage Possible"
    assert bool(result.loc["a", "liquefaction_review_flag"])
    assert result.loc["a", "liquefaction_overlap_matches"] == 2
    assert result.loc["b", "liquefaction_vulnerability"] == "Damage Unlikely"
    assert result.loc["c", "liquefaction_vulnerability"] == "Not mapped"
    assert not bool(result.loc["c", "liquefaction_mapped"])
