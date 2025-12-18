#!/usr/bin/env python3
"""
Match portfolio buildings to store locations using proper Haversine distance.
Find buildings with missing or incorrect tenant info.
"""

import csv
import math
from collections import defaultdict
from pathlib import Path

PORTFOLIO_PATH = Path("/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv")
STORES_PATH = Path("/Users/forrestmiller/Desktop/new data/all_stores.csv")
OUTPUT_PATH = Path("/Users/forrestmiller/Desktop/new data/matched_buildings.csv")

# Building types to match
TARGET_BUILDING_TYPES = {"Retail Store", "Wholesale Club", "Supermarket/Grocery"}

# Distance threshold in meters
MATCH_THRESHOLD_METERS = 50


def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on Earth.
    Returns distance in meters.
    """
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def normalize_city(city):
    """Normalize city name for grouping."""
    city = city.strip().lower()
    # Handle NYC boroughs
    if city in {"manhattan", "brooklyn", "queens", "bronx", "staten island", "new york city"}:
        return "new york"
    return city


def load_stores():
    """Load store locations and group by city."""
    stores_by_city = defaultdict(list)

    with open(STORES_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError):
                continue

            city = normalize_city(row.get("city", ""))
            state = row.get("state", "").strip().upper()

            stores_by_city[(city, state)].append({
                "retailer": row.get("retailer", ""),
                "store_name": row.get("store_name", ""),
                "street": row.get("street", ""),
                "city": row.get("city", ""),
                "state": state,
                "zip": row.get("zip", ""),
                "lat": lat,
                "lon": lon,
            })

    return stores_by_city


def load_buildings():
    """Load portfolio buildings (retail/wholesale/grocery only) and group by city."""
    buildings_by_city = defaultdict(list)
    total_relevant = 0

    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_type = row.get("building_type", "").strip()
            if building_type not in TARGET_BUILDING_TYPES:
                continue

            total_relevant += 1

            try:
                lat = float(row.get("latitude", ""))
                lon = float(row.get("longitude", ""))
            except (ValueError, TypeError):
                continue

            city = normalize_city(row.get("city", ""))
            state = row.get("state", "").strip().upper()

            buildings_by_city[(city, state)].append({
                "building_id": row.get("building_id", ""),
                "address": row.get("address", ""),
                "building_type": building_type,
                "tenant": row.get("tenant", "").strip(),
                "city": row.get("city", ""),
                "state": state,
                "zip_code": row.get("zip_code", ""),
                "lat": lat,
                "lon": lon,
            })

    print(f"[INFO] Loaded {total_relevant} relevant buildings ({len(buildings_by_city)} cities with lat/lon)")
    return buildings_by_city


def find_matches(buildings_by_city, stores_by_city):
    """Find buildings that match stores within threshold distance."""
    matches = []
    comparisons = 0

    for (city, state), buildings in buildings_by_city.items():
        stores = stores_by_city.get((city, state), [])
        if not stores:
            continue

        for building in buildings:
            best_match = None
            best_distance = float("inf")

            for store in stores:
                comparisons += 1
                distance = haversine(
                    building["lat"], building["lon"],
                    store["lat"], store["lon"]
                )

                if distance < best_distance:
                    best_distance = distance
                    best_match = store

            # Check if within threshold
            if best_match and best_distance <= MATCH_THRESHOLD_METERS:
                current_tenant = building["tenant"]
                expected_retailer = best_match["retailer"]

                # Check if tenant is missing or different
                tenant_missing = not current_tenant
                tenant_mismatch = (
                    current_tenant and
                    expected_retailer.lower() not in current_tenant.lower() and
                    current_tenant.lower() not in expected_retailer.lower()
                )

                if tenant_missing or tenant_mismatch:
                    matches.append({
                        "building_id": building["building_id"],
                        "building_address": building["address"],
                        "building_type": building["building_type"],
                        "building_lat": building["lat"],
                        "building_lon": building["lon"],
                        "current_tenant": current_tenant if current_tenant else "(MISSING)",
                        "matched_retailer": expected_retailer,
                        "store_name": best_match["store_name"],
                        "store_address": best_match["street"],
                        "store_lat": best_match["lat"],
                        "store_lon": best_match["lon"],
                        "distance_meters": round(best_distance, 2),
                        "issue": "MISSING_TENANT" if tenant_missing else "WRONG_TENANT",
                    })

    print(f"[INFO] Made {comparisons:,} distance comparisons")
    return matches


def write_output(matches):
    """Write matched buildings to CSV."""
    if not matches:
        print("[WARN] No matches found")
        return

    fieldnames = [
        "building_id", "building_address", "building_type",
        "current_tenant", "matched_retailer", "store_name",
        "distance_meters", "issue",
        "building_lat", "building_lon", "store_lat", "store_lon", "store_address"
    ]

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for match in sorted(matches, key=lambda x: x["distance_meters"]):
            writer.writerow(match)

    print(f"[OK] Wrote {len(matches)} matches to {OUTPUT_PATH}")


def main():
    print("=" * 70)
    print("Matching Portfolio Buildings to Store Locations")
    print(f"Distance threshold: {MATCH_THRESHOLD_METERS} meters")
    print("=" * 70)

    # Load data
    print("\n[INFO] Loading stores...")
    stores_by_city = load_stores()
    print(f"[INFO] Loaded {sum(len(v) for v in stores_by_city.values())} stores in {len(stores_by_city)} cities")

    print("\n[INFO] Loading buildings...")
    buildings_by_city = load_buildings()

    # Find matches
    print("\n[INFO] Finding matches...")
    matches = find_matches(buildings_by_city, stores_by_city)

    # Summarize
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    missing_tenant = [m for m in matches if m["issue"] == "MISSING_TENANT"]
    wrong_tenant = [m for m in matches if m["issue"] == "WRONG_TENANT"]

    print(f"Buildings with MISSING tenant: {len(missing_tenant)}")
    print(f"Buildings with WRONG tenant:   {len(wrong_tenant)}")
    print(f"TOTAL matches to review:       {len(matches)}")

    # Show by retailer
    print("\nBy retailer:")
    by_retailer = defaultdict(int)
    for m in matches:
        by_retailer[m["matched_retailer"]] += 1
    for retailer, count in sorted(by_retailer.items(), key=lambda x: -x[1]):
        print(f"  {retailer}: {count}")

    # Write output
    print()
    write_output(matches)

    # Show sample matches
    if matches:
        print("\n" + "=" * 70)
        print("SAMPLE MATCHES (closest first)")
        print("=" * 70)
        for m in sorted(matches, key=lambda x: x["distance_meters"])[:10]:
            print(f"\n{m['building_id']}: {m['building_address']}")
            print(f"  Current tenant: {m['current_tenant']}")
            print(f"  Should be:      {m['matched_retailer']} ({m['store_name']})")
            print(f"  Distance:       {m['distance_meters']} meters")
            print(f"  Issue:          {m['issue']}")


if __name__ == "__main__":
    main()
