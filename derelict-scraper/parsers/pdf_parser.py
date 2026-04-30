import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.pdf")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
}


def _extract_with_pdfplumber(filepath: Path) -> pd.DataFrame:
    import pdfplumber
    tables = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tbl = page.extract_table()
            if tbl:
                tables.extend(tbl)
    if not tables:
        return pd.DataFrame()
    header, *data = tables
    return pd.DataFrame(data, columns=header)


def _extract_with_tabula(filepath: Path) -> pd.DataFrame:
    try:
        import tabula
        dfs = tabula.read_pdf(str(filepath), pages="all", multiple_tables=True, silent=True)
        if dfs:
            return pd.concat(dfs, ignore_index=True)
    except Exception as exc:
        logger.warning("tabula fallback failed: %s", exc)
    return pd.DataFrame()


def parse(filepath: Path, column_map: dict) -> pd.DataFrame:
    df = _extract_with_pdfplumber(filepath)
    if df.empty:
        logger.info("pdfplumber found no tables, trying tabula")
        df = _extract_with_tabula(filepath)
    if df.empty:
        raise ValueError("Could not extract any tables from PDF")

    df.columns = [str(c).strip() if c else "" for c in df.columns]
    df = df.rename(columns=column_map)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError("No recognised columns found after column_map applied")

    return df[keep].dropna(how="all").reset_index(drop=True)
