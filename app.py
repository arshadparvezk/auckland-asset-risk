"""Executive Streamlit dashboard for the Auckland asset-risk model."""

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
    "baseline": "#155E75",
    "slr_1m": "#D97706",
    "slr_1m_mitigated": "#0F766E",
}
RISK_COLORS = {
    "No modelled exposure": "#94A3B8",
    "Low": "#23856D",
    "Moderate": "#C58A00",
    "High": "#E05D2A",
    "Very high": "#B42318",
}
RISK_BADGE_COLORS = {
    "No modelled exposure": "gray",
    "Low": "green",
    "Moderate": "yellow",
    "High": "orange",
    "Very high": "red",
}
RISK_ORDER = ["Very high", "High", "Moderate", "Low", "No modelled exposure"]
AEP_LABELS = {
    0.181: "18.1% AEP",
    0.049: "4.9% AEP",
    0.020: "2% AEP",
    0.010: "1% AEP",
}
AEP_EXPLANATIONS = {
    0.181: "Approximately a 1-in-6 annual chance",
    0.049: "Approximately a 1-in-20 annual chance",
    0.020: "A 1-in-50 annual chance",
    0.010: "A 1-in-100 annual chance",
}
CHART_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}
FILTER_DEFAULTS = {
    "filter_scenario": "slr_1m",
    "filter_boards": [],
    "filter_asset_types": [],
    "filter_risks": [],
    "filter_search": "",
    "filter_exposed": False,
}


st.set_page_config(
    page_title="Auckland asset risk intelligence",
    page_icon=":material/water:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def money(value: float) -> str:
    """Format NZD values compactly for decision-facing metrics."""
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return "NZ$" + f"{value / 1_000_000_000:,.2f}b"
    if abs(value) >= 1_000_000:
        return "NZ$" + f"{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return "NZ$" + f"{value / 1_000:,.0f}k"
    return "NZ$" + f"{value:,.0f}"


def style_figure(fig: go.Figure, *, height: int = 390) -> go.Figure:
    """Apply a consistent presentation theme to Plotly figures."""
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=28, b=24),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color="#294653", size=12),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=12),
    )
    fig.update_xaxes(gridcolor="#DCE6EA", zerolinecolor="#CBD8DE")
    fig.update_yaxes(gridcolor="#DCE6EA", zerolinecolor="#CBD8DE")
    return fig


def reset_filters() -> None:
    """Restore the initial portfolio view without selecting every option."""
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = value.copy() if isinstance(value, list) else value


def clear_scenario_filters() -> None:
    """Clear scenario-dependent selections when the scenario changes."""
    for key in ("filter_boards", "filter_asset_types", "filter_risks"):
        st.session_state[key] = []


@st.cache_data(show_spinner=False, max_entries=3)
def load_project_data(source_version: tuple[int, ...]) -> tuple[pd.DataFrame, ...]:
    """Load verified model outputs and map coordinates once per session."""
    del source_version  # The file timestamps are the cache-invalidation key.
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


@st.cache_data(show_spinner=False, max_entries=20)
def dataframe_to_csv(frame: pd.DataFrame) -> bytes:
    """Create an Excel-friendly CSV payload for downloads."""
    return frame.to_csv(index=False).encode("utf-8-sig")


def scenario_scope(register: pd.DataFrame, record_ids: list[str]) -> pd.DataFrame:
    """Summarise each scenario over exactly the same selected asset cohort."""
    scoped = register.loc[register["record_id"].isin(record_ids)]
    grouped = (
        scoped.groupby("scenario", as_index=False)
        .agg(
            expected_annual_loss_nzd=("expected_annual_loss_nzd", "sum"),
            assets_with_modelled_loss=(
                "expected_annual_loss_nzd",
                lambda values: int((values > 0).sum()),
            ),
        )
    )
    complete = pd.DataFrame({"scenario": list(SCENARIO_LABELS)}).merge(
        grouped, on="scenario", how="left"
    )
    complete[["expected_annual_loss_nzd", "assets_with_modelled_loss"]] = complete[
        ["expected_annual_loss_nzd", "assets_with_modelled_loss"]
    ].fillna(0)
    complete["Scenario"] = complete["scenario"].map(SCENARIO_LABELS)
    return complete


def build_portfolio_brief(
    view: pd.DataFrame,
    comparison: pd.DataFrame,
    scenario: str,
    metadata: dict,
    filter_summary: str,
) -> str:
    """Build an audit-friendly Markdown summary of the current selection."""
    totals = comparison.set_index("scenario")["expected_annual_loss_nzd"].to_dict()
    current_eal = float(totals.get(scenario, 0.0))
    untreated_eal = float(totals.get("slr_1m", 0.0))
    mitigated_eal = float(totals.get("slr_1m_mitigated", 0.0))
    avoided_eal = max(untreated_eal - mitigated_eal, 0.0)
    selected_value = float(view["replacement_value_nzd"].sum())
    selected_exposed = int((view["expected_annual_loss_nzd"] > 0).sum())
    top_assets = view.nlargest(10, "priority_score")
    completed_label = pd.to_datetime(metadata["completed_at_utc"]).strftime("%d %b %Y")

    lines = [
        "# Auckland asset risk decision brief",
        "",
        f"- Scenario: **{SCENARIO_LABELS[scenario]}**",
        f"- Scope: **{filter_summary}**",
        f"- Assets in view: **{len(view):,}**",
        f"- Assets with modelled loss: **{selected_exposed:,}**",
        f"- Illustrative replacement value: **{money(selected_value)}**",
        f"- Expected annual loss: **{money(current_eal)}**",
        f"- Modelled annual loss avoided by treatment: **{money(avoided_eal)}**",
        "",
        "## Highest-priority assets",
        "",
        "| Rank | Asset | Local board | Risk band | Expected annual loss |",
        "|---:|---|---|---|---:|",
    ]
    for rank, (_, row) in enumerate(top_assets.iterrows(), start=1):
        name = str(row["asset_name"]).replace("|", "\\|")
        board = str(row["local_board"]).replace("|", "\\|")
        lines.append(
            f"| {rank} | {name} | {board} | {row['risk_band']} | "
            f"{money(float(row['expected_annual_loss_nzd']))} |"
        )
    if top_assets.empty:
        lines.append("| – | No assets match the selected filters | – | – | – |")

    lines.extend(
        [
            "",
            "## Model traceability",
            "",
            f"- Project version: {metadata['project_version']}",
            f"- Model completed: {completed_label}",
            f"- Monte Carlo iterations: {metadata['monte_carlo_iterations']:,}",
            f"- Random seed: {metadata['random_seed']}",
            "",
            "> Portfolio-screening demonstration. Values and damage assumptions are illustrative and are not Auckland Council financial data.",
        ]
    )
    return "\n".join(lines)


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
    st.error("The model outputs are not available yet.", icon=":material/error:")
    st.code("python -m asset_risk.pipeline --project-root . --refresh")
    st.write("Missing files:", ", ".join(map(str, missing_files)))
    st.stop()

source_version = tuple(path.stat().st_mtime_ns for path in required_files)
register, curve, summary, coordinates, quality, metadata = load_project_data(source_version)
register["record_id"] = register["record_id"].astype(str)
curve["Scenario"] = curve["scenario"].map(SCENARIO_LABELS)
summary["Scenario"] = summary["scenario"].map(SCENARIO_LABELS)

description = register["description"].fillna("").astype(str).str.strip()
site_name = register["site_description"].fillna("").astype(str).str.strip()
register["asset_name"] = description.mask(description.eq(""), site_name)
register["asset_name"] = register["asset_name"].mask(
    register["asset_name"].eq(""), register["record_id"]
)

for state_key, default_value in FILTER_DEFAULTS.items():
    st.session_state.setdefault(
        state_key, default_value.copy() if isinstance(default_value, list) else default_value
    )

completed_at = pd.to_datetime(metadata["completed_at_utc"]).strftime("%d %b %Y")

with st.sidebar:
    st.caption("ASSET FINANCIAL RISK")
    st.markdown("## Analysis controls")
    st.badge("Model ready", icon=":material/check_circle:", color="green")
    st.caption("Start with the full portfolio, then select values one by one to narrow the view.")

    scenario = st.selectbox(
        "Hazard scenario",
        list(SCENARIO_LABELS),
        format_func=SCENARIO_LABELS.get,
        key="filter_scenario",
        on_change=clear_scenario_filters,
        help="Select the climate and treatment case used for asset-level risk bands and losses.",
    )
    scenario_register = register.loc[register["scenario"] == scenario].copy()

    boards = sorted(scenario_register["local_board"].dropna().astype(str).unique())
    selected_boards = st.multiselect(
        "Local boards",
        boards,
        key="filter_boards",
        placeholder="All local boards (select to filter)",
    )

    asset_types = sorted(scenario_register["asset_type"].dropna().astype(str).unique())
    selected_asset_types = st.multiselect(
        "Asset types",
        asset_types,
        key="filter_asset_types",
        placeholder="All asset types (select to filter)",
    )

    available_risks = [
        band for band in RISK_ORDER if band in set(scenario_register["risk_band"])
    ]
    selected_risks = st.pills(
        "Risk bands",
        available_risks,
        selection_mode="multi",
        key="filter_risks",
        help="No selection means all risk bands.",
    )

    search_text = st.text_input(
        "Search portfolio",
        key="filter_search",
        placeholder="Asset, site, street, board or ID",
        icon=":material/search:",
    )
    only_exposed = st.toggle(
        "Only assets with modelled loss",
        key="filter_exposed",
        help="Exclude records with zero expected annual loss in the selected scenario.",
    )
    st.button(
        "Reset all filters",
        key="reset_filters",
        on_click=reset_filters,
        icon=":material/restart_alt:",
        width="stretch",
    )
    filter_status = st.empty()

    with st.expander(
        "Model run details",
        icon=":material/fact_check:",
        type="compact",
    ):
        st.write(f"**{metadata['monte_carlo_iterations']:,}** Monte Carlo iterations")
        st.write(f"**{metadata['asset_count']:,}** public asset records")
        st.write(f"Completed **{completed_at}**")
        st.write(f"Seed {metadata['random_seed']} · v{metadata['project_version']}")


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
    search_columns = [
        "record_id",
        "asset_id",
        "asset_name",
        "site_description",
        "asset_type",
        "local_board",
        "STREETNUMBER",
        "STREETNAME",
        "city",
    ]
    searchable = (
        view[search_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )
    view = view.loc[searchable.str.contains(query, regex=False)].copy()

active_filter_count = sum(
    bool(value)
    for value in (
        selected_boards,
        selected_asset_types,
        selected_risks,
        search_text.strip(),
        only_exposed,
    )
)
filter_status.caption(
    f"{active_filter_count} narrowing filter{'s' if active_filter_count != 1 else ''} active · "
    f"{len(view):,} assets in view"
)

selected_ids = view["record_id"].drop_duplicates().tolist()
comparison = scenario_scope(register, selected_ids)
eal_by_scenario = comparison.set_index("scenario")["expected_annual_loss_nzd"].to_dict()
baseline_eal = float(eal_by_scenario.get("baseline", 0.0))
slr_eal = float(eal_by_scenario.get("slr_1m", 0.0))
mitigated_eal = float(eal_by_scenario.get("slr_1m_mitigated", 0.0))
selected_eal = float(eal_by_scenario.get(scenario, 0.0))
selected_value = float(view["replacement_value_nzd"].sum())
selected_exposed = int((view["expected_annual_loss_nzd"] > 0).sum())
exposure_rate = selected_exposed / len(view) if len(view) else 0.0
treatment_benefit = max(slr_eal - mitigated_eal, 0.0)
treatment_rate = treatment_benefit / slr_eal if slr_eal else 0.0

positive_risk = view.loc[view["expected_annual_loss_nzd"] > 0].sort_values(
    "expected_annual_loss_nzd", ascending=False
)
top_ten_share = (
    float(positive_risk.head(10)["expected_annual_loss_nzd"].sum()) / selected_eal
    if selected_eal
    else 0.0
)
if selected_eal:
    cumulative_share = positive_risk["expected_annual_loss_nzd"].cumsum() / selected_eal
    assets_for_80 = int((cumulative_share < 0.80).sum() + 1)
else:
    assets_for_80 = 0

scope_parts = []
if selected_boards:
    scope_parts.append(f"{len(selected_boards)} board{'s' if len(selected_boards) != 1 else ''}")
if selected_asset_types:
    scope_parts.append(
        f"{len(selected_asset_types)} asset type{'s' if len(selected_asset_types) != 1 else ''}"
    )
if selected_risks:
    scope_parts.append(f"{len(selected_risks)} risk band{'s' if len(selected_risks) != 1 else ''}")
if search_text.strip():
    scope_parts.append(f"search “{search_text.strip()}”")
if only_exposed:
    scope_parts.append("modelled-loss assets only")
filter_summary = (
    " · ".join(scope_parts)
    if scope_parts
    else "All boards · all asset types · all risk bands"
)


with st.container(border=True):
    header_left, header_right = st.columns([3.6, 1.2], vertical_alignment="center")
    with header_left:
        st.caption("ASSET FINANCIAL RISK · PORTFOLIO SCREENING")
        st.title("Auckland natural hazard risk intelligence")
        st.markdown(
            "Decision-ready coastal-inundation exposure, uncertainty and financial-loss "
            "prioritisation for public assets."
        )
        with st.container(horizontal=True, gap="xsmall"):
            st.badge("Geospatial analytics", icon=":material/map:", color="blue")
            st.badge(
                f"{metadata['monte_carlo_iterations']:,} simulations",
                icon=":material/query_stats:",
                color="violet",
            )
            st.badge("Reproducible model", icon=":material/check_circle:", color="green")
    with header_right:
        st.caption("CURRENT VIEW")
        st.markdown(f"### {SCENARIO_LABELS[scenario]}")
        st.badge("Model outputs verified", icon=":material/verified:", color="green")
        st.caption(f"{len(view):,} of {len(scenario_register):,} assets · completed {completed_at}")

if view.empty:
    st.warning(
        "No assets match the current filters. Reset the filters or broaden the selection.",
        icon=":material/filter_alt_off:",
    )

st.caption("CURRENT SELECTION")
with st.container(horizontal=True):
    st.metric(
        "Assets in view",
        f"{len(view):,}",
        border=True,
        help="Records remaining after all sidebar filters are applied.",
    )
    st.metric(
        "Assets with modelled loss",
        f"{selected_exposed:,} · {exposure_rate:.1%}",
        border=True,
        help="Assets with expected annual loss greater than zero in the selected scenario.",
    )
    st.metric(
        "Illustrative portfolio value",
        money(selected_value),
        border=True,
        help="Illustrative replacement values used for this demonstration; not Council financial data.",
    )

    if scenario == "slr_1m":
        eal_reference = baseline_eal
        reference_label = "vs current"
    elif scenario == "slr_1m_mitigated":
        eal_reference = slr_eal
        reference_label = "vs untreated"
    else:
        eal_reference = None
        reference_label = ""
    if eal_reference:
        eal_delta = f"{selected_eal / eal_reference - 1:+.0%} {reference_label}"
    elif scenario != "baseline" and selected_eal > 0:
        eal_delta = f"New exposure {reference_label}"
    else:
        eal_delta = None
    st.metric(
        "Expected annual loss",
        money(selected_eal),
        delta=eal_delta,
        delta_color="inverse",
        border=True,
        help="Long-run average annual modelled loss for the same selected asset cohort.",
    )

with st.container(border=True):
    signal_header, signal_scope = st.columns([2.3, 1], vertical_alignment="center")
    signal_header.markdown("#### Executive decision brief")
    signal_scope.caption("All signals use the same selected asset cohort across scenarios.")
    signal_1, signal_2, signal_3 = st.columns(3)
    with signal_1:
        st.markdown(":material/trending_up: **Sea-level-rise shift**")
        if baseline_eal:
            scenario_change = slr_eal - baseline_eal
            change_direction = "increase" if scenario_change >= 0 else "decrease"
            st.markdown(
                f"EAL changes from **{money(baseline_eal)}** to **{money(slr_eal)}** "
                f"(**{slr_eal / baseline_eal - 1:+.0%}**; "
                f"{money(abs(scenario_change))} {change_direction})."
            )
        elif slr_eal:
            st.markdown(f"+1 m SLR introduces **{money(slr_eal)}** of annual modelled loss.")
        else:
            st.markdown("No modelled loss remains in this selected cohort.")
    with signal_2:
        st.markdown(":material/shield: **Treatment opportunity**")
        st.markdown(
            f"The illustrative treatment avoids **{money(treatment_benefit)} per year** "
            f"(**{treatment_rate:.0%}** of untreated +1 m SLR EAL)."
        )
    with signal_3:
        st.markdown(":material/account_tree: **Risk concentration**")
        if selected_eal:
            st.markdown(
                f"The top 10 assets contribute **{top_ten_share:.1%}** of EAL; "
                f"**{assets_for_80:,} assets** account for 80%."
            )
        else:
            st.markdown("No positive-loss assets remain for concentration analysis.")


overview_tab, map_tab, register_tab, method_tab = st.tabs(
    [
        ":material/space_dashboard: Executive overview",
        ":material/map: Exposure map",
        ":material/format_list_numbered: Priority register",
        ":material/fact_check: Model & data quality",
    ]
)

with overview_tab:
    st.subheader("Portfolio outlook")
    st.caption("Compare the selected asset cohort, identify loss drivers and stress-test severe events.")

    outlook_left, outlook_right = st.columns(2)
    with outlook_left:
        with st.container(border=True, height="stretch"):
            st.markdown("#### Scenario outlook")
            st.caption("Expected annual loss for the same selected asset set across all scenarios.")
            if comparison["expected_annual_loss_nzd"].sum() == 0:
                st.info("No modelled loss remains under the selected filters.")
            else:
                comparison_fig = px.bar(
                    comparison,
                    x="Scenario",
                    y="expected_annual_loss_nzd",
                    color="scenario",
                    color_discrete_map=SCENARIO_COLORS,
                    text=comparison["expected_annual_loss_nzd"].map(money),
                    labels={"expected_annual_loss_nzd": "Expected annual loss (NZD)"},
                )
                comparison_fig.update_traces(
                    textposition="outside",
                    hovertemplate="%{x}<br>EAL: NZ$%{y:,.0f}<extra></extra>",
                )
                comparison_fig.update_yaxes(tickprefix="NZ$", tickformat="~s")
                comparison_fig.update_layout(showlegend=False)
                st.plotly_chart(
                    style_figure(comparison_fig, height=360),
                    width="stretch",
                    config=CHART_CONFIG,
                )

    with outlook_right:
        with st.container(border=True, height="stretch"):
            st.markdown("#### Loss concentration")
            concentration_dimension = st.segmented_control(
                "Group by",
                ["Local board", "Asset type"],
                default="Local board",
                required=True,
                key="concentration_dimension",
            )
            concentration_measure = st.segmented_control(
                "Measure",
                ["Total EAL", "EAL per NZ$1m value"],
                default="Total EAL",
                required=True,
                key="concentration_measure",
            )
            group_field = "local_board" if concentration_dimension == "Local board" else "asset_type"
            grouped_risk = (
                view.groupby(group_field, dropna=False, as_index=False)
                .agg(
                    expected_annual_loss_nzd=("expected_annual_loss_nzd", "sum"),
                    replacement_value_nzd=("replacement_value_nzd", "sum"),
                )
            )
            grouped_risk[group_field] = grouped_risk[group_field].fillna("Unknown").astype(str)
            grouped_risk["portfolio_share"] = (
                grouped_risk["expected_annual_loss_nzd"] / selected_eal if selected_eal else 0.0
            )
            grouped_risk["eal_per_million_nzd"] = (
                grouped_risk["expected_annual_loss_nzd"]
                / grouped_risk["replacement_value_nzd"].replace(0, pd.NA)
                * 1_000_000
            ).fillna(0.0)

            measure_column = (
                "expected_annual_loss_nzd"
                if concentration_measure == "Total EAL"
                else "eal_per_million_nzd"
            )
            top_groups = (
                grouped_risk.loc[grouped_risk[measure_column] > 0]
                .nlargest(10, measure_column)
                .sort_values(measure_column)
                .copy()
            )
            if top_groups.empty or float(top_groups[measure_column].sum()) == 0:
                st.info("No positive loss remains for concentration analysis.")
            else:
                top_groups["share_label"] = top_groups["portfolio_share"].map(
                    lambda value: f"{value:.0%}"
                )
                concentration_fig = px.bar(
                    top_groups,
                    x=measure_column,
                    y=group_field,
                    orientation="h",
                    text="share_label" if concentration_measure == "Total EAL" else None,
                    custom_data=[
                        "expected_annual_loss_nzd",
                        "replacement_value_nzd",
                        "portfolio_share",
                    ],
                    color_discrete_sequence=["#0F766E"],
                    labels={
                        group_field: "",
                        "expected_annual_loss_nzd": "Expected annual loss (NZD)",
                        "eal_per_million_nzd": "EAL per NZ$1m value",
                    },
                )
                concentration_fig.update_traces(
                    textposition="outside",
                    hovertemplate=(
                        "%{y}<br>EAL: NZ$%{customdata[0]:,.0f}"
                        "<br>Illustrative value: NZ$%{customdata[1]:,.0f}"
                        "<br>Share of selected EAL: %{customdata[2]:.1%}<extra></extra>"
                    ),
                )
                concentration_fig.update_xaxes(tickprefix="NZ$", tickformat="~s")
                concentration_fig.update_xaxes(automargin=True)
                concentration_fig.update_yaxes(automargin=True)
                st.plotly_chart(
                    style_figure(concentration_fig, height=330),
                    width="stretch",
                    config=CHART_CONFIG,
                )

    with st.container(border=True):
        stress_header, stress_control = st.columns([1.65, 1], vertical_alignment="bottom")
        with stress_header:
            st.markdown("#### Whole-portfolio event stress test")
            st.caption(
                "Event-loss outputs are portfolio-wide and do not change with asset filters. "
                "AEP is the annual probability of the event being exceeded."
            )
        with stress_control:
            stress_aep = st.selectbox(
                "Event severity",
                sorted(AEP_LABELS, reverse=True),
                index=3,
                format_func=AEP_LABELS.get,
                key="stress_aep",
                width="stretch",
            )
            st.caption(AEP_EXPLANATIONS[stress_aep])

        selected_stress = curve.loc[
            (curve["scenario"] == scenario)
            & (curve["aep"].round(3) == round(stress_aep, 3))
        ].iloc[0]
        uncertainty_buffer = float(selected_stress["p90_loss_nzd"]) - float(
            selected_stress["expected_loss_nzd"]
        )
        with st.container(horizontal=True):
            st.metric(
                "Expected event loss",
                money(float(selected_stress["expected_loss_nzd"])),
                border=True,
                help="Whole-portfolio expected conditional loss at the selected event probability.",
            )
            st.metric(
                "P90 event loss",
                money(float(selected_stress["p90_loss_nzd"])),
                border=True,
                help="Ninety percent of Monte Carlo outcomes are at or below this loss.",
            )
            st.metric(
                "Assets exposed",
                f"{int(selected_stress['exposed_assets']):,}",
                border=True,
            )
            st.metric(
                "P90 uncertainty buffer",
                money(uncertainty_buffer),
                border=True,
                help="P90 loss minus expected event loss.",
            )

        stress_data = curve.loc[curve["aep"].round(3) == round(stress_aep, 3)].copy()
        stress_fig = go.Figure()
        stress_fig.add_trace(
            go.Bar(
                x=stress_data["Scenario"],
                y=stress_data["expected_loss_nzd"],
                name="Expected loss",
                marker_color="#0F766E",
                hovertemplate="%{x}<br>Expected loss: NZ$%{y:,.0f}<extra></extra>",
            )
        )
        stress_fig.add_trace(
            go.Bar(
                x=stress_data["Scenario"],
                y=stress_data["p90_loss_nzd"],
                name="P90 loss",
                marker_color="#D97706",
                hovertemplate="%{x}<br>P90 loss: NZ$%{y:,.0f}<extra></extra>",
            )
        )
        stress_fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.08))
        stress_fig.update_yaxes(
            title="Whole-portfolio event loss",
            tickprefix="NZ$",
            tickformat="~s",
        )
        st.plotly_chart(
            style_figure(stress_fig, height=360),
            width="stretch",
            config=CHART_CONFIG,
        )

        with st.expander(
            "View full loss-exceedance curve",
            icon=":material/query_stats:",
        ):
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
                    fillcolor="rgba(15,118,110,.18)",
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
            curve_fig.update_yaxes(
                type="log",
                autorange="reversed",
                tickformat=".1%",
                title="Annual exceedance probability",
            )
            curve_fig.update_xaxes(
                tickprefix="NZ$",
                tickformat="~s",
                title="Whole-portfolio event loss",
            )
            st.plotly_chart(
                style_figure(curve_fig, height=470),
                width="stretch",
                config=CHART_CONFIG,
            )


with map_tab:
    map_heading, map_control = st.columns([2.4, 1], vertical_alignment="bottom")
    with map_heading:
        st.subheader("Asset-level exposure map")
        st.caption("Colour shows risk band; marker size can show financial loss or priority.")
    with map_control:
        map_metric = st.segmented_control(
            "Size markers by",
            ["Expected annual loss", "Priority score"],
            default="Expected annual loss",
            required=True,
            key="map_metric",
            width="stretch",
        )

    mapped = view.merge(coordinates, on="record_id", how="left")
    mapped = mapped.loc[
        (mapped["expected_annual_loss_nzd"] > 0)
        & mapped["latitude"].notna()
        & mapped["longitude"].notna()
    ].copy()
    with st.container(horizontal=True):
        st.metric("Mapped exposed assets", f"{len(mapped):,}", border=True)
        st.metric(
            "Local boards represented",
            f"{mapped['local_board'].nunique():,}" if not mapped.empty else "0",
            border=True,
        )
        st.metric(
            "Mapped expected annual loss",
            money(float(mapped["expected_annual_loss_nzd"].sum())),
            border=True,
        )

    if mapped.empty:
        st.info(
            "No mapped exposed assets remain. Adjust the sidebar filters.",
            icon=":material/map:",
        )
    else:
        size_column = (
            "expected_annual_loss_nzd"
            if map_metric == "Expected annual loss"
            else "priority_score"
        )
        map_fig = px.scatter_map(
            mapped,
            lat="latitude",
            lon="longitude",
            color="risk_band",
            color_discrete_map=RISK_COLORS,
            category_orders={"risk_band": RISK_ORDER},
            size=size_column,
            size_max=28,
            hover_name="asset_name",
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
            height=650,
        )
        map_fig.update_layout(
            margin=dict(l=0, r=0, t=8, b=0),
            legend=dict(orientation="h", y=1.02),
        )
        with st.container(border=True):
            st.plotly_chart(map_fig, width="stretch", config=CHART_CONFIG)

        map_export_columns = [
            "record_id",
            "scenario",
            "asset_name",
            "asset_type",
            "local_board",
            "risk_band",
            "expected_annual_loss_nzd",
            "priority_score",
            "latitude",
            "longitude",
        ]
        st.download_button(
            "Download mapped exposure",
            data=dataframe_to_csv(mapped[map_export_columns]),
            file_name=f"mapped_asset_exposure_{scenario}.csv",
            mime="text/csv",
            icon=":material/download:",
            on_click="ignore",
        )

with register_tab:
    st.subheader("Ranked asset risk register")
    st.caption(
        "Select a row to open an asset decision brief. Priority combines expected annual loss "
        "with a transparent service-criticality adjustment."
    )

    export_columns = [
        "record_id",
        "scenario",
        "asset_id",
        "asset_name",
        "description",
        "site_description",
        "asset_type",
        "asset_group",
        "local_board",
        "STREETNUMBER",
        "STREETNAME",
        "city",
        "replacement_value_nzd",
        "expected_annual_loss_nzd",
        "events_exposed",
        "criticality_score",
        "priority_score",
        "risk_band",
    ]
    export_table = view[export_columns].sort_values(
        ["priority_score", "record_id"],
        ascending=[False, True],
    ).reset_index(drop=True)
    scenario_rank_frame = scenario_register[
        ["record_id", "priority_score"]
    ].copy()
    scenario_rank_frame["scenario_rank"] = scenario_rank_frame[
        "priority_score"
    ].rank(method="min", ascending=False)
    scenario_rank_lookup = scenario_rank_frame.set_index("record_id")[
        "scenario_rank"
    ].astype(int).to_dict()
    scenario_tie_counts = scenario_register["priority_score"].value_counts().to_dict()
    briefing = build_portfolio_brief(view, comparison, scenario, metadata, filter_summary)
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.download_button(
            "Filtered register",
            data=dataframe_to_csv(export_table),
            file_name=f"asset_risk_register_{scenario}.csv",
            mime="text/csv",
            icon=":material/download:",
            on_click="ignore",
        )
        st.download_button(
            "Decision brief",
            data=briefing.encode("utf-8"),
            file_name=f"portfolio_decision_brief_{scenario}.md",
            mime="text/markdown",
            icon=":material/description:",
            on_click="ignore",
        )
        st.download_button(
            "Scenario summary",
            data=dataframe_to_csv(summary),
            file_name="scenario_summary.csv",
            mime="text/csv",
            icon=":material/table_view:",
            on_click="ignore",
        )

    table_columns = [
        "record_id",
        "asset_name",
        "asset_type",
        "local_board",
        "replacement_value_nzd",
        "expected_annual_loss_nzd",
        "events_exposed",
        "criticality_score",
        "priority_score",
        "risk_band",
    ]
    table = export_table[table_columns].copy()
    table_event = st.dataframe(
        table,
        key="risk_register_table",
        width="stretch",
        hide_index=True,
        height=520,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "record_id": st.column_config.TextColumn("Record ID", width="small"),
            "asset_name": st.column_config.TextColumn("Asset", pinned=True, width="large"),
            "asset_type": st.column_config.TextColumn("Asset type"),
            "local_board": st.column_config.TextColumn("Local board"),
            "replacement_value_nzd": st.column_config.NumberColumn(
                "Illustrative value", format="NZ$ %,.0f"
            ),
            "expected_annual_loss_nzd": st.column_config.NumberColumn(
                "Expected annual loss", format="NZ$ %,.0f"
            ),
            "events_exposed": st.column_config.NumberColumn(
                "Events exposed", format="%d"
            ),
            "criticality_score": st.column_config.NumberColumn(
                "Criticality",
                format="%d",
                help="Service-criticality score from 1 to 5.",
            ),
            "priority_score": st.column_config.NumberColumn(
                "Priority score",
                format="%,.0f",
                help="EAL adjusted upward by 15% for each criticality level above 1.",
            ),
            "risk_band": st.column_config.TextColumn("Risk band", pinned=True),
        },
    )

    if not table.empty:
        selected_rows = list(table_event.selection.rows)
        selected_position = (
            selected_rows[0]
            if selected_rows and selected_rows[0] < len(table)
            else 0
        )
        selected_asset = export_table.iloc[selected_position]
        selected_record_id = str(selected_asset["record_id"])
        selected_scenario_rank = scenario_rank_lookup[selected_record_id]
        selected_tie_count = int(
            scenario_tie_counts.get(float(selected_asset["priority_score"]), 1)
        )
        selected_loss_rate = (
            float(selected_asset["expected_annual_loss_nzd"])
            / float(selected_asset["replacement_value_nzd"])
            if float(selected_asset["replacement_value_nzd"])
            else 0.0
        )

        st.markdown("#### Asset decision brief")
        if not selected_rows:
            st.caption(
                "Showing the highest-priority asset. Select another row above to investigate it."
            )
        detail_left, detail_right = st.columns([1, 1.12])
        with detail_left:
            with st.container(border=True, height="stretch"):
                with st.container(horizontal=True, gap="xsmall"):
                    selected_risk_band = str(selected_asset["risk_band"])
                    risk_icon = (
                        ":material/warning:"
                        if selected_risk_band in {"High", "Very high"}
                        else ":material/shield:"
                    )
                    st.badge(
                        selected_risk_band,
                        icon=risk_icon,
                        color=RISK_BADGE_COLORS.get(
                            selected_risk_band, "gray"
                        ),
                    )
                    if float(selected_asset["priority_score"]) > 0:
                        tie_label = " · tied" if selected_tie_count > 1 else ""
                        st.badge(
                            f"Scenario rank #{selected_scenario_rank:,}{tie_label}",
                            icon=":material/format_list_numbered:",
                            color="primary",
                        )
                    else:
                        st.badge("Unranked", color="gray")
                st.markdown(f"### {selected_asset['asset_name']}")
                site_value = selected_asset["site_description"]
                selected_site = (
                    str(site_value).strip()
                    if pd.notna(site_value) and str(site_value).strip()
                    else "Site not supplied"
                )
                st.caption(
                    f"{selected_site} · "
                    f"{selected_asset['local_board']} · {selected_record_id}"
                )
                address_parts = [
                    str(selected_asset[field]).strip()
                    for field in ("STREETNUMBER", "STREETNAME", "city")
                    if pd.notna(selected_asset[field])
                    and str(selected_asset[field]).strip()
                ]
                if address_parts:
                    st.write(":material/location_on: " + " ".join(address_parts))
                detail_metrics = st.columns(2)
                detail_metrics[0].metric(
                    "Expected annual loss",
                    money(float(selected_asset["expected_annual_loss_nzd"])),
                    border=True,
                )
                detail_metrics[1].metric(
                    "Annual loss rate",
                    f"{selected_loss_rate:.2%}",
                    border=True,
                )
                detail_metrics_2 = st.columns(2)
                detail_metrics_2[0].metric(
                    "Illustrative value",
                    money(float(selected_asset["replacement_value_nzd"])),
                    border=True,
                )
                detail_metrics_2[1].metric(
                    "Events exposed",
                    f"{int(selected_asset['events_exposed'])} of 4",
                    border=True,
                )
                st.caption(
                    f"Criticality {int(selected_asset['criticality_score'])}/5 · "
                    f"priority score {float(selected_asset['priority_score']):,.0f}"
                )

        with detail_right:
            with st.container(border=True, height="stretch"):
                st.markdown("#### Asset scenario profile")
                st.caption(
                    "Expected annual loss for this same asset under each modelled scenario."
                )
                asset_profile = register.loc[
                    register["record_id"] == selected_record_id
                ].copy()
                asset_profile["Scenario"] = asset_profile["scenario"].map(
                    SCENARIO_LABELS
                )
                asset_fig = px.bar(
                    asset_profile,
                    x="Scenario",
                    y="expected_annual_loss_nzd",
                    color="scenario",
                    color_discrete_map=SCENARIO_COLORS,
                    text=asset_profile["expected_annual_loss_nzd"].map(money),
                    labels={"expected_annual_loss_nzd": "Expected annual loss (NZD)"},
                )
                asset_fig.update_traces(
                    textposition="outside",
                    hovertemplate="%{x}<br>EAL: NZ$%{y:,.0f}<extra></extra>",
                )
                asset_fig.update_yaxes(tickprefix="NZ$", tickformat="~s")
                asset_fig.update_layout(showlegend=False)
                st.plotly_chart(
                    style_figure(asset_fig, height=310),
                    width="stretch",
                    config=CHART_CONFIG,
                )
                asset_eal = asset_profile.set_index("scenario")[
                    "expected_annual_loss_nzd"
                ].to_dict()
                asset_avoided = max(
                    float(asset_eal.get("slr_1m", 0.0))
                    - float(asset_eal.get("slr_1m_mitigated", 0.0)),
                    0.0,
                )
                if asset_avoided > 0:
                    st.success(
                        f"Illustrative treatment avoids {money(asset_avoided)} in "
                        "modelled annual loss for this asset.",
                        icon=":material/shield:",
                    )
                else:
                    st.info(
                        "No modelled treatment benefit is estimated for this asset "
                        "because its untreated +1 m SLR EAL is zero.",
                        icon=":material/shield:",
                    )
    else:
        st.info("No assets are available to inspect under the selected filters.")


with method_tab:
    st.subheader("Model governance and data lineage")
    st.caption(
        "Trace what enters the model, what it produces and which controls support reproducibility."
    )

    input_col, output_col = st.columns(2)
    with input_col:
        with st.container(border=True, height="stretch"):
            st.badge("Inputs", icon=":material/input:", color="blue")
            st.markdown("#### Data and assumptions entering the model")
            st.markdown(
                """
                - **Asset locations:** 2,022 processed Auckland Council public asset records
                - **Hazard layers:** four AEP extents for current climate and +1 m sea-level rise
                - **Model configuration:** replacement values, criticality, damage ratios and uncertainty
                - **Treatment assumption:** 35% reduction in conditional damage under +1 m SLR
                """
            )
            st.caption("Primary configuration: config/model.yml")
    with output_col:
        with st.container(border=True, height="stretch"):
            st.badge("Outputs", icon=":material/output:", color="green")
            st.markdown("#### Evidence produced by the model")
            st.markdown(
                """
                - **Asset risk register:** EAL, criticality-adjusted priority and risk band
                - **Loss-exceedance curve:** expected, P50 and P90 event loss by AEP
                - **Scenario summary:** portfolio EAL, exposed assets and illustrative value
                - **Quality and run metadata:** validation results, seed, version and completion time
                """
            )
            st.caption("Verified outputs are stored in outputs/.")

    methodology_col, quality_col = st.columns([1.1, 0.9])
    with methodology_col:
        with st.container(border=True, height="stretch"):
            st.markdown("#### Transparent model workflow")
            st.markdown(
                """
                1. Download public asset locations and coastal-inundation layers.
                2. Standardise attributes and validate identifiers and geometries.
                3. Intersect assets with 18.1%, 4.9%, 2% and 1% AEP hazard extents.
                4. Convert exposure to loss using explicit value and damage assumptions.
                5. Propagate uncertainty through Monte Carlo simulation.
                6. Integrate the loss-exceedance curve to estimate expected annual loss.
                7. Rank assets using EAL adjusted by service criticality.
                """
            )
            formula_left, formula_right = st.columns(2)
            with formula_left:
                st.markdown("**Expected conditional loss**")
                st.latex(r"L_{i,e}=V_i \times DR_e \times M_s")
            with formula_right:
                st.markdown("**Criticality-adjusted priority**")
                st.latex(r"Priority_i=EAL_i \times [1+0.15(C_i-1)]")

    with quality_col:
        with st.container(border=True, height="stretch"):
            st.markdown("#### Data-quality controls")
            with st.container(horizontal=True):
                st.metric(
                    "Records validated",
                    f"{quality['record_count']:,}",
                    border=True,
                )
                st.metric(
                    "Invalid geometries",
                    f"{quality['invalid_geometry_records']:,}",
                    border=True,
                )
            with st.container(horizontal=True):
                st.metric(
                    "Empty geometries",
                    f"{quality['empty_geometry_records']:,}",
                    border=True,
                )
                st.metric(
                    "Duplicate IDs flagged",
                    f"{quality['duplicate_asset_id_records']:,}",
                    border=True,
                )
            missing_total = sum(quality.get("missing_by_critical_field", {}).values())
            st.metric("Missing critical fields", f"{missing_total:,}", border=True)
            with st.container(horizontal=True, gap="xsmall"):
                if (
                    quality["invalid_geometry_records"] == 0
                    and quality["empty_geometry_records"] == 0
                ):
                    st.badge(
                        "Geometry checks passed",
                        icon=":material/check:",
                        color="green",
                    )
                else:
                    st.badge(
                        "Geometry issues flagged",
                        icon=":material/warning:",
                        color="red",
                    )
                if quality["duplicate_asset_id_records"]:
                    st.badge("Duplicates retained and flagged", color="orange")
            unmapped = quality.get("unmapped_asset_types", [])
            st.write(
                "**Unmapped asset types:**",
                ", ".join(unmapped) if unmapped else "None",
            )
            st.caption(quality["validation_note"])

    with st.expander("Reproducibility record", icon=":material/history_edu:"):
        reproducibility = st.columns(4)
        reproducibility[0].metric("Version", metadata["project_version"], border=True)
        reproducibility[1].metric(
            "Random seed", f"{metadata['random_seed']}", border=True
        )
        reproducibility[2].metric(
            "Geometry simplification",
            f"{metadata['geometry_simplification_metres']} m",
            border=True,
        )
        reproducibility[3].metric("Completed", completed_at, border=True)

    st.warning(
        "Responsible-use limitation: hazard locations use public Auckland Council data. "
        "Replacement values and damage ratios are illustrative assumptions, not Council financial data. "
        "Use these results for portfolio-screening demonstration only—not engineering, insurance, "
        "valuation, regulatory or investment decisions.",
        icon=":material/gavel:",
    )

st.caption(
    "Auckland public asset portfolio screening · Public hazard and asset-location data · "
    f"Model v{metadata['project_version']}"
)
