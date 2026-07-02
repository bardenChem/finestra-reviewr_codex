from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

ExportFormat = Literal["csv", "json", "markdown"]


class ComparisonExporter:
    """Export evidence matrices to deterministic file formats."""

    def export(self, frame: pd.DataFrame, output_dir: Path, *, export_format: ExportFormat) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"comparison.{self._extension(export_format)}"
        if export_format == "csv":
            frame.to_csv(path, index=False)
        elif export_format == "json":
            frame.to_json(path, orient="records", indent=2)
        else:
            path.write_text(frame.to_markdown(index=False), encoding="utf-8")
        return path

    def _extension(self, export_format: ExportFormat) -> str:
        return "md" if export_format == "markdown" else export_format
