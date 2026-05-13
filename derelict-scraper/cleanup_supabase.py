#!/usr/bin/env python3
"""
One-time cleanup: deletes Supabase rows that no longer exist in SQLite.
Run from the derelict-scraper directory: python cleanup_supabase.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database
import requests

CLEANUP_URL = "https://wpgrcieidaalkkgococi.supabase.co/functions/v1/cleanup_orphans"


def main():
    conn = database.get_connection()

    councils = [r[0] for r in conn.execute(
        "SELECT DISTINCT council FROM derelict_sites"
    ).fetchall()]

    print(f"Building valid ref list for {len(councils)} councils...")

    payload = []
    for council in sorted(councils):
        refs = [r[0] for r in conn.execute(
            "SELECT ds_ref FROM derelict_sites WHERE council = ? AND ds_ref IS NOT NULL",
            (council,),
        ).fetchall()]
        payload.append({"council": council, "valid_refs": refs})
        print(f"  {council}: {len(refs)} valid refs in SQLite")

    print("\nCalling cleanup_orphans edge function...")
    resp = requests.post(
        CLEANUP_URL,
        json={"councils": payload},
        headers={
            "x-api-key": database._INGEST_API_KEY,
            "Authorization": f"Bearer {database._ANON_KEY}",
            "apikey": database._ANON_KEY,
            "Content-Type": "application/json",
        },
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()

    print(f"\nDeleted {result.get('deleted', 0)} orphaned properties from Supabase")
    if result.get("errors"):
        print("Errors:")
        for e in result["errors"]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
