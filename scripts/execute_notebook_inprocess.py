"""Execute the portfolio notebook without a Jupyter socket-based kernel.

Some restricted build environments disallow local ZeroMQ sockets. This runner
executes code cells in one Python namespace, captures stdout, rich HTML and
Matplotlib PNG outputs, and writes a valid executed notebook with counts.
"""

from __future__ import annotations

import base64
import io
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/asset-risk-mpl")

import matplotlib.pyplot as plt
import nbformat
from nbformat.v4 import new_output

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "auckland_asset_risk_model.ipynb"


def execute() -> tuple[int, int]:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    namespace: dict = {"__name__": "__main__", "__file__": str(NOTEBOOK)}
    execution_count = 0
    output_count = 0
    previous_cwd = Path.cwd()
    os.chdir(ROOT)

    try:
        for index, cell in enumerate(notebook.cells):
            cell["id"] = cell.get("id") or f"cell-{index:02d}"
            if cell.cell_type != "code":
                continue
            execution_count += 1
            cell.execution_count = execution_count
            cell.outputs = []
            rich_outputs = []

            def capture_display(*objects, **_kwargs):
                for value in objects:
                    if hasattr(value, "to_html"):
                        rendered = value.to_html()
                    elif hasattr(value, "_repr_html_"):
                        rendered = value._repr_html_()
                    else:
                        rendered = None
                    data = {"text/plain": repr(value)}
                    if rendered:
                        data["text/html"] = rendered
                    rich_outputs.append(new_output("display_data", data=data))

            # The first cell imports IPython.display.display; override that
            # name before each later cell so rich tables are captured.
            if execution_count > 1:
                namespace["display"] = capture_display

            stdout = io.StringIO()
            stderr = io.StringIO()
            figures_before = set(plt.get_fignums())
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exec(compile(cell.source, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace)
            except Exception:
                cell.outputs.append(
                    new_output(
                        "error",
                        ename="NotebookExecutionError",
                        evalue=traceback.format_exc().splitlines()[-1],
                        traceback=traceback.format_exc().splitlines(),
                    )
                )
                nbformat.write(notebook, NOTEBOOK)
                raise

            if stdout.getvalue():
                cell.outputs.append(new_output("stream", name="stdout", text=stdout.getvalue()))
            if stderr.getvalue():
                cell.outputs.append(new_output("stream", name="stderr", text=stderr.getvalue()))
            cell.outputs.extend(rich_outputs)

            for figure_number in sorted(set(plt.get_fignums()) - figures_before):
                figure = plt.figure(figure_number)
                buffer = io.BytesIO()
                figure.savefig(buffer, format="png", dpi=130, bbox_inches="tight")
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                cell.outputs.append(
                    new_output(
                        "display_data",
                        data={"image/png": encoded, "text/plain": "<Matplotlib figure>"},
                    )
                )
                plt.close(figure)
            output_count += len(cell.outputs)
    finally:
        os.chdir(previous_cwd)

    notebook.metadata["execution"] = {
        "engine": "in-process reproducible runner",
        "status": "all code cells completed",
    }
    nbformat.write(notebook, NOTEBOOK)
    return execution_count, output_count


if __name__ == "__main__":
    cells, outputs = execute()
    print(f"executed_code_cells={cells}; output_blocks={outputs}; notebook={NOTEBOOK}")

