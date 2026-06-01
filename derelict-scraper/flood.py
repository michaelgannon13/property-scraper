#!/usr/bin/env python3
"""
Flood risk checker using the OPW (Office of Public Works) CFRAM flood zone maps.
Queries the public ArcGIS REST API — no API key required.

Flood zones:
  A = High probability   (>1% annual chance of flooding)
  B = Moderate probability (0.1–1% annual chance)
  None = Low / outside mapped zones
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

# OPW CFRAM flood zone layers via ArcGIS REST
# Layer 0 = Zone A (high), Layer 1 = Zone B (moderate)
_OPW_BASE = "https://gis.floodinfo.ie/arcgis/rest/services/CFRAM/FZ_IE_CFRAM_PAFRA/MapServer"
_DELAY = 0.2  # seconds between requests — be a good citizen


def _query_zone(lat: float, lng: float, layer: int, session: requests.Session) -> bool:
    """Return True if the point falls within the given OPW flood zone layer."""
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
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.debug("OPW layer %d error: %s", layer, data["error"])
            return False
        return data.get("count", 0) > 0
    except Exception as exc:
        logger.debug("OPW layer %d query failed (%.4f,%.4f): %s", layer, lat, lng, exc)
        return False


def get_flood_risk(lat: float, lng: float,
                   session: Optional[requests.Session] = None) -> dict:
    """
    Returns {"flood_zone": "A"|"B"|None, "flood_risk": "High"|"Moderate"|"Low"}.
    Zone A (high) is checked first; if not in A, check Zone B.
    """
    s = session or requests.Session()
    if _query_zone(lat, lng, layer=0, session=s):
        return {"flood_zone": "A", "flood_risk": "High"}
    time.sleep(_DELAY)
    if _query_zone(lat, lng, layer=1, session=s):
        return {"flood_zone": "B", "flood_risk": "Moderate"}
    return {"flood_zone": None, "flood_risk": "Low"}


def run():
    """Check flood risk for all geocoded properties that haven't been checked yet."""
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
        print("Flood risk: all geocoded properties already checked.")
        return

    print(f"Checking flood risk for {total} properties...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; ReviveIreland/1.0)",
        "Accept": "application/json",
    })

    checked = high = moderate = 0
    for i, row in enumerate(rows, 1):
        result = get_flood_risk(row["lat"], row["lng"], session)
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

        if i % 50 == 0:
            print(f"  {i}/{total} checked ({high} high risk, {moderate} moderate)...")
        time.sleep(_DELAY)

    print(f"\nFlood check complete: {high} High, {moderate} Moderate, "
          f"{checked - high - moderate} Low risk")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    run()
