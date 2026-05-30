#!/usr/bin/env python3
import os
import re
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
import database

logger = logging.getLogger("derelict.geocode")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_GOOGLE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_NOMINATIM_DELAY = 1.1  # Nominatim policy: max 1 req/sec
_GOOGLE_DELAY = 0.05

# Eircode: letter + digit + (digit or W) + optional space + 4 alphanumeric
# Handles standard (D24 NN82) and D6W special case (D6W XY12)
_EIRCODE_RE = re.compile(r'\b([A-Z][0-9][0-9W])\s*([A-Z0-9]{4})\b')

# Ireland bounding box — any result outside this is rejected as garbage
_IE_LAT_MIN, _IE_LAT_MAX = 51.3, 55.5
_IE_LNG_MIN, _IE_LNG_MAX = -10.7, -5.5


def _in_ireland(lat: float, lng: float) -> bool:
    return _IE_LAT_MIN <= lat <= _IE_LAT_MAX and _IE_LNG_MIN <= lng <= _IE_LNG_MAX

_SMART_QUOTES = str.maketrans({
    '‘': '', '’': '',  # ' '
    '“': '', '”': '',  # " "
    '′': '', '″': '',  # ′ ″
})


def clean_address(address: str) -> str:
    address = address.translate(_SMART_QUOTES)
    address = re.sub(r'\n+', ', ', address)
    address = re.sub(r'[ \t]+', ' ', address)

    # Safe, conservative cleaning to improve geocoding success rate
    # Remove common noise that hurts address matching
    noise_patterns = [
        r'\bderelict\b', r'\bvacant\b', r'\bformer\b', r'\bdisused\b',
        r'\(opposite[^)]*\)', r'\(near[^)]*\)', r'\(at the rear[^)]*\)',
        r'\bderelict site\b', r'\bderelict house\b',
        r'\bsite of\b', r'\bland at\b', r'\bproperty known as\b',
        r'\bthe site of\b', r'\bat the site of\b',
        r'\bthe lands of\b', r'\bportion of\b', r'\bpart of the\b',
        r'\bcomprising\b', r'\bplot no\.?\s*\d*\b', r'\bsite no\.?\s*\d*\b',
    ]
    for pattern in noise_patterns:
        address = re.sub(pattern, '', address, flags=re.IGNORECASE)

    # Clean up messy punctuation and repeated separators
    address = re.sub(r'\s*,\s*,', ',', address)
    address = re.sub(r'\s+', ' ', address).strip(' ,').strip()

    return address


def extract_eircode(address: str) -> Optional[str]:
    match = _EIRCODE_RE.search(address.upper())
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return None


def _strip_eircode(address: str) -> str:
    return _EIRCODE_RE.sub('', address.upper()).strip().strip(',').strip()


def geocode_with_nominatim(query: str, session: requests.Session) -> Tuple[Optional[float], Optional[float]]:
    try:
        resp = session.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "ie"},
            headers={"User-Agent": "DerelictSitesScraper/1.0 (research; michael.gannon13@gmail.com)"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        logger.debug("Nominatim error for %r: %s", query, exc)
    return None, None


def geocode_with_google(address: str, session: requests.Session, api_key: str) -> Tuple[Optional[float], Optional[float]]:
    try:
        # components=country:IE forces Google to restrict results to Ireland
        # even when the address string is ambiguous (e.g. "Richmond Avenue")
        query = address if address.lower().endswith(", ireland") else f"{address}, Ireland"
        resp = session.get(
            _GOOGLE_URL,
            params={"address": query, "key": api_key, "components": "country:IE"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception as exc:
        logger.debug("Google error for %r: %s", address, exc)
    return None, None


def geocode_address(raw_address: str, session: requests.Session,
                    api_key: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (lat, lng, method_used) or (None, None, None) if failed."""
    cleaned = clean_address(raw_address)
    eircode = extract_eircode(cleaned)
    address_no_eircode = _strip_eircode(cleaned) if eircode else cleaned

    # 1. Google Maps with Eircode — Google understands Irish Eircodes; Nominatim does not
    if eircode and api_key:
        lat, lng = geocode_with_google(eircode, session, api_key)
        time.sleep(_GOOGLE_DELAY)
        if lat is not None and _in_ireland(lat, lng):
            return lat, lng, "google_eircode"

    # 2. Nominatim with address text only
    lat, lng = geocode_with_nominatim(f"{address_no_eircode}, Ireland", session)
    time.sleep(_NOMINATIM_DELAY)
    if lat is not None and _in_ireland(lat, lng):
        return lat, lng, "nominatim"

    # 3. Google Maps with address text as final fallback
    if api_key:
        lat, lng = geocode_with_google(address_no_eircode, session, api_key)
        time.sleep(_GOOGLE_DELAY)
        if lat is not None and _in_ireland(lat, lng):
            return lat, lng, "google_text"

    return None, None, None


def run(db_path=None, only_failed=False, limit: int = None, dry_run=False):
    """
    Geocode addresses.

    Args:
        db_path: Optional path to override the database location.
        only_failed: If True, only re-attempt addresses that previously failed geocoding.
        limit: Optional maximum number of addresses to process (useful with --failed-only).
        dry_run: If True, only show what would be geocoded without actually calling geocoding services.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set — will use Nominatim only (no Google fallback)")

    if db_path:
        database.DB_PATH = Path(db_path)

    database.init_db()
    conn = database.get_connection()

    if only_failed:
        # Safest targeted re-geocoding: only rows that previously failed
        query = """
            SELECT id, address, council 
            FROM derelict_sites 
            WHERE geocode_status = 'failed' 
              AND address IS NOT NULL
        """
        msg = "Re-geocoding only previously failed addresses"
    else:
        query = """
            SELECT id, address, council 
            FROM derelict_sites 
            WHERE lat IS NULL 
              AND address IS NOT NULL
        """
        msg = "Geocoding addresses with missing coordinates"

    if limit:
        query += f" LIMIT {int(limit)}"
        msg += f" (limited to {limit})"

    print(msg + "...")
    rows = conn.execute(query).fetchall()

    total = len(rows)
    if total == 0:
        print("Nothing to geocode — all addresses already have coordinates.")
        return

    print(f"Geocoding {total} addresses (Nominatim primary, Google fallback)...")

    session = requests.Session()
    geocoded = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        site_id, address, council = row["id"], row["address"], row["council"]

        if dry_run:
            print(f"  [DRY RUN] Would geocode: [{council}] {address[:80]}")
            geocoded += 1
            continue

        try:
            lat, lng, method = geocode_address(address, session, api_key)
            now = datetime.now(timezone.utc).isoformat()

            if lat is not None:
                conn.execute(
                    "UPDATE derelict_sites SET lat=?, lng=?, geocode_method=?, geocode_status=?, last_geocoded_at=? WHERE id=?",
                    (lat, lng, method, "success", now, site_id),
                )
                conn.commit()
                geocoded += 1
            else:
                conn.execute(
                    "UPDATE derelict_sites SET geocode_status=?, last_geocoded_at=? WHERE id=?",
                    ("failed", now, site_id),
                )
                conn.commit()
                logger.warning("[%s] No result: %r", council, address[:80])
                failed += 1
        except Exception as exc:
            logger.warning("[%s] Error geocoding %r: %s", council, address[:60], exc)
            failed += 1

        if i % 50 == 0 and not dry_run:
            print(f"  {i}/{total} processed ({geocoded} geocoded, {failed} failed)...")

    if dry_run:
        print(f"\n[DRY RUN] Would have processed {geocoded} addresses (no actual geocoding performed)")
    else:
        print(f"\nGeocoded {geocoded}/{total} addresses ({failed} failed)")


def print_geocoding_stats():
    """Show simple statistics about geocoding status (safe read-only operation)."""
    database.init_db()
    conn = database.get_connection()

    total = conn.execute("SELECT COUNT(*) FROM derelict_sites").fetchone()[0]
    with_coords = conn.execute("SELECT COUNT(*) FROM derelict_sites WHERE lat IS NOT NULL AND lng IS NOT NULL").fetchone()[0]
    without_coords = total - with_coords

    print("\n=== Geocoding Stats ===")
    print(f"Total records:          {total}")
    print(f"Have coordinates:       {with_coords}")
    print(f"Missing coordinates:    {without_coords}")

    # Breakdown by geocode_status (using the new tracking columns)
    try:
        rows = conn.execute("""
            SELECT COALESCE(geocode_status, 'never_attempted') as status, COUNT(*) as count
            FROM derelict_sites
            GROUP BY status
            ORDER BY count DESC
        """).fetchall()

        print("\nBy geocode_status:")
        for row in rows:
            print(f"  {row['status']}: {row['count']}")
    except Exception:
        print("\n(geocode_status column not yet populated on all rows)")

    # Breakdown by method (for records that have been geocoded)
    try:
        rows = conn.execute("""
            SELECT COALESCE(geocode_method, 'unknown') as method, COUNT(*) as count
            FROM derelict_sites
            WHERE geocode_method IS NOT NULL
            GROUP BY method
            ORDER BY count DESC
        """).fetchall()

        if rows:
            print("\nBy geocode_method:")
            for row in rows:
                print(f"  {row['method']}: {row['count']}")
    except Exception:
        pass

    print()


def show_failed_addresses(limit: int = 50):
    """Print addresses that are currently missing coordinates or marked as failed (safe, read-only)."""
    database.init_db()
    conn = database.get_connection()

    # Get all candidates
    all_rows = conn.execute("""
        SELECT council, address, geocode_status, last_geocoded_at
        FROM derelict_sites
        WHERE lat IS NULL OR geocode_status = 'failed'
        ORDER BY 
            CASE WHEN geocode_status = 'failed' THEN 0 ELSE 1 END,
            last_geocoded_at DESC NULLS LAST
    """).fetchall()

    if not all_rows:
        print("No addresses currently need geocoding attention.")
        return

    # Separate good vs poor address quality
    meaningful = []
    poor_address = []

    for row in all_rows:
        addr = (row["address"] or "").strip()
        if len(addr) >= 8:          # Very rough heuristic for "has real address text"
            meaningful.append(row)
        else:
            poor_address.append(row)

    print(f"\n=== Addresses needing geocoding attention ===")
    print(f"Total needing attention: {len(all_rows)}")
    print(f"  - With usable address text: {len(meaningful)}")
    print(f"  - Very poor / empty address: {len(poor_address)}\n")

    # Show the meaningful ones first (most useful)
    shown = 0
    for row in meaningful[:limit]:
        status = row["geocode_status"] or "missing_coords"
        last = row["last_geocoded_at"] or "never"
        addr = row["address"][:90]
        print(f"[{row['council']}] {addr}")
        print(f"    Status: {status} | Last attempt: {last}\n")
        shown += 1

    if len(meaningful) > limit:
        print(f"... and {len(meaningful) - limit} more with usable addresses.\n")

    if poor_address:
        print(f"Note: {len(poor_address)} records have very short or empty address text.")
        print("These are difficult to geocode regardless of method.\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Geocode addresses in the derelict sites database")
    parser.add_argument(
        "--failed-only", "--regeocode-failed",
        action="store_true",
        help="Only re-attempt addresses that previously failed geocoding (safest for fixing bad pins)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show geocoding statistics and exit (safe, read-only)"
    )
    parser.add_argument(
        "--show-failed", "--list-failed",
        action="store_true",
        help="List addresses that need geocoding attention (safe, read-only)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of addresses to process (especially useful with --failed-only)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be geocoded without actually calling geocoding services (safe)"
    )
    args = parser.parse_args()

    if args.stats:
        print_geocoding_stats()
    elif args.show_failed:
        show_failed_addresses(limit=args.limit or 50)
    else:
        run(only_failed=args.failed_only, limit=args.limit, dry_run=args.dry_run)
