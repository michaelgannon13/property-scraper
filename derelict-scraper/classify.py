#!/usr/bin/env python3
"""Backfill property_type for all rows in the database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database
from utils import classify_property_type


def run(db_path=None):
    if db_path:
        database.DB_PATH = Path(db_path)

    database.init_db()
    conn = database.get_connection()

    rows = conn.execute("SELECT id, address FROM derelict_sites").fetchall()
    total = len(rows)

    updated = 0
    for row in rows:
        prop_type = classify_property_type(row["address"])
        conn.execute(
            "UPDATE derelict_sites SET property_type=? WHERE id=?",
            (prop_type, row["id"]),
        )
        updated += 1

    conn.commit()
    print(f"Classified {updated}/{total} properties.")

    counts = conn.execute(
        "SELECT property_type, COUNT(*) as n FROM derelict_sites GROUP BY property_type ORDER BY n DESC"
    ).fetchall()
    print("\nBreakdown:")
    for r in counts:
        print(f"  {r['property_type']:15s}: {r['n']}")


if __name__ == "__main__":
    run()
