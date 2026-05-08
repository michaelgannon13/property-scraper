#!/usr/bin/env python3
"""
Enrich derelict properties with estimated floor area using Microsoft
Global ML Building Footprints (satellite-derived polygons, free, open data).

For each property with lat/lng, we find the building polygon it sits inside,
calculate the footprint area in m², multiply by estimated floor count based
on property type, and store the result.

Source: https://github.com/microsoft/GlobalMLBuildingFootprints
Licence: ODbL
"""
import gzip
import io
import json
import logging
import sys
from pathlib import Path

import requests
from shapely.geometry import Point, Polygon, shape
from shapely.strtree import STRtree
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent))
import database

log = logging.getLogger("derelict.floor_area")

CACHE_DIR = Path("data/buildings_cache")
DATASET_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
CACHE_FILE = CACHE_DIR / "ireland_buildings.geojsonl"

# Irish Transverse Mercator — accurate area calculations in m²
_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:2157", always_xy=True)

# Default floor counts by property type
_FLOOR_COUNTS = {
    "residential": 2,
    "commercial":  2,
    "industrial":  1,
    "mixed":       2,
}
_DEFAULT_FLOORS = 2

# Nearest-building fallback tolerance (~15m in degrees at Irish latitudes)
_PROXIMITY_DEG = 0.00015


def _floor_count(property_type: str) -> int:
    if not property_type:
        return _DEFAULT_FLOORS
    return _FLOOR_COUNTS.get(property_type.lower(), _DEFAULT_FLOORS)


def _footprint_m2(polygon: Polygon) -> float:
    xs, ys = zip(*[
        _TRANSFORMER.transform(x, y)
        for x, y in polygon.exterior.coords
    ])
    return Polygon(zip(xs, ys)).area


def _download_ireland_footprints() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        log.info("Using cached footprints at %s", CACHE_FILE)
        return

    log.info("Fetching dataset index from Microsoft...")
    resp = requests.get(DATASET_LINKS_URL, timeout=60)
    resp.raise_for_status()

    import pandas as pd
    links = pd.read_csv(io.StringIO(resp.text))
    ireland = links[links["Location"] == "Ireland"]

    if ireland.empty:
        raise RuntimeError("No Ireland entries in dataset-links.csv — check URL or column names")

    log.info("Downloading %d Ireland partition(s)...", len(ireland))
    with open(CACHE_FILE, "w") as out:
        for _, row in ireland.iterrows():
            url = row["Url"]
            log.info("  %s", url)
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as gz:
                for line in gz:
                    out.write(line)

    log.info("Saved %s (%.1f MB)", CACHE_FILE, CACHE_FILE.stat().st_size / 1e6)


def _build_spatial_index():
    log.info("Loading building polygons into memory...")
    geometries = []
    errors = 0

    with open(CACHE_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                feature = json.loads(line)
                geometries.append(shape(feature["geometry"]))
            except Exception:
                errors += 1

    log.info("Loaded %d polygons (%d parse errors), building index...", len(geometries), errors)
    tree = STRtree(geometries)
    log.info("Spatial index ready")
    return geometries, tree


def run(force: bool = False) -> None:
    conn = database.get_connection()

    # Add columns if they don't exist yet
    for col, coltype in (("floor_area_m2", "REAL"), ("floor_area_source", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE derelict_sites ADD COLUMN {col} {coltype}")
            conn.commit()
        except Exception:
            pass

    where = (
        "lat IS NOT NULL AND lng IS NOT NULL"
        if force else
        "lat IS NOT NULL AND lng IS NOT NULL AND floor_area_m2 IS NULL"
    )
    props = conn.execute(
        f"SELECT id, address, lat, lng, property_type FROM derelict_sites WHERE {where}"
    ).fetchall()

    if not props:
        log.info("No properties need floor area enrichment")
        return

    log.info("%d properties to enrich", len(props))

    _download_ireland_footprints()
    geometries, tree = _build_spatial_index()

    enriched = not_found = 0

    for row in props:
        prop_id, address, lat, lng, property_type = (
            row["id"], row["address"], row["lat"], row["lng"], row["property_type"]
        )
        point = Point(lng, lat)  # shapely: (x=lon, y=lat)

        # 1. Point-in-polygon (exact hit)
        footprint = None
        for idx in tree.query(point):
            if geometries[idx].contains(point):
                footprint = geometries[idx]
                break

        # 2. Nearest-building fallback for slightly off coordinates
        if footprint is None:
            nearest_idx = tree.nearest(point)
            if nearest_idx is not None:
                candidate = geometries[nearest_idx]
                if point.distance(candidate) <= _PROXIMITY_DEG:
                    footprint = candidate

        if footprint is None:
            not_found += 1
            log.debug("No building found for: %s", address)
            continue

        total_m2 = round(_footprint_m2(footprint) * _floor_count(property_type), 1)

        conn.execute(
            "UPDATE derelict_sites SET floor_area_m2 = ?, floor_area_source = ? WHERE id = ?",
            (total_m2, "msft_footprint", prop_id),
        )
        enriched += 1

    conn.commit()
    print(f"\nFloor area: {enriched} enriched │ {not_found} no building found")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Re-enrich all properties, not just missing ones")
    args = p.parse_args()
    database.init_db()
    run(force=args.force)
