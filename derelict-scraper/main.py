#!/usr/bin/env python3
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
from parsers import excel_parser, pdf_parser, html_parser


def load_config(path: Path = Path("config.json")) -> list:
    with open(path) as f:
        return json.load(f)


def dispatch_parser(filepath: Path, file_type: str, column_map: dict):
    # Actual file extension takes precedence over config file_type
    suffix = filepath.suffix.lower()
    if suffix == ".pdf" or file_type == "pdf":
        return pdf_parser.parse(filepath, column_map)
    if suffix in (".html", ".htm") or file_type == "html":
        return html_parser.parse(filepath, column_map)
    if suffix in (".xlsx", ".xls", ".csv") or file_type in ("excel", "csv"):
        return excel_parser.parse(filepath, column_map)
    raise ValueError(f"Cannot determine parser for {filepath.name} (file_type={file_type})")


def process_council(cfg: dict, run_id_str: str, session: requests.Session,
                    dry_run: bool, log) -> dict:
    code = cfg["council_code"]
    result = {"code": code, "status": "error", "rows": 0, "error": ""}
    _orig_verify = session.verify
    session.verify = cfg.get("ssl_verify", True)
    try:
        if cfg["file_type"] == "arcgis":
            from parsers import arcgis_parser
            arcgis_url = (cfg.get("hints") or {}).get("direct_url")
            if not arcgis_url:
                raise RuntimeError("arcgis file_type requires hints.direct_url")
            df = arcgis_parser.parse(arcgis_url, cfg.get("column_map") or {}, session)
            rows = utils.normalise_dataframe(df, code, arcgis_url)
            source_name = arcgis_url
        else:
            scraper = GenericScraper(cfg, session)
            link = scraper.find_link()
            if not link:
                raise RuntimeError("No register link found on page")
            filepath = utils.download_file(link, code, run_id_str, session,
                                           force_suffix=".html" if cfg["file_type"] == "html" else None)
            df = dispatch_parser(filepath, cfg["file_type"], cfg.get("column_map") or {})
            rows = utils.normalise_dataframe(df, code, filepath.name)
            source_name = filepath.name

        if not dry_run:
            conn = database.get_connection()
            database.replace_council(conn, code, rows, source_name)
            database.log_scrape(code, "ok", rows_inserted=len(rows),
                                source_file=source_name)

        result["status"] = "ok"
        result["rows"] = len(rows)
        log.info("[%s] OK — %d rows from %s", code, len(rows), source_name)

    except Exception as exc:
        result["error"] = str(exc)
        log.error("[%s] FAILED — %s", code, exc)
        if not dry_run:
            try:
                database.log_scrape(code, "error", error_msg=str(exc))
            except Exception:
                pass
    finally:
        session.verify = _orig_verify

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


def publish_to_supabase(log) -> None:
    import geocode
    geocode.run()
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM derelict_sites").fetchall()
    total = len(rows)
    new_count = updated_count = error_count = 0
    print(f"\nPublishing {total:,} properties to Supabase...\n")
    for row in tqdm(rows, desc="Publishing", unit="property"):
        prop = dict(row)
        try:
            resp = database.upsert_property(prop)
            if resp.get("was_new"):
                new_count += 1
            else:
                updated_count += 1
        except Exception as exc:
            error_count += 1
            log.warning("publish failed for %s/%s — %s",
                        prop.get("council"), prop.get("ds_ref") or prop.get("address"), exc)
    print(f"Published: {new_count} new │ {updated_count} updated │ {error_count} errors")


def main():
    parser = argparse.ArgumentParser(description="Irish Derelict Sites Scraper")
    parser.add_argument("--councils", help="Comma-separated council codes (e.g. DCC,SDCC)")
    parser.add_argument("--export", choices=["csv", "excel"], help="Export format after run")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--geocode", action="store_true", help="Geocode new addresses after scraping")
    parser.add_argument("--publish", action="store_true", help="Push all rows to Supabase via Edge Function after scraping/geocoding")
    parser.add_argument("--publish-only", action="store_true", help="Skip scraping — just push existing SQLite rows to Supabase")
    parser.add_argument("--floor-area", action="store_true", help="Enrich properties with estimated floor area from Microsoft Building Footprints")
    args = parser.parse_args()

    rid = utils.run_id()
    log = utils.setup_logging(rid)

    if args.publish_only:
        database.init_db()
        publish_to_supabase(log)
        sys.exit(0)

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

    if args.geocode and not args.publish and not args.dry_run:
        import geocode
        geocode.run()

    if args.floor_area and not args.dry_run:
        import floor_area
        floor_area.run()

    if args.publish and not args.dry_run:
        publish_to_supabase(log)

    if args.export:
        dest = export_data(args.export, rid)
        print(f"Exported → {dest}")

    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
