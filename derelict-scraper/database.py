import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import requests as _requests
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path("data/derelict_sites.db")

_EDGE_FUNCTION_URL = os.getenv(
    "SUPABASE_UPSERT_URL",
    "https://wpgrcieidaalkkgococi.supabase.co/functions/v1/upsert_property",
)
_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndwZ3JjaWVpZGFhbGtrZ29jb2NpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzODk0NzksImV4cCI6MjA5MDk2NTQ3OX0.W4lD56ON6bV3YKytEaaamxHcWA1at21oVlLxY1rZBKo",
)
_INGEST_API_KEY = os.getenv(
    "INGEST_API_KEY",
    "@u#9XQr!TNdV&G%rQIqivfh!QMWvc*UIDNrwNT0L",
)

_UPSERT_HEADERS = {
    "apikey": _ANON_KEY,
    "Authorization": f"Bearer {_ANON_KEY}",
    "x-api-key": _INGEST_API_KEY,
    "Content-Type": "application/json",
}


# Derelict Sites Levy rates by council (% of market value per year).
# Minimum is 3% under the Derelict Sites Act 1990. DCC charges 7%.
# All others default to 3% unless confirmed otherwise.
_LEVY_RATES = {
    "DCC":  0.07,
    "SDCC": 0.03,
    "DLR":  0.03,
    "FCC":  0.03,
}
_DEFAULT_LEVY_RATE = 0.03

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe_date(value) -> str | None:
    if not value:
        return None
    s = str(value).strip()[:10]
    if _ISO_DATE_RE.match(s):
        if s <= datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            return s
    return None


def _estimated_levy(prop: dict):
    valuation = prop.get("valuation")
    if not valuation:
        return None
    rate = _LEVY_RATES.get(prop.get("council"), _DEFAULT_LEVY_RATE)
    return round(valuation * rate, 2)


def _build_payload(prop: dict) -> dict:
    """Map local SQLite field names to the Edge Function's expected field names."""
    return {
        "county":             prop.get("council"),
        "council_reference":  prop.get("ds_ref"),
        "address":            prop.get("address"),
        "owner":              prop.get("owner"),
        "owner_address":      prop.get("owner_address"),
        "occupier":           prop.get("occupier"),
        "electoral_area":     prop.get("electoral_area"),
        "date_registered":    _safe_date(prop.get("date_entered_register")),
        "valuation":          prop.get("valuation"),
        "valuation_date":     _safe_date(prop.get("valuation_date")),
        "days_on_register":   prop.get("days_on_register"),
        "building_type":      prop.get("property_type"),
        "latitude":           prop.get("lat"),
        "longitude":          prop.get("lng"),
        "reg_no":               prop.get("reg_no"),
        "raw_source_file":      prop.get("raw_source_file"),
        "estimated_annual_levy": _estimated_levy(prop),
    }


def upsert_property(prop: dict) -> dict:
    """POST a single property to the Supabase upsert_property Edge Function."""
    if not prop.get("address") or not prop.get("ds_ref"):
        raise ValueError(f"skipped: missing {'address' if not prop.get('address') else 'ds_ref'}")
    payload = _build_payload(prop)
    resp = _requests.post(_EDGE_FUNCTION_URL, json=payload, headers=_UPSERT_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS derelict_sites (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                council                TEXT NOT NULL,
                ds_ref                 TEXT,
                reg_no                 TEXT,
                address                TEXT,
                owner                  TEXT,
                owner_address          TEXT,
                occupier               TEXT,
                electoral_area         TEXT,
                date_entered_register  TEXT,
                valuation              REAL,
                valuation_date         TEXT,
                days_on_register       INTEGER,
                last_updated           TEXT,
                raw_source_file        TEXT,
                lat                    REAL,
                lng                    REAL,
                property_type          TEXT,
                first_seen             TEXT,
                UNIQUE(council, ds_ref)
            );

            CREATE TABLE IF NOT EXISTS scrape_log (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                council        TEXT    NOT NULL,
                run_at         TEXT    NOT NULL,
                status         TEXT    NOT NULL,
                rows_inserted  INTEGER,
                source_file    TEXT,
                error_msg      TEXT
            );
        """)
        for col, coltype in (("lat", "REAL"), ("lng", "REAL"), ("property_type", "TEXT"),
                             ("first_seen", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE derelict_sites ADD COLUMN {col} {coltype}")
            except Exception:
                pass

        # Geocoding tracking columns (added safely - non-breaking)
        for col, coltype in (("geocode_method", "TEXT"), ("geocode_status", "TEXT"), ("last_geocoded_at", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE derelict_sites ADD COLUMN {col} {coltype}")
            except Exception:
                pass


def replace_council(conn: sqlite3.Connection, council_code: str,
                    rows: list, source_file: str) -> int:
    if rows:
        with conn:
            conn.executemany(
                """INSERT INTO derelict_sites
                   (council, ds_ref, reg_no, address, owner, owner_address, occupier,
                    electoral_area, date_entered_register, valuation, valuation_date,
                    days_on_register, last_updated, raw_source_file, property_type, first_seen)
                   VALUES (:council, :ds_ref, :reg_no, :address, :owner, :owner_address,
                           :occupier, :electoral_area, :date_entered_register, :valuation,
                           :valuation_date, :days_on_register, :last_updated, :raw_source_file,
                           :property_type, DATE('now'))
                   ON CONFLICT(council, ds_ref) DO UPDATE SET
                       reg_no                = excluded.reg_no,
                       address               = excluded.address,
                       owner                 = excluded.owner,
                       owner_address         = excluded.owner_address,
                       occupier              = excluded.occupier,
                       electoral_area        = excluded.electoral_area,
                       date_entered_register = excluded.date_entered_register,
                       valuation             = excluded.valuation,
                       valuation_date        = excluded.valuation_date,
                       days_on_register      = excluded.days_on_register,
                       last_updated          = excluded.last_updated,
                       raw_source_file       = excluded.raw_source_file,
                       property_type         = excluded.property_type""",
                rows,
            )
    return len(rows)


def get_changes_since(date_str: str, successful_councils: list) -> dict:
    """Return new and removed properties for today's run."""
    conn = get_connection()
    today = date_str

    new_props = conn.execute(
        "SELECT council, address, property_type, valuation FROM derelict_sites WHERE first_seen = ?",
        (today,),
    ).fetchall()

    removed_props = []
    if successful_councils:
        placeholders = ",".join("?" * len(successful_councils))
        removed_props = conn.execute(
            f"""SELECT council, address, property_type, valuation
                FROM derelict_sites
                WHERE council IN ({placeholders})
                AND (last_updated < ? OR last_updated IS NULL)""",
            (*successful_councils, today),
        ).fetchall()

    return {
        "new":     [dict(r) for r in new_props],
        "removed": [dict(r) for r in removed_props],
    }


def log_scrape(council: str, status: str, rows_inserted: int = 0,
               source_file: str = None, error_msg: str = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scrape_log (council, run_at, status, rows_inserted, source_file, error_msg)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (council, datetime.now(timezone.utc).isoformat(), status, rows_inserted, source_file, error_msg),
        )
