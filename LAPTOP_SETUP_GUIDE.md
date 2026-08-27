# Laptop Setup and Complete Project Execution Guide

This guide explains how to run the **Auckland Natural Hazard Asset Loss Engine** on a Windows laptop from the supplied source-code package. It covers the professional dashboard, the complete data pipeline, automated tests, generated outputs and a practical development workflow.

## 1. What this project demonstrates

The project is an end-to-end asset financial-risk prototype. It:

1. downloads public Auckland Council asset and coastal-inundation data;
2. cleans and standardises more than 2,000 asset records;
3. performs geospatial exposure analysis for four annual exceedance probabilities;
4. applies explicit financial-value and vulnerability assumptions;
5. performs 10,000-iteration Monte Carlo uncertainty analysis;
6. generates loss-exceedance curves and expected annual loss;
7. prioritises assets using financial loss and service criticality;
8. exports CSV, Parquet, SQLite, charts, an executive report and dashboards.

The package contains verified outputs, so the dashboard can be opened immediately after installing the environment. An internet connection is required only when re-downloading Auckland Council data or loading online map tiles.

## 2. Recommended laptop specification

- Windows 10 or Windows 11, 64-bit
- Python 3.11, 64-bit
- 8 GB RAM minimum; 16 GB recommended
- Approximately 5 GB free disk space
- Stable internet connection for the first full pipeline run
- No GPU is required

The model runs on a normal CPU. Your Intel i5-class laptop is suitable for this portfolio project.

## 3. Install the required software

### Step 3.1: Install Python 3.11

1. Open <https://www.python.org/downloads/>.
2. Download a 64-bit Python 3.11 installer.
3. Run the installer.
4. Select **Add python.exe to PATH**.
5. Select **Install Now**.
6. Open Command Prompt and verify:

```bat
py -3.11 --version
```

The result should begin with `Python 3.11`.

### Step 3.2: Install Visual Studio Code

1. Download VS Code from <https://code.visualstudio.com/>.
2. Install it with the default options.
3. Open VS Code and install the Microsoft **Python** extension.

Git is optional but recommended if you plan to publish the project on GitHub.

## 4. Extract and open the project

1. Download the supplied ZIP file.
2. Create a simple folder such as `C:\Projects`.
3. Extract the ZIP so the project is located at:

```text
C:\Projects\auckland-asset-risk
```

4. Open VS Code.
5. Select **File > Open Folder**.
6. Choose `C:\Projects\auckland-asset-risk`.

Avoid running the project directly inside the ZIP file.

## 5. Automatic Windows setup

The easiest setup method is the supplied batch file.

1. In the project folder, open `scripts\windows`.
2. Double-click `setup.bat`.
3. Wait while it creates an isolated `.venv` environment, installs the dependencies and runs the model tests.
4. Confirm that the final message says `SETUP COMPLETED SUCCESSFULLY`.

The setup can also be started from Command Prompt:

```bat
cd /d C:\Projects\auckland-asset-risk
scripts\windows\setup.bat
```

## 6. Launch the high-standard dashboard

### Fully offline dashboard (no Python or server)

To open the portable dashboard, double-click:

```text
scripts\windows\open_offline_dashboard.bat
```

You can also open `dashboard\index.html` directly in Chrome or Edge. This is a
self-contained file: the chart library, model results and dashboard controls
are embedded, so it works without Python, Streamlit, a local server or an
internet connection.

The offline dashboard includes scenario tabs, KPI cards, interactive charts
and priority tables. Use the Streamlit version when you need live filtering,
search, detailed data-quality views or CSV downloads.

### Interactive Streamlit dashboard

Double-click:

```text
scripts\windows\run_dashboard.bat
```

The dashboard should open automatically at:

```text
http://localhost:8501
```

If it does not open automatically, copy that address into Chrome or Edge. Keep the Command Prompt window open while using the dashboard. Press `Ctrl+C` in the window to stop it.

### Dashboard sections

- **Executive overview:** scenario KPIs, expected annual loss comparison, local-board ranking and loss-exceedance curve.
- **Exposure map:** interactive asset-level risk locations with financial-loss tooltips.
- **Priority register:** filtered, ranked asset table with CSV downloads.
- **Model & data quality:** methodology, equations, limitations, validation results and reproducibility metadata.

Use the left sidebar to change the scenario, local boards, asset types, risk bands and search criteria.

## 7. Execute the complete modelling pipeline

The included outputs let you view the dashboard immediately. To demonstrate that you can reproduce the analysis from source data, execute the full pipeline.

Double-click:

```text
scripts\windows\run_pipeline.bat
```

On the first run, the pipeline automatically downloads the required public data because `data\raw` is not included in the package. It then performs data validation, geospatial joins, 10,000 Monte Carlo iterations, EAL integration, database creation and report generation.

To force a fresh download later, run this in Command Prompt:

```bat
scripts\windows\run_pipeline.bat --refresh
```

After successful execution, launch `run_dashboard.bat` again. Streamlit automatically reloads the updated outputs.

## 8. Manual command-by-command execution

Use this method when you want to understand or demonstrate every technical step.

Open Command Prompt in the project folder:

```bat
cd /d C:\Projects\auckland-asset-risk
```

Create the virtual environment:

```bat
py -3.11 -m venv .venv
```

Activate it:

```bat
.venv\Scripts\activate.bat
```

Upgrade the packaging tools:

```bat
python -m pip install --upgrade pip setuptools wheel
```

Install the project and development dependencies:

```bat
python -m pip install -e ".[dev]"
```

Run the automated tests:

```bat
python -m pytest -q
```

Run the complete pipeline and download fresh public data:

```bat
python -m asset_risk.pipeline --project-root . --refresh
```

Rebuild the standalone HTML dashboard:

```bat
python scripts\build_static_dashboard.py
```

Launch the interactive dashboard:

```bat
python -m streamlit run app.py
```

Stop the dashboard with `Ctrl+C`. Deactivate the environment when finished:

```bat
deactivate
```

## 9. Project execution order

```text
Auckland Council ArcGIS services
        |
        v
Download and cache public data
        |
        v
Clean, standardise and validate assets
        |
        v
Spatial exposure across eight hazard layers
        |
        v
Financial assumptions and Monte Carlo uncertainty
        |
        v
Loss-exceedance curves and expected annual loss
        |
        v
Priority register, SQLite database and reports
        |
        v
Streamlit and standalone HTML dashboards
```

## 10. Important project files

| File or folder | Purpose |
| --- | --- |
| `app.py` | Professional interactive Streamlit dashboard |
| `config/model.yml` | Data sources, scenarios and transparent assumptions |
| `src/asset_risk/data.py` | ArcGIS download, standardisation and data quality |
| `src/asset_risk/model.py` | Exposure, Monte Carlo loss and EAL calculations |
| `src/asset_risk/pipeline.py` | Complete orchestration workflow |
| `src/asset_risk/reporting.py` | Figures, database and executive report |
| `tests/test_model.py` | Automated statistical and financial-model tests |
| `notebooks/auckland_asset_risk_model.ipynb` | Executed technical walkthrough |
| `outputs/` | Verified model results and decision outputs |
| `dashboard/index.html` | Standalone recruiter dashboard |
| `docs/METHODOLOGY.md` | Detailed assumptions, equations and limitations |
| `sql/portfolio_queries.sql` | Example database analysis queries |
| `r/validate_loss_curve.R` | Independent R validation of EAL calculations |

## 11. Outputs generated by the pipeline

| Output | Meaning |
| --- | --- |
| `outputs/asset_risk_register.csv` | Asset-level EAL, priority score and risk band |
| `outputs/loss_exceedance_curve.csv` | Expected, P50 and P90 losses by event probability |
| `outputs/scenario_summary.csv` | Current, +1 m SLR and treatment comparison |
| `outputs/asset_event_exposure.parquet` | Event-level exposure results |
| `outputs/risk_model.db` | Queryable SQLite analytical database |
| `outputs/data_quality_report.json` | Auditable data-validation results |
| `outputs/figures/` | Publication-quality model charts |
| `outputs/reports/executive_summary.html` | Non-technical decision summary |

## 12. Development workflow in VS Code

1. Open the project folder in VS Code.
2. Press `Ctrl+Shift+P`.
3. Select **Python: Select Interpreter**.
4. Choose `.venv\Scripts\python.exe`.
5. Modify assumptions only in `config/model.yml`.
6. Run `scripts\windows\run_tests.bat` after changing model code.
7. Run the pipeline again after changing assumptions or data logic.
8. Refresh the dashboard and confirm that the outputs remain reasonable.

Recommended changes for further development include adding new hazards, replacing illustrative values with authorised financial data, introducing intervention costs, and adding benefit-cost analysis.

## 13. Publish the source code to GitHub

Create an empty GitHub repository named `auckland-asset-risk`. Then run the following from the project folder after installing Git:

```bat
git init
git add .
git commit -m "Build Auckland natural hazard asset loss engine"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/auckland-asset-risk.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. Do not upload `.venv` or downloaded `data/raw` files; the included `.gitignore` excludes them.

## 14. Troubleshooting

### `py` is not recognised

Reinstall 64-bit Python 3.11 and select **Add python.exe to PATH**. Close and reopen Command Prompt.

### PowerShell blocks environment activation

Use Command Prompt and the supplied `.bat` files. They do not require a PowerShell execution-policy change.

### GeoPandas or PyArrow installation fails

Confirm that you are using 64-bit Python 3.11, upgrade pip, and retry:

```bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

### Public-data download times out

Check your connection and rerun the pipeline. The downloader uses retries, pagination and local caching. Avoid repeatedly using `--refresh` after the raw files have downloaded successfully.

### The interactive map is blank

Check your internet connection because the background map uses online tiles. The model data and other charts remain local.

### Port 8501 is already in use

Run the dashboard on another port:

```bat
python -m streamlit run app.py --server.port 8502
```

Then open `http://localhost:8502`.

### Dashboard says outputs are missing

Run:

```bat
scripts\windows\run_pipeline.bat
```

## 15. How to explain the project in an interview

Use this concise explanation:

> I built an end-to-end probabilistic natural-hazard loss model for more than 2,000 Auckland public assets. The pipeline downloads and validates Auckland Council open data, performs geospatial exposure analysis across multiple coastal-inundation probabilities, propagates financial uncertainty through 10,000 Monte Carlo iterations, produces loss-exceedance curves and expected annual loss, and publishes an interactive decision dashboard and asset-priority register. I clearly separated official hazard and asset data from illustrative financial assumptions so the results remain transparent and responsible.

Never describe the illustrative replacement values or damage ratios as official Auckland Council financial data.
