"""Build a self-contained, no-server HTML dashboard from verified model outputs."""

from __future__ import annotations

import html
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.io as pio
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DASHBOARD = ROOT / "dashboard" / "index.html"

LABELS = {
    "baseline": "Current climate",
    "slr_1m": "+1 m sea-level rise",
    "slr_1m_mitigated": "+1 m SLR with treatment",
}
COLORS = {
    "baseline": "#003b5c",
    "slr_1m": "#f59e0b",
    "slr_1m_mitigated": "#00a6a6",
}
RISK_COLORS = {
    "No modelled exposure": "#c9d3d8",
    "Low": "#6fb1a0",
    "Moderate": "#f2c14e",
    "High": "#f78154",
    "Very high": "#c73e1d",
}
VULNERABILITY_ORDER = [
    "Damage Possible",
    "Damage Unlikely",
    "Very Low",
    "Not mapped",
]
VULNERABILITY_COLORS = {
    "Not mapped": "#c9d3d8",
    "Very Low": "#91c7b1",
    "Damage Unlikely": "#69a8c4",
    "Damage Possible": "#b9341c",
}
ECONOMICS_COLORS = {
    "Positive illustrative NPV": "#00a6a6",
    "Below illustrative threshold": "#d56642",
}


def has_value(value: object) -> bool:
    """Return whether a scalar can be displayed without leaking a nan marker."""
    return bool(pd.notna(value) and str(value).strip() and str(value).lower() != "nan")


def safe_text(value: object, fallback: str = "—") -> str:
    """Escape text used in hand-built HTML tables."""
    return html.escape(str(value)) if has_value(value) else fallback


def first_text(row: pd.Series, *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if has_value(value):
            return str(value)
    return "Asset description not supplied"


def money(value: object) -> str:
    if not has_value(value):
        return "—"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"NZ${value / 1_000_000_000:,.2f}b"
    if abs(value) >= 1_000_000:
        return f"NZ${value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"NZ${value / 1_000:,.0f}k"
    return f"NZ${value:,.0f}"


def percent(value: object) -> str:
    return f"{float(value):.1%}" if has_value(value) else "—"


def ratio(value: object) -> str:
    return f"{float(value):.2f}" if has_value(value) else "—"


def whole(value: object) -> str:
    return f"{float(value):,.0f}" if has_value(value) else "—"


def as_bool(value: object) -> bool:
    """Normalise CSV Boolean values without treating the string 'False' as true."""
    if isinstance(value, bool):
        return value
    if not has_value(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def require_columns(frame: pd.DataFrame, filename: str, columns: set[str]) -> None:
    missing = sorted(columns.difference(frame.columns))
    if missing:
        raise ValueError(f"{filename} is missing required columns: {', '.join(missing)}")


def require_unique(frame: pd.DataFrame, filename: str, columns: list[str]) -> None:
    if frame.duplicated(columns).any():
        keys = ", ".join(columns)
        raise ValueError(f"{filename} must contain unique rows by {keys}")


def figure_html(figure, div_id: str) -> str:
    """Embed a Plotly figure without duplicating the bundled Plotly runtime."""
    return pio.to_html(
        figure,
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"responsive": True, "displaylogo": False},
    )


def top_table(frame: pd.DataFrame) -> str:
    rows = []
    for _, row in frame.nlargest(10, "priority_score").iterrows():
        name = first_text(row, "description", "site_description", "asset_id", "record_id")
        rows.append(
            "<tr>"
            f"<td>{safe_text(name)}</td>"
            f"<td>{safe_text(row['asset_type'])}</td>"
            f"<td>{safe_text(row['local_board'])}</td>"
            f"<td>{money(float(row['expected_annual_loss_nzd']))}</td>"
            f"<td><span class='risk {str(row['risk_band']).lower().replace(' ', '-')}'>{safe_text(row['risk_band'])}</span></td>"
            "</tr>"
        )
    return "".join(rows)


def build_hazard_section(screening: pd.DataFrame) -> str:
    """Render the non-financial liquefaction and dual-hazard screening section."""
    require_columns(
        screening,
        "asset_hazard_screening.csv",
        {
            "record_id",
            "asset_type",
            "local_board",
            "replacement_value_nzd",
            "coastal_slr_1m_eal_nzd",
            "coastal_slr_1m_exposed",
            "liquefaction_vulnerability",
            "liquefaction_mapped",
            "liquefaction_review_flag",
            "screening_flag_count",
            "screening_attention",
        },
    )
    require_unique(screening, "asset_hazard_screening.csv", ["record_id"])
    frame = screening.copy()
    frame["liquefaction_mapped"] = frame["liquefaction_mapped"].map(as_bool)
    frame["liquefaction_review_flag"] = frame["liquefaction_review_flag"].map(as_bool)
    frame["coastal_slr_1m_exposed"] = frame["coastal_slr_1m_exposed"].map(as_bool)
    mapped = int(frame["liquefaction_mapped"].sum())
    review = int(frame["liquefaction_review_flag"].sum())
    dual = int(
        (frame["liquefaction_review_flag"] & frame["coastal_slr_1m_exposed"]).sum()
    )
    coverage = mapped / len(frame) if len(frame) else 0.0

    category = (
        frame["liquefaction_vulnerability"]
        .value_counts()
        .reindex(VULNERABILITY_ORDER, fill_value=0)
        .rename_axis("Vulnerability")
        .reset_index(name="Assets")
    )
    hazard_fig = px.bar(
        category,
        x="Assets",
        y="Vulnerability",
        orientation="h",
        color="Vulnerability",
        color_discrete_map=VULNERABILITY_COLORS,
        text="Assets",
        category_orders={"Vulnerability": VULNERABILITY_ORDER},
        title="Liquefaction vulnerability profile",
    )
    hazard_fig.update_traces(textposition="outside")
    hazard_fig.update_yaxes(autorange="reversed", title="")
    hazard_fig.update_layout(
        height=390,
        margin=dict(l=35, r=30, t=65, b=45),
        showlegend=False,
    )

    flagged = frame.loc[
        frame["liquefaction_review_flag"] | frame["coastal_slr_1m_exposed"]
    ].sort_values(
        ["screening_flag_count", "coastal_slr_1m_eal_nzd"],
        ascending=[False, False],
    )
    rows = []
    for _, row in flagged.head(10).iterrows():
        rows.append(
            "<tr>"
            f"<td>{safe_text(first_text(row, 'description', 'site_description', 'asset_id', 'record_id'))}</td>"
            f"<td>{safe_text(row['asset_type'])}</td>"
            f"<td>{safe_text(row['local_board'])}</td>"
            f"<td>{safe_text(row['liquefaction_vulnerability'])}</td>"
            f"<td>{money(row['coastal_slr_1m_eal_nzd'])}</td>"
            f"<td>{safe_text(row['screening_attention'])}</td>"
            "</tr>"
        )
    return f"""<section class="section-card" id="multi-hazard-screening">
      <div class="section-head"><div><span class="eyebrow">NON-FINANCIAL HAZARD SCREEN</span><h2>Coastal and seismic evidence</h2></div>
      <p>Liquefaction categories remain separate from coastal EAL.</p></div>
      <div class="cards">
        <article class="card"><span>Liquefaction mapping coverage</span><strong>{coverage:.1%}</strong></article>
        <article class="card"><span>Assets mapped</span><strong>{mapped:,}</strong></article>
        <article class="card"><span>Damage Possible</span><strong>{review:,}</strong></article>
        <article class="card"><span>Dual-hazard review</span><strong>{dual:,}</strong></article>
      </div>
      <div class="chart">{figure_html(hazard_fig, 'liquefaction-vulnerability')}</div>
      <div class="table-card embedded"><h2>Highest-attention asset screens</h2>
        <div class="table-wrap"><table><thead><tr><th>Asset</th><th>Type</th><th>Local board</th><th>Liquefaction</th><th>+1 m coastal EAL</th><th>Attention</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table></div>
      </div>
      <p class="method-note"><strong>Interpret carefully:</strong> Auckland Council's liquefaction layer is city-scale desktop vulnerability mapping, not property-level earthquake risk. It excludes site-specific ground improvements and does not supply an occurrence or loss model.</p>
    </section>"""


def build_growth_section(growth: pd.DataFrame) -> str:
    """Render AGS23v1.1 planning context beside full-portfolio coastal evidence."""
    require_columns(
        growth,
        "local_board_growth_context.csv",
        {
            "scenario",
            "planning_area",
            "portfolio_assets",
            "assets_with_modelled_loss",
            "expected_annual_loss_nzd",
            "population_2022",
            "population_2052",
            "population_growth_rate",
            "households_growth_rate",
            "employment_growth_rate",
            "growth_data_mapped",
            "auckland_population_growth_rate",
            "above_auckland_population_growth",
        },
    )
    require_unique(
        growth,
        "local_board_growth_context.csv",
        ["scenario", "planning_area"],
    )
    frame = growth.loc[growth["scenario"] == "slr_1m"].copy()
    frame["growth_data_mapped"] = frame["growth_data_mapped"].map(as_bool)
    frame["above_auckland_population_growth"] = frame[
        "above_auckland_population_growth"
    ].map(as_bool)
    mapped = frame.loc[frame["growth_data_mapped"]].copy()
    benchmark = float(mapped["auckland_population_growth_rate"].iloc[0])
    population_2022 = float(mapped["population_2022"].sum())
    population_2052 = float(mapped["population_2052"].sum())
    focus = mapped.loc[
        mapped["above_auckland_population_growth"]
        & mapped["expected_annual_loss_nzd"].gt(0)
    ]

    growth_plot = mapped[
        [
            "planning_area",
            "population_growth_rate",
            "households_growth_rate",
            "employment_growth_rate",
        ]
    ].melt(
        id_vars="planning_area",
        var_name="Measure",
        value_name="Growth rate",
    )
    measure_labels = {
        "population_growth_rate": "Population",
        "households_growth_rate": "Households",
        "employment_growth_rate": "Employment",
    }
    growth_plot["Measure"] = growth_plot["Measure"].map(measure_labels)
    area_order = (
        mapped.sort_values("population_growth_rate")["planning_area"].astype(str).tolist()
    )
    growth_fig = px.bar(
        growth_plot,
        x="Growth rate",
        y="planning_area",
        color="Measure",
        barmode="group",
        orientation="h",
        category_orders={"planning_area": area_order},
        color_discrete_map={
            "Population": "#003b5c",
            "Households": "#00a6a6",
            "Employment": "#f59e0b",
        },
        labels={"planning_area": ""},
        title="Projected growth by planning area · 2022–2052",
    )
    growth_fig.update_xaxes(tickformat=".0%")
    growth_fig.update_layout(
        height=680,
        margin=dict(l=35, r=25, t=70, b=45),
        legend_title_text="",
    )

    rows = []
    table_frame = mapped.sort_values(
        ["above_auckland_population_growth", "expected_annual_loss_nzd"],
        ascending=[False, False],
    ).head(12)
    for _, row in table_frame.iterrows():
        rows.append(
            "<tr>"
            f"<td>{safe_text(row['planning_area'])}</td>"
            f"<td>{int(row['portfolio_assets']):,}</td>"
            f"<td>{money(row['expected_annual_loss_nzd'])}</td>"
            f"<td>{whole(row['population_2022'])}</td>"
            f"<td>{whole(row['population_2052'])}</td>"
            f"<td>{percent(row['population_growth_rate'])}</td>"
            f"<td>{percent(row['households_growth_rate'])}</td>"
            f"<td>{percent(row['employment_growth_rate'])}</td>"
            "</tr>"
        )
    represented_growth = population_2052 / population_2022 - 1 if population_2022 else 0.0
    return f"""<section class="section-card" id="growth-and-demand">
      <div class="section-head"><div><span class="eyebrow">PLANNING CONTEXT</span><h2>Growth and service demand</h2></div>
      <p>AGS23v1.1 context does not multiply modelled loss.</p></div>
      <div class="cards">
        <article class="card"><span>Population represented · 2022</span><strong>{population_2022:,.0f}</strong></article>
        <article class="card"><span>Population represented · 2052</span><strong>{population_2052:,.0f}</strong></article>
        <article class="card"><span>Represented growth</span><strong>{represented_growth:.1%}</strong></article>
        <article class="card"><span>Growth + loss focus areas</span><strong>{len(focus):,}</strong></article>
      </div>
      <div class="chart">{figure_html(growth_fig, 'growth-demand')}</div>
      <div class="table-card embedded"><h2>Planning-area resilience context</h2>
        <div class="table-wrap"><table><thead><tr><th>Planning area</th><th>Assets</th><th>+1 m EAL</th><th>Population 2022</th><th>Population 2052</th><th>Population growth</th><th>Household growth</th><th>Employment growth</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table></div>
      </div>
      <p class="method-note"><strong>Source:</strong> Auckland Council AGS23v1.1, the current Council growth scenario for planning and asset-management context. Auckland's population benchmark is {benchmark:.1%}. Waiheke and Aotea/Great Barrier share one published source geography. Projections are not guaranteed forecasts.</p>
    </section>"""


def build_economics_section(
    economics: pd.DataFrame, summary: pd.DataFrame
) -> str:
    """Render central lifecycle economics and its strongest decision caveats."""
    require_columns(
        economics,
        "intervention_economics.csv",
        {
            "record_id",
            "description",
            "asset_type",
            "local_board",
            "avoided_annual_loss_nzd",
            "pv_avoided_loss_nzd",
            "pv_lifecycle_cost_nzd",
            "illustrative_npv_nzd",
            "illustrative_bcr",
            "discounted_payback_year",
        },
    )
    require_unique(economics, "intervention_economics.csv", ["record_id"])
    require_columns(
        summary,
        "intervention_portfolio_summary.csv",
        {
            "cost_case",
            "real_discount_rate",
            "candidate_assets",
            "positive_npv_assets",
            "pv_avoided_loss_nzd",
            "pv_lifecycle_cost_nzd",
            "illustrative_npv_nzd",
            "illustrative_bcr",
            "discounted_payback_year",
        },
    )
    require_unique(
        summary,
        "intervention_portfolio_summary.csv",
        ["cost_case", "real_discount_rate"],
    )
    central = summary.loc[
        summary["cost_case"].eq("central")
        & summary["real_discount_rate"].round(4).eq(0.05)
    ]
    if len(central) != 1:
        raise ValueError("intervention_portfolio_summary.csv requires one central 5% row")
    central_row = central.iloc[0]

    plot_frame = economics.copy()
    plot_frame["Outcome"] = plot_frame["illustrative_npv_nzd"].map(
        lambda value: (
            "Positive illustrative NPV"
            if float(value) >= 0
            else "Below illustrative threshold"
        )
    )
    plot_frame["Asset"] = plot_frame.apply(
        lambda row: html.escape(
            first_text(row, "description", "site_description", "asset_id", "record_id")
        ),
        axis=1,
    )
    economics_fig = px.scatter(
        plot_frame,
        x="pv_lifecycle_cost_nzd",
        y="pv_avoided_loss_nzd",
        size="avoided_annual_loss_nzd",
        color="Outcome",
        hover_name="Asset",
        hover_data={
            "asset_type": True,
            "local_board": True,
            "illustrative_bcr": ":.2f",
            "illustrative_npv_nzd": ":,.0f",
            "Outcome": False,
        },
        color_discrete_map=ECONOMICS_COLORS,
        labels={
            "pv_lifecycle_cost_nzd": "PV lifecycle cost (NZD)",
            "pv_avoided_loss_nzd": "PV avoided loss (NZD)",
        },
        title="Asset intervention value screen · central assumptions",
        size_max=28,
    )
    axis_max = float(
        max(
            plot_frame["pv_lifecycle_cost_nzd"].max(),
            plot_frame["pv_avoided_loss_nzd"].max(),
        )
    )
    economics_fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=axis_max,
        y1=axis_max,
        line=dict(color="#64748b", dash="dash"),
    )
    economics_fig.update_xaxes(tickprefix="NZ$", tickformat="~s")
    economics_fig.update_yaxes(tickprefix="NZ$", tickformat="~s")
    economics_fig.update_layout(
        height=520,
        margin=dict(l=55, r=25, t=70, b=55),
        legend_title_text="",
    )

    rows = []
    for _, row in economics.nlargest(10, "illustrative_npv_nzd").iterrows():
        rows.append(
            "<tr>"
            f"<td>{safe_text(first_text(row, 'description', 'site_description', 'asset_id', 'record_id'))}</td>"
            f"<td>{safe_text(row['local_board'])}</td>"
            f"<td>{money(row['avoided_annual_loss_nzd'])}</td>"
            f"<td>{money(row['pv_lifecycle_cost_nzd'])}</td>"
            f"<td>{money(row['illustrative_npv_nzd'])}</td>"
            f"<td>{ratio(row['illustrative_bcr'])}</td>"
            f"<td>{whole(row['discounted_payback_year'])}</td>"
            "</tr>"
        )
    return f"""<section class="section-card" id="intervention-economics">
      <div class="section-head"><div><span class="eyebrow">DEMONSTRATION ECONOMICS</span><h2>Illustrative intervention screen</h2></div>
      <p>Conditional lifecycle appraisal under a static +1 m SLR stress case.</p></div>
      <div class="cards economics-cards">
        <article class="card"><span>Candidate assets</span><strong>{int(central_row['candidate_assets']):,}</strong></article>
        <article class="card"><span>PV avoided loss</span><strong>{money(central_row['pv_avoided_loss_nzd'])}</strong></article>
        <article class="card"><span>PV lifecycle cost</span><strong>{money(central_row['pv_lifecycle_cost_nzd'])}</strong></article>
        <article class="card"><span>Illustrative NPV</span><strong>{money(central_row['illustrative_npv_nzd'])}</strong></article>
        <article class="card"><span>Illustrative BCR</span><strong>{ratio(central_row['illustrative_bcr'])}</strong></article>
        <article class="card"><span>Discounted payback year</span><strong>{whole(central_row['discounted_payback_year'])}</strong></article>
      </div>
      <div class="chart">{figure_html(economics_fig, 'intervention-value')}</div>
      <div class="table-card embedded"><h2>Highest illustrative NPV assets</h2>
        <div class="table-wrap"><table><thead><tr><th>Asset</th><th>Local board</th><th>Annual avoided loss</th><th>PV lifecycle cost</th><th>Illustrative NPV</th><th>BCR</th><th>Payback year</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table></div>
      </div>
      <p class="method-note"><strong>Demonstration only:</strong> central costs equal 20% of illustrative value with a NZ$50,000 floor, plus 1% annual O&amp;M; horizon 30 years and real discount rate 5%. The screen excludes safety, service continuity, equity, environmental, insurance, financing and programme effects. It is not an investment recommendation.</p>
    </section>"""


def build() -> Path:
    register = pd.read_csv(OUTPUTS / "asset_risk_register.csv")
    curve = pd.read_csv(OUTPUTS / "loss_exceedance_curve.csv")
    summary = pd.read_csv(OUTPUTS / "scenario_summary.csv").set_index("scenario")
    screening = pd.read_csv(OUTPUTS / "asset_hazard_screening.csv")
    growth = pd.read_csv(OUTPUTS / "local_board_growth_context.csv")
    economics = pd.read_csv(OUTPUTS / "intervention_economics.csv")
    intervention_summary = pd.read_csv(
        OUTPUTS / "intervention_portfolio_summary.csv"
    )
    quality = json.loads((OUTPUTS / "data_quality_report.json").read_text(encoding="utf-8"))
    run = json.loads((OUTPUTS / "run_metadata.json").read_text(encoding="utf-8"))
    assets = gpd.read_parquet(ROOT / "data" / "processed" / "assets_clean.parquet").to_crs(4326)
    coordinates = pd.DataFrame(
        {
            "record_id": assets["record_id"].astype(str),
            "longitude": assets.geometry.x,
            "latitude": assets.geometry.y,
        }
    )

    curve["Scenario"] = curve["scenario"].map(LABELS)
    curve_fig = px.line(
        curve,
        x="expected_loss_nzd",
        y="aep",
        color="Scenario",
        markers=True,
        color_discrete_map={LABELS[key]: value for key, value in COLORS.items()},
        labels={"expected_loss_nzd": "Expected event loss (NZD)", "aep": "Annual exceedance probability"},
        title="Probabilistic loss-exceedance curves",
    )
    curve_fig.update_yaxes(type="log", autorange="reversed", tickformat=".1%")
    curve_fig.update_layout(legend_title_text="", height=500, margin=dict(l=55, r=20, t=70, b=55))
    # Embed Plotly once, before any chart initialisation scripts. This ordering is
    # required when the dashboard is opened directly from disk without a server.
    plotly_js = get_plotlyjs()
    curve_html = figure_html(curve_fig, "portfolio-loss-curve")

    panels = []
    for position, scenario in enumerate(LABELS):
        frame = register[register["scenario"] == scenario].copy()
        mapped = frame.merge(coordinates, on="record_id", how="left")
        mapped = mapped[mapped["expected_annual_loss_nzd"] > 0].copy()
        board = (
            frame.groupby("local_board", as_index=False)["expected_annual_loss_nzd"]
            .sum()
            .nlargest(12, "expected_annual_loss_nzd")
            .sort_values("expected_annual_loss_nzd")
        )
        board_fig = px.bar(
            board,
            x="expected_annual_loss_nzd",
            y="local_board",
            orientation="h",
            color_discrete_sequence=[COLORS[scenario]],
            labels={"expected_annual_loss_nzd": "Expected annual loss (NZD)", "local_board": ""},
            title="Highest modelled EAL by local board",
        )
        board_fig.update_layout(height=460, margin=dict(l=30, r=20, t=65, b=50), showlegend=False)

        hotspot_fig = px.scatter(
            mapped,
            x="longitude",
            y="latitude",
            color="risk_band",
            size="expected_annual_loss_nzd",
            hover_name="description",
            hover_data=["asset_type", "local_board", "expected_annual_loss_nzd"],
            color_discrete_map=RISK_COLORS,
            labels={"longitude": "Longitude", "latitude": "Latitude", "risk_band": "Risk band"},
            title="Geospatial asset-risk hotspots",
        )
        hotspot_fig.update_yaxes(scaleanchor="x", scaleratio=1)
        hotspot_fig.update_layout(height=460, margin=dict(l=45, r=20, t=65, b=50), legend_title_text="")

        row = summary.loc[scenario]
        p90 = float(row["p90_curve_eal_nzd"])
        active = " active" if position == 0 else ""
        panels.append(
            f"""<section class="scenario-panel{active}" id="panel-{scenario}">
            <div class="cards">
              <article class="card"><span>Portfolio assets</span><strong>{len(frame):,}</strong></article>
              <article class="card"><span>Assets with modelled loss</span><strong>{int((frame.expected_annual_loss_nzd > 0).sum()):,}</strong></article>
              <article class="card"><span>Expected annual loss</span><strong>{money(float(frame.expected_annual_loss_nzd.sum()))}</strong></article>
              <article class="card"><span>P90 curve EAL</span><strong>{money(p90)}</strong></article>
            </div>
            <div class="chart-grid">
              <div class="chart">{figure_html(board_fig, f'board-eal-{scenario}')}</div>
              <div class="chart">{figure_html(hotspot_fig, f'hotspots-{scenario}')}</div>
            </div>
            <div class="table-card"><h2>Highest-priority assets</h2>
              <div class="table-wrap"><table><thead><tr><th>Asset</th><th>Type</th><th>Local board</th><th>EAL</th><th>Risk band</th></tr></thead>
              <tbody>{top_table(frame)}</tbody></table></div>
            </div></section>"""
        )

    tabs = "".join(
        f"<button class='tab{' active' if index == 0 else ''}' data-target='{scenario}'>{label}</button>"
        for index, (scenario, label) in enumerate(LABELS.items())
    )
    hazard_section = build_hazard_section(screening)
    growth_section = build_growth_section(growth)
    economics_section = build_economics_section(economics, intervention_summary)
    DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auckland Natural Hazard Risk Intelligence</title>
<style>
:root{{--navy:#003b5c;--teal:#00a6a6;--orange:#f59e0b;--ink:#14252f;--muted:#5d707a;--bg:#f3f6f7;--line:#dce5e9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Arial,sans-serif}}
header{{background:linear-gradient(120deg,#003b5c,#075d78);color:white;padding:44px max(24px,calc((100vw - 1180px)/2)) 36px}}
header h1{{font-size:34px;margin:0 0 8px}}header p{{margin:0;color:#d8edf5;font-size:17px}}main{{max-width:1180px;margin:auto;padding:26px 24px 50px}}
.notice{{background:#fff6dc;border-left:5px solid var(--orange);padding:14px 18px;border-radius:8px;margin:0 0 22px;line-height:1.45}}
.tabs{{display:flex;gap:9px;flex-wrap:wrap;margin:18px 0}}.tab{{border:1px solid #aac0ca;background:white;color:var(--navy);padding:11px 18px;border-radius:999px;font-weight:700;cursor:pointer}}
.tab.active{{background:var(--navy);color:white;border-color:var(--navy)}}.scenario-panel{{display:none}}.scenario-panel.active{{display:block}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}}.card{{background:white;border-radius:12px;padding:19px;box-shadow:0 2px 9px #003b5c12}}
.card span{{display:block;color:var(--muted);font-size:13px;margin-bottom:8px}}.card strong{{font-size:25px;color:var(--navy)}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.chart,.table-card,.curve-card,.section-card{{background:white;border-radius:12px;padding:12px;box-shadow:0 2px 9px #003b5c12}}
.table-card,.curve-card{{margin-top:18px;padding:22px}}h2{{color:var(--navy);margin:0 0 16px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:11px 9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--navy)}}
.risk{{font-size:12px;font-weight:700;padding:4px 8px;border-radius:99px;background:#edf2f4}}.risk.very-high{{background:#fee4df;color:#9e2d16}}.risk.high{{background:#ffeadf;color:#a64420}}.risk.moderate{{background:#fff3cf;color:#7b5b00}}
.section-card{{margin-top:22px;padding:24px}}.section-card>.chart{{box-shadow:none;border:1px solid var(--line);margin-top:16px}}.table-card.embedded{{box-shadow:none;border:1px solid var(--line)}}
.section-head{{display:flex;justify-content:space-between;gap:22px;align-items:flex-end}}.section-head p{{color:var(--muted);margin:0 0 16px;text-align:right;max-width:480px}}.eyebrow{{display:block;font-size:12px;letter-spacing:.09em;font-weight:800;color:var(--teal);margin-bottom:8px}}.method-note{{background:#f4f8f9;border-left:4px solid var(--teal);padding:13px 15px;border-radius:7px;line-height:1.5;margin:18px 0 0}}.economics-cards{{grid-template-columns:repeat(3,1fr)}}
.footer{{color:var(--muted);font-size:13px;margin-top:24px;line-height:1.5}}@media(max-width:850px){{.cards,.economics-cards{{grid-template-columns:1fr 1fr}}.chart-grid{{grid-template-columns:1fr}}.section-head{{display:block}}.section-head p{{text-align:left}}}}@media(max-width:520px){{.cards,.economics-cards{{grid-template-columns:1fr}}header h1{{font-size:27px}}.table-wrap{{overflow-x:auto}}}}
</style>
<script>{plotly_js}</script>
</head><body>
<header><h1>Auckland natural hazard risk intelligence</h1><p>Coastal financial risk, seismic screening, growth context and intervention economics</p></header>
<main><div class="notice"><strong>Decision prototype:</strong> public asset, hazard and growth inputs are real Auckland Council data. Replacement values, damage, treatment and cost assumptions are transparent demonstrations, not Council financial or engineering data.</div>
<nav class="tabs" aria-label="Scenario selector">{tabs}</nav>{''.join(panels)}
<section class="curve-card"><h2>Portfolio scenario comparison</h2>{curve_html}</section>
{hazard_section}
{growth_section}
{economics_section}
<p class="footer">Model v{safe_text(run['project_version'])} · run {html.escape(run['completed_at_utc'])} · {run['monte_carlo_iterations']:,} Monte Carlo iterations · {quality['record_count']:,} asset records. Coastal geometry is generalised to 20 m; liquefaction screening uses source geometry. Portfolio demonstration only—not for engineering, insurance, valuation, regulatory or investment decisions.</p>
</main><script>
document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{{
  document.querySelectorAll('.tab,.scenario-panel').forEach(el=>el.classList.remove('active'));
  button.classList.add('active');document.getElementById('panel-'+button.dataset.target).classList.add('active');
  window.dispatchEvent(new Event('resize'));
}}));
</script></body></html>""",
        encoding="utf-8",
    )
    return DASHBOARD


if __name__ == "__main__":
    print(build())
