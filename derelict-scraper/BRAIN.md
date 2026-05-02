# Property Scraper — Project Brain

## What This Is
A Python scraper that collects every Irish local authority's Derelict Sites Register into a single SQLite database, geocodes each property, and classifies it by type. The data powers **revive-ireland.com** — a map-based tool for property developers to find motivated sellers of derelict Irish properties.

The core developer value: these properties are on a legal register, owners face compulsory purchase orders (CPOs) if they don't act, making them motivated sellers. The register is public but scattered across 31 council websites with no central view. This app is the only place that consolidates it.

---

## Tech Stack
- **Language**: Python 3.14
- **DB**: SQLite (local), syncing to Supabase (planned)
- **Geocoding**: Nominatim (primary, free) + Google Maps API (fallback, Eircode-only primary)
- **Scraping**: requests + BeautifulSoup, Playwright (for JS-heavy councils)
- **Parsing**: pdfplumber, tabula-py (PDFs), openpyxl/pandas (Excel), custom HTML parser
- **Frontend**: revive-ireland.com (Next.js 15 + Supabase + Tailwind, separate repo)
- **Repo**: github.com/michaelgannon13/property-scraper (private)
- **Venv**: `/Users/michael/projects/worktrees/derelict-scraper/venv/`
- **Working dir**: `/Users/michael/projects/worktrees/derelict-scraper/derelict-scraper/`

---

## Architecture

```
config.json          → council list, column maps, scrape hints
main.py              → orchestrator (CLI, progress bar, per-council error handling)
scrapers/            → per-council scraper classes (base + council-specific)
parsers/             → pdf_parser, excel_parser, html_parser, arcgis_parser
database.py          → SQLite schema, UPSERT (preserves lat/lng on re-scrape)
utils.py             → normalise_dataframe, parse_date, classify_property_type
geocode.py           → Nominatim + Google fallback, Ireland bounds check
classify.py          → backfill property_type for existing rows
```

---

## Council Coverage

**23/31 councils enabled, ~2,042 sites**

| Status | Councils |
|--------|----------|
| ✓ Enabled | SDCC, DCC, DLR, FCC, CCC, CORK_CITY, WEXFORD, WATERFORD, WICKLOW, GCC, LEITRIM, KILKENNY, KILDARE, LAOIS, MEATH, MONAGHAN, LOUTH, OFFALY, ROSCOMMON, DONEGAL, MAYO, LIMERICK, CARLOW |
| ✗ Disabled | CLARE, LONGFORD, SLIGO, TIPPERARY, GALWAY (county), KERRY, CAVAN, WESTMEATH |

Disabled councils are documented in `DISABLED_COUNCILS.md` with reasons.

---

## Database Schema

```sql
derelict_sites (
    id, council, ds_ref, reg_no,
    address, owner, owner_address, occupier,
    electoral_area, date_entered_register,
    valuation, valuation_date, days_on_register,
    last_updated, raw_source_file,
    lat, lng,
    property_type,
    UNIQUE(council, ds_ref)
)
```

UPSERT on `(council, ds_ref)` — **lat/lng are preserved** across re-scrapes (never overwritten). `property_type` is re-derived on each scrape.

---

## Data State (as of 2026-05-02)

| Metric | Value |
|--------|-------|
| Total sites | 2,042 |
| Geocoded (lat/lng) | ~2,028 |
| Has owner name | 813 (39%) |
| Has owner address | 55 (2%) |
| Has entry date | ~1,400 |
| Has valuation | ~1,200 |

**Owner coverage by council:**
- 100%: WEXFORD, WATERFORD, GCC, LEITRIM, SDCC, WICKLOW
- 99%: MAYO (307/308) ← fixed in this project
- 50-92%: DLR, OFFALY, DONEGAL
- 0%: LIMERICK, CORK_CITY, CCC, DCC, MONAGHAN, LOUTH, ROSCOMMON, KILKENNY, LAOIS, MEATH, KILDARE, CARLOW — **source registers don't include owner data, not a parsing gap**

**Property type breakdown:**
- Other: ~1,250 (plain street addresses, unclassifiable)
- House: ~365 (keyword + Limerick source data)
- Commercial: ~125
- Institutional: ~94
- Vacant Land: ~56
- Cottage: ~39
- Industrial: ~37
- Apartment: ~11

Limerick (391 sites) provides source property types (Residential/Commercial/Site) which are mapped to our standard types. All other councils use keyword classification from address text.

---

## Key Scripts

| Script | Purpose |
|--------|---------|
| `main.py` | Full scrape run. `--councils DCC,MAYO` for specific councils |
| `geocode.py` | Geocode all rows where `lat IS NULL AND address IS NOT NULL` |
| `classify.py` | Backfill `property_type` for all rows |

### Running a full pipeline
```bash
cd /Users/michael/projects/worktrees/derelict-scraper/derelict-scraper
python main.py
python geocode.py
```

---

## Geocoding Strategy

1. **If Eircode present → Google Maps** (Nominatim returns garbage for Eircodes — it matches routing keys as road numbers giving false Dublin coords)
2. **Nominatim** with address text (Eircode stripped), Ireland restricted
3. **Google Maps fallback** with address text

All results validated against Ireland bounding box (51.3–55.5°N, 10.7–5.5°W). Google calls use `components=country:IE`.

---

## Known Issues / Limitations

- **Owner coverage ceiling ~39%** — councils like DCC, Cork City, Limerick don't publish owner names. Land Registry (Tailte Éireann) has them but costs €5-25/folio lookup.
- **"Other" property type ~61%** — plain numbered street addresses can't be classified from text alone. Acceptable.
- **1 persistently ungeocoded site**: "Commercial Building, Dublin Road (Opposite ATU)" — no town name, can't resolve.
- **Pre-existing test failures**: `test_pdf_parser.py::test_parse_falls_back_to_tabula` and `test_parse_raises_when_both_extractors_empty` fail due to pdfminer rejecting fake PDFs in test fixtures. Not introduced by this work.

---

## Next Steps (Priority Order)

1. **Supabase sync** — `sync.py` to push SQLite → Supabase. Needs: project URL, service role key. Approach: truncate-replace per council.
2. **GitHub Actions nightly cron** — scrape → geocode → sync on schedule.
3. **Property Price Register scraper** — match derelict addresses to PPR for last sale price (feeds the "Last Sale Price" filter in UI). Free public data at propertypriceregister.ie.
4. **Enable more councils** — CLARE, KERRY, GALWAY (county) are likely feasible.

---

## Filter UI Requirements (from design screenshots)

| Filter | Data field | Status |
|--------|-----------|--------|
| Sort: Newest/Oldest | `date_entered_register` | ✓ in DB |
| Sort: Highest Valuation | `valuation` | ✓ in DB |
| Type (House/Commercial/etc.) | `property_type` | ✓ in DB |
| 2+ Years on Register | `days_on_register` | ✓ in DB |
| Commercial only | `property_type` | ✓ in DB |
| Valuation min/max | `valuation` | ✓ in DB |
| Last Sale Price min/max | PPR data | ✗ not yet scraped |
| Date Added | `date_entered_register` | ✓ in DB |

---

## Environment

```
GOOGLE_MAPS_API_KEY=...   # in derelict-scraper/.env (gitignored)
```

Google Maps API key has no IP restrictions (was needed to fix IPv6 geocoding issue).
