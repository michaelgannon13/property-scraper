import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.html")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
}


def parse(filepath: Path, column_map: dict) -> pd.DataFrame:
    """Parse an HTML file containing a table using pandas read_html."""
    try:
        tables = pd.read_html(filepath)
    except Exception as exc:
        raise ValueError(f"Could not extract HTML table from {filepath.name}: {exc}") from exc

    if not tables:
        raise ValueError("No tables found in HTML file")

    # Pick the largest table (most rows = most data)
    df = max(tables, key=len)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=column_map)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError("No recognised columns found after column_map applied")

    return df[keep].dropna(how="all").reset_index(drop=True)
