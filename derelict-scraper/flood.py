#!/usr/bin/env python3
"""
Flood risk checker using OPW CFRAM flood extent layers.

WFS endpoint: https://www.floodinfo.ie/geoserver/wfs (OPW GeoServer)
Layers (workspace esds_floodmaps, CRS EPSG:29903 — Irish National Grid TM65):
  ext_f_c_0100 — Fluvial (river) 1-in-100 yr  → Zone A river
  ext_c_c_0200 — Coastal 1-in-200 yr           → Zone A coastal
  ext_f_c_1000 — Fluvial 1-in-1000 yr          → Zone B river
  ext_c_c_1000 — Coastal 1-in-1000 yr          → Zone B coastal

Zone A = High probability (>1% AEP river or >0.5% AEP coastal)
Zone B = Moderate probability (0.1–1% AEP river or 0.1–0.5% AEP coastal)
None   = Low / outside all mapped flood zones

flood_checked_at is only set when the API returns a definitive answer.
If the API is unreachable the property stays unchecked and is retried
on the next nightly run.
"""
import logging
import time
from pathlib import Path
from typing import Optional, Tuple
import sys

import requests

sys.path.insert(0, str(Path(__file__).parent))
import database

logger = logging.getLogger("derelict.flood")

_WFS_URL   = "https://www.floodinfo.ie/geoserver/wfs"
_DELAY     = 0.3      # seconds between requests
_TIMEOUT   = 15       # seconds per HTTP call
_MAX_ERRORS = 10      # consecutive API errors before aborting run
_BBOX_M    = 25       # metre buffer around the point for BBOX query

# CFRAM community-scale flood extent layers (confirmed from OPW GeoServer)
_ZONE_A_LAYERS = [
    "esds_floodmaps:ext_f_c_0100",  # fluvial 1-in-100 yr
    "esds_floodmaps:ext_c_c_0200",  # coastal 1-in-200 yr
]
_ZONE_B_LAYERS = [
    "esds_floodmaps:ext_f_c_1000",  # fluvial 1-in-1000 yr
    "esds_floodmaps:ext_c_c_1000",  # coastal 1-in-1000 yr
]


def _wgs84_to_ing(lat: float, lng: float) -> Tuple[float, float]:
    """Convert WGS84 lat/lng to Irish National Grid eastings/northings (EPSG:29903)."""
    from pyproj import Transformer
    tf = Transformer.from_crs("EPSG:4326", "EPSG:29903", always_xy=True)
    return tf.transform(lng, lat)


def _query_layer(lat: float, lng: float, layer: str,
                 session: requests.Session) -> Optional[bool]:
    """
    Return True if the point lies within the layer's flood polygons, False if not,
    None on any API error (caller must not mark as checked).

    Uses a 25 m bounding-box GetFeature query in Irish National Grid coordinates.
    """
    try:
        x, y = _wgs84_to_ing(lat, lng)
    except Exception as exc:
        logger.warning("Coordinate projection failed (%s, %s): %s", lat, lng, exc)
        return None

    bbox = f"{x - _BBOX_M},{y - _BBOX_M},{x + _BBOX_M},{y + _BBOX_M},EPSG:29903"
    try:
        resp = session.get(
            _WFS_URL,
            params={
                "service":      "WFS",
                "version":      "1.1.0",
                "request":      "GetFeature",
                "typeName":     layer,
                "outputFormat": "application/json",
                "maxFeatures":  "1",
                "srsName":      "EPSG:29903",
                "BBOX":         bbox,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("totalFeatures", 0) > 0
    except requests.exceptions.Timeout:
        logger.debug("WFS timeout (%.4f,%.4f) layer=%s", lat, lng, layer)
        return None
    except requests.exceptions.ConnectionError:
        logger.debug("WFS connection error (%.4f,%.4f)", lat, lng)
        return None
    except Exception as exc:
        logger.debug("WFS error (%.4f,%.4f) layer=%s: %s", lat, lng, layer, exc)
        return None


def _in_any_layer(lat: float, lng: float, layers: list,
                  session: requests.Session) -> Optional[bool]:
    """
    Check a list of layers sequentially. Returns True on first hit, False if all miss,
    None if any layer returns an API error (so the property stays unclassified).
    """
    for layer in layers:
        result = _query_layer(lat, lng, layer, session)
        if result is None:
            return None   # API error — propagate upward
        if result:
            return True
        time.sleep(_DELAY)
    return False


def get_flood_risk(lat: float, lng: float,
                   session: Optional[requests.Session] = None) -> Optional[dict]:
    """
    Returns {"flood_zone": "A"|"B"|None, "flood_risk": "High"|"Moderate"|"Low"}
    or None if the OPW API was unreachable (caller should not mark as checked).
    """
    s = session or requests.Session()

    in_a = _in_any_layer(lat, lng, _ZONE_A_LAYERS, s)
    if in_a is None:
        return None
    if in_a:
        return {"flood_zone": "A", "flood_risk": "High"}

    in_b = _in_any_layer(lat, lng, _ZONE_B_LAYERS, s)
    if in_b is None:
        return None
    if in_b:
        return {"flood_zone": "B", "flood_risk": "Moderate"}

    return {"flood_zone": None, "flood_risk": "Low"}


def run():
    """
    Check flood risk for all geocoded properties not yet flood-checked.
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
        "Accept":     "application/json",
    })

    checked = high = moderate = low = api_errors = 0

    for i, row in enumerate(rows, 1):
        if api_errors >= _MAX_ERRORS:
            logger.warning(
                "OPW API appears to be down (%d consecutive errors) — "
                "stopping flood check, will retry tomorrow", api_errors
            )
            break

        result = get_flood_risk(row["lat"], row["lng"], session)

        if result is None:
            api_errors += 1
            continue

        api_errors = 0
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
