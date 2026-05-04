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

---

## Session: 2026-05-02

### What we worked on
- Resumed after context compaction. Previous session had built geocoding (Nominatim + Google), UPSERT schema, and fixed a critical Nominatim/Eircode bug (Nominatim matches Eircode routing keys as road numbers → all non-Dublin addresses got Dublin coords).
- Re-geocoded 4 NULLed overseas pins (had been set NULL after being geocoded to New York/France/Jamaica in the pre-fix run). Two came back wrong again (Richmond Ave D.3 → Westmeath, Spanish Parade Galway → Cavan) — Nominatim still wrong for ambiguous addresses. Fixed by forcing those two through Google directly with explicit city context in the query.
- Added `property_type` column and keyword classification (`classify_property_type()` in utils.py). Priority-ordered regex rules: Apartment > Cottage > Industrial > Institutional > Commercial > House > Vacant Land > Other. Found and fixed regex bug: `\bchurches?\b` matched "churches" but not "church" — changed to `\bchurch(?:es)?\b`.
- Moved project to its own private GitHub repo: `github.com/michaelgannon13/property-scraper`.
- Audited owner data coverage: only 24% overall. Found Mayo (308 sites) had an owner column in source XLSX that wasn't mapped. Fixed column_map → 307/308 now have owner data.
- Found Limerick (391 sites) had `PROPERTY TYPE` and `Section 8(7)` date columns not mapped. Fixed → all Limerick sites now have real source property types (Residential/Commercial/Site) and 377/391 have entry dates.
- Added `_SOURCE_TYPE_MAP` in utils.py so councils that provide property types in source data take precedence over keyword classification.
- Created `BRAIN.md` (this file) and `/update-brain` slash command.

### Decisions made
- **Owner coverage ceiling is ~39%** — councils like DCC, Cork City, Limerick simply don't publish owner names in their registers. Decided not to pursue Land Registry (Tailte Éireann) lookups — costs €5-25/folio, not viable for bulk use.
- **"Other" property type at ~61% is acceptable** — plain numbered street addresses genuinely can't be classified from text. Would need a different data source to do better.
- **Repo moved to `property-scraper` (private)** — code was previously in `michaelgannon13/youtube` which was wrong. Used `git subtree split` to extract history cleanly.
- **PPR (Property Price Register) deferred** — identified as the right source for last sale price and potentially some owner names, but deferred until after Supabase sync is live.
- **`days_on_register` recalculation is fine as-is** — it recalculates correctly on every scrape run via the UPSERT. No fix needed; just needs the nightly cron to keep it fresh.
- **Geocoding strategy**: Eircodes always go to Google (never Nominatim). For everything else, Nominatim first, Google fallback. Ireland bounding box rejects results outside 51.3–55.5°N, 10.7–5.5°W. All Google calls use `components=country:IE`.

### Problems hit and solved
- **Google API key had HTTP referer restriction** — blocked server-side geocoding. Fixed by removing all IP/referer restrictions.
- **IPv6 vs IPv4 whitelist mismatch** — machine was sending requests from IPv6 but user whitelisted IPv4. Fixed by removing IP restrictions entirely.
- **Nominatim + Eircode = garbage Dublin coords** — root cause: Nominatim matches "F26" (Eircode routing key) as a road number near Dublin. Fix: never send Eircodes to Nominatim; route to Google only.
- **4 overseas pins** (New York, France, England, Jamaica) from pre-fix run. NULLed and re-geocoded with fixed strategy.
- **3 FCC CSV header rows** leaked as property data ("Address of Owner", "Reasons", "Photographs"). Deleted from DB; added `_is_header_row()` filter to `normalise_dataframe()`.
- **Mayo owner column had multi-line header with Unicode ellipsis** — after whitespace normalisation in excel_parser (`re.sub(r'\s+', ' ')`), the key becomes a long single-line string. Had to compute exact normalised form to add to config.json.

### What's next
1. Supabase sync — waiting on project URL + service role key from user
2. GitHub Actions nightly cron
3. PPR scraper for last sale price
4. Enable more councils (CLARE, KERRY, GALWAY county)

---

## Session: 2026-05-03

### What we worked on
- Short session — planning and credential gathering for Supabase sync.
- Discussed PPR (Property Price Register) as a data enrichment step.

### Decisions made
- **PPR will be part of the nightly pipeline** — confirmed it's worth doing. Plan: download full PPR CSV (~600k rows), fuzzy-match against derelict addresses by county, store `last_sale_price` + `last_sale_date` in DB. Use rapidfuzz with ~85% confidence threshold. Expected coverage: 30-50% (residential only, commercial sales not in PPR).
- **Build order stays: Supabase sync → nightly cron → PPR** — rationale: PPR data is only useful once it flows end-to-end to the frontend automatically. No point building it while data is still local-only.
- **Supabase project identified**: `https://wpgrcieidaalkkgococi.supabase.co` — service role key still needed (from supabase.com → Project Settings → API, not from Lovable).

### What's next
1. **Immediate**: User to provide Supabase service role key → build `sync.py`
2. GitHub Actions nightly cron (scrape → geocode → PPR match → sync)
3. PPR scraper
4. Enable more councils

---

## Session: 2026-05-03 (evening)

### What we worked on
- Built the full Supabase publish pipeline using the `upsert_property` Edge Function
- Added `--publish` and `--publish-only` flags to `main.py`
- Ran multiple publish cycles, diagnosed and fixed all errors
- Set up GitHub Actions nightly cron at 2am Irish time
- Fixed git remote (code was pushing to wrong repo: `youtube` instead of `property-scraper`)
- Force-pushed `feature/derelict-scraper` as new `main` in `property-scraper` (old main had stale YouTube tutorial content)

### Architecture decision: SQLite as staging layer
- **Decision**: Keep SQLite as local staging DB; publish to Supabase as a separate step after geocoding
- **Why**: Geocoding preserves lat/lng across re-scrapes — if we bypass SQLite, every nightly run would re-geocode 2,000 rows from scratch (~30 min + Google Maps API cost)
- **Pipeline**: `python main.py --geocode --publish` — scrape → SQLite → geocode → push to Supabase
- **`--publish-only`**: skips scraping, pushes existing SQLite rows directly — useful for testing and one-off fixes

### Problems hit and solved
- **Duplicate rows (3,937 instead of ~2,000)**: Supabase table had 2,008 pre-existing Lovable seed rows with `register_ref = NULL`. Edge Function's `ON CONFLICT` never matched them → everything inserted as new. Fix: deleted NULL rows, added `UNIQUE(council_area, register_ref)` constraint, updated Edge Function to use `onConflict`.
- **Constraint creation failed silently**: First `ALTER TABLE` failed because a partial index with the same name already existed. Had to drop the partial index first, then create the real unique constraint.
- **500 errors on date fields**: Some rows had `date_entered_register` values like `"2015"`, `"Unknown"`, or PDF-parsing garbage. Supabase `date` column rejected them. Fix: `_safe_date()` in `database.py` validates and only sends `YYYY-MM-DD` format strings.
- **SDCC datetime format**: SDCC XLSX stores dates as `"2014-07-29 00:00:00"` (with time component). `_safe_date()` rejected these, sending all SDCC dates as null. Fix: `str(value).strip()[:10]` strips the time part before validating.
- **KILDARE null address rows**: Kildare PDF parser produced rows where `ds_ref` is a date (`07/09/2023`) and address is null — bad PDF parse artefacts. Supabase NOT NULL on `address` rejected them. Fix: skip rows missing `address` or `ds_ref` in `upsert_property()`.
- **KILKENNY null ds_ref rows**: Same issue — rows with no `ds_ref` rejected by Edge Function (requires `council_reference`). Covered by same skip guard.
- **Wrong git remote**: All commits had been pushed to `michaelgannon13/youtube` instead of `michaelgannon13/property-scraper`. Fixed by updating remote URL; deleted stale branch from youtube repo.
- **GitHub Actions billing lock**: Repo was private → free minutes exhausted or billing not set up. Fix: made repo public (free unlimited minutes for public repos).

### Final publish result
- **1,961 properties** in Supabase `properties_large`, clean and deduplicated
- **81 intentional skips** (no address or no ds_ref — bad PDF rows, not fixable without better source data)
- Upsert confirmed working: reruns show `0 new | N updated`

### Decisions NOT made / deferred
- **`sync.py` separate script**: Originally planned; replaced by Edge Function approach — no separate sync needed
- **Remove SQLite entirely**: Not done — geocoding pipeline depends on it as a staging store
- **Land Registry owner lookup**: Still deferred — €5-25/folio, not viable at scale
- **More councils (CLARE, KERRY, GALWAY county)**: Deferred — volume gain only, no new data types

### GitHub Actions nightly cron
- Workflow: `.github/workflows/nightly-scrape.yml`
- Schedule: `0 1 * * *` (1am UTC = 2am Irish summer time)
- Steps: checkout → install deps → `python main.py --geocode --publish` → commit updated SQLite DB back to repo
- SQLite committed back to repo so lat/lng persists across runs without re-geocoding
- Requires 4 GitHub Secrets: `GOOGLE_MAPS_API_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_UPSERT_URL`, `INGEST_API_KEY`
- **Not yet tested in CI** — GitHub billing lock prevented first manual trigger. Pending billing fix.

### What's next
1. **Immediate**: Resolve GitHub billing lock → trigger manual workflow run to verify CI pipeline
2. **PPR scraper**: Download PPR-ALL.csv (~600k rows), fuzzy-match by county against derelict addresses, store `last_sale_price` + `last_sale_date` — fills "Last PPR sale" in UI and enables deal snapshot calculations (GDV, all-in cost, yield, equity)
3. **Deal snapshot**: Once PPR data is in, calculate Est. GDV (PPR median by county/type), refurb cost (Buildcost.ie rate × sqm estimate), gross yield (RTB average rent), equity created
4. **Enable more councils**: CLARE, KERRY, GALWAY county
5. **RTB rents**: Quarterly CSV from RTB for yield calculations

---

## Session: 2026-05-04

### What we worked on
- Audited all enabled councils for hardcoded `direct_url` vs. auto-discovery from page
- Enabled TIPPERARY (was disabled) — found their register at new page URL as an XLSX
- Updated GCC (Galway City) to new page URL and removed hardcoded PDF link
- Fixed DONEGAL — was pointing at wrong/old page URL; correct page is `/en/services/planning/regeneration-and-development/vacancy-and-dereliction/derelict-sites`, Excel link scrapes correctly from static HTML
- Removed `direct_url` from DONEGAL, GCC, TIPPERARY — all three now auto-discover the latest file from their page on every run
- Scraped and published 82 new properties to Supabase (76 TIPPERARY + 6 GCC updates)
- Fixed geocoding not running before publish — new properties had no lat/lng so maps/streetview were broken

### Decisions made
- **All councils must auto-discover — no hardcoded file URLs** — rationale: registers get updated quarterly, hardcoded URLs silently serve stale data. Every council now visits its page and scores links to find the latest file.
- **`direct_url` is only acceptable for live endpoints** (CCC html page = always current; WATERFORD ArcGIS API = live query). Static file URLs must never be hardcoded.
- **Geocoding is now always part of publish** — `publish_to_supabase()` calls `geocode.run()` first. Prevents new properties appearing in Supabase without coordinates. Also deduplicated: `--geocode --publish` no longer geocodes twice.
- **Tipperary duplicates: skip, don't fix** — 35 of 111 TIPPERARY rows have duplicate `SiteID` values in their source register (Tipperary's own data quality issue). SQLite UNIQUE constraint drops them silently; 76 unique rows inserted. Not our problem to fix.

### Problems hit and solved
- **DONEGAL wrong page URL** — old config pointed at `/services/planning/derelictsites/` (no `/en/`, wrong path). The Excel link doesn't appear on that page. Correct page found via user, link confirmed in static HTML at right path.
- **GCC base64-encoded download URL** — Galway City's download links use `?r=/download&path=<base64>` format. Worried link scorer wouldn't match it. Confirmed it scores correctly: link text "Derelict Sites Register - 23rd April 2026" gives "register" + "derelict" + "sites" + year = score 7. Act link only scores 4. Used `url_contains: "gccfiles"` as extra safety.
- **New properties missing lat/lng** — publish ran before geocode, so TIPPERARY/GCC rows hit Supabase with NULL coordinates. Fix: geocode always runs inside `publish_to_supabase()` before the Supabase loop.

### Data state after this session
- **2,124 properties in SQLite** (was 2,042)
- **2,124 published to Supabase** (82 new, 1,960 updated, 82 errors on rows missing address/ds_ref)
- TIPPERARY: 76 properties (new)
- GCC: 114 properties (was 108, picked up 6 from newer April 23 register)
- DONEGAL: 10 (unchanged, just fixed page URL)
- New properties need geocoding — `--publish-only` needs to be re-run after geocoding completes

### What's next
1. Re-run `--publish-only` after geocoding new TIPPERARY/GCC rows to push coordinates
2. Resolve GitHub billing lock → test nightly cron
3. PPR scraper for last sale price enrichment
4. Enable more councils (CLARE, KERRY, GALWAY county)

---

## Session: 2026-05-04 (continued)

### What we worked on
- Completed geocoding + publish of new TIPPERARY/GCC rows (all 76 Tipperary properties now have lat/lng in Supabase)
- Fixed a bug where `-657 days ago` was showing for 80 McHale Road, Castlebar, Co Mayo — Mayo's register had a typo date of `2028-02-20`
- Investigated all 7 disabled councils to determine if any can be enabled
- Audited entire disabled council list — confirmed none are currently actionable

### Decisions made
- **`_safe_date()` now rejects future dates** — any date beyond today is treated as NULL. Rationale: source data typos (e.g. Mayo's 2028 date) should never show as negative days on register in the UI. One-line fix: `if s <= datetime.now(timezone.utc).strftime("%Y-%m-%d")`.
- **All 7 disabled councils remain disabled** — investigated each; none publish their register online. CLARE, LONGFORD, WESTMEATH: in-office/email only. KERRY, CAVAN: no register page exists. GALWAY (county): actively blocks bots. SLIGO: SSL error + no file. These are legal obligations the councils meet by maintaining a physical register — they're not required to publish it digitally.
- **`--publish-only` first run was killed by `| head -5` pipe** — lesson: never pipe publish command through `head`. `tail` is safe (reads all input), `head` causes SIGPIPE and kills the writer mid-run.

### Problems hit and solved
- **New Tipperary/GCC properties had NULL lat/lng in Supabase** — first `--publish-only` was piped through `head -5`, which killed the process after geocoding completed but before the Supabase push loop ran. Re-ran without pipe — all coordinates pushed correctly.
- **Mayo McHale Road showing "-657 days ago"** — date in source register was `2028-02-20` (typo, probably meant 2024 or 2022). Fixed in `_safe_date()` with a future-date guard. Re-scraped Mayo and re-published.

### Council coverage (final state)
- **24 councils enabled, 2,124 properties** in SQLite and Supabase
- **7 councils permanently disabled** — no public register available online (not a scraping problem, a council policy problem)
- No further councils can be added without the councils themselves publishing their registers

### What's next
1. Resolve GitHub billing lock → trigger manual workflow run to verify nightly cron
2. PPR scraper for last sale price enrichment
3. Deal snapshot calculations (GDV, refurb cost, yield, equity)
4. RTB rents data for yield calculations
