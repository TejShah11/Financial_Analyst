"""Excel export utility.

Converts structured records (a list of dictionaries) into a downloadable
``.xlsx`` workbook saved under the configured exports directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


def generate_excel(data: list[dict], filename: str = "export.xlsx") -> str:
    """Write ``data`` to an Excel workbook and return its absolute path.

    Args:
        data: Rows to export — each dict becomes one row, keys become columns.
        filename: Output file name; ``.xlsx`` is appended if missing.

    Returns:
        The absolute path to the written workbook.
    """
    exports_dir = get_settings().EXPORTS_DIR
    exports_dir.mkdir(parents=True, exist_ok=True)

    if not filename.lower().endswith(".xlsx"):
        filename = f"{filename}.xlsx"
    # Path(...).name strips any directory components — never trust raw names.
    output_path = exports_dir / Path(filename).name

    # An empty payload still produces a valid (empty) workbook rather than crash.
    frame = pd.DataFrame(data if data else [])
    frame.to_excel(output_path, index=False, engine="openpyxl")

    absolute = str(output_path.resolve())
    logger.info("Excel export written: %s (%d rows).", absolute, len(frame))
    return absolute
