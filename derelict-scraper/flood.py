#!/usr/bin/env python3
"""
Flood risk checker using the OPW (Office of Public Works) CFRAM flood zone maps.
Queries the public ArcGIS REST API — no API key required.

Flood zones:
  A = High probability   (>1% annual chance of flooding)
  B = Moderate probability (0.1–1% annual chance)
  None = Low / outside mapped zones

flood_checked_at is only set when the API returns a definitive answer.
If the API is unreachable or errors, the property stays unchecked and
will be retried on the next nightly run.
"""
import logging
import time
from pathlib import Path
from typing import Optional
import sys

import requests

sys.path.insert(0, str(Path(__file__).parent))
import database

logger = logging.getLogger("derelict.flood")

_OPW_BASE = "https://gis.floodinfo.ie/arcgis/rest/services/CFRAM/FZ_IE_CFRAM_PAFRA/MapServer"
_DELAY = 0.25       # seconds between requests
_TIMEOUT = 10       # seconds per HTTP call
_MAX_ERRORS = 10    # stop early if API appears to be down


def _query_zone(lat: float, lng: float, layer: int,
                session: requests.Session) -> Optional[bool]:
    """
    Return True if point is in the zone, False if not, None if the API failed.
    None means: don't mark as checked — retry next run.
    """
    try:
        resp = session.get(
            f"{_OPW_BASE}/{layer}/query",
            params={
                "geometry": f"{lng},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "OBJECTID",
                "returnGeometry": "false",
                "returnCountOnly": "true",
                "f": "json",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.debug("OPW layer %d error: %s", layer, data["error"])
            return None
        return data.get("count", 0) > 0
    except requests.exceptions.Timeout:
        logger.debug("OPW layer %d timeout (%.4f,%.4f)", layer, lat, lng)
        return None
    except requests.exceptions.ConnectionError:
        logger.debug("OPW layer %d connection error (%.4f,%.4f)", layer, lat, lng)
        return None
    except Exception as exc:
        logger.debug("OPW layer %d unexpected error (%.4f,%.4f): %s", layer, lat, lng, exc)
        return None


def get_flood_risk(lat: float, lng: float,
                   session: Optional[requests.Session] = None) -> Optional[dict]:
    """
    Returns {"flood_zone": "A"|"B"|None, "flood_risk": "High"|"Moderate"|"Low"}
    on success, or None if the API was unreachable (caller should not mark as checked).
    """
    s = session or requests.Session()

    in_a = _query_zone(lat, lng, layer=0, session=s)
    if in_a is None:
        return None  # API failed — don't mark as checked
    if in_a:
        return {"flood_zone": "A", "flood_risk": "High"}

    time.sleep(_DELAY)
    in_b = _query_zone(lat, lng, layer=1, session=s)
    if in_b is None:
        return None  # API failed — don't mark as checked
    if in_b:
        return {"flood_zone": "B", "flood_risk": "Moderate"}

    return {"flood_zone": None, "flood_risk": "Low"}


def run():
    """
    Check flood risk for all geocoded properties not yet checked.
    Safe to call every night — skips already-checked properties.
    Stops early if the OPW API appears to be down.
    """
    from datetime import date
    today = date.today().isoformat()

    conn = database.get_connection()
    rows = conn.execute(
        """SELECT id, lat, lng FROM derelict_sites
           WHERE lat IS NOT NULL AND lng IS NOT NULL
           AND flood_checked_at IS NULL""",
    ).fetchall()

    total = len(rows)
    if total == 0:
        logger.info("Flood risk: all geocoded properties already checked.")
        return

    print(f"Checking flood risk for {total} properties...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; ReviveIreland/1.0)",
        "Accept": "application/json",
    })

    checked = high = moderate = low = api_errors = 0

    for i, row in enumerate(rows, 1):
        # Bail out early if the API is consistently failing
        if api_errors >= _MAX_ERRORS:
            logger.warning(
                "OPW API appears to be down (%d consecutive errors) — "
                "stopping flood check, will retry tomorrow", api_errors
            )
            break

        result = get_flood_risk(row["lat"], row["lng"], session)

        if result is None:
            # API failure — do NOT set flood_checked_at, retry next run
            api_errors += 1
            continue

        api_errors = 0  # reset on success
        conn.execute(
            """UPDATE derelict_sites
               SET flood_zone = ?, flood_risk = ?, flood_checked_at = ?
               WHERE id = ?""",
            (result["flood_zone"], result["flood_risk"], today, row["id"]),
        )
        conn.commit()
        checked += 1

        if result["flood_risk"] == "High":
            high += 1
        elif result["flood_risk"] == "Moderate":
            moderate += 1
        else:
            low += 1

        if i % 100 == 0:
            print(f"  {i}/{total} checked — {high} High, {moderate} Moderate, {low} Low")

        time.sleep(_DELAY)

    skipped = total - checked
    print(f"Flood check complete: {high} High, {moderate} Moderate, {low} Low"
          + (f", {skipped} skipped (API errors — will retry)" if skipped else ""))
    logger.info("Flood check: %d checked, %d High, %d Moderate, %d Low, %d skipped",
                checked, high, moderate, low, skipped)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    run()
