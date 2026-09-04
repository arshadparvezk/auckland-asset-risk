from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_loads_verified_outputs_without_exceptions():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    assert not dashboard.exception
    assert len(dashboard.tabs) == 5
    metric_labels = {metric.label for metric in dashboard.metric}
    assert {
        "Assets in view",
        "Assets with modelled loss",
        "Illustrative portfolio value",
        "Expected annual loss",
        "Expected event loss",
        "P90 event loss",
        "Liquefaction coverage",
        "Damage Possible",
        "Dual-hazard review",
    }.issubset(metric_labels)
    assert len(dashboard.dataframe) >= 2
    assert len(dashboard.multiselect) == 2
    assert all(widget.value == [] for widget in dashboard.multiselect)
    assert len(dashboard.pills) == 1
    assert dashboard.pills("filter_risks").value == []
    assert len(dashboard.toggle) == 1
    assert dashboard.toggle("filter_exposed").value is False
    assert dashboard.selectbox("filter_scenario").value == "slr_1m"
    assert len(dashboard.download_button) >= 4


def test_resilience_lenses_and_liquefaction_map_render_without_exceptions():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    dashboard.segmented_control("resilience_lens").set_value("Growth & demand").run()
    assert not dashboard.exception
    assert any(metric.label == "Auckland benchmark" for metric in dashboard.metric)

    dashboard.segmented_control("resilience_lens").set_value(
        "Intervention economics"
    ).run()
    assert not dashboard.exception
    assert any(metric.label == "Illustrative BCR" for metric in dashboard.metric)

    dashboard.segmented_control("map_lens").set_value(
        "Liquefaction vulnerability"
    ).run()
    assert not dashboard.exception


def test_dashboard_reset_restores_unfiltered_default_view():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    dashboard.multiselect("filter_boards").set_value(["Rodney"]).run()
    dashboard.multiselect("filter_asset_types").set_value(["Public Toilet"]).run()
    dashboard.pills("filter_risks").set_value(["Very high"]).run()
    dashboard.text_input("filter_search").set_value("toilet").run()
    dashboard.toggle("filter_exposed").set_value(True).run()

    reset_button = next(
        button for button in dashboard.button if button.label == "Reset all filters"
    )
    reset_button.click().run()

    assert not dashboard.exception
    assert all(widget.value == [] for widget in dashboard.multiselect)
    assert dashboard.pills("filter_risks").value == []
    assert dashboard.text_input("filter_search").value == ""
    assert dashboard.toggle("filter_exposed").value is False
    assert dashboard.selectbox("filter_scenario").value == "slr_1m"


def test_scenario_change_clears_dependent_portfolio_filters():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    dashboard.multiselect("filter_boards").set_value(["Rodney"]).run()
    dashboard.multiselect("filter_asset_types").set_value(["Public Toilet"]).run()
    dashboard.pills("filter_risks").set_value(["Very high"]).run()
    dashboard.selectbox("filter_scenario").set_value("baseline").run()

    assert not dashboard.exception
    assert dashboard.selectbox("filter_scenario").value == "baseline"
    assert all(widget.value == [] for widget in dashboard.multiselect)
    assert dashboard.pills("filter_risks").value == []


def test_empty_search_result_renders_a_safe_empty_state():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    dashboard.text_input("filter_search").set_value(
        "asset-that-does-not-exist-9281"
    ).run()

    assert not dashboard.exception
    assets_metric = next(
        metric for metric in dashboard.metric if metric.label == "Assets in view"
    )
    assert assets_metric.value == "0"


def test_asset_inspector_handles_missing_site_and_zero_loss_records():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    dashboard = AppTest.from_file(str(app_path), default_timeout=60).run()

    dashboard.text_input("filter_search").set_value("park-1685").run()

    assert not dashboard.exception
    assert any("Site not supplied" in caption.value for caption in dashboard.caption)

    dashboard.text_input("filter_search").set_value("park-1684").run()

    assert not dashboard.exception
    assert any(
        "No modelled treatment benefit" in message.value
        for message in dashboard.info
    )
