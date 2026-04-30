# Derelict Sites Register Scraper — Design Spec
**Date:** 2026-04-30  
**Status:** Approved

---

## Goal

One-command Python scraper that visits all 31 Irish local authority derelict sites pages, downloads the latest register file, parses it, normalises it to a common schema, and stores it in a single master SQLite database. Each run fully replaces data for each council (complete current list semantics).

---

## Architecture

### File Structure

```
derelict-scraper/
├── main.py                  # CLI entry point, orchestrator loop
├── config.json              # 31 councils, 5 verified + 26 unverified stubs
├── database.py              # SQLite schema + replace_council() helper
├── utils.py                 # logging setup, file download, date helpers
├── scrapers/
│   ├── __init__.py
│   └── base.py              # GenericScraper: find link → download → dispatch parser
├── parsers/
│   ├── __init__.py
│   ├── excel_parser.py      # openpyxl/pandas → normalised DataFrame
│   └── pdf_parser.py        # pdfplumber primary, tabula-py fallback
├── logs/                    # rotating log files, one per run
└── data/                    # raw downloaded files (council_code + timestamp)
    └── exports/             # output CSVs/Excel files
```

### Data Flow Per Council

```
config.json entry
  → GenericScraper.find_link()   (heuristic + optional hints)
  → download_file()              (save to data/, return local path)
  → dispatch_parser()            (excel/csv/pdf → raw DataFrame)
  → normalise()                  (map columns → standard schema)
  → db.replace_council()         (DELETE + INSERT in one transaction)
```

---

## Data Schema

### Table: `derelict_sites`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `council` | TEXT | council_code from config |
| `ds_ref` | TEXT | derelict site reference |
| `reg_no` | TEXT | register number |
| `address` | TEXT | site address |
| `owner` | TEXT | |
| `owner_address` | TEXT | |
| `occupier` | TEXT | |
| `electoral_area` | TEXT | |
| `date_entered_register` | TEXT | ISO 8601 |
| `valuation` | REAL | numeric, strip €/commas |
| `valuation_date` | TEXT | ISO 8601 |
| `days_on_register` | INTEGER | calculated at insert time from date_entered_register |
| `last_updated` | TEXT | ISO 8601, from file metadata or scrape date |
| `raw_source_file` | TEXT | filename in data/ |

**Unique constraint:** `(council, ds_ref)` — no duplicates within a council's data.

**Replacement strategy:** `DELETE FROM derelict_sites WHERE council = ?` then batch INSERT, all in one transaction. If HTTP fails, skip DELETE (preserve last good data).

### Table: `scrape_log`

| Column | Type |
|---|---|
| `id` | INTEGER PK |
| `council` | TEXT |
| `run_at` | TEXT (ISO 8601) |
| `status` | TEXT (ok / error / partial) |
| `rows_inserted` | INTEGER |
| `source_file` | TEXT |
| `error_msg` | TEXT |

---

## Config Schema

Each entry in `config.json`:

```json
{
  "name": "South Dublin County Council",
  "council_code": "SDCC",
  "page_url": "https://www.sdcc.ie/en/services/...",
  "file_type": "excel",
  "verified": true,
  "enabled": true,
  "hints": {
    "selector": null,
    "url_contains": ".xlsx",
    "direct_url": null
  },
  "column_map": {
    "Site Reference": "ds_ref",
    "Address": "address"
  }
}
```

- `verified: false` councils are attempted and gracefully skipped on failure
- `enabled: false` councils are always skipped (for manual disabling)
- `hints.direct_url` bypasses page scraping entirely

---

## Link-Finding Heuristic

`GenericScraper.find_link()` runs these steps in order, stopping at the first hit:

1. **`hints.direct_url`** — return static URL immediately, skip page fetch entirely
2. **`hints.selector`** — fetch page, apply CSS selector, return that href
3. **`hints.url_contains`** — filter all `<a>` tags by href substring
4. **Keyword + extension scoring** — score all page links:
   - Contains `register`, `derelict`, `sites`: +2 each
   - Extension `.xlsx`, `.xls`, `.csv`, `.pdf`: +3
   - Year pattern `20\d\d` in text or href: +1
   - Return highest scorer; ties broken by last occurrence (newest)

---

## Parsers

### Excel / CSV (`excel_parser.py`)
- Use `pandas.read_excel()` / `pandas.read_csv()`
- Skip rows until a row containing at least 3 of the target column names is found (header detection)
- Apply `column_map` from config to rename columns
- Drop unmapped columns
- Return normalised DataFrame

### PDF (`pdf_parser.py`)
- Primary: `pdfplumber` — extract tables from all pages, concatenate
- Fallback: `tabula-py` if pdfplumber finds no tables
- Same header detection and column_map logic as Excel parser

---

## CLI Interface

```bash
python main.py                        # run all enabled councils
python main.py --councils DCC,SDCC    # specific councils only
python main.py --export csv           # run + export master CSV
python main.py --export excel         # run + export master Excel
python main.py --dry-run              # download + parse only, no DB writes
```

---

## Error Handling

- Each council wrapped in `try/except` — one failure never stops others
- HTTP failure (4xx, 5xx, timeout, SSL): log error, skip DELETE, preserve last good DB data
- No register link found: log error, skip council
- Parse failure: log error, skip council
- Partial parse (some rows malformed): insert good rows, log warning count, status = `partial`
- All errors written to `scrape_log` table and `logs/YYYY-MM-DD_HH-MM.log`

---

## Progress & Output

```
[1/31] SDCC        ✓  312 sites   (2.1s)
[2/31] DCC         ✓  489 sites   (3.4s)
[3/31] DLR         ✗  Error: no register link found
...
─────────────────────────────────────────
Updated 29/31 councils │ 2,847 sites total │ 2 errors
Errors: DLR, MAYO — see logs/2026-04-30.log
```

Export path: `data/exports/derelict_sites_national_YYYY-MM-DD.csv` (or `.xlsx`)

---

## Dependencies

```
requests
beautifulsoup4
pandas
openpyxl
pdfplumber
tabula-py
tqdm          # progress bar
```

Install: `pip install requests beautifulsoup4 pandas openpyxl pdfplumber tabula-py tqdm`

---

## Verified Councils (5)

| Code | Name | URL | File Type |
|---|---|---|---|
| SDCC | South Dublin County Council | https://www.sdcc.ie/en/services/planning-building-control/derelict-sites/ | excel |
| DCC | Dublin City Council | https://www.dublincity.ie/planning-and-land-use/active-land-management/derelict-sites-register | excel |
| DLR | Dún Laoghaire-Rathdown | https://www.dlrcoco.ie/property-management/derelict-sites | excel |
| FCC | Fingal County Council | https://www.fingal.ie/TownRegenerationOffice/DerelictSites | excel |
| CCC | Cork County Council | https://www.corkcoco.ie/en/resident/municipal-districts/derelict-sites-dangerous-structures/derelict-sites-register-list | excel |

Remaining 26 councils included as unverified stubs in `config.json`.

---

## Out of Scope

- Authentication / login-gated councils (none known, but graceful failure handles it)
- Incremental/diff updates (full replace per run is intentional)
- Scheduling (noted as future work via `schedule` library)
- Web UI or API layer
