import logging
from datetime import datetime, timezone

import pandas as pd
import requests

logger = logging.getLogger("derelict.arcgis")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
}


def _unix_ms_to_iso(ms_val) -> str | None:
    if ms_val is None:
        return None
    try:
        ts = int(ms_val)
        if ts == 0:
            return None
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, TypeError, OSError):
        return None


def parse(url: str, column_map: dict, session: requests.Session) -> pd.DataFrame:
    norm_map = {k.lower(): v for k, v in column_map.items()}
    all_features = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": 1000,
        }
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise ValueError(f"ArcGIS API error: {data['error'].get('message', data['error'])}")

        features = data.get("features", [])
        all_features.extend(features)

        if not features or not data.get("exceededTransferLimit"):
            break
        offset += 1000

    if not all_features:
        return pd.DataFrame()

    rows = [{k.lower(): v for k, v in feat.get("attributes", {}).items()} for feat in all_features]
    df = pd.DataFrame(rows)
    df = df.rename(columns=norm_map)

    for date_col in ("date_entered_register", "valuation_date"):
        if date_col in df.columns:
            numeric_mask = pd.to_numeric(df[date_col], errors="coerce").notna()
            if numeric_mask.any():
                df.loc[numeric_mask, date_col] = df.loc[numeric_mask, date_col].apply(_unix_ms_to_iso)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError(f"No recognised columns found. Available: {list(df.columns)}")

    return df[keep].dropna(how="all").reset_index(drop=True)
