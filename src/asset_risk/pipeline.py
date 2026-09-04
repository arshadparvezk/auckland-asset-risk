"""End-to-end command-line pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from .data import (
    data_quality_report,
    load_or_download_assets,
    load_or_download_hazard,
    load_or_download_screening_layer,
    write_clean_assets,
)
from .economics import build_intervention_economics, build_intervention_sensitivity
from .growth import assign_planning_area, build_growth_context, load_growth_reference
from .model import (
    assign_financial_assumptions,
    build_risk_register,
    calculate_exposure,
    integrate_eal,
    model_scenario,
)
from .reporting import save_figures, write_database, write_executive_summary, write_run_metadata
from .screening import build_asset_hazard_screening


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def run(project_root: Path, *, refresh: bool = False) -> dict[str, Path]:
    config = load_config(project_root / "config" / "model.yml")
    raw_dir = project_root / "data" / "raw"
    processed_dir = project_root / "data" / "processed"
    outputs = project_root / "outputs"
    figures = outputs / "figures"
    reports = outputs / "reports"
    for directory in (raw_dir, processed_dir, outputs, figures, reports):
        directory.mkdir(parents=True, exist_ok=True)

    assets = load_or_download_assets(config, raw_dir, refresh)
    assets = assign_planning_area(assets)
    assets = assign_financial_assumptions(assets, config)
    known_types = set(config["replacement_values_nzd"]) - {"__default__"}
    quality = data_quality_report(assets, known_types)
    (outputs / "data_quality_report.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )
    write_clean_assets(assets, processed_dir)

    direct_scenarios = {
        name: value
        for name, value in config["data_sources"]["hazard_scenarios"].items()
        if "layers" in value
    }
    exposure_cache: dict[str, dict[float, pd.Series]] = {}
    simplify = float(config["project"]["geometry_simplification_metres"])
    for scenario, scenario_cfg in direct_scenarios.items():
        exposure_cache[scenario] = {}
        for probability, service in scenario_cfg["layers"].items():
            hazard = load_or_download_hazard(
                service, raw_dir, refresh=refresh, simplify_metres=simplify
            )
            exposure_cache[scenario][float(probability)] = calculate_exposure(assets, hazard)

    rng = np.random.default_rng(int(config["project"]["random_seed"]))
    all_event_losses = []
    all_asset_events = []
    for scenario, scenario_cfg in config["data_sources"]["hazard_scenarios"].items():
        source = scenario_cfg.get("source_scenario", scenario)
        rows, asset_rows = model_scenario(
            assets,
            scenario,
            scenario_cfg,
            exposure_cache[source],
            config,
            rng,
        )
        all_event_losses.extend(row.__dict__ for row in rows)
        all_asset_events.append(asset_rows)

    event_losses = pd.DataFrame(all_event_losses).sort_values(["scenario", "aep"])
    asset_events = pd.concat(all_asset_events, ignore_index=True)
    register = build_risk_register(assets, asset_events)

    scenario_summary = (
        register.groupby("scenario", as_index=False)
        .agg(
            expected_annual_loss_nzd=("expected_annual_loss_nzd", "sum"),
            assets_with_modelled_loss=("expected_annual_loss_nzd", lambda x: int((x > 0).sum())),
            portfolio_value_nzd=("replacement_value_nzd", "sum"),
        )
    )
    p90_eal = []
    for scenario, group in event_losses.groupby("scenario"):
        p90_eal.append(
            {
                "scenario": scenario,
                "p90_curve_eal_nzd": integrate_eal(
                    group["aep"].to_numpy(), group["p90_loss_nzd"].to_numpy()
                ),
            }
        )
    scenario_summary = scenario_summary.merge(pd.DataFrame(p90_eal), on="scenario")

    screening_cfg = config["data_sources"]["screening_layers"]["liquefaction"]
    screening_simplify = float(
        config["project"].get("screening_geometry_simplification_metres", 0)
    )
    liquefaction = load_or_download_screening_layer(
        screening_cfg,
        raw_dir,
        refresh=refresh,
        simplify_metres=screening_simplify,
    )
    hazard_screening = build_asset_hazard_screening(
        assets,
        liquefaction,
        register,
        category_field=str(screening_cfg["category_field"]),
    )

    growth_cfg = config["data_sources"]["growth_context"]
    growth_reference = load_growth_reference(
        project_root / growth_cfg["reference_file"],
        start_year=int(growth_cfg["comparison_start_year"]),
        end_year=int(growth_cfg["comparison_end_year"]),
    )
    growth_context = build_growth_context(register, growth_reference)

    economics_cfg = config["intervention_economics"]
    intervention_economics = build_intervention_economics(register, economics_cfg)
    intervention_summary = build_intervention_sensitivity(register, economics_cfg)

    event_losses.to_csv(outputs / "loss_exceedance_curve.csv", index=False)
    asset_events.to_parquet(outputs / "asset_event_exposure.parquet", index=False)
    register.to_csv(outputs / "asset_risk_register.csv", index=False)
    scenario_summary.to_csv(outputs / "scenario_summary.csv", index=False)
    hazard_screening.to_csv(outputs / "asset_hazard_screening.csv", index=False)
    growth_context.to_csv(outputs / "local_board_growth_context.csv", index=False)
    intervention_economics.to_csv(outputs / "intervention_economics.csv", index=False)
    intervention_summary.to_csv(
        outputs / "intervention_portfolio_summary.csv", index=False
    )
    save_figures(event_losses, register, figures)
    write_database(
        assets,
        event_losses,
        asset_events,
        register,
        outputs / "risk_model.db",
        hazard_screening=hazard_screening,
        growth_context=growth_context,
        intervention_economics=intervention_economics,
        intervention_summary=intervention_summary,
    )
    write_executive_summary(
        event_losses,
        register,
        quality,
        reports / "executive_summary.html",
        iterations=int(config["project"]["monte_carlo_iterations"]),
        hazard_screening=hazard_screening,
        growth_context=growth_context,
        intervention_summary=intervention_summary,
    )

    metadata = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_version": str(config["project"]["version"]),
        "random_seed": int(config["project"]["random_seed"]),
        "monte_carlo_iterations": int(config["project"]["monte_carlo_iterations"]),
        "geometry_simplification_metres": simplify,
        "screening_geometry_simplification_metres": screening_simplify,
        "asset_count": int(len(assets)),
        "scenarios": list(config["data_sources"]["hazard_scenarios"]),
        "hazards_screened": ["coastal_inundation", "liquefaction_vulnerability"],
        "liquefaction_mapped_assets": int(hazard_screening["liquefaction_mapped"].sum()),
        "liquefaction_review_assets": int(
            hazard_screening["liquefaction_review_flag"].sum()
        ),
        "growth_context_source": str(growth_cfg["version"]),
        "growth_context_mapped_assets": int(
            assets["planning_area"].ne("Unmapped / not supplied").sum()
        ),
        "intervention_assumption_set": str(economics_cfg["assumption_set"]),
    }
    write_run_metadata(outputs / "run_metadata.json", metadata)
    return {
        "risk_register": outputs / "asset_risk_register.csv",
        "summary": outputs / "scenario_summary.csv",
        "hazard_screening": outputs / "asset_hazard_screening.csv",
        "growth_context": outputs / "local_board_growth_context.csv",
        "intervention_economics": outputs / "intervention_economics.csv",
        "report": reports / "executive_summary.html",
        "database": outputs / "risk_model.db",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--refresh", action="store_true", help="Re-download public ArcGIS data")
    args = parser.parse_args()
    paths = run(args.project_root.resolve(), refresh=args.refresh)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
