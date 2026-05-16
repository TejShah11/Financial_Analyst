"""Pandas REPL tool — Track B (quantitative analysis).

Loads the structured data files (stock price CSV, investor Excel sheet) into
pandas DataFrames and exposes them inside a sandboxed Python AST REPL. The agent
writes pandas code against these DataFrames to compute exact, math-correct
answers — something vector retrieval cannot do reliably.
"""

from __future__ import annotations

import logging

import pandas as pd
from langchain_experimental.tools import PythonAstREPLTool

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# Source files in data/raw/ and the DataFrame variable each is loaded into.
STOCK_CSV = "500209.csv"
INVESTOR_XLS = "investor-sheet.xls"


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


def _load_investor_df() -> pd.DataFrame | None:
    """Load the legacy .xls investor sheet (BIFF format → xlrd engine)."""
    path = get_settings().RAW_DATA_DIR / INVESTOR_XLS
    try:
        df = pd.read_excel(path, engine="xlrd")
        logger.info("Loaded investor_df from %s (%d rows).", path.name, len(df))
        return df
    except Exception:  # noqa: BLE001 - a missing/corrupt file must not break the tool
        logger.exception("Failed to load investor sheet %s", path)
        return None


def _describe_frame(name: str, df: pd.DataFrame) -> str:
    """Render a one-line schema summary the LLM can use to write valid code."""
    columns = ", ".join(f"'{c}'" for c in df.columns)
    return f"  - `{name}`: {len(df)} rows, {len(df.columns)} columns -> [{columns}]"


def get_tabular_tool() -> PythonAstREPLTool:
    """Build the pandas REPL tool with the financial DataFrames pre-loaded.

    Returns:
        A :class:`PythonAstREPLTool` whose namespace contains ``pd`` and the
        loaded DataFrames (``stock_df``, ``investor_df``). Its description lists
        the available variables and their schemas so the LLM knows what exists.
    """
    settings = get_settings()
    stock_df = _load_stock_df()
    investor_df = _load_investor_df()

    # Namespace exposed inside the REPL. DATA_FILES records on-disk locations so
    # the LLM can reload or inspect raw files if a DataFrame is unavailable.
    repl_namespace: dict[str, object] = {
        "pd": pd,
        "DATA_FILES": {
            "stock_df": str(settings.RAW_DATA_DIR / STOCK_CSV),
            "investor_df": str(settings.RAW_DATA_DIR / INVESTOR_XLS),
        },
    }

    schema_lines: list[str] = []
    if stock_df is not None:
        repl_namespace["stock_df"] = stock_df
        schema_lines.append(_describe_frame("stock_df", stock_df))
    if investor_df is not None:
        repl_namespace["investor_df"] = investor_df
        schema_lines.append(_describe_frame("investor_df", investor_df))

    schema_block = "\n".join(schema_lines) or "  (no data files could be loaded)"
    description = (
        "A Python REPL for exact quantitative analysis of Infosys structured "
        "financial data. Use it for any precise calculation, filtering, "
        "aggregation, or comparison over the stock-price or investor data.\n"
        "Pre-loaded variables (do NOT re-import or re-read them):\n"
        f"{schema_block}\n"
        "`pd` is pandas. `stock_df['Date']` is already a datetime column. "
        "Always end your code with a print(...) of the final answer."
    )

    logger.info("Pandas REPL tool ready with %d DataFrame(s).", len(schema_lines))
    return PythonAstREPLTool(locals=repl_namespace, description=description)
