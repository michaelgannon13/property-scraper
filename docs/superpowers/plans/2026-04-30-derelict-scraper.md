# Derelict Sites Register Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-command Python scraper that downloads, parses, normalises, and stores derelict sites registers from all 31 Irish local authorities into a single SQLite database.

**Architecture:** A single `GenericScraper` class driven entirely by `config.json` uses a four-step heuristic to find the register file on each council's page, delegates to typed parsers (Excel/PDF), normalises to a common schema, and atomically replaces each council's data in SQLite. All per-council quirks live in config `hints`, not Python.

**Tech Stack:** Python 3.11+, requests, beautifulsoup4, pandas, openpyxl, pdfplumber, tabula-py, tqdm, pytest, sqlite3 (built-in)

---

## File Map

| File | Responsibility |
|---|---|
| `derelict-scraper/main.py` | CLI entry, council loop, progress bar, summary |
| `derelict-scraper/config.json` | 31 council entries (5 verified, 26 stubs) |
| `derelict-scraper/database.py` | SQLite schema, `replace_council()`, `log_scrape()` |
| `derelict-scraper/utils.py` | logging setup, file download, `parse_date()`, `parse_valuation()`, `days_since()`, `run_id()` |
| `derelict-scraper/scrapers/__init__.py` | empty |
| `derelict-scraper/scrapers/base.py` | `GenericScraper.find_link()` with 4-step heuristic |
| `derelict-scraper/parsers/__init__.py` | empty |
| `derelict-scraper/parsers/excel_parser.py` | Excel/CSV → normalised DataFrame |
| `derelict-scraper/parsers/pdf_parser.py` | PDF → normalised DataFrame (pdfplumber + tabula fallback) |
| `derelict-scraper/tests/test_database.py` | DB init, replace, log |
| `derelict-scraper/tests/test_utils.py` | date/valuation parsing, days_since |
| `derelict-scraper/tests/test_excel_parser.py` | header detection, column mapping |
| `derelict-scraper/tests/test_scraper.py` | find_link heuristic with mocked HTTP |
| `derelict-scraper/tests/conftest.py` | shared fixtures |

---

## Task 1: Project Scaffold

**Files:**
- Create: `derelict-scraper/` (directory tree)
- Create: `derelict-scraper/requirements.txt`
- Create: `derelict-scraper/scrapers/__init__.py`
- Create: `derelict-scraper/parsers/__init__.py`
- Create: `derelict-scraper/tests/__init__.py`
- Create: `derelict-scraper/tests/conftest.py`

- [ ] **Step 1: Create the directory tree**

```bash
mkdir -p derelict-scraper/{scrapers,parsers,tests,logs,data/exports}
touch derelict-scraper/scrapers/__init__.py
touch derelict-scraper/parsers/__init__.py
touch derelict-scraper/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
# derelict-scraper/requirements.txt
requests==2.32.3
beautifulsoup4==4.12.3
pandas==2.2.2
openpyxl==3.1.3
pdfplumber==0.11.2
tabula-py==2.9.3
tqdm==4.66.4
pytest==8.2.2
pytest-mock==3.14.0
```

- [ ] **Step 3: Write tests/conftest.py**

```python
# derelict-scraper/tests/conftest.py
import pytest
import sqlite3
import tempfile
from pathlib import Path

@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a fresh temp SQLite DB."""
    return tmp_path / "test.db"

@pytest.fixture
def sample_column_map():
    return {
        "Site Ref": "ds_ref",
        "Reg No": "reg_no",
        "Address": "address",
        "Owner": "owner",
        "Owner Address": "owner_address",
        "Occupier": "occupier",
        "Electoral Area": "electoral_area",
        "Date Entered": "date_entered_register",
        "Valuation": "valuation",
        "Valuation Date": "valuation_date",
    }
```

- [ ] **Step 4: Install dependencies**

```bash
cd derelict-scraper
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/
git commit -m "chore: scaffold derelict-scraper project structure"
```

---

## Task 2: Config.json — All 31 Councils

**Files:**
- Create: `derelict-scraper/config.json`

- [ ] **Step 1: Write config.json**

```json
[
  {
    "name": "South Dublin County Council",
    "council_code": "SDCC",
    "page_url": "https://www.sdcc.ie/en/services/planning-building-control/derelict-sites/",
    "file_type": "excel",
    "verified": true,
    "enabled": true,
    "hints": { "selector": null, "url_contains": ".xlsx", "direct_url": null },
    "column_map": {
      "Site Reference": "ds_ref",
      "Register No": "reg_no",
      "Address": "address",
      "Owner": "owner",
      "Owner Address": "owner_address",
      "Occupier": "occupier",
      "Electoral Area": "electoral_area",
      "Date Entered Register": "date_entered_register",
      "Valuation": "valuation",
      "Valuation Date": "valuation_date"
    }
  },
  {
    "name": "Dublin City Council",
    "council_code": "DCC",
    "page_url": "https://www.dublincity.ie/planning-and-land-use/active-land-management/derelict-sites-register",
    "file_type": "excel",
    "verified": true,
    "enabled": true,
    "hints": { "selector": null, "url_contains": ".xlsx", "direct_url": null },
    "column_map": {
      "Site Reference": "ds_ref",
      "Register No": "reg_no",
      "Address": "address",
      "Owner": "owner",
      "Owner Address": "owner_address",
      "Occupier": "occupier",
      "Electoral Area": "electoral_area",
      "Date Entered Register": "date_entered_register",
      "Valuation": "valuation",
      "Valuation Date": "valuation_date"
    }
  },
  {
    "name": "Dún Laoghaire-Rathdown County Council",
    "council_code": "DLR",
    "page_url": "https://www.dlrcoco.ie/property-management/derelict-sites",
    "file_type": "excel",
    "verified": true,
    "enabled": true,
    "hints": { "selector": null, "url_contains": ".xlsx", "direct_url": null },
    "column_map": {
      "Site Reference": "ds_ref",
      "Register No": "reg_no",
      "Address": "address",
      "Owner": "owner",
      "Owner Address": "owner_address",
      "Occupier": "occupier",
      "Electoral Area": "electoral_area",
      "Date Entered Register": "date_entered_register",
      "Valuation": "valuation",
      "Valuation Date": "valuation_date"
    }
  },
  {
    "name": "Fingal County Council",
    "council_code": "FCC",
    "page_url": "https://www.fingal.ie/TownRegenerationOffice/DerelictSites",
    "file_type": "excel",
    "verified": true,
    "enabled": true,
    "hints": { "selector": null, "url_contains": ".xlsx", "direct_url": null },
    "column_map": {
      "Site Reference": "ds_ref",
      "Register No": "reg_no",
      "Address": "address",
      "Owner": "owner",
      "Owner Address": "owner_address",
      "Occupier": "occupier",
      "Electoral Area": "electoral_area",
      "Date Entered Register": "date_entered_register",
      "Valuation": "valuation",
      "Valuation Date": "valuation_date"
    }
  },
  {
    "name": "Cork County Council",
    "council_code": "CCC",
    "page_url": "https://www.corkcoco.ie/en/resident/municipal-districts/derelict-sites-dangerous-structures/derelict-sites-register-list",
    "file_type": "excel",
    "verified": true,
    "enabled": true,
    "hints": { "selector": null, "url_contains": ".xlsx", "direct_url": null },
    "column_map": {
      "Site Reference": "ds_ref",
      "Register No": "reg_no",
      "Address": "address",
      "Owner": "owner",
      "Owner Address": "owner_address",
      "Occupier": "occupier",
      "Electoral Area": "electoral_area",
      "Date Entered Register": "date_entered_register",
      "Valuation": "valuation",
      "Valuation Date": "valuation_date"
    }
  },
  {
    "name": "Cork City Council",
    "council_code": "CORK_CITY",
    "page_url": "https://www.corkcity.ie/en/council-services/planning-development/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Carlow County Council",
    "council_code": "CARLOW",
    "page_url": "https://www.carlowcoco.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Cavan County Council",
    "council_code": "CAVAN",
    "page_url": "https://www.cavancoco.ie/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Clare County Council",
    "council_code": "CLARE",
    "page_url": "https://www.clare.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Donegal County Council",
    "council_code": "DONEGAL",
    "page_url": "https://www.donegalcoco.ie/services/planning/derelictsites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Galway City Council",
    "council_code": "GCC",
    "page_url": "https://www.galwaycity.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Galway County Council",
    "council_code": "GALWAY",
    "page_url": "https://www.galway.ie/en/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Kerry County Council",
    "council_code": "KERRY",
    "page_url": "https://www.kerrycoco.ie/planning/derelict-sites-register/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Kildare County Council",
    "council_code": "KILDARE",
    "page_url": "https://www.kildare.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Kilkenny County Council",
    "council_code": "KILKENNY",
    "page_url": "https://www.kilkennycoco.ie/eng/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Laois County Council",
    "council_code": "LAOIS",
    "page_url": "https://www.laois.ie/departments/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Leitrim County Council",
    "council_code": "LEITRIM",
    "page_url": "https://www.leitrimcoco.ie/eng/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Limerick City and County Council",
    "council_code": "LIMERICK",
    "page_url": "https://www.limerick.ie/council/services/planning-and-development/derelict-sites",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Longford County Council",
    "council_code": "LONGFORD",
    "page_url": "https://www.longfordcoco.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Louth County Council",
    "council_code": "LOUTH",
    "page_url": "https://www.louthcoco.ie/en/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Mayo County Council",
    "council_code": "MAYO",
    "page_url": "https://www.mayo.ie/planning/derelict-sites-register/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Meath County Council",
    "council_code": "MEATH",
    "page_url": "https://www.meath.ie/council/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Monaghan County Council",
    "council_code": "MONAGHAN",
    "page_url": "https://www.monaghancoco.ie/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Offaly County Council",
    "council_code": "OFFALY",
    "page_url": "https://www.offaly.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Roscommon County Council",
    "council_code": "ROSCOMMON",
    "page_url": "https://www.roscommoncoco.ie/en/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Sligo County Council",
    "council_code": "SLIGO",
    "page_url": "https://www.sligococo.ie/services/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Tipperary County Council",
    "council_code": "TIPPERARY",
    "page_url": "https://www.tipperarycoco.ie/planning/derelict-sites-register/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Waterford City and County Council",
    "council_code": "WATERFORD",
    "page_url": "https://www.waterfordcouncil.ie/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Westmeath County Council",
    "council_code": "WESTMEATH",
    "page_url": "https://www.westmeathcoco.ie/en/ourservices/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Wexford County Council",
    "council_code": "WEXFORD",
    "page_url": "https://www.wexfordcoco.ie/departments/planning/derelict-sites/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  },
  {
    "name": "Wicklow County Council",
    "council_code": "WICKLOW",
    "page_url": "https://www.wicklow.ie/living/planning/derelict-sites-register/",
    "file_type": "excel",
    "verified": false,
    "enabled": true,
    "hints": { "selector": null, "url_contains": null, "direct_url": null },
    "column_map": {}
  }
]
```

- [ ] **Step 2: Verify JSON is valid**

```bash
cd derelict-scraper
python -c "import json; d = json.load(open('config.json')); print(f'{len(d)} councils loaded')"
```

Expected: `31 councils loaded`

- [ ] **Step 3: Commit**

```bash
git add derelict-scraper/config.json
git commit -m "feat: add config.json with 31 councils (5 verified, 26 stubs)"
```

---

## Task 3: Database Module

**Files:**
- Create: `derelict-scraper/database.py`
- Create: `derelict-scraper/tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

```python
# derelict-scraper/tests/test_database.py
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
         "days_on_register": 365, "last_updated": "2023-01-01", "raw_source_file": "test.xlsx"},
    ]
    conn = database.get_connection()
    count = database.replace_council(conn, "TEST", rows, "test.xlsx")
    assert count == 1
    result = conn.execute("SELECT address FROM derelict_sites WHERE council='TEST'").fetchone()
    assert result[0] == "1 Main St"

def test_replace_council_deletes_old_rows(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    rows_v1 = [
        {"council": "TEST", "ds_ref": "DS001", "reg_no": "R1", "address": "Old Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v1.xlsx"},
    ]
    rows_v2 = [
        {"council": "TEST", "ds_ref": "DS999", "reg_no": "R2", "address": "New Address",
         "owner": None, "owner_address": None, "occupier": None, "electoral_area": None,
         "date_entered_register": None, "valuation": None, "valuation_date": None,
         "days_on_register": None, "last_updated": None, "raw_source_file": "v2.xlsx"},
    ]
    conn = database.get_connection()
    database.replace_council(conn, "TEST", rows_v1, "v1.xlsx")
    database.replace_council(conn, "TEST", rows_v2, "v2.xlsx")
    all_rows = conn.execute("SELECT ds_ref FROM derelict_sites WHERE council='TEST'").fetchall()
    assert len(all_rows) == 1
    assert all_rows[0][0] == "DS999"

def test_log_scrape_inserts_record(tmp_db, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_db)
    database.init_db()
    database.log_scrape("TEST", "ok", rows_inserted=5, source_file="test.xlsx")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT status, rows_inserted FROM scrape_log WHERE council='TEST'").fetchone()
    assert row[0] == "ok"
    assert row[1] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd derelict-scraper
pytest tests/test_database.py -v
```

Expected: `ModuleNotFoundError: No module named 'database'` or `ImportError`

- [ ] **Step 3: Write database.py**

```python
# derelict-scraper/database.py
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("derelict_sites.db")


def get_connection() -> sqlite3.Connection:
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


def replace_council(conn: sqlite3.Connection, council_code: str,
                    rows: list, source_file: str) -> int:
    with conn:
        conn.execute("DELETE FROM derelict_sites WHERE council = ?", (council_code,))
        if rows:
            conn.executemany(
                """INSERT OR IGNORE INTO derelict_sites
                   (council, ds_ref, reg_no, address, owner, owner_address, occupier,
                    electoral_area, date_entered_register, valuation, valuation_date,
                    days_on_register, last_updated, raw_source_file)
                   VALUES (:council, :ds_ref, :reg_no, :address, :owner, :owner_address,
                           :occupier, :electoral_area, :date_entered_register, :valuation,
                           :valuation_date, :days_on_register, :last_updated, :raw_source_file)""",
                rows,
            )
    return len(rows)


def log_scrape(council: str, status: str, rows_inserted: int = 0,
               source_file: str = None, error_msg: str = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scrape_log (council, run_at, status, rows_inserted, source_file, error_msg)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (council, datetime.utcnow().isoformat(), status, rows_inserted, source_file, error_msg),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_database.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/database.py derelict-scraper/tests/test_database.py
git commit -m "feat: add database module with init, replace_council, log_scrape"
```

---

## Task 4: Utils Module

**Files:**
- Create: `derelict-scraper/utils.py`
- Create: `derelict-scraper/tests/test_utils.py`

- [ ] **Step 1: Write the failing tests**

```python
# derelict-scraper/tests/test_utils.py
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import utils


def test_parse_date_slash_dmy():
    assert utils.parse_date("25/06/2021") == "2021-06-25"


def test_parse_date_dash_dmy():
    assert utils.parse_date("25-06-2021") == "2021-06-25"


def test_parse_date_iso():
    assert utils.parse_date("2021-06-25") == "2021-06-25"


def test_parse_date_none_returns_none():
    assert utils.parse_date(None) is None


def test_parse_date_empty_returns_none():
    assert utils.parse_date("") is None


def test_parse_date_nan_returns_none():
    assert utils.parse_date("nan") is None


def test_parse_valuation_strips_euro_and_commas():
    assert utils.parse_valuation("€12,500.00") == 12500.0


def test_parse_valuation_plain_number():
    assert utils.parse_valuation("50000") == 50000.0


def test_parse_valuation_none_returns_none():
    assert utils.parse_valuation(None) is None


def test_parse_valuation_non_numeric_returns_none():
    assert utils.parse_valuation("N/A") is None


def test_days_since_known_date(monkeypatch):
    import utils
    from datetime import date
    monkeypatch.setattr(utils, "_today", lambda: date(2024, 1, 1))
    assert utils.days_since("2023-01-01") == 365


def test_days_since_none_returns_none():
    assert utils.days_since(None) is None


def test_run_id_format():
    rid = utils.run_id()
    assert len(rid) == 19
    assert rid[10] == "_"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd derelict-scraper
pytest tests/test_utils.py -v
```

Expected: `ImportError: No module named 'utils'`

- [ ] **Step 3: Write utils.py**

```python
# derelict-scraper/utils.py
import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests

LOGS_DIR = Path("logs")
DATA_DIR = Path("data")

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d/%m/%y")


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
                  session: requests.Session) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    suffix = Path(url.split("?")[0]).suffix or ".bin"
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
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_utils.py -v
```

Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/utils.py derelict-scraper/tests/test_utils.py
git commit -m "feat: add utils module with date/valuation parsing and download helper"
```

---

## Task 5: Excel Parser

**Files:**
- Create: `derelict-scraper/parsers/excel_parser.py`
- Create: `derelict-scraper/tests/test_excel_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# derelict-scraper/tests/test_excel_parser.py
import pytest
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import excel_parser


COLUMN_MAP = {
    "Site Ref": "ds_ref",
    "Address": "address",
    "Owner": "owner",
    "Electoral Area": "electoral_area",
    "Date Entered": "date_entered_register",
    "Valuation": "valuation",
}


def test_parse_excel_basic(tmp_path, sample_column_map):
    wb_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({
        "Site Ref": ["DS001", "DS002"],
        "Reg No": ["R1", "R2"],
        "Address": ["1 Main St", "2 Main St"],
        "Owner": ["Alice", "Bob"],
        "Owner Address": [None, None],
        "Occupier": [None, None],
        "Electoral Area": ["Area A", "Area B"],
        "Date Entered": ["25/06/2021", "01/01/2022"],
        "Valuation": ["€12,500", "€25,000"],
        "Valuation Date": [None, None],
    })
    df.to_excel(wb_path, index=False)
    result = excel_parser.parse(wb_path, sample_column_map)
    assert len(result) == 2
    assert "ds_ref" in result.columns
    assert "address" in result.columns
    assert result.iloc[0]["ds_ref"] == "DS001"


def test_parse_detects_header_after_junk_rows(tmp_path, sample_column_map):
    wb_path = tmp_path / "test_junk.xlsx"
    junk = pd.DataFrame([
        ["Council Derelict Sites Register 2024", None, None, None, None, None, None, None, None, None],
        ["Published by Planning Dept", None, None, None, None, None, None, None, None, None],
        ["Site Ref", "Reg No", "Address", "Owner", "Owner Address", "Occupier",
         "Electoral Area", "Date Entered", "Valuation", "Valuation Date"],
        ["DS001", "R1", "1 Main St", "Alice", None, None, "Area A", "25/06/2021", "€12,500", None],
    ])
    junk.to_excel(wb_path, index=False, header=False)
    result = excel_parser.parse(wb_path, sample_column_map)
    assert len(result) >= 1
    assert "ds_ref" in result.columns


def test_parse_csv_basic(tmp_path, sample_column_map):
    csv_path = tmp_path / "test.csv"
    df = pd.DataFrame({
        "Site Ref": ["DS001"],
        "Reg No": ["R1"],
        "Address": ["1 Main St"],
        "Owner": ["Alice"],
        "Owner Address": [None],
        "Occupier": [None],
        "Electoral Area": ["Area A"],
        "Date Entered": ["25/06/2021"],
        "Valuation": ["€12,500"],
        "Valuation Date": [None],
    })
    df.to_csv(csv_path, index=False)
    result = excel_parser.parse(csv_path, sample_column_map)
    assert len(result) == 1
    assert result.iloc[0]["address"] == "1 Main St"


def test_parse_raises_on_unrecognised_columns(tmp_path):
    wb_path = tmp_path / "bad.xlsx"
    df = pd.DataFrame({"Foo": [1], "Bar": [2]})
    df.to_excel(wb_path, index=False)
    with pytest.raises(ValueError, match="No recognised columns"):
        excel_parser.parse(wb_path, {})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd derelict-scraper
pytest tests/test_excel_parser.py -v
```

Expected: `ImportError: cannot import name 'excel_parser'`

- [ ] **Step 3: Write parsers/excel_parser.py**

```python
# derelict-scraper/parsers/excel_parser.py
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.excel")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
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

    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=column_map)

    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        raise ValueError("No recognised columns found after column_map applied")

    return df[keep].dropna(how="all").reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_excel_parser.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/parsers/excel_parser.py derelict-scraper/tests/test_excel_parser.py
git commit -m "feat: add Excel/CSV parser with header detection and column mapping"
```

---

## Task 6: PDF Parser

**Files:**
- Create: `derelict-scraper/parsers/pdf_parser.py`
- Create: `derelict-scraper/tests/test_pdf_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# derelict-scraper/tests/test_pdf_parser.py
import pytest
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import pdf_parser


COLUMN_MAP = {
    "Site Ref": "ds_ref",
    "Address": "address",
    "Owner": "owner",
}


def test_parse_uses_pdfplumber_result(tmp_path, monkeypatch):
    fake_df = pd.DataFrame({
        "Site Ref": ["DS001"],
        "Address": ["1 Main St"],
        "Owner": ["Alice"],
    })

    def mock_pdfplumber(filepath):
        return fake_df

    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", mock_pdfplumber)

    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    result = pdf_parser.parse(dummy_pdf, COLUMN_MAP)
    assert "ds_ref" in result.columns
    assert result.iloc[0]["address"] == "1 Main St"


def test_parse_falls_back_to_tabula_when_pdfplumber_empty(tmp_path, monkeypatch):
    fake_df = pd.DataFrame({
        "Site Ref": ["DS002"],
        "Address": ["2 Side St"],
        "Owner": ["Bob"],
    })

    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_with_tabula", lambda _: fake_df)

    dummy_pdf = tmp_path / "dummy2.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    result = pdf_parser.parse(dummy_pdf, COLUMN_MAP)
    assert result.iloc[0]["ds_ref"] == "DS002"


def test_parse_raises_when_both_extractors_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parser, "_extract_with_pdfplumber", lambda _: pd.DataFrame())
    monkeypatch.setattr(pdf_parser, "_extract_with_tabula", lambda _: pd.DataFrame())

    dummy_pdf = tmp_path / "dummy3.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ValueError, match="Could not extract"):
        pdf_parser.parse(dummy_pdf, COLUMN_MAP)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd derelict-scraper
pytest tests/test_pdf_parser.py -v
```

Expected: `ImportError: cannot import name 'pdf_parser'`

- [ ] **Step 3: Write parsers/pdf_parser.py**

```python
# derelict-scraper/parsers/pdf_parser.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_pdf_parser.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/parsers/pdf_parser.py derelict-scraper/tests/test_pdf_parser.py
git commit -m "feat: add PDF parser with pdfplumber primary and tabula fallback"
```

---

## Task 7: GenericScraper

**Files:**
- Create: `derelict-scraper/scrapers/base.py`
- Create: `derelict-scraper/tests/test_scraper.py`

- [ ] **Step 1: Write the failing tests**

```python
# derelict-scraper/tests/test_scraper.py
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.base import GenericScraper, _score_link


def make_scraper(hints=None, page_url="https://example.ie/derelict"):
    config = {
        "council_code": "TEST",
        "page_url": page_url,
        "hints": hints or {"selector": None, "url_contains": None, "direct_url": None},
    }
    session = MagicMock()
    return GenericScraper(config, session)


def test_score_link_excel_keyword():
    score = _score_link("/files/derelict-register.xlsx", "Download Register")
    assert score >= 5  # +3 for .xlsx, +2 for register


def test_score_link_no_match():
    assert _score_link("/contact-us", "Contact Us") == 0


def test_find_link_direct_url_skips_page_fetch():
    scraper = make_scraper(hints={"direct_url": "https://example.ie/register.xlsx",
                                  "selector": None, "url_contains": None})
    result = scraper.find_link()
    assert result == "https://example.ie/register.xlsx"
    scraper.session.get.assert_not_called()


def test_find_link_url_contains():
    html = '<html><body><a href="/files/derelict-register.xlsx">Register</a></body></html>'
    scraper = make_scraper(hints={"selector": None, "url_contains": ".xlsx", "direct_url": None})
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert result.endswith(".xlsx")


def test_find_link_heuristic_scores_correctly():
    html = """<html><body>
        <a href="/about">About Us</a>
        <a href="/files/derelict-sites-register-2024.xlsx">Derelict Sites Register 2024</a>
    </body></html>"""
    scraper = make_scraper(hints={"selector": None, "url_contains": None, "direct_url": None})
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert "derelict" in result.lower()
    assert result.endswith(".xlsx")


def test_find_link_returns_none_when_no_candidates():
    html = "<html><body><a href='/about'>About</a></body></html>"
    scraper = make_scraper()
    scraper.session.get.return_value.text = html
    scraper.session.get.return_value.raise_for_status = MagicMock()
    result = scraper.find_link()
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd derelict-scraper
pytest tests/test_scraper.py -v
```

Expected: `ImportError: cannot import name 'GenericScraper'`

- [ ] **Step 3: Write scrapers/base.py**

```python
# derelict-scraper/scrapers/base.py
import re
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("derelict.scraper")

_KEYWORDS = ["register", "derelict", "sites"]
_EXTENSIONS = [".xlsx", ".xls", ".csv", ".pdf"]
_YEAR_RE = re.compile(r"20\d{2}")


def _score_link(href: str, text: str) -> int:
    score = 0
    combined = (href + " " + text).lower()
    for kw in _KEYWORDS:
        if kw in combined:
            score += 2
    for ext in _EXTENSIONS:
        if href.lower().endswith(ext) or (ext + "?") in href.lower():
            score += 3
    if _YEAR_RE.search(combined):
        score += 1
    return score


class GenericScraper:
    def __init__(self, config: dict, session: requests.Session):
        self.config = config
        self.session = session
        self.hints = config.get("hints") or {}
        self._log = logging.getLogger(f"derelict.scraper.{config['council_code']}")

    def find_link(self) -> Optional[str]:
        if self.hints.get("direct_url"):
            return self.hints["direct_url"]

        resp = self.session.get(self.config["page_url"], timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        base = self.config["page_url"]

        if self.hints.get("selector"):
            el = soup.select_one(self.hints["selector"])
            if el and el.get("href"):
                return urljoin(base, el["href"])

        if self.hints.get("url_contains"):
            needle = self.hints["url_contains"].lower()
            for a in soup.find_all("a", href=True):
                if needle in a["href"].lower():
                    return urljoin(base, a["href"])

        candidates = []
        for a in soup.find_all("a", href=True):
            score = _score_link(a["href"], a.get_text(" ", strip=True))
            if score > 0:
                candidates.append((score, a))

        if not candidates:
            return None

        best_score = max(s for s, _ in candidates)
        best = [a for s, a in candidates if s == best_score]
        return urljoin(base, best[-1]["href"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_scraper.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/scrapers/base.py derelict-scraper/tests/test_scraper.py
git commit -m "feat: add GenericScraper with 4-step link-finding heuristic"
```

---

## Task 8: Normaliser — DataFrame → DB Rows

**Files:**
- Modify: `derelict-scraper/utils.py` (add `normalise_dataframe()`)
- Create: `derelict-scraper/tests/test_normalise.py`

- [ ] **Step 1: Write the failing test**

```python
# derelict-scraper/tests/test_normalise.py
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import utils


def test_normalise_dataframe_produces_correct_row():
    df = pd.DataFrame({
        "ds_ref": ["DS001"],
        "address": ["1 Main St"],
        "owner": ["Alice"],
        "date_entered_register": ["25/06/2020"],
        "valuation": ["€12,500"],
    })
    rows = utils.normalise_dataframe(df, "SDCC", "test.xlsx")
    assert len(rows) == 1
    row = rows[0]
    assert row["council"] == "SDCC"
    assert row["ds_ref"] == "DS001"
    assert row["date_entered_register"] == "2020-06-25"
    assert row["valuation"] == 12500.0
    assert row["days_on_register"] is not None
    assert row["days_on_register"] > 0
    assert row["raw_source_file"] == "test.xlsx"


def test_normalise_dataframe_fills_missing_fields_with_none():
    df = pd.DataFrame({"ds_ref": ["DS002"]})
    rows = utils.normalise_dataframe(df, "TEST", "x.xlsx")
    assert rows[0]["address"] is None
    assert rows[0]["owner"] is None


def test_normalise_dataframe_skips_fully_empty_rows():
    df = pd.DataFrame({
        "ds_ref": [None, "DS001"],
        "address": [None, "1 Main St"],
    })
    rows = utils.normalise_dataframe(df, "TEST", "x.xlsx")
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd derelict-scraper
pytest tests/test_normalise.py -v
```

Expected: `AttributeError: module 'utils' has no attribute 'normalise_dataframe'`

- [ ] **Step 3: Add normalise_dataframe() to utils.py**

Append this to the bottom of `derelict-scraper/utils.py`:

```python
_STANDARD_COLUMNS = [
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date",
]


def normalise_dataframe(df: "pd.DataFrame", council_code: str,
                        source_file: str) -> list:
    import pandas as pd
    rows = []
    for _, row in df.iterrows():
        entry = {"council": council_code, "raw_source_file": source_file}
        for col in _STANDARD_COLUMNS:
            raw = row.get(col) if col in row.index else None
            if pd.isna(raw) if raw is not None else True:
                raw = None
            entry[col] = raw

        if entry["ds_ref"] is None and entry["address"] is None:
            continue

        entry["date_entered_register"] = parse_date(entry["date_entered_register"])
        entry["valuation_date"] = parse_date(entry["valuation_date"])
        entry["valuation"] = parse_valuation(entry["valuation"])
        entry["days_on_register"] = days_since(entry["date_entered_register"])
        entry["last_updated"] = datetime.utcnow().date().isoformat()
        rows.append(entry)
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd derelict-scraper
pytest tests/test_normalise.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add derelict-scraper/utils.py derelict-scraper/tests/test_normalise.py
git commit -m "feat: add normalise_dataframe to produce DB-ready row dicts"
```

---

## Task 9: Main Orchestrator

**Files:**
- Create: `derelict-scraper/main.py`

- [ ] **Step 1: Write main.py**

```python
#!/usr/bin/env python3
# derelict-scraper/main.py
import argparse
import json
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

import database
import utils
from scrapers.base import GenericScraper
from parsers import excel_parser, pdf_parser


def load_config(path: Path = Path("config.json")) -> list:
    with open(path) as f:
        return json.load(f)


def dispatch_parser(filepath: Path, file_type: str, column_map: dict):
    if file_type in ("excel", "csv"):
        return excel_parser.parse(filepath, column_map)
    if file_type == "pdf":
        return pdf_parser.parse(filepath, column_map)
    raise ValueError(f"Unknown file_type: {file_type}")


def process_council(cfg: dict, run_id_str: str, session: requests.Session,
                    dry_run: bool, log) -> dict:
    code = cfg["council_code"]
    result = {"code": code, "status": "error", "rows": 0, "error": ""}

    try:
        scraper = GenericScraper(cfg, session)
        link = scraper.find_link()
        if not link:
            raise RuntimeError("No register link found on page")

        filepath = utils.download_file(link, code, run_id_str, session)
        df = dispatch_parser(filepath, cfg["file_type"], cfg.get("column_map") or {})
        rows = utils.normalise_dataframe(df, code, filepath.name)

        if not dry_run:
            conn = database.get_connection()
            database.replace_council(conn, code, rows, filepath.name)
            database.log_scrape(code, "ok", rows_inserted=len(rows),
                                source_file=filepath.name)

        result["status"] = "ok"
        result["rows"] = len(rows)
        log.info("[%s] OK — %d rows from %s", code, len(rows), filepath.name)

    except Exception as exc:
        result["error"] = str(exc)
        log.error("[%s] FAILED — %s", code, exc)
        if not dry_run:
            database.log_scrape(code, "error", error_msg=str(exc))

    return result


def export_data(fmt: str, run_id_str: str) -> Path:
    import pandas as pd
    conn = database.get_connection()
    df = pd.read_sql("SELECT * FROM derelict_sites", conn)
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    date_str = run_id_str[:10]
    if fmt == "csv":
        dest = export_dir / f"derelict_sites_national_{date_str}.csv"
        df.to_csv(dest, index=False)
    else:
        dest = export_dir / f"derelict_sites_national_{date_str}.xlsx"
        df.to_excel(dest, index=False)
    return dest


def main():
    parser = argparse.ArgumentParser(description="Irish Derelict Sites Scraper")
    parser.add_argument("--councils", help="Comma-separated council codes to run (e.g. DCC,SDCC)")
    parser.add_argument("--export", choices=["csv", "excel"], help="Export format after run")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()

    rid = utils.run_id()
    log = utils.setup_logging(rid)

    if not args.dry_run:
        database.init_db()

    councils = load_config()
    councils = [c for c in councils if c.get("enabled", True)]

    if args.councils:
        wanted = {x.strip().upper() for x in args.councils.split(",")}
        councils = [c for c in councils if c["council_code"].upper() in wanted]
        if not councils:
            print(f"No matching councils found for: {args.councils}")
            sys.exit(1)

    session = requests.Session()
    session.headers.update({"User-Agent": "DerelictSitesScraper/1.0 (research)"})

    results = []
    total = len(councils)

    print(f"\nRunning derelict sites scraper — {total} councils\n")

    for i, cfg in enumerate(tqdm(councils, desc="Councils", unit="council"), start=1):
        code = cfg["council_code"]
        t0 = time.time()
        tqdm.write(f"[{i}/{total}] {code:<12} ...", end="")
        res = process_council(cfg, rid, session, args.dry_run, log)
        elapsed = time.time() - t0
        if res["status"] == "ok":
            tqdm.write(f"\r[{i}/{total}] {code:<12} ✓  {res['rows']:>5} sites   ({elapsed:.1f}s)")
        else:
            tqdm.write(f"\r[{i}/{total}] {code:<12} ✗  Error: {res['error'][:60]}")
        results.append(res)

    ok = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] != "ok"]
    total_sites = sum(r["rows"] for r in ok)

    print("\n" + "─" * 60)
    print(f"Updated {len(ok)}/{total} councils │ {total_sites:,} sites total │ {len(errors)} errors")
    if errors:
        print(f"Errors: {', '.join(r['code'] for r in errors)}")
        print(f"See logs/{rid}.log for details")

    if args.export:
        dest = export_data(args.export, rid)
        print(f"Exported → {dest}")

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI help works**

```bash
cd derelict-scraper
python main.py --help
```

Expected output includes:
```
usage: main.py [-h] [--councils COUNCILS] [--export {csv,excel}] [--dry-run]
```

- [ ] **Step 3: Commit**

```bash
git add derelict-scraper/main.py
git commit -m "feat: add main orchestrator with CLI, progress bar, and per-council error handling"
```

---

## Task 10: Full Test Suite Run + Smoke Test

**Files:**
- No new files — verify all existing tests pass together

- [ ] **Step 1: Run the full test suite**

```bash
cd derelict-scraper
pytest tests/ -v --tb=short
```

Expected: all tests pass. If any fail, fix before proceeding.

- [ ] **Step 2: Dry-run smoke test against SDCC (one real council)**

```bash
cd derelict-scraper
python main.py --councils SDCC --dry-run
```

Expected output (approximate):
```
Running derelict sites scraper — 1 councils

[1/1] SDCC         ✓   NNN sites   (X.Xs)

────────────────────────────────────────────────────────────
Updated 1/1 councils │ NNN sites total │ 0 errors
```

If SDCC fails (network/page layout issue), check `logs/` for the error detail and update `config.json` hints accordingly (e.g. add a `url_contains` or `selector`).

- [ ] **Step 3: Full dry-run against all 5 verified councils**

```bash
cd derelict-scraper
python main.py --councils SDCC,DCC,DLR,FCC,CCC --dry-run
```

Expected: at least 3/5 succeed (layout of unverified councils may need hint tuning).

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "feat: derelict sites scraper complete — 31 councils configured, 5 verified"
```

---

## Hints Tuning Reference

When a verified council fails link detection, add hints to its `config.json` entry:

| Symptom | Fix |
|---|---|
| Wrong file picked | Add `"url_contains": ".xlsx"` |
| No link found (JS-rendered page) | Add `"direct_url"` with the static file URL |
| Multiple `.xlsx` files on page | Add `"selector": "a[href*='derelict']"` |
| PDF only (no Excel) | Change `"file_type": "pdf"` and add `"url_contains": ".pdf"` |

For unverified councils (26 stubs), the workflow is:
1. Visit the council's derelict sites page manually
2. Find the correct URL
3. Update `page_url` and `hints` in `config.json`
4. Set `"verified": true`
5. Run `python main.py --councils CODE --dry-run` to confirm

---

*Spec:* `docs/superpowers/specs/2026-04-30-derelict-scraper-design.md`
