"""Download, standardise, and validate Auckland Council ArcGIS data."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, LinearRing, MultiLineString, MultiPolygon, Point, Polygon

ARCGIS_ROOT = (
    "https://services1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services"
)


def _request_json(url: str, params: dict[str, Any], retries: int = 4) -> dict:
    """GET JSON with bounded retries for transient public-service errors."""
    error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=180)
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(payload["error"])
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"ArcGIS request failed after {retries} attempts: {error}")


def _layer_url(service: str, layer: int = 0) -> str:
    return f"{ARCGIS_ROOT}/{service}/FeatureServer/{layer}"


def download_feature_layer(
    service: str,
    output_path: Path,
    *,
    layer: int = 0,
    out_fields: str = "*",
    out_sr: int = 2193,
    simplify_metres: float | None = None,
    use_esri_json: bool = False,
) -> gpd.GeoDataFrame:
    """Download every record from a public ArcGIS feature layer.

    Esri JSON is used for complex hazard polygons because it honours server-side
    generalisation and is materially smaller than the equivalent GeoJSON.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    layer_url = _layer_url(service, layer)
    metadata = _request_json(layer_url, {"f": "json"})
    page_size = int(metadata.get("maxRecordCount", 2000))
    object_id = metadata.get("objectIdField", metadata.get("objectIdFieldName", "OBJECTID"))
    features: list[dict] = []
    offset = 0

    while True:
        params: dict[str, Any] = {
            "where": "1=1",
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": out_sr,
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": object_id,
            "f": "json" if use_esri_json else "geojson",
        }
        if simplify_metres:
            params["maxAllowableOffset"] = simplify_metres
            params["geometryPrecision"] = 0
        page = _request_json(f"{layer_url}/query", params)
        page_features = page.get("features", [])
        features.extend(page_features)
        if len(page_features) < page_size:
            break
        offset += page_size

    if use_esri_json:
        collection = {
            "spatialReference": {"wkid": out_sr},
            "geometryType": metadata.get("geometryType"),
            "features": features,
        }
        output_path.write_text(json.dumps(collection), encoding="utf-8")
        frame = geodataframe_from_esri(collection, crs=f"EPSG:{out_sr}")
    else:
        collection = {
            "type": "FeatureCollection",
            "name": service,
            "crs": {"type": "name", "properties": {"name": f"EPSG:{out_sr}"}},
            "features": features,
        }
        output_path.write_text(json.dumps(collection), encoding="utf-8")
        frame = gpd.GeoDataFrame.from_features(features, crs=f"EPSG:{out_sr}")
    return frame


def _polygon_from_rings(rings: list[list[list[float]]]):
    """Convert ArcGIS clockwise shells/counter-clockwise holes to Shapely."""
    shells: list[LinearRing] = []
    holes: list[LinearRing] = []
    for coordinates in rings:
        if len(coordinates) < 4:
            continue
        ring = LinearRing(coordinates)
        (holes if ring.is_ccw else shells).append(ring)
    if not shells and holes:
        # Defensive fallback for sources that do not follow ArcGIS orientation.
        shells = [max(holes, key=lambda ring: Polygon(ring).area)]
        holes = [ring for ring in holes if ring is not shells[0]]
    polygons = []
    for shell in shells:
        shell_polygon = Polygon(shell)
        contained_holes = [
            list(hole.coords)
            for hole in holes
            if shell_polygon.covers(Polygon(hole).representative_point())
        ]
        polygons.append(Polygon(shell.coords, holes=contained_holes))
    if not polygons:
        return Polygon()
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _esri_geometry(geometry: dict | None):
    if not geometry:
        return None
    if "x" in geometry and "y" in geometry:
        return Point(geometry["x"], geometry["y"])
    if "rings" in geometry:
        return _polygon_from_rings(geometry["rings"])
    if "paths" in geometry:
        paths = [LineString(path) for path in geometry["paths"] if len(path) >= 2]
        if not paths:
            return LineString()
        return paths[0] if len(paths) == 1 else MultiLineString(paths)
    raise ValueError(f"Unsupported Esri geometry keys: {sorted(geometry)}")


def geodataframe_from_esri(payload: dict, crs: str) -> gpd.GeoDataFrame:
    records = []
    geometries = []
    for feature in payload.get("features", []):
        records.append(feature.get("attributes", {}))
        geometries.append(_esri_geometry(feature.get("geometry")))
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def load_or_download_assets(config: dict, raw_dir: Path, refresh: bool) -> gpd.GeoDataFrame:
    source = config["data_sources"]["assets"]
    path = raw_dir / "park_asset_location.geojson"
    if refresh or not path.exists():
        assets = download_feature_layer(
            source["service"], path, layer=int(source.get("layer", 0))
        )
    else:
        assets = gpd.read_file(path)
    assets.columns = [str(c).strip() for c in assets.columns]
    assets = assets.rename(
        columns={
            "AssetType": "asset_type",
            "AssetGroup": "asset_group",
            "SAPID": "asset_id",
            "DESCRIPTION": "description",
            "SITEDESCRIPTION": "site_description",
            "LOCALBOARD": "local_board",
            "CITY": "city",
        }
    )
    assets["asset_id"] = assets["asset_id"].fillna(
        assets.get("GlobalID", assets.index.astype(str))
    )
    if "OBJECTID" in assets.columns:
        assets["record_id"] = "park-" + assets["OBJECTID"].astype(str)
    else:
        assets["record_id"] = "park-row-" + assets.index.astype(str)
    assets["asset_type"] = assets["asset_type"].fillna("Unknown")
    assets["local_board"] = assets["local_board"].fillna("Unknown")
    return assets.to_crs(config["project"]["crs"])


def load_or_download_hazard(
    service: str,
    raw_dir: Path,
    *,
    refresh: bool,
    simplify_metres: float,
) -> gpd.GeoDataFrame:
    path = raw_dir / f"{service}.json"
    if refresh or not path.exists():
        hazard = download_feature_layer(
            service,
            path,
            out_fields="OBJECTID,Hazard,ARI_years,AEP_percent,SeaLevelRiseScenario,Status",
            simplify_metres=simplify_metres,
            use_esri_json=True,
        )
    else:
        hazard = geodataframe_from_esri(json.loads(path.read_text(encoding="utf-8")), "EPSG:2193")
    return hazard.to_crs("EPSG:2193")


def load_or_download_screening_layer(
    source: dict,
    raw_dir: Path,
    *,
    refresh: bool,
    simplify_metres: float,
) -> gpd.GeoDataFrame:
    """Load a configured public polygon layer used for non-financial screening."""
    service = str(source["service"])
    layer = int(source.get("layer", 0))
    path = raw_dir / f"{service}.json"
    out_fields = ",".join(source.get("out_fields", ["*"]))
    if refresh or not path.exists():
        frame = download_feature_layer(
            service,
            path,
            layer=layer,
            out_fields=out_fields,
            simplify_metres=simplify_metres,
            use_esri_json=True,
        )
    else:
        frame = geodataframe_from_esri(
            json.loads(path.read_text(encoding="utf-8")), "EPSG:2193"
        )
    return frame.to_crs("EPSG:2193")


def data_quality_report(assets: gpd.GeoDataFrame, known_types: set[str]) -> dict:
    """Return auditable data-quality checks without silently dropping records."""
    critical = ["asset_id", "asset_type", "asset_group", "local_board", "geometry"]
    missing = {
        column: int(assets[column].isna().sum())
        for column in critical
        if column in assets.columns
    }
    duplicate_ids = int(assets["asset_id"].duplicated(keep=False).sum())
    invalid_geometry = int((~assets.geometry.is_valid).sum())
    empty_geometry = int(assets.geometry.is_empty.sum())
    unknown_types = sorted(set(assets["asset_type"].dropna()) - known_types)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": int(len(assets)),
        "missing_by_critical_field": missing,
        "duplicate_asset_id_records": duplicate_ids,
        "invalid_geometry_records": invalid_geometry,
        "empty_geometry_records": empty_geometry,
        "unmapped_asset_types": unknown_types,
        "validation_note": (
            "Records are retained and flagged. Public data is indicative and should be "
            "verified before operational or investment decisions."
        ),
    }


def write_clean_assets(assets: gpd.GeoDataFrame, processed_dir: Path) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / "assets_clean.parquet"
    assets.to_parquet(path, index=False)
    return path
