#!/usr/bin/env python3
import os
import re
import sys
import time
import logging
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

_SMART_QUOTES = str.maketrans({
    '‘': '', '’': '',  # ' '
    '“': '', '”': '',  # " "
    '′': '', '″': '',  # ′ ″
})


def clean_address(address: str) -> str:
    address = address.translate(_SMART_QUOTES)
    address = re.sub(r'\n+', ', ', address)
    address = re.sub(r'[ \t]+', ' ', address).strip().strip(',').strip()
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
        resp = session.get(
            _GOOGLE_URL,
            params={"address": f"{address}, Ireland", "key": api_key},
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
                    api_key: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    cleaned = clean_address(raw_address)
    eircode = extract_eircode(cleaned)
    address_no_eircode = _strip_eircode(cleaned) if eircode else cleaned

    # 1. Eircode alone — most precise for Irish addresses
    if eircode:
        lat, lng = geocode_with_nominatim(f"{eircode}, Ireland", session)
        time.sleep(_NOMINATIM_DELAY)
        if lat is not None:
            return lat, lng

    # 2. Full cleaned address (eircode stripped to avoid confusing geocoder)
    lat, lng = geocode_with_nominatim(f"{address_no_eircode}, Ireland", session)
    time.sleep(_NOMINATIM_DELAY)
    if lat is not None:
        return lat, lng

    # 3. Google Maps fallback
    if api_key:
        lat, lng = geocode_with_google(address_no_eircode, session, api_key)
        time.sleep(_GOOGLE_DELAY)
        if lat is not None:
            return lat, lng

    return None, None


def run(db_path=None):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set — will use Nominatim only (no Google fallback)")

    if db_path:
        database.DB_PATH = Path(db_path)

    database.init_db()
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT id, address, council FROM derelict_sites WHERE lat IS NULL AND address IS NOT NULL"
    ).fetchall()

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
        try:
            lat, lng = geocode_address(address, session, api_key)
            if lat is not None:
                conn.execute(
                    "UPDATE derelict_sites SET lat=?, lng=? WHERE id=?",
                    (lat, lng, site_id),
                )
                conn.commit()
                geocoded += 1
            else:
                logger.warning("[%s] No result: %r", council, address[:80])
                failed += 1
        except Exception as exc:
            logger.warning("[%s] Error geocoding %r: %s", council, address[:60], exc)
            failed += 1

        if i % 50 == 0:
            print(f"  {i}/{total} processed ({geocoded} geocoded, {failed} failed)...")

    print(f"\nGeocoded {geocoded}/{total} addresses ({failed} failed)")


if __name__ == "__main__":
    run()
