#!/usr/bin/env python3
"""
Flood risk checker using the OPW (Office of Public Works) GeoServer WFS.
Service: https://maps.opw.ie/geoserver/ows
No API key required.

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

_WFS_URL = "https://maps.opw.ie/geoserver/ows"
_DELAY = 0.25
_TIMEOUT = 15
_MAX_ERRORS = 10

# These layer names are discovered at runtime via GetCapabilities.
# Overrideable via env var for future-proofing.
import os
_LAYER_ZONE_A = os.getenv("OPW_FLOOD_LAYER_A", "")
_LAYER_ZONE_B = os.getenv("OPW_FLOOD_LAYER_B", "")


def _discover_flood_layers(session: requests.Session) -> tuple[str, str]:
    """
    Query WFS GetCapabilities and find the flood zone A and B layer names.
    Returns (layer_a, layer_b) or ("", "") on failure.
    """
    try:
        resp = session.get(
            _WFS_URL,
            params={"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.text.lower()

        # Parse layer names containing flood zone keywords
        import re
        names = re.findall(r'<name>([^<]+)</name>', resp.text)
        zone_a = next((n for n in names if "zone" in n.lower() and
                       ("_a" in n.lower() or "zonea" in n.lower() or "zone_a" in n.lower())), "")
        zone_b = next((n for n in names if "zone" in n.lower() and
                       ("_b" in n.lower() or "zoneb" in n.lower() or "zone_b" in n.lower())), "")

        if zone_a and zone_b:
            logger.info("Discovered flood zone layers: A=%s B=%s", zone_a, zone_b)
        else:
            # Fallback: log all flood-related layers found so we can identify them
            flood_layers = [n for n in names if "flood" in n.lower() or "zone" in n.lower()]
            logger.warning("Could not auto-detect zone A/B layers. Flood-related layers found: %s",
                           flood_layers)
        return zone_a, zone_b
    except Exception as exc:
        logger.warning("GetCapabilities failed: %s", exc)
        return "", ""


def _query_zone_wfs(lat: float, lng: float, layer: str,
                    session: requests.Session) -> Optional[bool]:
    """
    Return True if point is within the layer, False if not, None on API error.
    Uses WFS CQL_FILTER with INTERSECTS for a point query.
    """
    if not layer:
        return None
    try:
        resp = session.get(
            _WFS_URL,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetPropertyValue",
                "typeNames": layer,
                "valueReference": "@gml:id",
                "CQL_FILTER": f"INTERSECTS(the_geom,POINT({lng} {lat}))",
                "outputFormat": "application/json",
                "count": "1",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return len(data.get("values", [])) > 0
    except requests.exceptions.Timeout:
        logger.debug("WFS timeout (%.4f,%.4f) layer=%s", lat, lng, layer)
        return None
    except requests.exceptions.ConnectionError:
        logger.debug("WFS connection error (%.4f,%.4f)", lat, lng)
        return None
    except Exception as exc:
        logger.debug("WFS error (%.4f,%.4f) layer=%s: %s", lat, lng, layer, exc)
        return None


def get_flood_risk(lat: float, lng: float, layer_a: str, layer_b: str,
                   session: Optional[requests.Session] = None) -> Optional[dict]:
    """
    Returns {"flood_zone": "A"|"B"|None, "flood_risk": "High"|"Moderate"|"Low"}
    or None if the API was unreachable (caller should not mark as checked).
    """
    s = session or requests.Session()

    in_a = _query_zone_wfs(lat, lng, layer_a, s)
    if in_a is None:
        return None
    if in_a:
        return {"flood_zone": "A", "flood_risk": "High"}

    time.sleep(_DELAY)
    in_b = _query_zone_wfs(lat, lng, layer_b, s)
    if in_b is None:
        return None
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

    # Discover layer names (or use env var overrides)
    layer_a = _LAYER_ZONE_A or ""
    layer_b = _LAYER_ZONE_B or ""
    if not layer_a or not layer_b:
        layer_a, layer_b = _discover_flood_layers(session)

    if not layer_a or not layer_b:
        logger.warning(
            "OPW flood zone layers could not be determined — skipping flood check. "
            "Set OPW_FLOOD_LAYER_A and OPW_FLOOD_LAYER_B env vars to override."
        )
        return

    checked = high = moderate = low = api_errors = 0

    for i, row in enumerate(rows, 1):
        if api_errors >= _MAX_ERRORS:
            logger.warning(
                "OPW API appears to be down (%d consecutive errors) — "
                "stopping flood check, will retry tomorrow", api_errors
            )
            break

        result = get_flood_risk(row["lat"], row["lng"], layer_a, layer_b, session)

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
