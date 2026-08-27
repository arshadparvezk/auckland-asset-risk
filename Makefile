.PHONY: install run refresh test dashboard static-dashboard notebook all clean

install:
	python -m pip install -e ".[dev]"

run:
	python -m asset_risk.pipeline --project-root .

refresh:
	python -m asset_risk.pipeline --project-root . --refresh

test:
	pytest -q

dashboard:
	streamlit run app.py

static-dashboard:
	python scripts/build_static_dashboard.py

notebook:
	python scripts/execute_notebook_inprocess.py

all: run static-dashboard test

clean:
	rm -f outputs/*.csv outputs/*.parquet outputs/*.db outputs/*.json outputs/figures/*.png outputs/reports/*.html
