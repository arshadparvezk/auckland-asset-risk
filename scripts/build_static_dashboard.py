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


def money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"NZ${value / 1_000_000_000:,.2f}b"
    if abs(value) >= 1_000_000:
        return f"NZ${value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"NZ${value / 1_000:,.0f}k"
    return f"NZ${value:,.0f}"


def top_table(frame: pd.DataFrame) -> str:
    rows = []
    for _, row in frame.nlargest(10, "priority_score").iterrows():
        name = row.get("description") or row.get("site_description") or row["asset_id"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(name))}</td>"
            f"<td>{html.escape(str(row['asset_type']))}</td>"
            f"<td>{html.escape(str(row['local_board']))}</td>"
            f"<td>{money(float(row['expected_annual_loss_nzd']))}</td>"
            f"<td><span class='risk {str(row['risk_band']).lower().replace(' ', '-')}'>{html.escape(str(row['risk_band']))}</span></td>"
            "</tr>"
        )
    return "".join(rows)


def build() -> Path:
    register = pd.read_csv(OUTPUTS / "asset_risk_register.csv")
    curve = pd.read_csv(OUTPUTS / "loss_exceedance_curve.csv")
    summary = pd.read_csv(OUTPUTS / "scenario_summary.csv").set_index("scenario")
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
    curve_html = pio.to_html(curve_fig, full_html=False, include_plotlyjs=False)

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
              <div class="chart">{pio.to_html(board_fig, full_html=False, include_plotlyjs=False)}</div>
              <div class="chart">{pio.to_html(hotspot_fig, full_html=False, include_plotlyjs=False)}</div>
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
    DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auckland Natural Hazard Asset Loss Engine</title>
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
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.chart,.table-card,.curve-card{{background:white;border-radius:12px;padding:12px;box-shadow:0 2px 9px #003b5c12}}
.table-card,.curve-card{{margin-top:18px;padding:22px}}h2{{color:var(--navy);margin:0 0 16px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:11px 9px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--navy)}}
.risk{{font-size:12px;font-weight:700;padding:4px 8px;border-radius:99px;background:#edf2f4}}.risk.very-high{{background:#fee4df;color:#9e2d16}}.risk.high{{background:#ffeadf;color:#a64420}}.risk.moderate{{background:#fff3cf;color:#7b5b00}}
.footer{{color:var(--muted);font-size:13px;margin-top:24px;line-height:1.5}}@media(max-width:850px){{.cards{{grid-template-columns:1fr 1fr}}.chart-grid{{grid-template-columns:1fr}}}}@media(max-width:520px){{.cards{{grid-template-columns:1fr}}header h1{{font-size:27px}}.table-wrap{{overflow-x:auto}}}}
</style>
<script>{plotly_js}</script>
</head><body>
<header><h1>Auckland Natural Hazard Asset Loss Engine</h1><p>Coastal inundation exposure, probabilistic loss and asset-resilience prioritisation</p></header>
<main><div class="notice"><strong>Decision prototype:</strong> public asset locations and hazard extents are real Auckland Council open data. Replacement values and damage functions are transparent illustrative assumptions, not Council financial data.</div>
<nav class="tabs" aria-label="Scenario selector">{tabs}</nav>{''.join(panels)}
<section class="curve-card"><h2>Portfolio scenario comparison</h2>{curve_html}</section>
<p class="footer">Model run: {html.escape(run['completed_at_utc'])} · {run['monte_carlo_iterations']:,} Monte Carlo iterations · {quality['record_count']:,} asset records · 20 m generalised hazard geometry. Portfolio screening only; not for engineering, insurance, valuation or investment decisions.</p>
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
