from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_loads_verified_outputs_without_exceptions():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    assert not dashboard.exception
    assert len(dashboard.tabs) == 4
    assert len(dashboard.metric) >= 5
    assert len(dashboard.dataframe) == 1
    assert len(dashboard.multiselect) == 3
    assert all(widget.value == [] for widget in dashboard.multiselect)
