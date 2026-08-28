"""Professional Streamlit dashboard for the completed asset-risk model."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
ASSETS = ROOT / "data" / "processed" / "assets_clean.parquet"

SCENARIO_LABELS = {
    "baseline": "Current climate",
    "slr_1m": "+1 m sea-level rise",
    "slr_1m_mitigated": "+1 m SLR with treatment",
}
SCENARIO_COLORS = {
    "baseline": "#0B3954",
    "slr_1m": "#F59E0B",
    "slr_1m_mitigated": "#0F9D8A",
}
RISK_COLORS = {
    "No modelled exposure": "#CBD5E1",
    "Low": "#67B99A",
    "Moderate": "#F2C14E",
    "High": "#F78154",
    "Very high": "#C73E1D",
}
CHART_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


st.set_page_config(
    page_title="Auckland Asset Financial Risk",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --navy: #0B3954;
        --blue: #087E8B;
        --teal: #0F9D8A;
        --orange: #F59E0B;
        --ink: #132A3A;
        --muted: #5E7180;
        --surface: #F4F7F8;
    }
    .stApp { background: linear-gradient(180deg, #F6F9FA 0%, #FFFFFF 38%); }
    .block-container { max-width: 1480px; padding-top: 1.4rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #082F49; }
    [data-testid="stSidebar"] * { color: #F8FAFC; }
    [data-testid="stSidebar"] [data-baseweb="select"] * { color: #132A3A; }
    [data-testid="stSidebar"] input { color: #132A3A; }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.16); }
    .hero {
        padding: 1.35rem 1.55rem;
        border: 1px solid #DCE6EA;
        border-radius: 18px;
        background: linear-gradient(120deg, #FFFFFF 0%, #EEF7F7 100%);
        box-shadow: 0 8px 28px rgba(11,57,84,.07);
        margin-bottom: 1rem;
    }
    .hero h1 { color: var(--navy); font-size: clamp(1.8rem, 3vw, 2.75rem); margin: 0; }
    .hero p { color: var(--muted); font-size: 1rem; margin: .45rem 0 .8rem; }
    .chip {
        display: inline-block; padding: .28rem .58rem; margin: .15rem .3rem .05rem 0;
        border: 1px solid #BBD8D8; border-radius: 999px; color: #0B5660;
        background: #F5FFFF; font-size: .76rem; font-weight: 650;
    }
    [data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #DDE7EB; border-radius: 14px;
        padding: .8rem 1rem; box-shadow: 0 4px 16px rgba(11,57,84,.05);
    }
    [data-testid="stMetricValue"] { color: var(--navy); font-size: 1.75rem; }
    .insight {
        border-left: 5px solid var(--teal); background: #EFFAF7; color: #244A45;
        padding: .9rem 1rem; border-radius: 0 10px 10px 0; margin: .8rem 0 1rem;
    }
    .warning {
        border-left: 5px solid var(--orange); background: #FFF8E8; color: #5E4615;
        padding: .9rem 1rem; border-radius: 0 10px 10px 0;
    }
    .section-kicker { color: var(--blue); font-weight: 750; letter-spacing: .06em; font-size: .78rem; }
    h2, h3 { color: var(--navy); }
    .stTabs [data-baseweb="tab-list"] { gap: .5rem; }
    .stTabs [data-baseweb="tab"] {
        background: #EDF3F5; border-radius: 10px 10px 0 0; padding: .55rem .9rem;
    }
    .stTabs [aria-selected="true"] { background: #DCEEEE; color: var(--navy); }
    div[data-testid="stDataFrame"] { border: 1px solid #DDE7EB; border-radius: 12px; overflow: hidden; }
    .small-note { color: #607582; font-size: .82rem; }
    @media (max-width: 760px) {
        .block-container { padding-left: .8rem; padding-right: .8rem; }
        .hero { padding: 1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(value: float) -> str:
    """Format NZD values compactly for decision-facing metrics."""
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"NZ${value / 1_000_000_000:,.2f}b"
    if abs(value) >= 1_000_000:
        return f"NZ${value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"NZ${value / 1_000:,.0f}k"
    return f"NZ${value:,.0f}"


def style_figure(fig: go.Figure, *, height: int = 430) -> go.Figure:
    """Apply a consistent, presentation-ready Plotly theme."""
    fig.update_layout(
        height=height,
        margin=dict(l=24, r=24, t=60, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Arial, sans-serif", color="#274454", size=12),
        title_font=dict(color="#0B3954", size=18),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=12),
    )
    fig.update_xaxes(gridcolor="#E9F0F2", zerolinecolor="#D9E4E8")
    fig.update_yaxes(gridcolor="#E9F0F2", zerolinecolor="#D9E4E8")
    return fig


@st.cache_data(show_spinner=False)
def load_project_data() -> tuple[pd.DataFrame, ...]:
    """Load verified model outputs and map coordinates once per session."""
    register = pd.read_csv(OUTPUTS / "asset_risk_register.csv")
    curve = pd.read_csv(OUTPUTS / "loss_exceedance_curve.csv")
    summary = pd.read_csv(OUTPUTS / "scenario_summary.csv")
    assets = gpd.read_parquet(ASSETS).to_crs(4326)
    coordinates = pd.DataFrame(
        {
            "record_id": assets["record_id"].astype(str),
            "latitude": assets.geometry.y,
            "longitude": assets.geometry.x,
        }
    )
    quality = json.loads((OUTPUTS / "data_quality_report.json").read_text(encoding="utf-8"))
    metadata = json.loads((OUTPUTS / "run_metadata.json").read_text(encoding="utf-8"))
    return register, curve, summary, coordinates, quality, metadata


required_files = [
    OUTPUTS / "asset_risk_register.csv",
    OUTPUTS / "loss_exceedance_curve.csv",
    OUTPUTS / "scenario_summary.csv",
    OUTPUTS / "data_quality_report.json",
    OUTPUTS / "run_metadata.json",
    ASSETS,
]
missing_files = [path.relative_to(ROOT) for path in required_files if not path.exists()]
if missing_files:
    st.error("The model outputs are not available yet.")
    st.code("python -m asset_risk.pipeline --project-root . --refresh")
    st.write("Missing files:", ", ".join(map(str, missing_files)))
    st.stop()

register, curve, summary, coordinates, quality, metadata = load_project_data()
register["record_id"] = register["record_id"].astype(str)
curve["Scenario"] = curve["scenario"].map(SCENARIO_LABELS)
summary["Scenario"] = summary["scenario"].map(SCENARIO_LABELS)


with st.sidebar:
    st.markdown("## Analysis controls")
    st.caption(
        "Leave dropdowns empty to include all options, then add selections "
        "one by one to narrow the portfolio."
    )
    scenario_options = list(SCENARIO_LABELS)
    scenario = st.selectbox(
        "Hazard scenario",
        scenario_options,
        index=1,
        format_func=SCENARIO_LABELS.get,
    )
    scenario_register = register.loc[register["scenario"] == scenario].copy()

    boards = sorted(scenario_register["local_board"].dropna().astype(str).unique())
    selected_boards = st.multiselect(
        "Local boards",
        boards,
        placeholder="All local boards — select to filter",
    )

    asset_types = sorted(scenario_register["asset_type"].dropna().astype(str).unique())
    selected_asset_types = st.multiselect(
        "Asset types",
        asset_types,
        placeholder="All asset types — select to filter",
    )

    risk_order = ["Very high", "High", "Moderate", "Low", "No modelled exposure"]
    available_risks = [band for band in risk_order if band in set(scenario_register["risk_band"])]
    selected_risks = st.multiselect(
        "Risk bands",
        available_risks,
        placeholder="All risk bands — select to filter",
    )

    search_text = st.text_input("Search asset or site", placeholder="e.g. library, Onehunga")
    only_exposed = st.checkbox("Only assets with modelled loss", value=False)
    st.divider()
    st.caption("Model run")
    st.write(f"**{metadata['monte_carlo_iterations']:,}** Monte Carlo iterations")
    st.write(f"**{metadata['asset_count']:,}** public asset records")
    st.write(f"Seed: `{metadata['random_seed']}`")


view = scenario_register.copy()
if selected_boards:
    view = view.loc[view["local_board"].astype(str).isin(selected_boards)].copy()
if selected_asset_types:
    view = view.loc[view["asset_type"].astype(str).isin(selected_asset_types)].copy()
if selected_risks:
    view = view.loc[view["risk_band"].astype(str).isin(selected_risks)].copy()
if only_exposed:
    view = view.loc[view["expected_annual_loss_nzd"] > 0].copy()
if search_text.strip():
    query = search_text.strip().lower()
    searchable = (
        view["description"].fillna("").astype(str)
        + " "
        + view["site_description"].fillna("").astype(str)
        + " "
        + view["asset_type"].fillna("").astype(str)
        + " "
        + view["local_board"].fillna("").astype(str)
    ).str.lower()
    view = view.loc[searchable.str.contains(query, regex=False)].copy()

scenario_row = summary.loc[summary["scenario"] == scenario].iloc[0]
baseline_eal = float(summary.loc[summary["scenario"] == "baseline", "expected_annual_loss_nzd"].iloc[0])
slr_eal = float(summary.loc[summary["scenario"] == "slr_1m", "expected_annual_loss_nzd"].iloc[0])
mitigated_eal = float(
    summary.loc[summary["scenario"] == "slr_1m_mitigated", "expected_annual_loss_nzd"].iloc[0]
)
selected_eal = float(view["expected_annual_loss_nzd"].sum())
selected_value = float(view["replacement_value_nzd"].sum())
selected_exposed = int((view["expected_annual_loss_nzd"] > 0).sum())

st.markdown(
    f"""
    <section class="hero">
      <div class="section-kicker">PORTFOLIO DECISION PROTOTYPE</div>
      <h1>Auckland Natural Hazard Asset Loss Engine</h1>
      <p>Coastal-inundation exposure, uncertainty analysis and financial-loss prioritisation for public assets.</p>
      <span class="chip">Auckland Council open data</span>
      <span class="chip">{metadata['monte_carlo_iterations']:,}-iteration Monte Carlo</span>
      <span class="chip">Geospatial risk analytics</span>
      <span class="chip">Reproducible Python pipeline</span>
    </section>
    """,
    unsafe_allow_html=True,
)

metric_columns = st.columns(5)
metric_columns[0].metric("Selected assets", f"{len(view):,}")
metric_columns[1].metric("Assets with modelled loss", f"{selected_exposed:,}")
metric_columns[2].metric("Selected portfolio value", money(selected_value))
eal_change = (float(scenario_row["expected_annual_loss_nzd"]) / baseline_eal - 1) if baseline_eal else 0
metric_columns[3].metric(
    "Selected expected annual loss",
    money(selected_eal),
    delta=f"{eal_change:+.0%} scenario vs current" if scenario != "baseline" else None,
    delta_color="inverse",
)
metric_columns[4].metric("Scenario P90 curve EAL", money(float(scenario_row["p90_curve_eal_nzd"])))

if scenario == "slr_1m":
    st.markdown(
        f'<div class="insight"><strong>Decision signal:</strong> The +1 m sea-level-rise scenario increases portfolio EAL from {money(baseline_eal)} to {money(slr_eal)}. The illustrative treatment scenario reduces this by {money(slr_eal - mitigated_eal)} per year.</div>',
        unsafe_allow_html=True,
    )
elif scenario == "slr_1m_mitigated":
    st.markdown(
        f'<div class="insight"><strong>Illustrative benefit:</strong> Applying the stated 35% damage-reduction assumption avoids approximately {money(slr_eal - mitigated_eal)} in modelled annual loss compared with untreated +1 m SLR.</div>',
        unsafe_allow_html=True,
    )

overview_tab, map_tab, register_tab, method_tab = st.tabs(
    ["Executive overview", "Exposure map", "Priority register", "Model & data quality"]
)

with overview_tab:
    left, right = st.columns([1.02, 0.98])
    with left:
        comparison = summary.copy()
        comparison["EAL (NZD m)"] = comparison["expected_annual_loss_nzd"] / 1_000_000
        comparison_fig = px.bar(
            comparison,
            x="Scenario",
            y="EAL (NZD m)",
            color="scenario",
            color_discrete_map=SCENARIO_COLORS,
            text=comparison["expected_annual_loss_nzd"].map(money),
            title="Expected annual loss by scenario",
        )
        comparison_fig.update_traces(textposition="outside", hovertemplate="%{x}<br>EAL: NZ$%{y:.2f}m<extra></extra>")
        comparison_fig.update_layout(showlegend=False)
        st.plotly_chart(style_figure(comparison_fig), width="stretch", config=CHART_CONFIG)

    with right:
        board_eal = (
            view.groupby("local_board", as_index=False)["expected_annual_loss_nzd"]
            .sum()
            .nlargest(12, "expected_annual_loss_nzd")
            .sort_values("expected_annual_loss_nzd")
        )
        if board_eal.empty or board_eal["expected_annual_loss_nzd"].sum() == 0:
            st.info("No modelled local-board loss remains under the selected filters.")
        else:
            board_fig = px.bar(
                board_eal,
                x="expected_annual_loss_nzd",
                y="local_board",
                orientation="h",
                color_discrete_sequence=["#0F9D8A"],
                labels={"expected_annual_loss_nzd": "Expected annual loss (NZD)", "local_board": ""},
                title="Highest modelled EAL by local board",
            )
            board_fig.update_traces(hovertemplate="%{y}<br>EAL: NZ$%{x:,.0f}<extra></extra>")
            board_fig.update_xaxes(tickprefix="NZ$", tickformat="~s")
            st.plotly_chart(style_figure(board_fig), width="stretch", config=CHART_CONFIG)

    selected_curve = curve.loc[curve["scenario"] == scenario].sort_values("aep")
    curve_fig = go.Figure()
    curve_fig.add_trace(
        go.Scatter(
            x=selected_curve["p90_loss_nzd"],
            y=selected_curve["aep"],
            mode="lines",
            line=dict(width=0),
            name="P90",
            hovertemplate="P90 loss: NZ$%{x:,.0f}<br>AEP: %{y:.1%}<extra></extra>",
        )
    )
    curve_fig.add_trace(
        go.Scatter(
            x=selected_curve["p50_loss_nzd"],
            y=selected_curve["aep"],
            mode="lines",
            fill="tonextx",
            fillcolor="rgba(15,157,138,.18)",
            line=dict(width=0),
            name="P50–P90 uncertainty band",
            hovertemplate="P50 loss: NZ$%{x:,.0f}<br>AEP: %{y:.1%}<extra></extra>",
        )
    )
    curve_fig.add_trace(
        go.Scatter(
            x=selected_curve["expected_loss_nzd"],
            y=selected_curve["aep"],
            mode="lines+markers",
            line=dict(color=SCENARIO_COLORS[scenario], width=3),
            marker=dict(size=9, color=SCENARIO_COLORS[scenario]),
            name="Expected event loss",
            hovertemplate="Expected loss: NZ$%{x:,.0f}<br>AEP: %{y:.1%}<extra></extra>",
        )
    )
    curve_fig.update_yaxes(type="log", autorange="reversed", tickformat=".1%", title="Annual exceedance probability")
    curve_fig.update_xaxes(tickprefix="NZ$", tickformat="~s", title="Portfolio event loss")
    curve_fig.update_layout(title=f"Loss-exceedance curve · {SCENARIO_LABELS[scenario]}")
    st.plotly_chart(style_figure(curve_fig, height=500), width="stretch", config=CHART_CONFIG)

with map_tab:
    st.markdown("### Asset-level exposure and priority")
    st.caption("Marker size represents expected annual loss; colour represents the relative portfolio priority band.")
    mapped = view.merge(coordinates, on="record_id", how="left")
    mapped = mapped.loc[
        (mapped["expected_annual_loss_nzd"] > 0)
        & mapped["latitude"].notna()
        & mapped["longitude"].notna()
    ].copy()
    if mapped.empty:
        st.info("No mapped assets remain under the selected filters. Adjust the sidebar filters.")
    else:
        map_fig = px.scatter_map(
            mapped,
            lat="latitude",
            lon="longitude",
            color="risk_band",
            color_discrete_map=RISK_COLORS,
            category_orders={"risk_band": risk_order},
            size="expected_annual_loss_nzd",
            size_max=28,
            hover_name="description",
            hover_data={
                "asset_type": True,
                "local_board": True,
                "expected_annual_loss_nzd": ":,.0f",
                "priority_score": ":,.0f",
                "latitude": False,
                "longitude": False,
            },
            labels={
                "asset_type": "Asset type",
                "local_board": "Local board",
                "expected_annual_loss_nzd": "Expected annual loss (NZD)",
                "priority_score": "Priority score",
                "risk_band": "Risk band",
            },
            map_style="carto-positron",
            center={"lat": -36.85, "lon": 174.76},
            zoom=8,
            height=640,
        )
        map_fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.02))
        st.plotly_chart(map_fig, width="stretch", config=CHART_CONFIG)

with register_tab:
    st.markdown("### Ranked asset risk register")
    st.caption("The priority score combines expected annual loss with a transparent service-criticality adjustment.")
    table_columns = [
        "description",
        "site_description",
        "asset_type",
        "local_board",
        "replacement_value_nzd",
        "expected_annual_loss_nzd",
        "criticality_score",
        "priority_score",
        "risk_band",
    ]
    table = view[table_columns].sort_values("priority_score", ascending=False).reset_index(drop=True)
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        height=560,
        column_config={
            "description": st.column_config.TextColumn("Asset"),
            "site_description": st.column_config.TextColumn("Site"),
            "asset_type": st.column_config.TextColumn("Asset type"),
            "local_board": st.column_config.TextColumn("Local board"),
            "replacement_value_nzd": st.column_config.NumberColumn("Illustrative value", format="NZ$ %.0f"),
            "expected_annual_loss_nzd": st.column_config.NumberColumn("Expected annual loss", format="NZ$ %.0f"),
            "criticality_score": st.column_config.NumberColumn("Criticality", format="%d"),
            "priority_score": st.column_config.NumberColumn("Priority score", format="%.0f"),
            "risk_band": st.column_config.TextColumn("Risk band"),
        },
    )
    download_left, download_right, _ = st.columns([1, 1, 2])
    download_left.download_button(
        "Download filtered register",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name=f"asset_risk_register_{scenario}.csv",
        mime="text/csv",
        width="stretch",
    )
    download_right.download_button(
        "Download scenario summary",
        data=summary.to_csv(index=False).encode("utf-8"),
        file_name="scenario_summary.csv",
        mime="text/csv",
        width="stretch",
    )

with method_tab:
    methodology_col, quality_col = st.columns([1.12, 0.88])
    with methodology_col:
        st.markdown("### Model workflow")
        st.markdown(
            """
            1. Download Auckland Council public asset locations and eight coastal-inundation layers.
            2. Standardise asset attributes and validate identifiers and geometries.
            3. Intersect assets with 18.1%, 4.9%, 2% and 1% AEP hazard extents.
            4. Convert exposure to financial loss using explicit value and damage assumptions.
            5. Propagate uncertainty through 10,000 Monte Carlo iterations.
            6. Integrate the loss-exceedance curve to estimate expected annual loss.
            7. Rank assets using EAL adjusted by service criticality.
            """
        )
        st.markdown("**Expected conditional loss**")
        st.latex(r"L_{i,e}=V_i \times DR_e \times M_s")
        st.markdown("**Criticality-adjusted priority score**")
        st.latex(r"Priority_i=EAL_i \times [1+0.15(C_i-1)]")
        st.markdown(
            '<div class="warning"><strong>Responsible-use limitation:</strong> Hazard locations are based on public Auckland Council data. Replacement values and damage ratios are illustrative assumptions, not Council financial data. Results are suitable for portfolio-screening demonstration only.</div>',
            unsafe_allow_html=True,
        )

    with quality_col:
        st.markdown("### Data-quality controls")
        q1, q2 = st.columns(2)
        q1.metric("Records validated", f"{quality['record_count']:,}")
        q2.metric("Invalid geometries", f"{quality['invalid_geometry_records']:,}")
        q3, q4 = st.columns(2)
        q3.metric("Empty geometries", f"{quality['empty_geometry_records']:,}")
        q4.metric("Duplicate-ID records", f"{quality['duplicate_asset_id_records']:,}")
        missing_total = sum(quality.get("missing_by_critical_field", {}).values())
        st.metric("Missing critical-field values", f"{missing_total:,}")
        unmapped = quality.get("unmapped_asset_types", [])
        st.write("**Unmapped asset types:**", ", ".join(unmapped) if unmapped else "None")
        st.caption(quality["validation_note"])
        st.divider()
        st.markdown("### Reproducibility")
        st.write(f"Project version: **{metadata['project_version']}**")
        st.write(f"Random seed: **{metadata['random_seed']}**")
        st.write(f"Geometry simplification: **{metadata['geometry_simplification_metres']} m**")
        st.write(f"Completed: **{metadata['completed_at_utc']}**")

st.markdown(
    '<p class="small-note">Portfolio screening prototype · Public hazard and asset-location data · Not for engineering, insurance, valuation, regulatory or investment decisions.</p>',
    unsafe_allow_html=True,
)
