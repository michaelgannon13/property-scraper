import re
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.excel")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date", "property_type",
}


def _find_header_row(filepath: Path, suffix: str, column_map: dict) -> int:
    keys = {k.lower().strip() for k in column_map}
    if suffix in (".xlsx", ".xls"):
        raw = pd.read_excel(filepath, header=None, dtype=str)
    else:
        raw = pd.read_csv(filepath, header=None, dtype=str)
    for i, row in raw.iterrows():
        cells = {str(c).lower().strip() for c in row if pd.notna(c)}
        if len(keys & cells) >= min(3, max(1, len(keys))):
            return int(i)
    return 0


def parse(filepath: Path, column_map: dict) -> pd.DataFrame:
    suffix = filepath.suffix.lower()
    header_row = _find_header_row(filepath, suffix, column_map)

    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, header=header_row, dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(filepath, header=header_row, dtype=str)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df.columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in df.columns]
    df = df.rename(columns=column_map)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError("No recognised columns found after column_map applied")

    return df[keep].dropna(how="all").reset_index(drop=True)
