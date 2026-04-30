import re
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.pdf")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
}

_DS_REF_RE = re.compile(r'^(DS\d+)\s+(.+)$')


def _fix_shifted_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Fix merged-cell PDFs where pdfplumber places header text one column right of the data."""
    cols = list(df.columns)
    named_idxs = [i for i, c in enumerate(cols) if c and str(c).strip()]
    if not named_idxs:
        return df
    all_empty = all(df.iloc[:, i].replace('', pd.NA).isna().all() for i in named_idxs)
    if not all_empty:
        return df
    all_left_has_data = all(
        i > 0 and not df.iloc[:, i - 1].replace('', pd.NA).isna().all()
        for i in named_idxs
    )
    if not all_left_has_data:
        return df
    new_cols = list(cols)
    for i in named_idxs:
        new_cols[i - 1] = cols[i]
        new_cols[i] = ''
    df = df.copy()
    df.columns = new_cols
    return df


def _find_header_row_idx(rows: list) -> int:
    """Return index of the first row where the majority of cells are non-None (skips title rows)."""
    for i, row in enumerate(rows[:10]):
        non_null = sum(v is not None for v in row)
        if non_null > len(row) / 2:
            return i
    return 0


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
    header_idx = _find_header_row_idx(tables)
    header = tables[header_idx]
    data = tables[header_idx + 1:]
    df = pd.DataFrame(data, columns=header)
    return _fix_shifted_headers(df)


def _extract_text_fallback(filepath: Path) -> pd.DataFrame:
    """Parse text-only PDFs where pdfplumber finds no table borders."""
    import pdfplumber
    rows = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                m = _DS_REF_RE.match(line)
                if m:
                    rows.append({"ds_ref": m.group(1), "address": m.group(2)})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


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
        logger.info("pdfplumber found no tables, trying text extraction")
        df = _extract_text_fallback(filepath)
    if df.empty:
        logger.info("text extraction empty, trying tabula")
        df = _extract_with_tabula(filepath)
    if df.empty:
        raise ValueError("Could not extract any tables from PDF")

    df.columns = [re.sub(r'\s+', ' ', str(c)).strip() if c else "" for c in df.columns]
    df = df.rename(columns=column_map)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError("No recognised columns found after column_map applied")

    return df[keep].dropna(how="all").reset_index(drop=True)
