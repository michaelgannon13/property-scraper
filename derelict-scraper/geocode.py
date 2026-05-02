#!/usr/bin/env python3
import os
import sys
import time
import logging
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import database

logger = logging.getLogger("derelict.geocode")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_DELAY = 0.05  # 50 ms between requests — well under Google's rate limit


def geocode_address(address: str, session: requests.Session, api_key: str):
    resp = session.get(
        _GEOCODE_URL,
        params={"address": f"{address}, Ireland", "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["status"] == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None


def run(db_path=None):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        sys.exit("Error: GOOGLE_MAPS_API_KEY environment variable is not set")

    if db_path:
        import database as _db
        _db.DB_PATH = Path(db_path)

    conn = database.get_connection()
    rows = conn.execute(
        "SELECT id, address, council FROM derelict_sites WHERE lat IS NULL AND address IS NOT NULL"
    ).fetchall()

    total = len(rows)
    if total == 0:
        print("Nothing to geocode — all addresses already have coordinates.")
        return

    print(f"Geocoding {total} addresses...")

    session = requests.Session()
    geocoded = 0
    failed = 0

    for row in rows:
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
                logger.warning("No result for [%s] %r", council, address)
                failed += 1
        except Exception as exc:
            logger.warning("Failed to geocode [%s] %r: %s", council, address, exc)
            failed += 1
        time.sleep(_DELAY)

    print(f"Geocoded {geocoded}/{total} addresses ({failed} failed)")


if __name__ == "__main__":
    run()
