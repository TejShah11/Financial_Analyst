"""Pandas REPL tool — Track B (quantitative analysis).

Loads the structured data files into pandas DataFrames and exposes them inside a
sandboxed Python AST REPL. The agent writes pandas code against these DataFrames
to compute exact, math-correct answers.

The investor workbook is a multi-sheet file whose data sheets carry several
title rows above the real header. Each sheet's header row is *detected* (not
assumed) before loading, so the LLM receives DataFrames with meaningful column
names instead of garbled ones.
"""

from __future__ import annotations

import logging
import re

import pandas as pd
from langchain_experimental.tools import PythonAstREPLTool

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Source files in data/raw/.
STOCK_CSV = "500209.csv"
INVESTOR_XLS = "investor-sheet.xls"

# Investor workbook sheets worth loading -> the REPL variable each becomes.
# (The "Index" sheet is a table of contents and is skipped.)
_INVESTOR_SHEETS: dict[str, str] = {
    "1 INR- Consol Profit Loss": "pnl_inr_df",
    "2 INR - Consol Balance Sheet": "balancesheet_inr_df",
    "3 INR - Consol Cash flow": "cashflow_inr_df",
    "4 USD - Consol Profit Loss": "pnl_usd_df",
    "5 USD - Consol Balance Sheet": "balancesheet_usd_df",
    "6 USD - Consol Cash flow": "cashflow_usd_df",
    "7 Operating Metrics": "operating_metrics_df",
    "Disaggregate Revenue": "disaggregated_revenue_df",
}

# Variable names the agent may reference for investor-sheet data. Used by the
# quantitative node to attribute the INVESTOR_XLS source.
INVESTOR_DF_NAMES: tuple[str, ...] = tuple(_INVESTOR_SHEETS.values())

# A header cell in the investor workbook looks like "Q1 15", "Q4 26", "FY 26".
_PERIOD_RE = re.compile(r"^(Q[1-4]|FY)\s*\d{2,4}$", re.IGNORECASE)


def _load_stock_df() -> pd.DataFrame | None:
    """Load the daily stock-price CSV, parsing the Date column to datetime."""
    path = get_settings().RAW_DATA_DIR / STOCK_CSV
    try:
        df = pd.read_csv(path)
        # Dates arrive as e.g. "30-March-2026"; parse so .dt operations work.
        df["Date"] = pd.to_datetime(df["Date"], format="%d-%B-%Y", errors="coerce")
        logger.info("Loaded stock_df from %s (%d rows).", path.name, len(df))
        return df
    except Exception:  # noqa: BLE001 - a missing/corrupt file must not break the tool
        logger.exception("Failed to load stock CSV %s", path)
        return None


def _detect_header_row(raw: pd.DataFrame) -> int | None:
    """Find the row index that holds the period header (Q1 15 … FY 26)."""
    for row_index in range(min(15, len(raw))):
        period_cells = sum(
            1
            for value in raw.iloc[row_index]
            if _PERIOD_RE.match(str(value).strip())
        )
        if period_cells >= 4:
            return row_index
    return None


def _load_investor_sheet(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame | None:
    """Load and validate one investor-workbook sheet, or return None on failure."""
    try:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        header_row = _detect_header_row(raw)
        if header_row is None:
            logger.warning("No period header found in sheet %r; skipping.", sheet_name)
            return None

        df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
        # Drop fully empty columns (the workbook has a blank leading column).
        df = df.dropna(axis=1, how="all")
        if df.empty or len(df.columns) < 2:
            return None

        # The first surviving column holds the line-item labels.
        df = df.rename(columns={df.columns[0]: "Metric"})
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(subset=["Metric"]).reset_index(drop=True)
        return df
    except Exception:  # noqa: BLE001 - a bad sheet must not break the whole tool
        logger.exception("Failed to load investor sheet %r", sheet_name)
        return None


def _load_investor_frames() -> dict[str, pd.DataFrame]:
    """Load every usable investor-workbook sheet into named DataFrames."""
    path = get_settings().RAW_DATA_DIR / INVESTOR_XLS
    frames: dict[str, pd.DataFrame] = {}
    try:
        xls = pd.ExcelFile(path, engine="xlrd")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to open investor workbook %s", path)
        return frames

    for sheet_name, var_name in _INVESTOR_SHEETS.items():
        if sheet_name not in xls.sheet_names:
            logger.warning("Investor sheet %r not present in workbook.", sheet_name)
            continue
        df = _load_investor_sheet(xls, sheet_name)
        if df is not None:
            frames[var_name] = df
            logger.info("Loaded %s from sheet %r (%d rows).", var_name, sheet_name, len(df))
    return frames


def _describe(name: str, df: pd.DataFrame, note: str) -> str:
    """Render a compact one-line schema summary the LLM can write code against."""
    columns = list(df.columns)
    if len(columns) > 10:
        shown = ", ".join(f"'{c}'" for c in columns[:4])
        shown += f", … , " + ", ".join(f"'{c}'" for c in columns[-2:])
    else:
        shown = ", ".join(f"'{c}'" for c in columns)
    return f"  - `{name}` ({note}): {len(df)} rows x {len(df.columns)} cols -> [{shown}]"


def get_tabular_tool() -> PythonAstREPLTool:
    """Build the pandas REPL tool with the financial DataFrames pre-loaded.

    Returns:
        A :class:`PythonAstREPLTool` whose namespace contains ``pd`` and the
        loaded DataFrames. Its description lists every available variable and
        its real schema so the LLM writes valid code.
    """
    repl_namespace: dict[str, object] = {"pd": pd}
    schema_lines: list[str] = []

    stock_df = _load_stock_df()
    if stock_df is not None:
        repl_namespace["stock_df"] = stock_df
        schema_lines.append(
            _describe("stock_df", stock_df, "daily Infosys share-price history")
        )

    investor_frames = _load_investor_frames()
    for var_name, frame in investor_frames.items():
        repl_namespace[var_name] = frame
        sample_metrics = ", ".join(str(m) for m in frame["Metric"].head(3))
        schema_lines.append(
            _describe(var_name, frame, f"investor sheet; e.g. metrics: {sample_metrics}")
        )

    schema_block = "\n".join(schema_lines) or "  (no data files could be loaded)"
    description = (
        "A Python REPL for exact quantitative analysis of Infosys structured "
        "financial data. Use it for any precise calculation, filtering, "
        "aggregation, or comparison.\n"
        "Pre-loaded variables (do NOT re-import or re-read them):\n"
        f"{schema_block}\n\n"
        "STOCK_DF COLUMNS (exact spelling, case-sensitive):\n"
        "  'Date' (datetime), 'Open Price', 'High Price', 'Low Price', 'Close Price',\n"
        "  'WAP', 'No.of Shares', 'No. of Trades', 'Total Turnover (Rs.)',\n"
        "  'Deliverable Quantity', '% Deli. Qty to Traded Qty', 'Spread High-Low',\n"
        "  'Spread Close-Open'\n\n"
        "`pd` is pandas. `stock_df['Date']` is a datetime column.\n"
        "The investor DataFrames are wide: a 'Metric' column names each "
        "line item (a row), and period columns ('Q1 26', 'FY 26', …) hold the "
        "values. To read a figure, filter by Metric then select the period "
        "column, e.g. `pnl_usd_df.loc[pnl_usd_df['Metric'] == 'Revenues', 'Q3 26']`.\n"
        "INR sheets are in ₹ crore; USD sheets are in US$ million.\n"
        "Always end your code with a print(...) of the final answer."
    )

    logger.info(
        "Pandas REPL tool ready with %d DataFrame(s).", len(schema_lines)
    )
    return PythonAstREPLTool(locals=repl_namespace, description=description)
