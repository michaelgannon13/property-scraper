import sqlite3
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import database


def test_init_db_creates_tables(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "derelict_sites" in tables
    assert "scrape_log" in tables


def test_replace_council_inserts_rows(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    rows = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "1 Main St",
         "owner": "John", "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": "2022-01-01", "valuation": 50000.0, "valuation_date": None,
         "days_on_register": 365, "last_updated": "2023-01-01", "raw_source_file": "test.xlsx",
         "property_type": "Other"},
    ]
    conn = database.get_connection()
    count = database.replace_council(conn, "TEST", rows, "test.xlsx")
    assert count == 1
    result = conn.execute("SELECT address FROM derelict_sites WHERE council='TEST'").fetchone()
    assert result[0] == "1 Main St"


def test_replace_council_upserts_existing_row(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    row_v1 = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "Old Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v1.xlsx",
         "property_type": "Other"},
    ]
    row_v2 = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "Updated Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v2.xlsx",
         "property_type": "House"},
    ]
    conn = database.get_connection()
    database.replace_council(conn, "TEST", row_v1, "v1.xlsx")
    database.replace_council(conn, "TEST", row_v2, "v2.xlsx")
    all_rows = conn.execute("SELECT ds_ref, address FROM derelict_sites WHERE council='TEST'").fetchall()
    assert len(all_rows) == 1
    assert all_rows[0][1] == "Updated Address"


def test_replace_council_preserves_lat_lng(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    rows = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "Old Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v1.xlsx",
         "property_type": "Other"},
    ]
    conn = database.get_connection()
    database.replace_council(conn, "TEST", rows, "v1.xlsx")
    # Manually set geocoordinates as geocode.py would
    conn.execute("UPDATE derelict_sites SET lat=53.3, lng=-6.2 WHERE council='TEST' AND ds_ref='DS001'")
    conn.commit()
    # Run replace_council again with updated address
    rows_v2 = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "Updated Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v2.xlsx",
         "property_type": "House"},
    ]
    database.replace_council(conn, "TEST", rows_v2, "v2.xlsx")
    result = conn.execute("SELECT lat, lng FROM derelict_sites WHERE council='TEST' AND ds_ref='DS001'").fetchone()
    assert result[0] == 53.3
    assert result[1] == -6.2


def test_init_db_has_lat_lng_columns(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    conn = database.get_connection()
    col_names = {row[1] for row in conn.execute("PRAGMA table_info(derelict_sites)").fetchall()}
    assert "lat" in col_names
    assert "lng" in col_names
    assert "property_type" in col_names


def test_replace_council_stores_property_type(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    rows = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": None, "address": "Old Distillery, Cork",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v1.xlsx",
         "property_type": "Industrial"},
    ]
    conn = database.get_connection()
    database.replace_council(conn, "TEST", rows, "v1.xlsx")
    result = conn.execute("SELECT property_type FROM derelict_sites WHERE ds_ref='DS001'").fetchone()
    assert result[0] == "Industrial"


def test_log_scrape_inserts_record(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    database.log_scrape("TEST", "ok", rows_inserted=5, source_file="test.xlsx")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT status, rows_inserted FROM scrape_log WHERE council='TEST'").fetchone()
    assert row[0] == "ok"
    assert row[1] == 5
