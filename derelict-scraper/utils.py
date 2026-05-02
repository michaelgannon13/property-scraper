import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

import requests

LOGS_DIR = Path("logs")
DATA_DIR = Path("data")

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d/%m/%y")

_STANDARD_COLUMNS = [
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
]


def _today() -> date:
    return date.today()


def setup_logging(run_id_str: str) -> logging.Logger:
    LOGS_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("derelict")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fh = logging.FileHandler(LOGS_DIR / f"{run_id_str}.log")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def download_file(url: str, council_code: str, run_id_str: str,
                  session: requests.Session, force_suffix: str = None) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    suffix = force_suffix or Path(url.split("?")[0]).suffix or ".bin"
    dest = DATA_DIR / f"{council_code}_{run_id_str}{suffix}"
    resp = session.get(url, timeout=30, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            fh.write(chunk)
    return dest


def parse_date(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "nan", "NaT", "None"):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


def parse_valuation(value) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s in ("", "nan", "None"):
        return None
    cleaned = re.sub(r"[€,\s]", "", s)
    try:
        return float(cleaned)
    except ValueError:
        return None


def days_since(iso_date: Optional[str]) -> Optional[int]:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date)
        return (_today() - d).days
    except ValueError:
        return None


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


_HEADER_PATTERNS = re.compile(
    r'^(address of (owner|site)|reasons?|photographs?|site ref(erence)?|'
    r'reg(ister)? no\.?|owner|occupier|electoral area|valuation|date entered)$',
    re.IGNORECASE,
)


def _is_header_row(entry: dict) -> bool:
    address = str(entry.get("address") or "").strip()
    ds_ref = str(entry.get("ds_ref") or "").strip()
    return bool(_HEADER_PATTERNS.match(address) or _HEADER_PATTERNS.match(ds_ref))


def normalise_dataframe(df, council_code: str, source_file: str) -> list:
    import pandas as pd
    rows = []
    for _, row in df.iterrows():
        entry = {"council": council_code, "raw_source_file": source_file}
        for col in _STANDARD_COLUMNS:
            raw = row.get(col) if col in row.index else None
            if raw is not None and pd.isna(raw):
                raw = None
            entry[col] = raw

        if entry["ds_ref"] is None and entry["address"] is None:
            continue

        if _is_header_row(entry):
            continue

        entry["date_entered_register"] = parse_date(entry["date_entered_register"])
        entry["valuation_date"] = parse_date(entry["valuation_date"])
        entry["valuation"] = parse_valuation(entry["valuation"])
        entry["days_on_register"] = days_since(entry["date_entered_register"])
        entry["last_updated"] = date.today().isoformat()
        rows.append(entry)
    return rows
