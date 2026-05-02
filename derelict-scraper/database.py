import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/derelict_sites.db")


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
        for col, coltype in (("lat", "REAL"), ("lng", "REAL"), ("property_type", "TEXT")):
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
                    days_on_register, last_updated, raw_source_file, property_type)
                   VALUES (:council, :ds_ref, :reg_no, :address, :owner, :owner_address,
                           :occupier, :electoral_area, :date_entered_register, :valuation,
                           :valuation_date, :days_on_register, :last_updated, :raw_source_file,
                           :property_type)
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


def log_scrape(council: str, status: str, rows_inserted: int = 0,
               source_file: str = None, error_msg: str = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scrape_log (council, run_at, status, rows_inserted, source_file, error_msg)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (council, datetime.now(timezone.utc).isoformat(), status, rows_inserted, source_file, error_msg),
        )
