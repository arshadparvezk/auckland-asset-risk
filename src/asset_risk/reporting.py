"""Charts, database outputs, and concise decision-facing reporting."""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


NAVY = "#003b5c"
BLUE = "#0076a8"
TEAL = "#00a6a6"
ORANGE = "#f59e0b"


def _money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}m"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.0f}k"
    return f"${value:,.0f}"


def save_figures(event_losses: pd.DataFrame, register: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = {
        "baseline": "Current climate",
        "slr_1m": "+1 m SLR",
        "slr_1m_mitigated": "+1 m SLR + treatment",
    }
    colors = {"baseline": NAVY, "slr_1m": ORANGE, "slr_1m_mitigated": TEAL}

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for scenario, group in event_losses.groupby("scenario"):
        group = group.sort_values("aep")
        ax.plot(
            group["expected_loss_nzd"] / 1_000_000,
            group["aep"] * 100,
            marker="o",
            linewidth=2.5,
            label=labels.get(scenario, scenario),
            color=colors.get(scenario, BLUE),
        )
        ax.fill_betweenx(
            group["aep"] * 100,
            group["p50_loss_nzd"] / 1_000_000,
            group["p90_loss_nzd"] / 1_000_000,
            alpha=0.10,
            color=colors.get(scenario, BLUE),
        )
    ax.set_xlabel("Portfolio event loss (NZD millions)")
    ax.set_ylabel("Annual exceedance probability (%)")
    ax.set_yscale("log")
    ax.invert_yaxis()
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    ax.set_title("Coastal inundation loss-exceedance curves")
    fig.tight_layout()
    fig.savefig(out_dir / "loss_exceedance_curve.png", dpi=180)
    plt.close(fig)

    scenario_register = register.query("scenario == 'slr_1m'")
    board = (
        scenario_register.groupby("local_board", dropna=False)["expected_annual_loss_nzd"]
        .sum()
        .sort_values(ascending=False)
        .head(12)
        .sort_values()
    )
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(board.index.astype(str), board.values / 1_000_000, color=TEAL)
    ax.set_xlabel("Expected annual loss (NZD millions)")
    ax.set_title("Top local boards by modelled EAL · +1 m SLR")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "eal_by_local_board.png", dpi=180)
    plt.close(fig)


def write_database(
    assets: pd.DataFrame,
    event_losses: pd.DataFrame,
    asset_events: pd.DataFrame,
    register: pd.DataFrame,
    path: Path,
    *,
    hazard_screening: pd.DataFrame | None = None,
    growth_context: pd.DataFrame | None = None,
    intervention_economics: pd.DataFrame | None = None,
    intervention_summary: pd.DataFrame | None = None,
) -> None:
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as connection:
        pd.DataFrame(assets.drop(columns="geometry")).to_sql(
            "assets", connection, index=False, if_exists="replace"
        )
        event_losses.to_sql("event_losses", connection, index=False, if_exists="replace")
        asset_events.to_sql("asset_event_exposure", connection, index=False, if_exists="replace")
        register.to_sql("asset_risk_register", connection, index=False, if_exists="replace")
        if hazard_screening is not None:
            hazard_screening.to_sql(
                "asset_hazard_screening", connection, index=False, if_exists="replace"
            )
        if growth_context is not None:
            growth_context.to_sql(
                "local_board_growth_context", connection, index=False, if_exists="replace"
            )
        if intervention_economics is not None:
            intervention_economics.to_sql(
                "intervention_economics", connection, index=False, if_exists="replace"
            )
        if intervention_summary is not None:
            intervention_summary.to_sql(
                "intervention_portfolio_summary",
                connection,
                index=False,
                if_exists="replace",
            )
        connection.executescript(
            """
            CREATE INDEX idx_assets_asset_id ON assets(asset_id);
            CREATE INDEX idx_exposure_asset_scenario
              ON asset_event_exposure(asset_id, scenario, aep);
            CREATE INDEX idx_register_scenario_priority
              ON asset_risk_register(scenario, priority_score DESC);
            """
        )
        if hazard_screening is not None:
            connection.execute(
                "CREATE INDEX idx_screening_attention "
                "ON asset_hazard_screening(screening_flag_count DESC)"
            )
        if growth_context is not None:
            connection.execute(
                "CREATE INDEX idx_growth_scenario_area "
                "ON local_board_growth_context(scenario, planning_area)"
            )
        if intervention_economics is not None:
            connection.execute(
                "CREATE INDEX idx_intervention_npv "
                "ON intervention_economics(illustrative_npv_nzd DESC)"
            )


def write_executive_summary(
    event_losses: pd.DataFrame,
    register: pd.DataFrame,
    quality: dict,
    out_path: Path,
    iterations: int,
    *,
    hazard_screening: pd.DataFrame | None = None,
    growth_context: pd.DataFrame | None = None,
    intervention_summary: pd.DataFrame | None = None,
) -> None:
    scenario_eal = (
        register.groupby("scenario")["expected_annual_loss_nzd"].sum().to_dict()
    )
    baseline = float(scenario_eal.get("baseline", 0))
    slr = float(scenario_eal.get("slr_1m", 0))
    mitigated = float(scenario_eal.get("slr_1m_mitigated", 0))
    avoided = max(0.0, slr - mitigated)
    liquefaction_mapped = (
        int(hazard_screening["liquefaction_mapped"].sum())
        if hazard_screening is not None
        else 0
    )
    liquefaction_review = (
        int(hazard_screening["liquefaction_review_flag"].sum())
        if hazard_screening is not None
        else 0
    )
    growth_benchmark = 0.0
    if growth_context is not None and not growth_context.empty:
        growth_benchmark = float(
            growth_context["auckland_population_growth_rate"].dropna().iloc[0]
        )
    central_economics = None
    if intervention_summary is not None and not intervention_summary.empty:
        central_rows = intervention_summary.loc[
            (intervention_summary["cost_case"] == "central")
            & (intervention_summary["real_discount_rate"].round(4) == 0.05)
        ]
        if not central_rows.empty:
            central_economics = central_rows.iloc[0]
    economics_sentence = (
        "Under the central demonstration assumptions, the conditional intervention "
        f"screen has a benefit-cost ratio of {float(central_economics['illustrative_bcr']):.2f}."
        if central_economics is not None
        else ""
    )
    top = register.query("scenario == 'slr_1m'").head(10)
    table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('description') or row.get('site_description') or row['asset_id']))}</td>"
        f"<td>{html.escape(str(row['asset_type']))}</td>"
        f"<td>{html.escape(str(row['local_board']))}</td>"
        f"<td>{_money(float(row['expected_annual_loss_nzd']))}</td>"
        f"<td>{html.escape(str(row['risk_band']))}</td>"
        "</tr>"
        for _, row in top.iterrows()
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auckland Asset Risk Executive Summary</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f5f7f8;color:#15242e}}main{{max-width:1080px;margin:auto;padding:38px}}
h1{{color:{NAVY};margin-bottom:6px}}.sub{{color:#526772;margin-bottom:28px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card{{background:white;border-radius:10px;padding:20px;box-shadow:0 1px 5px #0001}}.value{{font-size:27px;font-weight:700;color:{NAVY}}}
.label{{font-size:13px;color:#5b6b73;margin-top:6px}}section{{background:white;margin-top:22px;padding:24px;border-radius:10px}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e5ecef;font-size:14px}}th{{color:{NAVY}}}
.note{{border-left:4px solid {ORANGE};padding:12px;background:#fff7e6}}img{{width:100%;max-width:880px}}@media(max-width:760px){{.cards{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<h1>Auckland Natural Hazard Asset Risk Intelligence</h1><div class="sub">Coastal financial risk &middot; seismic screening &middot; growth and intervention context</div>
<div class="cards">
<div class="card"><div class="value">{quality['record_count']:,}</div><div class="label">assets assessed</div></div>
<div class="card"><div class="value">{_money(baseline)}</div><div class="label">current-climate EAL</div></div>
<div class="card"><div class="value">{_money(slr)}</div><div class="label">+1 m SLR EAL</div></div>
<div class="card"><div class="value">{_money(avoided)}</div><div class="label">illustrative annual loss avoided by treatment</div></div>
<div class="card"><div class="value">{liquefaction_review:,}</div><div class="label">liquefaction review flags ({liquefaction_mapped:,} mapped)</div></div>
<div class="card"><div class="value">{growth_benchmark:.1%}</div><div class="label">Auckland population growth context, 2022&ndash;2052</div></div>
</div>
<section><h2>Loss-exceedance comparison</h2><img src="../figures/loss_exceedance_curve.png" alt="Loss exceedance curves"></section>
<section><h2>Highest-priority assets under +1 m SLR</h2><table><thead><tr><th>Asset</th><th>Type</th><th>Local board</th><th>EAL</th><th>Risk band</th></tr></thead><tbody>{table_rows}</tbody></table></section>
<section><h2>Interpretation</h2><p>The model joins public asset points to four coastal-inundation frequencies, converts exposure to financial loss using explicit vulnerability assumptions, and propagates replacement-value and damage uncertainty through {iterations:,} Monte Carlo iterations. A separate Council liquefaction layer adds non-financial seismic screening, while AGS23v1.1 supplies planning context.</p>
<p>{economics_sentence}</p>
<p class="note"><strong>Important:</strong> Replacement values, damage functions, intervention costs and treatment effects are illustrative assumptions, not Auckland Council financial data or engineering estimates. Liquefaction is a regional vulnerability screen, not property-level earthquake risk. Growth does not multiply loss. This prototype is not an engineering, valuation, insurance, regulatory or investment decision.</p></section>
</main></body></html>""",
        encoding="utf-8",
    )


def write_run_metadata(path: Path, metadata: dict) -> None:
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
