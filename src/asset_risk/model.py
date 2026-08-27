"""Exposure, uncertainty, and financial-loss calculations."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely


@dataclass(frozen=True)
class EventLoss:
    scenario: str
    aep: float
    expected_loss_nzd: float
    p50_loss_nzd: float
    p90_loss_nzd: float
    exposed_assets: int
    exposed_value_nzd: float


def beta_parameters(mean: float, concentration: float) -> tuple[float, float]:
    if not 0 < mean < 1:
        raise ValueError("Damage-ratio mean must lie strictly between zero and one")
    if concentration <= 0:
        raise ValueError("Beta concentration must be positive")
    return mean * concentration, (1 - mean) * concentration


def assign_financial_assumptions(assets: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    values = config["replacement_values_nzd"]
    scores = config["criticality_scores"]
    result = assets.copy()
    result["replacement_value_nzd"] = result["asset_type"].map(values).fillna(
        values["__default__"]
    )
    result["criticality_score"] = (
        result["asset_type"].map(scores).fillna(scores["__default__"]).astype(int)
    )
    return result


def calculate_exposure(
    assets: gpd.GeoDataFrame,
    hazard: gpd.GeoDataFrame,
) -> pd.Series:
    """Test each asset point against the unioned hazard extent."""
    valid = hazard.geometry[~hazard.geometry.is_empty & hazard.geometry.notna()]
    if valid.empty:
        return pd.Series(False, index=assets.index)
    repaired = shapely.make_valid(valid.array)
    footprint = shapely.union_all(repaired)
    return pd.Series(shapely.intersects(assets.geometry.array, footprint), index=assets.index)


def monte_carlo_event_loss(
    exposed_assets: pd.DataFrame,
    *,
    damage_mean: float,
    damage_concentration: float,
    mitigation_factor: float,
    iterations: int,
    rng: np.random.Generator,
    value_sigma: float,
    systematic_sigma: float,
) -> np.ndarray:
    if exposed_assets.empty:
        return np.zeros(iterations)
    base_values = exposed_assets["replacement_value_nzd"].to_numpy(float)
    alpha, beta = beta_parameters(damage_mean, damage_concentration)
    # Lognormal means are corrected so their expectation is one.
    value_factors = rng.lognormal(
        mean=-0.5 * value_sigma**2,
        sigma=value_sigma,
        size=(iterations, len(base_values)),
    )
    damage = rng.beta(alpha, beta, size=(iterations, len(base_values)))
    systematic = rng.lognormal(
        mean=-0.5 * systematic_sigma**2,
        sigma=systematic_sigma,
        size=(iterations, 1),
    )
    losses = base_values * value_factors * damage * systematic * mitigation_factor
    return losses.sum(axis=1)


def integrate_eal(aep: np.ndarray, loss: np.ndarray) -> float:
    """Approximate expected annual loss as area under the exceedance curve.

    The most-severe modelled loss is held constant between AEP 0 and the
    smallest supplied AEP; loss is linearly reduced to zero between the largest
    supplied AEP and AEP 1. This makes the approximation explicit and stable.
    """
    aep = np.asarray(aep, dtype=float)
    loss = np.asarray(loss, dtype=float)
    if len(aep) != len(loss) or len(aep) == 0:
        raise ValueError("AEP and loss must be non-empty arrays of equal length")
    order = np.argsort(aep)
    x = aep[order]
    y = loss[order]
    if np.any(np.diff(x) <= 0) or np.any((x <= 0) | (x >= 1)):
        raise ValueError("AEP values must be unique and lie between zero and one")
    y = np.minimum.accumulate(y)  # enforce a non-increasing curve as AEP rises
    x_full = np.concatenate(([0.0], x, [1.0]))
    y_full = np.concatenate(([y[0]], y, [0.0]))
    return float(np.trapezoid(y_full, x_full))


def model_scenario(
    assets: gpd.GeoDataFrame,
    scenario: str,
    scenario_cfg: dict,
    hazard_exposure: dict[float, pd.Series],
    config: dict,
    rng: np.random.Generator,
) -> tuple[list[EventLoss], pd.DataFrame]:
    iterations = int(config["project"]["monte_carlo_iterations"])
    uncertainty = config["uncertainty"]
    mitigation = float(scenario_cfg.get("mitigation_factor", 1.0))
    event_rows: list[EventLoss] = []
    asset_rows: list[pd.DataFrame] = []

    for aep in sorted(hazard_exposure, reverse=True):
        exposed_mask = hazard_exposure[aep].astype(bool)
        exposed = assets.loc[exposed_mask]
        damage_cfg = config["damage_ratios"][f"{aep:.3f}"]
        expected_ratio = float(damage_cfg["mean"]) * mitigation
        expected_asset_loss = np.where(
            exposed_mask,
            assets["replacement_value_nzd"].to_numpy(float) * expected_ratio,
            0.0,
        )
        draws = monte_carlo_event_loss(
            exposed,
            damage_mean=float(damage_cfg["mean"]),
            damage_concentration=float(damage_cfg["concentration"]),
            mitigation_factor=mitigation,
            iterations=iterations,
            rng=rng,
            value_sigma=float(uncertainty["replacement_value_lognormal_sigma"]),
            systematic_sigma=float(uncertainty["systematic_damage_lognormal_sigma"]),
        )
        event_rows.append(
            EventLoss(
                scenario=scenario,
                aep=aep,
                expected_loss_nzd=float(expected_asset_loss.sum()),
                p50_loss_nzd=float(np.quantile(draws, 0.50)),
                p90_loss_nzd=float(np.quantile(draws, 0.90)),
                exposed_assets=int(exposed_mask.sum()),
                exposed_value_nzd=float(exposed["replacement_value_nzd"].sum()),
            )
        )
        asset_rows.append(
            pd.DataFrame(
                {
                    "record_id": assets["record_id"].astype(str),
                    "asset_id": assets["asset_id"].astype(str),
                    "scenario": scenario,
                    "aep": aep,
                    "exposed": exposed_mask.to_numpy(),
                    "expected_event_loss_nzd": expected_asset_loss,
                }
            )
        )
    return event_rows, pd.concat(asset_rows, ignore_index=True)


def build_risk_register(assets: gpd.GeoDataFrame, asset_events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (record_id, scenario), group in asset_events.groupby(["record_id", "scenario"]):
        rows.append(
            {
                "record_id": record_id,
                "scenario": scenario,
                "expected_annual_loss_nzd": integrate_eal(
                    group["aep"].to_numpy(), group["expected_event_loss_nzd"].to_numpy()
                ),
                "events_exposed": int(group["exposed"].sum()),
            }
        )
    register = pd.DataFrame(rows)
    attributes = pd.DataFrame(assets.drop(columns="geometry")).copy()
    attributes["record_id"] = attributes["record_id"].astype(str)
    attributes["asset_id"] = attributes["asset_id"].astype(str)
    register = register.merge(attributes, on="record_id", how="left")
    register["priority_score"] = register["expected_annual_loss_nzd"] * (
        1 + 0.15 * (register["criticality_score"] - 1)
    )
    register["risk_band"] = "No modelled exposure"
    positive = register["priority_score"] > 0
    if positive.any():
        ranks = register.loc[positive, "priority_score"].rank(pct=True, method="max")
        register.loc[positive, "risk_band"] = pd.cut(
            ranks,
            bins=[0, 0.50, 0.80, 0.95, 1.0],
            labels=["Low", "Moderate", "High", "Very high"],
            include_lowest=True,
        ).astype(str)
    return register.sort_values(["scenario", "priority_score"], ascending=[True, False])
