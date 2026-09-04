import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFLINE_DASHBOARD = ROOT / "dashboard" / "index.html"


def test_offline_dashboard_is_self_contained_and_initialises_charts():
    document = OFFLINE_DASHBOARD.read_text(encoding="utf-8")

    assert "plotly.js v" in document
    assert document.index("plotly.js v") < document.index("Plotly.newPlot")
    assert len(re.findall(r"Plotly\.newPlot", document)) == 10

    external_resource = re.compile(
        r"<(?:script|img|link)\b[^>]+(?:src|href)=[\"']https?://",
        flags=re.IGNORECASE,
    )
    assert external_resource.search(document) is None
    assert "data-target='baseline'" in document
    assert "data-target='slr_1m'" in document
    assert "data-target='slr_1m_mitigated'" in document
    assert 'id="multi-hazard-screening"' in document
    assert 'id="growth-and-demand"' in document
    assert 'id="intervention-economics"' in document
    assert 'id="liquefaction-vulnerability"' in document
    assert 'id="growth-demand"' in document
    assert 'id="intervention-value"' in document
    assert "not property-level earthquake risk" in document
    assert "not an investment recommendation" in document
    assert ">nan<" not in document.lower()
