"""Excel export utility.

Converts structured records into a downloadable ``.xlsx`` workbook. A single
table becomes one sheet; multiple tables (e.g. a four-quarter comparison whose
answer contains several Markdown tables) each become their own sheet, so no
table is silently dropped.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Characters Excel forbids in sheet names, plus the 31-char length limit.
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet_name(name: str, fallback: str) -> str:
    """Coerce a string into a valid Excel sheet name (<=31 chars, no specials)."""
    cleaned = _INVALID_SHEET_CHARS.sub(" ", name).strip()
    return cleaned[:31] if cleaned else fallback


def generate_excel(
    data: list[dict] | dict[str, list[dict]],
    filename: str = "export.xlsx",
) -> str:
    """Write ``data`` to an Excel workbook and return its absolute path.

    Args:
        data: Either a list of row dicts (written as a single sheet) or a
            mapping of sheet-name -> row dicts (one sheet per entry).
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

    # Normalise to a {sheet_name: records} mapping.
    sheets = data if isinstance(data, dict) else {"Sheet1": data}
    if not sheets:
        sheets = {"Sheet1": []}

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for index, (raw_name, records) in enumerate(sheets.items(), start=1):
            frame = pd.DataFrame(records if records else [])
            sheet_name = _safe_sheet_name(raw_name, fallback=f"Sheet{index}")
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

    absolute = str(output_path.resolve())
    logger.info("Excel export written: %s (%d sheet(s)).", absolute, len(sheets))
    return absolute
