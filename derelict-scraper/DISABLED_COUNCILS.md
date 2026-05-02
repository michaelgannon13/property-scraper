# Disabled Councils — Investigation Notes

Investigated 2026-05-01. Each entry explains why the council remains disabled and what action is needed to enable it.

---

## CAVAN — Cavan County Council

**Page URL:** `https://www.cavancoco.ie/services/planning-building/derelict-sites/`

**Status:** Page loads but no downloadable register exists.

**Findings:** The register is available for public inspection by appointment only at the Planning Department, Johnston Centre, Farnham Street, Cavan Town. As of January 2025 there were 36 properties on the register. No levy was imposed in 2024. No PDF, Excel, or API endpoint was found on the website or ArcGIS. The council uses an ArcGIS Survey123 form for public reporting but does not publish the register digitally.

**To enable:** Council must publish the register as a downloadable file (or provide an ArcGIS feature service). Contact: Planning Department.

---

## CLARE — Clare County Council

**Page URL (fixed):** `https://www.clarecoco.ie/planning-and-building/vacant-sites-and-derelict-sites/derelict-sites`

**Previous URL (wrong domain, 404):** `https://www.clare.ie/planning/derelict-sites/`

**Status:** URL corrected; no downloadable register found.

**Findings:** The council's derelict sites page at `clarecoco.ie` (not `clare.ie`) confirms the register is "available for public viewing" during office hours at the Economic Development Department, Ennis. Only a complaint form (DOCX) and the Derelict Sites Act PDF are linked — no register download. 52 files opened in early 2026.

**To enable:** Council must publish the register as a downloadable file. Contact: `derelictsites@clarecoco.ie`.

---

## GALWAY — Galway County Council

**Page URL:** `https://www.galway.ie/en/environment/derelict-sites/`

**Status:** Page accessible (with browser User-Agent) but returns 403 to plain requests; no downloadable register linked.

**Findings:** The page describes the derelict sites process and links only to a complaint form PDF. There is no register download or ArcGIS feature service. The page explicitly states sites failing remediation notices "may be entered on the Derelict Sites Register" but does not link the register. The Galway County ArcGIS portal has no derelict sites feature service. (Note: Galway *City* Council is a separate enabled entry using a direct PDF URL.)

**To enable:** Council must publish the register. Additionally, add `"ssl_verify": false` or browser-spoof headers if the scraper's 403 issue is addressed. Contact: `environment@galwaycoco.ie`.

---

## KERRY — Kerry County Council

**Page URL:** `https://www.kerrycoco.ie/planning/`

**Status:** No dedicated derelict sites page found; no downloadable register.

**Findings:** The kerrycoco.ie website has a vacant sites page but no dedicated derelict sites register page. There is no `/derelict-sites/` path. The PSB Data Catalogue lists Kerry's derelict sites register but marks it as "No open data, No data sharing". Kerry actively pursues CPOs on derelict sites (6 CPO notices published December 2024) but does not publish the register publicly. No ArcGIS feature service found.

**To enable:** Council must publish the register digitally. There is no correct page URL to point to currently. Contact: Planning Department, `(066) 718 3582`.

---

## LONGFORD — Longford County Council

**Page URL (fixed):** `https://www.longfordcoco.ie/services/housing/vacant-homes-office/derelict-sites/`

**Previous URL (404):** `https://www.longfordcoco.ie/planning/derelict-sites/`

**Status:** URL corrected; register available only on request, not publicly downloadable.

**Findings:** The derelict sites function moved to the Vacant Homes Office under Housing (not Planning). The page explicitly states: *"If you wish to consult our latest Derelict Site register, please contact vacanthomesofficer@longfordcoco.ie"* — i.e., it is email-on-request only, not publicly posted.

**To enable:** Council must post the register publicly. Contact: `vacanthomesofficer@longfordcoco.ie`.

---

## SLIGO — Sligo County Council

**Page URL (fixed):** `https://www.sligococo.ie/planning/Enforcement/DerelictSites/`

**Previous URL (wrong path):** `https://www.sligococo.ie/services/planning/derelict-sites/`

**Status:** URL corrected; site has an SSL handshake failure that blocks all scraping.

**Findings:** The correct path is under `/planning/Enforcement/DerelictSites/`. However, `sligococo.ie` fails with `SSL: UNEXPECTED_EOF_WHILE_READING` on both Python requests and curl — a server-side TLS misconfiguration. Even if fixed, Sligo was cited in a March 2025 Irish Times report as one of 10 councils that issued no derelict site levy, suggesting a minimal or empty register. No ArcGIS service or downloadable PDF was found.

**To enable:** Two blockers — (1) sligococo.ie TLS must be fixed (server-side issue), (2) the council must publish the register as a downloadable file.

---

## TIPPERARY — Tipperary County Council

**Page URL (fixed):** `https://www.tipperarycoco.ie/planning-and-building/derelict-sites-register`

**Previous URL (wrong path, 403):** `https://www.tipperarycoco.ie/planning/derelict-sites-register/`

**Known PDF (direct_url set):** `https://www.tipperarycoco.ie/sites/default/files/2024-01/Derelict%20sites%20Register%2031st%20Dec%202023.pdf`

**Status:** URL corrected and direct_url pointed at the known PDF; PDF is image-based (scanned) and cannot be parsed by the current scraper.

**Findings:** A PDF register exists for 31st December 2023 (302KB, 2 pages). Confirmed downloadable. However, pdfplumber reports 0 text characters and 3 embedded images — it is a scanned document with no text layer. tabula-java (the other extractor) requires a JRE, which is not installed. No newer version of the PDF was found. The page listing has no PDF link embedded.

**To enable:** Either (a) add OCR support (`pytesseract` + `pdf2image` + `poppler`) to `parsers/pdf_parser.py`, or (b) wait for Tipperary to publish a text-based PDF. The `direct_url` is already set so the scraper will attempt the file once parsing is unblocked.

**Column map to add once parseable:**
```json
{
  "Ref. No.": "ds_ref",
  "Property": "address",
  "Owner": "owner",
  "Date Entered": "date_entered_register",
  "Market Value": "valuation"
}
```
(Exact headers to be confirmed via OCR or manual inspection.)

---

## WESTMEATH — Westmeath County Council

**Page URL:** `https://www.westmeathcoco.ie/en/ourservices/planning/derelict-sites/`

**Status:** Page loads but no downloadable register found.

**Findings:** The council's derelict sites page states the register is available to view at council offices. The PSB Data Catalogue lists Westmeath's register but marks it as "No open data, No data sharing". The Westmeath Open Data ArcGIS hub contains no derelict sites dataset. Westmeath was flagged in media reports for not collecting derelict site levies.

**To enable:** Council must publish the register digitally. Contact: Mullingar Municipal District, `044 933 2021`.
