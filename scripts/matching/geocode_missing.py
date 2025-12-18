#!/usr/bin/env python3
"""
Geocode missing lat/lon values using Google Geocoding API.
"""

import csv
import time
import os
import urllib.request
import urllib.parse
import json
from pathlib import Path

API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OUTPUT_DIR = Path("/Users/forrestmiller/Desktop/new data")

def geocode_address(street, city, state, zipcode):
    """Get lat/lon for an address using Google Geocoding API."""
    address = f"{street}, {city}, {state} {zipcode}"
    params = urllib.parse.urlencode({
        "address": address,
        "key": API_KEY
    })
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())

        if data["status"] == "OK" and data["results"]:
            location = data["results"][0]["geometry"]["location"]
            return str(location["lat"]), str(location["lng"])
        else:
            print(f"  [WARN] No results for: {address} ({data.get('status', 'unknown')})")
            return "", ""
    except Exception as e:
        print(f"  [ERROR] {address}: {e}")
        return "", ""


def process_csv(filepath):
    """Read CSV, geocode missing coords, write back."""
    print(f"\n[INFO] Processing {filepath.name}")

    rows = []
    missing_count = 0
    geocoded_count = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        for row in reader:
            rows.append(row)
            if not row.get("lat") or not row.get("lon"):
                missing_count += 1

    print(f"  Found {missing_count} rows missing coordinates")

    if missing_count == 0:
        return 0

    # Geocode missing entries
    for i, row in enumerate(rows):
        if not row.get("lat") or not row.get("lon"):
            lat, lon = geocode_address(
                row.get("street", ""),
                row.get("city", ""),
                row.get("state", ""),
                row.get("zip", "")
            )
            if lat and lon:
                row["lat"] = lat
                row["lon"] = lon
                geocoded_count += 1
                print(f"  [{geocoded_count}/{missing_count}] {row.get('store_name', '')}: {lat}, {lon}")

            # Rate limit: ~10 requests per second max
            time.sleep(0.1)

    # Write back
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  [OK] Geocoded {geocoded_count}/{missing_count} addresses")
    return geocoded_count


def rebuild_all_stores():
    """Rebuild all_stores.csv from individual files."""
    print("\n[INFO] Rebuilding all_stores.csv...")

    all_rows = []
    fieldnames = ["retailer", "store_name", "street", "city", "state", "zip", "phone", "lat", "lon"]

    for filename in ["walmart_stores.csv", "target_stores.csv", "costco_stores.csv",
                     "homedepot_stores.csv", "lowes_stores.csv"]:
        filepath = OUTPUT_DIR / filename
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    all_rows.append(row)

    with open(OUTPUT_DIR / "all_stores.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"  [OK] Wrote {len(all_rows)} total records")


def main():
    print("=" * 60)
    print("Geocoding Missing Coordinates")
    print("=" * 60)

    total_geocoded = 0

    # Process files that need geocoding
    for filename in ["walmart_stores.csv", "homedepot_stores.csv", "lowes_stores.csv"]:
        filepath = OUTPUT_DIR / filename
        if filepath.exists():
            total_geocoded += process_csv(filepath)

    # Rebuild combined file
    rebuild_all_stores()

    print("\n" + "=" * 60)
    print(f"DONE - Geocoded {total_geocoded} addresses")
    print("=" * 60)


if __name__ == "__main__":
    main()
